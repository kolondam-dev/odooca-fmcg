import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { MockProvider } from "../src/data/mock";
import { MorningSimulation } from "../src/domain/morning";
import { ownerKey } from "../src/domain/contracts";
import { Outbox } from "../src/domain/outbox";
import { PhotoSalesVisits, makeVisitPhoto } from "./visit-fixtures";
import {
    OrderRevisionSchema,
    revisionKey,
} from "../src/domain/order-revision-contracts";
import {
    submitRevision,
    validateRevisionMedia,
} from "../src/domain/order-revisions";
import { orderQuote } from "../src/domain/order-pricing";
import { approvalTiers } from "../src/domain/delivery-approval";
import {
    DeliverySessionSchema,
    podKey,
    type DeliveryPod,
} from "../src/domain/delivery-contracts";
import {
    TripCloseSchema,
    tripCloseKey,
    DEMO_OFFICE,
} from "../src/domain/trip-close-contracts";
import {
    tripPods,
    validateTripClose,
    validateTripCloseMedia,
} from "../src/domain/trip-close";
import { validatePodMedia } from "../src/domain/delivery";
import { requireVisitFix } from "../src/domain/visit-validation";
let store: FieldStore, name: string;
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
async function setup(actor = "sales", relaxed = true) {
    const provider = new MockProvider(actor, relaxed),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity),
        morningService = new MorningSimulation(store, identity, provider);
    // Use the same isolated receipt database as the domain/store under test.
    Object.defineProperty(provider, "store", { value: store });
    await morningService.acceptAttendance();
    const daily = await morningService.open(),
        engine = new Outbox(store, owner, provider);
    return { provider, identity, owner, daily, engine, morningService };
}
async function rejectedOrder() {
    const s = await setup();
    const service = new PhotoSalesVisits(
            store,
            s.identity,
            s.provider,
            s.engine,
        ),
        outlet = s.daily.snapshot!.outlets[0],
        fix = {
            latitude: outlet.latitude,
            longitude: outlet.longitude,
            accuracy: 3,
            sampled_at: new Date().toISOString(),
        };
    await service.checkIn(outlet.id, fix);
    const lines = [
        { product_id: "demo-product-1", qty: "1", uom: "pack" as const },
    ];
    const p = {
        outlet_id: outlet.id,
        work_session_id: s.daily.sessionId,
        morning_business_date: s.daily.businessDate,
        snapshot_version: s.daily.snapshot!.version,
        lines,
        note: "root",
        pricing_version: 1,
        discount_request: { percent: 5, reason: "Promo demo" },
        observed_total: String(
            orderQuote(lines, s.daily.snapshot!, {
                percent: 5,
                reason: "Promo demo",
            }).requestedTotal,
        ),
    };
    await service.submitOrder(p, fix);
    await s.engine.flush();
    const root = (await store.list(s.owner)).find(
        (r) => r.command.type === "sales.order.submit",
    )!;
    await store.decideDemoDiscount(s.owner, root, false, "Diskon ditolak");
    await service.checkOut(outlet.id, fix, "order_requested", "", undefined);
    await s.engine.flush();
    return {
        ...s,
        service,
        fix,
        root: (await store.list(s.owner)).find((r) => r.key === root.key)!,
    };
}
function revised(
    s: Awaited<ReturnType<typeof rejectedOrder>>,
    daily = s.daily,
) {
    const lines = [
        { product_id: "demo-product-2", qty: "2", uom: "pcs" as const },
    ];
    return OrderRevisionSchema.parse({
        revision_version: 1,
        root_uuid: s.root.command.client_uuid,
        supersedes_uuid: s.root.command.client_uuid,
        correction_reason: "Ganti SKU dan diskon",
        outlet_id: daily.snapshot!.outlets[0].id,
        snapshot_version: daily.snapshot!.version,
        business_date: daily.businessDate,
        daily_source: daily,
        lines,
        note: "baru",
        pricing_version: 1,
        discount_request: { percent: 2, reason: "Promo revisi" },
        observed_total: String(
            orderQuote(lines, daily.snapshot!, {
                percent: 2,
                reason: "Promo revisi",
            }).requestedTotal,
        ),
    });
}
it("revises a rejected SO after visit closed, new UUID and receipt, immutable source; replay next day", async () => {
    const s = await rejectedOrder(),
        before = structuredClone(s.root.command),
        child = await submitRevision(
            store,
            s.owner,
            s.root,
            revised(s),
            s.engine,
        );
    await s.engine.flush();
    const latest = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    expect(latest.state).toBe("needs_approval");
    expect(latest.command.client_uuid).not.toBe(s.root.command.client_uuid);
    expect(
        (await store.list(s.owner)).find((r) => r.key === s.root.key)!.command,
    ).toEqual(before);
    await store.decideDemoDiscount(s.owner, latest, true, "Sesuai pengajuan");
    vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    await expect(
        validateRevisionMedia(latest, s.owner, store),
    ).resolves.toBeUndefined();
});
it("correction on next business day stays blocked even with a fresh daily sync", async () => {
    const s = await rejectedOrder();
    vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    await expect(
        submitRevision(store, s.owner, s.root, revised(s), s.engine),
    ).rejects.toThrow();
    await s.morningService.acceptAttendance();
    const daily = await s.morningService.open(),
        p = revised(s, daily);
    const before = await store.list(s.owner);
    await expect(
        submitRevision(store, s.owner, s.root, p, s.engine),
    ).rejects.toThrow("batas hari");
    expect(await store.list(s.owner)).toEqual(before);
    expect(
        await store.draft(s.owner, revisionKey(p.root_uuid)),
    ).toBeUndefined();
});
it("two connections cannot fork revisions; accepted/pending/transport source and bad totals are locked", async () => {
    const s = await rejectedOrder(),
        p = revised(s),
        other = new FieldStore(name);
    try {
        const otherEngine = new Outbox(other, s.owner, s.provider);
        const results = await Promise.allSettled([
            submitRevision(store, s.owner, s.root, p, s.engine),
            submitRevision(other, s.owner, s.root, p, otherEngine),
        ]);
        expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    } finally {
        await other.close();
    }
    await expect(
        submitRevision(store, s.owner, s.root, p, s.engine),
    ).rejects.toThrow();
});
it("revision receipt source changed during commit, mixed principal and changed total do not enqueue", async () => {
    const s = await rejectedOrder(),
        p = revised(s);
    await expect(
        submitRevision(
            store,
            s.owner,
            s.root,
            { ...p, observed_total: "1" },
            s.engine,
        ),
    ).rejects.toThrow("Total");
    const lines = [
            { product_id: "demo-product-3", qty: "1", uom: "pcs" as const },
        ],
        wrong = {
            ...p,
            lines,
            observed_total: String(
                orderQuote(lines, s.daily.snapshot!, p.discount_request)
                    .requestedTotal,
            ),
        };
    await expect(
        submitRevision(store, s.owner, s.root, wrong, s.engine),
    ).rejects.toThrow("Principal");
    const altered = {
        ...s.root,
        receipt: { ...s.root.receipt!, message: "Changed" },
    };
    await store.put(altered);
    await expect(
        submitRevision(store, s.owner, s.root, p, s.engine),
    ).rejects.toThrow("berubah");
    expect(
        (await store.list(s.owner)).filter(
            (r) => r.command.type === "sales.order.revise",
        ),
    ).toHaveLength(0);
});
it.each([0, 1, 2, 3, 4])(
    "reschedule +%i days selects the required approval tiers",
    (days) => {
        expect(
            approvalTiers(
                {
                    kind: "reschedule",
                    requested_date: new Date(Date.UTC(2026, 9, 28 + days))
                        .toISOString()
                        .slice(0, 10),
                },
                "2026-10-28",
            ),
        ).toEqual(days < 3 ? ["spv"] : ["spv", "branch_manager"]);
    },
);
async function pods(request?: DeliveryPod["request"], relaxed = true) {
    const s = await setup("delivery", relaxed);
    await store.draft(
        s.owner,
        `delivery-manifest-v1:${s.daily.businessDate}`,
        s.daily.deliveryManifest,
    );
    const rows = [];
    for (const source of s.daily.deliveryManifest!) {
        const fix = {
                latitude: relaxed ? 10 : source.site.latitude,
                longitude: relaxed ? 100 : source.site.longitude,
                accuracy: relaxed ? 5000 : 3,
                sampled_at: new Date().toISOString(),
            },
            opening = await makeVisitPhoto(store, s.owner, fix),
            session = DeliverySessionSchema.parse({
                id: crypto.randomUUID(),
                owner: s.owner,
                task_id: source.id,
                opened_at: new Date().toISOString(),
                opening,
                pinpoint: fix,
                pinpoint_set_at: new Date().toISOString(),
                daily_source: s.daily,
            });
        await store.openDeliverySession(s.owner, source, session);
        const evidence = await makeVisitPhoto(store, s.owner, fix),
            p: DeliveryPod = {
                pod_version: 1,
                source,
                recipient: "Toko demo",
                session,
                evidence,
                outcome: request
                    ? request.kind === "cancel"
                        ? "cancel_delivery"
                        : "pending_requested"
                    : "delivered",
                delivery_status: request
                    ? request.kind === "cancel"
                        ? "Cancel Delivery"
                        : "Pending Requested"
                    : "Fully Received",
                reason: "Alasan demo",
                ...(request ? { request } : {}),
                lines: source.lines.map((l) => ({
                    id: l.id,
                    received: request ? 0 : l.quantity,
                    reason: "Alasan demo",
                })),
            };
        const uuid = crypto.randomUUID(),
            at = new Date().toISOString();
        rows.push(
            await s.engine.enqueue("delivery.pod.submit", p, "POD", uuid, {
                key: podKey(source),
                expected: undefined,
                value: {
                    schema_version: 1,
                    type: "delivery.pod.submit",
                    client_uuid: uuid,
                    occurred_at: at,
                    payload: p,
                },
                occurredAt: at,
            }),
        );
    }
    await s.engine.flush();
    return { ...s, rows };
}
it("cancel requires SPV; BM cannot bypass SPV; >=3 days needs sequential SPV+BM with reasons", async () => {
    const s = await pods({ kind: "reschedule", requested_date: "2026-10-31" }),
        root = (await store.list(s.owner)).find(
            (r) => r.key === s.rows[0].key,
        )!;
    await expect(
        store.decideDemoDelivery(
            s.owner,
            root,
            "branch_manager",
            true,
            "Approve",
        ),
    ).rejects.toThrow("Urutan");
    await store.decideDemoDelivery(s.owner, root, "spv", true, "SPV setuju");
    const after = (await store.list(s.owner)).find((r) => r.key === root.key)!;
    expect(after.state).toBe("needs_approval");
    await store.decideDemoDelivery(
        s.owner,
        after,
        "branch_manager",
        true,
        "BM setuju",
    );
    expect(
        (await store.list(s.owner)).find((r) => r.key === root.key)!.state,
    ).toBe("accepted");
    expect(
        approvalTiers(
            { kind: "cancel", sub_reason: "Toko Tutup" },
            s.daily.businessDate,
        ),
    ).toEqual(["spv"]);
});
it("closing in demo accepts location outside office, no cash settlement, is once-only and replays next day", async () => {
    const s = await pods(),
        rows = await store.list(s.owner),
        fix = {
            latitude: 10,
            longitude: 100,
            accuracy: 5000,
            sampled_at: new Date().toISOString(),
        },
        p = TripCloseSchema.parse({
            trip_id: s.daily.deliveryManifest![0].trip,
            business_date: s.daily.businessDate,
            daily_source: s.daily,
            office: DEMO_OFFICE,
            fix,
            pod_uuids: rows
                .filter((r) => r.command.type === "delivery.pod.submit")
                .map((r) => r.command.client_uuid)
                .sort(),
            demo_unrestricted: true,
        }),
        uuid = crypto.randomUUID(),
        at = new Date().toISOString(),
        draft = {
            key: tripCloseKey(p.trip_id, p.business_date),
            expected: undefined,
            value: {
                schema_version: 1,
                type: "delivery.trip.close",
                client_uuid: uuid,
                occurred_at: at,
                payload: p,
            },
            occurredAt: at,
        };
    const closed = await s.engine.enqueue(
        "delivery.trip.close",
        p,
        "Close",
        uuid,
        draft,
    );
    validateTripClose(closed, rows, s.owner);
    await expect(
        s.engine.enqueue(
            "delivery.trip.close",
            p,
            "Close",
            crypto.randomUUID(),
            draft,
        ),
    ).rejects.toThrow();
    const first = s.rows[0];
    if (first.command.type !== "delivery.pod.submit")
        throw new Error("fixture");
    await expect(
        store.openDeliverySession(s.owner, first.command.payload.source, {
            ...first.command.payload.session,
            id: crypto.randomUUID(),
        }),
    ).rejects.toThrow("Trip sudah closed");
    vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    await setup("delivery"); // current morning must not reinterpret a historic closing
    await expect(
        validateTripCloseMedia(closed, s.owner, store),
    ).resolves.toBeUndefined();
});
it("demo only relaxes geography; strict legacy location and corrupt package checks remain", () => {
    const fix = {
            latitude: 10,
            longitude: 100,
            accuracy: 5000,
            sampled_at: new Date().toISOString(),
        },
        site = { latitude: 1, longitude: 120, radius: 15 };
    expect(() => requireVisitFix(fix, site)).toThrow();
    expect(() =>
        requireVisitFix(fix, { ...site, demo_unrestricted: true }),
    ).not.toThrow();
    expect(() =>
        approvalTiers(
            { kind: "reschedule", requested_date: "2026-10-27" },
            "2026-10-28",
        ),
    ).toThrow();
});

