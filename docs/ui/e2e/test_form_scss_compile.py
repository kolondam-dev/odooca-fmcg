"""Regression test: production id_form.scss must compile with CI's libsass."""

from pathlib import Path
import unittest

import sass


SCSS = Path(__file__).resolve().parents[3] / "addons/id_ui_form/static/src/form/id_form.scss"


class TestFormStylesCompile(unittest.TestCase):
    def test_production_scss_compiles_with_pinned_libsass(self):
        # This intentionally compiles the real asset, not a reduced fixture.
        # CI installs libsass==0.23.0 before unittest discovery.
        css = sass.compile(filename=str(SCSS), output_style="expanded")
        self.assertIn(".oe_subtotal_footer", css)
        self.assertIn("width: 32rem;", css)
        self.assertIn("max-width: 100%;", css)
        # Footer must use bottom-sticky containment (not the top offset that
        # could never pin inside the short containing block).
        self.assertIn("position: sticky !important;", css)
        self.assertIn("bottom: 0 !important;", css)
        # Invoice totals live in a narrow colspan column; the tab must be the
        # sticky element and stack the columns to avoid horizontal overflow.
        self.assertIn(".o_form_view .o_form_sheet .oe_invoice_lines_tab", css)


if __name__ == "__main__":
    unittest.main()
