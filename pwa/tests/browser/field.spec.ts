import { sendOrder } from "./visit-helpers";
import { checkIn } from "./session-fixture";
import { switchPersona } from "./delivery-helpers";
import { saveDisplayPhoto, saveVisitPhoto } from "./visit-helpers";
import { expect, test, type Page } from "./session-fixture";
async function openMorning(page: Page) {
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
}
async function visitOrder(page: Page, first = true) {
    if (first) {
        await page
            .getByRole("button", {
                name: "Perbarui lokasi outlet",
                exact: true,
            })
            .click();
        await expect(
            page.getByText("Di dalam geofence", { exact: true }),
        ).toBeVisible();
        await saveVisitPhoto(page, "check-in");
        await page
            .getByRole("button", { name: "Mulai kunjungan", exact: true })
            .click();
        await expect(
            page.getByText("Kunjungan lokal aktif", { exact: true }),
        ).toBeVisible();
    } else {
        await page
            .getByRole("button", { name: "Check-in toko", exact: true })
            .click();
        const refreshBtn = page.getByRole("button", {
            name: "Perbarui lokasi outlet",
            exact: true,
        });
        await expect(refreshBtn).toBeVisible();
        await refreshBtn.click();
    }
    await page
        .getByRole("button", { name: "Open session", exact: true })
        .click();
}
async function demoGps(page: Page) {
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (success) =>
            success({
                coords: {
                    latitude: 1.465,
                    longitude: 124.833,
                    accuracy: 3,
                    altitude: null,
                    altitudeAccuracy: null,
                    heading: null,
                    speed: null,
                    toJSON() {
                        return {};
                    },
                },
                timestamp: Date.now(),
                toJSON() {
                    return {};
                },
            });
    });
}
test("home is usable on phone/tablet with no overflow and local assets", async ({
    page,
}) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("./");
    await expect(
        page.getByRole("heading", { name: /Selamat bekerja/ }),
    ).toBeVisible();
    await expect(
        page.getByRole("region", { name: "Sesi kerja", exact: true }),
    ).toBeVisible();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
    await page.evaluate(() => document.fonts.ready);
    expect(errors).toEqual([]);
    expect(
        await page
            .locator(".icon")
            .first()
            .evaluate((el) => el.getBoundingClientRect().width),
    ).toBeLessThanOrEqual(32);
    await page.screenshot({
        path: `test-results/home-${test.info().project.name}.png`,
        fullPage: true,
    });
});
test("stacked roles and persona switch never show another persona queue", async ({
    page,
}) => {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "delivery");
    await expect(page.getByRole("heading", { name: /Novry/ })).toBeVisible();
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Sales", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await switchPersona(page, "canvass");
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Sales", exact: true }),
    ).toBeVisible();
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Delivery", exact: true }),
    ).toHaveCount(0);
});
test("offline order survives reload, syncs on reconnect, stays separate across accounts", async ({
    page,
    context,
}) => {
    await demoGps(page);
    await page.goto("./");
    await openMorning(page);
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await visitOrder(page);
    await page.getByLabel("Kuantitas Biskuit Kelapa 300 g").fill("2");
    await page.getByRole("button", { name: "Tutup form", exact: true }).click();
    await page.reload();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    await page
        .getByRole("navigation", { name: "Navigasi utama" })
        .getByRole("button", { name: "Beranda", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await visitOrder(page, false);
    await expect(page.getByLabel("Kuantitas Biskuit Kelapa 300 g")).toHaveValue(
        "2",
    );
    await saveDisplayPhoto(page);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await sendOrder(page);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Menunggu koneksi", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    await page
        .getByRole("navigation", { name: "Navigasi utama" })
        .getByRole("button", { name: "Beranda", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: /Selamat bekerja/ }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Menunggu koneksi", { exact: true }),
    ).toBeVisible();
    await context.setOffline(false);
    await expect(
        page.getByText("Diterima simulator", { exact: true }).last(),
    ).toBeVisible({ timeout: 20000 });
    await switchPersona(page, "delivery");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Belum ada aktivitas. Mulai dari order atau pengajuan."),
    ).toBeVisible();
    await switchPersona(page, "sales");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(page.locator(".activity")).toHaveCount(2);
});
test("expense request is an approval request, not disbursement", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page
        .getByRole("button", { name: "Uang lapangan", exact: false })
        .click();
    await page
        .getByRole("combobox", { name: "Kategori", exact: true })
        .selectOption("fuel_emergency");
    await expect(
        page.getByText(
            "BBM insidentil: Supervisor + Branch Manager, berapa pun nominalnya.",
        ),
    ).toBeVisible();
    await page
        .getByLabel("Referensi trip / perjalanan")
        .selectOption("TRIP-01");
    await page.getByLabel("Tanggal perjalanan").fill("2026-10-28");
    await page.getByLabel("Nominal pengajuan (Rp)").fill("100000");
    await page.getByLabel("KM / odometer awal").fill("15000");
    await page
        .getByLabel("Tujuan / alasan")
        .fill("Permohonan demo perjalanan luar kota");
    await page.getByRole("button", { name: "Simpan ke antrean" }).click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toBeVisible();
});
test("missing evidence is not accepted as attendance", async ({
    page,
    context,
}) => {
    await context.clearPermissions();
    await page.goto("./");
    await page.getByRole("button", { name: /^Absensi/ }).click();
    await expect(
        page.getByRole("button", { name: "Check in", exact: true }),
    ).toBeDisabled();
});
test("live build is fail-closed with no simulation selector or data", async ({
    page,
}) => {
    await page.goto("http://127.0.0.1:4174/field/");
    await expect(
        page.getByText("Integrasi layanan perusahaan belum diaktifkan."),
    ).toBeVisible();
    await expect(page.getByLabel("Peran")).toHaveCount(0);
    await expect(page.getByText("Toko Sinar Pagi")).toHaveCount(0);
});

