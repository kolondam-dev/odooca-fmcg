import { checkIn, test, expect } from "./session-fixture";

test("Absen: akurasi GPS di atas batas ±30 m membuka lembar dan mengunci selfie sampai akurasi cukup", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 85,
    });
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    const sheet = page.getByRole("dialog", { name: "Akurasi lokasi rendah" });
    await expect(sheet).toContainText(
        "Akurasi saat ini ±85 m. Batas untuk absen dan check-in adalah ±30 m.",
    );
    await expect(sheet).toContainText("Pindah ke tempat terbuka");
    await sheet
        .getByRole("button", { name: "Tutup", exact: true })
        .last()
        .click();
    const screen = page.getByRole("region", {
        name: "Absensi foto dan lokasi",
    });
    await screen.getByLabel("Alamat / nama lokasi").fill("Jl. Uji, Manado");
    await expect(screen).toContainText("Akurasi saat ini ±85 m");
    await expect(
        screen.getByRole("button", { name: "Ambil selfie", exact: true }),
    ).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 10,
    });
    await screen
        .getByRole("button", { name: "Perbarui lokasi", exact: true })
        .click();
    await expect(
        screen.getByRole("button", { name: "Ambil selfie", exact: true }),
    ).toBeEnabled();
    await expect(screen).not.toContainText("Akurasi saat ini");
});

test("Absen: Coba lagi pada lembar akurasi rendah mengambil lokasi baru", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 85,
    });
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    const sheet = page.getByRole("dialog", { name: "Akurasi lokasi rendah" });
    await expect(sheet).toBeVisible();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 12,
    });
    await sheet.getByRole("button", { name: "Coba lagi" }).click();
    await expect(sheet).toHaveCount(0);
    await expect(
        page.getByRole("region", { name: "Lokasi dan foto absensi" }),
    ).toHaveAttribute("aria-busy", "false");
    await expect(page.getByText("±12 m").first()).toBeVisible();
});

test("Pita Offline tampil di bawah header saat jaringan putus dan hilang saat kembali", async ({
    page,
    context,
}) => {
    await page.goto("./");
    await expect(page.getByText(/Selamat bekerja/)).toBeVisible();
    const banner = page.locator(".offline-banner");
    await expect(banner).toHaveCount(0);
    await context.setOffline(true);
    await expect(banner).toContainText(/^Offline · /);
    await context.setOffline(false);
    await expect(banner).toHaveCount(0);
});

test("Check-in toko: izin lokasi ditolak membuka lembar Akses lokasi ditolak dan Coba lagi mengambil ulang", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    // Mode live eksplisit: izin ditolak hanya jatuh ke simulasi di mode demo.
    await page.addInitScript(() =>
        localStorage.setItem("fmcg:running-mode", "live"),
    );
    await page.goto("./");
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page.evaluate(() => {
        const real = navigator.geolocation.getCurrentPosition.bind(
            navigator.geolocation,
        );
        (window as unknown as { __denyGps: boolean }).__denyGps = true;
        navigator.geolocation.getCurrentPosition = (ok, fail, opts) =>
            (window as unknown as { __denyGps: boolean }).__denyGps
                ? fail?.({
                      code: 1,
                      message: "denied",
                  } as GeolocationPositionError)
                : real(ok, fail, opts);
    });
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const sheet = page.getByRole("dialog", { name: "Akses lokasi ditolak" });
    await expect(sheet).toContainText("Check-in butuh lokasi");
    await page.evaluate(() => {
        (window as unknown as { __denyGps: boolean }).__denyGps = false;
    });
    await sheet.getByRole("button", { name: "Coba lagi", exact: true }).click();
    await expect(
        page.getByRole("dialog", { name: "Akses lokasi ditolak" }),
    ).toHaveCount(0);
    await expect(
        page.getByRole("region", {
            name: "Preview peta Toko Sinar Pagi",
            exact: true,
        }),
    ).toContainText("Di dalam radius");
});
