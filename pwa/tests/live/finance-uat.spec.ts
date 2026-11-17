import { open, stat } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { evidenceName, odooBase, publicOnly, targetUrl } from "./helpers";

/**
 * Half of docs/finance/PRODUCTION_FINANCE_UAT.md that a browser session can
 * prove: company scope, the eight Finance Reports entries, one report run, and
 * the XLSX download.
 *
 * Read-only for business data. The only writes are the transient
 * `id.finance.report.wizard` record that the click itself creates and fills
 * (`action_run` and `action_export_xlsx` keep the preview/export there). No
 * account.move, account.move.line, product, category, or configuration record
 * is created, modified, or deleted, so LIVE_UI_ALLOW_WRITE stays NO. The
 * remaining manual steps are listed in the same document.
 */

const COMPANY = "PT Manado Distribusi Utama";

type FinanceAction = {
    fin: string;
    xmlid: string;
    label: string;
    reportType: string;
};

const FINANCE_ACTIONS: FinanceAction[] = [
    {
        fin: "FIN04",
        xmlid: "id_finance_reporting.action_finance_report_audit_trail",
        label: "Journal Items Audit Trail (FIN04)",
        reportType: "audit_trail",
    },
    {
        fin: "FIN05",
        xmlid: "id_finance_reporting.action_finance_report_partner_ledger",
        label: "Partner Ledger AR/AP (FIN05/FIN06)",
        reportType: "partner_ledger",
    },
    {
        fin: "FIN07",
        xmlid: "id_finance_reporting.action_finance_report_open_items",
        label: "Open Items AR/AP (FIN07)",
        reportType: "open_items",
    },
    {
        fin: "FIN08",
        xmlid: "id_finance_reporting.action_finance_report_aged_partner_balance",
        label: "Aged Partner Balance (FIN08/FIN09)",
        reportType: "aged_partner_balance",
    },
    {
        fin: "FIN51",
        xmlid: "id_finance_reporting.action_finance_report_combined_trial_balance",
        label: "Combined Trial Balance (FIN51)",
        reportType: "combined_trial_balance",
    },
    {
        fin: "FIN57",
        xmlid: "id_finance_reporting.action_finance_report_sales_purchase_register",
        label: "Sales and Purchase Register (FIN57)",
        reportType: "sales_purchase_register",
    },
    {
        fin: "FIN37",
        xmlid: "id_finance_reporting.action_finance_report_accrual_schedule",
        label: "Accrual Schedules (FIN37)",
        reportType: "accrual_schedule",
    },
    {
        fin: "FIN38",
        xmlid: "id_finance_reporting.action_finance_report_fx_revaluation",
        label: "FX Revaluation (FIN38)",
        reportType: "fx_revaluation",
    },
];

const FINANCE_MENU = [
    {
        xmlid: "id_finance_foundation.menu_finance_report_audit_trail",
        label: "Audit Trail (FIN04)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_partner_ledger",
        label: "Partner Ledger AR/AP (FIN05/FIN06)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_open_items",
        label: "Open Items AR/AP (FIN07)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_aged_partner_balance",
        label: "Aged Partner Balance (FIN08/FIN09)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_combined_trial_balance",
        label: "Combined Trial Balance (FIN51)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_sales_purchase_register",
        label: "Sales and Purchase Register (FIN57)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_accrual_schedule",
        label: "Accrual Schedules (FIN37)",
    },
    {
        xmlid: "id_finance_foundation.menu_finance_report_fx_revaluation",
        label: "FX Revaluation (FIN38)",
    },
];

type DateOrder = "ymd" | "mdy" | "dmy";

function dateOrder(sample: string): DateOrder {
    const parts = sample.split(/\D+/).filter(Boolean);
    if (parts.length < 3) return "mdy";
    if (parts[0].length === 4) return "ymd";
    const first = Number(parts[0]);
    const second = Number(parts[1]);
    if (first > 12) return "dmy";
    if (second > 12) return "mdy";
    // Both parts can be a month, so compare with today's real month and day.
    const today = new Date();
    if (first === today.getMonth() + 1 && second !== today.getDate()) {
        return "mdy";
    }
    if (second === today.getMonth() + 1 && first !== today.getDate()) {
        return "dmy";
    }
    return "mdy";
}

function formatDateLike(iso: string, sample: string, order: DateOrder) {
    const [year, month, day] = iso.split("-");
    const separator = sample.match(/\D+/)?.[0] ?? "/";
    const parts =
        order === "ymd"
            ? [year, month, day]
            : order === "dmy"
              ? [day, month, year]
              : [month, day, year];
    return parts.join(separator);
}

function parseDisplayed(value: string, order: DateOrder) {
    const parts = value.split(/\D+/).filter(Boolean).map(Number);
    if (parts.length < 3) return null;
    const [first, second, third] = parts;
    if (order === "ymd") return { year: first, month: second, day: third };
    if (order === "dmy") return { year: third, month: second, day: first };
    return { year: third, month: first, day: second };
}

/**
 * Type a date the way the demo user's locale renders it.
 *
 * The Odoo date widget shows a button until it receives focus, then an input
 * pre-filled with the current value. That value reveals the user's field order
 * and separator, so the same text can be built without hard-coding en_US.
 */
