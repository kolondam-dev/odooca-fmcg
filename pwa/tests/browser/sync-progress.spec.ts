import type { Page } from "@playwright/test";
import { checkIn, expect, test } from "./session-fixture";

/** Absen masuk dengan snapshot gagal (503), lalu muat ulang: Beranda memegang langkah Sinkron. */
async function attendThenReload(
    page: Page,
    mode: { fail: boolean; hold?: Promise<void> },
) {
    await page.context().grantPermissions(["geolocation"]);
    // Uji gagal-simpan: tolak penulisan draf sesi pagi saat flag menyala.
    await page.addInitScript(() => {
        const put = IDBObjectStore.prototype.put;
        IDBObjectStore.prototype.put = function (
            this: IDBObjectStore,
            value: unknown,
            key?: IDBValidKey,
        ) {
            const k = (value as { key?: string } | undefined)?.key;
            if (
                (window as unknown as { __failMorningSave?: boolean })
                    .__failMorningSave &&
                typeof k === "string" &&
                k.endsWith(":morning-session-v1")
            )
                throw new DOMException("quota", "QuotaExceededError");
            return put.call(this, value, key);
        };
    });
    await page.route("**/api/v1/sync/snapshot", async (route) => {
        if (mode.hold) await mode.hold;
        if (!mode.fail) return route.fallback();
        return route.fulfill({
            status: 503,
            json: { error: "snapshot unavailable" },
        });
    });
    const wanted = mode.fail;
    mode.fail = false;
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    await page
        .getByRole("button", { name: "Perbarui lokasi", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Lokasi dan foto absensi" }),
    ).toHaveAttribute("aria-busy", "false");
    await page
        .getByLabel("Alamat / nama lokasi")
        .fill("Jl. Sam Ratulangi, Sario, Manado, Sulawesi Utara");
    await page
        .getByRole("button", { name: "Ambil selfie", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await page
        .getByRole("button", { name: "Gunakan foto", exact: true })
        .click();
    await expect(
        page.getByAltText("Foto absensi dengan watermark"),
    ).toBeVisible();
    mode.fail = wanted;
    await page
        .getByRole("region", { name: "Absensi foto dan lokasi" })
        .getByRole("button", { name: "Absen masuk", exact: true })
        .click();
    await expect(page.getByRole("alert")).toContainText("snapshot unavailable");
    mode.fail = false;
    await page.reload();
    // Draf absen dipulihkan di dialog; tutup agar Beranda terlihat.
    await page
        .getByRole("button", { name: "Kembali", exact: true })
        .first()
        .click();
    await expect(
        page.getByRole("button", {
            name: "Sinkronkan data harian",
            exact: true,
        }),
    ).toBeVisible();
}

test("Sinkron gagal menampilkan baris per item, Lanjut offline terkunci, Ulangi sinkron memulihkan", async ({
    page,
}) => {
    const mode = { fail: true };
    await attendThenReload(page, mode);
    mode.fail = true;
    await page
        .getByRole("button", { name: "Sinkronkan data harian", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Sync belum selesai" }),
    ).toBeVisible();
    await expect(page.getByText("Gagal", { exact: true })).toBeVisible();
    await expect(page.locator('[data-sync-row="outlet"]')).toHaveAttribute(
        "data-state",
        "error",
    );
    await expect(page.locator('[data-sync-row="outlet"]')).toContainText(
        "Belum terunduh",
    );
    for (const id of ["ar", "riwayat", "diskon"])
        await expect(page.locator(`[data-sync-row="${id}"]`)).toContainText(
            "Segera tersedia",
        );
    await expect(
        page.getByRole("button", { name: "Lanjut offline", exact: true }),
    ).toBeDisabled();
    await expect(page.getByRole("alert")).toBeVisible();
    mode.fail = false;
    await page
        .getByRole("button", { name: "Ulangi sinkron", exact: true })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await expect(
        page.getByRole("heading", { name: "Sync belum selesai" }),
    ).toHaveCount(0);
});

test("Sinkron berjalan menampilkan progres dan Mulai kunjungan terkunci", async ({
    page,
}) => {
    const mode: { fail: boolean; hold?: Promise<void> } = { fail: true };
    await attendThenReload(page, mode);
    let release: () => void = () => undefined;
    mode.fail = false;
    mode.hold = new Promise<void>((r) => (release = r));
    await page
        .getByRole("button", { name: "Sinkronkan data harian", exact: true })
        .click();
    const card = page.getByRole("heading", { name: "Menyiapkan data kerja" });
    await expect(card).toBeVisible();
    await expect(
        page.locator(".ui-chip", { hasText: /^Online$/ }),
    ).toBeVisible();
    await expect(
        page.getByRole("progressbar", { name: "Kemajuan sinkron" }),
    ).toBeVisible();
    await expect(page.locator('[data-sync-row="produk"]')).toContainText(
        "Mengunduh…",
    );
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan", exact: true }),
    ).toBeDisabled();
    release();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
});

test("Beranda sales memakai angka Outlet selesai, Order, Order terkonfirmasi", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await expect(
        page.getByText("Outlet selesai", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Order", { exact: true })).toBeVisible();
    await expect(
        page.getByText("Order terkonfirmasi", { exact: true }),
    ).toBeVisible();
});

test("Gagal simpan setelah unduh menampilkan Terunduh belum tersimpan, sesi tetap terkunci, Ulangi sinkron membukanya", async ({
    page,
}) => {
    const mode = { fail: true };
    await attendThenReload(page, mode);
    mode.fail = false;
    await page.evaluate(() => {
        (
            window as unknown as { __failMorningSave: boolean }
        ).__failMorningSave = true;
    });
    await page
        .getByRole("button", { name: "Sinkronkan data harian", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Sync belum selesai" }),
    ).toBeVisible();
    for (const id of ["outlet", "produk"]) {
        await expect(page.locator(`[data-sync-row="${id}"]`)).toHaveAttribute(
            "data-state",
            "error",
        );
        await expect(page.locator(`[data-sync-row="${id}"]`)).toContainText(
            "Terunduh, belum tersimpan",
        );
    }
    await expect(page.getByText("Belum terunduh")).toHaveCount(0);
    await expect(page.getByText("Sesi aktif", { exact: true })).toHaveCount(0);
    await page.evaluate(() => {
        (
            window as unknown as { __failMorningSave: boolean }
        ).__failMorningSave = false;
    });
    await page
        .getByRole("button", { name: "Ulangi sinkron", exact: true })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
    await expect(
        page.getByRole("heading", { name: "Sync belum selesai" }),
    ).toHaveCount(0);
});

test("Respons 200 dengan payload tidak sesuai skema menampilkan Terunduh belum lolos validasi dan sesi tetap terkunci", async ({
    page,
}) => {
    const mode = { fail: true };
    await attendThenReload(page, mode);
    let invalid = true;
    await page.route("**/api/v1/sync/snapshot", (route) =>
        invalid
            ? route.fulfill({ status: 200, json: { bukan: "snapshot" } })
            : route.fallback(),
    );
    mode.fail = false;
    await page
        .getByRole("button", { name: "Sinkronkan data harian", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Sync belum selesai" }),
    ).toBeVisible();
    for (const id of ["outlet", "produk"]) {
        await expect(page.locator(`[data-sync-row="${id}"]`)).toHaveAttribute(
            "data-state",
            "error",
        );
        await expect(page.locator(`[data-sync-row="${id}"]`)).toContainText(
            "Terunduh, belum lolos validasi",
        );
    }
    await expect(page.getByText("Belum terunduh")).toHaveCount(0);
    await expect(page.getByText("Sesi aktif", { exact: true })).toHaveCount(0);
    invalid = false;
    await page
        .getByRole("button", { name: "Ulangi sinkron", exact: true })
        .click();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();
});
