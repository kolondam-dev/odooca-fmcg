import type { Snapshot } from "./contracts";
import type { OrderUom } from "./order-pricing";
import {
    quoteV2,
    type FooterDiscount,
    type LineDiscount,
    type OrderLineV2,
} from "./order-discount.ts";
import { productPackaging } from "./product-units.ts";

/** Keranjang POS: satu SKU boleh memuat beberapa satuan sekaligus (mis. 4 krt + 2 pak). */
export type Tiers = Partial<Record<OrderUom, number>>;
export type Cart = Record<string, Tiers>;
export const MAX_QTY = 999;
export function validQty(n: unknown): n is number {
    return (
        typeof n === "number" && Number.isInteger(n) && n >= 1 && n <= MAX_QTY
    );
}
const ORDER: OrderUom[] = ["carton", "pack", "pcs"];

type Product = Snapshot["products"][number];

export function tierQty(cart: Cart, productId: string, uom: OrderUom) {
    return cart[productId]?.[uom] ?? 0;
}

export function setTier(
    cart: Cart,
    productId: string,
    uom: OrderUom,
    value: number,
): Cart {
    const next: Tiers = { ...cart[productId], [uom]: value };
    const rest = { ...cart };
    if (ORDER.every((u) => !(next[u] ?? 0))) delete rest[productId];
    else rest[productId] = next;
    return rest;
}

/** Draf lama menyimpan satu satuan per SKU: {quantities, units}. */
export function cartFromLegacy(
    quantities: Record<string, number> = {},
    units: Record<string, OrderUom> = {},
): Cart {
    const cart: Cart = {};
    for (const [id, q] of Object.entries(quantities))
        if (q > 0) cart[id] = { [units[id] ?? "carton"]: q };
    return cart;
}

export function pcsOf(product: Product, tiers: Tiers, catalogVersion?: 2) {
    const per = productPackaging(product, catalogVersion);
    return ORDER.reduce((sum, u) => sum + (tiers[u] ?? 0) * per[u], 0);
}

/** Diskon baris per SKU (urut: program dulu, lalu pengajuan). */
export type LineDiscounts = Record<string, LineDiscount[]>;

export function cartLines(
    cart: Cart,
    discounts: LineDiscounts,
    snapshot: Snapshot,
) {
    const lines: OrderLineV2[] = [];
    /** SKU di draft yang sudah tidak ada di snapshot terbaru. */
    const stale: string[] = [];
    /** Kuantitas tidak valid: diblokir, tidak pernah dipotong diam-diam. */
    const invalid: string[] = [];
    for (const [id, tiers] of Object.entries(cart)) {
        const product = snapshot.products.find((p) => p.id === id);
        // Slot yang tidak ada (undefined) = kosong; null/NaN/string eksplisit = rusak.
        const active = ORDER.filter(
            (u) => tiers[u] !== undefined && tiers[u] !== 0,
        );
        if (!active.length) continue;
        if (!product) {
            stale.push(id);
            continue;
        }
        const bad = active.find((u) => !validQty(tiers[u]));
        if (bad) {
            invalid.push(
                `Kuantitas ${product.name} tidak valid (bilangan bulat 1–${MAX_QTY} per satuan).`,
            );
            continue;
        }
        const line: OrderLineV2 = {
            product_id: id,
            tiers: active.map((uom) => ({
                uom,
                qty: String(tiers[uom]),
            })),
        };
        if (discounts[id]?.length) line.discounts = discounts[id];
        lines.push(line);
    }
    return { lines, stale, invalid };
}

/** Teks "4 krt 2 pak" memakai singkatan satuan produk. */
export function tierText(_product: Product, tiers: Tiers) {
    const short: Record<OrderUom, string> = {
        carton: "krt",
        pack: "pak",
        pcs: "pcs",
    };
    return ORDER.filter((u) => (tiers[u] ?? 0) > 0)
        .map((u) => `${tiers[u]} ${short[u]}`)
        .join(" ");
}

export function cartTotals(
    cart: Cart,
    discounts: LineDiscounts,
    footer: FooterDiscount[],
    snapshot: Snapshot,
) {
    const { lines, stale, invalid } = cartLines(cart, discounts, snapshot);
    const quote = quoteV2(lines, footer, snapshot);
    return {
        skuCount: lines.length,
        lines,
        stale,
        quote,
        gross: quote.subtotal,
        total: quote.total,
        errors: [...invalid, ...quote.errors],
    };
}

/** Stok sistem (basis karton, boleh pecahan) dalam satuan campuran: "41 krt 6 pak". */
export function stockText(
    product: Product,
    cartons: number,
    catalogVersion?: 2,
) {
    const per = productPackaging(product, catalogVersion);
    let pcs = Math.max(0, Math.round(cartons * per.carton));
    const parts: string[] = [];
    const k = Math.floor(pcs / per.carton);
    pcs -= k * per.carton;
    const p = per.pack === per.carton ? 0 : Math.floor(pcs / per.pack);
    pcs -= p * per.pack;
    if (k) parts.push(`${k} krt`);
    if (p) parts.push(`${p} pak`);
    if (pcs) parts.push(`${pcs} pcs`);
    return parts.length ? parts.join(" · ") : "0 krt";
}