it("strict closing accepts office radius plus exactly25m tolerance; extra uncertainty is rejected", async () => {
    const s = await pods(undefined, false),
        rows = await store.list(s.owner),
        at = new Date().toISOString(),
        uuid = crypto.randomUUID();
    const payload = TripCloseSchema.parse({
        trip_id: s.daily.deliveryManifest![0].trip,
        business_date: s.daily.businessDate,
        daily_source: s.daily,
        office: DEMO_OFFICE,
        fix: {
            latitude: DEMO_OFFICE.latitude,
            longitude: DEMO_OFFICE.longitude,
            accuracy: 55,
            sampled_at: at,
        },
        pod_uuids: rows
            .filter((r) => r.command.type === "delivery.pod.submit")
            .map((r) => r.command.client_uuid)
            .sort(),
    });
    const row = {
        key: `${s.owner}:${uuid}`,
        owner: s.owner,
        label: "Close",
        state: "queued" as const,
        attempts: 0,
        nextAttempt: 0,
        command: {
            schema_version: 1 as const,
            client_uuid: uuid,
            occurred_at: at,
            type: "delivery.trip.close" as const,
            payload,
        },
    };
    expect(() => validateTripClose(row, rows, s.owner)).not.toThrow();
    expect(() =>
        validateTripClose(
            {
                ...row,
                command: {
                    ...row.command,
                    payload: {
                        ...payload,
                        fix: { ...payload.fix, accuracy: 55.01 },
                    },
                },
            },
            rows,
            s.owner,
        ),
    ).toThrow("toleransi25m");
});
it("pending/accepted/transport rejection never authorize an SO revision", async () => {
    const s = await rejectedOrder(),
        p = revised(s);
    for (const state of ["accepted", "needs_approval", "rejected"] as const) {
        const row = {
            ...s.root,
            state,
            ...(state === "rejected"
                ? { receipt: undefined }
                : { receipt: { ...s.root.receipt!, status: state } }),
        };
        await store.put(row);
        await expect(
            submitRevision(store, s.owner, row, p, s.engine),
        ).rejects.toThrow();
        expect(
            (await store.list(s.owner)).filter(
                (r) => r.command.type === "sales.order.revise",
            ),
        ).toHaveLength(0);
    }
});
it("a persisted revision cycle is held without deleting its command, draft or parent", async () => {
    const s = await rejectedOrder(),
        p = revised(s),
        child = await submitRevision(store, s.owner, s.root, p, s.engine);
    if (child.command.type !== "sales.order.revise") throw new Error("fixture");
    const broken = {
        ...child,
        command: {
            ...child.command,
            payload: {
                ...child.command.payload,
                supersedes_uuid: child.command.client_uuid,
            },
        },
    };
    await store.put(broken);
    const before = await store.list(s.owner);
    await expect(validateRevisionMedia(broken, s.owner, store)).rejects.toThrow(
        "review",
    );
    expect(await store.list(s.owner)).toEqual(before);
    expect(await store.draft(s.owner, revisionKey(p.root_uuid))).toEqual(
        child.command,
    );
});

