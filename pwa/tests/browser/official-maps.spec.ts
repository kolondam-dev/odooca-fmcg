import { expect, test, type Page } from "@playwright/test";
test.use({ baseURL: "http://127.0.0.1:4175/field/" });
const identity = {
    id: "41",
    companyId: "7",
    name: "Map Staging",
    title: "",
    roles: ["sales"],
    businessDate: "2026-10-30",
};
const office = {
    id: "4",
    name: "Server Office",
    latitude: -6.2,
    longitude: 106.8,
    radius: 50,
    coordinate_status: "unverified",
};
const outlet = {
    id: "12",
    name: "Assigned Server Outlet",
    channel: "GT",
    address: "Test",
    distance: "",
    time: "",
    latitude: 1.465,
    longitude: 124.833,
    radius: 10,
};
async function setup(page: Page, withOffice = true) {
    await page.clock.install({ time: new Date("2026-10-30T01:00:00Z") });
    const requests: string[] = [];
    await page.route("**/api/**", async (route) => {
        requests.push(route.request().method());
        await route.fulfill({
            contentType: "application/json",
            body: JSON.stringify(
                route.request().url().endsWith("bootstrap")
                    ? identity
                    : {
                          catalog_version: 2,
                          scope: {
                              company_id: "7",
                              user_id: "41",
                              warehouse_id: "9",
                              business_date: identity.businessDate,
                          },
                          version: "server-map-snapshot",
                          updatedAt: "2026-10-30T01:00:00Z",
                          outlets: [outlet],
                          products: [],
                          deliveries: [],
                          ...(withOffice ? { office } : {}),
                      },
            ),
        });
    });
    await page.goto("./");
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await expect(
        page.getByText("Daily sync berhasil.", { exact: true }),
    ).toBeVisible();
    return requests;
}
test("staging previews server office/outlet and GPS without writes or persistence", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: -6.201,
        longitude: 106.801,
        accuracy: 15,
    });
    const requests = await setup(page);
    const panel = page.getByRole("region", {
        name: "Preview lokasi check-in staging",
        exact: true,
    });
    await expect(panel).toContainText("Belum diverifikasi");
    await expect(panel).toContainText("-6.200000, 106.800000");
    await panel
        .getByRole("button", {
            name: "Ambil posisi untuk preview",
            exact: true,
        })
        .click();
    await expect(panel).toContainText("-6.201000, 106.801000");
    await panel.getByLabel("Tujuan preview staging").selectOption("outlet:12");
    await expect(panel).toContainText("1.465000, 124.833000");
    await expect(panel).not.toContainText("-6.201000, 106.801000");
    await panel
        .getByRole("button", {
            name: "Ambil posisi untuk preview",
            exact: true,
        })
        .click();
    await expect(panel).toContainText("Di luar radius");
    expect(requests.every((method) => method === "GET")).toBe(true);
    expect(
        await page.evaluate(async () => ({
            local: localStorage.length,
            session: sessionStorage.length,
            db: (await indexedDB.databases()).length,
        })),
    ).toEqual({ local: 0, session: 0, db: 0 });
    await page
        .getByRole("button", { name: "Bersihkan tampilan", exact: true })
        .click();
    await expect(panel).toHaveCount(0);
});
test("unconfigured office and denied GPS produce no fallback staging coordinates", async ({
    page,
}) => {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({ code: 1, message: "denied" } as GeolocationPositionError);
    });
    await setup(page, false);
    const panel = page.getByRole("region", {
        name: "Preview lokasi check-in staging",
        exact: true,
    });
    await expect(panel).toContainText("Master kantor belum ditetapkan");
    await panel
        .getByRole("button", {
            name: "Ambil posisi untuk preview",
            exact: true,
        })
        .click();
    await expect(panel).toContainText("Tidak ada posisi pengganti");
    await expect(panel).toContainText("Posisi perangkat belum tersedia");
    await expect(
        panel.getByRole("button", { name: "Gunakan lokasi demo", exact: true }),
    ).toHaveCount(0);
});
test("late GPS callback cannot populate a different server target", async ({
    page,
}) => {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (ok) => {
            (window as unknown as { releaseGPS: () => void }).releaseGPS = () =>
                ok({
                    coords: { latitude: 9, longitude: 99, accuracy: 3 },
                    timestamp: Date.now(),
                } as GeolocationPosition);
        };
    });
    await setup(page);
    const panel = page.getByRole("region", {
        name: "Preview lokasi check-in staging",
        exact: true,
    });
    await panel
        .getByRole("button", {
            name: "Ambil posisi untuk preview",
            exact: true,
        })
        .click();
    await panel.getByLabel("Tujuan preview staging").selectOption("outlet:12");
    await page.evaluate(() =>
        (window as unknown as { releaseGPS: () => void }).releaseGPS(),
    );
    await expect(panel).toContainText("Posisi perangkat belum tersedia");
    await expect(panel).not.toContainText("9.000000, 99.000000");
});
