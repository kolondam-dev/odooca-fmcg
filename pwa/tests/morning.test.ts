import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import {
    fieldBusinessDate,
    morningReady,
    MorningSimulation,
    MORNING_KEY,
} from "../src/domain/morning";
import { MockProvider } from "../src/data/mock";
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
it("expires at WITA midnight and isolates company/persona; driver and live provider cannot open", async () => {
    const { identity, provider, service } = await setup();
    await service.acceptAttendance();
    const session = await service.open();
    expect(morningReady(session, "other-company:" + identity.id)).toBe(false);
    const other = await setup("canvass");
    expect(await other.service.restore()).toBeUndefined();
    const driver = await setup("delivery");
    await expect(driver.service.acceptAttendance()).rejects.toThrow("Sales");
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
