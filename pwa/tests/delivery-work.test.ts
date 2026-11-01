import { expect, it } from "vitest";
import { MockProvider } from "../src/data/mock";
import {
    deliveryWorkKey,
    restoreDeliveryWork,
    receivedOutcome,
} from "../src/domain/delivery-work";
import { validateExpense } from "../src/domain/expense";
import { approvalRoles } from "../src/domain/settlement";
async function draft() {
    const task = (await new MockProvider("delivery").deliveryTasks())[0];
    return {
        task,
        value: {
            source: task,
            recipient: "PIC",
            outcome: "partial",
            reason: "Notes",
            doReason: "",
            requestedDate: "",
            cancelReason: "Toko Tutup",
            lines: task.lines.map((line) => ({
                id: line.id,
                received: Math.floor(line.quantity / 2),
                reason: "ITEM RUSAK",
                item_reason: "ITEM RUSAK",
            })),
        },
    };
}
it("restores item drafts by SKU identity and rejects a changed manifest/day or excessive quantity", async () => {
    const { task, value } = await draft();
    expect(
        restoreDeliveryWork(
            { ...value, lines: [...value.lines].reverse() },
            task,
        ).lines.map((line) => line.id),
    ).toEqual(task.lines.map((line) => line.id));
    expect(() =>
        restoreDeliveryWork(
            { ...value, source: { ...task, version: "other" } },
            task,
        ),
    ).toThrow();
    expect(() =>
        restoreDeliveryWork(
            {
                ...value,
                lines: value.lines.map((line) => ({
                    ...line,
                    received: 100000,
                })),
            },
            task,
        ),
    ).toThrow();
    expect(deliveryWorkKey(task)).not.toBe(
        deliveryWorkKey({ ...task, business_date: "2027-01-01" }),
    );
});
it("derives complete/partial/rejected from actual received quantities", async () => {
    const { task } = await draft();
    expect(
        receivedOutcome(
            task.lines.map((line) => ({ received: line.quantity })),
            task.lines,
        ),
    ).toBe("delivered");
    expect(
        receivedOutcome(
            task.lines.map(() => ({ received: 0 })),
            task.lines,
        ),
    ).toBe("rejected");
    expect(
        receivedOutcome(
            task.lines.map((line) => ({
                received: Math.floor(line.quantity / 2),
            })),
            task.lines,
        ),
    ).toBe("partial");
});
it("keeps DO and outlet expense scopes separate and preserves existing approval thresholds", () => {
    const base = {
        category: "delivery_fee",
        amount: "50000",
        expense_scope: "outlet",
        outlet_id: "outlet-1",
        trip_id: "trip-1",
        delivery_id: null,
        scheduled_date: "2026-11-01",
        odometer: null,
        reason: "Unloading fee",
        evidence: null,
    };
    expect(validateExpense(base, "2026-11-01").outlet_id).toBe("outlet-1");
    expect(() =>
        validateExpense({ ...base, delivery_id: "DO-1" }, "2026-11-01"),
    ).toThrow();
    expect(() =>
        validateExpense({ ...base, expense_scope: "delivery" }, "2026-11-01"),
    ).toThrow();
    expect(approvalRoles("delivery_fee", 50000, "250000")).toEqual([
        "supervisor",
    ]);
    expect(approvalRoles("delivery_fee", 300000, "250000")).toEqual([
        "supervisor",
        "branch_manager",
    ]);
});

it("atomically prevents duplicate fee requests when two screens submit the same scope", async () => {
    const { FieldStore } = await import("../src/storage/store");
    const { Outbox } = await import("../src/domain/outbox");
    const store = new FieldStore(`fee-race-${crypto.randomUUID()}`);
    try {
        const engine = new Outbox(store, "owner", new MockProvider("delivery"));
        const key = "delivery-fee-v1:trip/day/outlet/request";
        const submit = () => {
            const uuid = crypto.randomUUID();
            return engine.enqueue(
                "field_expense.request",
                { category: "delivery_fee", amount: "50000" },
                "Biaya toko",
                uuid,
                { key, expected: undefined, value: { client_uuid: uuid } },
            );
        };
        const results = await Promise.allSettled([submit(), submit()]);
        expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
        const rows = await store.list("owner");
        expect(rows).toHaveLength(1);
        expect(await store.draft("owner", key)).toEqual({
            client_uuid: rows[0].command.client_uuid,
        });
    } finally {
        await store.close();
    }
});
