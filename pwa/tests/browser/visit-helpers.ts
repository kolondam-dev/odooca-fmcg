import { expect, type Page } from "@playwright/test";
export async function saveVisitPhoto(
    page: Page,
    phase: "check-in" | "check-out",
) {
    const group = page.getByRole("group", {
        name: `Foto ${phase} kunjungan`,
        exact: true,
    });
    await group.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(
        group.getByAltText("Pratinjau foto bukti lokal"),
    ).toBeVisible();
    await group
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await group
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(
        group.getByText(`Paket foto tersimpan untuk ${phase} outlet ini.`, {
            exact: true,
        }),
    ).toBeVisible();
    if (phase === "check-in")
        await page
            .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
            .click();
}
