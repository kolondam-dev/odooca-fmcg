import { afterEach, expect, it, vi } from "vitest";
import { mapCatalogProducts } from "../src/data/catalog";
import { HttpProvider } from "../src/data/provider";
import { SnapshotSchema, type Snapshot } from "../src/domain/contracts";
import { PackagingSchema, productPackaging } from "../src/domain/product-units";
import { orderQuote, validateOrderQuote } from "../src/domain/order-pricing";
import { MorningRecordSchema, morningReady } from "../src/domain/morning";
import { MockProvider } from "../src/data/mock";
const row = {
    product_id: 41,
    default_code: "SKU-41",
    name: "SKU contoh",
    principal_id: 7,
    brand_name: "Brand",
    carton_qty: 24,
    inner_qty: 6,
    price_per_carton: 24000,
    stock_cartons: 1.5,
};
function catalog(): Snapshot {
    return SnapshotSchema.parse({
        catalog_version: 2,
        scope: {
            company_id: "c",
            user_id: "u",
            warehouse_id: "w",
            business_date: "2026-10-29",
        },
        version: "catalog-1",
        updatedAt: "2026-10-29T01:00:00Z",
        outlets: [],
        deliveries: [],
        products: mapCatalogProducts([
            row,
            {
                ...row,
                product_id: 42,
                default_code: "SKU-42",
                carton_qty: 120,
                inner_qty: 10,
                price_per_carton: 120000,
            },
        ]),
    });
}
afterEach(() => vi.unstubAllGlobals());
it("maps explicit carton price and stock, variant identity and principal; different SKU ratios remain independent", () => {
    const snapshot = catalog();
    expect(snapshot.products[0]).toMatchObject({
        id: "41",
        principal: "7",
        price: 24000,
        stock: 1.5,
        price_basis: "carton",
        stock_basis: "carton",
        packaging: { carton: 24, pack: 6, pcs: 1 },
    });
    const quote = (id: string, qty: string, uom: "carton" | "pack" | "pcs") =>
        orderQuote([{ product_id: id, qty, uom }], snapshot);
    expect(quote("41", "1", "carton")).toEqual(quote("41", "4", "pack"));
    expect(quote("41", "1", "carton")).toEqual(quote("41", "24", "pcs"));
    expect(quote("42", "1", "carton")).toEqual(quote("42", "12", "pack"));
    const lines = [
        { product_id: "41", qty: "1", uom: "pack" as const },
        { product_id: "42", qty: "2", uom: "pcs" as const },
    ];
    const discount = { percent: 5, reason: "Promo SKU" };
    expect(orderQuote(lines, snapshot, discount)).toEqual({
        gross: 8000,
        requestedDiscount: 400,
        requestedTotal: 7600,
    });
    expect(() =>
        validateOrderQuote(
            {
                lines,
                pricing_version: 1,
                discount_request: discount,
                observed_total: "7600",
            },
            snapshot,
        ),
    ).not.toThrow();
    expect(() =>
        validateOrderQuote(
            { lines, pricing_version: 1, observed_total: "1" },
            snapshot,
        ),
    ).toThrow("Total");
});
it.each([
    { carton: 0, pack: 6, pcs: 1 },
    { carton: 24, pack: 0, pcs: 1 },
    { carton: 24, pack: 5, pcs: 1 },
    { carton: 6, pack: 12, pcs: 1 },
    { carton: 24.5, pack: 6, pcs: 1 },
    { carton: 24, pack: 6, pcs: 2 },
])("rejects invalid packaging %j", (p) => {
    expect(PackagingSchema.safeParse(p).success).toBe(false);
    expect(() => productPackaging({ packaging: p as any }, 2)).toThrow();
});
it("rejects duplicate variant/code, missing principal, unknown raw ORM fields and ambiguous price bases", () => {
    expect(() => mapCatalogProducts([row, row])).toThrow("ganda");
    expect(() => mapCatalogProducts([row, { ...row, product_id: 42 }])).toThrow(
        "ganda",
    );
    expect(() => mapCatalogProducts([{ ...row, principal_id: 0 }])).toThrow();
    expect(() => mapCatalogProducts([{ ...row, list_price: 123 }])).toThrow();
    expect(() =>
        mapCatalogProducts([{ ...row, price_per_carton: undefined }]),
    ).toThrow();
    const snapshot = catalog();
    expect(
        SnapshotSchema.safeParse({
            ...snapshot,
            products: [{ ...snapshot.products[0], price_basis: "pcs" }],
        }).success,
    ).toBe(false);
});
it.each(["packaging", "sku_code", "price_basis", "stock_basis"] as const)(
    "v2 never silently infers missing %s",
    (field) => {
        const snapshot = catalog(),
            product = { ...snapshot.products[0] };
        delete product[field];
        expect(
            SnapshotSchema.safeParse({ ...snapshot, products: [product] })
                .success,
        ).toBe(false);
        if (field === "packaging")
            expect(() =>
                orderQuote([{ product_id: "41", qty: "1", uom: "pack" }], {
                    ...snapshot,
                    products: [product],
                }),
            ).toThrow("Rasio");
    },
);
it("preserves old demo snapshot quotes without adding metadata or rewriting their JSON", () => {
    const legacy = catalog();
    delete legacy.catalog_version;
    delete legacy.scope;
    legacy.products.forEach((p) => {
        delete p.packaging;
        delete p.sku_code;
        delete p.price_basis;
        delete p.stock_basis;
    });
    legacy.products[0].price = 144000;
    const before = JSON.stringify(legacy),
        parsed = SnapshotSchema.parse(legacy);
    expect(
        orderQuote([{ product_id: "41", qty: "1", uom: "pack" }], parsed).gross,
    ).toBe(12000);
    expect(JSON.stringify(parsed)).toBe(before);
});
it.each(["company_id", "user_id", "business_date"] as const)(
    "HTTP snapshot enforces bootstrap scope: %s",
    async (field) => {
        const snapshot = catalog(),
            identity = {
                id: "u",
                companyId: "c",
                name: "User",
                title: "",
                roles: ["sales"],
                businessDate: "2026-10-29",
                csrfToken: "test",
            };
        const fetch = vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(
                Response.json({
                    ...snapshot,
                    scope: {
                        ...snapshot.scope,
                        [field]:
                            field === "business_date" ? "2026-10-28" : "other",
                    },
                }),
            );
        vi.stubGlobal("fetch", fetch);
        const provider = new HttpProvider();
        await provider.bootstrap();
        await expect(provider.snapshot()).rejects.toMatchObject({
            status: 422,
        });
        expect(fetch.mock.calls[1][1]).toMatchObject({
            credentials: "same-origin",
            cache: "no-store",
        });
    },
);
it("HTTP snapshot requires bootstrap and catalog v2, accepts an authorized complete snapshot without enabling live", async () => {
    await expect(new HttpProvider().snapshot()).rejects.toMatchObject({
        status: 401,
    });
    const snapshot = catalog(),
        identity = {
            id: "u",
            companyId: "c",
            name: "User",
            title: "",
            roles: ["sales"],
            businessDate: "2026-10-29",
        };
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(Response.json(snapshot))
            .mockResolvedValueOnce(
                Response.json({ ...snapshot, catalog_version: undefined }),
            ),
    );
    const provider = new HttpProvider();
    await provider.bootstrap();
    expect(await provider.snapshot()).toEqual(snapshot);
    await expect(provider.snapshot()).rejects.toMatchObject({ status: 422 });
});
it("HTTP provider exposes native delivery tasks and preserves a server 422 message", async () => {
    const identity = {
        id: "u",
        companyId: "c",
        name: "Driver",
        title: "Driver",
        roles: ["delivery"],
        businessDate: "2026-10-29",
        csrfToken: "csrf",
    };
    const outlet = {
        id: "outlet-8",
        name: "FreshMart Bahu",
        channel: "GT",
        address: "Bahu",
        distance: "",
        time: "",
        latitude: 1.465,
        longitude: 124.833,
        radius: 100,
    };
    const delivery = {
        workflow_version: 2 as const,
        id: "WH/OUT/06409",
        trip: "TRIP-ACC-01",
        vehicle: "DB 8123 QA",
        outlet: outlet.name,
        outlet_id: outlet.id,
        address: outlet.address,
        owner: "c:u",
        business_date: identity.businessDate,
        version: "odoo-delivery-v1:abc",
        site: {
            latitude: outlet.latitude,
            longitude: outlet.longitude,
            radius: outlet.radius,
        },
        lines: [
            {
                id: "13612",
                name: "[MYR-RMA-01] Roma Kelapa 300g",
                quantity: 60,
                unit: "Units",
            },
        ],
    };
    const snapshot = {
        ...catalog(),
        outlets: [outlet],
        deliveries: [delivery],
    };
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(Response.json(snapshot))
            .mockResolvedValueOnce(
                Response.json(
                    {
                        error: "DO kedua belum memiliki POD yang diterima hari ini.",
                    },
                    { status: 422 },
                ),
            ),
    );
    const provider = new HttpProvider();
    await provider.bootstrap();
    expect(await provider.snapshot()).toEqual(snapshot);
    expect(await provider.deliveryTasks()).toEqual([delivery]);
    await expect(
        provider.submit({
            schema_version: 1,
            client_uuid: crypto.randomUUID(),
            occurred_at: new Date().toISOString(),
            type: "delivery.trip.close",
            payload: {},
        } as never),
    ).rejects.toMatchObject({
        status: 422,
        message: "DO kedua belum memiliki POD yang diterima hari ini.",
    });
});
it("a cached v2 morning bundle cannot cross owner/day scope", async () => {
    const provider = new MockProvider("sales", true),
        identity = await provider.bootstrap(),
        snapshot = await provider.snapshot(),
        now = new Date().toISOString();
    const record = MorningRecordSchema.parse({
        mode: "simulation",
        owner: `${identity.companyId}:${identity.id}`,
        businessDate: identity.businessDate,
        attendanceReference: "TEST",
        attendanceAt: now,
        sessionId: crypto.randomUUID(),
        openedAt: now,
        snapshot,
    });
    expect(morningReady(record, record.owner)).toBe(true);
    expect(
        morningReady(
            {
                ...record,
                snapshot: {
                    ...snapshot,
                    scope: { ...snapshot.scope, user_id: "other" },
                },
            },
            record.owner,
        ),
    ).toBe(false);
    expect(
        morningReady(
            {
                ...record,
                snapshot: {
                    ...snapshot,
                    scope: { ...snapshot.scope, business_date: "2000-01-01" },
                },
            },
            record.owner,
        ),
    ).toBe(false);
});

