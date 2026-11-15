from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_po_occurrences import invalid_occurrences


class TestPoOccurrences(unittest.TestCase):
    def check(self, occurrence: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "id.po"
            path.write_text(f"#: {occurrence}\nmsgid \"X\"\nmsgstr \"Y\"\n", encoding="utf-8")
            return invalid_occurrences(path)

    def test_odoo_code_occurrence_is_valid(self):
        self.assertEqual(self.check("code:addons/id_example/models/example.py:0"), [])

    def test_odoo_model_occurrence_is_valid(self):
        self.assertEqual(self.check("model:ir.model.fields,field_description:id_example.field_x"), [])

    def test_bare_source_path_reproduces_production_failure(self):
        self.assertEqual(
            self.check("addons/id_dashboard_redesign/static/src/action.js"),
            [(1, "addons/id_dashboard_redesign/static/src/action.js")],
        )


if __name__ == "__main__":
    unittest.main()
