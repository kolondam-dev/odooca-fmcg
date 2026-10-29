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
