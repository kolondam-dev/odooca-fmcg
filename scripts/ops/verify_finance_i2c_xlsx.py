#!/usr/bin/env python3
"""Offline XLSX comparators for FIN37 accrual schedules and FIN38 FX.

The expected values are supplied by the independent AML/partial-reconcile
oracle in ``verify_finance_i2c_schedules.py``.  This module only reads the
workbook produced by the real finance wizard; it never imports Odoo.
"""

import json
from decimal import Decimal

import verify_finance_i2_xlsx as xlsx


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _header(rows, required, where):
    return xlsx._header(rows, set(required), where)  # noqa: SLF001


def _text(row, column):
    return xlsx._text(row, column).strip()  # noqa: SLF001


def _integer(row, column, where, positive=True):
    return xlsx._integer(row.get(column), where, positive=positive)  # noqa: SLF001


def _number(row, column, where):
    return xlsx._number(row, column, where)  # noqa: SLF001


def _json(row, columns, where):
    value = xlsx._nested(row, columns, where)  # noqa: SLF001
    require(isinstance(value, dict), f"{where}: nested payload is not an object")
    return value


def _numeric_json(value, where):
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{where}: value is not numeric")
    return xlsx.decimal(value, where)


def _list_values(rows, where):
    if xlsx._empty_list(rows, where):  # noqa: SLF001
        return []
    index, columns = _header(rows, {"value"}, where)
    values = []
    for row in rows[index + 1:]:
        cell = row.get(columns["value"])
        if cell is None or not cell.value.strip():
            continue
        require(cell.kind == "n", f"{where}: list value must be numeric")
        value = xlsx.decimal(cell.value, where)
        require(value == value.to_integral_value(), f"{where}: list value is not an integer")
        values.append(int(value))
    return values


def _dict_numbers(rows, where):
    cells = xlsx._dict_cells(rows, where)  # noqa: SLF001
    values = {}
    for key, cell in cells.items():
        require(cell.kind == "n", f"{where} {key}: numeric cell is missing")
        values[key] = xlsx.decimal(cell.value, f"{where} {key}")
    return values


