import {
    sendOrder,
    applyDiscount,
    koreksiEditLines,
    koreksiTactical,
    leaveVisit,
} from "./visit-helpers";
import { expect, test, type Page } from "./session-fixture";
import {
    ensureDaily,
    switchPersona,
    startDelivery,
    saveDeliveryPhoto,
    openDeliveryTask,
    backFromTask,
    closeDeliveryScreens,
} from "./delivery-helpers";
import {
    leaveClosedVisit,
    saveDisplayPhoto,
    saveVisitPhoto,
} from "./visit-helpers";
test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 20,
        longitude: 80,
        accuracy: 500,
    });
});
async function readSoState(page: Page) {
    return page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction(["outbox", "drafts", "receipts"]);
        const read = (name: string) =>
            new Promise<any[]>((resolve) => {
                const r = tx.objectStore(name).getAll();
                r.onsuccess = () => resolve(r.result);
            });
        const [queue, drafts, receipts] = await Promise.all([
            read("outbox"),
            read("drafts"),
            read("receipts"),
        ]);
        db.close();
        return {
            queue: queue.filter((r) =>
                ["sales.order.submit", "sales.order.revise"].includes(
                    r.command?.type,
                ),
            ),
            drafts: drafts.filter(
                (r) =>
                    r.key.includes("sales-revision-form:") ||
                    r.key.includes("sales-order-revision-v1:"),
            ),
            receipts: receipts.filter((r) => r.key.includes("sales.order.")),
        };
    });
}
async function delivery(page: Page) {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
}
async function openDo(page: Page, id = "DEMO-DO-001") {
    const task = await openDeliveryTask(page, id);
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Toko Demo");
    return task;
}
for (const flow of ["same-day", "expired-draft", "expired-pending"] as const)
    test(`rejected SO after visit closed, offline draft and root-day rule: ${flow}`, async ({
        page,
        context,
    }) => {
        await page.clock.install({ time: new Date("2026-10-28T15:50:00Z") });
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
        await expect(
            page.getByText("Kunjungan lokal aktif", { exact: true }),
        ).toBeVisible();
        await page
            .getByRole("button", { name: "Buat order di outlet", exact: true })
            .click();
        await page
            .getByLabel("Kuantitas Biskuit Kelapa 300 g Karton", {
                exact: true,
            })
            .fill("1");
        await applyDiscount(page, 5, "Promo pertama");
        await saveDisplayPhoto(page);
        await sendOrder(page);
        await saveVisitPhoto(page, "check-out");
        await page
            .getByRole("button", { name: "Selesai kunjungan", exact: true })
            .first()
            .click();
        await leaveClosedVisit(page);
        await page
            .getByRole("button", { name: "Lainnya", exact: true })
            .click();
        await page
            .getByLabel("Alasan keputusan diskon", { exact: true })
            .fill("Diskon terlalu besar");
        await page
            .getByRole("button", {
                name: "Tolak diskon",
                exact: true,
            })
            .click();
        await page.getByRole("button", { name: /^Riwayat pengajuan/ }).click();
        await page.getByText(/Riwayat SO ·/).click();
        await page
            .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
            .click();
        await page
            .getByLabel("Catatan untuk SPV", { exact: true })
            .fill("Ganti SKU dan diskon");
        await koreksiEditLines(page, [
            { product: "Biskuit Kelapa 300 g", tier: "Karton", qty: 0 },
            { product: "Wafer Cokelat 24 g", tier: "Pcs", qty: 3 },
        ]);
        await koreksiTactical(page, "Wafer Cokelat 24 g", 2, "Promo revisi");
        await page.evaluate(() => navigator.serviceWorker.ready);
        await page.waitForFunction(() => !!navigator.serviceWorker.controller);
        await context.setOffline(true);
        // Draft koreksi tersimpan otomatis di perangkat (offline).
        await page.waitForTimeout(500);
        await page.reload();
        await expect(
            page.getByRole("button", { name: "Lainnya", exact: true }),
        ).toBeVisible();
        await page
            .getByRole("button", { name: "Lainnya", exact: true })
            .click();
        await page.getByRole("button", { name: /^Riwayat pengajuan/ }).click();
        await expect(page.getByText(/Riwayat SO ·/).first()).toBeVisible();
        await page.getByText(/Riwayat SO ·/).click();
        await page
            .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
            .click();
        await expect(
            page.getByRole("region", { name: "Koreksi order" }),
        ).toContainText("Wafer Cokelat 24 g");
        await expect(
            page.getByRole("region", { name: "Koreksi order" }),
        ).toContainText("3 pcs");
        if (flow === "expired-draft") {
            const before = await readSoState(page);
            await page.clock.setSystemTime(new Date("2026-10-28T16:00:00Z"));
            await page.clock.runFor(1000);
            await expect(
                page.getByRole("button", {
                    name: "Kirim ulang",
                    exact: true,
                }),
            ).toBeDisabled();
            await page.reload();
            await expect(
                page.getByRole("button", { name: "Lainnya", exact: true }),
            ).toBeVisible();
            await page
                .getByRole("button", { name: "Lainnya", exact: true })
                .click();
            await page
                .getByRole("button", { name: /^Riwayat pengajuan/ })
                .click();
            await expect(page.getByText(/Riwayat SO ·/).first()).toBeVisible();
            await page.getByText(/Riwayat SO ·/).click();
            await page
                .getByRole("button", {
                    name: "Lihat draft koreksi lewat hari",
                    exact: true,
                })
                .click();
            await expect(
                page.getByRole("region", { name: "Koreksi order" }),
            ).toContainText("3 pcs");
            await expect(
                page.getByRole("button", {
                    name: "Ubah baris order",
                    exact: true,
                }),
            ).toBeDisabled();
            await expect(
                page
                    .getByRole("region", { name: "Koreksi order" })
                    .getByText(/Lewat batas hari root SO/)
                    .first(),
            ).toBeVisible();
            expect(await readSoState(page)).toEqual(before);
            await context.setOffline(false);
            await leaveVisit(page);
            await ensureDaily(page);
            await page
                .getByRole("button", { name: "Lainnya", exact: true })
                .click();
            await page
                .getByRole("button", { name: /^Riwayat pengajuan/ })
                .click();
            await page.getByText(/Riwayat SO ·/).click();
            await page
                .getByRole("button", {
                    name: "Lihat draft koreksi lewat hari",
                    exact: true,
                })
                .click();
            await expect(
                page.getByRole("button", {
                    name: "Kirim ulang",
                    exact: true,
                }),
            ).toBeDisabled();
            await expect(
                page
                    .getByText(
                        /follow-up\/push approval ke manager secara manual/,
                    )
                    .first(),
            ).toBeVisible();
            expect(await readSoState(page)).toEqual(before);
            return;
        }
        await page
            .getByRole("button", { name: "Kirim ulang", exact: true })
            .click();
        await expect(page.getByText(/Revisi baru masuk antrean/)).toBeVisible();
        await context.setOffline(false);
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
        if (flow === "expired-pending") {
            const before = await readSoState(page);
            await page.clock.setSystemTime(new Date("2026-10-28T16:00:00Z"));
            await page.clock.runFor(1000);
            await expect(
                page.getByRole("button", {
                    name: "Setujui diskon",
                    exact: true,
                }),
            ).toBeDisabled();
            await expect(
                page.getByRole("button", {
                    name: "Tolak diskon",
                    exact: true,
                }),
            ).toBeDisabled();
            await context.setOffline(true);
            await page.reload();
            await page
                .getByRole("button", { name: "Lainnya", exact: true })
                .click();
            await expect(
                page.getByRole("button", {
                    name: "Setujui diskon",
                    exact: true,
                }),
            ).toBeDisabled();
            await expect(
                page
                    .getByRole("status")
                    .filter({ hasText: /Lewat batas hari root SO/ })
                    .first(),
            ).toBeVisible();
            expect(await readSoState(page)).toEqual(before);
            await context.setOffline(false);
            await ensureDaily(page);
            await page
                .getByRole("button", { name: "Lainnya", exact: true })
                .click();
            await expect(
                page.getByRole("button", {
                    name: "Setujui diskon",
                    exact: true,
                }),
            ).toBeDisabled();
            await expect(
                page
                    .getByText(
                        /follow-up\/push approval ke manager secara manual/,
                    )
                    .first(),
            ).toBeVisible();
            expect(await readSoState(page)).toEqual(before);
            return;
        }
        await page
            .getByLabel("Alasan keputusan diskon", { exact: true })
            .fill("Revisi disetujui");
        await page
            .getByRole("button", {
                name: "Setujui diskon",
                exact: true,
            })
            .click();
        await page.getByRole("button", { name: /^Riwayat pengajuan/ }).click();
        await expect(page.getByText(/Riwayat SO ·.*2 pengajuan/)).toBeVisible();
        await page.screenshot({
            path: `test-results/so-revision-${test.info().project.name}.png`,
            fullPage: true,
        });
    });
