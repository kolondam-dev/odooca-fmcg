import { expect, test, type Page, type BrowserContext } from "@playwright/test";
import { saveVisitPhoto } from "./visit-helpers";
async function openVisit(page: Page) {
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
}
async function prepare(page: Page, context: BrowserContext) {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Buka sesi kerja",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await openVisit(page);
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        page.getByText("Di dalam geofence", { exact: true }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
}
test("mandatory photo draft restores offline, binds both visit actions and remains read-only in history", async ({
    page,
    context,
}) => {
    await prepare(page, context);
    const start = page.getByRole("button", {
        name: "Mulai kunjungan",
        exact: true,
    });
    await expect(start).toBeDisabled();
    await saveVisitPhoto(page, "check-in");
    await expect(start).toBeEnabled();
    await context.setOffline(true);
    await page.reload();
    await openVisit(page);
    const photo = page.getByRole("group", {
        name: "Foto check-in kunjungan",
        exact: true,
    });
    await expect(photo.getByAltText("Pinpoint tanpa basemap")).toBeVisible();
    await expect(
        photo.getByText("Paket foto tersimpan untuk check-in outlet ini.", {
            exact: true,
        }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(start).toBeEnabled();
    await photo.screenshot({
        path: `test-results/visit-photo-${test.info().project.name}.png`,
    });
    await start.click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    const history = page.locator("details").filter({
        has: page.getByText("Bukti foto check-in tersimpan", {
            exact: true,
        }),
    });
    await history.locator("summary").click();
    await expect(history.getByAltText("Pinpoint tanpa basemap")).toBeVisible();
    await expect(history.getByLabel("Foto bukti")).toHaveCount(0);
    const close = page.getByRole("button", {
        name: "Tutup kunjungan",
        exact: true,
    });
    await expect(close).toBeDisabled();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByLabel("Catatan kunjungan")
        .fill("Selesai tanpa order pada simulasi");
    await close.click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();
    await page
        .getByText("Bukti foto check-out tersimpan", { exact: true })
        .click();
    const refs = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<any[]>((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return rows.map((r) => ({
            type: r.command.type,
            owner: r.owner,
            visit: r.command.payload.visit_uuid,
            session: r.command.payload.work_session_id,
            version: r.command.payload.evidence_version,
            evidence: r.command.payload.evidence,
        }));
    });
    expect(refs).toHaveLength(2);
    expect(new Set(refs.map((r) => r.visit)).size).toBe(1);
    expect(new Set(refs.map((r) => r.session)).size).toBe(1);
    expect(new Set(refs.map((r) => r.evidence.id)).size).toBe(2);
    expect(
        refs.every(
            (r) => r.version === 1 && r.evidence.packageHash.length === 64,
        ),
    ).toBe(true);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await context.setOffline(false);
    await expect(
        page
            .locator(".activity")
            .getByText("Diterima simulator", { exact: true }),
    ).toHaveCount(2, { timeout: 20000 });
});
test("tampered persisted parent media blocks restore and both queued actions after reconnect", async ({
    page,
    context,
}) => {
    await prepare(page, context);
    await saveVisitPhoto(page, "check-in");
    await context.setOffline(true);
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByLabel("Catatan kunjungan")
        .fill("Selesai kunjungan offline");
    await page
        .getByRole("button", { name: "Tutup kunjungan", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();
    await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<any[]>((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        const parent = rows.find(
                (r) => r.command.type === "sales.visit.check_in",
            ),
            key = `${parent.owner}:${parent.command.payload.evidence.id}`;
        const tx = db.transaction("evidence", "readwrite"),
            get = tx.objectStore("evidence").get(key);
        get.onsuccess = () => {
            const value = get.result;
            value.blob = new Blob(["tampered"], { type: "image/jpeg" });
            tx.objectStore("evidence").put(value);
        };
        await new Promise<void>((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        db.close();
    });
    await page.reload();
    await openVisit(page);
    await expect(
        page
            .getByRole("alert")
            .filter({ hasText: "Isi foto/snapshot/metadata berubah" }),
    ).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await context.setOffline(false);
    await expect(
        page.getByRole("button", { name: "Sinkronkan", exact: true }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "Sinkronkan", exact: true }).click();
    await expect(
        page.getByRole("button", { name: "Perlu review 1", exact: true }),
    ).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Menunggu 1", exact: true }),
    ).toBeVisible();
    await expect(
        page
            .locator(".activity")
            .getByText("Diterima simulator", { exact: true }),
    ).toHaveCount(0);
});
