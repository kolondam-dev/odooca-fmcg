import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import {
    fieldBusinessDate,
    morningReady,
    MorningSimulation,
    MORNING_KEY,
    type MorningRecord,
} from "../src/domain/morning";
import { MockProvider } from "../src/data/mock";
import { Outbox } from "../src/domain/outbox";
import { ownerKey } from "../src/domain/contracts";
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
async function setup(actor = "sales") {
    const provider = new MockProvider(actor);
    const identity = await provider.bootstrap();
    return {
        provider,
        identity,
        service: new MorningSimulation(store, identity, provider),
    };
}
it("requires accepted simulator attendance before a complete online snapshot, then restores the exact bundle offline", async () => {
    const { identity, service } = await setup();
    await expect(service.open()).rejects.toThrow("absensi");
    const attendance = await service.acceptAttendance();
    expect(morningReady(attendance, ownerKey(identity))).toBe(false);
    const session = await service.open();
    expect(morningReady(session, ownerKey(identity))).toBe(true);
    vi.stubGlobal("navigator", { onLine: false });
    expect(await service.restore()).toEqual(session);
    expect(session.snapshot?.products.length).toBeGreaterThan(0);
});
it("blocks offline morning opening and never converts rejected/expired scenarios into attendance", async () => {
    const { provider, service } = await setup();
    vi.stubGlobal("navigator", { onLine: false });
    await expect(service.acceptAttendance()).rejects.toThrow("online");
    vi.stubGlobal("navigator", { onLine: true });
    for (const scenario of [
        "approval",
        "rejected",
        "expired",
        "timeout",
    ] as const) {
        provider.scenario = scenario;
        await expect(service.acceptAttendance()).rejects.toThrow("Simulator");
        expect(await service.restore()).toBeUndefined();
    }
});
it("expires at WITA midnight and isolates company/persona; driver daily sync is supported and live provider cannot open", async () => {
    const { identity, provider, service } = await setup();
    await service.acceptAttendance();
    const session = await service.open();
    expect(morningReady(session, "other-company:" + identity.id)).toBe(false);
    const other = await setup("canvass");
    expect(await other.service.restore()).toBeUndefined();
    const driver = await setup("delivery");
    await driver.service.acceptAttendance();
    expect(
        (await driver.service.open()).deliveryManifest?.length,
    ).toBeGreaterThan(0);
    const live = {
        ...provider,
        mode: "live" as const,
        bootstrap: () => provider.bootstrap(),
        snapshot: () => provider.snapshot(),
        submit: provider.submit.bind(provider),
    };
    await expect(
        new MorningSimulation(store, identity, live).acceptAttendance(),
    ).rejects.toThrow("resmi");
    vi.setSystemTime(new Date("2026-10-27T16:00:00Z"));
    expect(fieldBusinessDate()).toBe("2026-10-28");
    expect(morningReady(session, ownerKey(identity))).toBe(false);
    expect(await service.restore()).toBeUndefined();
});
it("failed sync, incomplete snapshot and storage errors never unlock a session", async () => {
    const { provider, identity, service } = await setup();
    await service.acceptAttendance();
    vi.spyOn(provider, "snapshot").mockRejectedValueOnce(new Error("network"));
    await expect(service.open()).rejects.toThrow("network");
    const snapshot = await provider.snapshot();
    vi.spyOn(provider, "snapshot").mockResolvedValueOnce({
        ...snapshot,
        products: [],
    });
    await expect(service.open()).rejects.toThrow("belum lengkap");
    // Assert persistent state, independently of error wording.
    expect(morningReady(await service.restore(), ownerKey(identity))).toBe(
        false,
    );
    vi.spyOn(store, "draft").mockImplementationOnce(async () => {
        throw new Error("quota");
    });
    await expect(service.acceptAttendance()).rejects.toThrow("quota");
    expect(morningReady(await service.restore(), ownerKey(identity))).toBe(
        false,
    );
});
it("does not open a stale date if midnight happens while fetching the package", async () => {
    const { provider, service } = await setup();
    await service.acceptAttendance();
    const snapshot = await provider.snapshot();
    vi.spyOn(provider, "snapshot").mockImplementationOnce(async () => {
        vi.setSystemTime(new Date("2026-10-27T16:00:00Z"));
        return snapshot;
    });
    await expect(service.open()).rejects.toThrow();
    expect(await service.restore()).toBeUndefined();
});
it("ignores malformed persisted data", async () => {
    const { identity, service } = await setup();
    await store.draft(ownerKey(identity), MORNING_KEY, { sessionId: "forged" });
    expect(await service.restore()).toBeUndefined();
});

it("rejects yesterday's snapshot even when network fetch succeeded", async () => {
    const { provider, service, identity } = await setup();
    await service.acceptAttendance();
    const snapshot = await provider.snapshot();
    vi.spyOn(provider, "snapshot").mockResolvedValueOnce({
        ...snapshot,
        updatedAt: "2026-10-26T00:00:00Z",
    });
    await expect(service.open()).rejects.toThrow("belum lengkap");
    expect(morningReady(await service.restore(), ownerKey(identity))).toBe(
        false,
    );
});