it("a bootstrap failure invalidates the prior HTTP scope and CSRF", async () => {
    const identity = {
        id: "u",
        companyId: "c",
        name: "User",
        title: "",
        roles: ["sales"],
        businessDate: "2026-10-29",
        csrfToken: "old",
    };
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockResolvedValueOnce(new Response("{}", { status: 401 })),
    );
    const provider = new HttpProvider();
    await provider.bootstrap();
    await expect(provider.bootstrap()).rejects.toMatchObject({ status: 401 });
    await expect(provider.snapshot()).rejects.toMatchObject({ status: 401 });
    await expect(
        provider.submit({
            schema_version: 1,
            client_uuid: crypto.randomUUID(),
            occurred_at: new Date().toISOString(),
            type: "hris.leave.request",
            payload: {},
        }),
    ).rejects.toMatchObject({ status: 401 });
});
it("a response from an older bootstrap cannot be adopted by a new session", async () => {
    const identity = {
        id: "u",
        companyId: "c",
        name: "User",
        title: "",
        roles: ["sales"],
        businessDate: "2026-10-29",
    };
    let release!: (response: Response) => void;
    const delayed = new Promise<Response>((resolve) => {
        release = resolve;
    });
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(Response.json(identity))
            .mockReturnValueOnce(delayed)
            .mockResolvedValueOnce(Response.json({ ...identity, id: "other" })),
    );
    const provider = new HttpProvider();
    await provider.bootstrap();
    const pending = provider.snapshot();
    await provider.bootstrap();
    release(Response.json(catalog()));
    await expect(pending).rejects.toMatchObject({ status: 409 });
});

