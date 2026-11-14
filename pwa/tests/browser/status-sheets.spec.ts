import { test, expect } from "./session-fixture";

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
        "Akurasi saat ini ±85 m. Batas akurasi untuk absen adalah ±30 m.",
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
