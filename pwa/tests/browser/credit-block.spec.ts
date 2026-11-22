import { checkIn, expect, test } from "./session-fixture";
import { fillQty, openOrderScreen, saveVisitPhoto } from "./visit-helpers";

test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.456,
        longitude: 124.84,
        accuracy: 3,
    });
});

test("outlet strict dengan faktur jatuh tempo: order diblokir, kunjungan tetap jalan", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Minimarket Pelangi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(
        page.getByText(/ada 2 faktur jatuh tempo/).first(),
    ).toBeVisible();

    await openOrderScreen(page);
    await expect(
        page
            .getByText(/Order baru tidak dapat dikirim sampai tagihan lunas/)
            .first(),
    ).toBeVisible();
    await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
    await page.getByRole("button", { name: /SKU · .* · Lihat$/ }).click();
    const sheet = page.getByRole("dialog", { name: "Ringkasan order" });
    await expect(
        sheet.getByRole("button", { name: "Kirim order", exact: true }),
    ).toBeDisabled();
    await expect(sheet).toContainText("Diblokir: outlet mode wajib lunas");
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});

test("outlet lain tidak menampilkan blokir kredit", async ({
    page,
    context,
}) => {
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(page.getByText(/ada 2 faktur jatuh tempo/)).toHaveCount(0);
});