def verify_accrual_schedule(workbook, expected_rows, expected_exceptions,
                            expected_totals, where="FIN37"):
    """Tie exported schedules/exceptions to independent posted AML values."""
    sheets = xlsx.read_workbook(workbook)
    for name in ("rows", "exceptions"):
        require(name in sheets, f"{where} workbook has no {name} sheet")

    required = {"line_id", "move_id", "account_id", "partner_id", "balance",
                "start_date", "end_date", "total_days", "recognized_to_date",
                "remaining", "__nested"}
    if expected_rows:
        index, columns = _header(sheets["rows"], required, f"{where} rows")
        observed = {}
        for row in sheets["rows"][index + 1:]:
            if not any(cell.value.strip() for cell in row.values()):
                continue
            line_id = _integer(row, columns["line_id"], f"{where} line id")
            require(line_id not in observed, f"{where} repeats line {line_id}")
            values = {
                "move_id": _integer(row, columns["move_id"], f"{where} move id"),
                "account_id": _integer(row, columns["account_id"], f"{where} account id"),
                "partner_id": _integer(row, columns["partner_id"], f"{where} partner id",
                                       positive=False),
                "balance": _number(row, columns["balance"], f"{where} balance"),
                "start_date": _text(row, columns["start_date"]),
                "end_date": _text(row, columns["end_date"]),
                "total_days": _integer(row, columns["total_days"], f"{where} total days"),
                "recognized": _number(row, columns["recognized_to_date"],
                                      f"{where} recognized"),
                "remaining": _number(row, columns["remaining"], f"{where} remaining"),
            }
            nested = _json(row, columns, f"{where} line {line_id}")
            periods = nested.get("periods")
            require(isinstance(periods, list) and periods,
                    f"{where} line {line_id}: periods are missing")
            allocated = recognized = Decimal(0)
            for position, period in enumerate(periods, start=1):
                require(isinstance(period, dict),
                        f"{where} line {line_id} period {position}: not an object")
                amount = _numeric_json(period.get("amount"),
                                       f"{where} line {line_id} period amount")
                recognized_amount = _numeric_json(
                    period.get("recognized_amount"),
                    f"{where} line {line_id} period recognized",
                )
                allocated += amount
                recognized += recognized_amount
            require(allocated == values["balance"],
                    f"{where} line {line_id}: periods do not equal balance")
            require(recognized == values["recognized"],
                    f"{where} line {line_id}: periods do not equal recognized total")
            require(values["balance"] == values["recognized"] + values["remaining"],
                    f"{where} line {line_id}: recognized plus remaining differs")
            observed[line_id] = values
    else:
        require(xlsx._empty_list(sheets["rows"], f"{where} rows"),  # noqa: SLF001
                f"{where} rows must be empty")
        observed = {}

    wanted = {
        int(line_id): {
            key: (xlsx.decimal(value, f"expected {line_id} {key}")
                  if key in {"balance", "recognized", "remaining"} else value)
            for key, value in values.items()
        }
        for line_id, values in expected_rows.items()
    }
    require(observed == wanted, f"{where} schedule rows mismatch")

    if expected_exceptions:
        index, columns = _header(
            sheets["exceptions"],
            {"line_id", "move_id", "account_id", "partner_id", "balance", "reason"},
            f"{where} exceptions",
        )
        exceptions = {}
        for row in sheets["exceptions"][index + 1:]:
            if not any(cell.value.strip() for cell in row.values()):
                continue
            line_id = _integer(row, columns["line_id"], f"{where} exception line")
            require(line_id not in exceptions, f"{where} repeats exception {line_id}")
            exceptions[line_id] = {
                "move_id": _integer(row, columns["move_id"], f"{where} exception move"),
                "account_id": _integer(row, columns["account_id"],
                                       f"{where} exception account"),
                "partner_id": _integer(row, columns["partner_id"],
                                       f"{where} exception partner", positive=False),
                "balance": _number(row, columns["balance"], f"{where} exception balance"),
                "reason": _text(row, columns["reason"]),
            }
    else:
        require(xlsx._empty_list(sheets["exceptions"], f"{where} exceptions"),  # noqa: SLF001
                f"{where} exceptions must be empty")
        exceptions = {}
    wanted_exceptions = {
        int(line_id): {
            **values,
            "balance": xlsx.decimal(values["balance"], f"expected exception {line_id}"),
        }
        for line_id, values in expected_exceptions.items()
    }
    require(exceptions == wanted_exceptions, f"{where} exceptions mismatch")

    totals = {
        "control_total": sum(row["balance"] for row in observed.values())
                         + sum(row["balance"] for row in exceptions.values()),
        "recognized_total": sum(row["recognized"] for row in observed.values()),
        "remaining_total": sum(row["remaining"] for row in observed.values()),
        "exception_total": sum(row["balance"] for row in exceptions.values()),
    }
    wanted_totals = {key: xlsx.decimal(value, f"expected {key}")
                     for key, value in expected_totals.items()}
    require(totals == wanted_totals, f"{where} derived totals mismatch: {totals}")
    require(totals["control_total"] == totals["recognized_total"]
            + totals["remaining_total"] + totals["exception_total"],
            f"{where} workbook does not tie")
    return {"result": "PASS", "rows": len(observed), "exceptions": len(exceptions)}


