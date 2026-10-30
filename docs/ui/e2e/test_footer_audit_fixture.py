"""Controlled fixture for the bottom-sticky interval used by the Odoo audit.

The supervisor asked for explicit pinned/released evidence on a controlled
bottom-sticky fixture before trusting the same measurement on SO/invoice. This
test injects the *production* ``FOOTER_SCROLL_AUDIT`` function into a synthetic
form and asserts the derived interval, the pinned samples, the release point,
and last-item reachability.
"""
import os
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - CI installs Playwright before discovery
    sync_playwright = None

from js_blocks import js_blocks


def launch_chromium(playwright):
    """Launch Chromium, honouring an explicit binary for local runs."""
    options = {}
    if os.environ.get("UI_SMOKE_CHROMIUM"):
        options["executable_path"] = os.environ["UI_SMOKE_CHROMIUM"]
    try:
        return playwright.chromium.launch(**options)
    except Exception as exc:  # pragma: no cover - depends on local install
        raise unittest.SkipTest(f"Chromium unavailable: {exc}")



ROWS = "\n".join(
    f'<div class="o_data_row" style="height:80px">Line {i}</div>' for i in range(1, 13)
)

FOOTER = """    <div class="o_group fixture-footer">
      <div class="oe_subtotal_footer">Total</div>
    </div>"""

NESTED_FOOTER = """    <div class="o_group fixture-footer">
      <div class="o_group fixture-footer">
        <div class="oe_subtotal_footer">Total</div>
      </div>
    </div>"""

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; padding: 0; }}
.o_form_sheet_bg {{ width: 600px; height: 400px; overflow-y: auto; }}
.o_form_sheet {{ width: 600px; box-sizing: border-box; padding: 0 0 100px; }}
.o_data_row {{ height: 80px; box-sizing: border-box; border-bottom: 1px solid #ddd; }}
.fixture-footer {{ position: sticky; bottom: 0; height: 100px; box-sizing: border-box;
                   background: #fff; border-top: 1px solid #999; }}
.oe_subtotal_footer {{ width: 32rem; max-width: 100%; box-sizing: border-box; }}
</style></head><body>
<div class="o_form_sheet_bg">
  <div class="o_form_sheet">
    <div name="order_line">
{rows}
    </div>
{footer}
  </div>
</div>
</body></html>"""

FIXTURE = TEMPLATE.format(rows=ROWS, footer=FOOTER)
NESTED_FIXTURE = TEMPLATE.format(rows=ROWS, footer=NESTED_FOOTER)

# Same contract, but the containing block starts below the top of the scrollport
# and the sticky box is taller than the room left at scroll start. This is the
# invoice-on-mobile case: Chromium clamps the box to the containing block content
# edge, so the pinned interval must start after the clamp instead of at 0.
CLAMP_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; padding: 0; }}
.o_form_sheet_bg {{ width: 600px; height: 400px; overflow-y: auto; }}
.filler {{ height: 250px; background: #eee; }}
.o_form_sheet {{ box-sizing: border-box; width: 600px; padding: 16px 0 0; }}
.o_data_row {{ height: 80px; box-sizing: border-box; border-bottom: 1px solid #ddd; }}
.fixture-footer {{ position: sticky; bottom: 0; height: 200px; margin-top: 8px;
                   box-sizing: border-box; background: #fff; border-top: 1px solid #999; }}
.oe_subtotal_footer {{ width: 32rem; max-width: 100%; box-sizing: border-box; }}
</style></head><body>
<div class="o_form_sheet_bg">
  <div class="filler"></div>
  <div class="o_form_sheet">
    <div name="order_line">
{rows}
    </div>
{footer}
  </div>
</div>
</body></html>"""

CLAMP_FIXTURE = CLAMP_TEMPLATE.format(rows=ROWS, footer=FOOTER)


class TestFooterStickyIntervalFixture(unittest.TestCase):
    @unittest.skipUnless(sync_playwright, "playwright is required for the sticky fixture")
    def test_bottom_sticky_pins_then_releases_at_derived_interval(self):
        audit = js_blocks()["FOOTER_SCROLL_AUDIT"]
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 900, "height": 600})
            page.set_content(FIXTURE)
            result = page.evaluate(f"({audit})('order_line')")
            browser.close()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["stickyGroupCount"], 1, result)
        self.assertEqual(result["itemCount"], 12, result)
        self.assertEqual(result["itemKind"], "list-row", result)
        # 12 rows * 80 px = 960; footer 100; bottom padding 100; scrollport 400.
        self.assertEqual(result["maxScroll"], 760, result)
        self.assertEqual(result["releaseAt"], 660, result)
        self.assertEqual(result["pinStart"], 0, result)
        self.assertEqual(result["pinEnd"], 660, result)
        self.assertTrue(result["footerVisibleAtStart"], result)
        self.assertTrue(result["stickyEngagedAtLeastTwice"], result)
        self.assertTrue(result["stickyPinned"], result)
        self.assertTrue(result["footerInScrollport"], result)
        self.assertTrue(result["releasedAtEnd"], result)
        self.assertTrue(result["lastItemVisibleAndUncovered"], result)
        self.assertTrue(result["hiddenRowCounterexampleRejected"], result)
        self.assertFalse(result["horizontalOverflow"], result)
        self.assertGreaterEqual(len(result["stickySamples"]), 3, result)

    @unittest.skipUnless(sync_playwright, "playwright is required for the sticky fixture")
    def test_containing_block_clamp_moves_the_pinned_interval_start(self):
        audit = js_blocks()["FOOTER_SCROLL_AUDIT"]
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 900, "height": 600})
            page.set_content(CLAMP_FIXTURE)
            result = page.evaluate(f"({audit})('order_line')")
            browser.close()

        self.assertTrue(result["ok"], result)
        # Content top 250 + padding 16 + margin 8 - pinned top 200 = 74.
        self.assertEqual(result["containingBlockContentTop"], 266, result)
        self.assertEqual(result["pinStart"], 74, result)
        self.assertEqual(result["startOverflowBelow"], 74, result)
        self.assertTrue(result["startClampExplained"], result)
        self.assertTrue(result["stickyPinned"], result)
        self.assertTrue(result["stickyEngagedAtLeastTwice"], result)
        for sample in result["stickySamples"]:
            self.assertGreaterEqual(sample["scrollTop"], 74, sample)
            self.assertLessEqual(sample["drift"], 1, sample)
            self.assertTrue(sample["insideContainingBlockHorizontally"], sample)

    @unittest.skipUnless(sync_playwright, "playwright is required for the sticky fixture")
    def test_nested_sticky_containers_are_rejected(self):
        audit = js_blocks()["FOOTER_SCROLL_AUDIT"]
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page(viewport={"width": 900, "height": 600})
            page.set_content(NESTED_FIXTURE)
            result = page.evaluate(f"({audit})('order_line')")
            browser.close()

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["stickyGroupCount"], 2, result)


if __name__ == "__main__":
    unittest.main()
