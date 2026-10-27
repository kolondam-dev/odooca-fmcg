import { diagnoseSync } from "../src/domain/sync-diagnostics";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { openDB } from "idb";
import { FieldStore, type Evidence } from "../src/storage/store";
import {
    assertLocalEvidence,
    sha256,
    evidenceBinding,
    validateEvidenceTime,
    type EvidenceReference,
} from "../src/domain/evidence-package";
import { Outbox } from "../src/domain/outbox";
import { MockProvider } from "../src/data/mock";
let store: FieldStore, name: string;
beforeEach(() => {
    vi.stubGlobal("navigator", { onLine: true });
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
    name = crypto.randomUUID();
    store = new FieldStore(name);
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
async function make(owner = "owner") {
    const ref: EvidenceReference = {
        id: crypto.randomUUID(),
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
        capturedAt: new Date().toISOString(),
    };
    const row: Evidence = {
        key: `${owner}:${ref.id}`,
        owner,
        blob: new Blob(["photo"], { type: "image/jpeg" }),
        ...ref,
        mapStatus: "pending",
    };
    const map = new Blob(["pinpoint"], { type: "image/png" });
    const visual = {
        version: 1 as const,
        kind: "simulation_grid" as const,
        selectedAt: ref.capturedAt,
        fixSampledAt: ref.capturedAt,
        photoSha256: await sha256(row.blob),
        mapSha256: await sha256(map),
    };
    const bindingSha256 = await sha256(evidenceBinding(row, visual));
    row.visual = { ...visual, bindingSha256, map };
    ref.packageHash = bindingSha256;
    return { ref, row, owner };
}
it("stores one atomic immutable package and restores only for its owner and matching ref", async () => {
    const c = await make();
    await store.saveEvidence(c.row);
    const [saved] = await store.listEvidence(c.owner);
    await expect(
        assertLocalEvidence(saved, c.ref, c.owner),
    ).resolves.toBeUndefined();
    await expect(assertLocalEvidence(saved, c.ref, "other")).rejects.toThrow();
    await expect(
        store.saveEvidence({ ...c.row, blob: new Blob(["changed"]) }),
    ).rejects.toThrow();
    await expect(
        store.saveEvidence({ ...c.row, visual: undefined }),
    ).rejects.toThrow("immutable");
    expect(await store.listEvidence(c.owner)).toHaveLength(1);
});
it.each([
    "photo",
    "map",
    "coordinates",
    "time",
    "hash",
    "missing-package",
    "missing-map",
    "downgrade",
])(
    "rejects %s corruption on restore and send without deleting evidence or fabricating a receipt",
    async (kind) => {
        const c = await make();
        await store.saveEvidence(c.row);
        const provider = new MockProvider("sales"),
            engine = new Outbox(store, c.owner, provider);
        const item = await engine.enqueue(
            "field_expense.request",
            { evidence: c.ref },
            "Evidence test",
        );
        const broken = structuredClone(c.row);
        if (kind === "photo")
            broken.blob = new Blob(["changed"], { type: "image/jpeg" });
        if (kind === "map")
            broken.visual!.map = new Blob(["changed"], { type: "image/png" });
        if (kind === "coordinates") broken.latitude = 0;
        if (kind === "time") broken.capturedAt = "2026-10-26T00:00:00Z";
        if (kind === "hash") broken.visual!.photoSha256 = "0".repeat(64);
        if (kind === "missing-package") delete broken.visual;
        if (kind === "missing-map")
            broken.visual!.map = new Blob([], { type: "image/png" });
        if (kind === "downgrade") {
            delete c.ref.packageHash;
            if (item.command.type !== "field_expense.request")
                throw new Error("type");
            item.command.payload.evidence = c.ref;
            await store.put(item);
        }
        const db = await openDB(name);
        await db.put("evidence", broken);
        db.close();
        await expect(
            assertLocalEvidence(broken, c.ref, c.owner),
        ).rejects.toThrow();
        const send = vi.spyOn(provider, "submit");
        await engine.flush();
        await engine.retry();
        expect(send).not.toHaveBeenCalled();
        const [held] = await store.list(c.owner);
        expect(held.state).toBe("queued");
        expect(held.receipt).toBeUndefined();
        expect(held.error).toContain("review");
        expect(held.evidenceHold).toBe(true);
        expect(
            diagnoseSync(await store.visitSyncState(c.owner), c.owner, true)[0]
                .group,
        ).toBe("review");
        expect((await store.listEvidence(c.owner))[0]).toEqual(broken);
    },
);
it("requires fresh, finite GPS at creation but validates historic evidence at event time", async () => {
    const c = await make();
    const at = Date.parse(c.ref.capturedAt);
    for (const fix of [
        new Date(at - 60001).toISOString(),
        new Date(at + 1001).toISOString(),
        "bad",
    ])
        expect(() =>
            validateEvidenceTime(c.ref, c.ref.capturedAt, fix),
        ).toThrow();
    expect(() =>
        validateEvidenceTime(
            { ...c.ref, accuracy: 0 },
            c.ref.capturedAt,
            c.ref.capturedAt,
        ),
    ).toThrow();
    expect(() =>
        validateEvidenceTime(
            { ...c.ref, latitude: NaN },
            c.ref.capturedAt,
            c.ref.capturedAt,
        ),
    ).toThrow();
    await store.saveEvidence(c.row);
    vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
    await expect(
        assertLocalEvidence(
            (await store.listEvidence(c.owner))[0],
            c.ref,
            c.owner,
        ),
    ).resolves.toBeUndefined();
    const provider = new MockProvider("sales"),
        engine = new Outbox(store, c.owner, provider);
    await engine.enqueue(
        "field_expense.request",
        { evidence: c.ref },
        "Historic evidence",
    );
    await engine.flush();
    expect((await store.list(c.owner))[0].state).toBe("needs_approval");
});
it("does not invent a new package for legacy refs and does not create partial rows on invalid package", async () => {
    const c = await make();
    const legacy = { ...c.row, visual: undefined };
    delete c.ref.packageHash;
    await store.saveEvidence(legacy);
    await expect(
        assertLocalEvidence(legacy, c.ref, c.owner),
    ).resolves.toBeUndefined();
    const other = await make();
    other.row.visual!.map = new Blob([]);
    await expect(store.saveEvidence(other.row)).rejects.toThrow();
    expect(await store.listEvidence(c.owner)).toHaveLength(1);
});