it("revision without a discount still requires a fresh approval", async () => {
    const s = await rejectedOrder(),
        p = revised(s);
    delete p.discount_request;
    p.observed_total = String(
        orderQuote(p.lines, s.daily.snapshot!).requestedTotal,
    );
    const child = await submitRevision(store, s.owner, s.root, p, s.engine);
    await s.engine.flush();
    const pending = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    expect(pending.state).toBe("needs_approval");
    await store.decideDemoDiscount(
        s.owner,
        pending,
        true,
        "Revisi tanpa diskon disetujui",
    );
    expect(
        (await store.list(s.owner)).find((r) => r.key === child.key)!.state,
    ).toBe("accepted");
});

it("reconnect cannot mutate a queued row while revision media integrity reads its snapshot", async () => {
    const s = await rejectedOrder(),
        child = await submitRevision(
            store,
            s.owner,
            s.root,
            revised(s),
            s.engine,
        );
    const unrelated = await s.engine.enqueue(
        "field_expense.request",
        {},
        "Unrelated pending",
    );
    await store.put({ ...unrelated, nextAttempt: Date.now() + 60000 });
    let release!: () => void,
        entered!: () => void,
        once = false;
    const barrier = new Promise<void>((r) => {
            release = r;
        }),
        started = new Promise<void>((r) => {
            entered = r;
        });
    const original = store.getEvidence.bind(store);
    vi.spyOn(store, "getEvidence").mockImplementation(async (owner, id) => {
        if (!once) {
            once = true;
            entered();
            await barrier;
        }
        return original(owner, id);
    });
    const sending = s.engine.flush();
    await started;
    const reconnect = s.engine.retry();
    // No arbitrary delay: the retry reserves the engine synchronously and is
    // blocked by the explicit media barrier, so its writes cannot have started.
    expect(
        (await store.list(s.owner)).find((r) => r.key === unrelated.key)!
            .nextAttempt,
    ).toBeGreaterThan(Date.now());
    release();
    await Promise.all([sending, reconnect]);
    const after = (await store.list(s.owner)).find((r) => r.key === child.key)!;
    expect(after.state).toBe("needs_approval");
    expect(after.evidenceHold).toBeUndefined();
    expect(after.error).toBeUndefined();
});