const bootstrapIdentity = (id: string) => ({
    id,
    companyId: "c",
    name: "User",
    title: "",
    roles: ["sales"],
    businessDate: "2026-10-29",
    csrfToken: `${id}-token`,
});
function delayedResponse() {
    let resolve!: (response: Response) => void;
    let reject!: (error: Error) => void;
    const promise = new Promise<Response>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}
const harmlessCommand = () => ({
    schema_version: 1 as const,
    client_uuid: crypto.randomUUID(),
    occurred_at: new Date().toISOString(),
    type: "hris.leave.request" as const,
    payload: {},
});
it("bootstrap generation A pending, B succeeds, A succeeds: only B scope and CSRF survive", async () => {
    const a = delayedResponse(),
        snapshot = catalog(),
        command = harmlessCommand();
    const fetch = vi
        .fn()
        .mockReturnValueOnce(a.promise)
        .mockResolvedValueOnce(Response.json(bootstrapIdentity("new")))
        .mockResolvedValueOnce(
            Response.json({
                ...snapshot,
                scope: { ...snapshot.scope, user_id: "new" },
            }),
        )
        .mockResolvedValueOnce(
            Response.json({
                ...snapshot,
                scope: { ...snapshot.scope, user_id: "old" },
            }),
        )
        .mockResolvedValueOnce(
            Response.json({
                client_uuid: command.client_uuid,
                status: "accepted",
                reference: "test",
                message: "test",
            }),
        );
    vi.stubGlobal("fetch", fetch);
    const provider = new HttpProvider(),
        older = provider.bootstrap();
    const stale = expect(older).rejects.toMatchObject({ status: 409 });
    expect((await provider.bootstrap()).id).toBe("new");
    a.resolve(Response.json(bootstrapIdentity("old")));
    await stale;
    expect((await provider.snapshot()).scope?.user_id).toBe("new");
    await expect(provider.snapshot()).rejects.toMatchObject({ status: 422 });
    await provider.submit(command);
    expect(fetch.mock.calls.at(-1)![1]).toMatchObject({
        headers: { "X-CSRF-Token": "new-token" },
    });
});
it("bootstrap generation A pending, B fails401, A succeeds: the cleared session cannot be resurrected", async () => {
    const a = delayedResponse(),
        fetch = vi
            .fn()
            .mockReturnValueOnce(a.promise)
            .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetch);
    const provider = new HttpProvider(),
        older = provider.bootstrap();
    const stale = expect(older).rejects.toMatchObject({ status: 409 });
    await expect(provider.bootstrap()).rejects.toMatchObject({ status: 401 });
    a.resolve(Response.json(bootstrapIdentity("old")));
    await stale;
    await expect(provider.snapshot()).rejects.toMatchObject({ status: 401 });
    await expect(provider.submit(harmlessCommand())).rejects.toMatchObject({
        status: 401,
    });
    expect(fetch).toHaveBeenCalledTimes(2);
});
it.each(["401", "network", "malformed"] as const)(
    "bootstrap generation A pending, B succeeds, A fails %s: B is preserved",
    async (failure) => {
        const a = delayedResponse(),
            snapshot = catalog(),
            command = harmlessCommand();
        const fetch = vi
            .fn()
            .mockReturnValueOnce(a.promise)
            .mockResolvedValueOnce(Response.json(bootstrapIdentity("new")))
            .mockResolvedValueOnce(
                Response.json({
                    ...snapshot,
                    scope: { ...snapshot.scope, user_id: "new" },
                }),
            )
            .mockResolvedValueOnce(
                Response.json({
                    client_uuid: command.client_uuid,
                    status: "accepted",
                    reference: "test",
                    message: "test",
                }),
            );
        vi.stubGlobal("fetch", fetch);
        const provider = new HttpProvider(),
            older = provider.bootstrap();
        const stale = expect(older).rejects.toMatchObject({ status: 409 });
        await provider.bootstrap();
        if (failure === "401") a.resolve(new Response("{}", { status: 401 }));
        else if (failure === "network") a.reject(new Error("network failure"));
        else a.resolve(Response.json({ id: "invalid" }));
        await stale;
        expect((await provider.snapshot()).scope?.user_id).toBe("new");
        await provider.submit(command);
        expect(fetch.mock.calls.at(-1)![1]).toMatchObject({
            headers: { "X-CSRF-Token": "new-token" },
        });
    },
);

