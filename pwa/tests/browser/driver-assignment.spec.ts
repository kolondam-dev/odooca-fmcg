import { test, expect } from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { ensureDaily, switchPersona } from "./delivery-helpers";

test("authenticated driver opens two native DOs bound by outlet_id", async ({
    page,
}) => {
    await page.context().grantPermissions(["geolocation"]);
    await page.route("**/api/v1/sync/snapshot", async (route) => {
        const raw = await new MockProvider("delivery", true).snapshot();
        const now = await page.evaluate(() => new Date().toISOString());
        const date = await page.evaluate(() =>
            new Date().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            }),
        );
        const outlets = [
            {
                ...raw.outlets[1],
                id: "outlet-paniki",
                name: "FreshMart Paniki",
                address: "Paniki Address",
            },
            {
                ...raw.outlets[0],
                id: "outlet-bahu",
                name: "FreshMart Bahu",
                address: "Bahu Address",
            },
        ];
        const deliveries = [
            {
                ...raw.deliveries[0],
                id: "WH/OUT/06409",
                outlet_id: "outlet-bahu",
                outlet: "FreshMart Bahu",
                address: "Bahu Address",
                business_date: date,
                site: {
                    latitude: outlets[1].latitude,
                    longitude: outlets[1].longitude,
                    radius: outlets[1].radius,
                },
                lines: [
                    {
                        id: "move-rma-a",
                        name: "[MYR-RMA-01] Roma Kelapa 300g",
                        quantity: 60,
                        unit: "Units",
                    },
                    {
                        id: "move-btr-a",
                        name: "[MYR-BTR-01] Better Vanilla",
                        quantity: 160,
                        unit: "Units",
                    },
                ],
            },
            {
                ...raw.deliveries[1],
                id: "WH/OUT/06410",
                outlet_id: "outlet-paniki",
                outlet: "FreshMart Paniki",
                address: "Paniki Address",
                business_date: date,
                site: {
                    latitude: outlets[0].latitude,
                    longitude: outlets[0].longitude,
                    radius: outlets[0].radius,
                },
                lines: [
                    {
                        id: "move-rma-b",
                        name: "[MYR-RMA-01] Roma Kelapa 300g",
                        quantity: 90,
                        unit: "Units",
                    },
                    {
                        id: "move-btr-b",
                        name: "[MYR-BTR-01] Better Vanilla",
                        quantity: 320,
                        unit: "Units",
                    },
                ],
            },
        ];
        await route.fulfill({
            json: {
                ...raw,
                updatedAt: now,
                scope: { ...raw.scope, business_date: date },
                deliveries,
                outlets,
                office: {
                    id: "1",
                    name: "Kantor Pusat",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                    coordinate_status: "test",
                },
            },
        });
    });
    await page.goto("./");
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await expect(
        page.getByRole("button", { name: "Sales", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Delivery", exact: true }).click();
    // Array outlet sengaja berurutan Paniki/Bahu, sedangkan manifest DO Bahu/Paniki.
    // Pairing wajib mengikuti outlet_id, bukan indeks.
    await expect(page.getByRole("button", { name: /^Buka TRIP/ })).toHaveCount(
        1,
    );
    await expect(
        page.getByRole("button", { name: /^Buka TRIP/ }),
    ).toContainText("2 toko");
    await page.getByRole("button", { name: /^Buka TRIP/ }).click();
    const stores = page.getByRole("region", { name: /^Daftar toko / });
    await expect(stores).toContainText("WH/OUT/06409");
    await expect(stores).toContainText("FreshMart Bahu");
    await expect(stores).toContainText("Bahu Address");
    await expect(stores).toContainText("WH/OUT/06410");
    await expect(stores).toContainText("FreshMart Paniki");
    await expect(stores).toContainText("Paniki Address");
});

test("sales account retains its Sales menu", async ({ page }) => {
    await page.goto("./");
    await expect(
        page.getByRole("button", { name: "Sales", exact: true }),
    ).toBeVisible();
});