for (const days of [2, 3])
    test(`Pending Requested +${days} days enforces the approval ladder`, async ({
        page,
    }) => {
        await delivery(page);
        const task = await openDo(page);
        await task.getByRole("button", { name: "Tolak", exact: true }).click();
        await task.getByLabel("Request pending kirim", { exact: true }).check();
        const date = await page.evaluate((n) => {
            const date = new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            });
            return new Date(Date.parse(date + "T00:00:00Z") + n * 86400000)
                .toISOString()
                .slice(0, 10);
        }, days);
        await task.getByLabel("Tanggal kirim ulang").fill(date);
        await task
            .getByLabel("Catatan serah terima", {
                exact: true,
            })
            .fill("Toko minta kirim ulang");
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Selesai serah terima",
                exact: true,
            })
            .click();
        await closeDeliveryScreens(page);
        await page
            .getByRole("button", { name: "Lainnya", exact: true })
            .click();
        const approval = page
            .getByRole("heading", {
                name: "Simulator approval pending/cancel",
                exact: true,
            })
            .locator("..");
        await approval
            .getByLabel("Alasan keputusan delivery", { exact: true })
            .fill("Review pengiriman ulang");
        await approval
            .getByRole("button", {
                name: "Setujui branch_manager",
                exact: true,
            })
            .click();
        await expect(approval.getByRole("alert")).toContainText("Urutan");
        await approval
            .getByRole("button", {
                name: "Setujui spv",
                exact: true,
            })
            .click();
        if (days >= 3) {
            await expect(
                approval.getByText(/menunggu Branch Manager/),
            ).toBeVisible();
            await approval
                .getByRole("button", {
                    name: "Setujui branch_manager",
                    exact: true,
                })
                .click();
        }
        await expect(approval.getByText(/spv: disetujui/)).toBeVisible();
        await expect(
            approval.getByRole("button", {
                name: "Setujui spv",
                exact: true,
            }),
        ).toHaveCount(0);
    });
