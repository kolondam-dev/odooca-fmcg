import { expect, type Page } from "@playwright/test";
export async function saveVisitPhoto(
    page: Page,
    phase: "check-in" | "check-out",
) {
    const group = page.getByRole("group", {
        name: `Foto ${phase} kunjungan`,
        exact: true,
    });
    if (phase === "check-out" && !(await group.isVisible()))
        await page
            .getByRole("button", { name: "Selesai kunjungan", exact: true })
            .click();
    await group.scrollIntoViewIfNeeded();
    await group.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(group.getByAltText("Pratinjau foto bukti lokal")).toBeVisible({
        timeout: 15000,
    });
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
            .getByRole("button", {
                name: "Perbarui lokasi outlet",
                exact: true,
            })
            .click();
}
/** Store-display proof required before an order can leave the sheet. */
/**
 * Foto display toko disimpan di layar "Display & stok toko" (prasyarat order).
 * Dipanggil dari Hub kunjungan atau dari layar Order (tetap terbuka di bawahnya).
 */
export async function saveDisplayPhoto(page: Page) {
    const fromOrder = await page
        .getByRole("region", { name: "Order penjualan", exact: true })
        .isVisible();
    if (fromOrder)
        await page
            .getByRole("button", { name: "Buka Display & stok", exact: true })
            .click();
    else
        await page.getByRole("button", { name: /Display & stok toko/ }).click();
    const screen = page.getByRole("region", { name: "Display dan stok toko" });
    await screen
        .getByLabel("Foto display outlet")
        .setInputFiles("public/icon-192.png");
    await expect(screen.getByText("Tersimpan", { exact: true })).toBeVisible();
    await screen
        .getByRole("button", { name: "Simpan display & stok", exact: true })
        .click();
    await expect(screen).toHaveCount(0);
}

/** Buka layar Order dari Hub kunjungan. */
export async function openOrderScreen(page: Page) {
    await page
        .getByRole("button", { name: "Buat order di outlet", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Order penjualan", exact: true }),
    ).toBeVisible();
}

export async function fillQty(
    page: Page,
    product: string,
    tier: string,
    qty: number | string,
) {
    await page
        .getByLabel(`Kuantitas ${product} ${tier}`, { exact: true })
        .fill(String(qty));
}

/** Diskon order lewat lembar "Diskon order" (alasan bebas lewat pilihan Lainnya). */
export async function applyDiscount(
    page: Page,
    percent: number,
    reason: string,
) {
    await page.getByRole("button", { name: /^Diskon order/ }).click();
    const sheet = page.getByRole("dialog", { name: "Diskon order" });
    await sheet.getByLabel(/^Diskon diminta \(%\)/).fill(String(percent));
    await sheet.getByLabel("Alasan (wajib)").selectOption("Lainnya");
    await sheet
        .getByLabel("Alasan permintaan diskon", { exact: true })
        .fill(reason);
    await sheet
        .getByRole("button", { name: "Terapkan diskon", exact: true })
        .click();
}

/** Buka Ringkasan, kirim order, lalu tutup layar Hasil kirim kembali ke Hub. */
export async function sendOrder(page: Page) {
    await page.getByRole("button", { name: /SKU · .* · Lihat$/ }).click();
    await page
        .getByRole("dialog", { name: "Ringkasan order" })
        .getByRole("button", { name: "Kirim order", exact: true })
        .click();
    const result = page.getByRole("region", { name: "Hasil kirim order" });
    await expect(result).toBeVisible();
    await result
        .getByRole("button", { name: "Lihat order", exact: true })
        .click();
    await expect(result).toHaveCount(0);
}

/** Layar kunjungan menutupi navigasi bawah; keluar lewat tombol Kembali bila terbuka. */
export async function leaveVisit(page: Page) {
    const back = page.getByRole("button", { name: "Kembali", exact: true });
    const shown = await back
        .waitFor({ state: "visible", timeout: 1500 })
        .then(() => true)
        .catch(() => false);
    if (shown) await back.click();
}

/** Setelah "Tutup kunjungan": tunggu penutupan lokal, lalu kembali ke daftar agar navigasi bawah bebas. */
export async function leaveClosedVisit(page: Page) {
    await expect(
        page.getByText(/Kunjungan ditutup lokal/).first(),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Kembali ke daftar outlet", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Kunjungan outlet" }),
    ).toHaveCount(0);
}
