import { changeTestAccount, checkIn } from "./session-fixture";
import { expect, type Locator, type Page } from "@playwright/test";
const owners = {
    sales: "demo-mdu:DEMO-ANDRE",
    delivery: "demo-mdu:DEMO-NOVRY",
    canvass: "demo-mdu:DEMO-STEVEN",
};
export async function switchPersona(page: Page, actor: keyof typeof owners) {
    await changeTestAccount(page, actor);
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    const region = page.getByRole("region", {
        name: "Sesi kerja",
        exact: true,
    });
    await expect(region).toHaveAttribute("data-owner", owners[actor]);
    await expect(region).toHaveAttribute("aria-busy", "false");
}
export async function ensureDaily(page: Page) {
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    await checkIn(page);
    const region = page.getByRole("region", {
        name: "Sesi kerja",
        exact: true,
    });
    await expect(region).toHaveAttribute("aria-busy", "false");
    const ready = region.getByText("Sesi aktif", { exact: true });
    if (await ready.isVisible()) return;
    const open = region.getByRole("button", {
        name: "Sinkronkan data harian",
        exact: true,
    });
    await expect(open).toBeEnabled();
    await open.click();
    await expect(region).toHaveAttribute("aria-busy", "false");
    await expect(ready).toBeVisible();
}
/** Buka DO dari tab Delivery: kartu trip -> daftar toko -> DO. Layar penuh, jadi lokator = body. */
export async function openDeliveryTask(page: Page, id = "DEMO-DO-001") {
    const region = page.getByRole("region", {
        name: `Delivery ${id}`,
        exact: true,
    });
    if (!(await region.isVisible())) {
        const stores = page.getByRole("region", { name: /^Daftar toko / });
        if (!(await stores.isVisible()))
            await page
                .getByRole("button", { name: /^Buka TRIP/ })
                .first()
                .click();
        await page
            .getByRole("button", { name: `Buka ${id}`, exact: true })
            .click();
    }
    await expect(
        page.getByText("Memulihkan data…", { exact: true }),
    ).toHaveCount(0);
    return page.locator("body");
}
/** Tutup semua layar Delivery (hasil POD/hub -> daftar toko -> halaman) agar halaman di belakangnya terjangkau. */
export async function closeDeliveryScreens(page: Page) {
    for (let i = 0; i < 4; i++) {
        const screen = page
            .locator(".ui-screen--over")
            .filter({ has: page.getByRole("button", { name: "Kembali" }) })
            .last();
        if (!(await screen.isVisible())) return;
        await screen.getByRole("button", { name: "Kembali" }).first().click();
    }
}
/** Foto bukti + lokasi lokal pada layar yang sedang terbuka (check-in atau serah terima). */
export async function saveDeliveryPhoto(task: Locator) {
    // Layar teratas (check-in atau serah terima); halaman di belakangnya punya bidang foto sendiri.
    const top = task.page().locator(".ui-screen--top").last();
    await top.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(top.getByAltText("Pratinjau foto bukti lokal")).toBeVisible();
    await top
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await top
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(top.getByText("Foto dan lokasi tersimpan.")).toBeVisible();
}
/** Check-in toko (bila belum), masuk hub, lalu buka layar serah terima. */
export async function startDelivery(task: Locator) {
    const start = task.getByRole("button", {
        name: "Mulai sesi delivery",
        exact: true,
    });
    const form = task.getByRole("button", {
        name: /^Mulai (serah terima|koreksi POD)$/,
    });
    const note = task.getByLabel("Catatan serah terima", { exact: true });
    await expect(start.or(form).or(note)).toBeVisible();
    if (await start.isVisible()) {
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Perbarui lokasi delivery",
                exact: true,
            })
            .click();
        await start.click();
        await expect(task.getByText(/Sesi delivery aktif/)).toBeVisible();
    }
    if (await form.isVisible()) await form.click();
    await expect(note).toBeVisible();
    if (!(await note.inputValue())) await note.fill("Diterima sesuai dokumen");
}
/** Kembali dari layar DO (hasil/hub) ke daftar toko. */
export async function backFromTask(page: Page) {
    await page
        .getByRole("region", { name: /^Delivery DEMO/ })
        .getByRole("button", { name: "Kembali" })
        .first()
        .click();
}
