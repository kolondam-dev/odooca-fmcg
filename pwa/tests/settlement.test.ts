import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { MockProvider } from "../src/data/mock";
import { Outbox } from "../src/domain/outbox";
import { CommandSchema, ownerKey } from "../src/domain/contracts";
import {
    advanceKey,
    ExpenseSimulation,
    approvalRoles,
    settlementPreview,
    validateAdvance,
    validateRealization,
} from "../src/domain/settlement";
import type { ExpenseRequest } from "../src/domain/expense";
import type {
    ExpenseRealization,
    LocalExpenseEvidenceSchema,
} from "../src/domain/settlement-contracts";
import type { z } from "zod";
let store: FieldStore;
let dbName: string;
beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
    vi.stubGlobal("navigator", { onLine: true });
    dbName = crypto.randomUUID();
    store = new FieldStore(dbName);
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
async function setup(
    category: ExpenseRequest["category"] = "meal",
    amount = "200000",
) {
    const provider = new MockProvider("sales"),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity),
        outbox = new Outbox(store, owner, provider);
    const request: ExpenseRequest = {
        category,
        amount,
        expense_scope: "trip",
        trip_id: "TRIP-01",
        delivery_id: null,
        scheduled_date: "2026-10-28",
        odometer: category.startsWith("fuel") ? 1000 : null,
        reason: "Demo luar kota",
        evidence: null,
    };
    const item = await outbox.enqueue(
        "field_expense.request",
        request,
        "Advance request",
    );
    await outbox.flush();
    const source = (await store.list(owner)).find((q) => q.key === item.key)!;
    const service = new ExpenseSimulation(store, identity, provider, outbox);
    return {
        provider,
        identity,
        owner,
        outbox,
        request,
        source,
        service,
        uuid: item.command.client_uuid,
    };
}
async function evidence(
    owner: string,
): Promise<z.infer<typeof LocalExpenseEvidenceSchema>> {
    const ref = {
        id: crypto.randomUUID(),
        latitude: 1.46,
        longitude: 124.83,
        accuracy: 5,
        capturedAt: new Date().toISOString(),
    };
    await store.saveEvidence({
        key: `${owner}:${ref.id}`,
        owner,
        blob: new Blob([crypto.randomUUID()], { type: "image/jpeg" }),
        latitude: ref.latitude,
        longitude: ref.longitude,
        accuracy: ref.accuracy,
        capturedAt: ref.capturedAt,
        mapStatus: "pending",
    });
    return ref;
}
async function ready(
    category: ExpenseRequest["category"] = "meal",
    amount = "200000",
) {
    const ctx = await setup(category, amount),
        advance = await ctx.service.simulateDisbursement(ctx.uuid);
    const body: ExpenseRealization = {
        source_request_uuid: ctx.uuid,
        advance_reference: advance.reference,
        evidence_status: "local_map_pending",
        lines: [
            {
                description: "Realisasi",
                amount: "150000",
                merchant: "Toko contoh",
                receipt_number: "R-001",
                expense_date: "2026-10-27",
                evidence: await evidence(ctx.owner),
            },
        ],
        fuel: null,
    };
    if (category.startsWith("fuel"))
        body.fuel = {
            liters: "15",
            price_per_liter: "10000",
            odometer_before: 1000,
            odometer_after: 1001,
            before: await evidence(ctx.owner),
            after: await evidence(ctx.owner),
        };
    return { ...ctx, advance, body };
}
it("uses cumulative tiers and total exposure; emergency fuel always requires Supervisor + BM", async () => {
    expect(approvalRoles("meal", 250000, "250000")).toEqual(["supervisor"]);
    expect(approvalRoles("repair", 250001, "250000")).toEqual([
        "supervisor",
        "branch_manager",
    ]);
    expect(approvalRoles("fuel_emergency", 1, "250000")).toEqual([
        "supervisor",
        "branch_manager",
    ]);
    const c = await ready();
    expect(settlementPreview(c.request, c.advance, c.body)).toMatchObject({
        total: 150000,
        refund: 50000,
        variance: 0,
    });
    const over = {
        ...c.body,
        lines: [{ ...c.body.lines[0], amount: "300000" }],
    };
    expect(settlementPreview(c.request, c.advance, over)).toMatchObject({
        total: 300000,
        refund: 0,
        variance: 100000,
        approvals: ["supervisor", "branch_manager"],
    });
});
it("separates request receipt from simulated cash and blocks offline/expired/live disbursement", async () => {
    const c = await setup();
    expect(c.source.state).toBe("needs_approval");
    expect(await c.service.load(c.uuid)).toBeUndefined();
    vi.stubGlobal("navigator", { onLine: false });
    await expect(c.service.simulateDisbursement(c.uuid)).rejects.toThrow(
        "online",
    );
    vi.stubGlobal("navigator", { onLine: true });
    c.provider.scenario = "expired";
    await expect(c.service.simulateDisbursement(c.uuid)).rejects.toThrow(
        "Normal",
    );
    c.provider.scenario = "normal";
    const a = await c.service.simulateDisbursement(c.uuid);
    expect(await c.service.simulateDisbursement(c.uuid)).toEqual(a);
    const live = {
        ...c.provider,
        mode: "live" as const,
        bootstrap: c.provider.bootstrap.bind(c.provider),
        snapshot: c.provider.snapshot.bind(c.provider),
        submit: c.provider.submit.bind(c.provider),
    };
    await expect(
        new ExpenseSimulation(store, c.identity, live, c.outbox).submit(
            c.uuid,
            {},
        ),
    ).rejects.toThrow("resmi");
});
it("persists offline realization and linkage atomically, then retries same UUID without marking settlement paid", async () => {
    const c = await ready("fuel_emergency");
    vi.stubGlobal("navigator", { onLine: false });
    const item = await c.service.submit(c.uuid, c.body);
    expect(item.state).toBe("queued");
    expect((await c.service.load(c.uuid))?.realization_uuid).toBe(
        item.command.client_uuid,
    );
    await expect(c.service.submit(c.uuid, c.body)).rejects.toThrow(
        "sudah diantrekan",
    );
    const second = new FieldStore(dbName);
    expect(
        (await second.list(c.owner)).filter(
            (q) => q.command.type === "field_expense.realization.submit",
        ),
    ).toHaveLength(1);
    await second.close();
    await c.outbox.flush();
    vi.stubGlobal("navigator", { onLine: true });
    await c.outbox.retry();
    const result = (await store.list(c.owner)).find((q) => q.key === item.key)!;
    expect(result.state).toBe("needs_approval");
    expect(result.command.client_uuid).toBe(item.command.client_uuid);
});
it("rejects missing photos, forged metadata, reused evidence IDs, invalid KM and liters × price mismatch", async () => {
    const c = await ready("fuel_planned");
    await expect(
        c.service.submit(c.uuid, {
            ...c.body,
            lines: [
                {
                    ...c.body.lines[0],
                    evidence: {
                        ...c.body.lines[0].evidence,
                        id: crypto.randomUUID(),
                    },
                },
            ],
        }),
    ).rejects.toThrow("Foto lokal");
    await expect(
        c.service.submit(c.uuid, {
            ...c.body,
            lines: [
                {
                    ...c.body.lines[0],
                    evidence: { ...c.body.lines[0].evidence, latitude: 2 },
                },
            ],
        }),
    ).rejects.toThrow("metadata");
    for (const fuel of [
        { ...c.body.fuel!, odometer_before: 999 },
        { ...c.body.fuel!, odometer_after: 999 },
        { ...c.body.fuel!, liters: "0" },
        { ...c.body.fuel!, liters: "14" },
        { ...c.body.fuel!, before: c.body.lines[0].evidence },
    ])
        expect(() =>
            validateRealization(
                { ...c.body, fuel },
                c.source,
                c.advance,
                c.owner,
            ),
        ).toThrow();
    expect(() =>
        validateRealization(
            { ...c.body, fuel: null },
            c.source,
            c.advance,
            c.owner,
        ),
    ).toThrow("BBM");
    expect(() =>
        validateRealization(
            { ...c.body, lines: [{ ...c.body.lines[0], evidence: undefined }] },
            c.source,
            c.advance,
            c.owner,
        ),
    ).toThrow("Lengkapi");
});
it("computes fractional liters with integer milliliters and rupiah rounding", async () => {
    const c = await ready("fuel_emergency");
    const b = {
        ...c.body,
        lines: [{ ...c.body.lines[0], amount: "10001" }],
        fuel: { ...c.body.fuel!, liters: "1.001", price_per_liter: "9991" },
    };
    expect(
        validateRealization(b, c.source, c.advance, c.owner).lines[0].amount,
    ).toBe("10001");
});
it("invalidates altered approved requests and corrupted restored advance data, preserving pending commands", async () => {
    const c = await ready();
    const before = await store.list(c.owner);
    for (const corrupt of [
        { ...c.advance, amount: "1" },
        { ...c.advance, owner: "other" },
        { ...c.advance, approvals: [] },
        { ...c.advance, disbursed_at: "2030-01-01T00:00:00Z" },
        { ...c.advance, realization_uuid: crypto.randomUUID() },
    ]) {
        await store.draft(c.owner, advanceKey(c.uuid), corrupt);
        await expect(c.service.load(c.uuid)).rejects.toThrow();
        expect(await store.list(c.owner)).toEqual(before);
    }
    expect(() =>
        validateAdvance(
            c.advance,
            {
                ...c.source,
                command: {
                    ...c.source.command,
                    type: "field_expense.request",
                    payload: { ...c.request, amount: "200001" },
                },
            },
            c.owner,
        ),
    ).toThrow("Review ulang");
});
it("prevents same-advance double submission across independent connections with compare-and-set", async () => {
    const c = await ready();
    const second = new FieldStore(dbName);
    const service2 = new ExpenseSimulation(
        second,
        c.identity,
        c.provider,
        new Outbox(second, c.owner, c.provider),
    );
    // Hold both callers after reading the unconsumed advance, so the DB CAS
    // rather than an earlier readiness check must reject one write.
    let waiting = 0;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
        release = resolve;
    });
    for (const db of [store, second]) {
        const original = db.listEvidence.bind(db);
        vi.spyOn(db, "listEvidence").mockImplementation(async (owner) => {
            const rows = await original(owner);
            if (++waiting === 2) release();
            await gate;
            return rows;
        });
    }
    const results = await Promise.allSettled([
        c.service.submit(c.uuid, c.body),
        service2.submit(c.uuid, c.body),
    ]);
    expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    expect(
        (await store.list(c.owner)).filter(
            (q) => q.command.type === "field_expense.realization.submit",
        ),
    ).toHaveLength(1);
    await second.close();
});
it("quota failure does not create an orphan command or consume the advance", async () => {
    const c = await ready();
    vi.spyOn(store, "putWithDraft").mockRejectedValueOnce(new Error("quota"));
    await expect(c.service.submit(c.uuid, c.body)).rejects.toThrow("quota");
    expect((await c.service.load(c.uuid))?.realization_uuid).toBeNull();
    expect(
        (await store.list(c.owner)).filter(
            (q) => q.command.type === "field_expense.realization.submit",
        ),
    ).toHaveLength(0);
});
it("denies other personas, duplicate receipt components and stale/future receipt dates", async () => {
    const c = await ready();
    const other = new MockProvider("canvass"),
        id = await other.bootstrap();
    await expect(
        new ExpenseSimulation(
            store,
            id,
            other,
            new Outbox(store, ownerKey(id), other),
        ).load(c.uuid),
    ).rejects.toThrow("akun ini");
    expect(() =>
        validateRealization(
            { ...c.body, lines: [c.body.lines[0], c.body.lines[0]] },
            c.source,
            c.advance,
            c.owner,
        ),
    ).toThrow("dua kali");
    for (const expense_date of ["2020-01-01", "2030-01-01"])
        expect(() =>
            validateRealization(
                { ...c.body, lines: [{ ...c.body.lines[0], expense_date }] },
                c.source,
                c.advance,
                c.owner,
            ),
        ).toThrow("Tanggal struk");
});