test("Cancel Delivery has the required subreason and SPV rejection keeps original request", async ({
    page,
}) => {
    await delivery(page);
    const task = await openDo(page);
    await task.getByRole("button", { name: "Tolak", exact: true }).click();
    await task.getByLabel("Toko tidak dapat diakses", { exact: true }).check();
    await task
        .getByLabel("Catatan serah terima", { exact: true })
        .fill("Rute melebihi waktu kerja");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Selesai serah terima", exact: true })
        .click();
    await closeDeliveryScreens(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    const approval = page
        .getByRole("heading", {
            name: "Simulator approval pending/cancel",
            exact: true,
        })
        .locator("..");
    await approval
        .getByLabel("Alasan keputusan delivery", { exact: true })
        .fill("Rute perlu dievaluasi");
    await approval
        .getByRole("button", { name: "Tolak spv", exact: true })
        .click();
    await expect(approval.getByText(/spv: ditolak/)).toBeVisible();
    await expect(
        approval.getByText(/Cancel Toko tidak dapat diakses/),
    ).toBeVisible();
});
const closingScreen = (page: Page) =>
    page.getByRole("region", { name: /^Akhiri trip · / });
async function openClosing(page: Page) {
    if (await closingScreen(page).isVisible()) return;
    await page
        .getByRole("heading", { name: "Akhiri trip", exact: true })
        .locator("../..")
        .getByRole("button")
        .first()
        .click();
    await closingScreen(page).waitFor();
}
async function runClose(page: Page) {
    await openClosing(page);
    await closingScreen(page)
        .getByRole("button", { name: "Akhiri trip", exact: true })
        .click();
}
test("closing trip at office uses recorded location, accepts demo outside office, and does not settle cashier", async ({
    page,
}) => {
    await delivery(page);
    const closing = closingScreen(page);
    await runClose(page);
    await expect(closing.getByRole("alert")).toContainText(/hilang|lengkap/);
    await closing
        .getByRole("button", { name: "Kembali", exact: true })
        .first()
        .click();
    for (const id of ["DEMO-DO-001", "DEMO-DO-002"]) {
        const task = await openDo(page, id);
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Selesai serah terima",
                exact: true,
            })
            .click();
        await expect(task.getByText(/Session closed/).first()).toBeVisible();
        await backFromTask(page);
    }
    await closeDeliveryScreens(page);
    await runClose(page);
    await expect(closing.getByRole("alert")).toContainText("Trip closed lokal");
    await expect(closing.getByRole("alert")).toContainText(
        "Belum settlement kasir/Odoo",
    );
    await expect(
        closing.getByRole("button", { name: "Akhiri trip", exact: true }),
    ).toHaveCount(0);
});

