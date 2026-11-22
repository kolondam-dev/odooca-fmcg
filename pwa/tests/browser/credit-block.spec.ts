import { checkIn, expect, test, type Page } from "./session-fixture";
import {
    activity,
    fillQty,
    leaveClosedVisit,
    leaveVisit,
    openOrderScreen,
    openActivity,
    saveDisplayPhoto,
    saveVisitPhoto,
} from "./visit-helpers";

const STRICT_MESSAGE = /Order baru tidak dapat dikirim sampai tagihan lunas/;

test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
});

async function startVisit(
    page: Page,
    context: import("@playwright/test").BrowserContext,
    outlet: RegExp,
    at: { latitude: number; longitude: number },
) {
    await context.setGeolocation({ ...at, accuracy: 3 });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: outlet }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
}
const PELANGI = { latitude: 1.456, longitude: 124.84 }; // strict + 2 faktur jatuh tempo (demo)
const SINAR_PAGI = { latitude: 1.465, longitude: 124.833 };

/** Prasyarat order lengkap: SKU valid di keranjang + foto display tersimpan. */
async function prepareValidOrder(page: Page) {
    await openOrderScreen(page);
    await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
    await saveDisplayPhoto(page);
}
const openSummary = async (page: Page) => {
    await page.getByRole("button", { name: /SKU · .* · Lihat$/ }).click();
    return page.getByRole("dialog", { name: "Ringkasan order" });
};
/** Jumlah order terkirim/antre di Riwayat aktivitas (baris "Order • <outlet>"). */
async function sentOrders(page: Page) {
    await leaveVisit(page);
    await openActivity(page);
    return activity(page)
        .getByText(/Order • /)
        .count();
}

test("strict + faktur jatuh tempo: display dan keranjang valid, tombol tetap nonaktif karena guard kredit", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
    await expect(
        page.getByText(/ada 2 faktur jatuh tempo/).first(),
    ).toBeVisible();
    await prepareValidOrder(page);
    await expect(page.getByText(STRICT_MESSAGE).first()).toBeVisible();
    const sheet = await openSummary(page);
    // Semua prasyarat lain terpenuhi: penyebab nonaktif HANYA guard kredit.
    await expect(
        sheet.getByText("Foto display toko wajib sebelum order dikirim."),
    ).toHaveCount(0);
    await expect(sheet).toContainText("Diblokir: outlet mode wajib lunas");
    await expect(
        sheet.getByRole("button", { name: "Kirim order", exact: true }),
    ).toBeDisabled();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});

test("strict: send() yang dipaksa dijalankan tetap menolak, tidak mengirim dan draft tetap utuh", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
    await prepareValidOrder(page);
    const sheet = await openSummary(page);
    const send = sheet.getByRole("button", {
        name: "Kirim order",
        exact: true,
    });
    await expect(send).toBeDisabled();
    // Paksa event klik pada tombol nonaktif: jalur produksi send() harus menolak sendiri.
    await send.evaluate((el) => {
        el.removeAttribute("disabled");
        (el as HTMLButtonElement).click();
        el.setAttribute("disabled", "");
    });
    await expect(sheet.getByRole("alert")).toContainText(
        "Outlet ini wajib lunas",
    );
    await expect(
        page.getByRole("region", { name: "Hasil kirim order" }),
    ).toHaveCount(0);
    // Draft tetap utuh: ringkasan masih terbuka dengan baris SKU dan tidak ada order terkirim.
    await expect(sheet).toContainText("Biskuit Kelapa 300 g");
    await sheet
        .getByRole("button", { name: "Tutup", exact: true })
        .first()
        .click({ force: true });
    // Draft utuh (removeDraft tidak dipanggil) dan tidak ada Hasil kirim (submit tidak dipanggil).
    await expect(
        page.getByRole("button", { name: /^1 SKU · .* · Lihat$/ }),
    ).toBeVisible();
    await expect(
        page.getByRole("region", { name: "Hasil kirim order" }),
    ).toHaveCount(0);
});

test("strict: kunjungan tetap bisa ditutup tanpa order dan tidak ada order dikirim", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
    await expect(
        page.getByText(/ada 2 faktur jatuh tempo/).first(),
    ).toBeVisible();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByLabel(/^Catatan/)
        .fill("Tagihan jatuh tempo, minta pelunasan lewat Supervisor");
    await page
        .getByRole("button", { name: "Selesai kunjungan", exact: true })
        .first()
        .click();
    await leaveClosedVisit(page);
    expect(await sentOrders(page)).toBe(0);
});

test("outlet tanpa blokir: display dan keranjang valid, tombol aktif dan order berhasil masuk antrean", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Toko Sinar Pagi/, SINAR_PAGI);
    await prepareValidOrder(page);
    await expect(page.getByText(STRICT_MESSAGE)).toHaveCount(0);
    const sheet = await openSummary(page);
    const send = sheet.getByRole("button", {
        name: "Kirim order",
        exact: true,
    });
    await expect(send).toBeEnabled();
    await send.click();
    const result = page.getByRole("region", { name: "Hasil kirim order" });
    await expect(result).toBeVisible();
    await result
        .getByRole("button", { name: "Lihat order", exact: true })
        .click();
    expect(await sentOrders(page)).toBeGreaterThan(0);
});
