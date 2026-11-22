import type { Snapshot } from "./contracts";

/**
 * Pratinjau tier approval diskon (FE-11). HANYA indikasi untuk salesman: server tetap yang
 * menentukan perlu/tidaknya approval saat order dikirim (zona bebas `pct <= batas`, tier berlaku
 * bila `pct >= min_discount`, kumulatif % berbobot nilai per principal; BE-15/BE-18).
 */
type TierBlock = {
    free_zone_max: number | null;
    tiers: { min_discount: number; approver: string }[];
};
export type ApprovalTiers = NonNullable<Snapshot["approval_tiers"]>;

export type ApprovalPreview = {
    /** none = tanpa diskon; free = zona bebas; needs = perlu rantai approver. */
    status: "none" | "free" | "needs";
    /** Diskon kumulatif (%) termasuk pemakaian sebelumnya pada cakupan aturan. */
    pct: number;
    /** Diskon (%) order ini saja. */
    orderPct: number;
    scope: "order" | "outlet_month" | "salesman_day";
    /** Batas zona bebas principal (%), null = tidak ada zona bebas. */
    limit: number | null;
    /** Rantai approver berjenjang (urutan tier), kosong bila tidak ada tier terkonfigurasi. */
    chain: string[];
    /** Sisa diskon (Rp) yang masih di zona bebas; null bila tidak ada zona bebas. */
    headroom: number | null;
    /** Tier berikutnya yang akan ikut bila diskon naik (kosong bila sudah tier tertinggi). */
    next: { min_discount: number; approver: string } | null;
    /** Ada pemakaian sebelumnya yang ikut dihitung (pesanan lain pada jendela aturan). */
    cumulative: boolean;
    /** Order memakai promo resmi: pemantauan Supervisor bila tidak ada rantai taktikal. */
    promoMonitoring: boolean;
};

export function previewApproval(input: {
    tiers: ApprovalTiers | undefined;
    principal: string | null;
    outletId: string;
    /** Diskon (Rp) dan bruto (Rp) order ini untuk principal tersebut. */
    discount: number;
    gross: number;
    /** Ada diskon program resmi pada order. */
    hasProgram: boolean;
}): ApprovalPreview | null {
    const cfg = input.tiers?.discount;
    if (!cfg || input.gross <= 0) return null;
    const block: TierBlock =
        (input.principal ? cfg.principals[input.principal] : undefined) ??
        cfg.default;
    let usedDiscount = 0;
    let usedGross = 0;
    if (cfg.scope !== "order") {
        for (const u of cfg.usage) {
            if (u.principal !== input.principal) continue;
            if (cfg.scope === "outlet_month" && u.outlet_id !== input.outletId)
                continue;
            usedDiscount += u.discount_amount;
            usedGross += u.gross_amount;
        }
    }
    const orderPct = round4((input.discount / input.gross) * 100);
    const totalGross = usedGross + input.gross;
    const totalDiscount = usedDiscount + input.discount;
    const pct = round4((totalDiscount / totalGross) * 100);
    const limit = block.free_zone_max;
    const base = {
        pct,
        orderPct,
        scope: cfg.scope,
        limit,
        cumulative: usedGross > 0,
        promoMonitoring: false,
    };
    const headroom =
        limit === null
            ? null
            : Math.max(
                  0,
                  Math.floor((limit / 100) * totalGross - totalDiscount),
              );
    if (pct <= 0 && !input.hasProgram)
        return {
            ...base,
            status: "none",
            chain: [],
            headroom,
            next: null,
        };
    const free = pct > 0 && limit !== null && pct <= limit;
    if (pct <= 0 || free)
        return {
            ...base,
            status: "free",
            chain: [],
            headroom,
            next: block.tiers[0] ?? null,
            promoMonitoring: input.hasProgram,
        };
    const tiers = block.tiers;
    let chain = tiers.filter(
        (t) => t.min_discount <= 0 || pct >= t.min_discount,
    );
    if (!chain.length && tiers.length) chain = [tiers[0]];
    const next = tiers.find((t) => t.min_discount > pct) ?? null;
    return {
        ...base,
        status: "needs",
        chain: chain.map((t) => t.approver),
        headroom,
        next,
    };
}

function round4(n: number) {
    return Math.round(n * 10000) / 10000;
}

/** Teks pendek untuk Callout/Step. */
export function approvalPreviewText(p: ApprovalPreview): string {
    const pct = formatPct(p.pct);
    if (p.status === "needs") {
        const who = p.chain.length ? p.chain.join(" → ") : "approver";
        return `Diskon ${p.cumulative ? "kumulatif " : ""}${pct}% → perlu ${who}`;
    }
    if (p.promoMonitoring) return "Pemantauan promo: Supervisor";
    return p.status === "free"
        ? `Diskon ${p.cumulative ? "kumulatif " : ""}${pct}% dalam zona bebas`
        : "";
}

export function formatPct(n: number) {
    return n.toLocaleString("id-ID", { maximumFractionDigits: 2 });
}

/** Penjelasan cakupan kumulatif untuk salesman. */
export function scopeLabel(scope: ApprovalPreview["scope"]) {
    return scope === "outlet_month"
        ? "diskon outlet ini bulan ini"
        : scope === "salesman_day"
          ? "diskon Anda hari ini"
          : "order ini";
}
