import { checkIn, expect, test } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

test("Selesai kunjungan tanpa order: ringkasan, catatan min. 5 karakter, foto penutup", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Perbarui lokasi outlet", exact: true })
        .click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Selesai kunjungan", exact: true })
        .click();
    const screen = page.getByRole("region", { name: "Selesai kunjungan" });
    await expect(
        screen.getByRole("list", { name: "Tahap kunjungan" }),
    ).toBeVisible();
    for (const t of ["Tagihan", "Order", "Display & stok"])
        await expect(
            screen.locator(".ui-row__title", { hasText: t }),
        ).toBeVisible();
    await expect(screen.getByText("Belum ada order")).toBeVisible();
    const done = screen
        .getByRole("button", { name: "Selesai kunjungan", exact: true })
        .last();
    await expect(done).toBeDisabled();
    await saveVisitPhoto(page, "check-out");
    await screen.getByLabel(/^Catatan/).fill("abc");
    await expect(done).toBeDisabled();
    await screen.getByLabel(/^Catatan/).fill("Toko tutup siang");
    await expect(done).toBeEnabled();
});
