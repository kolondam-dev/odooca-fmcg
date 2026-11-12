import type { Page } from "@playwright/test";
import { expect, test, useLegacyServer } from "./session-fixture";
import { openActivity } from "./visit-helpers";
import { ensureDaily, switchPersona } from "./delivery-helpers";

async function toSetor(page: Page, legacy = false) {
    if (legacy) useLegacyServer(page);
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await page
        .getByRole("heading", { name: "Akhiri trip", exact: true })
        .locator("../..")
        .getByRole("button")
        .first()
        .click();
    await page.getByRole("button", { name: /^Setor uang ke kasir/ }).click();
    return page.getByRole("region", { name: "Setor uang" });
}
async function photo(screen: ReturnType<Page["getByRole"]>) {
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
}

test("Setor uang: bukti kosong dan selisih tanpa catatan ditolak, lalu tersimpan", async ({
    page,
}) => {
    const screen = await toSetor(page);
    await screen.getByLabel("Tunai disetor").fill("5000");
    await screen.getByRole("button", { name: "Simpan setoran" }).click();
    await expect(screen.getByRole("alert")).toContainText("Foto bukti setor");
    await photo(screen);
    await screen.getByRole("button", { name: "Simpan setoran" }).click();
    await expect(screen.getByRole("alert")).toContainText("Selisih setoran");
    await screen.getByLabel(/^Catatan selisih/).fill("Kurang untuk bensin");
    await screen.getByRole("button", { name: "Simpan setoran" }).click();
    await expect(screen).toHaveCount(0);
    await page
        .getByRole("button", { name: "Kembali", exact: true })
        .first()
        .click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openActivity(page);
    await expect(page.getByText(/Setor uang • .* • Rp\s5\.000/)).toBeVisible();
});

test("Setor uang: server tanpa kapabilitas mengunci tombol kirim", async ({
    page,
}) => {
    const screen = await toSetor(page, true);
    await expect(screen.getByRole("alert")).toContainText(
        "Server belum mendukung setoran",
    );
    await expect(
        screen.getByRole("button", { name: "Simpan setoran" }),
    ).toBeDisabled();
});
