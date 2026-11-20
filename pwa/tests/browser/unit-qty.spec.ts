import { checkIn, expect, test } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
});

test("POS menampilkan stok sebagai badge satuan, bukan teks krt/pak", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Buat order di outlet", exact: true })
        .click();
    const card = page.locator(".pos-card").first();
    const badge = card.locator(".ui-unitqty");
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute("aria-label", /\d+ (karton|pack|pcs)/);
    await expect(card).not.toContainText(/\bkrt\b|\bpak\b/);
    await expect(page.locator(".ui-unitlegend")).toHaveCount(1);
    // Subtotal kartu: jumlah sebagai badge, harga tetap benar.
    const wafer = page
        .locator(".pos-card")
        .filter({ hasText: "Wafer Cokelat 24 g" });
    await wafer
        .getByLabel("Kuantitas Wafer Cokelat 24 g Pack", { exact: true })
        .fill("2");
    const sum = wafer.locator(".pos-card__sum");
    await expect(sum.getByRole("img", { name: "2 pack" })).toBeVisible();
    await expect(sum).toContainText(/Rp\s*26\.400/);
    await expect(sum).not.toContainText(/pcs ·|box|karton/i);
});
