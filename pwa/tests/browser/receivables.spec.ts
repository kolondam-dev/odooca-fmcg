import {
    checkIn,
    expect,
    freshSnapshotMeta,
    test,
    type Page,
} from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { saveVisitPhoto } from "./visit-helpers";

const PELANGI = { latitude: 1.456, longitude: 124.84 };
const SINAR_PAGI = { latitude: 1.465, longitude: 124.833 };

async function startVisit(
    page: Page,
    context: import("@playwright/test").BrowserContext,
    outlet: RegExp,
    at: { latitude: number; longitude: number },
) {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({ ...at, accuracy: 3 });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: outlet }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
}

test("kartu Tagihan: piutang, faktur terbuka, dan wajib ditagih hari ini (jatuh tempo < 7 hari)", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
    const card = page
        .locator(".ui-card")
        .filter({ has: page.getByRole("heading", { name: "Tagihan" }) });
    await expect(card).toContainText("Wajib ditagih hari ini");
    await expect(card).toContainText(/1\.750\.000/); // piutang berjalan
    await expect(card).toContainText(/1\.550\.000\s*·\s*3 faktur/); // wajib ditagih
    const list = card.getByRole("list", { name: "Faktur terbuka" });
    await expect(list.getByRole("listitem")).toHaveCount(4);
    await expect(list).toContainText("Terlambat 34 hari");
    await expect(list).toContainText("Jatuh tempo 5 hari lagi");
    await expect(list).toContainText("Jatuh tempo 20 hari lagi");
    await expect(card).toContainText(
        "Pencatatan penagihan di aplikasi belum aktif",
    );
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});

test("kartu Tagihan: outlet tanpa piutang tampil Tidak ada tagihan", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Toko Sinar Pagi/, SINAR_PAGI);
    const card = page
        .locator(".ui-card")
        .filter({ has: page.getByRole("heading", { name: "Tagihan" }) });
    await expect(card).toContainText("Tidak ada tagihan");
    await expect(card).toContainText("Tidak ada faktur terbuka");
    await expect(
        card.getByRole("list", { name: "Faktur terbuka" }),
    ).toHaveCount(0);
});

for (const withAggregate of [false, true]) {
    test(`kartu Tagihan: daftar server terpotong (>50 faktur), ${withAggregate ? "agregat server collect_today → angka lengkap" : "server lama tanpa agregat → berlabel Minimal"}`, async ({
        page,
        context,
    }) => {
        const snapshot = await new MockProvider("sales", true).snapshot();
        const day = (n: number) => {
            const [y, m, d] = freshSnapshotMeta()
                .businessDate.split("-")
                .map(Number);
            return new Date(Date.UTC(y, m - 1, d + n))
                .toISOString()
                .slice(0, 10);
        };
        const invoices = Array.from({ length: 50 }, (_, i) => ({
            reference: `INV/BIG/${i}`,
            partner: "Minimarket Pelangi",
            invoice_date: day(-60),
            due_date: day(-1),
            total: 100_000,
            balance: 100_000,
            overdue: true,
        }));
        snapshot.outlet_receivables = {
            ...snapshot.outlet_receivables,
            "demo-outlet-3": {
                outstanding_total: 6_000_000,
                open_count: 60,
                overdue_count: 60,
                overdue_total: 6_000_000,
                oldest_due: day(-1),
                truncated: true,
                ...(withAggregate
                    ? {
                          collect_today: {
                              window_days: 7,
                              count: 60,
                              total: 6_000_000,
                              overdue_count: 60,
                          },
                      }
                    : {}),
                invoices,
            },
        };
        const meta = freshSnapshotMeta();
        await page.route("**/api/v1/sync/snapshot", (route) =>
            route.fulfill({
                json: {
                    ...snapshot,
                    updatedAt: meta.updatedAt,
                    scope: {
                        ...snapshot.scope,
                        business_date: meta.businessDate,
                    },
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
        await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
        const card = page
            .locator(".ui-card")
            .filter({ has: page.getByRole("heading", { name: "Tagihan" }) });
        if (withAggregate) {
            // Agregat server dari 60 faktur: angka lengkap, tanpa label Minimal/catatan terpotong.
            await expect(card).toContainText(
                /Rp\s?6\.000\.000\s*·\s*60 faktur/,
            );
            await expect(card).not.toContainText(/Minimal/);
            await expect(card).not.toContainText(
                /Daftar faktur dari server dipotong/,
            );
        } else {
            // Server lama: subtotal 50 x 100.000 hanya minimum; tidak boleh tampil sebagai total lengkap.
            await expect(card).toContainText(
                /Minimal Rp\s?5\.000\.000\s*·\s*50\+ faktur \(daftar terpotong\)/,
            );
            await expect(card).not.toContainText(
                /Rp\s?5\.000\.000\s*·\s*50 faktur/,
            );
            await expect(card).toContainText(
                /Daftar faktur dari server dipotong/,
            );
        }
        // Piutang berjalan dan jatuh tempo tetap agregat server (60 faktur / 6.000.000).
        await expect(card).toContainText(/6\.000\.000/);
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
    });
}
