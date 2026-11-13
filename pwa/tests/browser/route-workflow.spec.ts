import { test, expect, checkIn, freshSnapshotMeta } from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { saveVisitPhoto, saveDisplayPhoto } from "./visit-helpers";
import {
    switchPersona,
    ensureDaily,
    startDelivery,
    saveDeliveryPhoto,
    openDeliveryTask,
} from "./delivery-helpers";

test("outlet list alone scrolls, full search filters dynamically and dismissal restores focus", async ({
    page,
}) => {
    const provider = new MockProvider("sales", true),
        snapshot = await provider.snapshot();
    snapshot.outlets = Array.from({ length: 120 }, (_, i) => ({
        ...snapshot.outlets[0],
        id: `outlet-${i}`,
        name: `Toko ${i}`,
        address: `Alamat ${i}, Manado`,
    }));
    const meta = freshSnapshotMeta();
    await page.route("**/api/v1/sync/snapshot", (route) =>
        route.fulfill({
            json: {
                ...snapshot,
                updatedAt: meta.updatedAt,
                scope: { ...snapshot.scope, business_date: meta.businessDate },
                office: {
                    id: "1",
                    name: "Kantor Pusat",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                    coordinate_status: "test",
                },
            },
        }),
    );
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await expect(
        page.getByRole("region", { name: "Sesi kerja", exact: true }),
    ).toHaveCount(0);
    const toolbar = page.locator(".directory-toolbar"),
        list = page.locator(".outlet-list");
    const before = await toolbar.boundingBox();
    await list.evaluate((el) => {
        el.scrollTop = 1500;
    });
    expect((await toolbar.boundingBox())!.y).toBe(before!.y);
    expect(await page.evaluate(() => scrollY)).toBe(0);
    expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(
        true,
    );
    const input = page.getByLabel("Cari outlet", { exact: true });
    await input.focus();
    const drawer = page.getByRole("dialog", {
        name: "Pencarian outlet",
        exact: true,
    });
    await expect(drawer).toBeVisible();
    await drawer.getByRole("searchbox").fill("Alamat 87");
    await expect(drawer.locator(".ui-ocard")).toHaveCount(1);
    await expect(drawer.locator(".ui-ocard")).toContainText("Toko 87");
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(input).toBeFocused();
    await input.click();
    await drawer.getByRole("button", { name: /Toko 87/ }).click();
    await expect(page.getByRole("heading", { name: /Toko 87/ })).toBeVisible();
    await expect(page.locator(".outlet-list")).toHaveCount(0);
    expect(
        await page
            .getByRole("region", { name: "Kunjungan outlet" })
            .evaluate((el) => getComputedStyle(el).borderRadius),
    ).toBe("0px");
    expect(
        await page.evaluate(
            () => document.documentElement.scrollHeight <= innerHeight,
        ),
    ).toBe(true);
    await page.screenshot({
        path: `test-results/store-flow-${test.info().project.name}.png`,
        fullPage: true,
    });
    await page.goBack();
    await expect(page.locator(".outlet-list")).toBeVisible();
    await expect
        .poll(() => page.locator(".outlet-list").evaluate((el) => el.scrollTop))
        .toBe(1500);
    await expect(page.getByLabel("Cari outlet", { exact: true })).toHaveValue(
        "Alamat 87",
    );
});

