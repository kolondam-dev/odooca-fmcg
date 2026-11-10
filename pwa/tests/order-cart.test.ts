import { describe, expect, it } from "vitest";
import type { Snapshot } from "../src/domain/contracts";
import {
    cartFromLegacy,
    cartLines,
    cartTotals,
    setTier,
    tierText,
} from "../src/domain/order-cart";
import {
    OrderLineV2Schema,
    assertQuoteV2,
    quoteV2,
} from "../src/domain/order-discount";
import { validateOrderQuote } from "../src/domain/order-pricing";

const mk = (
    id: string,
    name: string,
    price: number,
    carton: number,
    pack: number,
) =>
    ({
        id,
        name,
        brand: "Mayora",
        principal: "mayora",
        unit: "krt",
        price,
        stock: 41,
        packaging: { carton, pack, pcs: 1 },
    }) as Snapshot["products"][number];
const roma = mk("roma", "Roma Kelapa 300g", 255000, 30, 10);
const benn = mk("benn", "Benn-Beng Reguler 20g", 400000, 160, 20);
const tora = mk("tora", "Torabikka Duo 25g", 180000, 120, 10);
const snapshot = {
    catalog_version: 2,
    products: [roma, benn, tora],
    discount_programs: [
        {
            id: "gebyar",
            name: "Gebyar Promo Torabika",
            scope: "line",
            principal: "mayora",
            product_ids: ["tora"],
            max_percent: 10,
            budget_remaining: 12500000,
        },
        {
            id: "ft",
            name: "Footer Q4",
            scope: "footer",
            max_amount: 100000,
            budget_remaining: 1000000,
        },
    ],
} as unknown as Snapshot;

const cart = {
    roma: { carton: 10 },
    benn: { carton: 4, pack: 2 },
    tora: { carton: 6, pack: 6 },
};
const discounts = {
    tora: [
        { kind: "program" as const, program_id: "gebyar", percent: 5 },
        {
            kind: "tactical" as const,
            percent: 1,
            reason: "Kompetitor lebih murah",
        },
    ],
};
const footer = [
    { kind: "tactical" as const, amount: 50000, reason: "Potongan ongkos" },
];

describe("order v2 sesuai mockup Ringkasan", () => {
    it("diskon baris bertingkat 5% lalu 1% = Rp 1.100.385, subtotal 5.420.000", () => {
        const q = quoteV2(
            cartLines(cart, discounts, snapshot).lines,
            footer,
            snapshot,
        );
        const t = q.lines.find((l) => l.product_id === "tora")!;
        expect(t.gross).toBe(1170000);
        expect(t.steps.map((s) => s.amount)).toEqual([58500, 11115]);
        expect(t.net).toBe(1100385);
        expect(q.subtotal).toBe(5420000);
        expect(q.lineDiscount).toBe(69615);
        expect(q.afterLine).toBe(5350385);
        expect(q.footerDiscount).toBe(50000);
        expect(q.total).toBe(5300385);
        expect(q.tactical).toBe(true);
        expect(q.errors).toEqual([]);
    });
    it("beberapa satuan per SKU dikirim apa adanya, tanpa peleburan", () => {
        const { lines } = cartLines(cart, {}, snapshot);
        expect(lines.find((l) => l.product_id === "benn")!.tiers).toEqual([
            { uom: "carton", qty: "4" },
            { uom: "pack", qty: "2" },
        ]);
    });
    it("lolos validateOrderQuote v2 dan menolak total yang tidak cocok", () => {
        const { lines } = cartLines(cart, discounts, snapshot);
        const body = {
            lines,
            footer_discounts: footer,
            pricing_version: 2 as const,
            observed_total: "5300385",
        };
        expect(() => validateOrderQuote(body, snapshot)).not.toThrow();
        expect(() =>
            validateOrderQuote(
                { ...body, observed_total: "5300000" },
                snapshot,
            ),
        ).toThrow(/Total estimasi/);
    });
    it("program: di luar SKU/maks/budget ditolak; urutan program-lalu-pengajuan wajib", () => {
        const bad = (d: unknown) =>
            quoteV2(
                [
                    {
                        product_id: "roma",
                        tiers: [{ uom: "carton", qty: "1" }],
                        discounts: [d as never],
                    },
                ],
                [],
                snapshot,
            ).errors;
        expect(
            bad({ kind: "program", program_id: "gebyar", percent: 5 })[0],
        ).toMatch(/tidak berlaku/);
        expect(
            bad({ kind: "program", program_id: "nope", percent: 5 })[0],
        ).toMatch(/tidak ditemukan/);
        const maxed = quoteV2(
            [
                {
                    product_id: "tora",
                    tiers: [{ uom: "carton", qty: "1" }],
                    discounts: [
                        { kind: "program", program_id: "gebyar", percent: 11 },
                    ],
                },
            ],
            [],
            snapshot,
        );
        expect(maxed.errors[0]).toMatch(/maksimal 10%/);
        expect(
            OrderLineV2Schema.safeParse({
                product_id: "tora",
                tiers: [{ uom: "carton", qty: "1" }],
                discounts: [
                    { kind: "tactical", percent: 1, reason: "abc" },
                    { kind: "program", program_id: "gebyar", percent: 5 },
                ],
            }).success,
        ).toBe(false);
    });
    it("diskon footer tidak boleh melebihi total dan program footer dibatasi maks", () => {
        const lines = cartLines({ roma: { carton: 1 } }, {}, snapshot).lines;
        expect(
            quoteV2(
                lines,
                [{ kind: "tactical", amount: 999999, reason: "abc" }],
                snapshot,
            ).errors[0],
        ).toMatch(/melebihi total/);
        expect(
            quoteV2(
                lines,
                [{ kind: "program", program_id: "ft", amount: 100001 }],
                snapshot,
            ).errors[0],
        ).toMatch(/maksimal/);
    });
    it("SKU ganda ditolak", () => {
        const l = {
            product_id: "roma",
            tiers: [{ uom: "carton" as const, qty: "1" }],
        };
        expect(() =>
            assertQuoteV2(
                { lines: [l, l], observed_total: "255000" },
                snapshot,
            ),
        ).toThrow(/SKU ganda/);
    });
});

describe("keranjang POS", () => {
    it("SKU hilang dari katalog dilaporkan sebagai stale, bukan dibuang diam-diam", () => {
        const r = cartLines(
            { roma: { carton: 1 }, gone: { pack: 2 } },
            {},
            snapshot,
        );
        expect(r.stale).toEqual(["gone"]);
        expect(r.lines).toHaveLength(1);
        const t = cartTotals({ gone: { pack: 2 } }, {}, [], snapshot);
        expect(t.skuCount).toBe(0);
        expect(t.stale).toEqual(["gone"]);
    });
    it("entri stale berkuantitas nol diabaikan", () => {
        expect(cartLines({ gone: { pack: 0 } }, {}, snapshot).stale).toEqual(
            [],
        );
    });
    it("setTier membuang SKU saat semua satuan nol", () => {
        const c = setTier({}, "roma", "carton", 2);
        expect(setTier(c, "roma", "carton", 0)).toEqual({});
    });
    it("draf lama satu-satuan dibaca ke keranjang baru", () => {
        expect(cartFromLegacy({ p1: 3, p2: 0 }, { p1: "pack" })).toEqual({
            p1: { pack: 3 },
        });
    });
    it("teks ringkas memakai singkatan krt/pak/pcs", () => {
        expect(tierText(benn, { carton: 4, pack: 2 })).toBe("4 krt 2 pak");
    });
});
