import { describe, expect, it } from "vitest";
import type { Snapshot } from "../src/domain/contracts";
import {
    cartFromLegacy,
    cartLines,
    cartTotals,
    normalizeLine,
    setTier,
    tierText,
} from "../src/domain/order-cart";
import { orderQuote } from "../src/domain/order-pricing";

const product = {
    id: "p1",
    name: "Benn-Beng Reguler 20g",
    brand: "Mayora",
    principal: "mayora",
    unit: "krt",
    price: 400000,
    stock: 41,
    packaging: { carton: 160, pack: 20, pcs: 1 },
} as Snapshot["products"][number];
const snapshot = {
    catalog_version: 2,
    products: [product],
} as unknown as Snapshot;

describe("keranjang POS multi-satuan", () => {
    it("melebur 4 krt + 2 pak menjadi satu baris pak (680 pcs = 34 pak)", () => {
        expect(normalizeLine(product, { carton: 4, pack: 2 }, 2)).toEqual({
            product_id: "p1",
            qty: "34",
            uom: "pack",
        });
    });
    it("memakai karton bila total habis dibagi karton", () => {
        expect(normalizeLine(product, { carton: 10 }, 2)).toMatchObject({
            qty: "10",
            uom: "carton",
        });
        expect(normalizeLine(product, { carton: 1, pack: 8 }, 2)).toMatchObject(
            {
                qty: "2",
                uom: "carton",
            },
        );
    });
    it("jatuh ke pcs bila ada sisa pcs", () => {
        expect(normalizeLine(product, { pack: 1, pcs: 3 }, 2)).toMatchObject({
            qty: "23",
            uom: "pcs",
        });
    });
    it("menolak total yang tidak muat 999 pada satuan mana pun", () => {
        const big = normalizeLine(product, { carton: 999, pcs: 1 }, 2);
        expect("error" in big).toBe(true);
    });
    it("total sama dengan orderQuote pada baris hasil lebur", () => {
        const cart = setTier(setTier({}, "p1", "carton", 4), "p1", "pack", 2);
        const { lines } = cartLines(cart, snapshot);
        expect(lines).toHaveLength(1);
        const totals = cartTotals(cart, snapshot, 5);
        expect(totals.gross).toBe(orderQuote(lines, snapshot).gross);
        expect(totals.gross).toBe(1700000);
        expect(totals.total).toBe(1700000 - 85000);
    });
    it("setTier membuang SKU saat semua satuan nol", () => {
        const cart = setTier({}, "p1", "carton", 2);
        expect(setTier(cart, "p1", "carton", 0)).toEqual({});
    });
    it("draf lama satu-satuan dibaca ke keranjang baru", () => {
        expect(cartFromLegacy({ p1: 3, p2: 0 }, { p1: "pack" })).toEqual({
            p1: { pack: 3 },
        });
    });
    it("teks ringkas memakai singkatan krt/pak/pcs", () => {
        expect(tierText(product, { carton: 4, pack: 2 })).toBe("4 krt 2 pak");
    });
});
