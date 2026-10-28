import { expect, test, type Page } from "@playwright/test";
import {
    ensureDaily,
    switchPersona,
    startDelivery,
    saveDeliveryPhoto,
} from "./delivery-helpers";
import { saveVisitPhoto } from "./visit-helpers";
test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 20,
        longitude: 80,
        accuracy: 500,
    });
});
async function delivery(page: Page) {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
}
async function openDo(page: Page, id = "DEMO-DO-001") {
    const task = page.locator(".delivery-task").filter({ hasText: id });
    await task.locator("summary").first().click();
    await startDelivery(task);
    await task.getByLabel("Penerima", { exact: true }).fill("Toko Demo");
    return task;
}
test("rejected SO is corrected after visit closed, offline draft restores and parent remains immutable", async ({
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
        .getByRole("button", { name: "Mulai kunjungan demo", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order di outlet", exact: true })
        .click();
    await page
        .getByLabel("Kuantitas Biskuit Kelapa 300 g", { exact: true })
        .fill("1");
    await page.getByLabel("Diskon diminta (%)", { exact: true }).fill("5");
    await page
        .getByLabel("Alasan permintaan diskon", { exact: true })
        .fill("Promo pertama");
    await page
        .getByRole("button", { name: "Simpan ke antrean demo", exact: true })
        .click();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByRole("button", { name: "Tutup kunjungan demo", exact: true })
        .click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page
        .getByLabel("Alasan keputusan diskon", { exact: true })
        .fill("Diskon terlalu besar");
    await page
        .getByRole("button", { name: "Simulasikan tolak diskon", exact: true })
        .click();
    await page.getByText(/Riwayat SO ·/).click();
    await page
        .getByRole("button", { name: "Koreksi SO ditolak", exact: true })
        .click();
    await page
        .getByLabel("Alasan koreksi SO", { exact: true })
        .fill("Ganti SKU dan diskon");
    await page
        .getByLabel("Qty revisi Biskuit Kelapa 300 g", { exact: true })
        .fill("0");
    await page
        .getByLabel("Qty revisi Wafer Cokelat 24 g", { exact: true })
        .fill("3");
    await page
        .getByLabel("Satuan revisi Wafer Cokelat 24 g", { exact: true })
        .selectOption("pcs");
    await page.getByLabel("Diskon revisi (%)", { exact: true }).fill("2");
    await page
        .getByLabel("Alasan diskon revisi", { exact: true })
        .fill("Promo revisi");
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
        page.getByLabel("Qty revisi Wafer Cokelat 24 g", { exact: true }),
    ).toHaveValue("3");
    await page
        .getByRole("button", { name: "Ajukan revisi SO", exact: true })
        .click();
    await expect(page.getByText(/Revisi baru masuk antrean/)).toBeVisible();
    await context.setOffline(false);
    await expect(
        page.getByRole("heading", {
            name: "Simulator approval diskon",
            exact: true,
        }),
    ).toBeVisible();
    await page
        .getByLabel("Alasan keputusan diskon", { exact: true })
        .fill("Revisi disetujui");
    await page
        .getByRole("button", {
            name: "Simulasikan setujui diskon",
            exact: true,
        })
        .click();
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
        await task
            .getByLabel("Hasil serah terima", { exact: true })
            .selectOption("pending_requested");
        const date = await page.evaluate((n) => {
            const date = new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            });
            return new Date(Date.parse(date + "T00:00:00Z") + n * 86400000)
                .toISOString()
                .slice(0, 10);
        }, days);
        await task
            .getByLabel("Tanggal kirim ulang", { exact: true })
            .fill(date);
        await task
            .getByLabel("Alasan status (direkam ke semua item)", {
                exact: true,
            })
            .fill("Toko minta kirim ulang");
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Ajukan POD untuk review",
                exact: true,
            })
            .click();
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
                name: "Simulasikan setujui branch_manager",
                exact: true,
            })
            .click();
        await expect(approval.getByRole("alert")).toContainText("Urutan");
        await approval
            .getByRole("button", {
                name: "Simulasikan setujui spv",
                exact: true,
            })
            .click();
        if (days >= 3) {
            await expect(
                approval.getByText(/menunggu Branch Manager/),
            ).toBeVisible();
            await approval
                .getByRole("button", {
                    name: "Simulasikan setujui branch_manager",
                    exact: true,
                })
                .click();
        }
        await expect(approval.getByText(/spv: disetujui/)).toBeVisible();
        await expect(
            approval.getByRole("button", {
                name: "Simulasikan setujui spv",
                exact: true,
            }),
        ).toHaveCount(0);
    });
