import { expect, type Page, type TestInfo } from "@playwright/test";

export const publicOnly =
    process.env.LIVE_UI_PUBLIC_ONLY?.toUpperCase() === "YES";

function normalizedBase(name: "LIVE_UI_ODOO_URL" | "LIVE_UI_PWA_URL") {
    const value = process.env[name];
    return value ? new URL(value.endsWith("/") ? value : `${value}/`) : null;
}

export const odooBase = normalizedBase("LIVE_UI_ODOO_URL");
export const pwaBase = normalizedBase("LIVE_UI_PWA_URL");

export function targetUrl(target: "odoo" | "pwa", path = "") {
    const base = target === "odoo" ? odooBase : pwaBase;
    if (!base) throw new Error(`No ${target.toUpperCase()} URL configured.`);
    if (!path) return base.href;
    return new URL(path, base).href;
}

export function credentials() {
    const login = process.env.ODOO_DEMO_LOGIN;
    const password = process.env.ODOO_DEMO_PASSWORD;
    if (!login || !password) {
        throw new Error("Live UI credentials are not configured.");
    }
    return { login, password };
}

export async function loginThroughForm(page: Page, url: string) {
    const { login, password } = credentials();
    const response = await page.goto(url, { waitUntil: "domcontentloaded" });
    expect(response?.status(), `GET ${url}`).toBeLessThan(400);

    const loginInput = page.locator('input[name="login"]');
    const passwordInput = page.locator('input[name="password"]');
    await expect(loginInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    const database = process.env.ODOO_DEMO_DB;
    const databaseInput = page.locator('input[name="db"], select[name="db"]');
    if (database && (await databaseInput.count())) {
        const tagName = await databaseInput
            .first()
            .evaluate((node) => node.tagName.toLowerCase());
        if (tagName === "select") {
            await databaseInput.first().selectOption(database);
        } else {
            await databaseInput.first().fill(database);
        }
    }

    await loginInput.fill(login);
    await passwordInput.fill(password);
    await page.locator('button[type="submit"]').click();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.locator(".alert-danger")).toHaveCount(0);
    await expect(passwordInput).toHaveCount(0, { timeout: 15000 });
}

export function evidenceName(testInfo: TestInfo, name: string) {
    const safe = name.toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
    return testInfo.outputPath(`${safe}.png`);
}

export function requireWriteOptIn() {
    if (process.env.LIVE_UI_ALLOW_WRITE?.toUpperCase() !== "YES") {
        throw new Error(
            "Mutating live UI scenarios require LIVE_UI_ALLOW_WRITE=YES and an explicitly authorized test account.",
        );
    }
}
