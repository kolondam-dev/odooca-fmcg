import { readFile, stat } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { evidenceName, odooBase, publicOnly, targetUrl } from "./helpers";
import { readZipEntry } from "./zip";

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
    selection: string;
};

const FINANCE_ACTIONS: FinanceAction[] = [
    {
        fin: "FIN04",
        xmlid: "id_finance_reporting.action_finance_report_audit_trail",
        label: "Journal Items Audit Trail (FIN04)",
        selection: "FIN04 - Journal Items Audit Trail",
    },
    {
        fin: "FIN05",
        xmlid: "id_finance_reporting.action_finance_report_partner_ledger",
        label: "Partner Ledger AR/AP (FIN05/FIN06)",
        selection: "FIN05/FIN06 - Partner Ledger AR/AP",
    },
    {
        fin: "FIN07",
        xmlid: "id_finance_reporting.action_finance_report_open_items",
        label: "Open Items AR/AP (FIN07)",
        selection: "FIN07 - Open Items AR/AP",
    },
    {
        fin: "FIN08",
        xmlid: "id_finance_reporting.action_finance_report_aged_partner_balance",
        label: "Aged Partner Balance (FIN08/FIN09)",
        selection: "FIN08/FIN09 - Aged Partner Balance",
    },
    {
        fin: "FIN51",
        xmlid: "id_finance_reporting.action_finance_report_combined_trial_balance",
        label: "Combined Trial Balance (FIN51)",
        selection: "FIN51 - Combined Trial Balance",
    },
    {
        fin: "FIN57",
        xmlid: "id_finance_reporting.action_finance_report_sales_purchase_register",
        label: "Sales and Purchase Register (FIN57)",
        selection: "FIN57 - Sales and Purchase Register",
    },
    {
        fin: "FIN37",
        xmlid: "id_finance_reporting.action_finance_report_accrual_schedule",
        label: "Accrual Schedules (FIN37)",
        selection: "FIN37 - Accrual / Prepayment Schedules",
    },
    {
        fin: "FIN38",
        xmlid: "id_finance_reporting.action_finance_report_fx_revaluation",
        label: "FX Revaluation (FIN38)",
        selection: "FIN38 - FX Revaluation",
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

    await page.goto(
        targetUrl(
            "odoo",
            "/odoo/action-id_finance_reporting.action_finance_report_audit_trail",
        ),
        { waitUntil: "domcontentloaded" },
    );

    // The deployed demo uses the id_ui_shell sidebar: applications live in
    // .id_sidebar and sections in .id_panel, which does not carry
    // data-menu-xmlid on every node. Opening a Finance action selects the app
    // and expands the Finance Reports group.
    const app = page
        .locator('[data-menu-xmlid="id_finance_foundation.menu_finance"]')
        .first();
    await expect(app).toBeVisible();

    const panel = page.locator(".id_panel");
    await expect(panel).toBeVisible();
    const section = panel.getByRole("button", {
        name: "Finance Reports",
        exact: true,
    });
    await expect(section).toBeVisible();
    if ((await section.getAttribute("aria-expanded")) !== "true") {
        await section.click();
    }

    const entries = section.locator(
        "xpath=following-sibling::div[contains(@class, 'id_pchildren')]",
    );
    for (const item of FINANCE_MENU) {
        await expect(
            entries.getByRole("button", { name: item.label, exact: true }),
            item.label,
        ).toBeVisible();
    }
    await expect(entries.locator("button.id_pitem--leaf")).toHaveCount(
        FINANCE_MENU.length,
    );
    await expect(entries.locator("button.id_pitem--leaf.is-active")).toHaveText(
        "Audit Trail (FIN04)",
    );

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
        await expect(page.locator(".o_form_view"), action.label).toBeVisible();
        await expect(
            page.locator('.o_field_widget[name="report_type"] input'),
            action.label,
        ).toHaveValue(action.selection);
        await expect(
            page.locator('.o_field_widget[name="company_id"] input'),
            action.label,
        ).toHaveValue(COMPANY);
        await page.screenshot({
            path: evidenceName(testInfo, `${action.fin}-wizard`),
            fullPage: true,
        });
    }

    // Separate pass: the deployed server must render both buttons in the form
    // header. Keeping it after the screenshots means a stale server build still
    // leaves evidence that all eight actions open the right wizard.
    for (const action of FINANCE_ACTIONS) {
        await page.goto(targetUrl("odoo", `/odoo/action-${action.xmlid}`), {
            waitUntil: "domcontentloaded",
        });
        const header = page.locator(".o_form_statusbar");
        for (const button of ["action_run", "action_export_xlsx"]) {
            await expect(
                header.locator(`button[name="${button}"]`),
                `${action.label}: ${button} in header`,
            ).toBeVisible();
        }
        await expect(
            page.locator(
                'footer button[name="action_run"], footer button[name="action_export_xlsx"]',
            ),
            action.label,
        ).toHaveCount(0);
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
    await expect(page.locator(".o_form_view")).toBeVisible();
    await expect(
        page.locator('.o_field_widget[name="company_id"] input'),
    ).toHaveValue(COMPANY);
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

    // Run and Export must be reachable on the full-page wizard. This assertion
    // fails until the server-side view with the header buttons is deployed.
    const header = page.locator(".o_form_statusbar");
    await expect(header.locator('button[name="action_run"]')).toBeVisible();
    await expect(
        header.locator('button[name="action_export_xlsx"]'),
    ).toBeVisible();

    await header.locator('button[name="action_run"]').click();
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
        header.locator('button[name="action_export_xlsx"]').click(),
    ]);
    // The period in the filename proves the July dates reached the report scope.
    expect(download.suggestedFilename()).toBe(
        "FIN04-audit-trail-2026-07-01_2026-07-31.xlsx",
    );
    expect(await download.failure()).toBeNull();

    const saved = await download.path();
    expect(saved, "download path").not.toBeNull();
    expect((await stat(saved!)).size).toBeGreaterThan(0);
    // Structure smoke test: an HTML error page saved as .xlsx would not be a
    // ZIP, and a ZIP that is not a workbook would miss the spreadsheet part.
    // Cell-level reconciliation against the finance payload stays manual UAT.
    const archive = await readFile(saved!);
    expect(archive.subarray(0, 2).toString("latin1")).toBe("PK");
    const contentTypes = readZipEntry(archive, "[Content_Types].xml").toString(
        "utf8",
    );
    expect(contentTypes).toContain("spreadsheetml.sheet.main+xml");
    const workbook = readZipEntry(archive, "xl/workbook.xml").toString("utf8");
    expect(workbook).toContain('name="Summary"');

    await page.screenshot({
        path: evidenceName(testInfo, "fin04-export-xlsx"),
        fullPage: true,
    });
});
