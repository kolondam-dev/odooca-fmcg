import type { Snapshot } from "./contracts";

/**
 * Pemblokiran order mode kredit `strict` (FE-12; keputusan pemilik 2026-11-22: PWA memblokir).
 * Aturan server (`sale.order._compute_credit_limit_exceeded`): outlet bermode strict dengan faktur
 * jatuh tempo tidak boleh mendapat order baru. Di sini hanya fakta snapshot yang dipakai:
 * - `credit_mode` bukan "strict" atau tidak diketahui (null/absen) → tidak memblokir;
 * - blok `outlet_credit` tidak ada (server lama/tanpa akses) → tidak diketahui → tidak memblokir;
 * - outlet tidak tercantum di `outlet_credit` → tidak ada tunggakan → tidak memblokir.
 * Server tetap otoritatif; PWA hanya mencegah order yang pasti ditolak.
 */
export type StrictCreditBlock = {
    count: number;
    total: number;
    /** Tanggal jatuh tempo tertua (YYYY-MM-DD) bila diketahui. */
    oldestDue: string | null;
};

type Outlet = Snapshot["outlets"][number];

export function strictCreditBlock(
    outlet: Pick<Outlet, "id" | "commercial"> | undefined,
    outletCredit: Snapshot["outlet_credit"],
): StrictCreditBlock | null {
    if (!outlet || outletCredit === undefined) return null;
    if (outlet.commercial?.credit_mode !== "strict") return null;
    const entry = outletCredit[outlet.id];
    if (!entry) return null;
    return {
        count: entry.overdue_count,
        total: entry.overdue_total,
        oldestDue: entry.oldest_due,
    };
}

/** Kalimat penjelasan untuk salesman (tanpa menyebut istilah teknis). */
export function strictCreditMessage(
    block: StrictCreditBlock,
    format: (n: number) => string,
): string {
    const faktur = `${block.count} faktur jatuh tempo (${format(block.total)})`;
    return `Outlet ini wajib lunas: ada ${faktur}. Order baru tidak dapat dikirim sampai tagihan lunas.`;
}
