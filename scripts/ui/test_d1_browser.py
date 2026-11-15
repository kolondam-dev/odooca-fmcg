"""Native browser acceptance against a disposable local Odoo database.

Run after d1_fixture.py. Env: D1_TEST_PASSWORD, D1_BROWSER (optional executable),
D1_BASE_URL (default local), D1_DB (default d1_native), D1_SCREENSHOT_DIR
(default d1-visual). CI supplies D1_EXPECTATIONS_FILE and runtime source hashes.
"""
import json
import os
from urllib.parse import urlparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from d1_evidence import REPORT, capture, checked, full_dashboard, set_page

base = os.environ.get("D1_BASE_URL", "http://127.0.0.1:18069")
database = os.environ.get("D1_DB", "d1_native")
if not database.startswith("d1_") or urlparse(base).hostname not in ("127.0.0.1", "localhost"):
    raise RuntimeError("D1 visual runner requires a disposable local database")
checks = []
errors = []


def check(ok, name):
    checked(ok, name)
    checks.append(name)


def click_dashboards_menu(page):
    menu = page.locator('[data-menu-xmlid="spreadsheet_dashboard.spreadsheet_dashboard_menu_root"]:visible')
    if not menu.count():
        page.locator('button[title="Home Menu"]').click()
    menu.first.click()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ.get("D1_BROWSER"),
                                         headless=True, args=["--no-sandbox", "--single-process"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    set_page(page)
    page.on("pageerror", lambda error: (errors.append(str(error)), print("PAGE_ERROR", str(error), flush=True)))
    page.on("console", lambda message: print("BROWSER", message.text, flush=True) if message.type == "error" else None)
    page.goto(base + "/web/login?db=" + database)
    page.locator("input[name=login]").fill("admin")
    page.locator("input[name=password]").fill(os.environ["D1_TEST_PASSWORD"])
    page.locator("button[type=submit]").click()
    page.wait_for_url(lambda url: "/odoo" in url and "/web/login" not in url)
    failed_once = [False]
    retry_captured = [False]

    def fail_first_data(route):
        if failed_once[0]:
            if not retry_captured[0]:
                page.wait_for_timeout(100)
                capture(page, "loading-retry-1440")
                retry_captured[0] = True
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
    capture(page, "initial-error-1440")
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
    action_scroll = page.locator(".id-d1-scroll")
    page.mouse.move(800, 650)
    page.mouse.wheel(0, 440)
    page.wait_for_function("document.querySelector('.id-d1-scroll').scrollTop > 0")
    check(action_scroll.evaluate("el => getComputedStyle(el).overflowY") == "auto",
          "D1 action scrolls with the mouse wheel")
    coverage = page.locator(".id-coverage")
    city = coverage.locator('path[data-code="71.71"]')
    city.scroll_into_view_if_needed()
    # Use a point inside the actual filled polygon, including on irregular coastline shapes.
    point = city.evaluate("""el => {
        const bounds = el.getBBox();
        const transform = el.getScreenCTM();
        for (let y = 1; y < 20; y++) for (let x = 1; x < 20; x++) {
            const p = new DOMPoint(bounds.x + bounds.width * x / 20, bounds.y + bounds.height * y / 20);
            if (!el.isPointInFill(p)) continue;
            const screen = p.matrixTransform(transform);
            if (document.elementFromPoint(screen.x, screen.y) === el) return [screen.x, screen.y];
        }
        return null;
    }""")
    check(bool(point), "Manado polygon is a reachable pointer target")
    page.mouse.click(*point)
    district_map = coverage.locator('svg[aria-label="District"]')
    district_map.wait_for()
    check(coverage.get_by_role("columnheader", name="District").is_visible(),
          "City click updates map and district ranking")
    district = district_map.locator('path[aria-label="Wenang"]')
    district_value = coverage.get_by_role("row", name="Wenang").locator("td").last.inner_text()
    check("100%" in district_value, "District ranking includes all selected Manado sales")
    district.press("Enter")
    coverage.locator('svg[aria-label="Village / ward"]').wait_for()
    check(coverage.get_by_role("columnheader", name="Village / ward").is_visible(),
          "District keyboard activation updates map and village ranking")
    village_value = coverage.get_by_role("row", name="Calaca").locator("td").last.inner_text()
    check(village_value == district_value, "Village ranking reconciles to its parent district")
    up = coverage.get_by_role("button", name="Back one level")
    up.click()
    district_map.wait_for()
    up.click()
    city.wait_for()
    check(not up.count(), "Two drill-up actions restore the city level")
    action_scroll.evaluate("el => el.scrollTop = 0")
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
        capture(page, f"period-open-{width}")
        page.keyboard.press("Escape")
        check(not panel.is_visible(), f"Escape discards draft {width}")
        check(trigger.evaluate("el => el === document.activeElement"), f"Trigger focus restored {width}")
        capture(page, f"dashboard-top-{width}")
        full_dashboard(page, f"dashboard-{width}")
        page.locator('[data-action="open-filter"]').click()
        capture(page, f"filter-open-{width}")
        filter_box = page.locator(".d1-popover").bounding_box()
        check(filter_box["x"] >= 0 and filter_box["x"] + filter_box["width"] <= width + 1,
              f"Filter panel within viewport {width}")
        page.locator('[data-action="pin"]').click()
        capture(page, f"filter-inline-{width}")
        page.locator('[data-action="pin"]').click()
        footer = page.locator('[data-action="cancel"]').last
        footer.scroll_into_view_if_needed()
        check(footer.evaluate("""el => {
            const b=el.getBoundingClientRect();
            return el.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2));
        }"""),
              f"Unpinned filter footer receives pointer {width}")
        footer.click()
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
    applied = json.loads(page.locator(".id-dashboard-controls").get_attribute("data-query"))
    city.press("Enter")
    district_map.wait_for()
    district.press("Enter")
    village_map = coverage.locator('svg[aria-label="Village / ward"]')
    village_map.wait_for()
    village_map.locator('path[aria-label="Calaca"]').press("Enter")
    selected_row = coverage.get_by_role("row", name="Calaca")
    active_calaca = selected_row.and_(coverage.locator("tr.table-active"))
    expect(active_calaca).to_be_visible()
    selected_row.get_by_role("button", name="Source documents: Calaca").click()
    page.get_by_role("button", name="Matching sales order lines", exact=True).click()
    page.locator(".o_list_view").wait_for()
    page.locator(".o_data_row").first.wait_for()
    check("D1 QA" in page.locator("body").inner_text(), "Scoped drill opens native order lines")
    capture(page, "scoped-native-drill-1440")
    page.get_by_role("link", name="Sales Performance & Salesforce Productivity").click()
    controls = page.locator('.id-dashboard-controls[data-ready="true"]')
    controls.wait_for()
    restored = controls.evaluate("(root) => root.__controls.getState()")
    check(restored["period"] == applied["period"], "D1 breadcrumb restores the applied period")
    check(restored["filters"]["sku"] == applied["filters"]["sku"], "D1 breadcrumb restores the exact SKU filter")
    village_map.wait_for()
    check(coverage.get_by_text("Manado › Wenang", exact=True).is_visible(), "D1 restores the geographic path")
    expect(active_calaca).to_be_visible()
    if expectations := os.environ.get("D1_EXPECTATIONS_FILE"):
        evidence = json.loads(Path(expectations).read_text())
        wanted = evidence["expected"]
        REPORT["fixture_reconciliation_checks"] = evidence["reconciliation"]
        query = {"period": {"from": "2026-10-01", "to": "2026-10-31", "compare": False}, "filters": {}}

        def native_source(client, selected_query):
            response = client.post(base + "/web/dataset/call_kw/id.dashboard.redesign/get_data", data=json.dumps({
                "jsonrpc": "2.0", "id": 9, "method": "call", "params": {
                    "model": "id.dashboard.redesign", "method": "get_data", "args": ["D1"],
                    "kwargs": {"params": {"query": selected_query}}}}), headers={"Content-Type": "application/json"})
            result = response.json()
            check("error" not in result, "Native authenticated reconciliation RPC succeeds")
            return result["result"]["source"]

        actual = native_source(page.request, query)
        for key in ("net", "gross", "discount", "orders"):
            check(abs(actual["total"][key] - wanted[key]) < .001, "Browser whole-scope reconciliation " + key)
        check(actual["target"]["amount"] == wanted["target"], "Browser target reconciliation")
        check(actual["refund"]["amount"] == wanted["refund"], "Browser posted refund reconciliation")
        check(actual["total"]["pjp"]["effective"] == wanted["effective"], "Browser accepted-call reconciliation")
        page.goto(base + "/odoo/action-id_dashboard_sales.action_sales_productivity")
        page.locator(".id-dash-kpis").wait_for()
        page.locator('[data-action="open-period"]').first.click()
        page.locator('[data-field="from"]').fill("2026-09-01")
        page.locator('[data-field="to"]').fill("2026-09-30")
        page.locator('[data-action="apply"]').click()
        page.wait_for_function("document.querySelector('.id-dashboard-controls').dataset.query?.includes('2026-09-01')")
        line_label = page.locator('[data-role="combo-line-value"]').last
        line_label.scroll_into_view_if_needed()
        line_box = line_label.bounding_box()
        bar_box = page.locator('[data-role="combo-bar-value"]').last.bounding_box()
        check(line_box["y"] + line_box["height"] + 1 <= bar_box["y"],
              "Negative monthly line and bar labels do not overlap")
        page.locator(".id-dash-action").evaluate("el => el.scrollTop = 0")
        capture(page, "negative-unavailable-1440")
        full_dashboard(page, "negative-1440")
        negative = native_source(page.request, {**query, "period": {"from": "2026-09-01", "to": "2026-09-30"}})
        check(negative["total"]["net"] == wanted["negative_net"], "Negative source remains signed")
        check(not negative["target"]["available"], "Missing target is unavailable")
        check("—%" not in page.locator(".id-dash-main").inner_text(),
              "Unavailable achievement has no percentage suffix")
        own_browser = playwright.chromium.launch(executable_path=os.environ.get("D1_BROWSER"),
            headless=True, args=["--no-sandbox", "--single-process"])
        own_page = own_browser.new_page(viewport={"width": 1440, "height": 1000})
        set_page(own_page)
        own_page.goto(base + "/web/login?db=" + database)
        own_page.locator("input[name=login]").fill(wanted["first_user"])
        own_page.locator("input[name=password]").fill(os.environ["D1_TEST_PASSWORD"])
        own_page.locator("button[type=submit]").click()
        own_page.wait_for_url(lambda url: "/odoo" in url and "/web/login" not in url)
        click_dashboards_menu(own_page)
        own_page.locator(".id-dash-kpis").wait_for()
        own = native_source(own_page.request, query)
        check(abs(own["total"]["net"] - wanted["first_user_net"]) < .001, "Salesperson browser respects own sales")
        check(own["total"]["orders"] == 28, "Salesperson browser cannot see other users' orders")
        capture(own_page, "own-sales-role-1440")
        full_dashboard(own_page, "own-sales-role-1440")
        check(own_page.locator(".id-d1-scroll").is_visible(), "Dashboards menu opens D1 for Sales")
        own_browser.close()
        no_sales_browser = playwright.chromium.launch(executable_path=os.environ.get("D1_BROWSER"),
            headless=True, args=["--no-sandbox", "--single-process"])
        no_sales_page = no_sales_browser.new_page(viewport={"width": 1440, "height": 1000})
        no_sales_page.goto(base + "/web/login?db=" + database)
        no_sales_page.locator("input[name=login]").fill("d1-visual-no-sales")
        no_sales_page.locator("input[name=password]").fill(os.environ["D1_TEST_PASSWORD"])
        no_sales_page.locator("button[type=submit]").click()
        no_sales_page.wait_for_url(lambda url: "/odoo" in url and "/web/login" not in url)
        click_dashboards_menu(no_sales_page)
        no_sales_page.locator(".o_spreadsheet_dashboard_action").wait_for()
        check(not no_sales_page.locator(".id-d1-scroll").count(), "Dashboards menu keeps Odoo for non-Sales")
        no_sales_browser.close()
        set_page(page)
    check(not errors, "No browser JS errors")
    REPORT["status"] = "PASS"
    browser.close()
print(json.dumps({"checks": len(checks), "passed": checks}, indent=2))
