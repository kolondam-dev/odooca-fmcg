import { test, expect, checkIn, freshSnapshotMeta } from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { saveVisitPhoto } from "./visit-helpers";

type Snapshot = Awaited<ReturnType<MockProvider["snapshot"]>>;

/** Sajikan snapshot demo yang sudah diubah (tanggal kerja tetap hari ini WITA). */
async function serveSnapshot(
    page: import("@playwright/test").Page,
    change: (snapshot: Snapshot) => void,
) {
    const snapshot = await new MockProvider("sales", true).snapshot();
    change(snapshot);
    const meta = freshSnapshotMeta();
    await page.route("**/api/v1/sync/snapshot", (route) =>
        route.fulfill({
            json: {
                ...snapshot,
                updatedAt: meta.updatedAt,
                scope: { ...snapshot.scope, business_date: meta.businessDate },
                office: {
                    id: "1",
                    name: "Kantor Pusat",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                    coordinate_status: "test",
                },
            },
        }),
    );
}

const commercial = (credit_limit: number, ar_outstanding: number) => ({
    max_order: null,
    previous_visit_total: null,
    top_sku: null,
    payment_terms: "TOP 7 hari",
    credit_limit,
    ar_outstanding,
    contact: null,
});

async function openSales(page: import("@playwright/test").Page) {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
}

test("Outlet: kartu menampilkan jam dan jarak dari snapshot; nilai kosong tidak ditampilkan", async ({
    page,
}) => {
    await serveSnapshot(page, (s) => {
        s.outlets[1] = { ...s.outlets[1], time: "—", distance: " " };
    });
    await openSales(page);
    const cards = page.locator(".ui-ocard");
    await expect(cards.first()).toContainText("Toko Sinar Pagi");
    await expect(cards.first().locator(".ui-ocard__meta")).toContainText(
        "08.30",
    );
    await expect(cards.first().locator(".ui-ocard__meta")).toContainText(
        "1,2 km",
    );
    // Outlet dengan jam/jarak kosong: tidak ada baris meta dan tidak ada angka karangan.
    await expect(cards.nth(1).locator(".ui-ocard__meta")).toHaveCount(0);
    // Tidak ada chip tagihan karangan: snapshot tidak membawa jumlah faktur.
    await expect(
        page.locator(".ui-ocard").getByText(/^Tagihan \d/),
    ).toHaveCount(0);
});

test("Outlet kosong: keadaan kosong DS dan Tambah Extra call membuka Extra call", async ({
    page,
}) => {
    // K28: paket dengan nol outlet ditolak `validMorningSnapshot` (morning.test.ts
    // "empty outlets"), jadi sesi kerja tidak terbuka dan layar ini belum terjangkau.
    // Tes ini lulus bila pengecekan `outlets.length > 0` dilonggarkan (diverifikasi
    // manual pada 3B-14); aktifkan setelah aturan PJP kosong diputuskan.
    test.fixme(true, "K28: PJP kosong belum dapat membuka sesi kerja");
    await serveSnapshot(page, (s) => {
        s.outlets = [];
    });
    await openSales(page);
    await expect(
        page.getByRole("heading", { name: "Belum ada outlet hari ini" }),
    ).toBeVisible();
    await expect(
        page.getByText(
            "PJP hari ini kosong atau belum disinkron. Tambahkan kunjungan di luar rencana lewat Extra call.",
        ),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Semua 0" })).toBeVisible();
    await expect(page.locator(".ui-ocard")).toHaveCount(0);
    await expect(
        page.getByText("Tidak ada outlet pada filter ini."),
    ).toHaveCount(0);
    await page
        .getByRole("button", { name: "Tambah Extra call", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Extra call" }),
    ).toBeVisible();
});

test("Outlet berisi: tidak ada keadaan kosong", async ({ page }) => {
    await openSales(page);
    await expect(page.locator(".ui-ocard").first()).toBeVisible();
    await expect(page.locator(".ui-empty")).toHaveCount(0);
});

for (const [name, limit, owed, expectNotice] of [
    ["melebihi limit kredit", 25_000_000, 41_484_793, true],
    ["di bawah limit kredit", 25_000_000, 1_000_000, false],
    ["dengan limit nol (tanpa pemeriksaan nominal)", 0, 5_000_000, false],
] as const) {
    test(`Hub kunjungan: piutang ${name} ${expectNotice ? "menampilkan" : "tidak menampilkan"} peringatan limit`, async ({
        page,
    }) => {
        await serveSnapshot(page, (s) => {
            s.outlets[0] = {
                ...s.outlets[0],
                commercial: commercial(limit, owed),
            };
            // Server lama tanpa blok piutang (BE-7): memakai commercial.ar_outstanding.
            delete s.outlet_receivables;
        });
        await openSales(page);
        await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
        await saveVisitPhoto(page, "check-in");
        await page
            .getByRole("button", { name: "Mulai kunjungan", exact: true })
            .click();
        const hub = page.getByRole("region", { name: "Kunjungan outlet" });
        await expect(
            hub.getByRole("heading", { name: "Tagihan" }),
        ).toBeVisible();
        await expect(hub.getByText("Piutang berjalan")).toBeVisible();
        const notice = hub.getByText(
            /Melebihi limit kredit Rp\s25\.000\.000 \(TOP 7 hari\)\./,
        );
        if (expectNotice) await expect(notice).toBeVisible();
        else await expect(notice).toHaveCount(0);
        // Faktur tidak dikarang: tanpa blok piutang server, daftar faktur tidak ada dan order tidak menunggu tagihan.
        await expect(
            hub.getByText(/Data piutang belum dikirim server/),
        ).toBeVisible();
        await expect(
            hub.getByRole("button", { name: "Buat order di outlet" }),
        ).toBeEnabled();
    });
}
