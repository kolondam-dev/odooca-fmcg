import { test, expect, checkIn } from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { saveVisitPhoto, saveDisplayPhoto } from "./visit-helpers";
import {
    switchPersona,
    ensureDaily,
    startDelivery,
    saveDeliveryPhoto,
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
    await page.route("**/api/v1/sync/snapshot", (route) =>
        route.fulfill({
            json: {
                ...snapshot,
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
    await expect(drawer.locator(".outlet-row")).toHaveCount(1);
    await expect(drawer.locator(".outlet-row")).toContainText("Toko 87");
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(input).toBeFocused();
    await input.click();
    await drawer.getByRole("button", { name: /Toko 87/ }).click();
    await expect(
        page.getByRole("heading", { name: "Toko 87", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".outlet-list")).toHaveCount(0);
    expect(
        await page
            .locator(".visit-panel")
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
        name: "Open session",
        exact: true,
    });
    await expect(open).toBeDisabled();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(open).toBeEnabled();
    await open.click();
    await page.getByLabel("Cari produk", { exact: true }).fill("Wafer");
    await expect(page.locator(".product-card")).toHaveCount(1);
    await expect(
        page
            .locator(".pos-toolbar")
            .getByRole("group", { name: "Principal", exact: true }),
    ).toBeVisible();
    await page
        .getByLabel("Kuantitas Wafer Cokelat 24 g", { exact: true })
        .fill("2");
    await saveDisplayPhoto(page);
    await page
        .getByRole("button", { name: "Preview order", exact: true })
        .last()
        .click();
    await expect(
        page.getByRole("region", { name: "Preview order", exact: true }),
    ).toContainText("Wafer");
    await expect(page.getByLabel("Cari produk", { exact: true })).toBeHidden();
    await page.screenshot({
        path: `test-results/pos-preview-${test.info().project.name}.png`,
        fullPage: true,
    });
    await page
        .getByRole("button", { name: "Kirim order", exact: true })
        .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Close session", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await saveVisitPhoto(page, "check-out");
    await page.getByLabel("Catatan kunjungan").fill("Order diajukan");
    await page
        .getByRole("button", { name: "Tutup kunjungan", exact: true })
        .click();
    await expect(
        page.getByRole("status").filter({ hasText: /Kunjungan ditutup lokal/ }),
    ).toBeVisible();
});

test("delivery wizard, item reasons and separate DO/outlet costs persist without double charging", async ({
    page,
}) => {
    await page.goto("./");
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    let task = page
        .locator(".delivery-task")
        .filter({ hasText: "DEMO-DO-001" });
    await task.locator("summary").first().click();
    await startDelivery(task);
    await task
        .getByRole("button", { name: "Terima setengah", exact: true })
        .click();
    await task.getByLabel("Penerima", { exact: true }).fill("PIC Outlet");
    const choices = task.locator('select[aria-label^="Pilihan alasan item"]');
    for (const field of await choices.all())
        await field.selectOption("ITEM RUSAK");
    await task
        .getByRole("button", { name: "Preview penerimaan", exact: true })
        .click();
    await expect(task.locator(".delivery-closing")).toContainText(
        "DITERIMA PARSIAL",
    );
    for (const [scope, amount] of [
        ["DO", "50000"],
        ["toko", "25000"],
    ]) {
        const fee = task.getByRole("group", {
            name: `Biaya ${scope}`,
            exact: true,
        });
        await fee.getByLabel(`Nominal ${scope} (Rp)`).fill(amount);
        await fee.getByLabel(`Catatan biaya ${scope}`).fill(`Bongkar ${scope}`);
        await fee
            .getByRole("button", { name: "Ajukan biaya", exact: true })
            .click();
        await expect(fee.getByRole("button")).toBeDisabled();
    }
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
    expect(fees).toHaveLength(2);
    expect(
        fees.find((fee) => fee.expense_scope === "delivery").delivery_id,
    ).toBe("DEMO-DO-001");
    expect(
        fees.find((fee) => fee.expense_scope === "outlet").outlet_id,
    ).toBeTruthy();
    expect(
        fees.find((fee) => fee.expense_scope === "outlet").delivery_id,
    ).toBeNull();
    await page.reload();
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    task = page.locator(".delivery-task").filter({ hasText: "DEMO-DO-001" });
    await task.locator("summary").first().click();
    await task
        .getByRole("button", { name: "Open session", exact: true })
        .click();
    for (const field of await task
        .locator('select[aria-label^="Pilihan alasan item"]')
        .all())
        await expect(field).toHaveValue("ITEM RUSAK");
    await task
        .getByRole("button", { name: "Preview penerimaan", exact: true })
        .click();
    await expect(
        task
            .getByRole("group", { name: "Biaya toko", exact: true })
            .getByRole("button"),
    ).toBeDisabled();
    await page.screenshot({
        path: `test-results/delivery-flow-${test.info().project.name}.png`,
        fullPage: false,
    });
    await task
        .getByRole("button", { name: "Ajukan POD untuk review", exact: true })
        .click();
    await expect(task.locator("summary").first()).toContainText(
        "Session closed",
    );
});
