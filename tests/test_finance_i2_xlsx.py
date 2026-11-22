"""Offline counterexamples for the I2a XLSX value tie-out module."""

import importlib.util
import json
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
    def register_sheets(self, difference=0, duplicate_value=None, non_register=None):
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
            ("duplicate_move_ids", [{"A": "value"}]
             + ([{"A": duplicate_value}] if duplicate_value is not None else [])),
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
            {1: (10, 15, 5, 0)},
            3, lines,
        )

    def test_sales_purchase_register_matches(self):
        write_workbook(self.xlsx, self.register_sheets())
        result = self.verify_register()
        self.assertEqual((result["documents"], result["tie_out_rows"]), (4, 1))
        self.assertEqual((result["non_register_moves"], result["non_register_rows"]), (3, 3))

    def test_register_duplicate_detected(self):
        write_workbook(self.xlsx, self.register_sheets(duplicate_value=5))
        with self.assertRaisesRegex(ValueError, "duplicate_move_ids is not empty"):
            self.verify_register()

    def test_register_text_duplicate_detected(self):
        write_workbook(self.xlsx, self.register_sheets(duplicate_value="5"))
        with self.assertRaisesRegex(ValueError, "duplicate_move_ids is not empty"):
            self.verify_register()

    def test_register_native_empty_placeholder_allowed(self):
        sheets = self.register_sheets()
        sheets[2] = ("duplicate_move_ids", [{"A": "No rows."}])
        sheets[3] = ("duplicate_line_ids", [{"A": "Tidak ada baris."}])
        write_workbook(self.xlsx, sheets)
        self.assertEqual(self.verify_register()["documents"], 4)

    def test_register_headerless_text_duplicate_detected(self):
        sheets = self.register_sheets()
        sheets[2] = ("duplicate_move_ids", [{"A": "5"}])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "duplicate_move_ids contains an entry"):
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

    def test_register_offsetting_tie_out_mutation_detected(self):
        sheets = self.register_sheets()
        # Internal arithmetic still balances, but both values differ from AML oracle.
        sheets[5][1][1]["C"] = 115
        sheets[5][1][1]["D"] = 105
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "tie-out account 1: expected"):
            self.verify_register()

    def test_register_duplicate_tie_out_account_detected(self):
        sheets = self.register_sheets()
        sheets[5][1].append(dict(sheets[5][1][1]))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "repeats account id 1"):
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


