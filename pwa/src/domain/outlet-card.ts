/**
 * Data kartu outlet dan kartu Tagihan hub kunjungan (DS: Outlet, Kunjungan_hub).
 * Hanya memakai yang benar-benar ada di snapshot; yang tidak ada tidak ditampilkan
 * dan tidak dikarang (lihat K7 dan K28).
 */
type MetaSource = { time?: unknown; distance?: unknown };

/** Nilai kosong atau tanda pengganti dari server dianggap tidak ada. */
const PLACEHOLDER = /^(?:[-–—]+|n\/?a|null|undefined|tbd)$/i;
const text = (value: unknown) => {
    const trimmed = typeof value === "string" ? value.trim() : "";
    return trimmed && !PLACEHOLDER.test(trimmed) ? trimmed : undefined;
};

/** Jam rencana kunjungan gaya DS ("09.15"); format lain dianggap tidak valid. */
export function plannedTime(value: unknown): string | undefined {
    const match = /^(\d{1,2})[.:](\d{2})$/.exec(text(value) ?? "");
    if (!match) return undefined;
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour > 23 || minute > 59) return undefined;
    return `${String(hour).padStart(2, "0")}.${match[2]}`;
}

export function outletMeta(outlet: MetaSource): {
    time?: string;
    distance?: string;
} {
    return { time: plannedTime(outlet.time), distance: text(outlet.distance) };
}

export type CreditCommercial = {
    credit_limit?: number | null;
    ar_outstanding?: number | null;
    payment_terms?: string | null;
};

/** Ada hanya bila limit dan piutang sama-sama diketahui dan piutang melebihi limit. */
export function creditExceeded(commercial?: CreditCommercial | null):
    | {
          limit: number;
          outstanding: number;
          terms?: string;
      }
    | undefined {
    if (!commercial) return undefined;
    const { credit_limit: limit, ar_outstanding: outstanding } = commercial;
    if (limit == null || outstanding == null) return undefined;
    if (!Number.isFinite(limit) || !Number.isFinite(outstanding))
        return undefined;
    if (outstanding <= limit) return undefined;
    return { limit, outstanding, terms: text(commercial.payment_terms) };
}
