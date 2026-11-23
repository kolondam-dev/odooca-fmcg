import type { Snapshot } from "./contracts";

/**
 * Piutang outlet dan "Wajib ditagih hari ini" (FE-8, data BE-7 `outlet_receivables`).
 *
 * Aturan pemilik (2026-11-23), dihitung dari snapshot sampai modul backend "AR collection assignment"
 * (surat jalan penagihan) tersedia:
 * - hanya outlet yang ditugaskan ke salesman aktif dan ada pada PJP hari itu (= outlet snapshot,
 *   server sudah membatasinya);
 * - faktur terbuka yang jatuh temponya KURANG dari 7 hari dari hari bisnis (termasuk yang sudah lewat).
 * Server tetap otoritatif; PWA hanya menampilkan. Tanpa blok `outlet_receivables` (server lama) hasilnya
 * "tidak diketahui", bukan "tidak ada tagihan".
 */
export const COLLECT_WINDOW_DAYS = 7;

type Receivables = NonNullable<Snapshot["outlet_receivables"]>;
export type OutletReceivable = Receivables[string];
export type ReceivableInvoice = OutletReceivable["invoices"][number];

const DAY_MS = 86_400_000;
const dayNumber = (iso: string) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / DAY_MS : null;
};

/** Selisih hari kalender jatuh tempo − hari bisnis (negatif = terlambat); null bila tanggal tidak valid. */
export function daysUntilDue(due: string | null, today: string) {
    if (!due) return null;
    const a = dayNumber(due);
    const b = dayNumber(today);
    return a === null || b === null ? null : a - b;
}

export function dueLabel(days: number | null) {
    if (days === null) return "Tanpa jatuh tempo";
    if (days < 0) return `Terlambat ${-days} hari`;
    if (days === 0) return "Jatuh tempo hari ini";
    return `Jatuh tempo ${days} hari lagi`;
}

export type CollectToday = {
    invoices: ReceivableInvoice[];
    count: number;
    total: number;
    overdueCount: number;
    /**
     * false = angka hanya SUBTOTAL/MINIMUM dari faktur yang dimuat: server memotong daftar (`truncated`,
     * urut jatuh tempo tertua dulu) dan faktur terakhir yang dimuat masih di dalam jendela, sehingga masih
     * ada faktur jendela yang tidak terkirim. Jumlah dan nominal tidak boleh disajikan sebagai total lengkap.
     */
    complete: boolean;
};

/**
 * Faktur yang wajib ditagih hari ini untuk satu outlet (urutan server: jatuh tempo tertua dulu).
 * Daftar server dipotong 50, jadi hasil bisa tidak lengkap: bila terpotong dan faktur dengan jatuh tempo
 * terjauh yang dimuat belum keluar dari jendela, `complete` = false. Bila faktur termuat sudah melewati
 * jendela, semua faktur jendela pasti sudah termuat (urutan tertua dulu) sehingga hasil lengkap.
 * Saldo sisa TIDAK diturunkan dari `outstanding_total` (faktur masa depan bisa di luar jendela).
 */
export function mustCollectToday(
    entry: OutletReceivable | undefined,
    today: string,
): CollectToday {
    const loaded = entry?.invoices ?? [];
    const days = loaded.map((i) => daysUntilDue(i.due_date, today));
    const invoices = loaded.filter((_, idx) => {
        const d = days[idx];
        return d !== null && d < COLLECT_WINDOW_DAYS;
    });
    const beyondWindow = days.some(
        (d) => d !== null && d >= COLLECT_WINDOW_DAYS,
    );
    return {
        invoices,
        count: invoices.length,
        total: invoices.reduce((s, i) => s + i.balance, 0),
        overdueCount: invoices.filter((i) => i.overdue).length,
        complete: !entry?.truncated || beyondWindow,
    };
}

/**
 * Piutang berjalan untuk pemeriksaan limit. `undefined` blok = tidak diketahui → pakai nilai lama
 * (`commercial.ar_outstanding`, bisa null); blok ada tetapi outlet tidak tercantum = 0.
 */
export function outstandingFor(
    outletId: string,
    receivables: Snapshot["outlet_receivables"],
    legacy?: number | null,
): number | null {
    if (receivables === undefined) return legacy ?? null;
    return receivables[outletId]?.outstanding_total ?? 0;
}