it("snapshot menerima approval_tiers opsional (BE-18) dan tetap valid tanpanya", () => {
    const base = catalog();
    expect(base.approval_tiers).toBeUndefined();
    const block = {
        free_zone_max: 6,
        tiers: [
            { min_discount: 0.01, approver: "Tier 1: Supervisor" },
            { min_discount: 3.01, approver: "Tier 2: Branch Manager" },
        ],
    };
    const parsed = SnapshotSchema.parse({
        ...base,
        approval_tiers: {
            discount: {
                scope: "salesman_day",
                default: { free_zone_max: null, tiers: block.tiers },
                principals: { "7": block },
                usage: [
                    {
                        outlet_id: null,
                        principal: "7",
                        discount_amount: 3000,
                        gross_amount: 60000,
                    },
                ],
            },
        },
    });
    expect(parsed.approval_tiers?.discount.principals["7"].free_zone_max).toBe(
        6,
    );
    expect(parsed.approval_tiers?.discount.default.free_zone_max).toBeNull();
});

it("approval_tiers dengan scope tak dikenal atau usage tanpa bruto ditolak", () => {
    const base = catalog();
    const block = { free_zone_max: 0, tiers: [] };
    const bad = (discount: object) =>
        SnapshotSchema.safeParse({
            ...base,
            approval_tiers: { discount },
        }).success;
    expect(
        bad({ scope: "year", default: block, principals: {}, usage: [] }),
    ).toBe(false);
    expect(
        bad({
            scope: "order",
            default: block,
            principals: {},
            usage: [
                {
                    outlet_id: null,
                    principal: null,
                    discount_amount: 1,
                    gross_amount: 0,
                },
            ],
        }),
    ).toBe(false);
});