test("expense guards keep invalid H-1 and missing DO out of outbox", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page
        .getByRole("button", { name: "Uang lapangan", exact: false })
        .click();
    await page
        .getByLabel("Referensi trip / perjalanan")
        .selectOption("TRIP-01");
    await page.getByLabel("Tanggal perjalanan").fill("2000-01-01");
    await page.getByLabel("Nominal pengajuan (Rp)").fill("100000");
    await page.getByLabel("KM / odometer awal").fill("15000");
    await page.getByLabel("Tujuan / alasan").fill("Perjalanan demo");
    await page.getByRole("button", { name: "Simpan ke antrean" }).click();
    await expect(
        page.getByText("BBM terencana wajib diajukan H-1.", { exact: false }),
    ).toBeVisible();
    await page.getByLabel("Kategori", { exact: true }).selectOption("meal");
    await page.getByLabel("Lingkup biaya").selectOption("delivery");
    await page.getByRole("button", { name: "Simpan ke antrean" }).click();
    expect(
        await page
            .getByLabel("Referensi DO (untuk biaya per pengiriman)")
            .evaluate((el) => (el as HTMLSelectElement).validity.valueMissing),
    ).toBe(true);
    await page
        .getByLabel("Referensi DO (untuk biaya per pengiriman)")
        .selectOption("DEMO-DO-001");
    await page.getByRole("button", { name: "Simpan ke antrean" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(page.locator(".activity")).toHaveCount(1);
});

test("morning gate requires attendance, preserves account separation and expires next WITA day", async ({
    page,
}) => {
    await page.clock.install({ time: new Date("2026-10-27T00:00:00Z") });
    await page.goto("./");
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeDisabled();
    await expect(
        page.getByRole("button", { name: "Buka sesi kerja", exact: true }),
    ).toBeDisabled();
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page.reload();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    await page
        .getByRole("navigation", { name: "Navigasi utama" })
        .getByRole("button", { name: "Beranda", exact: true })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await switchPersona(page, "canvass");
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeDisabled();
    await switchPersona(page, "sales");
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await page.clock.setSystemTime(new Date("2026-10-27T16:00:01Z"));
    await page.reload();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    await page
        .getByRole("navigation", { name: "Navigasi utama" })
        .getByRole("button", { name: "Beranda", exact: true })
        .click();
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeDisabled();
    await expect(page.getByText("Sesi aktif", { exact: true })).toHaveCount(0);
});

test("branding uses the same name, local logo and install icons in demo/live", async ({
    page,
}) => {
    for (const url of ["./", "http://127.0.0.1:4174/field/"]) {
        await page.goto(url);
        await expect(page).toHaveTitle("Odoo FMCG Mobile");
        const logo = page.getByRole("img", {
            name: "Odoo FMCG Mobile",
            exact: true,
        });
        await expect(logo).toBeVisible();
        await expect
            .poll(() =>
                logo.evaluate(
                    (el: HTMLImageElement) =>
                        el.complete && el.naturalWidth > 0,
                ),
            )
            .toBe(true);
        const result = await page.evaluate(async () => {
            const manifest = await (
                await fetch("/field/manifest.webmanifest")
            ).json();
            const sizes = await Promise.all(
                [
                    "icon-192.png",
                    "icon-512.png",
                    "apple-touch-icon.png",
                    "favicon-32.png",
                ].map(
                    (src) =>
                        new Promise((resolve) => {
                            const img = new Image();
                            img.onload = () =>
                                resolve([img.naturalWidth, img.naturalHeight]);
                            img.onerror = () => resolve(null);
                            img.src = "/field/" + src;
                        }),
                ),
            );
            return { name: manifest.name, sizes };
        });
        expect(result).toEqual({
            name: "Odoo FMCG Mobile",
            sizes: [
                [192, 192],
                [512, 512],
                [180, 180],
                [32, 32],
            ],
        });
    }
});

test("corrupt restored bundle locks order and extra call without deleting pending orders/drafts", async ({
    page,
    context,
}) => {
    await page.clock.install({ time: new Date("2026-10-27T00:00:00Z") });
    await demoGps(page);
    await page.goto("./");
    await openMorning(page);
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await visitOrder(page);
    await page.getByLabel("Kuantitas Biskuit Kelapa 300 g").fill("2");
    await saveDisplayPhoto(page);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await sendOrder(page);
    await visitOrder(page, false);
    await page.getByLabel("Kuantitas Biskuit Kelapa 300 g").fill("3");
    await page.getByRole("button", { name: "Tutup form", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const before = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
            r.onerror = () => reject(r.error);
        });
        const tx = db.transaction("drafts", "readwrite");
        await new Promise<void>((resolve, reject) => {
            const r = tx
                .objectStore("drafts")
                .get("demo-mdu:DEMO-ANDRE:morning-session-v1");
            r.onsuccess = () => {
                const row = r.result;
                row.value.snapshot.products = [];
                row.value.snapshot.updatedAt = "2020-01-01T00:00:00Z";
                tx.objectStore("drafts").put(row);
            };
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        const read = db.transaction(["drafts", "outbox"], "readonly");
        const value = await Promise.all(
            ["drafts", "outbox"].map(
                (name) =>
                    new Promise((resolve) => {
                        const r = read.objectStore(name).getAll();
                        r.onsuccess = () => resolve(r.result);
                    }),
            ),
        );
        db.close();
        return value;
    });
    await page.reload();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    await page
        .getByRole("navigation", { name: "Navigasi utama" })
        .getByRole("button", { name: "Beranda", exact: true })
        .click();
    await expect(
        page.getByRole("button", {
            name: "Buka sesi kerja",
            exact: true,
        }),
    ).toBeVisible();
    await expect(page.getByText("Sesi aktif", { exact: true })).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Buat order", exact: false }),
    ).toBeDisabled();
    await expect(
        page.getByRole("button", { name: /Toko Sinar Pagi/ }),
    ).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page
        .getByRole("navigation")
        .getByRole("button", { name: "Sales", exact: true })
        .click();
    await expect(
        page.getByText("Buka sesi kerja sebelum membuka daftar outlet."),
    ).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Ajukan extra call" }),
    ).toHaveCount(0);
    const after = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction(["drafts", "outbox"], "readonly");
        const value = await Promise.all(
            ["drafts", "outbox"].map(
                (name) =>
                    new Promise((resolve) => {
                        const r = tx.objectStore(name).getAll();
                        r.onsuccess = () => resolve(r.result);
                    }),
            ),
        );
        db.close();
        return value;
    });
    expect(after).toEqual(before);
});
