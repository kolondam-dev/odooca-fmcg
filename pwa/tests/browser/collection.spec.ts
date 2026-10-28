import { expect, test, type Page, type Locator } from "@playwright/test";
async function open(page: Page) {
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Persona demo").selectOption("delivery");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    const task = page
        .locator(".collection-task")
        .filter({ has: page.locator("summary", { hasText: "SIM-TAGIHAN-1" }) });
    await task.locator("summary").click();
    return task;
}
async function photo(task: Locator) {
    await task.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(task.getByAltText("Pratinjau foto bukti lokal")).toBeVisible();
    await task
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await task
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(
        task.getByText(
            "Foto dan pinpoint simulasi tersimpan lokal. Peta resmi belum tersedia.",
        ),
    ).toBeVisible();
}
async function form(task: Locator) {
    await task.getByLabel("Pembayar", { exact: true }).fill("Budi Outlet");
    await task
        .getByLabel("Nominal diterima (Rupiah bulat)", { exact: true })
        .fill("500000");
    await task.getByLabel("Nomor tanda terima", { exact: true }).fill("KW-001");
    await photo(task);
}
test("cash collection draft restores offline and syncs only for review", async ({
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
    let task = await open(page);
    await expect(
        task.getByRole("button", { name: "Ajukan penerimaan untuk review" }),
    ).toBeDisabled();
    await form(task);
    await task.getByRole("button", { name: "Simpan draft collection" }).click();
    await expect(
        task.getByText(/Draft collection tersimpan offline/),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.reload();
    task = await open(page);
    await expect(task.getByLabel("Pembayar", { exact: true })).toHaveValue(
        "Budi Outlet",
    );
    await expect(
        task.getByLabel("Nominal diterima (Rupiah bulat)"),
    ).toHaveValue("500000");
    await expect(
        task.getByAltText("Pinpoint simulasi tanpa basemap"),
    ).toBeVisible();
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(task.getByText(/Pencatatan tersimpan ·/)).toBeVisible();
    await expect(task.locator('input[type="file"]')).toHaveCount(0);
    await expect(
        page.getByText("Saldo contoh Rp 1.000.000", { exact: false }).first(),
    ).toBeVisible();
    await page.screenshot({
        path: `test-results/collection-${test.info().project.name}.png`,
        fullPage: true,
    });
    await context.setOffline(false);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toHaveCount(1);
});
test("transfer requires reference and prevents excessive or duplicate collection", async ({
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
    const task = await open(page);
    await form(task);
    await task.getByLabel("Metode penerimaan").selectOption("transfer");
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(task.getByText(/Periksa pembayar/)).toBeVisible();
    await task
        .getByLabel("Referensi transfer", { exact: true })
        .fill("BANK-001");
    await task.getByLabel("Nominal diterima (Rupiah bulat)").fill("1000001");
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(
        task.getByText("Nominal melebihi saldo tagihan contoh."),
    ).toBeVisible();
    await task.getByLabel("Nominal diterima (Rupiah bulat)").fill("500000");
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(task.getByText(/Pencatatan tersimpan ·/)).toBeVisible();
    const second = page
        .locator(".collection-task")
        .filter({ has: page.locator("summary", { hasText: "SIM-TAGIHAN-2" }) });
    await second.locator("summary").click();
    await context.setGeolocation({
        latitude: 1.447,
        longitude: 124.825,
        accuracy: 3,
    });
    await form(second);
    await second.getByLabel("Nomor tanda terima").fill("kw / 001");
    await second
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(second.getByText(/sudah dipakai/)).toBeVisible();
    await expect(
        second.getByRole("button", { name: "Ajukan penerimaan untuk review" }),
    ).toBeEnabled();
});
test("corrupt offline collection photo holds restore and reconnect sync", async ({
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
    const task = await open(page);
    await form(task);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(task.getByText(/Pencatatan tersimpan ·/)).toBeVisible();
    await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction("evidence", "readwrite"),
            get = tx.objectStore("evidence").getAll();
        get.onsuccess = () => {
            for (const r of get.result) {
                r.blob = new Blob(["corrupt"], { type: "image/jpeg" });
                tx.objectStore("evidence").put(r);
            }
        };
        await new Promise<void>((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        db.close();
    });
    await page.reload();
    const restored = await open(page);
    await expect(
        restored.getByText(/Collection\/tagihan\/foto tidak valid/),
    ).toBeVisible();
    await expect(
        restored.getByRole("button", {
            name: "Ajukan penerimaan untuk review",
        }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await context.setOffline(false);
    await page.getByRole("button", { name: "Sinkronkan", exact: true }).click();
    await expect(
        page.getByRole("button", { name: "Perlu review 1", exact: true }),
    ).toBeVisible();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toHaveCount(0);
});

test("business rejection opens offline correction draft and preserves immutable parent", async ({
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
    await open(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Respons simulator").selectOption("rejected");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    let task = page
        .locator(".collection-task")
        .filter({ hasText: "SIM-TAGIHAN-1" });
    await task.locator("summary").first().click();
    await task.getByLabel("Pembayar", { exact: true }).fill("Budi Lama");
    await task.getByLabel("Nominal diterima (Rupiah bulat)").fill("500000");
    await task.getByLabel("Nomor tanda terima").fill("KW-001");
    await photo(task);
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(
        task.getByRole("button", { name: "Koreksi collection ditolak" }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task
        .getByRole("button", { name: "Koreksi collection ditolak" })
        .click();
    await expect(
        task.getByRole("button", { name: "Ajukan penerimaan untuk review" }),
    ).toBeDisabled();
    await task.getByLabel("Pembayar", { exact: true }).fill("Siti Benar");
    await task
        .getByLabel("Alasan koreksi collection", { exact: true })
        .fill("Nama penerima diperbaiki");
    await photo(task);
    await task
        .getByRole("button", { name: "Simpan draft collection", exact: true })
        .click();
    await expect(
        task.getByText(/Draft collection tersimpan offline/),
    ).toBeVisible();
    await page.reload();
    task = await open(page);
    await task
        .getByRole("button", { name: "Koreksi collection ditolak" })
        .click();
    await expect(task.getByLabel("Pembayar", { exact: true })).toHaveValue(
        "Siti Benar",
    );
    await expect(
        task.getByLabel("Alasan koreksi collection", { exact: true }),
    ).toHaveValue("Nama penerima diperbaiki");
    await task
        .getByRole("button", { name: "Ajukan penerimaan untuk review" })
        .click();
    await expect(task.getByText(/Parent tetap utuh di Lainnya/)).toBeVisible();
    await expect(
        task.getByRole("button", { name: "Koreksi collection ditolak" }),
    ).toHaveCount(0);
    await expect(task.locator('input[type="file"]')).toHaveCount(0);
    const rows = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<any[]>((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return rows.filter(
            (r) => r.command.type === "collection.receipt.submit",
        );
    });
    const parent = rows.find((r) => !r.command.payload.supersedes_uuid),
        child = rows.find((r) => r.command.payload.supersedes_uuid);
    expect(parent.command.payload.payer).toBe("Budi Lama");
    expect(parent.state).toBe("rejected");
    expect(child.command.payload.payer).toBe("Siti Benar");
    expect(child.command.payload.supersedes_uuid).toBe(
        parent.command.client_uuid,
    );
    expect(child.command.payload.evidence.id).not.toBe(
        parent.command.payload.evidence.id,
    );
    await page.screenshot({
        path: `test-results/collection-correction-${test.info().project.name}.png`,
        fullPage: true,
    });
    await context.setOffline(false);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toHaveCount(1);
});
