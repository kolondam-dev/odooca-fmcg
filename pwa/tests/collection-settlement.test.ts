import { describe, expect, it } from "vitest";
import {
    CollectionSettlementSchema,
    collectionV2Enabled,
    settledReceivables,
} from "../src/domain/collection-settlement.ts";
import { normalizedReference as n } from "../src/domain/collection-contracts.ts";
import { tripMoney } from "../src/domain/trip-summary.ts";

const evidence = {
    id: "8f14e45f-ceea-467f-a0e6-1b8f1e3a1c11",
    latitude: 1.4,
    longitude: 124.8,
    accuracy: 3,
    capturedAt: "2026-11-13T02:00:00.000Z",
};
const base = {
    settlement_version: 1,
    outlet_id: "O1",
    outlet: "Toko A",
    trip_id: "TRIP-01",
    business_date: "2026-11-13",
    method: "cash",
    payer: "Budi",
    receipt_number: "KW-001",
    notes: "",
    evidence,
    allocations: [
        {
            receivable_reference: "INV-1",
            amount_due: "1000000",
            amount: "1000000",
        },
        {
            receivable_reference: "INV-2",
            amount_due: "750000",
            amount: "400000",
        },
    ],
    remainders: [
        {
            receivable_reference: "INV-2",
            reason: "Toko tidak punya uang",
            promise_date: "2026-12-01",
        },
    ],
};
describe("CollectionSettlementSchema", () => {
    it("menerima banyak faktur dalam satu bukti", () => {
        expect(CollectionSettlementSchema.safeParse(base).success).toBe(true);
    });
    it("menolak sisa tanpa alasan, alasan untuk faktur lunas, dan faktur ganda", () => {
        expect(
            CollectionSettlementSchema.safeParse({ ...base, remainders: [] })
                .success,
        ).toBe(false);
        expect(
            CollectionSettlementSchema.safeParse({
                ...base,
                remainders: [
                    ...base.remainders,
                    { ...base.remainders[0], receivable_reference: "INV-1" },
                ],
            }).success,
        ).toBe(false);
        expect(
            CollectionSettlementSchema.safeParse({
                ...base,
                allocations: [base.allocations[0], base.allocations[0]],
                remainders: [],
            }).success,
        ).toBe(false);
    });
    it("menolak nominal melebihi saldo, transfer tanpa referensi, dan tunai dengan referensi", () => {
        expect(
            CollectionSettlementSchema.safeParse({
                ...base,
                allocations: [{ ...base.allocations[0], amount: "1000001" }],
                remainders: [],
            }).success,
        ).toBe(false);
        expect(
            CollectionSettlementSchema.safeParse({
                ...base,
                method: "transfer",
            }).success,
        ).toBe(false);
        expect(
            CollectionSettlementSchema.safeParse({
                ...base,
                transfer_reference: "TRF-9",
            }).success,
        ).toBe(false);
    });
    it("flag server wajib true", () => {
        expect(collectionV2Enabled({})).toBe(false);
        expect(collectionV2Enabled({ features: { collection_v2: true } })).toBe(
            true,
        );
    });
});
describe("settlement pada antrean", () => {
    const row = (state: string, refs: string[], method = "cash") =>
        ({
            owner: "o",
            state,
            command: {
                type: "collection.settlement.submit",
                client_uuid: `u-${state}-${refs[0]}`,
                occurred_at: "2026-11-13T02:00:00.000Z",
                payload: {
                    trip_id: "TRIP-01",
                    method,
                    allocations: refs.map((r) => ({
                        receivable_reference: r,
                        amount: "100",
                    })),
                },
            },
        }) as never;
    it("settledReceivables mengabaikan yang ditolak", () => {
        const s = settledReceivables([
            row("queued", ["INV-1"]),
            row("rejected", ["INV-2"]),
        ] as never);
        expect(s.has(n("INV-1"))).toBe(true);
        expect(s.has(n("INV-2"))).toBe(false);
    });
    it("tripMoney menjumlahkan alokasi per metode dan memasukkan UUID tunai", () => {
        const q = [row("queued", ["A", "B"]), row("queued", ["C"], "transfer")];
        const m = tripMoney(q, "o", "2026-11-13", "TRIP-01");
        expect(m.cash).toBe(200);
        expect(m.transfer).toBe(100);
        expect(m.cashReceiptUuids).toEqual(["u-queued-A"]);
    });
});
