import { checkIn, expect, test } from "./session-fixture";
import {
    applyDiscount,
    fillQty,
    openOrderScreen,
    saveVisitPhoto,
} from "./visit-helpers";

test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
});

async function startOrder(page: import("@playwright/test").Page) {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await openOrderScreen(page);
}

async function openSummary(page: import("@playwright/test").Page) {
    await page.getByRole("button", { name: /SKU · .* · Lihat$/ }).click();
    return page.getByRole("dialog", { name: "Ringkasan order" });
}

test("ringkasan order: diskon kecil berada di zona bebas tanpa menunggu approval", async ({
    page,
}) => {
    await startOrder(page);
    await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
    await applyDiscount(page, 1, "Pratinjau zona bebas");
    const sheet = await openSummary(page);
    await expect(sheet).toContainText("dalam zona bebas");
    await expect(sheet).toContainText("server yang memutuskan");
    await expect(sheet).not.toContainText("Menunggu approval");
});

test("ringkasan order: diskon besar menampilkan rantai approver berjenjang", async ({
    page,
}) => {
    await startOrder(page);
    await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
    await applyDiscount(page, 5, "Pratinjau rantai");
    const sheet = await openSummary(page);
    await expect(sheet).toContainText(
        "Menunggu approval: Diskon 5% → perlu Supervisor → Branch Manager",
    );
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
