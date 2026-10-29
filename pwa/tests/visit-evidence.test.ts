import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { openDB } from "idb";
import { SalesVisits } from "../src/domain/visits";
import { FieldStore } from "../src/storage/store";
import { Outbox } from "../src/domain/outbox";
import { MockProvider } from "../src/data/mock";
import { MorningSimulation, MORNING_KEY } from "../src/domain/morning";
import { ownerKey } from "../src/domain/contracts";
import { VISITS_KEY } from "../src/domain/visit-validation";
import type { VisitLedger } from "../src/domain/visit-contracts";
import { makeVisitPhoto } from "./visit-fixtures";
let store: FieldStore, name: string;
beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
    vi.stubGlobal("navigator", { onLine: true });
    name = crypto.randomUUID();
    store = new FieldStore(name);
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
async function setup() {
    const provider = new MockProvider("sales"),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity),
        engine = new Outbox(store, owner, provider),
        morning = new MorningSimulation(store, identity, provider);
    await morning.acceptAttendance();
    const source = await morning.open(),
        outlet = source.snapshot!.outlets[0];
    const service = new SalesVisits(store, identity, provider, engine),
        fix = {
            latitude: outlet.latitude,
            longitude: outlet.longitude,
            accuracy: 3,
            sampled_at: new Date().toISOString(),
        };
    return {
        provider,
        identity,
        owner,
        engine,
        morning,
        source,
        outlet,
        service,
        fix,
    };
}
it("requires new packages for both actions and atomically copies distinct refs into command and ledger", async () => {
    const c = await setup();
    await expect(c.service.checkIn(c.outlet.id, c.fix)).rejects.toThrow(
        "paket foto",
    );
    expect(await store.list(c.owner)).toHaveLength(0);
    const id = crypto.randomUUID(),
        at = new Date().toISOString();
    const context = {
        visit_uuid: id,
        work_session_id: c.source.sessionId!,
        business_date: c.source.businessDate,
        snapshot_version: c.source.snapshot!.version,
        outlet_id: c.outlet.id,
        site: {
            latitude: c.outlet.latitude,
            longitude: c.outlet.longitude,
            radius: c.outlet.radius,
        },
        fix: c.fix,
    };
    await expect(
        c.engine.enqueue(
            "sales.visit.check_in",
            context,
            "Attempt without photo",
            id,
            {
                key: VISITS_KEY,
                expected: undefined,
                value: {
                    version: 1,
                    visits: [
                        {
                            mode: "simulation",
                            owner: c.owner,
                            context,
                            session_opened_at: c.source.openedAt!,
                            morning_source: c.source,
                            check_in_at: at,
                            check_out: null,
                        },
                    ],
                },
                visitGuard: { morning: c.source },
                occurredAt: at,
            },
        ),
    ).rejects.toThrow("wajib foto");
    expect(await store.list(c.owner)).toHaveLength(0);
    const photo = await makeVisitPhoto(store, c.owner, c.fix),
        start = await c.service.checkIn(c.outlet.id, c.fix, photo);
    await expect(
        c.service.checkOut(c.outlet.id, c.fix, "no_order", "Tidak ada order"),
    ).rejects.toThrow("paket foto");
    await expect(
        c.service.checkOut(
            c.outlet.id,
            c.fix,
            "no_order",
            "Tidak ada order",
            photo,
        ),
    ).rejects.toThrow("sudah digunakan");
    const after = await makeVisitPhoto(store, c.owner, c.fix);
    await c.service.checkOut(
        c.outlet.id,
        c.fix,
        "no_order",
        "Tidak ada order",
        after,
    );
    const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
    expect(ledger.visits[0].photo_required).toBe(true);
    expect(ledger.visits[0].check_in_evidence).toEqual(photo);
    expect(ledger.visits[0].check_out?.payload.evidence).toEqual(after);
    expect(
        start.command.type === "sales.visit.check_in" &&
            start.command.payload.evidence,
    ).toEqual(photo);
    const source = JSON.stringify(ledger);
    await store.draft(c.owner, "unrelated-photo-draft", { ref: after });
    expect(JSON.stringify(await store.draft(c.owner, VISITS_KEY))).toBe(source);
});
it("holds wrong owner, wrong site, old photo, legacy photo and bad package before queue commit", async () => {
    const c = await setup();
    const correct = await makeVisitPhoto(store, c.owner, c.fix);
    const otherOwner = await makeVisitPhoto(store, "other", c.fix),
        outside = await makeVisitPhoto(store, c.owner, {
            ...c.fix,
            latitude: 0,
        });
    for (const ref of [
        otherOwner,
        outside,
        { ...correct, packageHash: "0".repeat(64) },
        { ...correct, packageHash: undefined },
    ])
        await expect(
            c.service.checkIn(c.outlet.id, c.fix, ref as typeof correct),
        ).rejects.toThrow();
    vi.setSystemTime(new Date("2026-10-27T00:01:01Z"));
    await expect(
        c.service.checkIn(
            c.outlet.id,
            { ...c.fix, sampled_at: new Date().toISOString() },
            correct,
        ),
    ).rejects.toThrow("kedaluwarsa");
    expect(await store.list(c.owner)).toHaveLength(0);
    expect(await store.draft(c.owner, VISITS_KEY)).toBeUndefined();
    const oldSessionPhoto = await makeVisitPhoto(store, c.owner, {
        ...c.fix,
        sampled_at: new Date().toISOString(),
    });
    vi.setSystemTime(new Date("2026-10-27T00:01:02Z"));
    await c.morning.acceptAttendance();
    await c.morning.open();
    await expect(
        c.service.checkIn(
            c.outlet.id,
            { ...c.fix, sampled_at: new Date().toISOString() },
            oldSessionPhoto,
        ),
    ).rejects.toThrow("Waktu foto");
});
it.each(["photo", "map", "missing", "ref", "marker"])(
    "restore and replay hold corrupt parent %s even after accepted receipt, preserving descendants",
    async (kind) => {
        const c = await setup(),
            photo = await makeVisitPhoto(store, c.owner, c.fix);
        await c.service.checkIn(c.outlet.id, c.fix, photo);
        await c.engine.flush();
        const end = await makeVisitPhoto(store, c.owner, c.fix);
        await c.service.checkOut(
            c.outlet.id,
            c.fix,
            "no_order",
            "Selesai tanpa order",
            end,
        );
        const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
        const db = await openDB(name),
            row = await db.get("evidence", `${c.owner}:${photo.id}`);
        if (kind === "photo") {
            row.blob = new Blob(["changed"], { type: "image/jpeg" });
            await db.put("evidence", row);
        }
        if (kind === "map") {
            row.visual.map = new Blob(["changed"], { type: "image/png" });
            await db.put("evidence", row);
        }
        if (kind === "missing") await db.delete("evidence", row.key);
        if (kind === "ref") {
            delete ledger.visits[0].check_in_evidence;
            await store.draft(c.owner, VISITS_KEY, ledger);
        }
        if (kind === "marker") {
            delete ledger.visits[0].photo_required;
            await store.draft(c.owner, VISITS_KEY, ledger);
        }
        db.close();
        const before = await store.list(c.owner);
        await store.close();
        store = new FieldStore(name);
        const engine = new Outbox(store, c.owner, c.provider),
            restored = new SalesVisits(store, c.identity, c.provider, engine);
        await expect(restored.restore(c.outlet.id)).rejects.toThrow();
        const send = vi.spyOn(c.provider, "submit");
        await engine.flush();
        await engine.retry();
        expect(send).not.toHaveBeenCalled();
        const after = await store.list(c.owner);
        expect(after.map((q) => q.command)).toEqual(
            before.map((q) => q.command),
        );
        expect(after.find((q) => q.state === "accepted")?.receipt?.status).toBe(
            "accepted",
        );
        expect(after.filter((q) => q.state === "queued")).toHaveLength(1);
    },
);
it("rechecks morning at commit after awaiting media hashes", async () => {
    const c = await setup(),
        photo = await makeVisitPhoto(store, c.owner, c.fix),
        get = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementationOnce(async (...args) => {
        await store.draft(c.owner, MORNING_KEY, {
            ...c.source,
            snapshot: { ...c.source.snapshot!, version: "changed" },
        });
        return get(...args);
    });
    await expect(c.service.checkIn(c.outlet.id, c.fix, photo)).rejects.toThrow(
        "paket pagi berubah",
    );
    expect(await store.list(c.owner)).toHaveLength(0);
    expect(await store.draft(c.owner, VISITS_KEY)).toBeUndefined();
});
it("replays historical photo visits after the morning bundle is replaced the next day", async () => {
    const c = await setup();
    await c.service.checkIn(
        c.outlet.id,
        c.fix,
        await makeVisitPhoto(store, c.owner, c.fix),
    );
    await c.service.checkOut(
        c.outlet.id,
        c.fix,
        "no_order",
        "Selesai tanpa order",
        await makeVisitPhoto(store, c.owner, c.fix),
    );
    vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
    await c.morning.acceptAttendance();
    await c.morning.open();
    await c.engine.flush();
    expect(
        (await store.list(c.owner)).every((q) => q.state === "accepted"),
    ).toBe(true);
});
it("supports a pre-upgrade photo-less queue without rewriting a previously accepted UUID", async () => {
    const c = await setup();
    await c.service.checkIn(
        c.outlet.id,
        c.fix,
        await makeVisitPhoto(store, c.owner, c.fix),
    );
    await c.service.checkOut(
        c.outlet.id,
        c.fix,
        "no_order",
        "Selesai tanpa order",
        await makeVisitPhoto(store, c.owner, c.fix),
    );
    const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
    delete ledger.visits[0].photo_required;
    delete ledger.visits[0].check_in_evidence;
    delete ledger.visits[0].check_out!.payload.evidence;
    delete ledger.visits[0].check_out!.payload.evidence_version;
    await store.draft(c.owner, VISITS_KEY, ledger);
    for (const row of await store.list(c.owner)) {
        if (
            row.command.type !== "sales.visit.check_in" &&
            row.command.type !== "sales.visit.check_out"
        )
            throw new Error("type");
        delete row.command.payload.evidence;
        delete row.command.payload.evidence_version;
        row.state = "queued";
        delete row.receipt;
        await store.put(row);
    }
    vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
    await c.engine.flush();
    expect(
        (await store.list(c.owner)).every((q) => q.state === "accepted"),
    ).toBe(true);
});