it("keeps attendance-only state if writing the completed package exceeds storage quota", async () => {
    const { service, identity } = await setup();
    await service.acceptAttendance();
    const original = store.draft.bind(store);
    const spy = vi
        .spyOn(store, "draft")
        .mockImplementation(async (owner, key, value) => {
            if (value !== undefined) throw new Error("quota");
            return original(owner, key);
        });
    await expect(service.open()).rejects.toThrow("quota");
    spy.mockRestore();
    expect(morningReady(await service.restore(), ownerKey(identity))).toBe(
        false,
    );
});

const corruptions: [string, (record: MorningRecord) => unknown][] = [
    [
        "empty products",
        (r) => ({ ...r, snapshot: { ...r.snapshot!, products: [] } }),
    ],
    [
        "empty outlets",
        (r) => ({ ...r, snapshot: { ...r.snapshot!, outlets: [] } }),
    ],
    [
        "blank version",
        (r) => ({ ...r, snapshot: { ...r.snapshot!, version: "  " } }),
    ],
    [
        "old snapshot timestamp",
        (r) => ({
            ...r,
            snapshot: { ...r.snapshot!, updatedAt: "2020-01-01T00:00:00Z" },
        }),
    ],
    [
        "invalid snapshot timestamp",
        (r) => ({
            ...r,
            snapshot: { ...r.snapshot!, updatedAt: "not-a-date" },
        }),
    ],
    [
        "next WITA day snapshot",
        (r) => ({
            ...r,
            snapshot: { ...r.snapshot!, updatedAt: "2026-10-27T16:00:00Z" },
        }),
    ],
    [
        "future snapshot timestamp",
        (r) => ({
            ...r,
            snapshot: { ...r.snapshot!, updatedAt: "2026-10-27T00:01:00Z" },
        }),
    ],
    ["wrong owner", (r) => ({ ...r, owner: "other-company:other-user" })],
    ["old business date", (r) => ({ ...r, businessDate: "2026-10-26" })],
    [
        "old attendance date",
        (r) => ({ ...r, attendanceAt: "2026-10-26T00:00:00Z" }),
    ],
    [
        "invalid attendance timestamp",
        (r) => ({ ...r, attendanceAt: "not-a-date" }),
    ],
    [
        "future attendance",
        (r) => ({ ...r, attendanceAt: "2026-10-27T00:01:00Z" }),
    ],
    [
        "old session timestamp",
        (r) => ({ ...r, openedAt: "2026-10-26T00:00:00Z" }),
    ],
    ["invalid session timestamp", (r) => ({ ...r, openedAt: "not-a-date" })],
    [
        "session before attendance",
        (r) => ({ ...r, openedAt: "2026-10-26T23:59:59Z" }),
    ],
    ["future session", (r) => ({ ...r, openedAt: "2026-10-27T00:01:00Z" })],
    ["missing session id with snapshot", (r) => ({ ...r, sessionId: null })],
    [
        "missing session timestamp with snapshot",
        (r) => ({ ...r, openedAt: null }),
    ],
    ["missing snapshot in opened session", (r) => ({ ...r, snapshot: null })],
];
it.each(corruptions)(
    "rejects persisted %s on restore/readiness without losing pending business data",
    async (_name, mutate) => {
        const { provider, service, identity } = await setup();
        await service.acceptAttendance();
        const session = await service.open();
        const owner = ownerKey(identity);
        const queued = await new Outbox(store, owner, provider).enqueue(
            "sales.order.submit",
            { note: "pending transaction" },
            "Preserve pending",
        );
        const draft = { qty: { "demo-product-1": 2 } };
        await store.draft(owner, "order:demo-outlet-1", draft);
        const corrupt = mutate(session);
        await store.draft(owner, MORNING_KEY, corrupt);
        expect.soft(morningReady(corrupt as MorningRecord, owner)).toBe(false);
        expect(await service.restore()).toBeUndefined();
        expect(await store.list(owner)).toEqual([queued]);
        expect(await store.draft(owner, "order:demo-outlet-1")).toEqual(draft);
    },
);

it("restores same WITA-day packages across the UTC date boundary", async () => {
    const { service, identity } = await setup();
    await service.acceptAttendance();
    const record = await service.open();
    const valid = {
        ...record,
        snapshot: { ...record.snapshot!, updatedAt: "2026-10-26T23:59:59Z" },
    };
    await store.draft(ownerKey(identity), MORNING_KEY, valid);
    expect(morningReady(await service.restore(), ownerKey(identity))).toBe(
        true,
    );
});
it("rejects a snapshot newer than its session even if both timestamps are in the past", async () => {
    const { service, identity } = await setup();
    await service.acceptAttendance();
    const record = await service.open();
    vi.setSystemTime(new Date("2026-10-27T00:02:00Z"));
    const invalid = {
        ...record,
        snapshot: { ...record.snapshot!, updatedAt: "2026-10-27T00:01:00Z" },
    };
    await store.draft(ownerKey(identity), MORNING_KEY, invalid);
    expect(morningReady(invalid, ownerKey(identity))).toBe(false);
    expect(await service.restore()).toBeUndefined();
});