it("snapshot menerima credit_mode dan outlet_credit opsional (BE-19)", () => {
    const base = catalog();
    expect(base.outlet_credit).toBeUndefined();
    const outlet = {
        id: "5",
        name: "Toko Uji",
        channel: "GT",
        address: "Jl. Uji",
        distance: "",
        time: "",
        latitude: 1.4,
        longitude: 124.8,
        radius: 50,
        commercial: {
            max_order: null,
            previous_visit_total: null,
            top_sku: null,
            payment_terms: null,
            credit_limit: null,
            contact: null,
            credit_mode: "strict",
        },
    };
    const parsed = SnapshotSchema.parse({
        ...base,
        outlets: [outlet],
        outlet_credit: {
            "5": {
                overdue_count: 2,
                overdue_total: 150000,
                oldest_due: "2026-10-01",
            },
        },
    });
    expect(parsed.outlets[0].commercial?.credit_mode).toBe("strict");
    expect(parsed.outlet_credit?.["5"].overdue_count).toBe(2);
    expect(
        SnapshotSchema.safeParse({
            ...base,
            outlet_credit: {
                "5": { overdue_count: 0, overdue_total: 0, oldest_due: null },
            },
        }).success,
    ).toBe(false);
});

it("snapshot menerima collection_sheets opsional (BE-20c)", () => {
    const base = catalog();
    expect(base.collection_sheets).toBeUndefined();
    const line = {
        id: "11",
        reference: "INV/2026/0001",
        partner: "Toko Uji",
        partner_id: "5",
        outlet_id: "5",
        due_date: "2026-11-16",
        overdue: false,
        amount_due: 100000,
        balance: 40000,
        outcome: "pending",
        document_return: "none",
        receipt_state: "posted",
        receipt_amount: 40000,
    };
    const sheet = {
        id: "3",
        name: "SJP/2026/00003",
        collect_date: "2026-11-16",
        due_until: "2026-11-16",
        route: null,
        state: "issued",
        line_count: 1,
        amount_total: 100000,
        truncated: false,
        lines: [line],
    };
    const parsed = SnapshotSchema.parse({
        ...base,
        collection_sheets: { sheets: [sheet], truncated: false },
    });
    expect(parsed.collection_sheets?.sheets[0].lines[0].balance).toBe(40000);
    expect(parsed.collection_sheets?.sheets[0].lines[0].receipt_state).toBe(
        "posted",
    );
    const bad = (patch: object) =>
        SnapshotSchema.safeParse({
            ...base,
            collection_sheets: {
                sheets: [{ ...sheet, ...patch }],
                truncated: false,
            },
        }).success;
    expect(bad({ state: "draft" })).toBe(false);
    expect(bad({ lines: [{ ...line, outcome: "settled" }] })).toBe(false);
    expect(bad({ lines: [{ ...line, document_return: "x" }] })).toBe(false);
    expect(bad({ line_count: -1 })).toBe(false);
});

it("snapshot menerima outlet_receivables opsional (BE-7)", () => {
    const base = catalog();
    expect(base.outlet_receivables).toBeUndefined();
    const entry = {
        outstanding_total: 180000,
        open_count: 2,
        overdue_count: 1,
        overdue_total: 100000,
        oldest_due: "2026-10-01",
        truncated: false,
        invoices: [
            {
                reference: "INV/2026/0001",
                partner: "Toko Uji",
                invoice_date: "2026-09-01",
                due_date: "2026-10-01",
                total: 100000,
                balance: 100000,
                overdue: true,
            },
            {
                reference: "INV/2026/0002",
                partner: "Toko Uji",
                invoice_date: null,
                due_date: null,
                total: 80000,
                balance: 80000,
                overdue: false,
            },
        ],
    };
    const parsed = SnapshotSchema.parse({
        ...base,
        outlet_receivables: { "5": entry },
    });
    expect(parsed.outlet_receivables?.["5"].invoices).toHaveLength(2);
    expect(
        SnapshotSchema.safeParse({
            ...base,
            outlet_receivables: { "5": { ...entry, open_count: 0 } },
        }).success,
    ).toBe(false);
    expect(
        SnapshotSchema.safeParse({
            ...base,
            outlet_receivables: {
                "5": { ...entry, invoices: [{ reference: "X" }] },
            },
        }).success,
    ).toBe(false);
});
