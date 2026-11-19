#!/usr/bin/env python3
"""Value tie-out for the I2a XLSX exports against native report oracles.

No Odoo import: this module reads an already produced workbook and compares
stored cell values with figures computed independently from journal items
(``independent_aml_oracle``) or from the I2A expected tables. It never writes
business data and never prints row values.

The layout checks are deliberately narrow. A renamed, reordered or newly typed
column fails loudly instead of silently skipping a cell. Two workbook families
are supported:

* the custom finance wizard (FIN51/FIN57), whose sheets are named after the
  snapshot sections and use a ``key``/``value`` pair for dictionaries;
* the OCA ``account_financial_report`` XLSX reports (FIN01/FIN02/FIN03), whose
  headers, amount columns and balance labels are fixed by the pinned module.

Only the exact disposable reports database may feed this comparison; the
ledger verification script enforces that boundary before calling in.
"""

import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import NamedTuple
from zipfile import ZipFile

NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_ID = f"{{{NS['r']}}}id"
COLUMN = re.compile(r"[A-Z]+")


class Cell(NamedTuple):
    value: str
    kind: str  # "n" numeric, "s" string, "b" boolean, "blank" empty


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decimal(value, label="value"):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} is not numeric") from exc
    require(result.is_finite(), f"{label} is not finite")
    return result


def _shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall("x:si", NS)]


def _cell(cell, strings):
    inline = cell.find("x:is", NS)
    if inline is not None:
        return Cell("".join(inline.itertext()), "s")
    value = cell.find("x:v", NS)
    kind = cell.get("t")
    if value is None or (value.text is None and kind not in ("s",)):
        return Cell("", "blank")
    raw = value.text or ""
    if kind == "s":
        try:
            index = int(raw)
        except ValueError as exc:
            raise ValueError("Workbook has a malformed shared string index") from exc
        require(0 <= index < len(strings), "Workbook shared string index is out of range")
        return Cell(strings[index], "s")
    if kind in (None, "n"):
        return Cell(raw, "n")
    if kind in ("str", "e"):
        return Cell(raw, "s")
    if kind == "b":
        return Cell(raw, "b")
    return Cell(raw, "s")


def _sheet_rows(data, strings):
    root = ET.fromstring(data)
    require(not root.findall(".//x:f", NS), "Workbook contains formula cells")
    rows = []
    for row in root.findall(".//x:sheetData/x:row", NS):
        cells = {}
        for cell in row.findall("x:c", NS):
            column = COLUMN.match(cell.attrib.get("r", ""))
            require(column is not None, "Cell has no column reference")
            letter = column.group()
            require(letter not in cells, f"Workbook repeats column {letter} in one row")
            cells[letter] = _cell(cell, strings)
        rows.append(cells)
    return rows


def read_workbook(source):
    """Return ``{sheet name: rows}``; each row maps a column letter to a Cell."""
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    require(data[:2] == b"PK", "XLSX export is not a ZIP archive")
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        require("xl/workbook.xml" in names, "XLSX workbook part is missing")
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        require("xl/_rels/workbook.xml.rels" in names, "XLSX workbook relationships are missing")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation = {node.get("Id"): node.get("Target")
                    for node in rels.findall(f"{{{REL}}}Relationship")}
        strings = _shared_strings(archive)
        sheets = {}
        for node in book.findall("x:sheets/x:sheet", NS):
            name = node.get("name")
            target = relation.get(node.get(REL_ID))
            require(bool(target), f"Workbook sheet {name!r} has no relationship")
            part = target.lstrip("/") if target.startswith("/") else "xl/" + target
            require(part in names, f"Workbook sheet part is missing: {part}")
            require(name not in sheets, f"Workbook repeats sheet {name!r}")
            sheets[name] = _sheet_rows(archive.read(part), strings)
        require(bool(sheets), "Workbook has no worksheet")
        return sheets


def _text(row, column):
    cell = row.get(column)
    return cell.value if cell else ""


def _number(row, column, where):
    cell = row.get(column)
    require(cell is not None and cell.kind == "n", f"{where}: numeric cell is missing")
    return decimal(cell.value, where)


