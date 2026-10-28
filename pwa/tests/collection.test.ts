import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { Outbox } from "../src/domain/outbox";
import {
    validateCollection,
    validateCollectionMedia,
} from "../src/domain/collection";
import {
    collectionKey,
    collectionSourceKey,
    type CollectionReceipt,
} from "../src/domain/collection-contracts";
import type { FieldProvider } from "../src/domain/contracts";
import { makeVisitPhoto } from "./visit-fixtures";
let store: FieldStore;
const owner = "demo:collector";
let provider: FieldProvider;
beforeEach(() => {
    store = new FieldStore(`collection-${crypto.randomUUID()}`);
    provider = {
        mode: "demo",
        bootstrap: vi.fn(),
        snapshot: vi.fn(),
        submit: vi.fn(async (c) => ({
            client_uuid: c.client_uuid,
            status: "needs_approval" as const,
            reference: "SIM",
            message: "Review",
        })),
    };
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
});
async function fixture(): Promise<CollectionReceipt> {
    const issued = new Date().toISOString(),
        evidence = await makeVisitPhoto(store, owner, {
            latitude: 1.465,
            longitude: 124.833,
            accuracy: 3,
            sampled_at: issued,
        });
    const p: CollectionReceipt = {
        collection_version: 1,
        source: {
            delivery: {
                id: "DO1",
                trip: "TRIP1",
                vehicle: "DEMO",
                outlet: "Outlet",
                outlet_id: "o1",
                address: "Manado",
                owner,
                business_date: new Date().toLocaleDateString("en-CA", {
                    timeZone: "Asia/Makassar",
                }),
                version: "v1",
                site: { latitude: 1.465, longitude: 124.833, radius: 15 },
                lines: [
                    { id: "l1", name: "Produk", quantity: 12, unit: "karton" },
                ],
            },
            receivable_reference: "INV-1",
            amount_due: "1000000",
            currency: "IDR",
            version: "cv1",
            issued_at: issued,
            capture_allowed: true,
        },
        payer: "Budi",
        method: "cash",
        amount: "500000",
        receipt_number: "KW-001",
        notes: "",
        evidence,
    };
    await store.draft(owner, collectionSourceKey(p.source), [p.source]);
    return p;
}
async function enqueue(
    p: CollectionReceipt,
    e = new Outbox(store, owner, provider),
    parent?: import("../src/storage/store").QueueItem,
) {
    const uuid = crypto.randomUUID(),
        at = new Date().toISOString();
    return e.enqueue("collection.receipt.submit", p, "Collection", uuid, {
        key: collectionKey(p.source),
        expected: parent?.command,
        ...(parent ? { guards: { source: parent } } : {}),
        occurredAt: at,
        value: {
            schema_version: 1,
            client_uuid: uuid,
            type: "collection.receipt.submit",
            occurred_at: at,
            payload: p,
        },
    });
}
it("cash record is durable, read-only source, review-only and valid next-day replay", async () => {
    const p = await fixture(),
        row = await enqueue(p);
    await validateCollectionMedia(row, owner, store);
    p.amount = "1";
    const stored = (await store.list(owner))[0].command;
    if (stored.type !== "collection.receipt.submit") throw new Error("fixture");
    expect(stored.payload.amount).toBe("500000");
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.now() + 86400000);
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).toHaveBeenCalledTimes(1);
    expect((await store.list(owner))[0].state).toBe("needs_approval");
});
it("transfer requires a reference and accepts exact due without float conversion", async () => {
    const p = await fixture();
    p.method = "transfer";
    expect(() =>
        validateCollection(p, owner, new Date().toISOString()),
    ).toThrow();
    p.transfer_reference = "BANK-001";
    p.amount = p.source.amount_due;
    expect(validateCollection(p, owner, new Date().toISOString()).amount).toBe(
        "1000000",
    );
    await enqueue(p);
});
it.each(["0", "-1", "0.1", "1e6", "01", "1000001", "9999999999999", "NaN"])(
    "rejects invalid or excessive amount %s",
    async (amount) => {
        const p = await fixture();
        p.amount = amount;
        expect(() =>
            validateCollection(p, owner, new Date().toISOString()),
        ).toThrow();
    },
);
it.each([
    "owner",
    "date",
    "capability",
    "gps",
    "stale",
    "issued",
    "future_issued",
    "missing_photo",
    "cash_ref",
])("rejects invalid %s", async (kind) => {
    const p = await fixture();
    switch (kind) {
        case "owner":
            p.source.delivery.owner = "other";
            break;
        case "date":
            p.source.delivery.business_date = "2020-01-01";
            break;
        case "capability":
            (p.source as any).capture_allowed = false;
            break;
        case "gps":
            p.evidence.latitude = 0;
            break;
        case "stale":
            p.evidence.capturedAt = new Date(Date.now() - 61000).toISOString();
            break;
        case "issued":
            p.source.issued_at = new Date(
                Date.parse(p.evidence.capturedAt) + 1000,
            ).toISOString();
            break;
        case "future_issued":
            p.source.issued_at = new Date(Date.now() + 10000).toISOString();
            break;
        case "missing_photo":
            (p as any).evidence = undefined;
            break;
        case "cash_ref":
            p.transfer_reference = "BANK1";
            break;
    }
    expect(() =>
        validateCollection(p, owner, new Date().toISOString()),
    ).toThrow();
});
it("two connections cannot record one receivable twice", async () => {
    await store.close();
    const name = `collection-race-${crypto.randomUUID()}`;
    store = new FieldStore(name);
    const second = new FieldStore(name);
    try {
        const p = await fixture();
        const result = await Promise.allSettled([
            enqueue(p),
            enqueue(p, new Outbox(second, owner, provider)),
        ]);
        expect(result.filter((r) => r.status === "fulfilled")).toHaveLength(1);
        expect(await second.list(owner)).toHaveLength(1);
    } finally {
        await second.close();
    }
});
it.each(["receipt", "transfer", "photo", "receivable"])(
    "deduplicates %s across assignments atomically",
    async (kind) => {
        const p = await fixture();
        p.method = "transfer";
        p.transfer_reference = "BANK-001";
        await enqueue(p);
        const q = await fixture();
        q.source.receivable_reference = "INV-2";
        q.source.delivery.id = "DO2";
        q.receipt_number = "KW-002";
        q.method = "transfer";
        q.transfer_reference = "BANK-002";
        if (kind === "receipt") q.receipt_number = "kw / 001";
        if (kind === "transfer") q.transfer_reference = "bank / 001";
        if (kind === "photo") q.evidence = p.evidence;
        if (kind === "receivable") q.source.receivable_reference = "inv / 1";
        await store.draft(owner, collectionSourceKey(q.source), [
            p.source,
            q.source,
        ]);
        await expect(enqueue(q)).rejects.toThrow();
        expect(await store.list(owner)).toHaveLength(1);
    },
);
it.each(["source", "ledger", "queue", "photo"])(
    "corrupt %s blocks restore, flush and retry without losing UUID",
    async (kind) => {
        const p = await fixture(),
            row = await enqueue(p);
        if (kind === "source")
            await store.draft(owner, collectionSourceKey(p.source), []);
        if (kind === "ledger")
            await store.removeDraft(owner, collectionKey(p.source));
        if (kind === "queue") {
            if (row.command.type !== "collection.receipt.submit")
                throw new Error("fixture");
            row.command.payload.amount = "999999999";
            await store.put(row);
        }
        if (kind === "photo") {
            const original = store.getEvidence.bind(store);
            vi.spyOn(store, "getEvidence").mockImplementation(async (o, id) => {
                const r = await original(o, id);
                return r
                    ? { ...r, blob: new Blob(["bad"], { type: "image/jpeg" }) }
                    : r;
            });
        }
        await expect(
            validateCollectionMedia(row, owner, store),
        ).rejects.toThrow();
        const e = new Outbox(store, owner, provider);
        await e.flush();
        await e.retry();
        expect(provider.submit).not.toHaveBeenCalled();
        expect((await store.list(owner))[0].command.client_uuid).toBe(
            row.command.client_uuid,
        );
    },
);
it("source changes during media hashing hold sync", async () => {
    const p = await fixture();
    await enqueue(p);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementationOnce(async (o, id) => {
        const r = await original(o, id);
        await store.draft(owner, collectionSourceKey(p.source), []);
        return r;
    });
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).not.toHaveBeenCalled();
});
it("direct enqueue without transaction or changed source cannot create orphan", async () => {
    const p = await fixture();
    await expect(
        new Outbox(store, owner, provider).enqueue(
            "collection.receipt.submit",
            p,
            "Bad",
        ),
    ).rejects.toThrow();
    p.source.amount_due = "999999";
    await expect(enqueue(p)).rejects.toThrow();
    expect(await store.list(owner)).toHaveLength(0);
});
it("issued snapshot must belong to the assignment business day", async () => {
    const p = await fixture();
    p.source.issued_at = new Date(
        Date.parse(p.source.issued_at) - 86400000,
    ).toISOString();
    expect(() =>
        validateCollection(p, owner, new Date().toISOString()),
    ).toThrow();
});
it("two different invoices cannot concurrently reserve the same transfer reference", async () => {
    await store.close();
    const name = `collection-ref-race-${crypto.randomUUID()}`;
    store = new FieldStore(name);
    const other = new FieldStore(name);
    try {
        const a = await fixture(),
            b = await fixture();
        a.method = "transfer";
        a.transfer_reference = "BANK-XYZ";
        b.method = "transfer";
        b.transfer_reference = "bank / xyz";
        b.source.receivable_reference = "INV-2";
        b.source.delivery.id = "DO2";
        b.receipt_number = "KW-002";
        await store.draft(owner, collectionSourceKey(a.source), [
            a.source,
            b.source,
        ]);
        const result = await Promise.allSettled([
            enqueue(a),
            enqueue(b, new Outbox(other, owner, provider)),
        ]);
        expect(result.filter((r) => r.status === "fulfilled")).toHaveLength(1);
        expect(await other.list(owner)).toHaveLength(1);
    } finally {
        await other.close();
    }
});
it("reference reservation survives transport or business rejection", async () => {
    const p = await fixture(),
        row = await enqueue(p);
    row.state = "rejected";
    await store.put(row);
    const q = await fixture();
    q.source.receivable_reference = "INV-2";
    q.receipt_number = "kw / 001";
    await store.draft(owner, collectionSourceKey(q.source), [
        p.source,
        q.source,
    ]);
    await expect(enqueue(q)).rejects.toThrow();
    row.receipt = {
        client_uuid: row.command.client_uuid,
        status: "rejected",
        reference: "SIM-REJ",
        message: "Perlu review",
    };
    await store.put(row);
    await expect(enqueue(q)).rejects.toThrow();
    expect(await store.list(owner)).toHaveLength(1);
});
async function rejected() {
    const p = await fixture(),
        row = await enqueue(p);
    row.state = "rejected";
    row.receipt = {
        client_uuid: row.command.client_uuid,
        status: "rejected",
        reference: "REJ",
        message: "Perbaiki",
    };
    await store.put(row);
    return { p, row };
}
async function revised(
    p: CollectionReceipt,
    parent: import("../src/storage/store").QueueItem,
) {
    return {
        ...p,
        payer: "Siti",
        supersedes_uuid: parent.command.client_uuid,
        correction_reason: "Pembayar diperbaiki",
        evidence: await makeVisitPhoto(store, owner, {
            latitude: 1.465,
            longitude: 124.833,
            accuracy: 3,
            sampled_at: new Date().toISOString(),
        }),
    };
}
it("correction preserves parent and reuses receipt within lineage, then syncs only child", async () => {
    const { p, row } = await rejected(),
        before = structuredClone(row);
    const child = await enqueue(await revised(p, row), undefined, row);
    await validateCollectionMedia(child, owner, store);
    await validateCollectionMedia(row, owner, store);
    expect((await store.list(owner)).find((r) => r.key === row.key)).toEqual(
        before,
    );
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).toHaveBeenCalledTimes(1);
});
it.each(["queued", "needs_approval", "accepted", "transport", "wrong_uuid"])(
    "does not open correction for %s",
    async (kind) => {
        const { p, row } = await rejected();
        if (kind === "transport") delete row.receipt;
        else if (kind === "wrong_uuid")
            row.receipt!.client_uuid = crypto.randomUUID();
        else row.state = kind as typeof row.state;
        await store.put(row);
        await expect(
            enqueue(await revised(p, row), undefined, row),
        ).rejects.toThrow();
        expect(await store.list(owner)).toHaveLength(1);
    },
);
it("two connections cannot fork rejected collection", async () => {
    await store.close();
    const name = `correction-${crypto.randomUUID()}`;
    store = new FieldStore(name);
    const other = new FieldStore(name);
    try {
        const { p, row } = await rejected();
        const a = await revised(p, row),
            b = await revised(p, row);
        const result = await Promise.allSettled([
            enqueue(a, undefined, row),
            enqueue(b, new Outbox(other, owner, provider), row),
        ]);
        expect(result.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    } finally {
        await other.close();
    }
});
it("changed receipt snapshot rolls back correction", async () => {
    const { p, row } = await rejected();
    const next = await revised(p, row),
        changed = structuredClone(row);
    changed.receipt!.reference = "NEW";
    await store.put(changed);
    await expect(enqueue(next, undefined, row)).rejects.toThrow();
    expect(await store.list(owner)).toHaveLength(1);
});
it("ancestor receipt number remains reserved after corrected receipt number changes", async () => {
    const { p, row } = await rejected(),
        next = await revised(p, row);
    next.receipt_number = "KW-NEW";
    await enqueue(next, undefined, row);
    const q = await fixture();
    q.source.receivable_reference = "INV-OTHER";
    await store.draft(owner, collectionSourceKey(p.source), [
        p.source,
        q.source,
    ]);
    await expect(enqueue(q)).rejects.toThrow();
});
it.each(["cycle", "missing_parent", "source", "photo_reuse", "missing_reason"])(
    "rejects corrupt correction %s",
    async (kind) => {
        const { p, row } = await rejected(),
            next = await revised(p, row);
        if (kind === "cycle") next.supersedes_uuid = crypto.randomUUID();
        if (kind === "missing_parent")
            next.supersedes_uuid = crypto.randomUUID();
        if (kind === "source")
            next.source = { ...next.source, amount_due: "900000" };
        if (kind === "photo_reuse") next.evidence = p.evidence;
        if (kind === "missing_reason") next.correction_reason = "";
        await expect(enqueue(next, undefined, row)).rejects.toThrow();
    },
);
it("parent receipt mutation during media read blocks child sync and retains both rows", async () => {
    const { p, row } = await rejected();
    const child = await enqueue(await revised(p, row), undefined, row);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementationOnce(async (o, id) => {
        const media = await original(o, id);
        row.receipt!.status = "accepted";
        await store.put(row);
        return media;
    });
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).not.toHaveBeenCalled();
    expect(await store.list(owner)).toHaveLength(2);
    await expect(
        validateCollectionMedia(child, owner, store),
    ).rejects.toThrow();
});
it("multi-level corrections validate root media and hold sync when root is damaged", async () => {
    const { p, row } = await rejected();
    const child = await enqueue(await revised(p, row), undefined, row);
    child.state = "rejected";
    child.receipt = {
        client_uuid: child.command.client_uuid,
        status: "rejected",
        reference: "REJ2",
        message: "Review",
    };
    await store.put(child);
    const latest = await enqueue(await revised(p, child), undefined, child);
    await validateCollectionMedia(latest, owner, store);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementation(async (o, id) => {
        const media = await original(o, id);
        return media && id === p.evidence.id
            ? { ...media, blob: new Blob(["bad"], { type: "image/jpeg" }) }
            : media;
    });
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).not.toHaveBeenCalled();
    expect(await store.list(owner)).toHaveLength(3);
});
it.each(["cycle", "missing_parent", "dropped_reference"])(
    "persisted %s cannot bypass restore or flush",
    async (kind) => {
        const { p, row } = await rejected();
        const child = await enqueue(await revised(p, row), undefined, row);
        if (
            child.command.type !== "collection.receipt.submit" ||
            row.command.type !== "collection.receipt.submit"
        )
            throw new Error("fixture");
        if (kind === "cycle") {
            row.command.payload.supersedes_uuid = child.command.client_uuid;
            row.command.payload.correction_reason = "Cycle";
            await store.put(row);
        }
        if (kind === "missing_parent")
            child.command.payload.supersedes_uuid = crypto.randomUUID();
        if (kind === "dropped_reference") {
            delete child.command.payload.supersedes_uuid;
            delete child.command.payload.correction_reason;
        }
        await store.put(child);
        await expect(
            validateCollectionMedia(child, owner, store),
        ).rejects.toThrow();
        await new Outbox(store, owner, provider).flush();
        expect(provider.submit).not.toHaveBeenCalled();
    },
);
