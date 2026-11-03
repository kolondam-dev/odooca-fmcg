import { test, expect } from "./session-fixture";
import { MockProvider } from "../../src/data/mock";
import { ensureDaily, switchPersona } from "./delivery-helpers";

test("authenticated driver with one assigned outlet opens daily sync and consistent Delivery", async ({
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
        await route.fulfill({
            json: {
                ...raw,
                updatedAt: now,
                scope: { ...raw.scope, business_date: date },
                deliveries: [],
                outlets: [
                    {
                        ...raw.outlets[0],
                        id: "assigned-only",
                        name: "Assigned Only Store",
                        address: "Assigned Only Address",
                    },
                ],
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
    await expect(page.locator(".delivery-task")).toHaveCount(1);
    await expect(page.locator(".delivery-task")).toContainText(
        "Assigned Only Store",
    );
    await expect(page.locator(".delivery-task")).toContainText(
        "Assigned Only Address",
    );
});

test("sales account retains its Sales menu", async ({ page }) => {
    await page.goto("./");
    await expect(
        page.getByRole("button", { name: "Sales", exact: true }),
    ).toBeVisible();
});
