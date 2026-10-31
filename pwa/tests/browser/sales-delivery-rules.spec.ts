import { switchPersona } from "./delivery-helpers";
import { expect, test } from "@playwright/test";
import {
    ensureDaily,
    saveDeliveryPhoto,
    startDelivery,
} from "./delivery-helpers";
import { saveDisplayPhoto, saveVisitPhoto } from "./visit-helpers";
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
            page.getByText("Buka sesi kerja sebelum membuka daftar outlet."),
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
            .getByRole("button", { name: "Mulai kunjungan", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Buat order di outlet", exact: true })
            .click();
        const units = page.getByRole("group", {
            name: "Satuan Biskuit Kelapa 300 g",
            exact: true,
        });
        await expect(
            units.getByRole("button", { name: "Renceng", exact: true }),
        ).toBeVisible();
        await expect(
            page
                .getByText("1 Karton = 144 Pcs · 1 Renceng = 12 Pcs", {
                    exact: true,
                })
                .first(),
        ).toBeVisible();
        await units
            .getByRole("button", { name: "Renceng", exact: true })
            .click();
        await page
            .getByLabel("Kuantitas Biskuit Kelapa 300 g", { exact: true })
            .fill("1");
        await page.locator("details.order-extra > summary").click();
        await page.getByLabel("Diskon diminta (%)", { exact: true }).fill("5");
        await page
            .getByLabel("Alasan permintaan diskon", { exact: true })
            .fill("Promo contoh");
        await saveDisplayPhoto(page);
        await page.locator(".product-card").first().scrollIntoViewIfNeeded();
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
                name: "Simpan ke antrean",
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
                name: approved ? "Setujui diskon" : "Tolak diskon",
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

test("SKU packaging drives new order and offline correction prices independently", async ({
    page,
    context,
}) => {
    await page.goto("./");
    await ensureDaily(page);
    await page
        .getByRole("navigation")
        .getByRole("button", { name: "Sales", exact: true })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Buat order di outlet", exact: true })
        .click();
    const units = page.getByRole("group", {
        name: "Satuan Biskuit Mini 24 pcs",
        exact: true,
    });
    await expect(
        units.getByRole("button", { name: "Box", exact: true }),
    ).toBeVisible();
    await expect(
        units.getByRole("button", { name: "Pack", exact: true }),
    ).toBeVisible();
    await expect(
        page.getByText("1 Box = 24 Pcs · 1 Pack = 6 Pcs", {
            exact: true,
        }),
    ).toBeVisible();
    await units.getByRole("button", { name: "Pack", exact: true }).click();
    await page
        .getByLabel("Kuantitas Biskuit Mini 24 pcs", { exact: true })
        .fill("2");
    await page
        .getByRole("group", {
            name: "Satuan Biskuit Kelapa 300 g",
            exact: true,
        })
        .getByRole("button", { name: "Renceng", exact: true })
        .click();
    await page
        .getByLabel("Kuantitas Biskuit Kelapa 300 g", { exact: true })
        .fill("1");
    await page.locator("details.order-extra > summary").click();
    await page.getByLabel("Diskon diminta (%)", { exact: true }).fill("5");
    await page
        .getByLabel("Alasan permintaan diskon", { exact: true })
        .fill("Promo kemasan SKU");
    await saveDisplayPhoto(page);
    await page
        .getByRole("button", { name: "Simpan ke antrean", exact: true })
        .click();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByRole("button", { name: "Tutup kunjungan", exact: true })
        .click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page
        .getByLabel("Alasan keputusan diskon", { exact: true })
        .fill("Revisi jumlah pack");
    await page
        .getByRole("button", { name: "Tolak diskon", exact: true })
        .click();
    await page.getByText(/Riwayat SO ·/).click();
    await page
        .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
        .click();
    await expect(
        page
            .getByLabel("Satuan revisi Biskuit Mini 24 pcs", { exact: true })
            .locator('option[value="pack"]'),
    ).toHaveText("Pack6pcs");
    await page
        .getByLabel("Qty revisi Biskuit Kelapa 300 g", { exact: true })
        .fill("0");
    await page
        .getByLabel("Qty revisi Biskuit Mini 24 pcs", { exact: true })
        .fill("1");
    await page.getByLabel("Diskon revisi (%)", { exact: true }).fill("0");
    await page
        .getByLabel("Alasan koreksi SO", { exact: true })
        .fill("Satu pack enam pcs");
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page
        .getByRole("button", { name: "Simpan draft koreksi SO", exact: true })
        .click();
    await expect(
        page.getByText("Draft koreksi SO tersimpan offline.", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByText(/Riwayat SO ·/).click();
    await page
        .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
        .click();
    await expect(
        page.getByLabel("Satuan revisi Biskuit Mini 24 pcs", { exact: true }),
    ).toHaveValue("pack");
    await page
        .getByRole("button", { name: "Ajukan revisi SO", exact: true })
        .click();
    await expect(page.getByText(/Revisi baru masuk antrean/)).toBeVisible();
    const commands = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<any[]>((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return rows
            .map((r) => r.command)
            .filter(
                (c) =>
                    c.type === "sales.order.submit" ||
                    c.type === "sales.order.revise",
            );
    });
    expect(
        commands.find((c) => c.type === "sales.order.submit").payload
            .observed_total,
    ).toBe("26220");
    expect(
        commands.find((c) => c.type === "sales.order.revise").payload
            .observed_total,
    ).toBe("6000");
});