def verify_fx_revaluation(workbook, expected_unrealized, expected_realized,
                          expected_unposted, expected_by_currency,
                          expected_exchange_moves, expected_gl, where="FIN38"):
    """Tie FIN38 line coverage, realized evidence and per-currency GL rows."""
    sheets = xlsx.read_workbook(workbook)
    needed = ("unrealized_rows", "realized_rows", "realized_unposted_rows",
              "realized_by_currency", "tied_exchange_move_ids", "gl_tie_out")
    for name in needed:
        require(name in sheets, f"{where} workbook has no {name} sheet")

    def line_amounts(name, id_field, amount_fields, expected):
        if not expected:
            require(xlsx._empty_list(sheets[name], f"{where} {name}"),  # noqa: SLF001
                    f"{where} {name} must be empty")
            return {}
        index, columns = _header(sheets[name], {id_field, *amount_fields},
                                 f"{where} {name}")
        observed = {}
        for row in sheets[name][index + 1:]:
            if not any(cell.value.strip() for cell in row.values()):
                continue
            row_id = _integer(row, columns[id_field], f"{where} {name} id")
            require(row_id not in observed, f"{where} {name} repeats {row_id}")
            observed[row_id] = tuple(
                _number(row, columns[field], f"{where} {name} {row_id} {field}")
                for field in amount_fields
            )
        wanted = {int(row_id): tuple(xlsx.decimal(value, f"expected {name} {row_id}")
                                     for value in values)
                  for row_id, values in expected.items()}
        require(set(observed) == set(wanted),
                f"{where} {name} coverage mismatch: "
                f"{sorted(observed)} != {sorted(wanted)}")
        for row_id, wanted_values in wanted.items():
            got_values = observed[row_id]
            for field, got, wanted_value in zip(amount_fields, got_values, wanted_values):
                if field == "rate_as_of":
                    # XLSX stores IEEE floats at Excel's effective precision.
                    # Odoo may return 15999.999999999998 while xlsxwriter emits
                    # 16000; compare the rate at 1e-12 relative precision, never
                    # relax currency amounts or differences.
                    tolerance = max(Decimal(1), abs(wanted_value)) * Decimal("1e-12")
                    require(abs(got - wanted_value) <= tolerance,
                            f"{where} {name} {row_id} {field}: "
                            f"{got} != {wanted_value}")
                else:
                    require(got == wanted_value,
                            f"{where} {name} {row_id} {field}: "
                            f"{got} != {wanted_value}")
        return observed

    unrealized = line_amounts(
        "unrealized_rows", "line_id",
        ("amount_residual_currency", "amount_residual", "rate_as_of",
         "revalued_balance", "unrealized_difference"), expected_unrealized,
    )
    realized = line_amounts("realized_rows", "partial_id", ("realized_amount",),
                            expected_realized)
    unposted = line_amounts("realized_unposted_rows", "partial_id", ("realized_amount",),
                            expected_unposted)
    by_currency_rows = line_amounts(
        "realized_by_currency", "currency_id", ("realized_amount",),
        expected_by_currency,
    )
    moves = _list_values(sheets["tied_exchange_move_ids"],
                         f"{where} tied_exchange_move_ids")
    require(moves == sorted(int(value) for value in expected_exchange_moves),
            f"{where} exchange move coverage mismatch")

    gl = xlsx._dict_cells(sheets["gl_tie_out"], f"{where} gl_tie_out")  # noqa: SLF001
    rows_cell = gl.get("rows")
    require(rows_cell is not None and rows_cell.kind == "s",
            f"{where} GL rows are missing")
    try:
        gl_rows = json.loads(rows_cell.value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{where} GL rows JSON is invalid") from exc
    require(isinstance(gl_rows, list), f"{where} GL rows are not a list")
    observed_gl = {}
    for row in gl_rows:
        require(isinstance(row, dict), f"{where} GL row is not an object")
        currency_id = row.get("currency_id")
        require(isinstance(currency_id, int) and not isinstance(currency_id, bool),
                f"{where} GL currency id is invalid")
        require(currency_id not in observed_gl, f"{where} repeats GL currency {currency_id}")
        observed_gl[currency_id] = (
            _numeric_json(row.get("realized_amount"), f"{where} GL realized"),
            _numeric_json(row.get("gl_balance"), f"{where} GL total"),
            _numeric_json(row.get("difference"), f"{where} GL difference"),
        )
    wanted_gl = {
        int(currency_id): tuple(xlsx.decimal(value, f"expected GL {currency_id}")
                                for value in values)
        for currency_id, values in expected_gl.items()
    }
    require(observed_gl == wanted_gl, f"{where} per-currency GL mismatch")
    require(all(realized_total == gl_total and difference == 0
                for realized_total, gl_total, difference in observed_gl.values()),
            f"{where} GL tie-out is not balanced")
    require(sum(value[0] for value in realized.values())
            == sum(value[0] for value in by_currency_rows.values()),
            f"{where} realized rows differ from currency totals")
    return {"result": "PASS", "unrealized_rows": len(unrealized),
            "realized_rows": len(realized), "unposted_rows": len(unposted)}
