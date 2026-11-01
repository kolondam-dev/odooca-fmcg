import { test as base, expect, type Page } from "@playwright/test";
import { MockProvider } from "../../src/data/mock";
import "fake-indexeddb/auto";
(globalThis as Record<string, unknown>).__DEMO__ = true;
const actors = new WeakMap<Page, string>();
export async function changeTestAccount(page: Page, actor: string) {
    actors.set(page, actor);
    if (await page.evaluate(() => navigator.onLine))
        await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    else await page.reload();
}
// HTTP fixtures emulate authenticated backend responses, never a runtime login bypass.
export const test = base.extend({
    page: async ({ page }, use) => {
        actors.set(page, "sales");
        await page.context().setGeolocation({
            latitude: 1.465,
            longitude: 124.833,
            accuracy: 3,
        });
        await page.route("**/api/v1/me/bootstrap", async (route) => {
            if (new URL(route.request().url()).port !== "4173")
                return route.fallback();
            const provider = new MockProvider(
                actors.get(page) ?? "sales",
                true,
            );
            const identity = await provider.bootstrap();
            const date = await page.evaluate(() =>
                new Date().toLocaleDateString("en-CA", {
                    timeZone: "Asia/Makassar",
                }),
            );
            await route.fulfill({
                json: {
                    ...identity,
                    businessDate: date,
                    companyName: "PT. Demo FMCG",
                },
            });
        });
        await page.route("**/api/v1/sync/snapshot", async (route) => {
            if (new URL(route.request().url()).port !== "4173")
                return route.fallback();
            const provider = new MockProvider(
                actors.get(page) ?? "sales",
                true,
            );
            const snapshot = await provider.snapshot();
            const now = await page.evaluate(() => new Date().toISOString());
            const date = await page.evaluate(() =>
                new Date().toLocaleDateString("en-CA", {
                    timeZone: "Asia/Makassar",
                }),
            );
            await route.fulfill({
                json: {
                    ...snapshot,
                    updatedAt: now,
                    scope: { ...snapshot.scope, business_date: date },
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
        await use(page);
    },
});
export { expect };
export type { Page, Locator, BrowserContext } from "@playwright/test";
export async function checkIn(page: Page) {
    const clock = page.locator(".quick-attendance-record");
    if (await clock.isVisible()) return;
    await page.context().grantPermissions(["geolocation"]);
    await page
        .getByRole("button", { name: /^Absensi/ })
        .first()
        .click();
    await page
        .getByRole("button", { name: "Ambil Lokasi Presisi", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Lokasi dan foto absensi" }),
    ).toHaveAttribute("aria-busy", "false");
    await page
        .getByLabel("Alamat / nama lokasi")
        .fill("Jl. Sam Ratulangi, Sario, Manado, Sulawesi Utara");
    await page
        .getByRole("button", { name: "Buka Kamera", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await expect(
        page.getByAltText("Foto absensi dengan watermark"),
    ).toBeVisible();
    await page.getByRole("button", { name: "Check in", exact: true }).click();
    await expect(clock).toBeVisible();
}
