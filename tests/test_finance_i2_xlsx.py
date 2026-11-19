"""Offline counterexamples for the I2a XLSX value tie-out module."""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile

SPEC = importlib.util.spec_from_file_location(
    "verify_finance_i2_xlsx",
    Path(__file__).resolve().parents[1] / "scripts/ops/verify_finance_i2_xlsx.py",
)
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def row_xml(index, values):
    cells = []
    for col, value in values.items():
        ref = f"{col}{index}"
        if isinstance(value, str):
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        elif value is not None:
            cells.append(f'<c r="{ref}"><v>{value}</v></c>')
    return f'<row r="{index}">{"".join(cells)}</row>'


def sheet_xml(rows):
    return (f'<worksheet xmlns="{MAIN}"><sheetData>'
            + "".join(row_xml(index, row) for index, row in enumerate(rows, start=1))
            + "</sheetData></worksheet>")


def write_workbook(path, sheets):
    with ZipFile(path, "w") as archive:
        book = "".join(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _rows) in enumerate(sheets, start=1)
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{MAIN}" xmlns:r="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships"><sheets>{book}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{REL}">'
            + "".join(
                f'<Relationship Id="rId{index}" Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        for index, (_name, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml(rows))


class I2XlsxOracleTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.xlsx = Path(self.temp.name) / "report.xlsx"

    def check(self, verifier, *args):
        return verifier(self.xlsx.read_bytes(), *args)

    # ------------------------------------------------------------------ FIN51
    def combined_sheets(self, balance=45):
        rows = [
            ("I2ACOMB00", 100, 75, 30, balance, 145),
            ("I2ACOMB01", 0, 110, 82, 28, 28),
        ]
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("combined_rows", [
                {"A": "code", "B": "initial_balance", "C": "debit", "D": "credit",
                 "E": "balance", "F": "ending_balance"},
                *({"A": code, "B": init, "C": debit, "D": credit, "E": period, "F": ending}
                  for code, init, debit, credit, period, ending in rows),
            ]),
            ("totals", [
                {"A": "key", "B": "value"},
                {"A": "initial_balance", "B": 100},
                {"A": "debit", "B": 185},
                {"A": "credit", "B": 112},
                {"A": "balance", "B": 73},
                {"A": "ending_balance", "B": 173},
            ]),
        ]

    def verify_combined(self):
        return oracle.verify_combined_trial_balance(
            self.xlsx.read_bytes(),
            {"I2ACOMB00": (100, 75, 30, 45, 145), "I2ACOMB01": (0, 110, 82, 28, 28)},
            {"initial_balance": 100, "debit": 185, "credit": 112, "balance": 73,
             "ending_balance": 173},
        )

    def test_combined_trial_balance_matches(self):
        write_workbook(self.xlsx, self.combined_sheets())
        self.assertEqual(self.verify_combined()["rows"], 2)

    def test_combined_balance_mutation_detected(self):
        write_workbook(self.xlsx, self.combined_sheets(balance=46))
        with self.assertRaisesRegex(ValueError, "period balance differs"):
            self.verify_combined()

    def test_combined_missing_code_detected(self):
        sheets = self.combined_sheets()
        sheets[1] = ("combined_rows", sheets[1][1][:2])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            self.verify_combined()

    # ------------------------------------------------------------------ FIN57
    def register_sheets(self, difference=0, duplicates=False, non_register=None):
        if non_register is None:
            non_register = [{"A": 11, "B": 101}, {"A": 12, "B": 102}, {"A": 13, "B": 103}]
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("documents", [
                {"A": "move_type", "B": "net_signed_amount", "C": "tax_signed_amount",
                 "D": "gross_signed_amount"},
                {"A": "out_invoice", "B": 100, "C": 10, "D": 110},
                {"A": "out_refund", "B": -20, "C": -2, "D": -22},
                {"A": "in_invoice", "B": 80, "C": 8, "D": 88},
                {"A": "in_refund", "B": -10, "C": -1, "D": -11},
            ]),
            ("duplicate_move_ids", [{"A": "value"}] + ([{"A": 5}] if duplicates else [])),
            ("duplicate_line_ids", [{"A": "value"}]),
            ("non_register_gl_lines", [{"A": "line_id", "B": "move_id"}, *non_register]),
            ("gl_tie_out", [
                {"A": "account_id", "B": "register_balance", "C": "gl_balance",
                 "D": "non_register_gl_balance", "E": "unexplained_difference",
                 "F": "__nested"},
                {"A": 1, "B": 10, "C": 15 + difference, "D": 5, "E": difference,
                 "F": '{"issues": []}'},
            ]),
        ]

    def verify_register(self, lines=3):
        return oracle.verify_sales_purchase_register(
            self.xlsx.read_bytes(),
            {"out_invoice": (100, 10, 110, 1), "out_refund": (-20, -2, -22, 1),
             "in_invoice": (80, 8, 88, 1), "in_refund": (-10, -1, -11, 1)},
            3, lines,
        )

    def test_sales_purchase_register_matches(self):
        write_workbook(self.xlsx, self.register_sheets())
        result = self.verify_register()
        self.assertEqual((result["documents"], result["tie_out_rows"]), (4, 1))
        self.assertEqual((result["non_register_moves"], result["non_register_rows"]), (3, 3))

    def test_register_duplicate_detected(self):
        write_workbook(self.xlsx, self.register_sheets(duplicates=True))
        with self.assertRaisesRegex(ValueError, "duplicate_move_ids is not empty"):
            self.verify_register()

    def test_register_tie_out_difference_detected(self):
        write_workbook(self.xlsx, self.register_sheets(difference=1))
        with self.assertRaisesRegex(ValueError, "unexplained difference"):
            self.verify_register()

    def test_register_split_document_count_detected(self):
        sheets = self.register_sheets()
        documents = sheets[1][1]
        documents[1] = {"A": "out_invoice", "B": 60, "C": 6, "D": 66}
        documents.insert(2, {"A": "out_invoice", "B": 40, "C": 4, "D": 44})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "out_invoice: expected"):
            self.verify_register()

    def test_register_gross_mutation_detected(self):
        sheets = self.register_sheets()
        sheets[1][1][1]["D"] = 111
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "out_invoice: expected"):
            self.verify_register()

    def test_register_tie_out_arithmetic_detected(self):
        sheets = self.register_sheets()
        sheets[5][1][1]["C"] = 16
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "tie-out arithmetic"):
            self.verify_register()

    def test_register_non_register_move_count_detected(self):
        # Three lines but only two distinct moves.
        sheets = self.register_sheets(
            non_register=[{"A": 11, "B": 101}, {"A": 12, "B": 101}, {"A": 13, "B": 103}],
        )
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "non-register moves: expected 3, got 2"):
            self.verify_register()

    def test_register_non_register_line_count_detected(self):
        # Three distinct moves, four lines: the extra line of move 101 is caught.
        sheets = self.register_sheets(non_register=[
            {"A": 11, "B": 101}, {"A": 12, "B": 101}, {"A": 13, "B": 102}, {"A": 14, "B": 103},
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "non-register lines: expected 3, got 4"):
            self.verify_register()

    def test_register_duplicate_line_ids_detected(self):
        sheets = self.register_sheets(
            non_register=[{"A": 11, "B": 101}, {"A": 11, "B": 102}, {"A": 13, "B": 103}],
        )
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "repeats a line id"):
            self.verify_register()

    # ------------------------------------------------------------------ FIN02
    def trial_balance_sheet(self, ending=110):
        return [("Trial Balance - FINANCE GOLDEN A - IDR", [
            {"A": "Trial Balance - FINANCE GOLDEN A - IDR"},
            {},
            {},
            {"A": "Code", "B": "Account", "C": "Initial balance", "D": "Debit",
             "E": "Credit", "F": "Period balance", "G": "Ending balance"},
            {"A": "FG000", "B": "Golden cash", "C": 100, "D": 10, "E": 0, "F": 10,
             "G": ending},
        ])]

    def test_oca_trial_balance_matches(self):
        write_workbook(self.xlsx, self.trial_balance_sheet())
        expected = {"FG000": (100, 10, 0, 110)}
        self.assertEqual(self.check(oracle.verify_oca_trial_balance, expected)["rows"], 1)

    def test_oca_trial_balance_ending_mutation_detected(self):
        sheets = self.trial_balance_sheet(ending=111)
        sheets[0][1][4].update({"D": 11, "F": 11})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "FIN02 FG000: expected"):
            self.check(oracle.verify_oca_trial_balance, {"FG000": (100, 10, 0, 110)})

    def test_text_amount_in_trial_balance_detected(self):
        sheets = self.trial_balance_sheet()
        sheets[0][1][4]["G"] = "110"
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "numeric cell is missing"):
            self.check(oracle.verify_oca_trial_balance, {"FG000": (100, 10, 0, 110)})

    # ------------------------------------------------------------------ FIN01
    def general_ledger_sheet(self, debit=10, duplicate=False):
        header = {"A": "Date", "B": "Entry", "C": "Journal", "D": "Account", "E": "Taxes",
                  "F": "Partner", "G": "Ref - Label", "H": "Rec.", "I": "Debit",
                  "J": "Credit", "K": "Cumul. Bal."}
        rows = [
            {"A": "General Ledger - FINANCE GOLDEN A - IDR"},
            {"A": "Date range filter", "B": "From: 2026-07-01 To: 2026-07-31"},
            {"A": "Target moves filter", "B": "All posted entries"},
            {"A": "Centralize filter", "B": "No"},
            {},
            {},
            {"A": "FG000 - Golden cash"},
            {},
            header,
            {"F": "Initial balance", "I": 100, "J": 0, "K": 100},
            {"A": "01/07/2026", "B": "INV/1", "C": "FG", "D": "FG000", "G": "sale",
             "I": debit, "J": 0, "K": 100 + debit},
            {"A": "FG000 - Golden cash", "F": "Ending balance", "I": 100 + debit, "J": 0,
             "K": 100 + debit},
            {},
            {},
        ]
        if duplicate:
            rows += [
                {"A": "FG000 - Golden cash"},
                {},
                header,
                {"F": "Initial balance", "I": 100, "J": 0, "K": 100},
                {"A": "FG000 - Golden cash", "F": "Ending balance", "I": 100, "J": 0,
                 "K": 100},
            ]
        return [("General Ledger - FINANCE GOLDEN A - IDR", rows)]

    def test_oca_general_ledger_matches(self):
        write_workbook(self.xlsx, self.general_ledger_sheet())
        result = self.check(oracle.verify_oca_general_ledger,
                            {"FG000": (100, 10, 0, 110)}, 1)
        self.assertEqual((result["accounts"], result["detail_lines"]), (1, 1))

    def test_oca_general_ledger_detail_mutation_detected(self):
        write_workbook(self.xlsx, self.general_ledger_sheet(debit=11))
        with self.assertRaisesRegex(ValueError, "period: expected"):
            self.check(oracle.verify_oca_general_ledger, {"FG000": (100, 10, 0, 110)}, 1)

    def test_oca_general_ledger_duplicate_block_detected(self):
        write_workbook(self.xlsx, self.general_ledger_sheet(duplicate=True))
        with self.assertRaisesRegex(ValueError, "repeats account block"):
            self.check(oracle.verify_oca_general_ledger, {"FG000": (100, 10, 0, 110)}, 1)

    # ------------------------------------------------------------------ FIN03
    def journal_ledger_sheets(self, credit=0):
        header = {"A": "Entry", "B": "Date", "C": "Account", "D": "Partner",
                  "E": "Ref - Label", "F": "Taxes", "G": "Debit", "H": "Credit"}
        return [
            ("Journal Ledger - FINANCE GOLDEN", [
                {"A": "Journal Ledger - FINANCE GOLDEN A - IDR"},
                {"B": "Company", "E": "FINANCE GOLDEN A"},
            ]),
            ("FG A (IDR) - Golden A", [
                {"A": "Journal Ledger"},
                {},
                {},
                header,
                {"A": "MISC/1", "B": "01/07/2026", "C": "FG000", "E": "sale", "G": 10,
                 "H": credit},
                {"A": "MISC/2", "B": "02/07/2026", "C": "FG001", "E": "sale", "G": 0,
                 "H": 10},
            ]),
            ("Tax - FG A (IDR) - Golden A", [{"A": "Tax summary"}]),
        ]

    def test_oca_journal_ledger_matches(self):
        write_workbook(self.xlsx, self.journal_ledger_sheets())
        result = self.check(oracle.verify_oca_journal_ledger, {"FG A": (10, 10, 2)})
        self.assertEqual(result["detail_lines"], 2)
        self.assertEqual(result["cover_sheets"], 1)

    def test_oca_journal_ledger_totals_mutation_detected(self):
        write_workbook(self.xlsx, self.journal_ledger_sheets(credit=1))
        with self.assertRaisesRegex(ValueError, "FIN03 FG A: expected"):
            self.check(oracle.verify_oca_journal_ledger, {"FG A": (10, 10, 2)})

    def test_oca_journal_ledger_missing_journal_detected(self):
        write_workbook(self.xlsx, self.journal_ledger_sheets())
        with self.assertRaisesRegex(ValueError, "journal coverage mismatch"):
            self.check(oracle.verify_oca_journal_ledger, {"FG B": (10, 10, 2)})

    def test_oca_journal_ledger_unknown_headerless_sheet_detected(self):
        sheets = self.journal_ledger_sheets()
        sheets.append(("Unexpected", [{"A": "not a journal detail sheet"}]))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "Unexpected.*no detail header"):
            self.check(oracle.verify_oca_journal_ledger, {"FG A": (10, 10, 2)})

    def test_formula_cell_rejected(self):
        write_workbook(self.xlsx, self.trial_balance_sheet())
        with ZipFile(self.xlsx) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        with ZipFile(self.xlsx, "w") as archive:
            for name, data in parts.items():
                if name == "xl/worksheets/sheet1.xml":
                    data = data.replace(b"</sheetData>", b'<row r="9"><c r="A9"><f>1+1</f>'
                                                            b"<v>2</v></c></row></sheetData>")
                archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "formula cells"):
            self.check(oracle.verify_oca_trial_balance, {"FG000": (100, 10, 0, 110)})


if __name__ == "__main__":
    unittest.main()