test("new daily sync cannot close today's trip using yesterday's PODs with repeated DO IDs", async ({
    page,
}) => {
    await page.clock.install({ time: new Date("2026-10-28T01:00:00Z") });
    await delivery(page);
    for (const id of ["DEMO-DO-001", "DEMO-DO-002"]) {
        const task = await openDo(page, id);
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Selesai serah terima",
                exact: true,
            })
            .click();
        await expect(task.getByText(/Session closed/).first()).toBeVisible();
        await backFromTask(page);
    }
    await closeDeliveryScreens(page);
    const closing = closingScreen(page);
    await runClose(page);
    await expect(closing.getByRole("alert")).toContainText("Trip closed lokal");
    const readLocal = () =>
        page.evaluate(async () => {
            const db = await new Promise<IDBDatabase>((resolve) => {
                const request = indexedDB.open("fmcg-field-demo-v1");
                request.onsuccess = () => resolve(request.result);
            });
            const tx = db.transaction(["outbox", "drafts"]);
            const read = (name: string) =>
                new Promise<any[]>((resolve) => {
                    const request = tx.objectStore(name).getAll();
                    request.onsuccess = () => resolve(request.result);
                });
            const [rows, drafts] = await Promise.all([
                read("outbox"),
                read("drafts"),
            ]);
            db.close();
            return {
                commands: rows.map((r) => r.command),
                closings: drafts.filter(
                    (r) => r.value?.type === "delivery.trip.close",
                ),
            };
        });
    const before = await readLocal();
    await page.clock.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await expect(
        page.getByRole("button", { name: /^Buka TRIP/ }),
    ).toContainText("Belum mulai");
    for (const id of ["DEMO-DO-001", "DEMO-DO-002"]) {
        const task = await openDeliveryTask(page, id);
        await expect(
            task
                .getByRole("region", { name: `Delivery ${id}`, exact: true })
                .getByRole("status"),
        ).toContainText("POD berbeda sumber manifest");
        await backFromTask(page);
        await expect(task.getByText(/Session closed/)).toHaveCount(0);
    }
    await closeDeliveryScreens(page);
    await runClose(page);
    await expect(closing.getByRole("alert")).toContainText(
        "POD berbeda sumber manifest",
    );
    expect(await readLocal()).toEqual(before);
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await runClose(page);
    await expect(closing.getByRole("alert")).toContainText(
        "POD berbeda sumber manifest",
    );
    expect(await readLocal()).toEqual(before);
    // A forged/restored current-day closing pointer must pass the same source
    // guard before the UI can display a closed trip. Historical data stays put.
    await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const request = indexedDB.open("fmcg-field-demo-v1");
            request.onsuccess = () => resolve(request.result);
        });
        const tx = db.transaction(["outbox", "drafts"], "readwrite"),
            drafts = tx.objectStore("drafts");
        const get = drafts.getAll();
        get.onsuccess = () => {
            const all = get.result,
                owner = "demo-mdu:DEMO-NOVRY";
            const daily = all.find(
                (r) => r.key === `${owner}:morning-session-v1`,
            ).value;
            const old = all.find(
                (r) =>
                    r.owner === owner &&
                    r.value?.type === "delivery.trip.close",
            ).value;
            const command = {
                ...old,
                client_uuid: crypto.randomUUID(),
                occurred_at: new Date().toISOString(),
                payload: {
                    ...old.payload,
                    business_date: daily.businessDate,
                    daily_source: daily,
                },
            };
            const key = `trip-close-v1:${JSON.stringify([command.payload.trip_id, daily.businessDate])}`;
            drafts.put({ key: `${owner}:${key}`, owner, value: command });
            tx.objectStore("outbox").put({
                key: `${owner}:${command.client_uuid}`,
                owner,
                command,
                state: "queued",
                attempts: 0,
                nextAttempt: 0,
                label: "Invalid restored closing",
            });
        };
        await new Promise<void>((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        db.close();
    });
    const restored = await readLocal();
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await openClosing(page);
    await expect(closing.getByRole("alert")).toContainText(
        "Status closing tidak valid",
    );
    await expect(
        closing.getByRole("button", { name: "Akhiri trip", exact: true }),
    ).toBeVisible();
    expect(await readLocal()).toEqual(restored);
});
