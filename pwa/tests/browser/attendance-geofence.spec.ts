import { test, expect, freshSnapshotMeta, type Page } from "./session-fixture";

async function verifiedOffice(page: Page) {
    const { MockProvider } = await import("../../src/data/mock");
    const snapshot = await new MockProvider("sales", true).snapshot();
    const meta = freshSnapshotMeta();
    await page.route("**/api/v1/sync/snapshot", (route) =>
        route.fulfill({
            json: {
                ...snapshot,
                updatedAt: meta.updatedAt,
                scope: { ...snapshot.scope, business_date: meta.businessDate },
                office: {
                    id: "1",
                    name: "Kantor Pusat",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                    coordinate_status: "verified",
                },
            },
        }),
    );
}

test("Absen: titik terverifikasi mengunci Ambil selfie di luar area dan membukanya di dalam area", async ({
    page,
    context,
}) => {
    await verifiedOffice(page);
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.5,
        longitude: 124.9,
        accuracy: 3,
    });
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    const screen = page.getByRole("region", {
        name: "Absensi foto dan lokasi",
    });
    await screen.getByLabel("Alamat / nama lokasi").fill("Jl. Uji, Manado");
    await expect(screen).toContainText(/Di luar area · \d+ m dari batas/);
    await expect(screen).toContainText(
        "Absen hanya bisa di dalam area kantor.",
    );
    await expect(
        screen.getByRole("button", { name: "Ambil selfie", exact: true }),
    ).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await screen
        .getByRole("button", { name: "Perbarui lokasi", exact: true })
        .click();
    await expect(screen).toContainText(
        /Di dalam area · \d+ m dari titik absen/,
    );
    await expect(
        screen.getByRole("button", { name: "Ambil selfie", exact: true }),
    ).toBeEnabled();
});

test("Absen: sheet Aturan geofence terbuka dari header, Back dan Mengerti menutupnya", async ({
    page,
}) => {
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    const open = () =>
        page
            .getByRole("button", { name: "Aturan geofence", exact: true })
            .click();
    await open();
    const sheet = page.getByRole("dialog", { name: "Aturan geofence" });
    await expect(sheet).toContainText("Hanya kamera");
    await expect(sheet).toContainText("wajib kamera depan");
    await expect(sheet).toContainText("validasi dilakukan server");
    await page.goBack();
    await expect(sheet).toHaveCount(0);
    await expect(
        page.getByRole("region", { name: "Absensi foto dan lokasi" }),
    ).toBeVisible();
    await open();
    await sheet.getByRole("button", { name: "Mengerti" }).click();
    await expect(sheet).toHaveCount(0);
});