test("sales check-in unlocks mini POS, preview submits through outbox then closes visit", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const open = page.getByRole("button", {
        name: "Buat order di outlet",
        exact: true,
    });
    await expect(open).toHaveCount(0);
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(open).toBeEnabled();
    await open.click();
    await expect(
        page.getByRole("region", { name: "Order penjualan", exact: true }),
    ).toBeVisible();
    await page.getByLabel("Cari produk", { exact: true }).fill("Wafer");
    await expect(page.locator(".pos-card")).toHaveCount(1);
    await expect(
        page
            .getByRole("button", { name: /^Principal .* terkunci$/ })
            .or(page.getByLabel("Principal", { exact: true })),
    ).toBeVisible();
    await page
        .getByLabel("Kuantitas Wafer Cokelat 24 g Karton", { exact: true })
        .fill("2");
    await saveDisplayPhoto(page);
    await page.getByRole("button", { name: /SKU · .* · Lihat$/ }).click();
    const summary = page.getByRole("dialog", { name: "Ringkasan order" });
    await expect(summary).toContainText("Wafer");
    await page.screenshot({
        path: `test-results/pos-preview-${test.info().project.name}.png`,
        fullPage: true,
    });
    await summary
        .getByRole("button", { name: "Kirim order", exact: true })
        .click();
    await page
        .getByRole("region", { name: "Hasil kirim order" })
        .getByRole("button", { name: "Lihat order", exact: true })
        .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await saveVisitPhoto(page, "check-out");
    await page.getByLabel(/^Catatan/).fill("Order diajukan");
    await page
        .getByRole("button", { name: "Selesai kunjungan", exact: true })
        .first()
        .click();
    await expect(
        page.getByRole("status").filter({ hasText: /Kunjungan ditutup lokal/ }),
    ).toBeVisible();
});

test("delivery partial items, item reasons and Biaya toko persist without double charging", async ({
    page,
}) => {
    await page.goto("./");
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    let task = await openDeliveryTask(page, "DEMO-DO-001");
    await startDelivery(task);
    // Biaya toko dibuka dari hub toko (kembali dulu dari layar serah terima).
    await task
        .getByRole("region", { name: "Serah terima DEMO-DO-001" })
        .getByRole("button", { name: "Kembali" })
        .click();
    await task.getByRole("button", { name: /^Biaya operasional toko/ }).click();
    const biaya = page.getByRole("region", { name: "Biaya toko" });
    await biaya.getByLabel("Parkir").fill("25000");
    await biaya.getByRole("button", { name: /^Simpan biaya/ }).click();
    await expect(biaya).toHaveCount(0);
    await task.getByRole("button", { name: "Mulai serah terima" }).click();
    await task.getByRole("button", { name: "Sebagian", exact: true }).click();
    await task.getByLabel("Penerima", { exact: true }).fill("PIC Outlet");
    for (const field of await task.getByLabel(/^Diterima /).all())
        await field.fill("1");
    const choices = task.getByLabel(/^Alasan item .* \(wajib\)/);
    for (const field of await choices.all())
        await field.selectOption("ITEM RUSAK");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(
        task.getByRole("status").filter({ hasText: "Draft POD tersimpan" }),
    ).toContainText("Draft POD tersimpan");
    const fees = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const req = indexedDB.open("fmcg-field-demo-v1");
            req.onsuccess = () => resolve(req.result);
        });
        const rows = await new Promise<any[]>((resolve) => {
            const req = db.transaction("outbox").objectStore("outbox").getAll();
            req.onsuccess = () => resolve(req.result);
        });
        db.close();
        return rows
            .filter((row) => row.command.type === "field_expense.request")
            .map((row) => row.command.payload);
    });
    expect(fees).toHaveLength(1);
    expect(fees[0].expense_scope).toBe("outlet");
    expect(fees[0].category).toBe("store_parking");
    expect(fees[0].outlet_id).toBeTruthy();
    expect(fees[0].delivery_id).toBeNull();
    await page.reload();
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    task = await openDeliveryTask(page, "DEMO-DO-001");
    await task.getByRole("button", { name: "Mulai serah terima" }).click();
    for (const field of await task
        .getByLabel(/^Alasan item .* \(wajib\)/)
        .all())
        await expect(field).toHaveValue("ITEM RUSAK");
    await page.screenshot({
        path: `test-results/delivery-flow-${test.info().project.name}.png`,
        fullPage: false,
    });
    await task
        .getByRole("button", { name: "Selesai serah terima", exact: true })
        .click();
    await expect(task.getByText(/Session closed/).first()).toBeVisible();
});
