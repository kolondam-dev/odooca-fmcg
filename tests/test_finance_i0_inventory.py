"""Safety and source-discovery regressions for the operator-only I0 audit."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "finance_i0_inventory", Path(__file__).parents[1] / "scripts/ops/finance_i0_inventory.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class InventoryTests(unittest.TestCase):
    def test_dependency_closure_and_ambiguous_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in {
                "account": "{'depends': ['missing', 'base'], 'license': 'LGPL-3'}",
                "base": "{'depends': ['account']}",
            }.items():
                (root / name).mkdir()
                (root / name / "__manifest__.py").write_text(text)
            result = audit.source_inventory([root])
            self.assertEqual(result["missing"]["status"], "MISSING_SOURCE")
            self.assertEqual(result["base"]["status"], "MANIFEST_ONLY")
            self.assertEqual(len(result["account"]["sha256"]), 64)
            duplicate = audit.source_inventory([root, root])
            self.assertEqual(duplicate["account"]["status"], "AMBIGUOUS_SOURCE")

    def test_manifest_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "account").mkdir()
            (root / "account/__manifest__.py").write_text("__import__('sys').exit(99)")
            result = audit.source_inventory([root])
            self.assertEqual(result["account"]["status"], "UNPARSEABLE_MANIFEST")

    def test_readonly_transaction_rollback_and_redacted_failure(self):
        class Cursor:
            description = [("count",)]

            def __init__(self):
                self.commands = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, query):
                self.commands.append(query)
                if query == "SELECT broken":
                    raise ValueError("sensitive connection or business data")

            def fetchone(self):
                return ("on",)

            def fetchall(self):
                return [(3,)]

        class Connection:
            def __init__(self):
                self.reader = Cursor()
                self.rolled_back = False

            def set_session(self, **kwargs):
                self.settings = kwargs

            def cursor(self):
                return self.reader

            def rollback(self):
                self.rolled_back = True

        connection = Connection()
        with patch.object(audit, "QUERIES", {"bad": "SELECT broken", "good": "SELECT 3"}):
            report = audit.collect(connection, [])
        self.assertTrue(connection.settings["readonly"])
        self.assertFalse(connection.settings["autocommit"])
        self.assertTrue(connection.rolled_back)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["errors"], {"bad": "ValueError"})
        self.assertEqual(report["database"]["good"], [{"count": 3}])
        self.assertIn("ROLLBACK TO SAVEPOINT audit_section", connection.reader.commands)
        self.assertNotIn("sensitive", str(report))


if __name__ == "__main__":
    unittest.main()
