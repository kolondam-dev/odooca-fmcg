import { productPackaging, type UnitTier } from "./product-units.ts";
import { z } from "zod";
import {
    assertQuoteV2,
    type FooterDiscount,
    type OrderLineV2,
} from "./order-discount.ts";
import type { Snapshot } from "./contracts";
export const UomSchema = z.enum(["carton", "pack", "pcs"]);
export type OrderUom = z.infer<typeof UomSchema>;
export const DiscountRequestSchema = z
    .object({
        percent: z.number().int().min(1).max(100),
        reason: z.string().trim().min(3).max(500),
    })
    .strict();
export function orderQuote(
    lines: { product_id: string; qty: string; uom: OrderUom }[],
    snapshot: Snapshot,
    discount?: z.infer<typeof DiscountRequestSchema>,
) {
    let gross = 0;
    for (const l of lines) {
        const p = snapshot.products.find((p) => p.id === l.product_id);
        if (
            !p ||
            !/^[1-9]\d{0,2}$/.test(l.qty) ||
            !UomSchema.safeParse(l.uom).success
        )
            throw new Error("SKU/satuan/qty tidak valid.");
        const units = productPackaging(p, snapshot.catalog_version);
        gross += (p.price * Number(l.qty) * units[l.uom]) / units.carton;
    }
    gross = Math.round(gross);
    if (!Number.isSafeInteger(gross))
        throw new Error("Total estimasi melampaui batas angka aman.");
    const request = discount
        ? DiscountRequestSchema.parse(discount)
        : undefined;
    return {
        gross,
        requestedDiscount: request
            ? Math.round((gross * request.percent) / 100)
            : 0,
        requestedTotal:
            gross - (request ? Math.round((gross * request.percent) / 100) : 0),
    };
}
/**
 * Presentation-only per-line numbers. The authoritative totals still come from
 * orderQuote so the observed_total sent to the outbox stays identical.
 */
export function lineQuote(
    product: Snapshot["products"][number],
    qty: number,
    uom: UnitTier,
    catalogVersion?: 2,
) {
    const units = productPackaging(product, catalogVersion);
    const per = units[uom];
    const pcs = qty * per;
    return {
        per,
        pcs,
        cartons: pcs / units.carton,
        subtotal: Math.round((product.price * pcs) / units.carton),
    };
}
export function orderSummary(
    lines: { product_id: string; qty: string; uom: OrderUom }[],
    snapshot: Snapshot,
) {
    let items = 0,
        pcs = 0,
        cartons = 0;
    for (const line of lines) {
        const product = snapshot.products.find((p) => p.id === line.product_id);
        if (!product || !/^[1-9]\d{0,2}$/.test(line.qty)) continue;
        const units = productPackaging(product, snapshot.catalog_version);
        const quantity = Number(line.qty);
        const pieces = quantity * units[line.uom];
        items += quantity;
        pcs += pieces;
        cartons += pieces / units.carton;
    }
    let subtotal = 0;
    try {
        subtotal = orderQuote(lines, snapshot).gross;
    } catch {
        subtotal = 0;
    }
    return { items, pcs, cartons, subtotal };
}
type LegacyLine = { product_id: string; qty: string; uom: OrderUom };
export type AnyOrderLine = LegacyLine | OrderLineV2;
export const isV2Line = (l: AnyOrderLine): l is OrderLineV2 => "tiers" in l;
/** Bentuk seragam untuk validateOrder (SKU ada, qty 1–999, satu principal). */
export function lineChecks(lines: AnyOrderLine[]) {
    return lines.map((l) => ({
        productId: l.product_id,
        quantity: Number(isV2Line(l) ? l.tiers[0]!.qty : l.qty),
    }));
}
export function validateOrderQuote(
    body: {
        lines: AnyOrderLine[];
        pricing_version?: 1 | 2;
        discount_request?: z.infer<typeof DiscountRequestSchema>;
        footer_discounts?: FooterDiscount[];
        observed_total: string;
    },
    snapshot: Snapshot,
) {
    if (body.pricing_version === 2) {
        if (body.discount_request || !body.lines.every(isV2Line))
            throw new Error("Order v2 wajib tier dan diskon bertingkat.");
        assertQuoteV2(
            {
                lines: body.lines,
                footer_discounts: body.footer_discounts,
                observed_total: body.observed_total,
            },
            snapshot,
        );
        return;
    }
    if (body.lines.some(isV2Line) || body.footer_discounts)
        throw new Error("Order tier/diskon wajib versi harga.");
    const lines = body.lines as LegacyLine[];
    if (body.pricing_version !== 1) {
        if (body.discount_request || lines.some((l) => l.uom !== "carton"))
            throw new Error("Order tier/diskon wajib versi harga.");
        return;
    }
    if (new Set(lines.map((l) => l.product_id)).size !== lines.length)
        throw new Error("SKU ganda.");
    if (
        body.observed_total !==
        String(
            orderQuote(lines, snapshot, body.discount_request).requestedTotal,
        )
    )
        throw new Error("Total estimasi tidak cocok dengan satuan/diskon.");
}

/** Pengajuan diskon (tactical) pada order apa pun: v1 percent, atau v2 baris/footer. */
export function orderHasDiscountRequest(payload: unknown): boolean {
    const p = payload as {
        discount_request?: unknown;
        footer_discounts?: { kind?: string }[];
        lines?: { discounts?: { kind?: string }[] }[];
    } | null;
    if (!p) return false;
    return (
        !!p.discount_request ||
        !!p.footer_discounts?.some((d) => d.kind === "tactical") ||
        !!p.lines?.some((l) => l.discounts?.some((d) => d.kind === "tactical"))
    );
}

/** Gerbang kontrak: backend belum menyatakan dukungan v2 -> submit/revisi v2 dikunci. */
export const ORDER_V2_UNSUPPORTED =
    "Server belum mendukung kontrak order v2 (diskon bertingkat). Order belum dapat dikirim.";
export function orderV2Enabled(snapshot: {
    features?: { order_pricing_v2?: boolean };
}) {
    return snapshot.features?.order_pricing_v2 === true;
}