def _header(rows, required, where):
    for index, row in enumerate(rows):
        names = {}
        for column, cell in row.items():
            if cell.kind == "s" and cell.value.strip():
                names.setdefault(cell.value.strip(), column)
        if required <= set(names):
            return index, names
    raise ValueError(f"{where}: header row {sorted(required)} not found")


def _single_sheet(sheets, where):
    require(len(sheets) == 1, f"{where}: expected one worksheet, got {sorted(sheets)}")
    return next(iter(sheets.values()))


def _dict_sheet(rows, where):
    index, columns = _header(rows, {"key", "value"}, where)
    values = {}
    for row in rows[index + 1:]:
        key = _text(row, columns["key"]).strip()
        if not key:
            continue
        require(key not in values, f"{where}: duplicate key {key!r}")
        values[key] = _number(row, columns["value"], f"{where} {key}")
    return values


def verify_combined_trial_balance(workbook, expected_rows, expected_totals):
    """FIN51: every combined account row and the totals sheet must tie out."""
    sheets = read_workbook(workbook)
    require("combined_rows" in sheets, "FIN51 workbook has no combined_rows sheet")
    fields = ("initial_balance", "debit", "credit", "balance", "ending_balance")
    index, columns = _header(sheets["combined_rows"], {"code", *fields}, "FIN51 combined_rows")
    seen = {}
    for row in sheets["combined_rows"][index + 1:]:
        code = _text(row, columns["code"]).strip()
        if not code:
            continue
        require(code not in seen, f"FIN51 workbook repeats combined code {code!r}")
        values = tuple(
            _number(row, columns[field], f"FIN51 {code} {field}") for field in fields
        )
        require(values[3] == values[1] - values[2],
                f"FIN51 {code}: period balance differs from debit minus credit")
        require(values[4] == values[0] + values[3],
                f"FIN51 {code}: ending balance differs from opening plus period balance")
        seen[code] = values
    expected = {
        code: tuple(decimal(value, f"expected {code}") for value in values)
        for code, values in expected_rows.items()
    }
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    require(not missing and not extra,
            f"FIN51 combined coverage mismatch: missing={missing}, extra={extra}")
    for code, wanted in expected.items():
        require(seen[code] == wanted,
                f"FIN51 {code}: expected {wanted}, got {seen[code]}")
    require("totals" in sheets, "FIN51 workbook has no totals sheet")
    totals = _dict_sheet(sheets["totals"], "FIN51 totals")
    wanted_totals = {key: decimal(value, f"expected total {key}")
                     for key, value in expected_totals.items()}
    require(set(totals) == set(wanted_totals),
            f"FIN51 totals keys mismatch: {sorted(totals)} != {sorted(wanted_totals)}")
    for key, wanted in wanted_totals.items():
        require(totals[key] == wanted, f"FIN51 total {key}: expected {wanted}, got {totals[key]}")
    return {"result": "PASS", "report_id": "FIN51", "rows": len(seen)}


