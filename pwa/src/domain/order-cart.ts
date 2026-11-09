import type { Snapshot } from "./contracts";
import { orderQuote, type OrderUom } from "./order-pricing";
import { productPackaging } from "./product-units.ts";

/** Keranjang POS: satu SKU boleh memuat beberapa satuan sekaligus (mis. 4 krt + 2 pak). */
export type Tiers = Partial<Record<OrderUom, number>>;
export type Cart = Record<string, Tiers>;
export const MAX_QTY = 999;
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

/**
 * Kontrak dan backend hanya menerima satu baris per SKU (satu satuan, qty 1–999).
 * Beberapa satuan dilebur ke total pcs lalu diekspresikan dalam satuan terbesar
 * yang habis membagi total tersebut. Melebihi 999 pada satuan itu -> galat jelas.
 */
export function normalizeLine(
    product: Product,
    tiers: Tiers,
    catalogVersion?: 2,
): { product_id: string; qty: string; uom: OrderUom } | { error: string } {
    const per = productPackaging(product, catalogVersion);
    const pcs = pcsOf(product, tiers, catalogVersion);
    if (pcs <= 0) return { error: "Kuantitas kosong." };
    for (const uom of ORDER) {
        if (pcs % per[uom] === 0 && pcs / per[uom] <= MAX_QTY)
            return {
                product_id: product.id,
                qty: String(pcs / per[uom]),
                uom,
            };
    }
    return {
        error: `${product.name}: total ${pcs} pcs melebihi batas ${MAX_QTY} per satuan. Kurangi jumlah atau pecah order.`,
    };
}

export function cartLines(cart: Cart, snapshot: Snapshot) {
    const lines: { product_id: string; qty: string; uom: OrderUom }[] = [];
    const errors: string[] = [];
    /** SKU di draft yang sudah tidak ada di snapshot terbaru. */
    const stale: string[] = [];
    for (const [id, tiers] of Object.entries(cart)) {
        const product = snapshot.products.find((p) => p.id === id);
        if (!product) {
            if (Object.values(tiers).some((q) => (q ?? 0) > 0)) stale.push(id);
            continue;
        }
        if (pcsOf(product, tiers, snapshot.catalog_version) <= 0) continue;
        const line = normalizeLine(product, tiers, snapshot.catalog_version);
        if ("error" in line) errors.push(line.error);
        else lines.push(line);
    }
    return { lines, errors, stale };
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
    snapshot: Snapshot,
    discountPercent = 0,
) {
    const { lines, errors, stale } = cartLines(cart, snapshot);
    let gross = 0;
    try {
        gross = lines.length ? orderQuote(lines, snapshot).gross : 0;
    } catch {
        gross = 0;
    }
    const discount = Math.round((gross * discountPercent) / 100);
    return {
        skuCount: lines.length,
        gross,
        discount,
        total: gross - discount,
        lines,
        errors,
        stale,
    };
}
