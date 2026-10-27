import { expect, test } from "@playwright/test";
test("visit location guards, offline restore and checkout sync", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.47,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Simulasikan absensi diterima",
            exact: true,
        })
        .click();
    await page
        .getByRole("button", {
            name: "Sync pagi & buka sesi demo",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const locate = page.getByRole("button", {
        name: "Ambil lokasi outlet",
        exact: true,
    });
    const start = page.getByRole("button", {
        name: "Mulai kunjungan demo",
        exact: true,
    });
    await locate.click();
    await expect(
        page.getByText("Di luar geofence", { exact: true }),
    ).toBeVisible();
    await expect(start).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 30,
    });
    await locate.click();
    await expect(
        page.getByText("Akurasi belum pasti", { exact: true }),
    ).toBeVisible();
    await expect(start).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await locate.click();
    await expect(start).toBeEnabled();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await start.click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await page
        .getByLabel("Catatan kunjungan")
        .fill("Toko tutup untuk kunjungan simulasi");
    await page.getByLabel("Hasil kunjungan").selectOption("outlet_closed");
    await page
        .getByRole("button", { name: "Tutup kunjungan demo", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(page.locator(".activity")).toHaveCount(2);
    await context.setOffline(false);
    await expect(
        page
            .locator(".activity")
            .getByText("Diterima simulator", { exact: true }),
    ).toHaveCount(2, { timeout: 20000 });
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
test("denied GPS keeps visit closed", async ({ page }) => {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({
                code: 1,
                message: "denied",
                PERMISSION_DENIED: 1,
                POSITION_UNAVAILABLE: 2,
                TIMEOUT: 3,
            });
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Simulasikan absensi diterima",
            exact: true,
        })
        .click();
    await page
        .getByRole("button", {
            name: "Sync pagi & buka sesi demo",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(page.getByRole("alert")).toContainText(/lokasi/i);
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan demo", exact: true }),
    ).toBeDisabled();
});
