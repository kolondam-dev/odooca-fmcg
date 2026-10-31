import { expect, test } from "@playwright/test";
test("office check-in previews real fix and handles failed road tiles without authorizing attendance", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: -6.2,
        longitude: 106.8,
        accuracy: 35,
    });
    let tiles = 0;
    await page.route("https://tile.openstreetmap.org/**", (route) => {
        tiles++;
        return route.abort();
    });
    await page.goto("./");
    await page.getByRole("button", { name: /^Absensi Foto/ }).click();
    const map = page.getByRole("region", {
        name: "Preview peta Kantor Pusat",
        exact: true,
    });
    await expect(map).toContainText("Posisi perangkat belum tersedia");
    await expect(map).toContainText("Titik tujuan simulasi");
    await page
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await expect(map).toContainText("Di luar radius");
    await expect(map).toContainText("-6.200000, 106.800000");
    expect(tiles).toBe(0);
    await map
        .getByRole("button", { name: "Muat peta jalan", exact: true })
        .click();
    await expect(map.getByRole("status")).toContainText("Peta jalan gagal");
    await expect(map.getByRole("img")).toBeVisible();
    await page.getByRole("button", { name: "Simpan absensi" }).click();
    await expect(page.getByRole("alert")).toContainText(
        "Simpan foto dan lokasi dahulu.",
    );
    expect(tiles).toBeGreaterThan(0);
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
test("office simulated position is labeled and new real fix clears simulated label", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await page.getByRole("button", { name: /^Absensi Foto/ }).click();
    const map = page.getByRole("region", {
        name: "Preview peta Kantor Pusat",
        exact: true,
    });
    await page
        .getByRole("button", { name: "Gunakan lokasi acuan", exact: true })
        .click();
    await expect(map).toContainText("posisi simulasi");
    await page
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await expect(map).toContainText("Di dalam radius");
    await expect(map).not.toContainText("posisi simulasi");
});
test("outlet check-in renders attributed road preview, zoom and scope reset with strict guard intact", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.47,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.route("https://tile.openstreetmap.org/**", (route) =>
        route.fulfill({
            path: "public/icon-192.png",
            contentType: "image/png",
        }),
    );
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Buka sesi kerja",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const map = page.getByRole("region", {
        name: "Preview peta Toko Sinar Pagi",
        exact: true,
    });
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(map).toContainText("Di luar radius");
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan", exact: true }),
    ).toBeDisabled();
    await map
        .getByRole("button", { name: "Muat peta jalan", exact: true })
        .click();
    await expect(map.locator("img").first()).toBeVisible();
    await expect
        .poll(() =>
            map
                .locator("img")
                .evaluateAll((imgs) =>
                    imgs.every(
                        (i) =>
                            (i as HTMLImageElement).complete &&
                            (i as HTMLImageElement).naturalWidth > 0,
                    ),
                ),
        )
        .toBe(true);
    await expect(
        map.getByRole("link", { name: "OpenStreetMap contributors" }),
    ).toBeVisible();
    await map
        .getByRole("button", { name: "Perbesar peta", exact: true })
        .click();
    await map
        .getByRole("button", { name: "Tampilkan kedua titik", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        map.getByRole("button", { name: "Muat peta jalan", exact: true }),
    ).toBeVisible();
    await expect(map.locator("img")).toHaveCount(0);
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
test("denied outlet GPS labels fallback as simulation", async ({ page }) => {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({ code: 1, message: "denied" } as GeolocationPositionError);
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Buka sesi kerja",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        page.getByRole("region", {
            name: "Preview peta Toko Sinar Pagi",
            exact: true,
        }),
    ).toContainText("posisi simulasi");
});