def verify_sales_purchase_register(workbook, expected_documents, expected_non_register_moves,
                                   expected_non_register_lines=None):
    """FIN57: document amounts per type, empty duplicate lists, clean GL tie-out.

    ``expected_non_register_moves`` counts the distinct posted moves that touch a
    tracked register account without being an invoice or bill (one move can post
    two lines), while ``expected_non_register_lines`` pins the row count of the
    exported sheet when the caller knows the snapshot's line count.
    """
    sheets = read_workbook(workbook)
    require("documents" in sheets, "FIN57 workbook has no documents sheet")
    index, columns = _header(
        sheets["documents"],
        {"move_type", "net_signed_amount", "tax_signed_amount", "gross_signed_amount"},
        "FIN57 documents",
    )
    seen = {}
    for row in sheets["documents"][index + 1:]:
        move_type = _text(row, columns["move_type"]).strip()
        if not move_type:
            continue
        require(move_type in expected_documents,
                f"FIN57 workbook has unexpected document type {move_type!r}")
        net = _number(row, columns["net_signed_amount"], f"FIN57 {move_type} net")
        tax = _number(row, columns["tax_signed_amount"], f"FIN57 {move_type} tax")
        gross = _number(row, columns["gross_signed_amount"], f"FIN57 {move_type} gross")
        totals = seen.setdefault(move_type, [Decimal(0), Decimal(0), Decimal(0), 0])
        totals[0] += net
        totals[1] += tax
        totals[2] += gross
        totals[3] += 1
    require(set(seen) == set(expected_documents),
            f"FIN57 document type coverage mismatch: {sorted(seen)} != {sorted(expected_documents)}")
    for move_type, (net, tax, gross, count) in expected_documents.items():
        wanted = (
            decimal(net, "expected net"),
            decimal(tax, "expected tax"),
            decimal(gross, "expected gross"),
            int(count),
        )
        got = seen[move_type]
        require(tuple(got) == wanted,
                f"FIN57 {move_type}: expected {wanted}, got {tuple(got)}")
    for name in ("duplicate_move_ids", "duplicate_line_ids"):
        require(name in sheets, f"FIN57 workbook has no {name} sheet")
        values = [cell.value for row in sheets[name] for cell in row.values() if cell.kind == "n"]
        require(not values, f"FIN57 {name} is not empty: {len(values)} duplicate ids")
    require("gl_tie_out" in sheets, "FIN57 workbook has no gl_tie_out sheet")
    index, columns = _header(
        sheets["gl_tie_out"],
        {"account_id", "register_balance", "gl_balance", "non_register_gl_balance",
         "unexplained_difference"},
        "FIN57 gl_tie_out",
    )
    tie_rows = 0
    for row in sheets["gl_tie_out"][index + 1:]:
        account = row.get(columns["account_id"])
        if account is None or account.kind != "n":
            continue
        tie_rows += 1
        register = _number(row, columns["register_balance"], "FIN57 register balance")
        gl_balance = _number(row, columns["gl_balance"], "FIN57 GL balance")
        non_register = _number(
            row, columns["non_register_gl_balance"], "FIN57 non-register GL balance",
        )
        difference = _number(row, columns["unexplained_difference"], "FIN57 tie-out difference")
        require(gl_balance - register - non_register == difference,
                "FIN57 tie-out arithmetic differs from its exported values")
        require(difference == 0, f"FIN57 tie-out leaves an unexplained difference: {difference}")
        nested_column = columns.get("__nested")
        nested = _text(row, nested_column) if nested_column else ""
        require("unexplained_register_gl_difference" not in nested,
                "FIN57 tie-out still reports an unexplained register/GL difference")
    require(tie_rows > 0, "FIN57 workbook has no GL tie-out rows")
    require("non_register_gl_lines" in sheets, "FIN57 workbook has no non_register_gl_lines sheet")
    index, columns = _header(sheets["non_register_gl_lines"], {"line_id", "move_id"},
                             "FIN57 non_register_gl_lines")
    line_ids = set()
    move_ids = set()
    for row in sheets["non_register_gl_lines"][index + 1:]:
        cell = row.get(columns["line_id"])
        if cell is None or cell.kind != "n":
            continue
        line_id = decimal(cell.value, "FIN57 non-register line id")
        require(line_id not in line_ids, "FIN57 non-register sheet repeats a line id")
        line_ids.add(line_id)
        move_cell = row.get(columns["move_id"])
        require(move_cell is not None and move_cell.kind == "n",
                "FIN57 non-register row has no numeric move id")
        move_ids.add(decimal(move_cell.value, "FIN57 non-register move id"))
    require(len(move_ids) == expected_non_register_moves,
            "FIN57 non-register moves: expected "
            f"{expected_non_register_moves}, got {len(move_ids)}")
    if expected_non_register_lines is not None:
        require(len(line_ids) == expected_non_register_lines,
                "FIN57 non-register lines: expected "
                f"{expected_non_register_lines}, got {len(line_ids)}")
    return {"result": "PASS", "report_id": "FIN57", "documents": sum(v[3] for v in seen.values()),
            "tie_out_rows": tie_rows, "non_register_moves": len(move_ids),
            "non_register_rows": len(line_ids)}


