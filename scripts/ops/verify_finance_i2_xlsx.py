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

import json
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


def _assert_empty_id_list(rows, where):
    """Accept only the exporter's explicit empty placeholder or a header-only list."""
    populated = [cell for row in rows for cell in row.values() if cell.value.strip()]
    if (len(populated) == 1 and populated[0].kind == "s"
            and populated[0].value.strip() in ("No rows.", "Tidak ada baris.")):
        return
    try:
        index, columns = _header(rows, {"value"}, where)
    except ValueError as exc:
        raise ValueError(f"{where} contains an entry") from exc
    entries = [
        cell for row in rows[index + 1:] for cell in row.values()
        if cell.value.strip()
    ]
    require(not entries, f"{where} is not empty: {len(entries)} duplicate ids")


def verify_sales_purchase_register(workbook, expected_documents, expected_tie_out,
                                   expected_non_register_moves,
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
        _assert_empty_id_list(sheets[name], f"FIN57 {name}")
    require("gl_tie_out" in sheets, "FIN57 workbook has no gl_tie_out sheet")
    index, columns = _header(
        sheets["gl_tie_out"],
        {"account_id", "register_balance", "gl_balance", "non_register_gl_balance",
         "unexplained_difference"},
        "FIN57 gl_tie_out",
    )
    tie_rows = {}
    for row in sheets["gl_tie_out"][index + 1:]:
        account = row.get(columns["account_id"])
        if account is None or account.kind != "n":
            continue
        account_id = decimal(account.value, "FIN57 tie-out account id")
        require(account_id == account_id.to_integral_value() and account_id > 0,
                "FIN57 tie-out account id must be a positive integer")
        account_id = int(account_id)
        require(account_id not in tie_rows,
                f"FIN57 tie-out repeats account id {account_id}")
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
        tie_rows[account_id] = (register, gl_balance, non_register, difference)
    expected_ties = {
        int(account_id): tuple(decimal(value, f"expected tie-out account {account_id}")
                               for value in values)
        for account_id, values in expected_tie_out.items()
    }
    missing = sorted(set(expected_ties) - set(tie_rows))
    extra = sorted(set(tie_rows) - set(expected_ties))
    require(not missing and not extra,
            f"FIN57 tie-out account coverage mismatch: missing={missing}, extra={extra}")
    for account_id, wanted in expected_ties.items():
        require(tie_rows[account_id] == wanted,
                f"FIN57 tie-out account {account_id}: expected {wanted}, got {tie_rows[account_id]}")
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
            "tie_out_rows": len(tie_rows), "non_register_moves": len(move_ids),
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
    cover_sheets = 0
    for name, rows in sheets.items():
        if name.startswith("Tax - "):
            continue
        code = name.split(" (", 1)[0].strip()
        require(bool(code), f"FIN03 sheet {name!r} has no journal code")
        require(code not in seen, f"FIN03 repeats journal sheet {code!r}")
        try:
            index, columns = _header(
                rows, {"Entry", "Date", "Account", "Debit", "Credit"}, f"FIN03 {code}",
            )
        except ValueError:
            # AbstractReportXlsx creates its report sheet before the Journal
            # Ledger implementation adds one detail sheet per journal. That
            # first sheet contains only the report title and filters.
            require(name.startswith("Journal Ledger - "),
                    f"FIN03 sheet {name!r} has no detail header")
            cover_sheets += 1
            require(cover_sheets == 1, "FIN03 workbook repeats its cover sheet")
            continue
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
            "detail_lines": sum(value[2] for value in seen.values()),
            "cover_sheets": cover_sheets}


def _dict_cells(rows, where):
    """Return ``{key: Cell}`` for a custom-wizard ``key``/``value`` sheet."""
    index, columns = _header(rows, {"key", "value"}, where)
    values = {}
    for row in rows[index + 1:]:
        key = _text(row, columns["key"]).strip()
        if not key:
            continue
        require(key not in values, f"{where}: duplicate key {key!r}")
        cell = row.get(columns["value"])
        require(cell is not None, f"{where} {key}: value cell is missing")
        values[key] = cell
    return values