class I2BXlsxOracleTest(unittest.TestCase):
    """FIN05-FIN09 exported cells must match the independent subledger oracle."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.xlsx = Path(self.temp.name) / "arap.xlsx"

    def verify(self, verifier, *args):
        return verifier(self.xlsx.read_bytes(), *args)

    # ------------------------------------------------------------- FIN05/FIN06
    def ledger_sheets(self, rows=None, totals=None, by_type=None, gl=None):
        rows = rows if rows is not None else [
            (7, "asset_receivable", 0, 110, 82, 28, 28),
            (0, "liability_payable", 0, 53, 100, -47, -47),
        ]
        totals = totals if totals is not None else {
            "opening_balance": 0, "debit": 163, "credit": 182,
            "movement_balance": -19, "closing_balance": -19, "partner_count": 2,
        }
        by_type = by_type if by_type is not None else [
            ("asset_receivable", 0, 110, 82, 28),
            ("liability_payable", 0, 53, 100, -47),
        ]
        gl = gl if gl is not None else (None, -19, -19)
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("rows", [
                {"A": "partner_id", "B": "account_type", "C": "opening_balance",
                 "D": "debit", "E": "credit", "F": "movement_balance",
                 "G": "closing_balance"},
                *({"A": partner, "B": account, "C": opening, "D": debit,
                   "E": credit, "F": movement, "G": closing}
                  for partner, account, opening, debit, credit, movement, closing in rows),
            ]),
            ("totals", [
                {"A": "key", "B": "value"},
                *({"A": key, "B": value} for key, value in totals.items()),
            ]),
            ("by_account_type", [
                {"A": "key", "B": "value"},
                *({"A": account,
                   "B": json.dumps({
                       "opening_balance": opening, "debit": debit,
                       "credit": credit, "closing_balance": closing,
                   })}
                  for account, opening, debit, credit, closing in by_type),
            ]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "subledger_total", "B": gl[1]},
                {"A": "gl_control_total", "B": gl[2]},
                {"A": "difference", "B": gl[1] - gl[2]},
                {"A": "balanced", "B": "Yes" if gl[1] == gl[2] else "No"},
            ]),
        ]

    def verify_ledger(self):
        return self.verify(
            oracle.verify_partner_ledger,
            {(7, "asset_receivable"): (0, 110, 82, 28),
             (0, "liability_payable"): (0, 53, 100, -47)},
            {"opening_balance": 0, "debit": 163, "credit": 182, "closing_balance": -19},
            {"asset_receivable": (0, 110, 82, 28),
             "liability_payable": (0, 53, 100, -47)},
            (-19, -19),
        )

    def test_partner_ledger_matches(self):
        write_workbook(self.xlsx, self.ledger_sheets())
        self.assertEqual(self.verify_ledger()["partners"], 2)

    def test_partner_ledger_row_mutation_detected(self):
        sheets = self.ledger_sheets()
        sheets[1][1][1].update({"D": 111})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "movement differs from debit minus credit"):
            self.verify_ledger()

    def test_partner_ledger_consistent_offset_detected(self):
        sheets = self.ledger_sheets()
        row = sheets[1][1][1]
        row.update({"D": 111, "F": 29, "G": 29})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "expected"):
            self.verify_ledger()

    def test_partner_ledger_duplicate_partner_detected(self):
        sheets = self.ledger_sheets()
        sheets[1][1].append(dict(sheets[1][1][1]))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "repeats partner"):
            self.verify_ledger()

    def test_partner_ledger_partner_count_detected(self):
        sheets = self.ledger_sheets(totals={
            "opening_balance": 0, "debit": 163, "credit": 182,
            "movement_balance": -19, "closing_balance": -19, "partner_count": 1,
        })
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "partner_count"):
            self.verify_ledger()

    def test_partner_ledger_type_split_detected(self):
        sheets = self.ledger_sheets(by_type=[
            ("asset_receivable", 0, 110, 81, 29),
            ("liability_payable", 0, 53, 100, -47),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "asset_receivable"):
            self.verify_ledger()

    def test_partner_ledger_gl_control_detected(self):
        sheets = self.ledger_sheets(gl=(None, -19, -20))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "GL tie-out"):
            self.verify_ledger()

    # ------------------------------------------------------------------ FIN07
    def open_item_sheets(self, rows=None, partners=None, totals=None, gl=None):
        rows = rows if rows is not None else [
            (11, 101, 5, 7, "asset_receivable", "2026-07-01", "2026-07-31", 110, -82, 28),
            (12, 102, 5, 0, "asset_receivable", "2026-07-05", "2026-07-05", 12, 0, 12),
        ]
        partners = partners if partners is not None else [
            (7, "asset_receivable", 28, [11]),
            (0, "asset_receivable", 12, [12]),
        ]
        totals = totals if totals is not None else [("asset_receivable", 40)]
        gl = gl if gl is not None else (40, 40)
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("rows", [
                {"A": "line_id", "B": "move_id", "C": "account_id", "D": "partner_id",
                 "E": "account_type", "F": "date", "G": "due_date", "H": "balance",
                 "I": "matched_amount", "J": "residual"},
                *({"A": line, "B": move, "C": account, "D": partner, "E": account_type,
                   "F": date, "G": due, "H": balance, "I": matched, "J": residual}
                  for line, move, account, partner, account_type, date, due, balance,
                  matched, residual in rows),
            ]),
            ("partners", [
                {"A": "partner_id", "B": "account_type", "C": "residual", "D": "__nested"},
                *({"A": partner, "B": account_type, "C": residual,
                   "D": f'{{"line_ids": {line_ids}}}'}
                  for partner, account_type, residual, line_ids in partners),
            ]),
            ("account_totals", [
                {"A": "account_type", "B": "residual"},
                *({"A": account_type, "B": residual}
                  for account_type, residual in totals),
            ]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "subledger_total", "B": gl[0]},
                {"A": "gl_control_total", "B": gl[1]},
                {"A": "difference", "B": gl[0] - gl[1]},
                {"A": "balanced", "B": "Yes" if gl[0] == gl[1] else "No"},
            ]),
        ]

    def verify_open_items(self):
        return self.verify(
            oracle.verify_open_items,
            {
                11: (101, 5, 7, "asset_receivable", "2026-07-01", "2026-07-31",
                     110, -82, 28),
                12: (102, 5, 0, "asset_receivable", "2026-07-05", "2026-07-05",
                     12, 0, 12),
            },
            {(7, "asset_receivable"): 28, (0, "asset_receivable"): 12},
            {"asset_receivable": 40},
            (40, 40),
        )

    def test_open_items_matches(self):
        write_workbook(self.xlsx, self.open_item_sheets())
        self.assertEqual(self.verify_open_items()["lines"], 2)

    def test_open_items_residual_arithmetic_detected(self):
        sheets = self.open_item_sheets()
        sheets[1][1][1].update({"J": 29})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "residual differs"):
            self.verify_open_items()

    def test_open_items_balanced_mutation_detected(self):
        sheets = self.open_item_sheets()
        sheets[1][1][1].update({"H": 111, "J": 29})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "line 11"):
            self.verify_open_items()

    def test_open_items_duplicate_line_detected(self):
        sheets = self.open_item_sheets()
        sheets[1][1].append(dict(sheets[1][1][1]))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "repeats line id"):
            self.verify_open_items()

    def test_open_items_partner_lines_detected(self):
        sheets = self.open_item_sheets(partners=[
            (7, "asset_receivable", 28, []),
            (0, "asset_receivable", 12, [12]),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "line ids"):
            self.verify_open_items()

    def test_open_items_partner_total_detected(self):
        sheets = self.open_item_sheets(partners=[
            (7, "asset_receivable", 27, [11]),
            (0, "asset_receivable", 12, [12]),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "partner"):
            self.verify_open_items()

    def test_open_items_account_total_detected(self):
        sheets = self.open_item_sheets(totals=[("asset_receivable", 39)])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "total asset_receivable"):
            self.verify_open_items()

    def test_open_items_gl_control_detected(self):
        sheets = self.open_item_sheets(gl=(40, 39))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "GL tie-out"):
            self.verify_open_items()

    def test_open_items_empty_export_allowed(self):
        sheets = [
            ("Summary", [{"A": "Finance report export"}]),
            ("rows", [{"A": "No rows."}]),
            ("partners", [{"A": "Tidak ada baris."}]),
            ("account_totals", [{"A": "No rows."}]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "subledger_total", "B": 0},
                {"A": "gl_control_total", "B": 0},
                {"A": "difference", "B": 0},
                {"A": "balanced", "B": "Yes"},
            ]),
        ]
        write_workbook(self.xlsx, sheets)
        result = oracle.verify_open_items(
            self.xlsx.read_bytes(), {}, {}, {}, (0, 0),
        )
        self.assertEqual(result["lines"], 0)

    def test_open_items_empty_export_nonzero_gl_detected(self):
        sheets = [
            ("Summary", [{"A": "Finance report export"}]),
            ("rows", [{"A": "No rows."}]),
            ("partners", [{"A": "No rows."}]),
            ("account_totals", [{"A": "No rows."}]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "subledger_total", "B": 0},
                {"A": "gl_control_total", "B": 5},
                {"A": "difference", "B": 5},
                {"A": "balanced", "B": "No"},
            ]),
        ]
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "empty GL tie-out"):
            oracle.verify_open_items(self.xlsx.read_bytes(), {}, {}, {}, (0, 0))

    # ------------------------------------------------------------- FIN08/FIN09
    def aged_sheets(self, buckets=None, partners=None, totals=None, details=None,
                    edges=None, gl=None):
        names = ["current", "days_1_30", "days_31_60", "days_61_90",
                 "days_91_120", "older"]
        buckets = buckets if buckets is not None else {
            "current": 12, "days_1_30": 28, "days_31_60": 0,
            "days_61_90": 0, "days_91_120": 0, "older": 0,
        }
        partners = partners if partners is not None else [
            (7, "asset_receivable", 28, {**{name: 0 for name in names},
                                         "days_1_30": 28}, [11]),
            (0, "asset_receivable", 12, {**{name: 0 for name in names},
                                         "current": 12}, [12]),
        ]
        totals = totals if totals is not None else [("asset_receivable", 40)]
        details = details if details is not None else [
            (11, 7, "asset_receivable", "days_1_30", "2026-07-01", 28),
            (12, 0, "asset_receivable", "current", "2026-07-31", 12),
        ]
        edges = edges if edges is not None else [30, 60, 90, 120]
        gl = gl if gl is not None else (40, 40)
        import json as _json
        return [
            ("Summary", [{"A": "Finance report export"}]),
            ("bucket_order", [{"A": "value"}, *({"A": name} for name in names)]),
            ("edges", [{"A": "value"}, *({"A": edge} for edge in edges)]),
            ("buckets", [{"A": "key", "B": "value"},
                         *({"A": key, "B": value} for key, value in buckets.items())]),
            ("partners", [
                {"A": "partner_id", "B": "account_type", "C": "residual", "D": "__nested"},
                *({"A": partner, "B": account_type, "C": residual,
                   "D": _json.dumps({"buckets": partner_buckets, "line_ids": line_ids})}
                  for partner, account_type, residual, partner_buckets, line_ids
                  in partners),
            ]),
            ("account_totals", [
                {"A": "account_type", "B": "residual"},
                *({"A": account_type, "B": residual}
                  for account_type, residual in totals),
            ]),
            ("rows", [
                {"A": "line_id", "B": "partner_id", "C": "account_type",
                 "D": "bucket", "E": "due_date", "F": "residual"},
                *({"A": line, "B": partner, "C": account_type, "D": bucket,
                   "E": due, "F": residual}
                  for line, partner, account_type, bucket, due, residual in details),
            ]),
            ("gl_tie_out", [
                {"A": "key", "B": "value"},
                {"A": "subledger_total", "B": gl[0]},
                {"A": "gl_control_total", "B": gl[1]},
                {"A": "difference", "B": gl[0] - gl[1]},
                {"A": "balanced", "B": "Yes" if gl[0] == gl[1] else "No"},
            ]),
        ]

    def verify_aged(self):
        names = ["current", "days_1_30", "days_31_60", "days_61_90",
                 "days_91_120", "older"]
        return self.verify(
            oracle.verify_aged_partner_balance,
            {"current": 12, "days_1_30": 28, "days_31_60": 0,
             "days_61_90": 0, "days_91_120": 0, "older": 0},
            {(7, "asset_receivable"): {name: (28 if name == "days_1_30" else 0)
                                       for name in names},
             (0, "asset_receivable"): {name: (12 if name == "current" else 0)
                                       for name in names}},
            {"asset_receivable": 40},
            {11: (7, "asset_receivable", "2026-07-01", "days_1_30", 28),
             12: (0, "asset_receivable", "2026-07-31", "current", 12)},
            (40, 40),
            (30, 60, 90, 120),
        )

    def test_aged_partner_balance_matches(self):
        write_workbook(self.xlsx, self.aged_sheets())
        self.assertEqual(self.verify_aged()["lines"], 2)

    def test_aged_bucket_mutation_detected(self):
        sheets = self.aged_sheets()
        for row in sheets[3][1]:
            if row.get("A") == "days_1_30":
                row["B"] = 29
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "bucket days_1_30"):
            self.verify_aged()

    def test_aged_partner_bucket_mutation_detected(self):
        sheets = self.aged_sheets()
        import json as _json
        row = sheets[4][1][1]
        data = _json.loads(row["D"])
        data["buckets"]["days_1_30"] = 29
        row["D"] = _json.dumps(data)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "residual differs from its buckets"):
            self.verify_aged()

    def test_aged_missing_detail_detected(self):
        sheets = self.aged_sheets(details=[
            (11, 7, "asset_receivable", "days_1_30", "2026-07-01", 28),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "detail coverage"):
            self.verify_aged()

    def test_aged_detail_bucket_mutation_detected(self):
        sheets = self.aged_sheets(details=[
            (11, 7, "asset_receivable", "current", "2026-07-01", 28),
            (12, 0, "asset_receivable", "current", "2026-07-31", 12),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "line 11"):
            self.verify_aged()

    def test_aged_edge_mutation_detected(self):
        sheets = self.aged_sheets(edges=[31, 60, 90, 120])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "bucket edges"):
            self.verify_aged()

    def test_aged_gl_control_detected(self):
        sheets = self.aged_sheets(gl=(40, 39))
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "GL tie-out"):
            self.verify_aged()

    def test_aged_partner_line_swap_detected(self):
        names = ["current", "days_1_30", "days_31_60", "days_61_90",
                 "days_91_120", "older"]
        buckets = {name: 0 for name in names}
        customer = dict(buckets, days_1_30=28)
        partnerless = dict(buckets, current=12)
        sheets = self.aged_sheets(partners=[
            (7, "asset_receivable", 28, customer, [12]),
            (0, "asset_receivable", 12, partnerless, [11]),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "line coverage"):
            self.verify_aged()

    def test_aged_detail_partner_swap_detected(self):
        sheets = self.aged_sheets(details=[
            (11, 0, "asset_receivable", "days_1_30", "2026-07-01", 28),
            (12, 7, "asset_receivable", "current", "2026-07-31", 12),
        ])
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "line 11"):
            self.verify_aged()

    def test_aged_partner_orphan_row_detected(self):
        sheets = self.aged_sheets()
        sheets[4][1].append({"A": 7, "C": 28})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "without account_type"):
            self.verify_aged()

    def test_aged_partner_bucket_text_detected(self):
        sheets = self.aged_sheets()
        row = sheets[4][1][1]
        data = json.loads(row["D"])
        data["buckets"]["days_1_30"] = "28"
        row["D"] = json.dumps(data)
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "not a number"):
            self.verify_aged()

    def test_partner_ledger_orphan_row_detected(self):
        sheets = self.ledger_sheets()
        sheets[1][1].append({"A": 7, "B": "", "D": 100})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "without account_type"):
            self.verify_ledger()

    def test_partner_ledger_text_total_detected(self):
        sheets = self.ledger_sheets()
        for row in sheets[2][1]:
            if row.get("A") == "debit":
                row["B"] = "163"
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "numeric cell is missing"):
            self.verify_ledger()

    def test_open_items_partner_orphan_row_detected(self):
        sheets = self.open_item_sheets()
        sheets[2][1].append({"A": 7, "C": 28})
        write_workbook(self.xlsx, sheets)
        with self.assertRaisesRegex(ValueError, "without account_type"):
            self.verify_open_items()
