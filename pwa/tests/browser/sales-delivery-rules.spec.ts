import {
    sendOrder,
    applyDiscount,
    fillQty,
    koreksiEditLines,
    activity,
    openActivity,
} from "./visit-helpers";
import { switchPersona } from "./delivery-helpers";
import { expect, test } from "./session-fixture";
import {
    ensureDaily,
    saveDeliveryPhoto,
    startDelivery,
    openDeliveryTask,
    backFromTask,
} from "./delivery-helpers";
import {
    leaveClosedVisit,
    leaveVisit,
    saveDisplayPhoto,
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
            .getByRole("button", {
                name: "Perbarui lokasi outlet",
                exact: true,
            })
            .click();
        await page
            .getByRole("button", { name: "Mulai kunjungan", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Buat order di outlet", exact: true })
            .click();
        await page
            .getByRole("button", { name: "Detail SKU Biskuit Kelapa 300 g" })
            .click();
        const info = page.getByRole("dialog", {
            name: "Biskuit Kelapa 300 g",
        });
        await expect(
            info.getByText("1 karton = 144 pcs · 1 renceng = 12 pcs", {
                exact: true,
            }),
        ).toBeVisible();
        await info
            .getByRole("button", { name: "Tutup", exact: true })
            .last()
            .click();
        await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
        await applyDiscount(page, 5, "Promo contoh");
        await saveDisplayPhoto(page);
        await page.locator(".pos-card").first().scrollIntoViewIfNeeded();
        await page.screenshot({
            path: `test-results/order-tiers-${test.info().project.name}.png`,
            fullPage: true,
        });
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
        const liveRequest = page.waitForRequest(
            (request) =>
                request.url().endsWith("/api/v1/sync/commands") &&
                request
                    .postDataJSON()
                    ?.payload?.lines?.some(
                        (l: { discounts?: { kind: string }[] }) =>
                            l.discounts?.some((d) => d.kind === "tactical"),
                    ),
        );
        await sendOrder(page);
        expect((await liveRequest).headers()["x-csrf-token"]).toBe(
            "fixture-command-csrf",
        );
        await leaveVisit(page);
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
        await openActivity(page);
        await activity(page).first().click();
        await expect(
            page
                .getByRole("dialog")
                .getByText(
                    approved
                        ? /pengajuan diskon disetujui/
                        : /pengajuan diskon ditolak/,
                ),
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
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    const task = await openDeliveryTask(page, "DEMO-DO-001");
    await expect(
        task.getByRole("button", { name: "Mulai sesi delivery", exact: true }),
    ).toBeVisible();
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
    await task.getByRole("button", { name: "Sebagian", exact: true }).click();
    await task.getByLabel("Diterima Biskuit Kelapa 300 g (contoh)").fill("120");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Selesai serah terima", exact: true })
        .click();
    await expect(
        task.getByText("Pilih alasan untuk setiap item yang tidak diterima", {
            exact: false,
        }),
    ).toBeVisible();
    await task
        .getByLabel("Catatan item Biskuit Kelapa 300 g (contoh)", {
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
    const restored = await openDeliveryTask(page, "DEMO-DO-001");
    await restored.getByRole("button", { name: "Mulai serah terima" }).click();
    await expect(
        restored.getByLabel("Catatan item Biskuit Kelapa 300 g (contoh)", {
            exact: true,
        }),
    ).toHaveValue("Kemasan rusak");
    await restored
        .getByLabel("Alasan item Biskuit Kelapa 300 g (contoh) (wajib)")
        .selectOption("ITEM RUSAK");
    await restored
        .getByRole("button", { name: "Selesai serah terima", exact: true })
        .click();
    await expect(restored.getByText(/Session closed/).first()).toBeVisible();
    await expect(restored.getByText(/Kemasan rusak/)).toBeVisible();
    await expect(
        restored.getByText("Received Partial", { exact: false }).first(),
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
    await backFromTask(page);
    const next = await openDeliveryTask(page, "DEMO-DO-002");
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
    await page
        .getByRole("button", { name: "Detail SKU Biskuit Mini 24 pcs" })
        .click();
    const mini = page.getByRole("dialog", { name: "Biskuit Mini 24 pcs" });
    await expect(
        mini.getByText("1 box = 24 pcs · 1 pack = 6 pcs", { exact: true }),
    ).toBeVisible();
    await mini
        .getByRole("button", { name: "Tutup", exact: true })
        .last()
        .click();
    await fillQty(page, "Biskuit Mini 24 pcs", "Pack", 2);
    await fillQty(page, "Biskuit Kelapa 300 g", "Renceng", 1);
    await applyDiscount(page, 5, "Promo kemasan SKU");
    await saveDisplayPhoto(page);
    await sendOrder(page);
    await saveVisitPhoto(page, "check-out");
    await page
        .getByRole("button", { name: "Selesai kunjungan", exact: true })
        .first()
        .click();
    await leaveClosedVisit(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page
        .getByLabel("Alasan keputusan diskon", { exact: true })
        .fill("Revisi jumlah pack");
    await page
        .getByRole("button", { name: "Tolak diskon", exact: true })
        .click();
    await page.getByRole("button", { name: /^Riwayat pengajuan/ }).click();
    await page.getByText(/Riwayat SO ·/).click();
    await page
        .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
        .click();
    await page
        .getByLabel("Catatan untuk SPV", { exact: true })
        .fill("Satu pack enam pcs");
    await koreksiEditLines(page, [
        { product: "Biskuit Kelapa 300 g", tier: "Renceng", qty: 0 },
        { product: "Biskuit Mini 24 pcs", tier: "Pack", qty: 1 },
    ]);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    // Draft tersimpan otomatis; muat ulang memulihkan satu pack.
    await page.waitForTimeout(500);
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByRole("button", { name: /^Riwayat pengajuan/ }).click();
    await page.getByText(/Riwayat SO ·/).click();
    await page
        .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Koreksi order" }),
    ).toContainText("1 pak");
    await page
        .getByRole("button", { name: "Kirim ulang", exact: true })
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
    ).toBe("26820");
    expect(
        commands.find((c) => c.type === "sales.order.revise").payload
            .observed_total,
    ).toBe("6000");
});