def _nested(row, columns, where):
    """Parse the exporter's JSON column that carries nested values."""
    column = columns.get("__nested")
    if not column:
        return {}
    cell = row.get(column)
    if cell is None or not cell.value.strip():
        return {}
    try:
        value = json.loads(cell.value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{where}: nested JSON is invalid") from exc
    require(isinstance(value, dict), f"{where}: nested JSON is not an object")
    return value


def _integer(cell, where, positive=False):
    require(cell is not None and cell.kind == "n", f"{where}: integer cell is missing")
    value = decimal(cell.value, where)
    require(value == value.to_integral_value(), f"{where}: {cell.value!r} is not an integer")
    number = int(value)
    if positive:
        require(number > 0, f"{where}: {number} is not positive")
    return number


def _value_cells(rows, where):
    index, columns = _header(rows, {"value"}, where)
    return [row[columns["value"]] for row in rows[index + 1:] if row.get(columns["value"])]


def _empty_list(rows, where):
    """True for the exporter's explicit placeholder, which has no header."""
    cells = [cell.value.strip() for row in rows for cell in row.values() if cell.value.strip()]
    return len(cells) == 1 and cells[0] in ("No rows.", "Tidak ada baris.")


def _decimal(value, where):
    return decimal(value, where)


def _decimal_cell(cell, where):
    """Require an exported numeric cell; a number stored as text must fail."""
    require(cell is not None and cell.kind == "n", f"{where}: numeric cell is missing")
    return decimal(cell.value, where)


def _json_number(value, where):
    """Require a JSON number so a stringified amount cannot sneak through."""
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{where}: {value!r} is not a number")
    return decimal(repr(value) if isinstance(value, float) else str(value), where)


def _json_integer(value, where, positive=False):
    """Require a JSON integer for ids so a float or string cannot slip through."""
    require(isinstance(value, int) and not isinstance(value, bool),
            f"{where}: {value!r} is not an integer")
    if positive:
        require(value > 0, f"{where}: {value} is not positive")
    return int(value)


def _row_has_data(row, columns):
    """True when any mapped column of the row still carries a value."""
    return any(_text(row, column).strip() for column in set(columns.values()))


PARTNER_LEDGER_FIELDS = ("opening_balance", "debit", "credit", "closing_balance")


def verify_partner_ledger(workbook, expected_rows, expected_totals, expected_by_type,
                          expected_gl, where="FIN05/FIN06"):
    """PIN FIN05/FIN06 exported partner rows, totals, type split and GL tie-out.

    ``expected_rows`` maps ``(partner_id, account_type)`` to the four amounts,
    ``expected_totals``/``expected_by_type`` carry the independent aggregates and
    ``expected_gl`` is ``(subledger_total, gl_control_total)``.
    """
    sheets = read_workbook(workbook)
    for name in ("rows", "totals", "by_account_type", "gl_tie_out"):
        require(name in sheets, f"{where} workbook has no {name} sheet")
    index, columns = _header(
        sheets["rows"],
        {"partner_id", "account_type", "movement_balance", *PARTNER_LEDGER_FIELDS},
        f"{where} rows",
    )
    seen = {}
    partners = set()
    for row in sheets["rows"][index + 1:]:
        account_type = _text(row, columns["account_type"]).strip()
        if not account_type:
            require(not _row_has_data(row, columns),
                    f"{where} rows: row without account_type carries data")
            continue
        partner_id = _integer(row.get(columns["partner_id"]), f"{where} partner id")
        key = (partner_id, account_type)
        require(key not in seen, f"{where} repeats partner {key}")
        values = tuple(
            _number(row, columns[field], f"{where} {key} {field}")
            for field in PARTNER_LEDGER_FIELDS
        )
        movement = _number(row, columns["movement_balance"], f"{where} {key} movement")
        require(movement == values[1] - values[2],
                f"{where} {key}: movement differs from debit minus credit")
        require(values[3] == values[0] + movement,
                f"{where} {key}: closing differs from opening plus movement")
        seen[key] = values
        partners.add(partner_id)
    expected = {
        (int(partner_id), account_type): tuple(
            _decimal(value, f"expected {partner_id}/{account_type}") for value in values
        )
        for (partner_id, account_type), values in expected_rows.items()
    }
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    require(not missing and not extra,
            f"{where} partner coverage mismatch: missing={missing}, extra={extra}")
    for key, wanted in expected.items():
        require(seen[key] == wanted, f"{where} {key}: expected {wanted}, got {seen[key]}")

    totals = _dict_cells(sheets["totals"], f"{where} totals")
    required = ("opening_balance", "debit", "credit", "movement_balance",
                "closing_balance", "partner_count")
    require(set(totals) == set(required),
            f"{where} totals keys mismatch: {sorted(totals)}")
    numbers = {key: _decimal_cell(totals[key], f"{where} total {key}")
               for key in ("opening_balance", "debit", "credit", "movement_balance",
                           "closing_balance")}
    require(totals["partner_count"].kind == "n",
            f"{where} partner_count is not numeric")
    partner_count = _integer(totals["partner_count"], f"{where} partner_count")
    require(numbers["movement_balance"] == numbers["debit"] - numbers["credit"],
            f"{where} totals: movement differs from debit minus credit")
    require(numbers["closing_balance"] == numbers["opening_balance"]
            + numbers["movement_balance"],
            f"{where} totals: closing differs from opening plus movement")
    wanted_totals = {
        key: _decimal(value, f"expected total {key}")
        for key, value in expected_totals.items()
    }
    require(set(wanted_totals) == set(PARTNER_LEDGER_FIELDS),
            f"{where} expected totals keys: {sorted(wanted_totals)}")
    for key, wanted in wanted_totals.items():
        require(numbers[key] == wanted,
                f"{where} total {key}: expected {wanted}, got {numbers[key]}")
    for key in PARTNER_LEDGER_FIELDS:
        require(numbers[key] == sum(row[PARTNER_LEDGER_FIELDS.index(key)]
                                    for row in seen.values()),
                f"{where} total {key}: differs from the exported partner rows")
    require(partner_count == len(partners) == len({key[0] for key in expected}),
            f"{where} partner_count: {partner_count} != {len(partners)}")

    populated = [
        cell.value.strip() for row in sheets["by_account_type"]
        for cell in row.values() if cell.value.strip()
    ]
    by_type_cells = {} if len(populated) == 1 else _dict_cells(
        sheets["by_account_type"], f"{where} by_account_type",
    )
    observed_types = {}
    for account_type, cell in by_type_cells.items():
        try:
            data = json.loads(cell.value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{where} account type {account_type!r}: nested JSON is invalid"
            ) from exc
        require(isinstance(data, dict),
                f"{where} account type {account_type!r}: value is not an object")
        require(set(data) == set(PARTNER_LEDGER_FIELDS),
                f"{where} account type {account_type!r} keys mismatch: {sorted(data)}")
        observed_types[account_type] = tuple(
            _json_number(data[field], f"{where} {account_type} {field}")
            for field in PARTNER_LEDGER_FIELDS
        )
    expected_types = {
        account_type: tuple(_decimal(value, f"expected type {account_type}")
                            for value in values)
        for account_type, values in expected_by_type.items()
    }
    require(set(observed_types) == set(expected_types),
            f"{where} account-type coverage mismatch: "
            f"{sorted(observed_types)} != {sorted(expected_types)}")
    for account_type, wanted in expected_types.items():
        require(observed_types[account_type] == wanted,
                f"{where} type {account_type}: expected {wanted}, "
                f"got {observed_types[account_type]}")
    for position, key in enumerate(PARTNER_LEDGER_FIELDS):
        require(numbers[key] == sum(row[position] for row in observed_types.values()),
                f"{where} total {key}: differs from the account-type split")

    gl = _dict_cells(sheets["gl_tie_out"], f"{where} gl_tie_out")
    for key in ("subledger_total", "gl_control_total", "difference"):
        require(key in gl, f"{where} gl_tie_out has no {key} key")
    subledger = _decimal_cell(gl["subledger_total"], f"{where} subledger total")
    control = _decimal_cell(gl["gl_control_total"], f"{where} GL control total")
    difference = _decimal_cell(gl["difference"], f"{where} tie-out difference")
    wanted_subledger, wanted_control = (
        _decimal(value, f"expected GL {value}") for value in expected_gl
    )
    require((subledger, control) == (wanted_subledger, wanted_control),
            f"{where} GL tie-out: expected {(wanted_subledger, wanted_control)}, "
            f"got {(subledger, control)}")
    require(subledger == numbers["closing_balance"],
            f"{where} GL subledger total differs from exported closing total")
    require(difference == subledger - control and difference == 0,
            f"{where} GL tie-out leaves a difference: {difference}")
    return {"result": "PASS", "rows": len(seen), "partners": partner_count}


OPEN_ITEM_FIELDS = ("move_id", "account_id", "partner_id", "account_type", "date",
                    "due_date", "balance", "matched_amount", "residual")
OPEN_ITEM_NUMERIC = {"move_id", "account_id", "partner_id", "balance", "matched_amount",
                     "residual"}


def verify_open_items(workbook, expected_lines, expected_partners,
                      expected_account_totals, expected_gl, where="FIN07"):
    """PIN FIN07 exported open items against dated partials from the AML oracle."""
    sheets = read_workbook(workbook)
    for name in ("rows", "partners", "account_totals", "gl_tie_out"):
        require(name in sheets, f"{where} workbook has no {name} sheet")
    if not expected_lines:
        require(not expected_partners and not expected_account_totals,
                f"{where} expected open items are inconsistent")
        for name in ("rows", "partners", "account_totals"):
            require(_empty_list(sheets[name], f"{where} {name}"),
                    f"{where} {name} is not empty")
        gl = _dict_cells(sheets["gl_tie_out"], f"{where} gl_tie_out")
        for key in ("subledger_total", "gl_control_total", "difference"):
            require(key in gl, f"{where} gl_tie_out has no {key} key")
        observed = tuple(
            _decimal_cell(gl[key], f"{where} {key}")
            for key in ("subledger_total", "gl_control_total", "difference")
        )
        wanted = tuple(_decimal(value, f"expected GL {value}") for value in expected_gl)
        require(observed == (*wanted, Decimal(0)),
                f"{where} empty GL tie-out: expected {(*wanted, Decimal(0))}, "
                f"got {observed}")
        return {"result": "PASS", "lines": 0, "partners": 0}
    index, columns = _header(sheets["rows"], {"line_id", *OPEN_ITEM_FIELDS},
                             f"{where} rows")
    seen = {}
    for row in sheets["rows"][index + 1:]:
        if not any(cell.value.strip() for cell in row.values()):
            continue
        line_id = _integer(row.get(columns["line_id"]), f"{where} line id", positive=True)
        require(line_id not in seen, f"{where} repeats line id {line_id}")
        values = []
        for field in OPEN_ITEM_FIELDS:
            if field in OPEN_ITEM_NUMERIC:
                if field in ("move_id", "account_id", "partner_id"):
                    number = _integer(
                        row.get(columns[field]), f"{where} line {line_id} {field}",
                        positive=field != "partner_id",
                    )
                    values.append(Decimal(number))
                else:
                    values.append(_number(row, columns[field],
                                          f"{where} line {line_id} {field}"))
            else:
                text = _text(row, columns[field]).strip()
                require(bool(text), f"{where} line {line_id} has no {field}")
                values.append(text)
        balance, matched, residual = values[-3:]
        require(residual == balance + matched,
                f"{where} line {line_id}: residual differs from balance plus matched amount")
        seen[line_id] = tuple(values)
    expected = {
        int(line_id): tuple(
            _decimal(value, f"expected line {line_id}")
            if field in OPEN_ITEM_NUMERIC else str(value)
            for field, value in zip(OPEN_ITEM_FIELDS, values)
        )
        for line_id, values in expected_lines.items()
    }
    missing = sorted(set(expected) - set(seen))
    extra = sorted(set(seen) - set(expected))
    require(not missing and not extra,
            f"{where} open-item coverage mismatch: missing={missing}, extra={extra}")
    for line_id, wanted in expected.items():
        require(seen[line_id] == wanted,
                f"{where} line {line_id}: expected {wanted}, got {seen[line_id]}")

    # partner_id is numeric even though it is not in the arithmetic triple.
    group_lines = {}
    for line_id, values in expected.items():
        key = (int(values[2]), values[3])
        group_lines.setdefault(key, set()).add(line_id)

    index, columns = _header(sheets["partners"],
                             {"partner_id", "account_type", "residual"},
                             f"{where} partners")
    observed_partners = {}
    for row in sheets["partners"][index + 1:]:
        account_type = _text(row, columns["account_type"]).strip()
        if not account_type:
            require(not _row_has_data(row, columns),
                    f"{where} partners: row without account_type carries data")
            continue
        partner_id = _integer(row.get(columns["partner_id"]), f"{where} partner id")
        key = (partner_id, account_type)
        require(key not in observed_partners, f"{where} repeats partner {key}")
        residual = _number(row, columns["residual"], f"{where} partner {key} residual")
        nested = _nested(row, columns, f"{where} partner {key}")
        line_ids = nested.get("line_ids")
        require(isinstance(line_ids, list) and line_ids,
                f"{where} partner {key} has no line ids")
        parsed = {int(item) for item in line_ids}
        require(len(parsed) == len(line_ids),
                f"{where} partner {key} repeats a line id")
        require(parsed == group_lines.get(key),
                f"{where} partner {key} line coverage mismatch: "
                f"{sorted(parsed)} != {sorted(group_lines.get(key, set()))}")
        observed_partners[key] = residual
    wanted_partners = {
        (int(partner_id), account_type): _decimal(value, f"expected partner {partner_id}")
        for (partner_id, account_type), value in expected_partners.items()
    }
    require(set(observed_partners) == set(wanted_partners),
            f"{where} partner coverage mismatch: "
            f"{sorted(observed_partners)} != {sorted(wanted_partners)}")
    for key, wanted in wanted_partners.items():
        require(observed_partners[key] == wanted,
                f"{where} partner {key}: expected {wanted}, "
                f"got {observed_partners[key]}")

    index, columns = _header(sheets["account_totals"], {"account_type", "residual"},
                             f"{where} account_totals")
    observed_totals = {}
    for row in sheets["account_totals"][index + 1:]:
        account_type = _text(row, columns["account_type"]).strip()
        if not account_type:
            require(not _row_has_data(row, columns),
                    f"{where} account_totals: row without account_type carries data")
            continue
        require(account_type not in observed_totals,
                f"{where} repeats account type {account_type!r}")
        observed_totals[account_type] = _number(
            row, columns["residual"], f"{where} {account_type} residual")
    wanted_totals = {
        account_type: _decimal(value, f"expected {account_type} total")
        for account_type, value in expected_account_totals.items()
    }
    require(set(observed_totals) == set(wanted_totals),
            f"{where} account-total coverage mismatch: "
            f"{sorted(observed_totals)} != {sorted(wanted_totals)}")
    for account_type, wanted in wanted_totals.items():
        require(observed_totals[account_type] == wanted,
                f"{where} total {account_type}: expected {wanted}, "
                f"got {observed_totals[account_type]}")

    row_total = sum(values[-1] for values in seen.values())
    partner_total = sum(observed_partners.values())
    account_total = sum(observed_totals.values())
    require(row_total == partner_total == account_total,
            f"{where} row, partner and account totals disagree")
    gl = _dict_cells(sheets["gl_tie_out"], f"{where} gl_tie_out")
    for key in ("subledger_total", "gl_control_total", "difference"):
        require(key in gl, f"{where} gl_tie_out has no {key} key")
    subledger = _decimal_cell(gl["subledger_total"], f"{where} subledger total")
    control = _decimal_cell(gl["gl_control_total"], f"{where} GL control total")
    difference = _decimal_cell(gl["difference"], f"{where} tie-out difference")
    wanted_subledger, wanted_control = (
        _decimal(value, f"expected GL {value}") for value in expected_gl
    )
    require((subledger, control) == (wanted_subledger, wanted_control),
            f"{where} GL tie-out: expected {(wanted_subledger, wanted_control)}, "
            f"got {(subledger, control)}")
    require(subledger == row_total,
            f"{where} GL subledger total differs from the exported rows")
    require(difference == subledger - control and difference == 0,
            f"{where} GL tie-out leaves a difference: {difference}")
    return {"result": "PASS", "lines": len(seen), "partners": len(observed_partners)}


def verify_aged_partner_balance(workbook, expected_buckets, expected_partners,
                                expected_account_totals, expected_rows, expected_gl,
                                expected_edges, where="FIN08/FIN09"):
    """PIN FIN08/FIN09 bucket split, partner buckets and detail rows to the oracle.

    ``expected_rows`` maps each ``line_id`` to
    ``(partner_id, account_type, due_date, bucket, residual)`` so a swap between
    partners fails even when every partner total and bucket stays unchanged.
    """
    sheets = read_workbook(workbook)
    for name in ("bucket_order", "edges", "buckets", "partners", "account_totals",
                 "rows", "gl_tie_out"):
        require(name in sheets, f"{where} workbook has no {name} sheet")
    names = [cell.value.strip() for cell in _value_cells(sheets["bucket_order"],
                                                         f"{where} bucket_order")]
    require(names == list(expected_buckets),
            f"{where} bucket order mismatch: {names} != {list(expected_buckets)}")
    edges = [
        _integer(cell, f"{where} bucket edge")
        for cell in _value_cells(sheets["edges"], f"{where} edges")
    ]
    require(edges == [int(edge) for edge in expected_edges],
            f"{where} bucket edges mismatch: {edges} != {list(expected_edges)}")

    buckets = _dict_cells(sheets["buckets"], f"{where} buckets")
    require(set(buckets) == set(names),
            f"{where} bucket keys mismatch: {sorted(buckets)}")
    observed_buckets = {name: _decimal_cell(buckets[name], f"{where} bucket {name}")
                        for name in names}
    wanted_buckets = {name: _decimal(value, f"expected bucket {name}")
                      for name, value in expected_buckets.items()}
    for name, wanted in wanted_buckets.items():
        require(observed_buckets[name] == wanted,
                f"{where} bucket {name}: expected {wanted}, "
                f"got {observed_buckets[name]}")

    expected = {
        int(line_id): (
            int(partner_id), account_type, str(due_date), bucket,
            _decimal(residual, f"expected line {line_id}"),
        )
        for line_id, (partner_id, account_type, due_date, bucket, residual)
        in expected_rows.items()
    }
    partner_lines = {}
    for line_id, values in expected.items():
        partner_lines.setdefault((values[0], values[1]), set()).add(line_id)

    index, columns = _header(sheets["partners"],
                             {"partner_id", "account_type", "residual"},
                             f"{where} partners")
    observed_partners = {}
    partner_lines_exported = {}
    for row in sheets["partners"][index + 1:]:
        account_type = _text(row, columns["account_type"]).strip()
        if not account_type:
            require(not _row_has_data(row, columns),
                    f"{where} partners: row without account_type carries data")
            continue
        partner_id = _integer(row.get(columns["partner_id"]), f"{where} partner id")
        key = (partner_id, account_type)
        require(key not in observed_partners, f"{where} repeats partner {key}")
        residual = _number(row, columns["residual"], f"{where} partner {key} residual")
        nested = _nested(row, columns, f"{where} partner {key}")
        partner_buckets = nested.get("buckets")
        require(isinstance(partner_buckets, dict),
                f"{where} partner {key} has no bucket split")
        require(set(partner_buckets) == set(names),
                f"{where} partner {key} bucket keys mismatch: "
                f"{sorted(partner_buckets)}")
        converted = {
            name: _json_number(partner_buckets[name], f"{where} partner {key} {name}")
            for name in names
        }
        require(residual == sum(converted.values()),
                f"{where} partner {key}: residual differs from its buckets")
        line_ids = nested.get("line_ids")
        require(isinstance(line_ids, list) and line_ids,
                f"{where} partner {key} has no line ids")
        exported = {
            _json_integer(item, f"{where} partner {key} line id", positive=True)
            for item in line_ids
        }
        require(len(exported) == len(line_ids),
                f"{where} partner {key} repeats a line id")
        require(exported == partner_lines.get(key, set()),
                f"{where} partner {key} line coverage mismatch: "
                f"{sorted(exported)} != {sorted(partner_lines.get(key, set()))}")
        observed_partners[key] = converted
        partner_lines_exported[key] = exported
    wanted_partners = {
        (int(partner_id), account_type): {
            name: _decimal(value, f"expected partner {partner_id} {name}")
            for name, value in partner_buckets.items()
        }
        for (partner_id, account_type), partner_buckets in expected_partners.items()
    }
    require(set(observed_partners) == set(wanted_partners),
            f"{where} partner coverage mismatch: "
            f"{sorted(observed_partners)} != {sorted(wanted_partners)}")
    for key, wanted in wanted_partners.items():
        require(set(wanted) == set(names),
                f"expected partner {key} bucket names: {sorted(wanted)}")
        for name, value in wanted.items():
            require(observed_partners[key][name] == value,
                    f"{where} partner {key} bucket {name}: expected {value}, "
                    f"got {observed_partners[key][name]}")
    for name, wanted in wanted_buckets.items():
        require(sum(partner[name] for partner in observed_partners.values()) == wanted,
                f"{where} partner buckets do not add up to bucket {name}")

    index, columns = _header(sheets["account_totals"], {"account_type", "residual"},
                             f"{where} account_totals")
    observed_totals = {}
    for row in sheets["account_totals"][index + 1:]:
        account_type = _text(row, columns["account_type"]).strip()
        if not account_type:
            require(not _row_has_data(row, columns),
                    f"{where} account_totals: row without account_type carries data")
            continue
        require(account_type not in observed_totals,
                f"{where} repeats account type {account_type!r}")
        observed_totals[account_type] = _number(
            row, columns["residual"], f"{where} {account_type} residual")
    wanted_totals = {
        account_type: _decimal(value, f"expected {account_type} total")
        for account_type, value in expected_account_totals.items()
    }
    require(set(observed_totals) == set(wanted_totals),
            f"{where} account-total coverage mismatch: "
            f"{sorted(observed_totals)} != {sorted(wanted_totals)}")
    for account_type, wanted in wanted_totals.items():
        require(observed_totals[account_type] == wanted,
                f"{where} total {account_type}: expected {wanted}, "
                f"got {observed_totals[account_type]}")

    index, columns = _header(sheets["rows"],
                             {"line_id", "partner_id", "account_type", "bucket",
                              "due_date", "residual"},
                             f"{where} rows")
    observed_rows = {}
    for row in sheets["rows"][index + 1:]:
        if not any(cell.value.strip() for cell in row.values()):
            continue
        line_id = _integer(row.get(columns["line_id"]), f"{where} line id", positive=True)
        require(line_id not in observed_rows, f"{where} repeats line id {line_id}")
        partner_id = _integer(row.get(columns["partner_id"]),
                              f"{where} line {line_id} partner id")
        account_type = _text(row, columns["account_type"]).strip()
        bucket = _text(row, columns["bucket"]).strip()
        due_date = _text(row, columns["due_date"]).strip()
        require(account_type and due_date, f"{where} line {line_id} lacks account/date")
        require(bucket in names, f"{where} line {line_id} has unknown bucket {bucket!r}")
        residual = _number(row, columns["residual"], f"{where} line {line_id} residual")
        observed_rows[line_id] = (partner_id, account_type, due_date, bucket, residual)
    require(set(observed_rows) == set(expected),
            f"{where} detail coverage mismatch: "
            f"{sorted(observed_rows)} != {sorted(expected)}")
    for line_id, wanted in expected.items():
        require(observed_rows[line_id] == wanted,
                f"{where} line {line_id}: expected {wanted}, "
                f"got {observed_rows[line_id]}")
    for key, buckets_exported in observed_partners.items():
        lines = partner_lines_exported[key]
        for name in names:
            require(
                sum(observed_rows[line][4] for line in lines
                    if observed_rows[line][3] == name) == buckets_exported[name],
                f"{where} partner {key} bucket {name}: detail rows do not match",
            )
    for name in names:
        require(sum(row[4] for row in observed_rows.values() if row[3] == name)
                == observed_buckets[name],
                f"{where} detail rows do not add up to bucket {name}")

    row_total = sum(row[4] for row in observed_rows.values())
    require(row_total == sum(observed_totals.values()) == sum(observed_buckets.values()),
            f"{where} row, account and bucket totals disagree")
    gl = _dict_cells(sheets["gl_tie_out"], f"{where} gl_tie_out")
    for key in ("subledger_total", "gl_control_total", "difference"):
        require(key in gl, f"{where} gl_tie_out has no {key} key")
    subledger = _decimal_cell(gl["subledger_total"], f"{where} subledger total")
    control = _decimal_cell(gl["gl_control_total"], f"{where} GL control total")
    difference = _decimal_cell(gl["difference"], f"{where} tie-out difference")
    wanted_subledger, wanted_control = (
        _decimal(value, f"expected GL {value}") for value in expected_gl
    )
    require((subledger, control) == (wanted_subledger, wanted_control),
            f"{where} GL tie-out: expected {(wanted_subledger, wanted_control)}, "
            f"got {(subledger, control)}")
    require(subledger == row_total,
            f"{where} GL subledger total differs from the exported rows")
    require(difference == subledger - control and difference == 0,
            f"{where} GL tie-out leaves a difference: {difference}")
    return {"result": "PASS", "lines": len(observed_rows),
            "partners": len(observed_partners)}
