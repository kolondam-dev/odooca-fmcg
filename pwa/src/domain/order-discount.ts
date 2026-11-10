import { z } from "zod";
import { productPackaging } from "./product-units.ts";
import type { Snapshot } from "./contracts";

/**
 * Pricing v2 (design system: Diskon_baris, Diskon_footer, Ringkasan).
 * - Satu SKU boleh memuat beberapa satuan sekaligus (tiers).
 * - Diskon baris bertingkat: dihitung berurutan atas sisa harga (program dulu, lalu pengajuan).
 * - Diskon footer dalam Rupiah, dihitung setelah diskon baris.
 * Semua angka bulat (Rupiah) agar identik di PWA dan backend.
 */
export const UomV2Schema = z.enum(["carton", "pack", "pcs"]);
export type Uom = z.infer<typeof UomV2Schema>;
const Percent = z.number().int().min(1).max(100);
const Reason = z.string().trim().min(3).max(500);

export const LineDiscountSchema = z.discriminatedUnion("kind", [
    z
        .object({
            kind: z.literal("program"),
            program_id: z.string().min(1).max(64),
            percent: Percent,
        })
        .strict(),
    z
        .object({
            kind: z.literal("tactical"),
            percent: Percent,
            reason: Reason,
        })
        .strict(),
]);
export type LineDiscount = z.infer<typeof LineDiscountSchema>;

export const FooterDiscountSchema = z.discriminatedUnion("kind", [
    z
        .object({
            kind: z.literal("program"),
            program_id: z.string().min(1).max(64),
            amount: z.number().int().min(1).max(999_999_999_999),
        })
        .strict(),
    z
        .object({
            kind: z.literal("tactical"),
            amount: z.number().int().min(1).max(999_999_999_999),
            reason: Reason,
        })
        .strict(),
]);
export type FooterDiscount = z.infer<typeof FooterDiscountSchema>;

export const TierQtySchema = z
    .object({ uom: UomV2Schema, qty: z.string().regex(/^[1-9]\d{0,2}$/) })
    .strict();
export const OrderLineV2Schema = z
    .object({
        product_id: z.string().min(1),
        tiers: z.array(TierQtySchema).min(1).max(3),
        discounts: z.array(LineDiscountSchema).max(6).optional(),
    })
    .strict()
    .superRefine((line, ctx) => {
        if (new Set(line.tiers.map((t) => t.uom)).size !== line.tiers.length)
            ctx.addIssue({ code: "custom", message: "Satuan ganda pada SKU." });
        if (!programsFirst(line.discounts ?? []))
            ctx.addIssue({
                code: "custom",
                message: "Diskon program harus sebelum pengajuan.",
            });
    });
export type OrderLineV2 = z.infer<typeof OrderLineV2Schema>;

export const DiscountProgramSchema = z
    .object({
        id: z.string().min(1).max(64),
        name: z.string().min(1).max(120),
        scope: z.enum(["line", "footer"]),
        principal: z.string().optional(),
        /** Kosong = berlaku untuk semua SKU principal. */
        product_ids: z.array(z.string()).optional(),
        max_percent: Percent.optional(),
        max_amount: z.number().int().positive().optional(),
        budget_remaining: z.number().int().nonnegative(),
    })
    .strict();
export type DiscountProgram = z.infer<typeof DiscountProgramSchema>;

function programsFirst(items: { kind: string }[]) {
    let seenTactical = false;
    for (const d of items) {
        if (d.kind === "tactical") seenTactical = true;
        else if (seenTactical) return false;
    }
    return true;
}

export type QuoteLine = {
    product_id: string;
    pcs: number;
    gross: number;
    steps: { label: string; amount: number }[];
    discount: number;
    net: number;
};
export type QuoteV2 = {
    lines: QuoteLine[];
    subtotal: number;
    lineDiscount: number;
    afterLine: number;
    footerSteps: { label: string; amount: number }[];
    footerDiscount: number;
    total: number;
    tactical: boolean;
    /** Pemakaian budget per program (Rp). */
    usage: Record<string, number>;
    errors: string[];
};

