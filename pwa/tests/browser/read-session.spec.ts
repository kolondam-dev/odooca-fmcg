import { expect, test, type Page } from "./session-fixture";
test.use({ baseURL: "http://127.0.0.1:4175/field/" });
const identity = {
    id: "41",
    companyId: "7",
    name: "Sales Staging",
    title: "Salesman",
    roles: ["sales"],
    businessDate: "2026-10-29",
    csrfToken: "test-token",
};
const snapshot = {
    catalog_version: 2,
    scope: {
        company_id: "7",
        user_id: "41",
        warehouse_id: "9",
        business_date: "2026-10-29",
    },
    version: "read-fixture",
    updatedAt: "2026-10-29T01:00:00Z",
    deliveries: [],
    outlets: [
        {
            id: "12",
            name: "Outlet Scope A",
            channel: "GT",
            address: "Jalan Uji",
            distance: "",
            time: "",
            latitude: 1.4,
            longitude: 124.8,
            radius: 10,
        },
    ],
    products: [
        {
            id: "5",
            sku_code: "SKU-24",
            name: "Produk Scope A",
            brand: "",
            principal: "6",
            unit: "karton 24 pcs / pack 6 pcs",
            price: 24000,
            stock: 1.5,
            packaging: { carton: 24, pack: 6, pcs: 1 },
            price_basis: "carton",
            stock_basis: "carton",
        },
    ],
};
async function api(page: Page) {
    await page.clock.install({ time: new Date("2026-10-29T01:00:00Z") });
    let status = 200;
    let payload: unknown = snapshot;
    const requests: string[] = [];
    await page.route("**/api/**", async (route) => {
        const request = route.request();
        requests.push(request.method() + " " + new URL(request.url()).pathname);
        expect(new URL(request.url()).origin).toBe("http://127.0.0.1:4175");
        await route.fulfill({
            status,
            contentType: "application/json",
            body: JSON.stringify(
                status === 200
                    ? request.url().endsWith("bootstrap")
                        ? identity
                        : payload
                    : { error: "denied" },
            ),
        });
    });
    return {
        requests,
        status: (value: number) => {
            status = value;
        },
        payload: (value: unknown) => {
            payload = value;
        },
    };
}
async function sync(page: Page) {
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await expect(
        page.getByText("Daily sync berhasil.", { exact: true }),
    ).toBeVisible();
}
test("native login handoff then bootstrap and read-only daily sync", async ({
    page,
}) => {
    const server = await api(page);
    server.status(401);
    await page.goto("./");
    await expect(page.getByRole("status")).toContainText("belum login");
    const link = page.getByRole("link", { name: "Masuk / ganti akun di Odoo" });
    await expect(link).toHaveAttribute(
        "href",
        "/web/login?redirect=%2Ffield%2F",
    );
    // Transport fixture only; native Odoo authentication is covered by HttpCase.
    await page.route("**/web/login?*", (route) =>
        route.fulfill({
            contentType: "text/html",
            body: '<a href="/field/">Kembali ke Field</a>',
        }),
    );
    await link.click();
    server.status(200);
    await page.getByRole("link", { name: "Kembali ke Field" }).click();
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    await sync(page);
    await expect(
        page.getByText("Outlet Scope A", { exact: true }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Katalog SKU", exact: true })
        .click();
    await expect(
        page.getByText("SKU-24 · karton 24 pcs / pack 6 pcs", { exact: true }),
    ).toBeVisible();
    expect(
        server.requests.every((request) => request.startsWith("GET ")),
    ).toBeTruthy();
    expect(
        server.requests.filter((request) => request.endsWith("/me/bootstrap")),
    ).toHaveLength(3);
    expect(
        server.requests.filter((request) => request.endsWith("/sync/snapshot")),
    ).toHaveLength(1);
    expect(
        await page.evaluate(async () => ({
            local: localStorage.length,
            session: sessionStorage.length,
            dbs: (await indexedDB.databases()).length,
        })),
    ).toEqual({ local: 0, session: 0, dbs: 0 });
    await expect(
        page.getByRole("button", { name: /Buat order|Ajukan|absensi/i }),
    ).toHaveCount(0);
});
test("failed refresh clears identity, products and outlets and allows recovery", async ({
    page,
}) => {
    const server = await api(page);
    await page.goto("./");
    await sync(page);
    server.status(403);
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Hubungi admin");
    await expect(page.getByText("Sales Staging", { exact: true })).toHaveCount(
        0,
    );
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    await expect(
        page.getByRole("button", { name: "Daily sync", exact: true }),
    ).toBeDisabled();
    server.status(200);
    await page
        .getByRole("button", { name: "Hubungkan sesi", exact: true })
        .click();
    await sync(page);
});
test("mismatched or malformed snapshots never expose a previous catalog", async ({
    page,
}) => {
    const server = await api(page);
    await page.goto("./");
    await sync(page);
    server.payload({
        ...snapshot,
        scope: { ...snapshot.scope, user_id: "other" },
    });
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("scope data");
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    server.payload({ products: [] });
    await page
        .getByRole("button", { name: "Hubungkan sesi", exact: true })
        .click();
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("belum dapat dibaca");
});
test("clearing an in-flight sync prevents its delayed result from returning", async ({
    page,
}) => {
    await api(page);
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
        release = resolve;
    });
    let received!: () => void;
    const arrived = new Promise<void>((resolve) => {
        received = resolve;
    });
    await page.route("**/sync/snapshot", async (route) => {
        received();
        await held;
        await route.fulfill({
            contentType: "application/json",
            body: JSON.stringify(snapshot),
        });
    });
    await page.goto("./");
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Daily sync", exact: true }).click();
    await arrived;
    await page
        .getByRole("button", { name: "Bersihkan tampilan", exact: true })
        .click();
    const response = page.waitForResponse("**/sync/snapshot");
    release();
    await response;
    await expect(page.getByRole("status")).toHaveText("Tampilan dibersihkan.");
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
});
test("WITA midnight clears visible data and rejects an expired bootstrap", async ({
    page,
}) => {
    await api(page);
    await page.goto("./");
    await sync(page);
    await page.clock.setFixedTime(new Date("2026-10-29T16:00:00Z"));
    await page.clock.runFor(1000);
    await expect(page.getByRole("status")).toContainText("Hari WITA berganti");
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    await page
        .getByRole("button", { name: "Hubungkan sesi", exact: true })
        .click();
    await expect(page.getByRole("status")).toContainText("hari WITA berubah");
});
test("offline event clears lists; reload and online recovery require a new sync", async ({
    page,
    context,
}) => {
    await api(page);
    await page.goto("./");
    await sync(page);
    await context.setOffline(true);
    await expect(page.getByRole("status")).toContainText("Koneksi terputus");
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    await context.setOffline(false);
    await page.reload();
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await expect(page.getByText("Outlet Scope A", { exact: true })).toHaveCount(
        0,
    );
    await sync(page);
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBeTruthy();
});

test("staging retires old shell caches and does not register an offline worker", async ({
    page,
}) => {
    await api(page);
    await page.goto("./");
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    await page.evaluate(async () => {
        const cache = await caches.open("fmcg-field-old-demo");
        await cache.put("/field/index.html", new Response("old shell"));
    });
    await page.reload();
    await expect(
        page.getByText("Sesi terhubung.", { exact: false }),
    ).toBeVisible();
    expect(await page.evaluate(() => caches.keys())).not.toContain(
        "fmcg-field-old-demo",
    );
    expect(
        await page.evaluate(
            async () =>
                (await navigator.serviceWorker.getRegistrations()).length,
        ),
    ).toBe(0);
});