for (const tamper of [false, true]) {
    it(`POD evidence tolerates transport progress but detects command mutation during closing, tamper=${tamper}`, async () => {
        const s = await pods(),
            row = s.rows[0];
        const original = store.getEvidence.bind(store);
        let once = false;
        vi.spyOn(store, "getEvidence").mockImplementation(async (owner, id) => {
            if (!once) {
                once = true;
                const current = (await store.list(s.owner)).find(
                    (r) => r.key === row.key,
                )!;
                await store.put({
                    ...current,
                    state: "sending",
                    attempts: current.attempts + 1,
                    ...(tamper
                        ? {
                              command: {
                                  ...current.command,
                                  occurred_at: new Date(
                                      Date.now() + 1,
                                  ).toISOString(),
                              },
                          }
                        : {}),
                });
            }
            return original(owner, id);
        });
        if (tamper)
            await expect(validatePodMedia(row, s.owner, store)).rejects.toThrow(
                "POD/manifest/foto",
            );
        else
            await expect(
                validatePodMedia(row, s.owner, store),
            ).resolves.toBeUndefined();
    });
}

for (const mismatch of [
    "day",
    "trip",
    "version",
    "quantity",
    "owner",
] as const) {
    it(`closing binds complete POD source to its daily manifest: ${mismatch}`, async () => {
        const s = await pods();
        const before = await store.list(s.owner);
        let daily = structuredClone(s.daily);
        if (mismatch === "day") {
            vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
            daily = (await setup("delivery")).daily;
        } else {
            for (const task of daily.deliveryManifest!) {
                if (mismatch === "trip") task.trip += "-changed";
                if (mismatch === "version") task.version += "-changed";
                if (mismatch === "quantity") task.lines[0].quantity++;
                if (mismatch === "owner") task.owner = "other-owner";
            }
            await store.draft(s.owner, "morning-session-v1", daily);
        }
        const payload = TripCloseSchema.parse({
            trip_id: daily.deliveryManifest![0].trip,
            business_date: daily.businessDate,
            daily_source: daily,
            office: DEMO_OFFICE,
            fix: {
                latitude: 10,
                longitude: 100,
                accuracy: 5000,
                sampled_at: new Date().toISOString(),
            },
            pod_uuids: s.rows.map((r) => r.command.client_uuid).sort(),
            demo_unrestricted: true,
        });
        const uuid = crypto.randomUUID(),
            at = new Date().toISOString();
        const command = {
            schema_version: 1 as const,
            client_uuid: uuid,
            occurred_at: at,
            type: "delivery.trip.close" as const,
            payload,
        };
        const row = {
            key: `${s.owner}:${uuid}`,
            owner: s.owner,
            label: "Bad close",
            state: "queued" as const,
            attempts: 0,
            nextAttempt: 0,
            command,
        };
        // Preview, atomic commit, and restore/pre-sync must share this guard.
        expect(() =>
            tripPods(before, s.owner, daily, payload.trip_id),
        ).toThrow();
        await expect(
            s.engine.enqueue(
                "delivery.trip.close",
                payload,
                "Bad close",
                uuid,
                {
                    key: tripCloseKey(payload.trip_id, payload.business_date),
                    expected: undefined,
                    value: command,
                    occurredAt: at,
                },
            ),
        ).rejects.toThrow();
        expect(await store.list(s.owner)).toEqual(before);
        expect(
            await store.draft(
                s.owner,
                tripCloseKey(payload.trip_id, payload.business_date),
            ),
        ).toBeUndefined();
        await store.draft(
            s.owner,
            tripCloseKey(payload.trip_id, payload.business_date),
            command,
        );
        await expect(
            validateTripCloseMedia(row, s.owner, store),
        ).rejects.toThrow("Closing/sumber trip");
    });
}

