import { expect, test, type Page } from "./session-fixture";
import {
    ensureDaily,
    switchPersona,
    startDelivery,
    saveDeliveryPhoto,
} from "./delivery-helpers";
async function driver(page: Page) {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
}
async function readDrafts(page: Page) {
    return page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const result = await new Promise<any[]>((resolve) => {
            const r = db.transaction("drafts").objectStore("drafts").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return result.filter(
            (r) =>
                r.key.includes("morning-session-v1") ||
                r.key.includes("delivery-manifest-v1:"),
        );
    });
}
test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
});
for (const reload of [false, true])
    test(`daily sync opens first Delivery offline, reload=${reload}, and saves a session draft`, async ({
        page,
        context,
    }) => {
        await driver(page);
        await ensureDaily(page);
        expect(
            (await readDrafts(page)).filter((r) =>
                r.key.includes("delivery-manifest-v1:"),
            ),
        ).toHaveLength(0);
        await page.evaluate(() => navigator.serviceWorker.ready);
        await page.waitForFunction(() => !!navigator.serviceWorker.controller);
        await context.setOffline(true);
        if (reload) {
            await page.reload();
            await page
                .getByRole("button", { name: "Lainnya", exact: true })
                .click();
            await switchPersona(page, "delivery");
            await ensureDaily(page);
        }
        await page
            .getByRole("button", { name: "Delivery", exact: true })
            .click();
        await expect(page.locator(".delivery-task")).toHaveCount(2);
        await expect(
            page
                .getByRole("heading", {
                    name: "Serah terima pengiriman",
                    exact: true,
                })
                .locator("..")
                .getByRole("alert"),
        ).toHaveCount(0);
        const task = page
            .locator(".delivery-task")
            .filter({ hasText: "DEMO-DO-001" });
        await task.locator("summary").first().click();
        await startDelivery(task);
        await task.getByLabel("Penerima", { exact: true }).fill("Budi Offline");
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", { name: "Simpan draft POD", exact: true })
            .click();
        await expect(
            task.getByText(/Draft POD tersimpan offline/),
        ).toBeVisible();
    });
for (const invalid of ["none", "owner", "day", "cache"] as const)
    test(`first Delivery rejects ${invalid} daily/cache without overwriting it`, async ({
        page,
    }) => {
        await driver(page);
        if (invalid !== "none") await ensureDaily(page);
        await page.evaluate(async (kind) => {
            if (kind === "none") return;
            const db = await new Promise<IDBDatabase>((resolve) => {
                const r = indexedDB.open("fmcg-field-demo-v1");
                r.onsuccess = () => resolve(r.result);
            });
            const tx = db.transaction("drafts", "readwrite"),
                drafts = tx.objectStore("drafts"),
                get = drafts.get("demo-mdu:DEMO-NOVRY:morning-session-v1");
            get.onsuccess = () => {
                const record = get.result,
                    manifest = record.value.deliveryManifest;
                if (kind === "cache")
                    drafts.put({
                        key: `demo-mdu:DEMO-NOVRY:delivery-manifest-v1:${record.value.businessDate}`,
                        owner: "demo-mdu:DEMO-NOVRY",
                        value: [{ ...manifest[0], version: "CORRUPT-CACHE" }],
                    });
                else {
                    manifest[0][kind === "owner" ? "owner" : "business_date"] =
                        kind === "owner" ? "other-owner" : "2000-01-01";
                    drafts.put(record);
                }
            };
            await new Promise<void>((resolve, reject) => {
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error);
            });
            db.close();
        }, invalid);
        const before = await readDrafts(page);
        await page
            .getByRole("button", { name: "Delivery", exact: true })
            .click();
        if (invalid === "none")
            await expect(
                page.getByText(
                    "Daily sync wajib sebelum membuka list Delivery.",
                ),
            ).toBeVisible();
        else
            await expect(page.getByRole("alert")).toContainText(
                "Manifest tidak cocok",
            );
        await expect(page.locator(".delivery-task")).toHaveCount(0);
        expect(await readDrafts(page)).toEqual(before);
    });