export function lineGross(
    snapshot: Snapshot,
    line: { product_id: string; tiers: { uom: Uom; qty: string }[] },
) {
    const product = snapshot.products.find((p) => p.id === line.product_id);
    if (!product) throw new Error("SKU tidak ada di katalog.");
    const units = productPackaging(product, snapshot.catalog_version);
    let pcs = 0;
    for (const t of line.tiers) pcs += Number(t.qty) * units[t.uom];
    return { pcs, gross: Math.round((product.price * pcs) / units.carton) };
}

export function quoteV2(
    lines: OrderLineV2[],
    footer: FooterDiscount[],
    snapshot: Snapshot,
): QuoteV2 {
    const programs = new Map(
        (snapshot.discount_programs ?? []).map((p) => [p.id, p]),
    );
    const errors: string[] = [];
    const usage: Record<string, number> = {};
    let tactical = false;
    const out: QuoteLine[] = [];
    for (const line of lines) {
        const { pcs, gross } = lineGross(snapshot, line);
        const product = snapshot.products.find(
            (p) => p.id === line.product_id,
        )!;
        let base = gross;
        const steps: QuoteLine["steps"] = [];
        for (const d of line.discounts ?? []) {
            const amount = Math.round((base * d.percent) / 100);
            if (d.kind === "tactical") tactical = true;
            else {
                const p = programs.get(d.program_id);
                if (!p || p.scope !== "line")
                    errors.push(`Program ${d.program_id} tidak ditemukan.`);
                else {
                    if (
                        (p.principal && p.principal !== product.principal) ||
                        (p.product_ids?.length &&
                            !p.product_ids.includes(product.id))
                    )
                        errors.push(
                            `${p.name}: tidak berlaku untuk ${product.name}.`,
                        );
                    if (p.max_percent && d.percent > p.max_percent)
                        errors.push(`${p.name}: maksimal ${p.max_percent}%.`);
                    usage[p.id] = (usage[p.id] ?? 0) + amount;
                }
            }
            steps.push({
                label: d.kind === "program" ? d.program_id : "tactical",
                amount,
            });
            base -= amount;
        }
        out.push({
            product_id: line.product_id,
            pcs,
            gross,
            steps,
            discount: gross - base,
            net: base,
        });
    }
    const subtotal = out.reduce((s, l) => s + l.gross, 0);
    const lineDiscount = out.reduce((s, l) => s + l.discount, 0);
    const afterLine = subtotal - lineDiscount;
    let remaining = afterLine;
    const footerSteps: QuoteV2["footerSteps"] = [];
    if (!programsFirst(footer))
        errors.push("Diskon program harus sebelum pengajuan.");
    for (const d of footer) {
        if (d.kind === "tactical") tactical = true;
        else {
            const p = programs.get(d.program_id);
            if (!p || p.scope !== "footer")
                errors.push(`Program ${d.program_id} tidak ditemukan.`);
            else {
                if (p.max_amount && d.amount > p.max_amount)
                    errors.push(`${p.name}: maksimal Rp ${p.max_amount}.`);
                usage[p.id] = (usage[p.id] ?? 0) + d.amount;
            }
        }
        if (d.amount > remaining)
            errors.push("Diskon footer melebihi total order.");
        footerSteps.push({
            label: d.kind === "program" ? d.program_id : "tactical",
            amount: Math.min(d.amount, remaining),
        });
        remaining -= Math.min(d.amount, remaining);
    }
    for (const [id, used] of Object.entries(usage)) {
        const p = programs.get(id);
        if (p && used > p.budget_remaining)
            errors.push(`${p.name}: melebihi sisa budget.`);
    }
    return {
        lines: out,
        subtotal,
        lineDiscount,
        afterLine,
        footerSteps,
        footerDiscount: afterLine - remaining,
        total: remaining,
        tactical,
        usage,
        errors,
    };
}

/** Validasi ketat dipakai outbox/commit: melempar pada kesalahan apa pun. */
export function assertQuoteV2(
    body: {
        lines: OrderLineV2[];
        footer_discounts?: FooterDiscount[];
        observed_total: string;
    },
    snapshot: Snapshot,
) {
    if (new Set(body.lines.map((l) => l.product_id)).size !== body.lines.length)
        throw new Error("SKU ganda.");
    const q = quoteV2(body.lines, body.footer_discounts ?? [], snapshot);
    if (q.errors.length) throw new Error(q.errors[0]);
    if (body.observed_total !== String(q.total))
        throw new Error("Total estimasi tidak cocok dengan satuan/diskon.");
    return q;
}
