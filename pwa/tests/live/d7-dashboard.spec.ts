import { expect, test, type Page } from "@playwright/test";
import { odooBase } from "./helpers";

type Line = { price_subtotal: number; currency_id: [number, string]; product_id: [number, string]; order_id: [number, string] };
type Detail = { net: number; currency: string; lines: number; orders: number; domain: unknown[] };

async function sourceLines(page: Page, domain: unknown[]) {
    const response = await page.request.post(new URL("web/dataset/call_kw/sale.order.line/search_read", odooBase).href, {
        data: { jsonrpc: "2.0", method: "call", params: {
            model: "sale.order.line", method: "search_read",
            args: [domain], kwargs: { fields: ["price_subtotal", "currency_id", "product_id", "order_id"], limit: 2001 },
        } },
    });
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(Array.isArray(payload.result), "Native source lines returned").toBeTruthy();
    const lines = payload.result as Line[];
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.length).toBeLessThan(2001);
    return lines;
}

test("@odoo-live D1 → D7 reconciles and restores July sales scope", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    if (!odooBase) throw new Error("Odoo base URL is required");
    await page.goto(new URL("odoo/action-id_dashboard_sales.action_sales_productivity", odooBase).href);
    const controls = page.locator('.id-dashboard-controls[data-ready="true"]');
    const coverage = page.locator(".id-coverage");
    const row = coverage.getByRole("row", { name: /Calaca/ });
    const active = row.and(coverage.locator("tr.table-active"));
    const source = row.getByRole("button", { name: "Source documents: Calaca" });
    const detailPage = page.locator(".id-dash--d7");

    async function openDetail() {
        await source.click();
        const response = page.waitForResponse(resp => resp.url().endsWith("/get_sales_detail"));
        await page.getByRole("button", { name: "Open detail dashboard", exact: true }).click();
        const payload = await (await response).json();
        await expect(detailPage.getByRole("heading", { name: "Sales detail · Calaca" })).toBeVisible();
        expect(payload.result?.lines).toBeGreaterThan(0);
        return payload.result as Detail;
    }

    async function openCalaca() {
        await coverage.locator('path[data-code="71.71"]').waitFor({ state: "attached" });
        await coverage.locator('path[data-code="71.71"]').press("Enter");
        await coverage.locator('path[aria-label="Wenang"]').press("Enter");
        await coverage.locator('path[aria-label="Calaca"]').press("Enter");
        await expect(active).toBeVisible();
    }

    const back = page.getByRole("button", { name: "Back to Sales Productivity" });
    await controls.locator('[data-action="open-period"]').first().click();
    await controls.locator('[data-field="from"]').fill("2026-07-01");
    await controls.locator('[data-field="to"]').fill("2026-07-31");
    await controls.locator('[data-action="apply"]').click();
    await expect(controls).toHaveAttribute("data-query", /2026-07-01.*2026-07-31/);
    await openCalaca();
    const baseline = await openDetail();
    const [first] = await sourceLines(page, baseline.domain);
    const sku = first.product_id[0];

    await back.click();
    await expect(active).toBeVisible();
    await controls.locator('[data-action="open-filter"]').click();
    await controls.locator('[data-dimension="sku"]').click();
    await controls.locator('[data-field="search"]').fill(first.product_id[1]);
    await controls.locator(`[data-choice="${sku}"]`).check();
    await controls.locator('[data-action="apply"]').click();
    await expect(controls).toHaveAttribute("data-query", /"sku":/);
    const applied = JSON.parse((await controls.getAttribute("data-query"))!);
    expect(applied.filters.sku.ids.map(Number)).toEqual([sku]);
    const chosenVillage = coverage.locator('path[aria-label="Calaca"]');
    if (!(await chosenVillage.count())) await openCalaca();
    else if (!(await active.count())) await chosenVillage.press("Enter");
    await expect(active).toBeVisible();
    const detail = await openDetail();
    await expect(detailPage.getByText("2026-07-01 – 2026-07-31", { exact: false })).toBeVisible();
    await expect(detailPage.getByText(first.product_id[1], { exact: true }).first()).toBeVisible();

    const sourceRead = page.waitForRequest(request => request.url().endsWith("/sale.order.line/web_search_read"));
    await page.getByRole("button", { name: "Matching sales order lines", exact: true }).click();
    const nativeDomain = (await sourceRead).postDataJSON().params.kwargs.domain;
    await expect(page.locator(".o_list_view .o_data_row").first()).toBeVisible();
    expect(nativeDomain).toEqual(detail.domain);
    const lines = await sourceLines(page, nativeDomain);
    expect(lines.every(line => line.product_id[0] === sku && line.currency_id[1] === detail.currency)).toBeTruthy();
    expect(lines.length).toBe(detail.lines);
    expect(new Set(lines.map(line => line.order_id[0])).size).toBe(detail.orders);
    const subtotal = lines.reduce((sum, line) => sum + line.price_subtotal, 0);
    expect(subtotal).toBeCloseTo(detail.net, 2);

    await page.getByRole("link", { name: "Sales detail", exact: true }).click();
    await expect(detailPage.getByRole("heading", { name: "Sales detail · Calaca" })).toBeVisible();
    await back.click();
    await expect(active).toBeVisible();
    await expect(coverage.getByText("Manado › Wenang", { exact: true })).toBeVisible();
    expect(JSON.parse((await controls.getAttribute("data-query"))!)).toEqual(applied);
    await testInfo.attach("reconciliation", {
        contentType: "application/json",
        body: JSON.stringify({ period: applied.period, sku, territory: "Manado / Wenang / Calaca",
            currency: detail.currency, net: detail.net, subtotal, difference: detail.net - subtotal,
            lines: lines.length, orders: detail.orders, contextRestored: true }),
    });
});
