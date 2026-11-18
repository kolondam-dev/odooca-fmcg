import { test, expect } from "./session-fixture";

test("Profil: layar penuh DS dengan identitas, konteks kerja, dan tautan akun", async ({
    page,
}) => {
    await page.goto("./");
    await page
        .getByRole("button", { name: "Profil dan Sesi Akun", exact: true })
        .click();
    const screen = page.getByRole("region", { name: "Profil dan sesi akun" });
    await expect(screen).toBeVisible();
    await expect(
        screen.getByRole("heading", { name: "Profil & Sesi Akun" }),
    ).toBeVisible();
    for (const label of ["Perusahaan", "Gudang & Hub", "Rute & Sesi"])
        await expect(screen.getByText(label, { exact: true })).toBeVisible();
    await expect(
        screen.getByRole("link", { name: /Masuk Akun Odoo/ }),
    ).toHaveAttribute("href", "/web/login?redirect=/field/");
    await expect(
        screen.getByRole("link", { name: /Keluar dari Sesi/ }),
    ).toHaveAttribute("href", "/web/session/logout?redirect=/field/");
    // Tidak ada sisa dialog lama.
    await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("Profil: tombol Kembali dan Back peramban menutup layar", async ({
    page,
}) => {
    await page.goto("./");
    const open = () =>
        page
            .getByRole("button", { name: "Profil dan Sesi Akun", exact: true })
            .click();
    const screen = page.getByRole("region", { name: "Profil dan sesi akun" });
    await open();
    await expect(screen).toBeVisible();
    await page.getByRole("button", { name: "Kembali", exact: true }).click();
    await expect(screen).toHaveCount(0);
    await open();
    await expect(screen).toBeVisible();
    await page.goBack();
    await expect(screen).toHaveCount(0);
});
