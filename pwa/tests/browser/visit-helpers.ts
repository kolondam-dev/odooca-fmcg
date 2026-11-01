import { expect, type Page } from "@playwright/test";
export async function saveVisitPhoto(
    page: Page,
    phase: "check-in" | "check-out",
) {
    if (phase === "check-out")
        await page
            .getByRole("button", { name: "Close session", exact: true })
            .click();
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
/** Store-display proof required before an order can leave the sheet. */
export async function saveDisplayPhoto(page: Page) {
    await page
        .getByLabel("Foto display outlet")
        .setInputFiles("public/icon-192.png");
    await expect(
        page.getByRole("dialog").getByText("Tersimpan", { exact: true }),
    ).toBeVisible();
}

export async function sendOrder(page: Page) {
    await page
        .getByRole("button", { name: "Preview order", exact: true })
        .last()
        .click();
    await page
        .getByRole("button", { name: "Kirim order", exact: true })
        .click();
}
