import { expect, test } from "@playwright/test";
import {
    evidenceName,
    loginThroughForm,
    odooBase,
    publicOnly,
    pwaBase,
} from "./helpers";

test("@smoke @odoo-live Odoo web is reachable and session is usable", async ({
    page,
}, testInfo) => {
    const base = odooBase;
    test.skip(!base, "LIVE_UI_ODOO_URL is not configured");
    if (!base) return;
    const response = await page.goto(new URL("web/login", base).href, {
        waitUntil: "domcontentloaded",
    });
    expect(response?.status()).toBeLessThan(400);

    if (publicOnly) {
        await expect(page.locator('input[name="login"]')).toBeVisible();
        return;
    }

    await page.goto(new URL("odoo", base).href, {
        waitUntil: "domcontentloaded",
    });
    await expect(page.locator('input[name="password"]')).toHaveCount(0);
    await expect(page.locator("body")).not.toBeEmpty();
    await page.screenshot({
        path: evidenceName(testInfo, "odoo-home"),
        fullPage: true,
    });
});

test("@smoke @pwa-live PWA is reachable and accepts the test session", async ({
    page,
}, testInfo) => {
    const base = pwaBase;
    test.skip(!base, "LIVE_UI_PWA_URL is not configured");
    if (!base) return;
    const response = await page.goto(base.href, {
        waitUntil: "domcontentloaded",
    });
    expect(response?.status()).toBeLessThan(400);

    const passwordInput = page.locator('input[name="password"]');
    if (publicOnly) {
        await expect(page.locator("body")).not.toBeEmpty();
        return;
    }
    if (await passwordInput.isVisible()) {
        await loginThroughForm(page, base.href);
    }
    await expect(passwordInput).toHaveCount(0, { timeout: 15000 });
    await expect(page.locator("body")).not.toBeEmpty();
    await page.screenshot({
        path: evidenceName(testInfo, "pwa-home"),
        fullPage: true,
    });
});
