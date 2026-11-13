import { switchPersona } from "./delivery-helpers";
import { syncNow, activity, openActivity } from "./visit-helpers";
import {
    backFromTask,
    closeDeliveryScreens,
    ensureDaily,
    openDeliveryTask,
    saveDeliveryPhoto,
    startDelivery,
} from "./delivery-helpers";
import { expect, test, type Page } from "./session-fixture";
async function openDelivery(page: Page) {
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    return openDeliveryTask(page, "DEMO-DO-001");
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
    await startDelivery(task);
    await expect(
        task.getByRole("button", { name: "Selesai serah terima" }),
    ).toBeDisabled();
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(task.getByText(/Draft POD tersimpan offline/)).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.reload();
    task = await openDelivery(page);
    await startDelivery(task);
    await expect(task.getByLabel("Penerima", { exact: true })).toHaveValue(
        "Budi Outlet",
    );
    await expect(task.getByAltText("Pinpoint tanpa basemap")).toBeVisible();
    await task.getByRole("button", { name: "Selesai serah terima" }).click();
    await expect(task.getByText(/POD tersimpan ·/)).toBeVisible();
    await expect(
        page
            .getByRole("region", { name: "Delivery DEMO-DO-001", exact: true })
            .locator('input[type="file"]'),
    ).toHaveCount(0);
    await page.screenshot({
        path: `test-results/pod-${test.info().project.name}.png`,
        fullPage: true,
    });
    await closeDeliveryScreens(page);
    await context.setOffline(false);
    await openActivity(page);
    await expect(
        activity(page).getByText("POD • DEMO-DO-001", { exact: true }),
    ).toBeVisible();
    await expect(
        activity(page).getByText("Menunggu approval", { exact: true }),
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
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Outlet");
    await saveDeliveryPhoto(task);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task.getByRole("button", { name: "Selesai serah terima" }).click();
    await expect(task.getByText(/POD tersimpan ·/)).toBeVisible();
    await closeDeliveryScreens(page);
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
        restored.getByRole("button", { name: "Selesai serah terima" }),
    ).toHaveCount(0);
    await closeDeliveryScreens(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await context.setOffline(false);
    const queue = await syncNow(page);
    await expect(queue.locator(".ui-chip", { hasText: "Gagal" })).toHaveCount(
        1,
    );
    await expect(
        queue.getByText("Menunggu approval", { exact: true }),
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
    const initial = await openDelivery(page);
    await startDelivery(initial);
    await closeDeliveryScreens(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Mode respons").selectOption("rejected");
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    let task = await openDeliveryTask(page, "DEMO-DO-001");
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Budi Lama");
    await saveDeliveryPhoto(task);
    await task.getByRole("button", { name: "Selesai serah terima" }).click();
    await expect(
        task.getByRole("button", { name: "Koreksi POD ditolak" }),
    ).toBeVisible();
    // Dua toko dalam satu trip: POD ditolak server tidak menghitung selesai; koreksi tetap terjangkau.
    const trip = page.getByRole("button", { name: /^Buka TRIP/ });
    await expect(trip).toContainText("0/2 toko selesai");
    await backFromTask(page);
    await expect(
        page.getByRole("button", { name: /^Check-in toko · / }),
    ).toContainText("Toko Sinar Pagi");
    await expect(
        page
            .getByRole("region", { name: /^Daftar toko / })
            .getByText("Berikutnya", { exact: true }),
    ).toHaveCount(1);
    task = await openDeliveryTask(page, "DEMO-DO-001");
    await expect(
        task.getByRole("button", { name: "Koreksi POD ditolak" }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await task.getByRole("button", { name: "Koreksi POD ditolak" }).click();
    await startDelivery(task);
    await expect(
        task.getByRole("button", { name: "Selesai serah terima" }),
    ).toBeDisabled();
    await task.getByLabel("Penerima", { exact: true }).fill("Siti Benar");
    await task
        .getByLabel("Alasan koreksi", { exact: true })
        .fill("Nama penerima diperbaiki");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Simpan draft POD", exact: true })
        .click();
    await expect(task.getByText(/Draft POD tersimpan offline/)).toBeVisible();
    await page.reload();
    task = await openDelivery(page);
    await task.getByRole("button", { name: "Koreksi POD ditolak" }).click();
    await startDelivery(task);
    await expect(task.getByLabel("Penerima", { exact: true })).toHaveValue(
        "Siti Benar",
    );
    await expect(
        task.getByLabel("Alasan koreksi", { exact: true }),
    ).toHaveValue("Nama penerima diperbaiki");
    await task.getByRole("button", { name: "Selesai serah terima" }).click();
    await expect(
        task.getByText("Riwayat POD (2)", { exact: true }),
    ).toBeVisible();
    // Koreksi valid (anak) menghitung selesai; induk ditolak tidak dihitung ganda.
    await expect(trip).toContainText("1/2 toko selesai");
    await expect(
        task.getByRole("button", { name: "Koreksi POD ditolak" }),
    ).toHaveCount(0);
    await expect(
        page
            .getByRole("region", { name: "Delivery DEMO-DO-001", exact: true })
            .locator('input[type="file"]'),
    ).toHaveCount(0);
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
    await closeDeliveryScreens(page);
    await context.setOffline(false);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openActivity(page);
    await expect(
        activity(page).getByText("Menunggu approval", { exact: true }),
    ).toHaveCount(1);
});