async function setDate(page: Page, field: string, iso: string) {
    const widget = page.locator(`.o_field_widget[name="${field}"]`);
    await expect(widget).toBeVisible();

    const button = widget.locator("button").first();
    if (await button.count()) {
        await button.click();
    }
    const input = widget.locator("input").first();
    await expect(input).toBeVisible();

    const sample = await input.inputValue();
    const order = dateOrder(sample);
    await input.fill(formatDateLike(iso, sample, order));
    await input.press("Enter");

    const [year, month, day] = iso.split("-").map(Number);
    await expect
        .poll(async () => {
            const current = widget.locator("input");
            const raw = (await current.count())
                ? await current.first().inputValue()
                : await widget.innerText();
            return parseDisplayed(raw, order);
        })
        .toEqual({ year, month, day });
}

test("@finance-uat @odoo-live Finance app exposes eight Finance Reports menu entries", async ({
    page,
}, testInfo) => {
    test.skip(!odooBase, "LIVE_UI_ODOO_URL is not configured");
    test.skip(publicOnly, "Finance UAT needs an authenticated accounting user");
    test.skip(
        testInfo.project.name !== "live-desktop",
        "Navbar section assertions use the desktop layout",
    );

    await page.goto(targetUrl("odoo", "/odoo"), {
        waitUntil: "domcontentloaded",
    });
    await page.locator(".o_navbar_apps_menu button").first().click();
    await page
        .locator('[data-menu-xmlid="id_finance_foundation.menu_finance"]')
        .first()
        .click();

    const brand = page.locator(
        '.o_menu_brand[data-menu-xmlid="id_finance_foundation.menu_finance"]',
    );
    await expect(brand).toContainText("Finance");

    const section = page.locator(
        'button[data-menu-xmlid="id_finance_foundation.menu_finance_reports"]',
    );
    await expect(section).toContainText("Finance Reports");
    await section.click();

    for (const item of FINANCE_MENU) {
        const entry = page.locator(`[data-menu-xmlid="${item.xmlid}"]`).last();
        await expect(entry, item.label).toBeVisible();
        await expect(entry, item.label).toContainText(item.label);
    }
    await expect(
        page.locator(
            '[data-menu-xmlid^="id_finance_foundation.menu_finance_report_"]',
        ),
    ).toHaveCount(FINANCE_MENU.length);

    await page.screenshot({
        path: evidenceName(testInfo, "finance-menu-eight-reports"),
        fullPage: true,
    });
});

test("@finance-uat @odoo-live every Finance Reports action opens its wizard in company 1", async ({
    page,
}, testInfo) => {
    test.skip(!odooBase, "LIVE_UI_ODOO_URL is not configured");
    test.skip(publicOnly, "Finance UAT needs an authenticated accounting user");
    test.setTimeout(300_000);

    for (const action of FINANCE_ACTIONS) {
        await page.goto(targetUrl("odoo", `/odoo/action-${action.xmlid}`), {
            waitUntil: "domcontentloaded",
        });
        await expect(
            page.locator(".o_control_panel"),
            action.label,
        ).toContainText(action.label);
        await expect(
            page.locator('.o_field_widget[name="report_type"] select'),
            action.label,
        ).toHaveValue(action.reportType);
        await expect(
            page.locator('.o_field_widget[name="company_id"]'),
            action.label,
        ).toContainText(COMPANY);
        await expect(
            page.locator('button[name="action_run"]'),
            action.label,
        ).toBeVisible();
        await page.screenshot({
            path: evidenceName(testInfo, `${action.fin}-wizard`),
            fullPage: true,
        });
    }
});

test("@finance-uat @odoo-live FIN04 runs for July 2026 and downloads an XLSX", async ({
    page,
}, testInfo) => {
    test.skip(!odooBase, "LIVE_UI_ODOO_URL is not configured");
    test.skip(publicOnly, "Finance UAT needs an authenticated accounting user");
    test.setTimeout(180_000);

    await page.goto(
        targetUrl(
            "odoo",
            "/odoo/action-id_finance_reporting.action_finance_report_audit_trail",
        ),
        { waitUntil: "domcontentloaded" },
    );
    await expect(page.locator(".o_control_panel")).toContainText(
        "Journal Items Audit Trail (FIN04)",
    );
    await expect(
        page.locator('.o_field_widget[name="company_id"]'),
    ).toContainText(COMPANY);
    await page.screenshot({
        path: evidenceName(testInfo, "fin04-wizard-company"),
        fullPage: true,
    });

    await setDate(page, "date_from", "2026-07-01");
    await setDate(page, "date_to", "2026-07-31");
    await page.screenshot({
        path: evidenceName(testInfo, "fin04-period-july-2026"),
        fullPage: true,
    });

    await page.locator('button[name="action_run"]').click();
    await expect(
        page.locator('.o_field_widget[name="result_summary"]'),
    ).toContainText("FIN04");
    await expect(page.locator(".o_crash_manager")).toHaveCount(0);
    await page.screenshot({
        path: evidenceName(testInfo, "fin04-run-result"),
        fullPage: true,
    });

    const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.locator('button[name="action_export_xlsx"]').click(),
    ]);
    // The period in the filename proves the July dates reached the report scope.
    expect(download.suggestedFilename()).toBe(
        "FIN04-audit-trail-2026-07-01_2026-07-31.xlsx",
    );
    expect(await download.failure()).toBeNull();

    const saved = await download.path();
    expect(saved, "download path").not.toBeNull();
    expect((await stat(saved!)).size).toBeGreaterThan(0);
    // A workbook is a ZIP container; an HTML error page would not start with PK.
    const handle = await open(saved!, "r");
    const header = Buffer.alloc(2);
    await handle.read(header, 0, 2, 0);
    await handle.close();
    expect(header.toString("latin1")).toBe("PK");

    await page.screenshot({
        path: evidenceName(testInfo, "fin04-export-xlsx"),
        fullPage: true,
    });
});
