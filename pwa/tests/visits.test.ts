import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { FieldStore } from "../src/storage/store";
import { MockProvider } from "../src/data/mock";
import { Outbox } from "../src/domain/outbox";
import { MorningSimulation, MORNING_KEY } from "../src/domain/morning";
import { ownerKey } from "../src/domain/contracts";
import { PhotoSalesVisits as SalesVisits } from "./visit-fixtures";
import { assessVisitFix, VISITS_KEY } from "../src/domain/visit-validation";
import type { VisitFix, VisitLedger } from "../src/domain/visit-contracts";
let store: FieldStore, dbName: string;
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
async function setup(actor = "sales") {
    const provider = new MockProvider(actor),
        identity = await provider.bootstrap(),
        owner = ownerKey(identity),
        outbox = new Outbox(store, owner, provider),
        morningService = new MorningSimulation(store, identity, provider);
    await morningService.acceptAttendance();
    const morning = await morningService.open(),
        outlet = morning.snapshot!.outlets[0];
    const service = new SalesVisits(store, identity, provider, outbox);
    const fix: VisitFix = {
        latitude: outlet.latitude,
        longitude: outlet.longitude,
        accuracy: 3,
        sampled_at: new Date().toISOString(),
    };
    const payload = {
        outlet_id: outlet.id,
        work_session_id: morning.sessionId!,
        morning_business_date: morning.businessDate,
        snapshot_version: morning.snapshot!.version,
        lines: [
            {
                product_id: morning.snapshot!.products[0].id,
                qty: "2",
                uom: "carton",
            },
        ],
        note: "",
        observed_total: "1",
    };
    return {
        provider,
        identity,
        owner,
        outbox,
        morningService,
        morning,
        outlet,
        service,
        fix,
        payload,
    };
}
it("uses distance plus accuracy without expanding the 5-15m radius and rejects stale/future/invalid fixes", () => {
    const site = { latitude: 1.465, longitude: 124.833, radius: 15 },
        fix = { ...site, accuracy: 3, sampled_at: new Date().toISOString() };
    const { radius: _, ...point } = fix;
    void _;
    expect(assessVisitFix(point, site).status).toBe("inside");
    expect(assessVisitFix({ ...point, accuracy: 30 }, site).status).toBe(
        "uncertain",
    );
    expect(assessVisitFix({ ...point, latitude: 1.466 }, site).status).toBe(
        "outside",
    );
    expect(
        assessVisitFix(
            {
                ...point,
                sampled_at: new Date(Date.now() - 60001).toISOString(),
            },
            site,
        ).status,
    ).toBe("stale");
    expect(
        assessVisitFix(
            { ...point, sampled_at: new Date(Date.now() + 1001).toISOString() },
            site,
        ).status,
    ).toBe("future");
    expect(assessVisitFix({ ...point, latitude: 100 }, site).status).toBe(
        "invalid",
    );
    expect(assessVisitFix(point, { ...site, radius: 100 }).status).toBe(
        "inside",
    );
    expect(assessVisitFix(point, { ...site, radius: 200 }).status).toBe(
        "invalid",
    );
});
it("records check-in/order/check-out offline and flushes in dependency order even with reversed UUID ordering", async () => {
    const c = await setup();
    vi.stubGlobal("navigator", { onLine: false });
    const start = await c.service.checkIn(c.outlet.id, c.fix),
        order = await c.service.submitOrder(c.payload, c.fix),
        end = await c.service.checkOut(
            c.outlet.id,
            c.fix,
            "order_requested",
            "",
        );
    const orig = store.list.bind(store);
    vi.spyOn(store, "list").mockImplementation(async (owner) =>
        (await orig(owner)).sort((a, b) =>
            a.command.type === "sales.visit.check_in"
                ? 1
                : b.command.type === "sales.visit.check_in"
                  ? -1
                  : a.command.type === "sales.visit.check_out"
                    ? -1
                    : 1,
        ),
    );
    const sent: string[] = [];
    const submit = c.provider.submit.bind(c.provider);
    vi.spyOn(c.provider, "submit").mockImplementation(async (cmd) => {
        sent.push(cmd.client_uuid);
        return submit(cmd);
    });
    vi.stubGlobal("navigator", { onLine: true });
    await c.outbox.flush();
    expect(sent).toEqual([
        start.command.client_uuid,
        order.command.client_uuid,
        end.command.client_uuid,
    ]);
    expect(
        (await c.service.restore(c.outlet.id)).selected?.check_out?.payload
            .outcome,
    ).toBe("order_requested");
    expect((await orig(c.owner)).every((q) => q.state === "accepted")).toBe(
        true,
    );
    await c.outbox.flush();
    expect(sent).toHaveLength(3);
});
it("holds dependent orders when check-in is denied or needs approval", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    await c.service.submitOrder(c.payload, c.fix);
    c.provider.scenario = "rejected";
    const spy = vi.spyOn(c.provider, "submit");
    await c.outbox.flush();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(
        (await store.list(c.owner)).find(
            (q) => q.command.type === "sales.order.submit",
        )?.state,
    ).toBe("queued");
    await expect(c.service.submitOrder(c.payload, c.fix)).rejects.toThrow(
        "ditahan/ditolak",
    );
});
it("requires morning session, correct PJP/owner and conservative geo proof for each action", async () => {
    const c = await setup();
    await expect(c.service.submitOrder(c.payload, c.fix)).rejects.toThrow(
        "Mulai kunjungan",
    );
    await expect(c.service.checkIn("not-PJP", c.fix)).rejects.toThrow(
        "Extra call",
    );
    await expect(
        c.service.checkIn(c.outlet.id, { ...c.fix, accuracy: 100 }),
    ).rejects.toThrow("Akurasi");
    await c.service.checkIn(c.outlet.id, c.fix);
    await expect(
        c.service.submitOrder(c.payload, { ...c.fix, latitude: 0 }),
    ).rejects.toThrow("luar geofence");
    await expect(
        c.service.checkOut(
            c.outlet.id,
            { ...c.fix, latitude: 0 },
            "no_order",
            "Outlet ditinjau",
        ),
    ).rejects.toThrow("luar geofence");
    const other = new MockProvider("canvass"),
        otherId = await other.bootstrap();
    await expect(
        new SalesVisits(
            store,
            otherId,
            other,
            new Outbox(store, ownerKey(otherId), other),
        ).restore(c.outlet.id),
    ).rejects.toThrow("Sesi pagi");
    vi.setSystemTime(new Date("2026-10-27T16:00:00Z"));
    await expect(
        c.service.submitOrder(c.payload, {
            ...c.fix,
            sampled_at: new Date().toISOString(),
        }),
    ).rejects.toThrow("Sesi pagi");
});
it("does not close a no-order visit without a reason, misreport an existing order, or create new orders after closing", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    await expect(
        c.service.checkOut(c.outlet.id, c.fix, "no_order", ""),
    ).rejects.toThrow("Hasil kunjungan");
    await c.service.submitOrder(c.payload, c.fix);
    await expect(
        c.service.checkOut(c.outlet.id, c.fix, "no_order", "Alasan lengkap"),
    ).rejects.toThrow("Hasil kunjungan");
    await c.service.checkOut(c.outlet.id, c.fix, "order_requested", "");
    await expect(c.service.submitOrder(c.payload, c.fix)).rejects.toThrow(
        "Mulai kunjungan",
    );
    await expect(c.service.checkIn(c.outlet.id, c.fix)).rejects.toThrow(
        "sudah dikunjungi",
    );
});
it("prevents concurrent active visits across two connections", async () => {
    const c = await setup(),
        db2 = new FieldStore(dbName),
        s2 = new SalesVisits(
            db2,
            c.identity,
            c.provider,
            new Outbox(db2, c.owner, c.provider),
        );
    const next = c.morning.snapshot!.outlets[1],
        fix = { ...c.fix, latitude: next.latitude, longitude: next.longitude };
    const results = await Promise.allSettled([
        c.service.checkIn(c.outlet.id, c.fix),
        s2.checkIn(next.id, fix),
    ]);
    expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    expect(
        (await store.list(c.owner)).filter(
            (q) => q.command.type === "sales.visit.check_in",
        ),
    ).toHaveLength(1);
    await db2.close();
});
it("rechecks source morning and active visit at the atomic write boundary", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    const original = store.putWithDraft.bind(store);
    vi.spyOn(store, "putWithDraft").mockImplementationOnce(async (...args) => {
        await store.draft(c.owner, MORNING_KEY, {
            ...c.morning,
            snapshot: { ...c.morning.snapshot!, version: "changed" },
        });
        return original(...args);
    });
    await expect(c.service.submitOrder(c.payload, c.fix)).rejects.toThrow(
        "paket pagi berubah",
    );
    expect(
        (await store.list(c.owner)).filter(
            (q) => q.command.type === "sales.order.submit",
        ),
    ).toHaveLength(0);
});
it("order/check-out race cannot append an order to a closed visit", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    const db2 = new FieldStore(dbName),
        s2 = new SalesVisits(
            db2,
            c.identity,
            c.provider,
            new Outbox(db2, c.owner, c.provider),
        );
    const original = store.putWithDraft.bind(store);
    vi.spyOn(store, "putWithDraft").mockImplementationOnce(async (...args) => {
        await s2.checkOut(
            c.outlet.id,
            c.fix,
            "no_order",
            "Selesai tanpa order",
        );
        return original(...args);
    });
    await expect(c.service.submitOrder(c.payload, c.fix)).rejects.toThrow(
        "tab lain",
    );
    expect(
        (await store.list(c.owner)).filter(
            (q) => q.command.type === "sales.order.submit",
        ),
    ).toHaveLength(0);
    await db2.close();
});
it("restore rejects corrupt geo/context/history without deleting queued transactions", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    const before = await store.list(c.owner),
        ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
    for (const corrupt of [
        { ...ledger, visits: [{ ...ledger.visits[0], owner: "other" }] },
        {
            ...ledger,
            visits: [
                {
                    ...ledger.visits[0],
                    context: {
                        ...ledger.visits[0].context,
                        fix: { ...c.fix, accuracy: 100 },
                    },
                },
            ],
        },
        { version: 1, visits: [] },
    ]) {
        await store.draft(c.owner, VISITS_KEY, corrupt);
        await expect(c.service.restore(c.outlet.id)).rejects.toThrow();
        expect(await store.list(c.owner)).toEqual(before);
    }
});
it("quota/transaction failure leaves no orphan visit command or false active status", async () => {
    const c = await setup();
    vi.spyOn(store, "putWithDraft").mockRejectedValueOnce(new Error("quota"));
    await expect(c.service.checkIn(c.outlet.id, c.fix)).rejects.toThrow(
        "quota",
    );
    expect(await store.list(c.owner)).toHaveLength(0);
    expect((await c.service.restore(c.outlet.id)).active).toBeUndefined();
});