it.each([true, false])(
    "new revision decision after midnight WITA is blocked without changing pending/cached receipt, approve=%s",
    async (approve) => {
        const s = await rejectedOrder();
        const child = await submitRevision(
            store,
            s.owner,
            s.root,
            revised(s),
            s.engine,
        );
        await s.engine.flush();
        const pending = (await store.list(s.owner)).find(
            (r) => r.key === child.key,
        )!;
        vi.setSystemTime(new Date("2026-10-28T16:00:00Z"));
        const before = await store.list(s.owner),
            cached = await store.receipt(
                `DEMO-ANDRE:sales.order.revise:${child.command.client_uuid}`,
            );
        await expect(
            store.decideDemoDiscount(
                s.owner,
                pending,
                approve,
                "Keputusan terlambat",
            ),
        ).rejects.toThrow("batas hari");
        const other = new FieldStore(name);
        try {
            const attempts = await Promise.allSettled([
                store.decideDemoDiscount(
                    s.owner,
                    pending,
                    approve,
                    "Tab pertama lewat batas",
                ),
                other.decideDemoDiscount(
                    s.owner,
                    pending,
                    approve,
                    "Tab kedua lewat batas",
                ),
            ]);
            expect(
                attempts.every(
                    (result) =>
                        result.status === "rejected" &&
                        String(result.reason).includes("batas hari"),
                ),
            ).toBe(true);
        } finally {
            await other.close();
        }
        expect(await store.list(s.owner)).toEqual(before);
        expect(
            await store.receipt(
                `DEMO-ANDRE:sales.order.revise:${child.command.client_uuid}`,
            ),
        ).toEqual(cached);
    },
);

