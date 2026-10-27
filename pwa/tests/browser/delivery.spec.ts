import { expect, test, type Page } from "@playwright/test";
async function openDelivery(page: Page) {
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Persona demo").selectOption("delivery");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    const task = page
        .locator("details")
        .filter({ has: page.locator("summary", { hasText: "DEMO-DO-001" }) });
    await task.locator("summary").click();
    return task;
}
test("POD draft restores offline and queues only for review, with read-only proof", async ({
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
    let task = await openDelivery(page);
    await expect(
        task.getByRole("button", { name: "Ajukan POD untuk review" }),
    ).toBeDisabled();
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
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
            { exact: false },
        ),
    ).toBeVisible();
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(task.getByText(/Draft POD tersimpan offline/)).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.reload();
    task = await openDelivery(page);
    await expect(task.getByLabel("Penerima", { exact: true })).toHaveValue(
        "Budi Outlet",
    );
    await expect(
        task.getByAltText("Pinpoint simulasi tanpa basemap"),
    ).toBeVisible();
    await task.getByRole("button", { name: "Ajukan POD untuk review" }).click();
    await expect(task.getByText(/POD tersimpan ·/)).toBeVisible();
    await expect(task.locator('input[type="file"]')).toHaveCount(0);
    await page.screenshot({
        path: `test-results/pod-${test.info().project.name}.png`,
        fullPage: true,
    });
    await context.setOffline(false);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("POD • DEMO-DO-001", { exact: true }),
    ).toBeVisible();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toBeVisible();
});
test("corrupt offline POD media blocks restore and reconnect sync", async ({
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
    const task = await openDelivery(page);
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
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
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task.getByRole("button", { name: "Ajukan POD untuk review" }).click();
    await expect(task.getByText(/POD tersimpan ·/)).toBeVisible();
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
    const restored = await openDelivery(page);
    await expect(
        restored.getByText(/POD\/manifest\/foto tidak valid/),
    ).toBeVisible();
    await expect(
        restored.getByRole("button", { name: "Ajukan POD untuk review" }),
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
async function savePodPhoto(task: ReturnType<Page["locator"]>) {
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
    await openDelivery(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Respons simulator").selectOption("rejected");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    let task = page
        .locator(".delivery-task")
        .filter({ hasText: "DEMO-DO-001" });
    await task.locator("summary").first().click();
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Lama");
    await savePodPhoto(task);
    await task.getByRole("button", { name: "Ajukan POD untuk review" }).click();
    await expect(
        task.getByRole("button", { name: "Koreksi POD ditolak" }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task.getByRole("button", { name: "Koreksi POD ditolak" }).click();
    await expect(
        task.getByRole("button", { name: "Ajukan POD untuk review" }),
    ).toBeDisabled();
    await task.getByLabel("Penerima", { exact: true }).fill("Siti Benar");
    await task
        .getByLabel("Alasan koreksi", { exact: true })
        .fill("Nama penerima diperbaiki");
    await savePodPhoto(task);
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(task.getByText(/Draft POD tersimpan offline/)).toBeVisible();
    await page.reload();
    task = await openDelivery(page);
    await task.getByRole("button", { name: "Koreksi POD ditolak" }).click();
    await expect(task.getByLabel("Penerima", { exact: true })).toHaveValue(
        "Siti Benar",
    );
    await expect(
        task.getByLabel("Alasan koreksi", { exact: true }),
    ).toHaveValue("Nama penerima diperbaiki");
    await task.getByRole("button", { name: "Ajukan POD untuk review" }).click();
    await expect(
        task.getByText("Riwayat POD (2)", { exact: true }),
    ).toBeVisible();
    await expect(
        task.getByRole("button", { name: "Koreksi POD ditolak" }),
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
        return rows.filter((r) => r.command.type === "delivery.pod.submit");
    });
    const parent = rows.find((r) => !r.command.payload.supersedes_uuid),
        child = rows.find((r) => r.command.payload.supersedes_uuid);
    expect(parent.command.payload.recipient).toBe("Budi Lama");
    expect(parent.state).toBe("rejected");
    expect(child.command.payload.recipient).toBe("Siti Benar");
    expect(child.command.payload.supersedes_uuid).toBe(
        parent.command.client_uuid,
    );
    expect(child.command.payload.evidence.id).not.toBe(
        parent.command.payload.evidence.id,
    );
    await page.screenshot({
        path: `test-results/pod-correction-${test.info().project.name}.png`,
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