it.each([
    "sales.visit.check_in",
    "sales.order.submit",
    "sales.visit.check_out",
] as const)(
    "holds corrupt persisted %s and descendants on reload, flush and retry without deleting data",
    async (type) => {
        const c = await setup();
        await c.service.checkIn(c.outlet.id, c.fix);
        await c.service.submitOrder(c.payload, c.fix);
        await c.service.checkOut(c.outlet.id, c.fix, "order_requested", "");
        const rows = await store.list(c.owner);
        const broken = rows.find((q) => q.command.type === type)!;
        const body = broken.command.payload as Record<string, unknown>;
        const context = (
            type === "sales.order.submit" ? body.visit_context : body
        ) as { fix: VisitFix };
        context.fix.latitude = 0;
        await store.put(broken);
        const before = await store.list(c.owner),
            ledger = await store.draft(c.owner, VISITS_KEY);
        await store.close();
        store = new FieldStore(dbName);
        const engine = new Outbox(store, c.owner, c.provider);
        const restored = new SalesVisits(store, c.identity, c.provider, engine);
        await expect(restored.restore(c.outlet.id)).rejects.toThrow();
        const send = vi.spyOn(c.provider, "submit");
        await engine.flush();
        await engine.retry();
        expect(send).not.toHaveBeenCalled();
        const after = await store.list(c.owner);
        expect(after.map((q) => q.command)).toEqual(
            before.map((q) => q.command),
        );
        expect(
            after.every(
                (q) =>
                    q.state === "queued" &&
                    !q.receipt &&
                    q.attempts === 0 &&
                    q.error?.includes("review"),
            ),
        ).toBe(true);
        expect(await store.draft(c.owner, VISITS_KEY)).toEqual(ledger);
    },
);
it.each([
    "parent-geo",
    "parent-session",
    "order-outlet",
    "checkout-session",
    "missing-ledger",
    "missing-source",
    "historical-source",
    "owner",
    "command-time",
    "envelope",
])(
    "holds invalid graph %s even with accepted parent receipts",
    async (mutation) => {
        const c = await setup();
        const first = await c.service.checkIn(c.outlet.id, c.fix);
        await c.outbox.flush();
        expect((await store.list(c.owner))[0].state).toBe("accepted");
        const order = await c.service.submitOrder(c.payload, c.fix);
        const end = await c.service.checkOut(
            c.outlet.id,
            c.fix,
            "order_requested",
            "",
        );
        const rows = await store.list(c.owner);
        const parent = rows.find((q) => q.key === first.key)!;
        if (
            parent.command.type !== "sales.visit.check_in" ||
            order.command.type !== "sales.order.submit" ||
            end.command.type !== "sales.visit.check_out"
        )
            throw new Error("type");
        const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
        switch (mutation) {
            case "parent-geo":
                parent.command.payload.fix.latitude = 0;
                await store.put(parent);
                break;
            case "parent-session":
                parent.command.payload.work_session_id = crypto.randomUUID();
                await store.put(parent);
                break;
            case "order-outlet":
                order.command.payload.outlet_id = "other";
                await store.put(order);
                break;
            case "checkout-session":
                end.command.payload.work_session_id = crypto.randomUUID();
                await store.put(end);
                break;
            case "missing-ledger":
                await store.draft(c.owner, VISITS_KEY, {
                    version: 1,
                    visits: [],
                });
                break;
            case "missing-source":
                delete ledger.visits[0].morning_source;
                await store.draft(c.owner, VISITS_KEY, ledger);
                await store.draft(c.owner, MORNING_KEY, {});
                break;
            case "historical-source":
                ledger.visits[0].morning_source = {
                    ...c.morning,
                    snapshot: { ...c.morning.snapshot!, products: [] },
                };
                await store.draft(c.owner, VISITS_KEY, ledger);
                break;
            case "owner":
                ledger.visits[0].owner = "other";
                await store.draft(c.owner, VISITS_KEY, ledger);
                break;
            case "command-time":
                order.command.occurred_at = "2026-10-26T00:00:00Z";
                await store.put(order);
                break;
            case "envelope":
                (order.command as { schema_version: number }).schema_version =
                    99;
                await store.put(order);
                break;
        }
        const send = vi.spyOn(c.provider, "submit");
        await expect(c.service.restore(c.outlet.id)).rejects.toThrow();
        await c.outbox.flush();
        await c.outbox.retry();
        expect(send).not.toHaveBeenCalled();
        expect(
            (await store.list(c.owner)).filter((q) => q.state === "queued"),
        ).toHaveLength(2);
        expect(
            (await store.list(c.owner)).find((q) => q.key === first.key)
                ?.receipt?.status,
        ).toBe("accepted");
    },
);
it("replays valid historical visits after morning is replaced the next day using event-time GPS and original source", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    await c.service.submitOrder(c.payload, c.fix);
    await c.service.checkOut(c.outlet.id, c.fix, "order_requested", "");
    vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
    await c.morningService.acceptAttendance();
    await c.morningService.open();
    await store.close();
    store = new FieldStore(dbName);
    const send = vi.spyOn(c.provider, "submit");
    await new Outbox(store, c.owner, c.provider).flush();
    expect(send.mock.calls.map(([cmd]) => cmd.type)).toEqual([
        "sales.visit.check_in",
        "sales.order.submit",
        "sales.visit.check_out",
    ]);
    expect(
        (await store.list(c.owner)).every((q) => q.state === "accepted"),
    ).toBe(true);
});
it("supports legacy unbound orders and a matching legacy visit source, but never guesses a missing historical source", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
    delete ledger.visits[0].morning_source;
    await store.draft(c.owner, VISITS_KEY, ledger);
    await c.outbox.flush();
    expect((await store.list(c.owner))[0].state).toBe("accepted");
    await c.outbox.enqueue(
        "sales.order.submit",
        { outlet_id: "legacy-outlet", lines: [] },
        "Legacy order",
    );
    await store.draft(c.owner, VISITS_KEY, { version: 1, visits: [] });
    const send = vi.spyOn(c.provider, "submit");
    await c.outbox.flush();
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0].type).toBe("sales.order.submit");
});
it.each(["geo", "source", "stale-fix", "unknown-product", "dropped-context"])(
    "shares semantic restore/send checks for consistent but invalid %s",
    async (mutation) => {
        const c = await setup();
        await c.service.checkIn(c.outlet.id, c.fix);
        const order = await c.service.submitOrder(c.payload, c.fix);
        const ledger = (await store.draft(c.owner, VISITS_KEY)) as VisitLedger;
        const first = (await store.list(c.owner)).find(
            (q) => q.command.type === "sales.visit.check_in",
        )!;
        if (
            first.command.type !== "sales.visit.check_in" ||
            order.command.type !== "sales.order.submit"
        )
            throw new Error("type");
        if (mutation === "geo") {
            first.command.payload.fix.latitude = 0;
            ledger.visits[0].context.fix.latitude = 0;
            await store.put(first);
        }
        if (mutation === "source") {
            first.command.payload.site.latitude = 0;
            ledger.visits[0].context.site.latitude = 0;
            await store.put(first);
        }
        if (mutation === "stale-fix") {
            first.command.payload.fix.sampled_at = "2026-10-26T23:58:59Z";
            ledger.visits[0].context.fix.sampled_at = "2026-10-26T23:58:59Z";
            await store.put(first);
        }
        if (mutation === "unknown-product") {
            order.command.payload.lines = [
                { product_id: "unknown", qty: "1", uom: "carton" },
            ];
            await store.put(order);
        }
        if (mutation === "dropped-context") {
            delete order.command.payload.visit_context;
            await store.put(order);
        }
        await store.draft(c.owner, VISITS_KEY, ledger);
        const send = vi.spyOn(c.provider, "submit");
        await c.outbox.flush();
        await c.outbox.retry();
        expect(send).not.toHaveBeenCalled();
    },
);
it("rechecks the persisted graph after marking sending and before the provider boundary", async () => {
    const c = await setup();
    await c.service.checkIn(c.outlet.id, c.fix);
    const put = store.put.bind(store);
    vi.spyOn(store, "put").mockImplementation(async (item) => {
        await put(item);
        if (item.state === "sending")
            await store.draft(c.owner, VISITS_KEY, { version: 1, visits: [] });
    });
    const send = vi.spyOn(c.provider, "submit");
    await c.outbox.flush();
    expect(send).not.toHaveBeenCalled();
    const [row] = await store.list(c.owner);
    expect(row.state).toBe("queued");
    expect(row.receipt).toBeUndefined();
    expect(row.error).toContain("review");
});