it("rolls back ledger changes if the queue insertion aborts", async () => {
    const c = await ready();
    const before = await store.list(c.owner);
    await expect(
        store.putWithDraft(
            c.source,
            advanceKey(c.uuid),
            { ...c.advance, realization_uuid: crypto.randomUUID() },
            c.advance,
        ),
    ).rejects.toThrow();
    expect(await store.list(c.owner)).toEqual(before);
    expect(await c.service.load(c.uuid)).toEqual(c.advance);
});
it("rejects reusing a merchant/date/receipt across sequential realizations", async () => {
    const first = await ready();
    await first.service.submit(first.uuid, first.body);
    const second = await ready();
    await expect(
        second.service.submit(second.uuid, second.body),
    ).rejects.toThrow("Struk sudah dipakai");
});

it("enforces the realization payload on the shared command envelope, without a generic fallback", async () => {
    const c = await ready();
    const envelope = {
        schema_version: 1,
        client_uuid: crypto.randomUUID(),
        occurred_at: new Date().toISOString(),
        type: "field_expense.realization.submit",
    };
    expect(
        CommandSchema.safeParse({ ...envelope, payload: c.body }).success,
    ).toBe(true);
    expect(CommandSchema.safeParse({ ...envelope, payload: {} }).success).toBe(
        false,
    );
    expect(
        CommandSchema.safeParse({
            ...envelope,
            payload: { ...c.body, approved: true },
        }).success,
    ).toBe(false);
});
