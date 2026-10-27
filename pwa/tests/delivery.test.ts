import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { Outbox } from "../src/domain/outbox";
import { validatePod, validatePodMedia } from "../src/domain/delivery";
import { podKey, type DeliveryPod } from "../src/domain/delivery-contracts";
import type { FieldProvider } from "../src/domain/contracts";
import { makeVisitPhoto } from "./visit-fixtures";
let store: FieldStore;
const owner = "demo:driver";
let provider: FieldProvider;
beforeEach(() => {
    store = new FieldStore(`pod-${crypto.randomUUID()}`);
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
async function fixture() {
    const now = new Date().toISOString();
    const evidence = await makeVisitPhoto(store, owner, {
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
        sampled_at: now,
    });
    const p: DeliveryPod = {
        pod_version: 1,
        source: {
            id: "DO1",
            trip: "TRIP1",
            vehicle: "DEMO",
            owner,
            outlet: "Outlet",
            outlet_id: "o1",
            address: "Manado",
            business_date: new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            }),
            version: "v1",
            site: { latitude: 1.465, longitude: 124.833, radius: 15 },
            lines: [{ id: "l1", name: "Produk", quantity: 12, unit: "karton" }],
        },
        recipient: "Budi",
        outcome: "delivered",
        reason: "",
        lines: [{ id: "l1", received: 12 }],
        evidence,
    };
    await store.draft(owner, `delivery-manifest-v1:${p.source.business_date}`, [
        p.source,
    ]);
    return p;
}
async function enqueue(
    p: DeliveryPod,
    engine = new Outbox(store, owner, provider),
    expected?: unknown,
) {
    const uuid = crypto.randomUUID(),
        at = new Date().toISOString();
    return engine.enqueue("delivery.pod.submit", p, "POD", uuid, {
        key: podKey(p.source),
        expected,
        ...(p.supersedes_uuid
            ? {
                  guards: {
                      source: (await store.list(owner)).find(
                          (r) => r.command.client_uuid === p.supersedes_uuid,
                      )!,
                  },
              }
            : {}),
        value: {
            schema_version: 1,
            client_uuid: uuid,
            type: "delivery.pod.submit",
            occurred_at: at,
            payload: p,
        },
        occurredAt: at,
    });
}
it("queues durable bound POD, validates restore and replays next day at event time", async () => {
    const p = await fixture();
    const row = await enqueue(p);
    await validatePodMedia(row, owner, store);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(Date.now() + 86400000);
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).toHaveBeenCalledTimes(1);
    expect((await store.list(owner))[0].state).toBe("needs_approval");
});
it.each([
    "owner",
    "day",
    "qty",
    "line",
    "duplicate",
    "outcome",
    "reason",
    "gps",
    "stale",
    "hash",
])("rejects invalid %s at submit/restore/sync", async (kind) => {
    const p = await fixture();
    switch (kind) {
        case "owner":
            p.source.owner = "other";
            break;
        case "day":
            p.source.business_date = "2020-01-01";
            break;
        case "qty":
            p.lines[0].received = 13;
            break;
        case "line":
            p.lines[0].id = "bad";
            break;
        case "duplicate":
            p.lines.push(p.lines[0]);
            break;
        case "outcome":
            p.outcome = "rejected";
            break;
        case "reason":
            p.outcome = "partial";
            p.lines[0].received = 4;
            break;
        case "gps":
            p.evidence.latitude = 0;
            break;
        case "stale":
            p.evidence.capturedAt = new Date(Date.now() - 61000).toISOString();
            break;
        case "hash":
            p.evidence.packageHash = "0".repeat(64);
            break;
    }
    if (kind === "hash") {
        const row = await enqueue(p);
        await expect(validatePodMedia(row, owner, store)).rejects.toThrow();
        await new Outbox(store, owner, provider).flush();
        expect(provider.submit).not.toHaveBeenCalled();
    } else
        expect(() => validatePod(p, owner, new Date().toISOString())).toThrow();
});
it("supports partial/rejected with consistent quantities and reason", async () => {
    const p = await fixture();
    p.outcome = "partial";
    p.lines[0].received = 4;
    p.reason = "Kemasan rusak";
    expect(validatePod(p, owner, new Date().toISOString()).outcome).toBe(
        "partial",
    );
    p.outcome = "rejected";
    p.lines[0].received = 0;
    expect(validatePod(p, owner, new Date().toISOString()).outcome).toBe(
        "rejected",
    );
});
it("atomic double submission allows only one queue/ledger pair", async () => {
    const p = await fixture();
    const results = await Promise.allSettled([enqueue(p), enqueue(p)]);
    expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    expect(await store.list(owner)).toHaveLength(1);
});
it("cannot reuse photo across different DO/trip", async () => {
    const p = await fixture();
    await enqueue(p);
    const q = structuredClone(p);
    q.source.id = "DO2";
    q.source.trip = "TRIP2";
    await store.draft(owner, `delivery-manifest-v1:${p.source.business_date}`, [
        p.source,
        q.source,
    ]);
    await expect(enqueue(q)).rejects.toThrow("foto");
});
it("blocks direct enqueue and missing manifest without orphan command", async () => {
    const p = await fixture();
    await expect(
        new Outbox(store, owner, provider).enqueue(
            "delivery.pod.submit",
            p,
            "POD",
        ),
    ).rejects.toThrow();
    await store.removeDraft(
        owner,
        `delivery-manifest-v1:${p.source.business_date}`,
    );
    await expect(enqueue(p)).rejects.toThrow("Manifest");
    expect(await store.list(owner)).toHaveLength(0);
});
it.each(["source", "ledger", "photo"])(
    "holds damaged %s on restore and retry, preserving UUID",
    async (kind) => {
        const p = await fixture(),
            row = await enqueue(p);
        if (kind === "source")
            await store.draft(
                owner,
                `delivery-manifest-v1:${p.source.business_date}`,
                [],
            );
        if (kind === "ledger") await store.removeDraft(owner, podKey(p.source));
        if (kind === "photo") {
            const original = store.getEvidence.bind(store);
            vi.spyOn(store, "getEvidence").mockImplementation(async (o, id) => {
                const r = await original(o, id);
                return r
                    ? {
                          ...r,
                          blob: new Blob(["corrupt"], { type: "image/jpeg" }),
                      }
                    : r;
            });
        }
        await expect(validatePodMedia(row, owner, store)).rejects.toThrow();
        const e = new Outbox(store, owner, provider);
        await e.flush();
        await e.retry();
        expect(provider.submit).not.toHaveBeenCalled();
        expect((await store.list(owner))[0].command.client_uuid).toBe(
            row.command.client_uuid,
        );
    },
);
it("rechecks source after asynchronous media read before provider submit", async () => {
    const p = await fixture();
    await enqueue(p);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementationOnce(async (o, id) => {
        const row = await original(o, id);
        await store.draft(
            owner,
            `delivery-manifest-v1:${p.source.business_date}`,
            [],
        );
        return row;
    });
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).not.toHaveBeenCalled();
    expect((await store.list(owner))[0].evidenceHold).toBe(true);
});
it("two database connections cannot reserve the same DO concurrently", async () => {
    await store.close();
    const name = `pod-race-${crypto.randomUUID()}`;
    store = new FieldStore(name);
    const other = new FieldStore(name);
    try {
        const p = await fixture();
        const e = new Outbox(other, owner, provider);
        const results = await Promise.allSettled([enqueue(p), enqueue(p, e)]);
        expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
        expect(await other.list(owner)).toHaveLength(1);
    } finally {
        await other.close();
    }
});
async function rejectedParent() {
    const p = await fixture();
    const row = await enqueue(p);
    row.state = "rejected";
    row.receipt = {
        client_uuid: row.command.client_uuid,
        status: "rejected",
        message: "Perbaiki penerima",
        reference: "SIM-REJ",
    };
    await store.put(row);
    return { p, row };
}
async function correction(
    p: DeliveryPod,
    parent: import("../src/storage/store").QueueItem,
) {
    const next = structuredClone(p);
    next.supersedes_uuid = parent.command.client_uuid;
    next.correction_reason = "Nama penerima diperbaiki";
    next.recipient = "Siti Outlet";
    next.evidence = await makeVisitPhoto(store, owner, {
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
        sampled_at: new Date().toISOString(),
    });
    return next;
}
it("rejected POD correction keeps parent immutable, changes UUID, validates history and syncs review", async () => {
    const { p, row } = await rejectedParent();
    const before = structuredClone(row);
    const next = await correction(p, row);
    const child = await enqueue(next, undefined, row.command);
    expect(child.command.client_uuid).not.toBe(row.command.client_uuid);
    expect((await store.list(owner)).find((r) => r.key === row.key)).toEqual(
        before,
    );
    await validatePodMedia(child, owner, store);
    await validatePodMedia(row, owner, store);
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).toHaveBeenCalledTimes(1);
});
it.each(["queued", "needs_approval", "accepted", "transport", "wrong_uuid"])(
    "does not unlock correction for %s",
    async (kind) => {
        const { p, row } = await rejectedParent();
        if (kind === "transport") delete row.receipt;
        else if (kind === "wrong_uuid")
            row.receipt!.client_uuid = crypto.randomUUID();
        else {
            row.state = kind as typeof row.state;
            row.receipt!.status =
                kind === "queued"
                    ? "rejected"
                    : (kind as "accepted" | "needs_approval");
        }
        await store.put(row);
        const next = await correction(p, row);
        await expect(enqueue(next, undefined, row.command)).rejects.toThrow();
        expect(await store.list(owner)).toHaveLength(1);
    },
);
it("two competing correction submissions allow only one successor", async () => {
    const { p, row } = await rejectedParent();
    const a = await correction(p, row),
        b = await correction(p, row);
    const result = await Promise.allSettled([
        enqueue(a, undefined, row.command),
        enqueue(b, undefined, row.command),
    ]);
    expect(result.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    expect(await store.list(owner)).toHaveLength(2);
});
it.each([
    "parent_missing",
    "receipt_changed",
    "source_changed",
    "cycle",
    "duplicate_photo",
    "missing_reason",
])("blocks invalid correction lineage: %s", async (kind) => {
    const { p, row } = await rejectedParent();
    const next = await correction(p, row);
    if (kind === "parent_missing") next.supersedes_uuid = crypto.randomUUID();
    if (kind === "receipt_changed") {
        row.receipt!.status = "accepted";
        await store.put(row);
    }
    if (kind === "source_changed") next.source.trip = "TRIP-OTHER";
    if (kind === "cycle") next.supersedes_uuid = undefined;
    if (kind === "duplicate_photo") next.evidence = p.evidence;
    if (kind === "missing_reason") delete next.correction_reason;
    await expect(enqueue(next, undefined, row.command)).rejects.toThrow();
    expect(await store.list(owner)).toHaveLength(1);
});
it("parent receipt changed during async media read holds child without erasing history", async () => {
    const { p, row } = await rejectedParent();
    const child = await enqueue(
        await correction(p, row),
        undefined,
        row.command,
    );
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
    await expect(validatePodMedia(child, owner, store)).rejects.toThrow();
});
it("two connections cannot fork a rejected parent", async () => {
    await store.close();
    const name = `pod-revision-race-${crypto.randomUUID()}`;
    store = new FieldStore(name);
    const second = new FieldStore(name);
    try {
        const { p, row } = await rejectedParent();
        const a = await correction(p, row),
            b = await correction(p, row);
        const results = await Promise.allSettled([
            enqueue(a, undefined, row.command),
            enqueue(b, new Outbox(second, owner, provider), row.command),
        ]);
        expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
        expect(await second.list(owner)).toHaveLength(2);
    } finally {
        await second.close();
    }
});
it("receipt snapshot changing before commit rolls back correction", async () => {
    const { p, row } = await rejectedParent(),
        next = await correction(p, row);
    const changed = structuredClone(row);
    changed.receipt!.reference = "NEW-REJECTION";
    await store.put(changed);
    const uuid = crypto.randomUUID(),
        at = new Date().toISOString();
    await expect(
        new Outbox(store, owner, provider).enqueue(
            "delivery.pod.submit",
            next,
            "POD",
            uuid,
            {
                key: podKey(p.source),
                expected: row.command,
                guards: { source: row },
                occurredAt: at,
                value: {
                    schema_version: 1,
                    client_uuid: uuid,
                    type: "delivery.pod.submit",
                    occurred_at: at,
                    payload: next,
                },
            },
        ),
    ).rejects.toThrow("Parent/receipt");
    expect(await store.list(owner)).toHaveLength(1);
});
it("multi-level correction validates rejected ancestors; damaged root media holds latest child", async () => {
    const { p, row } = await rejectedParent();
    const child = await enqueue(
        await correction(p, row),
        undefined,
        row.command,
    );
    child.state = "rejected";
    child.receipt = {
        client_uuid: child.command.client_uuid,
        status: "rejected",
        reference: "SIM-REJ2",
        message: "Perbaiki",
    };
    await store.put(child);
    const latest = await enqueue(
        await correction(p, child),
        undefined,
        child.command,
    );
    await validatePodMedia(latest, owner, store);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementation(async (o, id) => {
        const media = await original(o, id);
        return media && id === p.evidence.id
            ? { ...media, blob: new Blob(["broken"], { type: "image/jpeg" }) }
            : media;
    });
    await new Outbox(store, owner, provider).flush();
    expect(provider.submit).not.toHaveBeenCalled();
    expect(await store.list(owner)).toHaveLength(3);
});
it.each(["cycle", "missing_parent", "source", "dropped_reference"])(
    "persisted lineage damage %s cannot bypass sync",
    async (kind) => {
        const { p, row } = await rejectedParent();
        const child = await enqueue(
            await correction(p, row),
            undefined,
            row.command,
        );
        if (
            child.command.type !== "delivery.pod.submit" ||
            row.command.type !== "delivery.pod.submit"
        )
            throw new Error("fixture");
        if (kind === "cycle") {
            row.command.payload.supersedes_uuid = child.command.client_uuid;
            row.command.payload.correction_reason = "Cycle invalid";
            await store.put(row);
        }
        if (kind === "missing_parent")
            child.command.payload.supersedes_uuid = crypto.randomUUID();
        if (kind === "source") child.command.payload.source.trip = "CHANGED";
        if (kind === "dropped_reference") {
            delete child.command.payload.supersedes_uuid;
            delete child.command.payload.correction_reason;
        }
        await store.put(child);
        await expect(validatePodMedia(child, owner, store)).rejects.toThrow();
        await new Outbox(store, owner, provider).flush();
        expect(provider.submit).not.toHaveBeenCalled();
        expect(await store.list(owner)).toHaveLength(2);
    },
);
