"""Native browser acceptance against a disposable local Odoo database.

Run after d1_fixture.py. Env: D1_TEST_PASSWORD, D1_BROWSER (optional executable),
D1_BASE_URL (default local), D1_SCREENSHOT_DIR (optional, local QA only).
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

base = os.environ.get("D1_BASE_URL", "http://127.0.0.1:18069")
checks = []
errors = []


def check(ok, name):
    assert ok, name
    checks.append(name)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ.get("D1_BROWSER"),
                                         headless=True, args=["--no-sandbox", "--single-process"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: (errors.append(str(error)), print("PAGE_ERROR", str(error), flush=True)))
    page.on("console", lambda message: print("BROWSER", message.text, flush=True) if message.type == "error" else None)
    page.goto(base + "/web/login?db=d1_native")
    page.locator("input[name=login]").fill("admin")
    page.locator("input[name=password]").fill(os.environ["D1_TEST_PASSWORD"])
    page.locator("button[type=submit]").click()
    page.wait_for_url(lambda url: "/odoo" in url and "/web/login" not in url)
    failed_once = [False]

    def fail_first_data(route):
        if failed_once[0]:
            route.continue_()
            return
        failed_once[0] = True
        request = route.request.post_data_json
        route.fulfill(json={"jsonrpc": "2.0", "id": request["id"], "error": {
            "code": 200, "message": "Odoo Server Error", "data": {
                "name": "odoo.exceptions.UserError", "message": "D1 test: narrow the query",
                "arguments": ["D1 test: narrow the query"], "debug": ""}}})

    page.route("**/web/dataset/call_kw/id.dashboard.redesign/get_data", fail_first_data)
    page.goto(base + "/odoo/action-id_dashboard_sales.action_sales_productivity")
    page.locator(".alert-danger").wait_for()
    check("narrow the query" in page.locator(".alert-danger").inner_text(), "Initial source error is actionable")
    page.locator('[data-action="open-period"]').first.click()
    check(page.locator(".d1-popover").is_visible(), "Controls remain usable after initial source error")
    page.locator('[data-action="apply"]').click()

    page.locator(".id-dash-kpis").wait_for()
    page.locator(".d1-controls").wait_for()
    compiled = page.evaluate("""() => {
        const { App, Component } = odoo.loader.modules.get('@odoo/owl');
        const { getTemplate } = odoo.loader.modules.get('@web/core/templates');
        const app = new App(Component, { getTemplate });
        const names = ['KpiCard', 'BarRows', 'TrendChart', 'ComboChart', 'Scatter',
            'DataTable', 'GeoMap', 'CoveragePanel', 'ApprovedControls', 'D1', 'Shell'];
        for (const name of names) app.getTemplate('id_dashboard_ui.' + name);
        return names.length;
    }""")
    check(compiled == 11, "All D1 templates compile in native OWL, including unavailable scatter")
    check(page.locator(".id-dash-kpis > div").count() == 8, "Eight native KPI cards")
    check(not page.locator(".alert-danger").count(), "Initial native RPC succeeds")
    for width in (1440, 1024, 768):
        page.set_viewport_size({"width": width, "height": 1000})
        page.wait_for_timeout(150)
        check(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),
              f"No horizontal page overflow {width}")
        trigger = page.locator('[data-action="open-period"]').first
        trigger.click()
        panel = page.locator(".d1-popover")
        check(panel.is_visible(), f"Period popover opens {width}")
        check(panel.get_attribute("aria-modal") == "false", f"No modal backdrop {width}")
        box = panel.bounding_box()
        check(box["x"] >= 0 and box["x"] + box["width"] <= width + 1, f"Popover within viewport {width}")
        page.keyboard.press("Escape")
        check(not panel.is_visible(), f"Escape discards draft {width}")
        check(trigger.evaluate("el => el === document.activeElement"), f"Trigger focus restored {width}")
        if directory := os.environ.get("D1_SCREENSHOT_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(directory) / f"d1-native-{width}.png"), full_page=True)
            page.locator(".id-dash-action").evaluate("el => el.scrollTop = el.scrollHeight")
            page.screenshot(path=str(Path(directory) / f"d1-native-{width}-bottom.png"), full_page=True)
            page.locator(".id-dash-action").evaluate("el => el.scrollTop = 0")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator('[data-action="open-filter"]').click()
    before = page.locator(".id-dash-main").bounding_box()["y"]
    page.locator('[data-action="pin"]').click()
    check(page.locator(".id-dash-main").bounding_box()["y"] > before + 100, "Inline panel pushes dashboard below")
    page.locator('[data-action="cancel"]').last.click()
    # A real server query with a changed period and comparison, not a preview callback.
    page.locator('[data-action="open-period"]').first.click()
    page.locator('[data-field="from"]').fill("2026-10-10")
    page.locator('[data-field="to"]').fill("2026-10-20")
    page.locator('[data-field="compare"]').check()
    page.locator('[data-action="apply"]').click()
    page.wait_for_function("document.querySelector('.d1-controls').closest('.id-dashboard-controls').dataset.query")
    applied = json.loads(page.locator(".id-dashboard-controls").get_attribute("data-query"))
    check(applied["period"]["from"] == "2026-10-10", "Custom dates committed after native RPC")
    check(not page.locator(".alert-danger").count(), "Custom comparison succeeds")
    page.locator('[data-action="open-filter"]').click()
    page.locator('[data-dimension="sku"]').click()
    choice = page.locator('[data-choice]').first
    choice.check()
    page.locator('[data-action="apply"]').click()
    page.wait_for_function("JSON.parse(document.querySelector('.id-dashboard-controls').dataset.query).filters.sku?.ids.length")
    check(not page.locator(".alert-danger").count(), "SKU filter reaches server")
    # Period and SKU slice must survive the native document action.
    page.locator(".id-dash-row").first.locator('[role="button"]').first.click()
    page.locator(".o_list_view").wait_for()
    page.locator(".o_data_row").first.wait_for()
    check("D1 QA" in page.locator("body").inner_text(), "Scoped drill opens native order lines")
    check(not errors, "No browser JS errors")
    browser.close()
print(json.dumps({"checks": len(checks), "passed": checks}, indent=2))
