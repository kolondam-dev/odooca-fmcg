import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { MockProvider } from "../src/data/mock";
import { MorningSimulation, MORNING_KEY } from "../src/domain/morning";
import { ownerKey } from "../src/domain/contracts";
import {
    DeliveryPodSchema,
    type DeliveryPod,
} from "../src/domain/delivery-contracts";
import {
    validatePod,
    validatePodMedia,
    DELIVERY_SESSION_KEY,
    statusOutcome,
} from "../src/domain/delivery";
import { orderQuote, validateOrderQuote } from "../src/domain/order-pricing";
import { Outbox } from "../src/domain/outbox";
import { podKey } from "../src/domain/delivery-contracts";
import { makeVisitPhoto, PhotoSalesVisits } from "./visit-fixtures";
let store: FieldStore;
let name: string;
beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-28T01:00:00Z"));
    vi.stubGlobal("navigator", { onLine: true });
    name = crypto.randomUUID();
    store = new FieldStore(name);
});
afterEach(async () => {
    await store.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
async function fixture() {
    const provider = new MockProvider("delivery"),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity);
    const morning = new MorningSimulation(store, identity, provider);
    await morning.acceptAttendance();
    const daily = await morning.open();
    const source = daily.deliveryManifest![0];
    await store.draft(
        owner,
        `delivery-manifest-v1:${source.business_date}`,
        daily.deliveryManifest,
    );
    const fix = {
        ...source.site,
        accuracy: 3,
        sampled_at: new Date().toISOString(),
    };
    const opening = await makeVisitPhoto(store, owner, fix);
    const session = {
        id: crypto.randomUUID(),
        owner,
        task_id: source.id,
        opened_at: new Date().toISOString(),
        opening,
        pinpoint: {
            latitude: fix.latitude,
            longitude: fix.longitude,
            accuracy: 3,
            sampled_at: fix.sampled_at,
        },
        pinpoint_set_at: new Date().toISOString(),
        daily_source: daily,
    };
    const evidence = await makeVisitPhoto(store, owner, fix);
    const p: DeliveryPod = {
        pod_version: 1,
        source,
        session,
        delivery_status: "Fully Received",
        recipient: "Budi",
        outcome: "delivered",
        reason: "Sesuai dokumen",
        lines: source.lines.map((l) => ({
            id: l.id,
            received: l.quantity,
            reason: "Sesuai dokumen",
        })),
        evidence,
    };
    return { provider, owner, p, daily, source, session };
}
async function enqueue(f: Awaited<ReturnType<typeof fixture>>, p = f.p) {
    const uuid = crypto.randomUUID(),
        occurred_at = new Date().toISOString();
    return new Outbox(store, f.owner, f.provider).enqueue(
        "delivery.pod.submit",
        p,
        "POD",
        uuid,
        {
            key: podKey(p.source),
            expected: undefined,
            value: {
                schema_version: 1,
                client_uuid: uuid,
                occurred_at,
                type: "delivery.pod.submit",
                payload: p,
            },
            occurredAt: occurred_at,
        },
    );
}
it.each(Object.entries(statusOutcome))(
    "%s stores every required line reason and consistent quantities",
    async (status, outcome) => {
        const f = await fixture();
        const p = structuredClone(f.p);
        p.delivery_status = status as DeliveryPod["delivery_status"];
        p.outcome = outcome;
        if (outcome !== "delivered") p.lines.forEach((l) => (l.received = 0));
        if (outcome === "partial") {
            p.lines[0].received = 12;
            p.reason = "";
        }
        await store.openDeliverySession(f.owner, f.source, f.session);
        validatePod(p, f.owner, new Date().toISOString());
        await enqueue(f, p);
        const rows = await store.list(f.owner);
        expect(rows).toHaveLength(1);
        expect(DeliveryPodSchema.parse(rows[0].command.payload).lines).toEqual(
            p.lines,
        );
        expect(
            (
                (await store.draft(f.owner, DELIVERY_SESSION_KEY)) as {
                    closed?: string;
                }
            ).closed,
        ).toBe(rows[0].command.client_uuid);
    },
);
it("partial needs each affected item reason; full/global status needs matching reason on every row", async () => {
    const f = await fixture(),
        at = new Date().toISOString();
    const p = structuredClone(f.p);
    p.delivery_status = "Received Partial";
    p.outcome = "partial";
    p.lines[0].received = 12;
    p.lines[0].reason = "";
    expect(() => validatePod(p, f.owner, at)).toThrow("Alasan");
    p.lines[0].reason = "Kemasan rusak";
    p.lines[1].received = 0;
    p.lines[1].reason = "";
    expect(() => validatePod(p, f.owner, at)).toThrow("Alasan");
    p.lines[1].reason = "Toko menolak";
    p.reason = "";
    expect(() => validatePod(p, f.owner, at)).not.toThrow();
    f.p.lines[0].reason = "Lain";
    expect(() => validatePod(f.p, f.owner, at)).toThrow("Alasan");
});
it("two connections cannot open two active sessions; closing without active session or with changed daily source is atomic", async () => {
    const f = await fixture(),
        other = new FieldStore(name);
    try {
        const outcomes = await Promise.allSettled([
            store.openDeliverySession(f.owner, f.source, f.session),
            other.openDeliverySession(f.owner, f.source, {
                ...f.session,
                id: crypto.randomUUID(),
            }),
        ]);
        expect(outcomes.filter((x) => x.status === "fulfilled")).toHaveLength(
            1,
        );
    } finally {
        await other.close();
    }
    const active = (await store.draft(f.owner, DELIVERY_SESSION_KEY)) as {
        session: DeliveryPod["session"];
    };
    f.p.session = active.session;
    await store.draft(f.owner, MORNING_KEY, {
        ...f.daily,
        sessionId: crypto.randomUUID(),
    });
    await expect(enqueue(f)).rejects.toThrow("daily sync");
    expect(await store.list(f.owner)).toHaveLength(0);
    expect(await store.draft(f.owner, DELIVERY_SESSION_KEY)).toEqual(active);
});
it("no daily sync, stale pinpoint, reused closing photo and sessionless v2 POD fail closed", async () => {
    const f = await fixture(),
        at = new Date().toISOString();
    await expect(enqueue(f)).rejects.toThrow("daily sync");
    expect(() =>
        validatePod({ ...f.p, session: undefined }, f.owner, at),
    ).toThrow();
    expect(() =>
        validatePod({ ...f.p, evidence: f.session.opening }, f.owner, at),
    ).toThrow("closing");
    await expect(
        store.openDeliverySession(f.owner, f.source, {
            ...f.session,
            pinpoint: {
                ...f.session.pinpoint,
                sampled_at: "2026-10-27T01:00:00Z",
            },
        }),
    ).rejects.toThrow();
    await store.draft(f.owner, MORNING_KEY, {});
    await expect(
        store.openDeliverySession(f.owner, f.source, f.session),
    ).rejects.toThrow("Daily sync");
});
it("closed historical POD replays next day but changed opening media is held", async () => {
    const f = await fixture();
    await store.openDeliverySession(f.owner, f.source, f.session);
    const row = await enqueue(f);
    vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    await expect(
        validatePodMedia(row, f.owner, store),
    ).resolves.toBeUndefined();
    const media = await store.getEvidence(f.owner, f.session.opening.id);
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementation(async (owner, id) =>
        id === f.session.opening.id
            ? { ...media!, blob: new Blob(["broken"]) }
            : original(owner, id),
    );
    // Only the opening read is reached before the integrity failure.
    await expect(validatePodMedia(row, f.owner, store)).rejects.toThrow(
        "tidak valid",
    );
});
it("carton/pack/pcs preserve equivalent quantities, discount rounding and total tamper guard", async () => {
    const snapshot = await new MockProvider("sales").snapshot();
    const q = (qty: string, uom: "carton" | "pack" | "pcs") =>
        orderQuote([{ product_id: "demo-product-1", qty, uom }], snapshot);
    expect(q("1", "carton")).toEqual(q("12", "pack"));
    expect(q("1", "carton")).toEqual(q("144", "pcs"));
    const lines = [
        { product_id: "demo-product-1", qty: "1", uom: "pack" as const },
    ];
    const quote = orderQuote(lines, snapshot, {
        percent: 5,
        reason: "Promo demo",
    });
    expect(quote.requestedTotal).toBe(14820);
    expect(() =>
        validateOrderQuote(
            { lines, pricing_version: 1, observed_total: "1" },
            snapshot,
        ),
    ).toThrow("Total");
    expect(() =>
        orderQuote(lines, snapshot, { percent: 101, reason: "Promo" }),
    ).toThrow();
});
it.each([true, false])(
    "discount decision %s applies to pending request once, immutable command and matching receipt",
    async (approved) => {
        const provider = new MockProvider("sales"),
            identity = await provider.bootstrap(),
            owner = ownerKey(identity),
            morning = new MorningSimulation(store, identity, provider);
        await morning.acceptAttendance();
        const daily = await morning.open();
        const engine = new Outbox(store, owner, provider),
            visits = new PhotoSalesVisits(store, identity, provider, engine),
            site = daily.snapshot!.outlets[0];
        const fix = {
            latitude: site.latitude,
            longitude: site.longitude,
            accuracy: 3,
            sampled_at: new Date().toISOString(),
        };
        await visits.checkIn(site.id, fix);
        const payload = {
            outlet_id: site.id,
            work_session_id: daily.sessionId,
            morning_business_date: daily.businessDate,
            snapshot_version: daily.snapshot!.version,
            lines: [{ product_id: "demo-product-1", qty: "1", uom: "pack" }],
            note: "",
            pricing_version: 1,
            discount_request: { percent: 5, reason: "Promo demo" },
            observed_total: "14820",
        };
        await visits.submitOrder(payload, fix);
        await engine.flush();
        const row = (await store.list(owner)).find(
            (r) => r.command.type === "sales.order.submit",
        )!;
        expect(row.state).toBe("needs_approval");
        await expect(
            store.decideDemoDiscount("other", row, approved, "Keputusan demo"),
        ).rejects.toThrow();
        const other = new FieldStore(name);
        try {
            const decisions = await Promise.allSettled([
                store.decideDemoDiscount(
                    owner,
                    row,
                    approved,
                    "Keputusan demo",
                ),
                other.decideDemoDiscount(
                    owner,
                    row,
                    approved,
                    "Keputusan demo",
                ),
            ]);
            expect(
                decisions.filter((d) => d.status === "fulfilled"),
            ).toHaveLength(1);
        } finally {
            await other.close();
        }
        const result = (await store.list(owner)).find(
            (r) => r.key === row.key,
        )!;
        expect(result.command).toEqual(row.command);
        expect(result.state).toBe(approved ? "accepted" : "rejected");
        expect(result.receipt?.message).toContain(
            approved ? "disetujui 5%" : "disetujui 0%",
        );
        await expect(
            store.decideDemoDiscount(owner, row, !approved, "Balik keputusan"),
        ).rejects.toThrow("berubah");
    },
);
