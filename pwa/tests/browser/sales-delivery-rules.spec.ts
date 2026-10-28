import { switchPersona } from "./delivery-helpers";
import { expect, test } from "@playwright/test";
import {
    ensureDaily,
    saveDeliveryPhoto,
    startDelivery,
} from "./delivery-helpers";
import { saveVisitPhoto } from "./visit-helpers";
test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
});
for (const approved of [true, false])
    test(`tier order requests discount, then simulator decision ${approved}`, async ({
        page,
    }) => {
        await page.goto("./");
        await page
            .getByRole("navigation")
            .getByRole("button", { name: "Sales", exact: true })
            .click();
        await expect(
            page.getByText("Daily sync wajib sebelum membuka list Sales."),
        ).toBeVisible();
        await expect(
            page.getByRole("button", { name: /Toko Sinar Pagi/ }),
        ).toHaveCount(0);
        await ensureDaily(page);
        await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
        await saveVisitPhoto(page, "check-in");
        await page
            .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Mulai kunjungan demo", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Buat order di outlet", exact: true })
            .click();
        await page
            .getByLabel("Satuan Biskuit Kelapa 300 g", { exact: true })
            .selectOption("pack");
        await page
            .getByLabel("Kuantitas Biskuit Kelapa 300 g", { exact: true })
            .fill("1");
        await page.getByLabel("Diskon diminta (%)", { exact: true }).fill("5");
        await page
            .getByLabel("Alasan permintaan diskon", { exact: true })
            .fill("Promo contoh");
        await page.locator(".product").first().scrollIntoViewIfNeeded();
        await page.screenshot({
            path: `test-results/order-tiers-${test.info().project.name}.png`,
            fullPage: true,
        });
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
        await page
            .getByRole("button", {
                name: "Simpan ke antrean demo",
                exact: true,
            })
            .click();
        await page
            .getByRole("button", { name: "Lainnya", exact: true })
            .click();
        await expect(
            page.getByRole("heading", {
                name: "Simulator approval diskon",
                exact: true,
            }),
        ).toBeVisible();
        await page
            .getByLabel("Alasan keputusan diskon", { exact: true })
            .fill("Review simulasi");
        await page
            .getByRole("button", {
                name: approved
                    ? "Simulasikan setujui diskon"
                    : "Simulasikan tolak diskon",
                exact: true,
            })
            .click();
        await expect(
            page
                .locator(".activity")
                .getByText(new RegExp(`disetujui ${approved ? 5 : 0}%`)),
        ).toBeVisible();
    });
test("multi-SKU partial requires line reasons, closes session offline and updates list", async ({
    page,
    context,
}) => {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await expect(
        page.getByText("Daily sync wajib sebelum membuka list Delivery."),
    ).toBeVisible();
    await ensureDaily(page);
    const task = page
        .locator(".delivery-task")
        .filter({ hasText: "DEMO-DO-001" });
    await task.locator("summary").first().click();
    await expect(
        task.getByRole("button", { name: "Mulai sesi delivery", exact: true }),
    ).toBeVisible();
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
    await task
        .getByLabel("Hasil serah terima", { exact: true })
        .selectOption("partial");
    await task
        .getByLabel("Diterima Biskuit Kelapa 300 g (contoh)", { exact: true })
        .fill("120");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Ajukan POD untuk review", exact: true })
        .click();
    await expect(
        task.getByText("Alasan wajib direkam pada item terkait.", {
            exact: true,
        }),
    ).toBeVisible();
    await task
        .getByLabel("Alasan item Biskuit Kelapa 300 g (contoh)", {
            exact: true,
        })
        .fill("Kemasan rusak");
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(task.getByText(/Draft POD tersimpan offline/)).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    const restored = page
        .locator(".delivery-task")
        .filter({ hasText: "DEMO-DO-001" });
    await restored.locator("summary").first().click();
    await expect(
        restored.getByLabel("Alasan item Biskuit Kelapa 300 g (contoh)", {
            exact: true,
        }),
    ).toHaveValue("Kemasan rusak");
    await restored
        .getByRole("button", { name: "Ajukan POD untuk review", exact: true })
        .click();
    await expect(restored.getByText(/Session closed/).first()).toBeVisible();
    await expect(restored.getByText(/Kemasan rusak/)).toBeVisible();
    await expect(
        restored.getByText("Hasil: Received Partial", { exact: false }),
    ).toBeVisible();
    await page.screenshot({
        path: `test-results/partial-session-${test.info().project.name}.png`,
        fullPage: true,
    });
    await context.setGeolocation({
        latitude: 1.447,
        longitude: 124.825,
        accuracy: 3,
    });
    const next = page
        .locator(".delivery-task")
        .filter({ hasText: "DEMO-DO-002" });
    await next.locator("summary").first().click();
    await startDelivery(next);
    await expect(next.getByText(/Sesi delivery aktif/)).toBeVisible();
});
