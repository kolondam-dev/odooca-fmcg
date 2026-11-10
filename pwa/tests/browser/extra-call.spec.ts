import { checkIn, expect, test } from "./session-fixture";
import { openQueue } from "./visit-helpers";

test("Extra call: cari outlet, pilih, alasan, tersimpan di antrean", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: "Extra call", exact: true }).click();
    const screen = page.getByRole("region", { name: "Extra call" });
    await expect(screen.getByText(/kunjungan di luar PJP/)).toBeVisible();
    await screen.getByLabel("Cari outlet").fill("Grosir");
    await expect(screen.getByText("Warung Bahu Mall")).toHaveCount(0);
    await screen.getByRole("button", { name: /Grosir Calaca Baru/ }).click();
    await expect(screen.getByText("Dipilih", { exact: true })).toBeVisible();
    await screen.getByLabel("Alasan").selectOption("stock_follow_up");
    await screen.getByLabel("Catatan (opsional)").fill("Stok tambahan");
    await screen
        .getByRole("button", { name: "Tambahkan ke daftar hari ini" })
        .click();
    await expect(screen).toHaveCount(0);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    const queue = await openQueue(page);
    await expect(
        queue.getByText("Extra call • Grosir Calaca Baru"),
    ).toBeVisible();
});

test("Extra call tanpa memilih outlet ditolak", async ({ page }) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: "Extra call", exact: true }).click();
    await page
        .getByRole("button", { name: "Tambahkan ke daftar hari ini" })
        .click();
    await expect(page.getByRole("alert")).toContainText("Pilih outlet");
});
