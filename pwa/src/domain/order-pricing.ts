import { productPackaging } from "./product-units.ts";
import { z } from "zod";
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
export function validateOrderQuote(
    body: {
        lines: { product_id: string; qty: string; uom: OrderUom }[];
        pricing_version?: 1;
        discount_request?: z.infer<typeof DiscountRequestSchema>;
        observed_total: string;
    },
    snapshot: Snapshot,
) {
    if (body.pricing_version !== 1) {
        if (body.discount_request || body.lines.some((l) => l.uom !== "carton"))
            throw new Error("Order tier/diskon wajib versi harga.");
        return;
    }
    if (new Set(body.lines.map((l) => l.product_id)).size !== body.lines.length)
        throw new Error("SKU ganda.");
    if (
        body.observed_total !==
        String(
            orderQuote(body.lines, snapshot, body.discount_request)
                .requestedTotal,
        )
    )
        throw new Error("Total estimasi tidak cocok dengan satuan/diskon.");
}
