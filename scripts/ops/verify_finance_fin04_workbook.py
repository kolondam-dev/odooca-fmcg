#!/usr/bin/env python3
"""Compare FIN04 XLSX rows with an independently exported, private AML CSV.

No network or Odoo dependency; never writes business data or prints row values.
The CSV must be exported independently of the FIN04 report, for the same company
and date interval, with columns aml_id,company_id,date,parent_state,journal_id,
account_id,display_type,debit,credit,balance. The operator must confirm the
source export includes *all* AMLs, including drafts and other companies when
testing exclusion, and for keeping both input files outside the repository.
"""

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
FIELDS = ("aml_id", "debit", "credit", "balance")
REQUIRED_CSV = {*FIELDS, "company_id", "date", "parent_state", "journal_id", "account_id",
                "display_type"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Non-numeric amount or identifier") from exc
    need(result.is_finite(), "Non-finite amount")
    return result


def identifier(value):
    result = number(value)
    need(result > 0 and result == result.to_integral_value(), "Invalid AML identifier")
    return str(int(result))


def source_rows(path, company, start, end, journal, account, posted):
    selected = {}
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        need(REQUIRED_CSV <= set(reader.fieldnames or []), "Missing required AML CSV columns")
        for item in reader:
            if (item["company_id"] != company or not start <= item["date"] <= end
                    or (posted and item["parent_state"] != "posted")
                    or item["display_type"] in ("line_note", "line_section", "line_subsection")
                    or (journal and item["journal_id"] != journal)
                    or (account and item["account_id"] != account)):
                continue
            need(item["parent_state"] in ("posted", "draft"), "Unexpected source state")
            key = identifier(item["aml_id"])
            need(key not in selected, "Duplicate source AML id")
            selected[key] = tuple(number(item[field]) for field in FIELDS[1:])
            need(selected[key][0] - selected[key][1] == selected[key][2],
                 "Source AML debit minus credit differs from balance")
    return selected


def cells_in_sheet(archive, part, strings):
    root = ET.fromstring(archive.read(part))
    need(not root.findall(".//x:f", NS), "Workbook contains formula cells")
    table = []
    cell_types = []
    for row in root.findall(".//x:sheetData/x:row", NS):
        cells = {}
        types = {}
        for cell in row.findall("x:c", NS):
            col = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
            need(col is not None, "Cell has no column reference")
            value = cell.find("x:v", NS)
            inline = cell.find("x:is", NS)
            raw = value.text if value is not None else ""
            if cell.get("t") == "s":
                raw = strings[int(raw)]
            elif inline is not None:
                raw = "".join(inline.itertext())
            need(col.group() not in cells, "Duplicate workbook column")
            cells[col.group()] = raw
            types[col.group()] = cell.get("t")
        table.append(cells)
        cell_types.append(types)
    return table, cell_types


def workbook_rows(path):
    with ZipFile(path) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation = {node.get("Id"): node.get("Target") for node in rels.findall(f"{{{REL}}}Relationship")}
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.itertext()) for node in root.findall("x:si", NS)]
        sheets = {}
        for node in book.findall("x:sheets/x:sheet", NS):
            name = node.get("name")
            target = relation[node.get(f"{{{NS['r']}}}id")]
            part = target.lstrip("/") if target.startswith("/") else "xl/" + target
            need(part in archive.namelist(), "Missing workbook sheet")
            need(name not in sheets, "Duplicate workbook sheet")
            sheets[name] = cells_in_sheet(archive, part, strings)
        need("Summary" in sheets and "rows" in sheets, "FIN04 Summary/rows sheet missing")
        summary = sheets["Summary"][0]
        need(any("FIN04" in str(row.get("B", "")) for row in summary), "FIN04 marker missing")
        table, typed = sheets["rows"]
        need(bool(table), "Missing rows header")
        headers = table[0]
        by_name = {name: column for column, name in headers.items()}
        need(set(FIELDS) <= set(by_name), "FIN04 required columns missing")
        rows = {}
        for item, types in zip(table[1:], typed[1:]):
            need(all(types.get(by_name[field]) in (None, "n") for field in FIELDS),
                 "FIN04 numeric column was stored as text")
            key = identifier(item.get(by_name["aml_id"], ""))
            need(key not in rows, "Duplicate XLSX AML id")
            rows[key] = tuple(number(item.get(by_name[field], "")) for field in FIELDS[1:])
        return rows


def verify(source, workbook, company, start, end, journal=None, account=None, posted=True):
    expected = source_rows(source, company, start, end, journal, account, posted)
    actual = workbook_rows(workbook)
    need(set(expected) == set(actual),
         f"AML coverage mismatch: source={len(expected)}, workbook={len(actual)}, "
         f"missing={len(set(expected)-set(actual))}, extra={len(set(actual)-set(expected))}")
    need(all(expected[key] == actual[key] for key in expected), "FIN04 AML amount mismatch")
    return {"result": "PASS", "report_id": "FIN04", "rows": len(expected),
            "debit": str(sum((v[0] for v in expected.values()), Decimal(0))),
            "credit": str(sum((v[1] for v in expected.values()), Decimal(0))),
            "balance": str(sum((v[2] for v in expected.values()), Decimal(0)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--company", required=True, help="Odoo company ID")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--journal", help="Optional journal ID")
    parser.add_argument("--account", help="Optional account ID")
    parser.add_argument("--include-draft", action="store_true")
    args = parser.parse_args()
    try:
        need(re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.from_date) is not None
             and re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.to_date) is not None
             and args.from_date <= args.to_date, "Invalid period")
        result = verify(args.source, args.workbook, args.company, args.from_date,
                        args.to_date, args.journal, args.account, not args.include_draft)
    except (ValueError, KeyError, OSError) as exc:
        print(f"FIN04_WORKBOOK=FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("FIN04_WORKBOOK=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
