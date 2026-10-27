import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { FieldStore, type QueueItem } from "../src/storage/store";
import {
    diagnoseSync,
    type SyncSnapshot,
} from "../src/domain/sync-diagnostics";
import { Outbox } from "../src/domain/outbox";
import { MockProvider } from "../src/data/mock";
import { ownerKey } from "../src/domain/contracts";
import { MorningSimulation } from "../src/domain/morning";
import { SalesVisits } from "../src/domain/visits";
import { VISITS_KEY } from "../src/domain/visit-validation";
let store: FieldStore;
beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
    vi.stubGlobal("navigator", { onLine: true });
    store = new FieldStore(crypto.randomUUID());
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
function row(state: QueueItem["state"] = "queued"): QueueItem {
    const id = crypto.randomUUID();
    return {
        key: `owner:${id}`,
        owner: "owner",
        label: "Pengajuan simulasi",
        state,
        attempts: 0,
        nextAttempt: 0,
        command: {
            schema_version: 1,
            client_uuid: id,
            type: "field_expense.request",
            occurred_at: new Date().toISOString(),
            payload: {
                private_note: "not for diagnostics",
                photo: "private-photo",
                token: "secret-token",
            },
        },
    };
}
function snapshot(item: QueueItem): SyncSnapshot {
    return { rows: [item], ledger: undefined, morning: undefined };
}
it("distinguishes offline, backoff, sending and auth without claiming approval or recovery", () => {
    const item = row(),
        s = snapshot(item);
    expect(diagnoseSync(s, "owner", false)[0].code).toBe("offline");
    expect(diagnoseSync(s, "owner", true)[0].code).toBe("ready");
    item.nextAttempt = Date.now() + 30000;
    expect(diagnoseSync(s, "owner", true)[0].code).toBe("backoff");
    item.state = "sending";
    expect(diagnoseSync(s, "owner", true)[0].code).toBe("sending");
    item.state = "auth_required";
    const d = diagnoseSync(s, "owner", true)[0];
    expect(d.group).toBe("review");
    expect(d.guidance).toContain("tidak memulihkan sesi yang habis");
});
it.each(["accepted", "needs_approval", "rejected"] as const)(
    "requires matching business receipt for %s",
    (state) => {
        const item = row(state);
        item.receipt = {
            client_uuid: item.command.client_uuid,
            status: state,
            message: "simulator",
            reference: "SIM-1",
        };
        expect(diagnoseSync(snapshot(item), "owner", true)[0].code).toBe(
            state === "accepted"
                ? "accepted"
                : state === "needs_approval"
                  ? "approval"
                  : "business_rejected",
        );
        item.receipt.client_uuid = crypto.randomUUID();
        const invalid = diagnoseSync(snapshot(item), "owner", true)[0];
        expect(invalid.code).toBe("integrity");
        expect(invalid.reference).toBeUndefined();
        expect(invalid.message).not.toBe("simulator");
        delete item.receipt;
        expect(diagnoseSync(snapshot(item), "owner", true)[0].code).toBe(
            state === "rejected" ? "transport_rejected" : "integrity",
        );
    },
);
it("projects a bounded allowlist without mutating data or exposing raw payload/evidence/secrets", () => {
    const item = row(),
        s = snapshot(item);
    item.label = "x".repeat(1000);
    const before = JSON.stringify(s);
    const d = diagnoseSync(s, "owner", true);
    expect(JSON.stringify(s)).toBe(before);
    expect(d[0].label).toHaveLength(160);
    expect(JSON.stringify(d)).not.toMatch(
        /private_note|private-photo|secret-token/,
    );
    expect(
        diagnoseSync(
            {
                ...s,
                rows: [
                    item,
                    { ...item, owner: "other", label: "private account" },
                ],
            },
            "owner",
            true,
        ),
    ).toHaveLength(1);
});
it("malformed command, timestamp, state or retry metadata becomes review data without a render exception", () => {
    const item = row();
    const variants = [
        { ...item, command: null },
        { ...item, command: { ...item.command, occurred_at: "bad" } },
        { ...item, state: "unknown" },
        { ...item, attempts: -1 },
        { ...item, nextAttempt: NaN },
        { ...item, key: "wrong" },
    ];
    for (const broken of variants) {
        const d = diagnoseSync(snapshot(broken as QueueItem), "owner", true)[0];
        expect(d.code).toBe("integrity");
        expect(d.group).toBe("review");
    }
});
async function visit() {
    const provider = new MockProvider("sales"),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity),
        engine = new Outbox(store, owner, provider);
    const morning = new MorningSimulation(store, identity, provider);
    await morning.acceptAttendance();
    const source = await morning.open();
    const service = new SalesVisits(store, identity, provider, engine),
        outlet = source.snapshot!.outlets[0];
    const fix = {
        latitude: outlet.latitude,
        longitude: outlet.longitude,
        accuracy: 3,
        sampled_at: new Date().toISOString(),
    };
    const start = await service.checkIn(outlet.id, fix);
    await service.checkOut(
        outlet.id,
        fix,
        "no_order",
        "Kunjungan selesai tanpa order",
    );
    return { provider, owner, engine, start };
}
it("uses sync's actual visit integrity and dependencies, including an accepted but corrupt parent", async () => {
    const c = await visit();
    let s = await store.visitSyncState(c.owner),
        before = JSON.stringify(s);
    let d = diagnoseSync(s, c.owner, true);
    const end = d.find((r) => r.type === "sales.visit.check_out")!;
    expect(end.code).toBe("dependency");
    expect(end.dependencies[0].uuid).toBe(c.start.command.client_uuid);
    expect(end.context?.outlet).toBe("demo-outlet-1");
    expect(JSON.stringify(s)).toBe(before);
    await c.engine.flush();
    s = await store.visitSyncState(c.owner);
    expect(
        diagnoseSync(s, c.owner, true).every((r) => r.code === "accepted"),
    ).toBe(true);
    const parent = s.rows.find(
        (r) => r.command.type === "sales.visit.check_in",
    )!;
    if (parent.command.type !== "sales.visit.check_in") throw new Error("type");
    parent.command.payload.fix.latitude = 0;
    await store.put(parent);
    s = await store.visitSyncState(c.owner);
    before = JSON.stringify(s);
    d = diagnoseSync(s, c.owner, true);
    expect(d.every((r) => r.code === "integrity")).toBe(true);
    expect(JSON.stringify(s)).toBe(before);
    expect(d.find((r) => r.type === "sales.visit.check_in")?.state).toBe(
        "accepted",
    ); // retain historical receipt/state, flag current integrity
});
it("diagnosing missing source/ledger neither repairs nor deletes persisted data", async () => {
    const c = await visit();
    await store.draft(c.owner, VISITS_KEY, { version: 1, visits: [] });
    const before = await store.visitSyncState(c.owner);
    const d = diagnoseSync(before, c.owner, true);
    expect(d.every((r) => r.code === "integrity")).toBe(true);
    expect(await store.visitSyncState(c.owner)).toEqual(before);
});
it("shows old valid receipts on the next business day using historical source", async () => {
    const c = await visit();
    vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
    expect(
        diagnoseSync(await store.visitSyncState(c.owner), c.owner, true)
            .map((r) => r.code)
            .sort(),
    ).toEqual(["dependency", "ready"]);
    await c.engine.flush();
    expect(
        diagnoseSync(await store.visitSyncState(c.owner), c.owner, true).every(
            (r) => r.code === "accepted",
        ),
    ).toBe(true);
});
