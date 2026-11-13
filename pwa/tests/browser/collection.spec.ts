import type { Page } from "@playwright/test";
import { expect, test, useLegacyServer } from "./session-fixture";
import { activity, openActivity } from "./visit-helpers";
import { ensureDaily, switchPersona } from "./delivery-helpers";

/** Beranda -> persona delivery -> sesi aktif -> tab Delivery -> kartu trip -> daftar toko. */
async function toStores(page: Page) {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await page
        .getByRole("button", { name: /^Buka TRIP/ })
        .first()
        .click();
}
async function openPenagihan(page: Page) {
    await page
        .getByRole("button", { name: /^Tagihan / })
        .first()
        .click();
    return page.getByRole("region", { name: /^Penagihan / });
}
async function photo(page: Page) {
    const screen = page.getByRole("region", { name: "Bukti penagihan" });
    await screen.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(
        screen.getByAltText("Pratinjau foto bukti lokal"),
    ).toBeVisible();
    await screen
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await screen
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(screen.getByText("Foto dan lokasi tersimpan.")).toBeVisible();
    return screen;
}

test("Penagihan: dua faktur satu bukti, sisa wajib alasan, tersimpan lalu tidak bisa ditagih ulang", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await toStores(page);
    const penagihan = await openPenagihan(page);
    await expect(penagihan.getByText(/SIM-TAGIHAN-1 · saldo/)).toBeVisible();
    await expect(penagihan.getByText(/SIM-TAGIHAN-1B · saldo/)).toBeVisible();
    // Bayar sebagian faktur pertama: wajib alasan dan janji bayar.
    await penagihan
        .getByLabel("Nominal SIM-TAGIHAN-1", { exact: false })
        .first()
        .fill("400000");
    await penagihan.getByRole("button", { name: /^Lanjut ke bukti/ }).click();
    await expect(penagihan.getByRole("alert")).toContainText("alasan sisa");
    await penagihan
        .getByLabel(/^Alasan sisa SIM-TAGIHAN-1/)
        .first()
        .selectOption("Toko tidak punya uang");
    await penagihan
        .getByLabel(/^Janji bayar SIM-TAGIHAN-1/)
        .first()
        .fill("2099-01-01");
    await penagihan.getByRole("button", { name: /^Lanjut ke bukti/ }).click();
    const bukti = page.getByRole("region", { name: "Bukti penagihan" });
    await bukti.getByRole("button", { name: /^Simpan penagihan/ }).click();
    await expect(bukti.getByRole("alert")).toContainText("pembayar");
    await bukti.getByLabel("Nama pembayar").fill("Budi Outlet");
    await bukti.getByLabel("Nomor tanda terima").fill("KW-001");
    await bukti.getByRole("button", { name: /^Simpan penagihan/ }).click();
    await expect(bukti.getByRole("alert")).toContainText("Foto bukti");
    await photo(page);
    await bukti.getByRole("button", { name: /^Simpan penagihan/ }).click();
    await expect(bukti).toHaveCount(0);
    // Faktur yang sudah dicatat tidak muncul lagi.
    const again = await openPenagihan(page);
    await expect(again.getByText(/sudah dicatat/)).toBeVisible();
    await page.screenshot({
        path: `test-results/penagihan-${test.info().project.name}.png`,
        fullPage: true,
    });
    await page.getByRole("button", { name: "Kembali" }).last().click();
    await page.getByRole("button", { name: "Kembali" }).last().click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openActivity(page);
    await expect(
        activity(page).getByText(/Penagihan • .* • Rp\s1\.150\.000/),
    ).toBeVisible();
});

test("Penagihan: server tanpa kapabilitas mengunci tombol kirim dan Giro tidak dapat dipilih", async ({
    page,
}) => {
    useLegacyServer(page);
    await toStores(page);
    const penagihan = await openPenagihan(page);
    await expect(penagihan.getByRole("alert")).toContainText(
        "Server belum mendukung penagihan",
    );
    await penagihan.getByRole("button", { name: /^Lanjut ke bukti/ }).click();
    const bukti = page.getByRole("region", { name: "Bukti penagihan" });
    await expect(bukti.getByRole("button", { name: "Giro" })).toBeDisabled();
    await expect(
        bukti.getByRole("button", { name: /^Simpan penagihan/ }),
    ).toBeDisabled();
});