test("daily helper waits for deliberately held attendance persistence before sync", async ({
    page,
}) => {
    await driver(page);
    await page.evaluate(() => {
        const held = new WeakSet<IDBTransaction>();
        const put = IDBObjectStore.prototype.put;
        IDBObjectStore.prototype.put = function (value, key) {
            if (
                this.name === "drafts" &&
                value.value?.attendanceReference &&
                value.value.sessionId === null
            )
                held.add(this.transaction);
            return key === undefined
                ? put.call(this, value)
                : put.call(this, value, key);
        };
        const add = IDBTransaction.prototype.addEventListener;
        (IDBTransaction.prototype as any).addEventListener = function (
            type: string,
            listener: any,
            options: any,
        ) {
            return add.call(
                this,
                type,
                (event: Event) => {
                    const deliver = () =>
                        typeof listener === "function"
                            ? listener.call(this, event)
                            : listener?.handleEvent(event);
                    if (type === "complete" && held.has(this)) {
                        (window as any).__attendanceHeld = true;
                        (window as any).__releaseAttendance = deliver;
                    } else deliver();
                },
                options,
            );
        };
    });
    const pending = ensureDaily(page);
    await page.waitForFunction(() => (window as any).__attendanceHeld === true);
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Menyimpan…", exact: true }),
    ).toBeDisabled();
    await expect(page.getByText("Sesi aktif", { exact: true })).toHaveCount(0);
    await page.evaluate(() => (window as any).__releaseAttendance());
    await pending;
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
});
test("persona helper waits for deliberately held restore of the destination owner", async ({
    page,
    context,
}) => {
    await driver(page);
    await ensureDaily(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "sales");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.evaluate(() => {
        const targets = new WeakSet<IDBRequest>();
        const get = IDBObjectStore.prototype.get;
        IDBObjectStore.prototype.get = function (key) {
            const r = get.call(this, key);
            if (
                this.name === "drafts" &&
                key === "demo-mdu:DEMO-NOVRY:morning-session-v1"
            )
                targets.add(r);
            return r;
        };
        const add = IDBRequest.prototype.addEventListener;
        (IDBRequest.prototype as any).addEventListener = function (
            type: string,
            listener: any,
            options: any,
        ) {
            return add.call(
                this,
                type,
                (event: Event) => {
                    const deliver = () =>
                        typeof listener === "function"
                            ? listener.call(this, event)
                            : listener?.handleEvent(event);
                    if (type === "success" && targets.has(this)) {
                        (window as any).__restoreHeld = true;
                        (window as any).__releaseRestore = deliver;
                    } else deliver();
                },
                options,
            );
        };
    });
    const pending = switchPersona(page, "delivery");
    await page.waitForFunction(() => (window as any).__restoreHeld === true);
    const region = page.getByRole("region", {
        name: "Sesi kerja",
        exact: true,
    });
    await expect(region).toHaveAttribute("data-owner", "demo-mdu:DEMO-NOVRY");
    await expect(region).toHaveAttribute("aria-busy", "true");
    await page.evaluate(() => (window as any).__releaseRestore());
    await pending;
    await context.setOffline(true);
    await ensureDaily(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
});
for (const legacy of [false, true])
    test(`POD revision history uses each historical SKU unit, legacy=${legacy}`, async ({
        page,
    }) => {
        await driver(page);
        await ensureDaily(page);
        if (legacy)
            await page.evaluate(async () => {
                const db = await new Promise<IDBDatabase>((resolve) => {
                    const r = indexedDB.open("fmcg-field-demo-v1");
                    r.onsuccess = () => resolve(r.result);
                });
                const tx = db.transaction("drafts", "readwrite"),
                    drafts = tx.objectStore("drafts"),
                    get = drafts.get("demo-mdu:DEMO-NOVRY:morning-session-v1");
                get.onsuccess = () => {
                    const r = get.result;
                    for (const t of r.value.deliveryManifest) {
                        delete t.workflow_version;
                        t.lines.forEach((l: any, i: number) => {
                            l.unit = "karton";
                            l.quantity = i + 1;
                        });
                    }
                    drafts.put(r);
                };
                await new Promise<void>((resolve, reject) => {
                    tx.oncomplete = () => resolve();
                    tx.onerror = () => reject(tx.error);
                });
                db.close();
            });
        await page
            .getByRole("button", { name: "Lainnya", exact: true })
            .click();
        await page.getByLabel("Mode respons").selectOption("rejected");
        await page
            .getByRole("button", { name: "Delivery", exact: true })
            .click();
        const task = page
            .locator(".delivery-task")
            .filter({ hasText: "DEMO-DO-001" });
        await task.locator("summary").first().click();
        await startDelivery(task);
        await task.getByLabel("Penerima", { exact: true }).fill("Budi Toko");
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Ajukan POD untuk review",
                exact: true,
            })
            .click();
        await task
            .getByRole("button", { name: "Koreksi POD ditolak", exact: true })
            .click();
        await startDelivery(task);
        await task
            .getByLabel("Alasan koreksi", { exact: true })
            .fill("Perbaikan nama penerima");
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Ajukan POD untuk review",
                exact: true,
            })
            .click();
        const history = task.locator("details").filter({
            has: page.locator("summary", { hasText: "Riwayat POD (2)" }),
        });
        await history.locator("summary").click();
        for (const paragraph of await history.locator("p").all()) {
            await expect(paragraph).toContainText(
                `Biskuit Kelapa 300 g (contoh): ${legacy ? 1 : 1440} ${legacy ? "karton" : "pcs"}`,
            );
            await expect(paragraph).toContainText(
                `Wafer Cokelat (contoh): ${legacy ? 2 : 144} ${legacy ? "karton" : "pcs"}`,
            );
            await expect(paragraph).toContainText(
                `Kopi Bubuk (contoh): ${legacy ? 3 : 144} ${legacy ? "karton" : "pcs"}`,
            );
        }
        await expect(history.locator("p")).toHaveCount(2);
    });
