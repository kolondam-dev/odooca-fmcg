import { describe, expect, it } from "vitest";
import type { Snapshot } from "../src/domain/contracts";
import {
    strictCreditBlock,
    strictCreditMessage,
} from "../src/domain/credit-block";

const credit: NonNullable<Snapshot["outlet_credit"]> = {
    "5": { overdue_count: 2, overdue_total: 150000, oldest_due: "2026-10-01" },
};
const outlet = (mode: string | null | undefined, id = "5") =>
    ({
        id,
        commercial:
            mode === undefined
                ? undefined
                : {
                      max_order: null,
                      previous_visit_total: null,
                      top_sku: null,
                      payment_terms: null,
                      credit_limit: null,
                      contact: null,
                      credit_mode: mode,
                  },
    }) as never;

describe("strictCreditBlock", () => {
    it("strict + outlet menunggak → blokir dengan jumlah, total, dan tertua", () => {
        expect(strictCreditBlock(outlet("strict"), credit)).toEqual({
            count: 2,
            total: 150000,
            oldestDue: "2026-10-01",
        });
    });
    it("mode lain dengan tunggakan tidak memblokir (server yang memutuskan)", () => {
        for (const mode of ["limit", "limit_due", "approval"])
            expect(strictCreditBlock(outlet(mode), credit)).toBeNull();
    });
    it("tidak diketahui tidak memblokir: credit_mode null/absen, blok outlet_credit absen", () => {
        expect(strictCreditBlock(outlet(null), credit)).toBeNull();
        expect(strictCreditBlock(outlet(undefined), credit)).toBeNull();
        expect(strictCreditBlock(outlet("strict"), undefined)).toBeNull();
        expect(strictCreditBlock(undefined, credit)).toBeNull();
    });
    it("blok ada tetapi outlet tidak tercantum → tidak ada tunggakan", () => {
        expect(strictCreditBlock(outlet("strict", "9"), credit)).toBeNull();
        expect(strictCreditBlock(outlet("strict"), {})).toBeNull();
    });
    it("pesan memuat jumlah faktur dan total tanpa istilah teknis", () => {
        const text = strictCreditMessage(
            { count: 2, total: 150000, oldestDue: null },
            (n) => `Rp${n}`,
        );
        expect(text).toBe(
            "Outlet ini wajib lunas: ada 2 faktur jatuh tempo (Rp150000). Order baru tidak dapat dikirim sampai tagihan lunas.",
        );
    });
});

describe("penjaga regresi: kirim order memeriksa blokir strict", () => {
    it("send() menolak sebelum foto display dan tombol Kirim dinonaktifkan", async () => {
        const { readFileSync } = await import("node:fs");
        const src = readFileSync("src/components/OrderScreen.tsx", "utf8");
        expect(src).toContain(
            "strictCreditBlock(outlet, snapshot.outlet_credit)",
        );
        expect(src).toMatch(
            /if \(strictBlock\) \{\s*setError\(strictCreditMessage/,
        );
        expect(src).toMatch(/disabled=\{[^}]*!!strictBlock[^}]*\}/s);
    });
});
