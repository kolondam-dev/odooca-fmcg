import { describe, expect, it } from "vitest";
import type { Snapshot } from "../src/domain/contracts";
import { creditExceeded, creditRoom } from "../src/domain/outlet-card";
import {
    COLLECT_WINDOW_DAYS,
    daysUntilDue,
    dueLabel,
    mustCollectToday,
    outstandingFor,
    type OutletReceivable,
} from "../src/domain/receivables";

const TODAY = "2026-11-23";
const inv = (reference: string, due: string | null, balance: number) => ({
    reference,
    partner: "Toko",
    invoice_date: null,
    due_date: due,
    total: balance,
    balance,
    overdue: due !== null && due < TODAY,
});
const entry = (
    invoices: ReturnType<typeof inv>[],
    extra: Partial<OutletReceivable> = {},
): OutletReceivable => ({
    outstanding_total: invoices.reduce((s, i) => s + i.balance, 0),
    open_count: invoices.length,
    overdue_count: invoices.filter((i) => i.overdue).length,
    overdue_total: 0,
    oldest_due: null,
    truncated: false,
    invoices,
    ...extra,
});

describe("daysUntilDue / dueLabel", () => {
    it("selisih hari kalender, negatif = terlambat, tanggal tidak valid = null", () => {
        expect(daysUntilDue("2026-11-23", TODAY)).toBe(0);
        expect(daysUntilDue("2026-11-30", TODAY)).toBe(7);
        expect(daysUntilDue("2026-11-20", TODAY)).toBe(-3);
        expect(daysUntilDue("2026-12-01", "2026-11-30")).toBe(1);
        expect(daysUntilDue(null, TODAY)).toBeNull();
        expect(daysUntilDue("bukan-tanggal", TODAY)).toBeNull();
    });
    it("label ramah", () => {
        expect(dueLabel(-3)).toBe("Terlambat 3 hari");
        expect(dueLabel(0)).toBe("Jatuh tempo hari ini");
        expect(dueLabel(5)).toBe("Jatuh tempo 5 hari lagi");
        expect(dueLabel(null)).toBe("Tanpa jatuh tempo");
    });
});

describe("mustCollectToday (aturan pemilik: jatuh tempo < 7 hari dari hari bisnis)", () => {
    it("jendela 7 hari: +6 ikut, +7 tidak; terlambat dan hari ini ikut; tanpa jatuh tempo tidak", () => {
        expect(COLLECT_WINDOW_DAYS).toBe(7);
        const r = mustCollectToday(
            entry([
                inv("A", "2026-10-01", 100), // terlambat
                inv("B", "2026-11-23", 200), // hari ini
                inv("C", "2026-11-29", 300), // +6
                inv("D", "2026-11-30", 400), // +7 → tidak
                inv("E", null, 500), // tanpa jatuh tempo → tidak
            ]),
            TODAY,
        );
        expect(r.invoices.map((i) => i.reference)).toEqual(["A", "B", "C"]);
        expect(r.count).toBe(3);
        expect(r.total).toBe(600);
        expect(r.overdueCount).toBe(1);
    });
    it("outlet tanpa piutang atau blok tidak ada → kosong dan lengkap", () => {
        const r = mustCollectToday(undefined, TODAY);
        expect([r.count, r.total, r.overdueCount]).toEqual([0, 0, 0]);
        expect(r.complete).toBe(true);
    });
    it("daftar tidak terpotong selalu lengkap", () => {
        expect(
            mustCollectToday(entry([inv("A", "2026-11-22", 100)]), TODAY)
                .complete,
        ).toBe(true);
    });
    it("60 faktur terlambat, server hanya kirim 50: subtotal BUKAN total lengkap", () => {
        const loaded = Array.from({ length: 50 }, (_, i) =>
            inv(`F${i}`, "2026-11-22", 100),
        );
        const r = mustCollectToday(
            entry(loaded, {
                open_count: 60,
                outstanding_total: 6000,
                overdue_count: 60,
                overdue_total: 6000,
                truncated: true,
            }),
            TODAY,
        );
        expect([r.count, r.total]).toEqual([50, 5000]);
        expect(r.complete).toBe(false);
    });
    it("terpotong tetapi faktur termuat sudah melewati jendela (+7) → semua faktur jendela termuat, lengkap", () => {
        const r = mustCollectToday(
            entry(
                [
                    inv("A", "2026-11-01", 100),
                    inv("B", "2026-11-29", 200), // +6
                    inv("C", "2026-11-30", 300), // +7 di luar
                ],
                { truncated: true },
            ),
            TODAY,
        );
        expect([r.count, r.total]).toEqual([2, 300]);
        expect(r.complete).toBe(true);
    });
    it("terpotong dengan faktur terakhir +6 masih di jendela → tidak lengkap; tanpa jatuh tempo tidak membuktikan lengkap", () => {
        const e = entry(
            [
                inv("A", "2026-11-01", 100),
                inv("B", "2026-11-29", 200),
                inv("N", null, 50),
            ],
            { truncated: true },
        );
        const r = mustCollectToday(e, TODAY);
        expect([r.count, r.total]).toEqual([2, 300]);
        expect(r.complete).toBe(false);
    });
    it("terpotong tanpa faktur jendela sama sekali → count 0 tetapi tidak lengkap (bukan 'Tidak ada')", () => {
        const r = mustCollectToday(
            entry([inv("N", null, 50)], { truncated: true }),
            TODAY,
        );
        expect(r.count).toBe(0);
        expect(r.complete).toBe(false);
    });
});

describe("outstandingFor", () => {
    it("blok tidak ada = tidak diketahui → nilai lama; blok ada tanpa outlet = 0", () => {
        expect(outstandingFor("5", undefined, 123)).toBe(123);
        expect(outstandingFor("5", undefined)).toBeNull();
        const block: NonNullable<Snapshot["outlet_receivables"]> = {
            "5": entry([inv("A", TODAY, 900)]),
        };
        expect(outstandingFor("5", block, 1)).toBe(900);
        expect(outstandingFor("9", block, 1)).toBe(0);
    });
});

describe("limit kredit mengikuti credit_mode dan limit > 0 (sama dengan server)", () => {
    const c = (o: Record<string, unknown>) => ({
        credit_limit: 1000,
        ar_outstanding: 1500,
        ...o,
    });
    it("mode strict tidak memeriksa nominal", () => {
        expect(creditExceeded(c({ credit_mode: "strict" }))).toBeUndefined();
        expect(creditRoom(c({ credit_mode: "strict" }), 1500)).toBeNull();
    });
    it("mode limit/limit_due/approval/tidak diketahui memeriksa nominal", () => {
        for (const mode of ["limit", "limit_due", "approval", null, undefined])
            expect(creditExceeded(c({ credit_mode: mode }))?.limit).toBe(1000);
        expect(creditRoom(c({ credit_mode: "limit" }), 400)).toBe(600);
    });
    it("limit 0 atau kosong berarti tanpa pemeriksaan nominal (bukan selalu melebihi)", () => {
        expect(creditRoom(c({ credit_limit: 0 }), 0)).toBeNull();
        expect(creditRoom(c({ credit_limit: null }), 0)).toBeNull();
        expect(creditRoom(undefined, 0)).toBeNull();
    });
});
