import { describe, expect, it } from "vitest";
import { orderSummary } from "../src/components/CloseVisitScreen";
import {
    fieldExpenseV2Enabled,
    needsRequestOdometer,
} from "../src/domain/expense";
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
});