test("Cancel Delivery has the required subreason and SPV rejection keeps original request", async ({
    page,
}) => {
    await delivery(page);
    const task = await openDo(page);
    await task
        .getByLabel("Hasil serah terima", { exact: true })
        .selectOption("cancel_delivery");
    await task
        .getByLabel("Subreason cancel delivery", { exact: true })
        .selectOption("Waktu pengiriman tidak cukup");
    await task
        .getByLabel("Alasan status (direkam ke semua item)", { exact: true })
        .fill("Rute melebihi waktu kerja");
    await saveDeliveryPhoto(task);
    await task
        .getByRole("button", { name: "Ajukan POD untuk review", exact: true })
        .click();
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
        .getByRole("button", { name: "Simulasikan tolak spv", exact: true })
        .click();
    await expect(approval.getByText(/spv: ditolak/)).toBeVisible();
    await expect(
        approval.getByText(/Cancel Waktu pengiriman tidak cukup/),
    ).toBeVisible();
});
test("closing trip at office uses recorded location, accepts demo outside office, and does not settle cashier", async ({
    page,
}) => {
    await delivery(page);
    const closing = page
        .getByRole("heading", {
            name: "Closing trip · tiba di kantor",
            exact: true,
        })
        .locator("..");
    await closing
        .getByRole("button", { name: "Tutup trip demo", exact: true })
        .click();
    await expect(closing.getByRole("status")).toContainText(/hilang|lengkap/);
    for (const id of ["DEMO-DO-001", "DEMO-DO-002"]) {
        const task = await openDo(page, id);
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Ajukan POD untuk review",
                exact: true,
            })
            .click();
        await expect(task.getByText(/Session closed/).first()).toBeVisible();
    }
    await closing
        .getByRole("button", { name: "Tutup trip demo", exact: true })
        .click();
    await expect(closing.getByRole("status")).toContainText(
        "Trip closed lokal",
    );
    await expect(closing.getByRole("status")).toContainText(
        "Belum settlement kasir/Odoo",
    );
    await expect(
        closing.getByRole("button", { name: "Tutup trip demo", exact: true }),
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
                name: "Ajukan POD untuk review",
                exact: true,
            })
            .click();
        await expect(task.getByText(/Session closed/).first()).toBeVisible();
    }
    const closing = page
        .getByRole("heading", {
            name: "Closing trip · tiba di kantor",
            exact: true,
        })
        .locator("..");
    await closing
        .getByRole("button", { name: "Tutup trip demo", exact: true })
        .click();
    await expect(closing.getByRole("status")).toContainText(
        "Trip closed lokal",
    );
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
    await expect(page.locator(".delivery-task")).toHaveCount(2);
    for (const task of await page.locator(".delivery-task").all()) {
        await expect(task.locator("summary")).toContainText("Belum dimulai");
        await task.locator("summary").click();
        await expect(task.getByRole("status")).toContainText(
            "POD berbeda sumber manifest",
        );
        await expect(task.getByText(/Session closed/)).toHaveCount(0);
    }
    await closing
        .getByRole("button", { name: "Tutup trip demo", exact: true })
        .click();
    await expect(closing.getByRole("status")).toContainText(
        "POD berbeda sumber manifest",
    );
    expect(await readLocal()).toEqual(before);
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    await closing
        .getByRole("button", { name: "Tutup trip demo", exact: true })
        .click();
    await expect(closing.getByRole("status")).toContainText(
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
    await expect(closing.getByRole("status")).toContainText(
        "Status closing tidak valid",
    );
    await expect(
        closing.getByRole("button", { name: "Tutup trip demo", exact: true }),
    ).toBeVisible();
    expect(await readLocal()).toEqual(restored);
});
