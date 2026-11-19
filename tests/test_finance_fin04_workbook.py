"""Offline counterexamples for FIN04 XLSX vs independent AML CSV comparator."""

import csv
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

SPEC = importlib.util.spec_from_file_location(
    "verify_finance_fin04_workbook",
    Path(__file__).resolve().parents[1] / "scripts/ops/verify_finance_fin04_workbook.py",
)
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)


def row_xml(index, values):
    cells = "".join(
        f'<c r="{col}{index}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
        if isinstance(value, str) else f'<c r="{col}{index}"><v>{value}</v></c>'
        for col, value in values.items()
    )
    return f'<row r="{index}">{cells}</row>'


def sheet_xml(rows):
    return ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>' + "".join(rows) + '</sheetData></worksheet>')


class WorkbookOracleTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "aml.csv"
        self.xlsx = Path(self.temp.name) / "fin04.xlsx"
        self.aml = [
            {"aml_id": "1", "company_id": "1", "date": "2026-07-01", "parent_state": "posted",
             "journal_id": "3", "account_id": "7", "display_type": "product",
             "debit": "12.5", "credit": "0", "balance": "12.5"},
            {"aml_id": "2", "company_id": "1", "date": "2026-07-02", "parent_state": "posted",
             "journal_id": "3", "account_id": "8", "display_type": "product",
             "debit": "0", "credit": "12.5", "balance": "-12.5"},
            {"aml_id": "3", "company_id": "1", "date": "2026-07-03", "parent_state": "draft",
             "journal_id": "3", "account_id": "7", "display_type": "product",
             "debit": "9", "credit": "0", "balance": "9"},
            {"aml_id": "4", "company_id": "2", "date": "2026-07-01", "parent_state": "posted",
             "journal_id": "3", "account_id": "7", "display_type": "product",
             "debit": "5", "credit": "0", "balance": "5"},
        ]
        self.write_csv()
        self.write_xlsx()

    def write_csv(self):
        with self.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.aml[0]))
            writer.writeheader()
            writer.writerows(self.aml)

    def write_xlsx(self, ids=(1, 2), altered=None, text_amount=False, formula=False):
        cells = [row_xml(1, {"A": "aml_id", "B": "debit", "C": "credit", "D": "balance"})]
        for index, key in enumerate(ids, start=2):
            source = next(item for item in self.aml if int(item["aml_id"]) == key)
            balance = altered if altered is not None and key == 1 else source["balance"]
            cells.append(row_xml(index, {
                "A": key,
                "B": str(source["debit"]) if text_amount else float(source["debit"]),
                "C": float(source["credit"]),
                "D": float(balance),
            }))
        if formula:
            cells.append('<row r="9"><c r="A9"><f>1+1</f><v>2</v></c></row>')
        with ZipFile(self.xlsx, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Summary" sheetId="1" r:id="rId1"/>'
                '<sheet name="rows" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                             '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                             '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml([row_xml(3, {"B": "FIN04 - Audit"})]))
            archive.writestr("xl/worksheets/sheet2.xml", sheet_xml(cells))

    def check(self, **kwargs):
        return oracle.verify(self.csv, self.xlsx, "1", "2026-07-01", "2026-07-31", **kwargs)

    def test_match_and_exclusions(self):
        self.assertEqual(self.check()["rows"], 2)

    def test_amount_mutation_detected(self):
        self.write_xlsx(altered="13.5")
        with self.assertRaisesRegex(ValueError, "amount mismatch"):
            self.check()

    def test_missing_and_duplicate_detected(self):
        self.write_xlsx(ids=(1,))
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            self.check()
        self.write_xlsx(ids=(1, 1, 2))
        with self.assertRaisesRegex(ValueError, "Duplicate XLSX"):
            self.check()

    def test_filter_mismatch_detected(self):
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            self.check(account="7")
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            self.check(posted=False)

    def test_bad_source_detected(self):
        self.aml[0]["balance"] = "13"
        self.write_csv()
        with self.assertRaisesRegex(ValueError, "Source AML"):
            self.check()

    def test_text_number_detected(self):
        self.write_xlsx(text_amount=True)
        with self.assertRaisesRegex(ValueError, "stored as text"):
            self.check()

    def test_formula_detected(self):
        self.write_xlsx(formula=True)
        with self.assertRaisesRegex(ValueError, "formula cells"):
            self.check()

    def test_note_excluded(self):
        self.aml.append({**self.aml[0], "aml_id": "5", "display_type": "line_note"})
        self.write_csv()
        self.assertEqual(self.check()["rows"], 2)


if __name__ == "__main__":
    unittest.main()