def verify_oca_trial_balance(workbook, expected_by_code):
    """FIN02: every account row must equal the independent AML oracle."""
    rows = _single_sheet(read_workbook(workbook), "FIN02")
    index, columns = _header(
        rows,
        {"Code", "Account", "Initial balance", "Debit", "Credit", "Period balance",
         "Ending balance"},
        "FIN02",
    )
    seen = {}
    for row in rows[index + 1:]:
        code = _text(row, columns["Code"]).strip()
        if not code:
            continue
        require(code not in seen, f"FIN02 repeats account code {code!r}")
        initial = _number(row, columns["Initial balance"], f"FIN02 {code} initial")
        debit = _number(row, columns["Debit"], f"FIN02 {code} debit")
        credit = _number(row, columns["Credit"], f"FIN02 {code} credit")
        balance = _number(row, columns["Period balance"], f"FIN02 {code} balance")
        ending = _number(row, columns["Ending balance"], f"FIN02 {code} ending")
        require(balance == debit - credit, f"FIN02 {code}: period balance differs from debit minus credit")
        require(ending == initial + balance, f"FIN02 {code}: ending balance differs from opening plus period balance")
        seen[code] = (initial, debit, credit, ending)
    expected = {
        code: tuple(decimal(value, f"expected {code}") for value in values)
        for code, values in expected_by_code.items()
    }
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    require(not missing and not extra,
            f"FIN02 account coverage mismatch: missing={missing}, extra={extra}")
    for code, wanted in expected.items():
        require(seen[code] == wanted, f"FIN02 {code}: expected {wanted}, got {seen[code]}")
    return {"result": "PASS", "report_id": "FIN02", "rows": len(seen)}


def _gl_blocks(rows):
    headers = []
    for index, row in enumerate(rows):
        texts = {cell.value.strip() for cell in row.values() if cell.kind == "s"}
        if {"Debit", "Credit", "Cumul. Bal."} <= texts:
            headers.append(index)
    return headers


def _gl_label(row):
    for cell in row.values():
        if cell.kind == "s" and cell.value.strip() in ("Initial balance", "Ending balance"):
            return cell.value.strip()
    return ""


def _gl_title(rows, header, floor):
    """Return the account title written above ``header``, never the next block.

    OCA writes ``code + " - " + name`` on its own merged row and leaves two
    spacer rows before the array header, so the previous emitted row is not a
    reliable anchor. Search backwards but never cross the previous block.
    """
    for position in range(header - 1, floor - 1, -1):
        for cell in rows[position].values():
            if cell.kind == "s" and " - " in cell.value:
                return cell.value.strip()
    return ""


