import { saveVisitPhoto } from "./visit-helpers";
import { expect, test } from "@playwright/test";
test("visit location guards, offline restore and checkout sync", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.47,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Simulasikan absensi diterima",
            exact: true,
        })
        .click();
    await page
        .getByRole("button", {
            name: "Sync pagi & buka sesi demo",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const locate = page.getByRole("button", {
        name: "Ambil lokasi outlet",
        exact: true,
    });
    const start = page.getByRole("button", {
        name: "Mulai kunjungan demo",
        exact: true,
    });
    await locate.click();
    await expect(
        page.getByText("Di luar geofence", { exact: true }),
    ).toBeVisible();
    await expect(start).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 30,
    });
    await locate.click();
    await expect(
        page.getByText("Akurasi belum pasti", { exact: true }),
    ).toBeVisible();
    await expect(start).toBeDisabled();
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await locate.click();
    await saveVisitPhoto(page, "check-in");
    await expect(start).toBeEnabled();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await start.click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    await saveVisitPhoto(page, "check-out");
    await page
        .getByLabel("Catatan kunjungan")
        .fill("Toko tutup untuk kunjungan simulasi");
    await page.getByLabel("Hasil kunjungan").selectOption("outlet_closed");
    await page
        .getByRole("button", { name: "Tutup kunjungan demo", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(page.locator(".activity")).toHaveCount(2);
    await context.setOffline(false);
    await expect(
        page
            .locator(".activity")
            .getByText("Diterima simulator", { exact: true }),
    ).toHaveCount(2, { timeout: 20000 });
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
test("denied GPS permits demo coordinates but photo is still mandatory", async ({
    page,
}) => {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({
                code: 1,
                message: "denied",
                PERMISSION_DENIED: 1,
                POSITION_UNAVAILABLE: 2,
                TIMEOUT: 3,
            });
    });
    await page.goto("./");
    await page
        .getByRole("button", {
            name: "Simulasikan absensi diterima",
            exact: true,
        })
        .click();
    await page
        .getByRole("button", {
            name: "Sync pagi & buka sesi demo",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        page.getByText(/Lokasi\/foto diterima tanpa validasi/),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan demo", exact: true }),
    ).toBeDisabled();
    const photo = page.getByRole("group", {
        name: "Foto check-in kunjungan",
        exact: true,
    });
    await photo.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(
        photo.getByAltText("Pratinjau foto bukti lokal"),
    ).toBeVisible();
    await photo
        .getByRole("button", { name: "Gunakan lokasi demo", exact: true })
        .click();
    await photo
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(
        photo.getByText("Paket foto tersimpan untuk check-in outlet ini.", {
            exact: true,
        }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan demo", exact: true }),
    ).toBeEnabled();
});

test("corrupt offline check-in remains held after reload, reconnect and manual retry", async ({
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
    await page
        .getByRole("button", {
            name: "Simulasikan absensi diterima",
            exact: true,
        })
        .click();
    await page
        .getByRole("button", {
            name: "Sync pagi & buka sesi demo",
            exact: true,
        })
        .click();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Ambil lokasi outlet", exact: true })
        .click();
    await expect(
        page.getByText("Di dalam geofence", { exact: true }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan demo", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
    const before = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
            r.onerror = () => reject(r.error);
        });
        const tx = db.transaction("outbox", "readwrite");
        const r = tx.objectStore("outbox").getAll();
        const result = await new Promise<unknown>((resolve, reject) => {
            r.onsuccess = () => {
                const row = r.result.find(
                    (q) => q.command.type === "sales.visit.check_in",
                );
                row.command.payload.fix.latitude = 0;
                tx.objectStore("outbox").put(row);
                tx.oncomplete = () => resolve(row.command);
            };
            tx.onerror = () => reject(tx.error);
        });
        db.close();
        return result;
    });
    await page.reload();
    await expect(page.getByText("Sesi terbuka", { exact: true })).toBeVisible();
    await context.setOffline(false);
    // Reload online too: setOffline may fire before Preact's post-paint
    // connectivity effect attaches during boot. Test the persisted sync guard.
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText(
            "Integritas antrean/sumber kunjungan tidak valid. Data tetap lokal; perlu review.",
            { exact: true },
        ),
    ).toBeVisible();
    await page.getByRole("button", { name: "Sinkronkan", exact: true }).click();
    const after = (await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<unknown[]>((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return rows;
    })) as {
        command: unknown;
        state: string;
        receipt?: unknown;
        attempts: number;
    }[];
    expect(after).toHaveLength(1);
    expect(after[0].command).toEqual(before);
    expect(after[0].state).toBe("queued");
    expect(after[0].receipt).toBeUndefined();
    expect(after[0].attempts).toBe(0);
});
