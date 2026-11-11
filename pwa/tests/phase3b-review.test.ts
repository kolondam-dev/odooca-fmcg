import { describe, expect, it } from "vitest";
import { orderSummary } from "../src/components/CloseVisitScreen";
import {
    fieldExpenseV2Enabled,
    needsRequestOdometer,
} from "../src/domain/expense";
import { tripMoney } from "../src/domain/trip-summary";
import type { QueueItem } from "../src/storage/store";

const V1 = "11111111-1111-4111-8111-111111111111";
const V2 = "22222222-2222-4222-8222-222222222222";
const order = (visit: string, total: string, key: string) =>
    ({
        key,
        owner: "u",
        label: "SO",
        state: "accepted",
        attempts: 0,
        nextAttempt: 0,
        command: {
            type: "sales.order.submit",
            client_uuid: key,
            payload: {
                outlet_id: "O1",
                observed_total: total,
                lines: [{ product_id: "P1" }],
                visit_context: {
                    visit_uuid: visit,
                    work_session_id: "33333333-3333-4333-8333-333333333333",
                    business_date: "2026-11-10",
                    snapshot_version: "s1",
                    outlet_id: "O1",
                    site: { latitude: 1.4, longitude: 124.8, radius: 50 },
                    fix: {
                        latitude: 1.4,
                        longitude: 124.8,
                        accuracy: 5,
                        sampled_at: "2026-11-10T01:00:00.000Z",
                    },
                },
            },
        },
    }) as unknown as QueueItem;

describe("review #114", () => {
    it("ringkasan penutupan hanya menghitung order kunjungan aktif", () => {
        const q = [order(V1, "100", "a"), order(V2, "250", "b")];
        expect(orderSummary(q, V2).total).toBe(250);
        expect(orderSummary(q, V2).count).toBe(1);
        expect(orderSummary(q, undefined).count).toBe(0);
    });
    it("revisi diterima menggantikan root ditolak di ringkasan", () => {
        const root = order(V1, "100", "r");
        root.state = "rejected";
        const rev = {
            ...order(V1, "150", "v"),
            command: {
                type: "sales.order.revise",
                client_uuid: "v",
                payload: {
                    root_uuid: "r",
                    supersedes_uuid: "r",
                    observed_total: "150",
                    lines: [{ product_id: "P2" }],
                },
            },
        } as unknown as QueueItem;
        const sum = orderSummary([root, rev], V1);
        expect(sum.count).toBe(1);
        expect(sum.total).toBe(150);
        expect(sum.status?.label).toBe("Diposting");
    });
    it("pengajuan uang lapangan baru terkunci tanpa kapabilitas server", () => {
        expect(fieldExpenseV2Enabled({})).toBe(false);
        expect(fieldExpenseV2Enabled({ features: {} })).toBe(false);
        expect(
            fieldExpenseV2Enabled({ features: { field_expense_v2: true } }),
        ).toBe(true);
        expect(needsRequestOdometer("emergency")).toBe(false);
    });
    it("ringkasan uang trip dibatasi trip, hari kerja, dan status", () => {
        const rc = (
            trip: string,
            amount: string,
            method: string,
            extra: Record<string, unknown> = {},
            state = "accepted",
            at = "2026-11-10T02:00:00.000Z",
            id: string = crypto.randomUUID(),
        ) =>
            ({
                key: id,
                owner: "u",
                state,
                command: {
                    type: "collection.receipt.submit",
                    client_uuid: id,
                    occurred_at: at,
                    payload: {
                        source: { delivery: { trip } },
                        method,
                        amount,
                        ...extra,
                    },
                },
            }) as unknown as QueueItem;
        const ex = (
            trip: string,
            amount: string,
            date: string,
            state = "queued",
        ) =>
            ({
                key: crypto.randomUUID(),
                owner: "u",
                state,
                command: {
                    type: "field_expense.request",
                    client_uuid: crypto.randomUUID(),
                    occurred_at: "2026-11-10T02:00:00.000Z",
                    payload: { trip_id: trip, amount, scheduled_date: date },
                },
            }) as unknown as QueueItem;
        const old = rc(
            "A",
            "100",
            "cash",
            {},
            "accepted",
            "2026-11-10T02:00:00.000Z",
            "old",
        );
        const q = [
            rc("A", "1000", "cash"),
            rc("B", "5000", "cash"),
            rc("A", "2000", "transfer"),
            rc("A", "9999", "cash", {}, "rejected"),
            rc("A", "7777", "cash", {}, "accepted", "2026-11-09T02:00:00.000Z"),
            old,
            rc("A", "150", "cash", { supersedes_uuid: "old" }),
            ex("A", "70000", "2026-11-10"),
            ex("A", "50000", "2026-11-09"),
            ex("B", "30000", "2026-11-10"),
            ex("A", "99999", "2026-11-10", "rejected"),
        ];
        expect(tripMoney(q, "u", "2026-11-10", "A")).toEqual({
            cash: 1150,
            transfer: 2000,
            cost: 70000,
            cashReceiptUuids: expect.any(Array),
        });
        expect(tripMoney(q, "u", "2026-11-10", "B").cash).toBe(5000);
        expect(tripMoney(q, "x", "2026-11-10", "A").cash).toBe(0);
    });
});

import { CashDepositSchema } from "../src/domain/cash-deposit";
describe("setor uang", () => {
    const base = {
        deposit_version: 1,
        trip_id: "DO-001",
        business_date: "2026-11-10",
        cash_expected: "5700000",
        cash_deposited: "5700000",
        receipt_uuids: [],
        evidence: {
            id: "44444444-4444-4444-8444-444444444444",
            latitude: 1.4,
            longitude: 124.8,
            accuracy: 5,
            capturedAt: "2026-11-10T01:00:00.000Z",
        },
    };
    it("selisih wajib catatan dan foto bukti wajib", () => {
        expect(CashDepositSchema.safeParse(base).success).toBe(true);
        expect(
            CashDepositSchema.safeParse({ ...base, cash_deposited: "5600000" })
                .success,
        ).toBe(false);
        expect(
            CashDepositSchema.safeParse({
                ...base,
                cash_deposited: "5600000",
                difference_note: "Kurang Rp100.000 untuk BBM",
            }).success,
        ).toBe(true);
        for (const bad of [undefined, true, {}, { id: "x" }])
            expect(
                CashDepositSchema.safeParse({ ...base, evidence: bad }).success,
            ).toBe(false);
    });
});

import { submitPending } from "../src/domain/outlet-expense";
describe("biaya toko retry", () => {
    it("kegagalan pada komponen kedua lalu retry menghasilkan satu entri per komponen", async () => {
        const queued: string[] = [];
        const done = new Set<string>();
        const items = [
            { key: "parkir" },
            { key: "kuli" },
            { key: "retribusi" },
        ];
        let failKuli = true;
        const send = async (i: { key: string }) => {
            if (i.key === "kuli" && failKuli) throw new Error("gagal simpan");
            queued.push(i.key);
        };
        await expect(submitPending(items, done, send)).rejects.toThrow();
        expect(queued).toEqual(["parkir"]);
        failKuli = false;
        await submitPending(items, done, send);
        expect(queued).toEqual(["parkir", "kuli", "retribusi"]);
    });
});