it("revision and manager decision at 23:59:59.999 WITA succeed; replay of the cached decision next day is not a new approval", async () => {
    const s = await rejectedOrder();
    vi.setSystemTime(new Date("2026-10-28T15:59:59.999Z"));
    const child = await submitRevision(
        store,
        s.owner,
        s.root,
        revised(s),
        s.engine,
    );
    await s.engine.flush();
    const pending = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    await store.decideDemoDiscount(
        s.owner,
        pending,
        true,
        "Disetujui sebelum batas",
    );
    const accepted = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    vi.setSystemTime(new Date("2026-10-28T16:00:00Z"));
    await setup();
    await expect(
        validateRevisionMedia(accepted, s.owner, store),
    ).resolves.toBeUndefined();
    expect(await s.provider.submit(accepted.command)).toEqual(accepted.receipt);
    expect(
        (await store.list(s.owner)).find((r) => r.key === child.key),
    ).toEqual(accepted);
});
it("a valid offline revision sent next day stays pending; no automatic business decision", async () => {
    const s = await rejectedOrder();
    const child = await submitRevision(
        store,
        s.owner,
        s.root,
        revised(s),
        s.engine,
    );
    vi.setSystemTime(new Date("2026-10-28T16:00:00Z"));
    await setup();
    await s.engine.retry();
    const pending = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    expect(pending.state).toBe("needs_approval");
    await expect(
        store.decideDemoDiscount(
            s.owner,
            pending,
            true,
            "Khair setelah lewat hari",
        ),
    ).rejects.toThrow("batas hari");
    expect(
        (await store.list(s.owner)).find((r) => r.key === child.key),
    ).toEqual(pending);
});
it.each(["revision", "decision"] as const)(
    "midnight during atomic %s writes rolls back all outbox/pointer/receipt changes",
    async (kind) => {
        const s = await rejectedOrder(),
            p = revised(s);
        let pending: typeof s.root | undefined;
        if (kind === "decision") {
            const child = await submitRevision(
                store,
                s.owner,
                s.root,
                p,
                s.engine,
            );
            await s.engine.flush();
            pending = (await store.list(s.owner)).find(
                (r) => r.key === child.key,
            )!;
        }
        const before = await store.list(s.owner),
            pointer = await store.draft(s.owner, revisionKey(p.root_uuid));
        const receiptKey = pending
            ? `DEMO-ANDRE:sales.order.revise:${pending.command.client_uuid}`
            : "unused";
        const cache = await store.receipt(receiptKey);
        vi.setSystemTime(new Date("2026-10-28T15:59:59.999Z"));
        const method = kind === "revision" ? "add" : "put";
        const original = IDBObjectStore.prototype[method];
        let crossed = false;
        const spy = vi
            .spyOn(IDBObjectStore.prototype, method)
            .mockImplementation(function (
                this: IDBObjectStore,
                value: any,
                key?: IDBValidKey,
            ) {
                const request = original.call(this, value, key);
                if (
                    !crossed &&
                    this.name === "outbox" &&
                    value.command?.type === "sales.order.revise"
                ) {
                    crossed = true;
                    vi.setSystemTime(new Date("2026-10-28T16:00:00Z"));
                }
                return request;
            });
        try {
            if (pending)
                await expect(
                    store.decideDemoDiscount(
                        s.owner,
                        pending,
                        true,
                        "Aksi bersamaan midnight",
                    ),
                ).rejects.toThrow("batas hari");
            else
                await expect(
                    submitRevision(store, s.owner, s.root, p, s.engine),
                ).rejects.toThrow("batas hari");
            expect(crossed).toBe(true);
        } finally {
            spy.mockRestore();
        }
        expect(await store.list(s.owner)).toEqual(before);
        expect(await store.draft(s.owner, revisionKey(p.root_uuid))).toEqual(
            pointer,
        );
        expect(await store.receipt(receiptKey)).toEqual(cache);
    },
);
it("backdating a new command or changing the last parent's date does not extend the root deadline", async () => {
    const s = await rejectedOrder(),
        p = revised(s);
    const child = await submitRevision(store, s.owner, s.root, p, s.engine);
    await s.engine.flush();
    const pending = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    await store.decideDemoDiscount(
        s.owner,
        pending,
        false,
        "Perlu koreksi lain",
    );
    vi.setSystemTime(new Date("2026-10-29T01:00:00Z"));
    const daily = (await setup()).daily;
    const parent = (await store.list(s.owner)).find(
        (r) => r.key === child.key,
    )!;
    const next = {
        ...revised(s, daily),
        supersedes_uuid: child.command.client_uuid,
    };
    const uuid = crypto.randomUUID(),
        at = "2026-10-28T15:59:59.999Z";
    const before = await store.list(s.owner),
        pointer = await store.draft(s.owner, revisionKey(p.root_uuid));
    await expect(
        s.engine.enqueue("sales.order.revise", next, "Backdated", uuid, {
            key: revisionKey(p.root_uuid),
            expected: parent.command,
            guards: { source: parent },
            occurredAt: at,
            value: {
                schema_version: 1,
                client_uuid: uuid,
                occurred_at: at,
                type: "sales.order.revise",
                payload: next,
            },
        }),
    ).rejects.toThrow("batas hari");
    expect(await store.list(s.owner)).toEqual(before);
    expect(await store.draft(s.owner, revisionKey(p.root_uuid))).toEqual(
        pointer,
    );
    const forged = {
        ...pending,
        command: {
            ...pending.command,
            occurred_at: new Date().toISOString(),
            payload: {
                ...pending.command.payload,
                business_date: daily.businessDate,
                daily_source: daily,
            },
        },
    };
    await store.put(forged as typeof pending);
    const saved = await store.list(s.owner);
    await expect(
        store.decideDemoDiscount(
            s.owner,
            forged as typeof pending,
            true,
            "Tanggal parent baru",
        ),
    ).rejects.toThrow();
    expect(await store.list(s.owner)).toEqual(saved);
});