def verify_oca_general_ledger(workbook, expected_by_code, expected_line_count):
    """FIN01: per account initial/ending rows plus every detail AML must tie out."""
    rows = _single_sheet(read_workbook(workbook), "FIN01")
    headers = _gl_blocks(rows)
    require(bool(headers), "FIN01 header row not found")
    seen = {}
    detail_lines = 0
    for position, index in enumerate(headers):
        title_text = _gl_title(rows, index, headers[position - 1] + 1 if position else 0)
        require(" - " in title_text, f"FIN01 block {position + 1}: account title is missing")
        code = title_text.split(" - ", 1)[0].strip()
        require(code not in seen, f"FIN01 repeats account block {code!r}")
        stop = headers[position + 1] - 1 if position + 1 < len(headers) else len(rows)
        block = rows[index + 1:stop]
        initial_index = next((offset for offset, row in enumerate(block)
                              if _gl_label(row) == "Initial balance"), None)
        ending_index = next((offset for offset, row in enumerate(block)
                             if _gl_label(row) == "Ending balance"), None)
        require(initial_index is not None, f"FIN01 {code}: initial balance row is missing")
        require(ending_index is not None and ending_index > initial_index,
                f"FIN01 {code}: ending balance row is missing")
        initial = block[initial_index]
        ending = block[ending_index]
        columns = _header([rows[index]], {"Debit", "Credit", "Cumul. Bal."}, f"FIN01 {code}")[1]
        init_debit = _number(initial, columns["Debit"], f"FIN01 {code} initial debit")
        init_credit = _number(initial, columns["Credit"], f"FIN01 {code} initial credit")
        init_balance = _number(initial, columns["Cumul. Bal."], f"FIN01 {code} initial balance")
        require(init_debit - init_credit == init_balance,
                f"FIN01 {code}: initial row is not debit minus credit")
        end_debit = _number(ending, columns["Debit"], f"FIN01 {code} ending debit")
        end_credit = _number(ending, columns["Credit"], f"FIN01 {code} ending credit")
        end_balance = _number(ending, columns["Cumul. Bal."], f"FIN01 {code} ending balance")
        require(end_debit - end_credit == end_balance,
                f"FIN01 {code}: ending row is not debit minus credit")
        start = initial_index + 1
        finish = ending_index
        period_debit = period_credit = Decimal(0)
        for line in block[start:finish]:
            if not any(cell.kind == "s" and cell.value.strip() for cell in line.values()) \
                    and not any(cell.kind == "n" for cell in line.values()):
                continue
            period_debit += _number(line, columns["Debit"], f"FIN01 {code} detail debit")
            period_credit += _number(line, columns["Credit"], f"FIN01 {code} detail credit")
            detail_lines += 1
        seen[code] = {
            "initial": init_balance,
            "debit": period_debit,
            "credit": period_credit,
            "ending": end_balance,
            "cumulative_debit": end_debit - init_debit,
            "cumulative_credit": end_credit - init_credit,
        }
    expected = {}
    for code, values in expected_by_code.items():
        expected[code] = tuple(decimal(value, f"expected {code}") for value in values)
    nonzero = {code: values for code, values in expected.items() if any(values)}
    missing = sorted(set(nonzero) - set(seen))
    extra = sorted(set(seen) - set(expected))
    require(not missing and not extra,
            f"FIN01 account coverage mismatch: missing={missing}, extra={extra}")
    for code, (initial, debit, credit, ending) in expected.items():
        if code not in seen:
            continue
        got = seen[code]
        require(got["initial"] == initial,
                f"FIN01 {code} initial: expected {initial}, got {got['initial']}")
        require((got["debit"], got["credit"]) == (debit, credit),
                f"FIN01 {code} period: expected ({debit}, {credit}), got ({got['debit']}, {got['credit']})")
        require(got["ending"] == ending,
                f"FIN01 {code} ending: expected {ending}, got {got['ending']}")
        require((got["cumulative_debit"], got["cumulative_credit"]) == (debit, credit),
                f"FIN01 {code}: ending minus initial does not equal the period movement")
    require(detail_lines == expected_line_count,
            f"FIN01 detail lines: expected {expected_line_count}, got {detail_lines}")
    return {"result": "PASS", "report_id": "FIN01", "accounts": len(seen),
            "detail_lines": detail_lines}


def verify_oca_journal_ledger(workbook, expected_by_code):
    """FIN03: each journal sheet must total to the independent AML oracle."""
    sheets = read_workbook(workbook)
    seen = {}
    for name, rows in sheets.items():
        if name.startswith("Tax - "):
            continue
        code = name.split(" (", 1)[0].strip()
        require(bool(code), f"FIN03 sheet {name!r} has no journal code")
        require(code not in seen, f"FIN03 repeats journal sheet {code!r}")
        index, columns = _header(rows, {"Entry", "Date", "Account", "Debit", "Credit"},
                                 f"FIN03 {code}")
        debit = credit = Decimal(0)
        lines = 0
        for row in rows[index + 1:]:
            entry = _text(row, columns["Entry"]).strip()
            account = _text(row, columns["Account"]).strip()
            if not entry and not account:
                continue
            require(bool(entry), f"FIN03 {code}: detail row has no entry number")
            debit += _number(row, columns["Debit"], f"FIN03 {code} debit")
            credit += _number(row, columns["Credit"], f"FIN03 {code} credit")
            lines += 1
        seen[code] = (debit, credit, lines)
    expected = {
        code: (decimal(debit, f"expected {code} debit"),
               decimal(credit, f"expected {code} credit"), int(lines))
        for code, (debit, credit, lines) in expected_by_code.items()
    }
    missing = sorted(set(expected) - set(seen))
    require(not missing, f"FIN03 journal coverage mismatch: missing={missing}")
    for code, wanted in expected.items():
        require(seen[code] == wanted, f"FIN03 {code}: expected {wanted}, got {seen[code]}")
    for code in set(seen) - set(expected):
        require(seen[code][:2] == (Decimal(0), Decimal(0)) and seen[code][2] == 0,
                f"FIN03 unexpected active journal sheet {code!r}: {seen[code]}")
    return {"result": "PASS", "report_id": "FIN03", "journals": len(expected),
            "detail_lines": sum(value[2] for value in seen.values())}
