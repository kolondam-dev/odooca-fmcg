# Part of odooca-fmcg. License LGPL-3.
"""Single screen entry point for the custom I2 finance reports.

The report models themselves are ``AbstractModel`` services without any
persisted record, so they cannot be opened from a menu. This transient wizard
collects the bounded filters, dispatches to the matching ``_snapshot`` service
and renders the returned payload in a read-only preview.

Nothing is posted, created or mutated: every report is a read-only projection
of posted journal items and partial reconciliations.
"""

import base64
import json
import math
import re
from html import escape
from io import BytesIO

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

REPORT_TYPES = [
    ("audit_trail", _("FIN04 - Journal Items Audit Trail")),
    ("partner_ledger", _("FIN05/FIN06 - Partner Ledger AR/AP")),
    ("open_items", _("FIN07 - Open Items AR/AP")),
    ("aged_partner_balance", _("FIN08/FIN09 - Aged Partner Balance")),
    ("combined_trial_balance", _("FIN51 - Combined Trial Balance")),
    ("sales_purchase_register", _("FIN57 - Sales and Purchase Register")),
    ("accrual_schedule", _("FIN37 - Accrual / Prepayment Schedules")),
    ("fx_revaluation", _("FIN38 - FX Revaluation")),
]

RANGE_REPORTS = {
    "audit_trail",
    "partner_ledger",
    "combined_trial_balance",
    "sales_purchase_register",
}
AS_OF_REPORTS = {
    "open_items",
    "aged_partner_balance",
    "accrual_schedule",
    "fx_revaluation",
}
PARTNER_TYPE_REPORTS = {"partner_ledger", "open_items", "aged_partner_balance"}

MAX_TABLE_ROWS = 300
MAX_TABLE_COLUMNS = 24
MAX_CELL_CHARS = 200
MAX_JSON_CHARS = 200000

# XLSX export limits are deliberately separate from the preview limits: the
# preview bounds what a browser must render, the export bounds what a workbook
# may contain. Nothing is truncated silently; a section above the row limit
# raises instead of writing a partial workbook.
MAX_XLSX_ROWS = 20000
MAX_XLSX_COLUMNS = 40
MAX_XLSX_CELL_CHARS = 32000
# Bookkeeping column that carries everything a row holds beyond the scalar
# columns: nested lists/objects and scalar columns past the column limit. It is
# added on top of MAX_XLSX_COLUMNS, never counted as one of them.
NESTED_COLUMN = "__nested"
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHEET_NAME_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")

META_KEYS = {
    "report_id",
    "report_ids",
    "company_id",
    "currency_id",
    "date_from",
    "date_to",
    "as_of_date",
    "partner_type",
    "only_posted_moves",
}


def _default_month_start(self):
    return fields.Date.context_today(self).replace(day=1)


def _format_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return _("Yes") if value else _("No")
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    text = str(value)
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS] + "..."
    return escape(text)


def _is_scalar(value):
    return value is None or isinstance(value, (str, int, float, bool))


def _xlsx_text_parts(value):
    """Render one cell as inert text and report whether the cell had to be cut.

    Cells are written with ``write_string`` so a spreadsheet stores them as
    strings, and a leading formula trigger is quoted as well. Both layers are
    needed: the string type stops Excel from evaluating the cell, and the
    quote stops a later CSV/TSV re-export (or an importer that re-parses the
    text) from promoting report data into a formula.
    """
    text = "" if value is None else str(value)
    text = INVALID_XML_CHARS.sub("", text)
    truncated = len(text) > MAX_XLSX_CELL_CHARS
    if truncated:
        text = text[:MAX_XLSX_CELL_CHARS] + " ... (truncated)"
    if text[:1] in FORMULA_TRIGGERS:
        text = "'" + text
    return text, truncated


def _xlsx_text(value):
    """Inert text for an XLSX cell, without the truncation flag."""
    return _xlsx_text_parts(value)[0]


class FinanceReportWizard(models.TransientModel):
    _name = "id.finance.report.wizard"
    _description = "Finance Report Runner"

    report_type = fields.Selection(REPORT_TYPES, required=True, default="audit_trail")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        domain="[('id', 'in', allowed_company_ids)]",
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Companies",
        default=lambda self: self.env.companies,
        domain="[('id', 'in', allowed_company_ids)]",
    )
    date_from = fields.Date(default=_default_month_start)
    date_to = fields.Date(default=fields.Date.context_today)
    as_of_date = fields.Date(default=fields.Date.context_today)

    partner_type = fields.Selection(
        [
            ("customer", _("Customers")),
            ("supplier", _("Suppliers")),
            ("all", _("Customers and Suppliers")),
        ],
        default="customer",
    )
    partner_ids = fields.Many2many("res.partner", string="Partners")
    journal_ids = fields.Many2many("account.journal", string="Journals")
    account_ids = fields.Many2many("account.account", string="Accounts")

    only_posted_moves = fields.Boolean(default=True)
    register_type = fields.Selection(
        [
            ("all", _("All documents")),
            ("sale", _("Sales only")),
            ("purchase", _("Purchases only")),
        ],
        default="all",
    )

    presentation_currency_id = fields.Many2one("res.currency", string="Presentation currency")
    rate_date = fields.Date(string="Conversion date")
    hide_account_at_0 = fields.Boolean(string="Hide zero balances")
    account_map_json = fields.Text(
        string="COA mapping (JSON)",
        help="Optional JSON object keyed by account code or by '<company_id>|<code>'. "
        "Each value is either [code, name, account_type] or "
        '{"code": ..., "name": ..., "account_type": ...}.',
    )

    result_summary = fields.Char(readonly=True)
    # Stored markup is sanitized server-side: ``readonly`` only locks the UI, and
    # the Accounting Readonly group has create/write on this transient model.
    # Keeping ``sanitize=True`` means a direct ORM write cannot persist active
    # markup, while the whitelisted report tags (div/table/thead/tbody/tr/th/td/
    # p/pre) still render.
    result_html = fields.Html(readonly=True, sanitize=True)
    result_json = fields.Text(readonly=True)
    # Binary attachments are served back through /web/content; the download is
    # built from the same snapshot as the preview, never from stored rows.
    result_xlsx = fields.Binary(readonly=True, attachment=True, string="XLSX export")
    result_filename = fields.Char(readonly=True)
    generated_at = fields.Datetime(readonly=True)

    # ------------------------------------------------------------------ actions
    def action_run(self):
        self.ensure_one()
        snapshot = self._dispatch()
        self.write({
            "result_summary": self._summary(snapshot),
            "result_html": self._render(snapshot),
            "result_json": self._payload_json(snapshot),
            "generated_at": fields.Datetime.now(),
            # A re-run must not leave the previous workbook downloadable.
            "result_xlsx": False,
            "result_filename": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_export_xlsx(self):
        """Build the workbook from a fresh snapshot and start the download.

        The export repeats the same server-side dispatch as the preview, so the
        role/company checks and the report scope are enforced here as well.
        """
        self.ensure_one()
        snapshot = self._dispatch()
        filename = self._xlsx_filename(snapshot)
        payload = self._xlsx_payload(snapshot, filename)
        self.write({
            "result_summary": self._summary(snapshot),
            "result_html": self._render(snapshot),
            "result_json": self._payload_json(snapshot),
            "result_filename": filename,
            "result_xlsx": base64.b64encode(payload),
            "generated_at": fields.Datetime.now(),
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self._name}/{self.id}/result_xlsx/{filename}?download=true",
            "target": "self",
        }

    # ---------------------------------------------------------------- dispatch
    def _dispatch(self):
        report = self.report_type
        company = self.company_id
        if company not in self.env.companies:
            raise UserError(_("Select a company available in the current context."))

        partner_ids = self.partner_ids.ids or None
        journal_ids = self.journal_ids.ids or None
        account_ids = self.account_ids.ids or None
        posted = self.only_posted_moves

        if report in RANGE_REPORTS:
            date_from, date_to = self._required_range()

        if report in AS_OF_REPORTS:
            as_of = self._required_as_of()

        if report == "audit_trail":
            return self.env["id.finance.audit.trail"]._snapshot(
                company_id=company.id,
                date_from=date_from,
                date_to=date_to,
                only_posted_moves=posted,
                journal_ids=journal_ids,
                account_ids=account_ids,
            )

        if report == "partner_ledger":
            return self.env["id.finance.partner.ledger"]._snapshot(
                company_id=company.id,
                date_from=date_from,
                date_to=date_to,
                partner_type=self.partner_type or "customer",
                only_posted_moves=posted,
                partner_ids=partner_ids,
                journal_ids=journal_ids,
            )

        if report == "open_items":
            return self.env["id.finance.open.items"]._snapshot(
                company_id=company.id,
                as_of_date=as_of,
                partner_type=self.partner_type or "customer",
                only_posted_moves=posted,
                partner_ids=partner_ids,
                journal_ids=journal_ids,
            )

        if report == "aged_partner_balance":
            return self.env["id.finance.aged.partner.balance"]._snapshot(
                company_id=company.id,
                as_of_date=as_of,
                partner_type=self.partner_type or "customer",
                only_posted_moves=posted,
                partner_ids=partner_ids,
                journal_ids=journal_ids,
            )

        if report == "combined_trial_balance":
            companies = self.company_ids or company
            if any(c not in self.env.companies for c in companies):
                raise UserError(_("Select only companies available in the current context."))
            return self.env["id.finance.combined.trial.balance"]._snapshot(
                company_ids=companies.ids,
                date_from=date_from,
                date_to=date_to,
                presentation_currency_id=self.presentation_currency_id.id or None,
                rate_date=self.rate_date,
                only_posted_moves=posted,
                hide_account_at_0=self.hide_account_at_0,
                account_map=self._account_map(),
            )

        if report == "sales_purchase_register":
            return self.env["id.finance.sales.purchase.register"]._snapshot(
                company_id=company.id,
                date_from=date_from,
                date_to=date_to,
                register_type=self.register_type or "all",
                only_posted_moves=posted,
                journal_ids=journal_ids,
            )

        if report == "accrual_schedule":
            return self.env["id.finance.accrual.schedule"]._snapshot(
                company_id=company.id,
                as_of_date=as_of,
                account_ids=account_ids,
                journal_ids=journal_ids,
                partner_ids=partner_ids,
                only_posted_moves=posted,
            )

        if report == "fx_revaluation":
            return self.env["id.finance.fx.revaluation"]._snapshot(
                company_id=company.id,
                as_of_date=as_of,
                account_ids=account_ids,
                journal_ids=journal_ids,
                partner_ids=partner_ids,
                only_posted_moves=posted,
            )

        raise UserError(_("Unknown report type."))

    def _required_range(self):
        if not self.date_from or not self.date_to:
            raise UserError(_("Select both the start and end date of the report period."))
        return self.date_from, self.date_to

    def _required_as_of(self):
        if not self.as_of_date:
            raise UserError(_("Select a single as-of date for this report."))
        return self.as_of_date

    def _account_map(self):
        raw = (self.account_map_json or "").strip()
        if not raw:
            return None
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UserError(_("The COA mapping must be a valid JSON object.")) from exc
        if not isinstance(loaded, dict):
            raise UserError(_("The COA mapping must be a valid JSON object."))
        mapping = {}
        for key, value in loaded.items():
            key = str(key).strip()
            if not key:
                raise UserError(_("The COA mapping contains an empty account key."))
            if "|" in key:
                company_part, code = key.split("|", 1)
                try:
                    company_ref = int(company_part)
                except ValueError as exc:
                    raise UserError(
                        _("The COA mapping key '%(key)s' must start with a numeric company id.", key=key)
                    ) from exc
                mapping[(company_ref, code.strip())] = value
            else:
                mapping[key] = value
        return mapping

    # ---------------------------------------------------------------- payload
    @api.model
    def _label(self, report_type):
        return dict(REPORT_TYPES).get(report_type, report_type)

    def _summary(self, snapshot):
        parts = [str(snapshot.get("report_id") or ""), self._label(self.report_type)]
        lists = [key for key in snapshot if isinstance(snapshot[key], list)]
        if lists:
            parts.append(", ".join(f"{key}: {len(snapshot[key])}" for key in lists))
        return " | ".join(part for part in parts if part)

    def _payload_json(self, snapshot):
        try:
            payload = json.dumps(snapshot, default=str, indent=1)
        except (TypeError, ValueError):
            return json.dumps({"error": "payload is not JSON serialisable"}, default=str)
        if len(payload) <= MAX_JSON_CHARS:
            return payload
        # A raw cut would produce invalid JSON and drop everything after the cut
        # without a trace. Keep the payload valid and make the omission explicit:
        # include whole sections while they fit, then name what was left out.
        meta = {key: value for key, value in snapshot.items() if key in META_KEYS}
        keys = [key for key in snapshot if key not in META_KEYS]
        included = []
        for key in keys:
            trial = included + [key]
            omitted = [other for other in keys if other not in trial]
            if len(self._json_with_disclosure(meta, snapshot, trial, omitted)) <= MAX_JSON_CHARS:
                included = trial
        omitted = [key for key in keys if key not in included]
        return self._json_with_disclosure(meta, snapshot, included, omitted)

    def _json_with_disclosure(self, meta, snapshot, included, omitted):
        payload = dict(meta)
        for key in included:
            payload[key] = snapshot[key]
        payload["__truncation__"] = {
            "applied": True,
            "limit_chars": MAX_JSON_CHARS,
            "included_sections": list(included),
            "omitted_sections": list(omitted),
            "note": _("The JSON payload is capped; omitted sections are exported in the workbook."),
        }
        return json.dumps(payload, default=str, indent=1)

    # --------------------------------------------------------------- rendering
    def _render(self, snapshot):
        company = self.env["res.company"].browse(snapshot.get("company_id") or self.company_id.id)
        currency = self.env["res.currency"].browse(
            snapshot.get("currency_id") or company.currency_id.id
        )
        parts = ['<div class="o_finance_report">']
        heading = f"{escape(str(snapshot.get('report_id') or ''))} &middot; "
        heading += escape(self._label(self.report_type))
        parts.append(f"<h3>{heading}</h3>")
        parts.append("<table class='table table-sm table-bordered'><tbody>")
        for label, value in (
            (_("Company"), company.display_name),
            (_("Currency"), currency.name),
            (_("Period"), self._period_label(snapshot)),
            (_("Filters"), self._filter_label()),
        ):
            parts.append(f"<tr><th>{escape(label)}</th><td>{escape(str(value or ''))}</td></tr>")
        parts.append("</tbody></table>")

        parts.append(self._scalar_table(snapshot))

        for key in snapshot:
            value = snapshot[key]
            if key in META_KEYS:
                continue
            if isinstance(value, list):
                parts.append(self._list_section(key, value))
            elif isinstance(value, dict):
                parts.append(self._dict_section(key, value))

        parts.append("</div>")
        return "".join(parts)

    def _period_label(self, snapshot):
        if snapshot.get("as_of_date"):
            start = snapshot.get("date_from")
            prefix = f"{start} - " if start else ""
            return f"{prefix}{snapshot['as_of_date']}"
        if snapshot.get("date_from") or snapshot.get("date_to"):
            return f"{snapshot.get('date_from') or ''} - {snapshot.get('date_to') or ''}"
        return _("As of today")

    def _filter_label(self):
        bits = []
        if self.report_type in PARTNER_TYPE_REPORTS:
            bits.append(f"partner type: {self.partner_type or 'customer'}")
        if self.partner_ids:
            bits.append(f"partners: {len(self.partner_ids)}")
        if self.journal_ids:
            bits.append(f"journals: {len(self.journal_ids)}")
        if self.account_ids:
            bits.append(f"accounts: {len(self.account_ids)}")
        if self.report_type == "combined_trial_balance" and self.company_ids:
            bits.append(f"companies: {len(self.company_ids)}")
        if self.report_type == "sales_purchase_register":
            bits.append(f"documents: {self.register_type or 'all'}")
        bits.append("posted only" if self.only_posted_moves else "posted and draft")
        return ", ".join(bits)

    def _scalar_table(self, snapshot):
        rows = [
            (key, value)
            for key, value in snapshot.items()
            if key not in META_KEYS and _is_scalar(value)
        ]
        if not rows:
            return ""
        parts = ["<h4>", escape(_("Summary")), "</h4>"]
        parts.append("<table class='table table-sm table-bordered'><tbody>")
        for key, value in rows:
            parts.append(
                f"<tr><th>{escape(str(key))}</th><td>{_format_cell(value)}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)

    def _list_section(self, key, value):
        title = f"<h4>{escape(str(key))} ({len(value)})</h4>"
        if not value:
            return title + f"<p class='text-muted'>{escape(_('No rows.'))}</p>"
        if not isinstance(value[0], dict):
            preview = ", ".join(_format_cell(item) for item in value[:MAX_TABLE_ROWS])
            return title + f"<p>{preview}</p>"
        columns = self._columns(value)
        parts = [title, "<table class='table table-sm table-bordered'><thead><tr>"]
        for column in columns:
            parts.append(f"<th>{escape(str(column))}</th>")
        parts.append("</tr></thead><tbody>")
        for row in value[:MAX_TABLE_ROWS]:
            parts.append("<tr>")
            for column in columns:
                parts.append(f"<td>{_format_cell(row.get(column))}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
        if len(value) > MAX_TABLE_ROWS:
            note = _(
                "Showing the first %(shown)s of %(total)s rows.",
                shown=MAX_TABLE_ROWS,
                total=len(value),
            )
            parts.append(f"<p class='text-muted'>{escape(note)}</p>")
        return "".join(parts)

    def _dict_section(self, key, value):
        title = f"<h4>{escape(str(key))}</h4>"
        if not value:
            return title + f"<p class='text-muted'>{escape(_('Empty.'))}</p>"
        if all(_is_scalar(item) for item in value.values()):
            parts = [title, "<table class='table table-sm table-bordered'><tbody>"]
            for sub_key, sub_value in value.items():
                parts.append(
                    f"<tr><th>{escape(str(sub_key))}</th><td>{_format_cell(sub_value)}</td></tr>"
                )
            parts.append("</tbody></table>")
            return "".join(parts)
        rendered = escape(json.dumps(value, default=str, indent=1)[:4000])
        return title + f"<pre>{rendered}</pre>"

    def _columns(self, rows):
        columns = []
        for row in rows[:MAX_TABLE_ROWS]:
            for key, value in row.items():
                if key not in columns and _is_scalar(value):
                    columns.append(key)
                if len(columns) >= MAX_TABLE_COLUMNS:
                    return columns
        return columns

    # ------------------------------------------------------------------- xlsx
    def _xlsx_filename(self, snapshot):
        report_id = re.sub(r"[^A-Za-z0-9]+", "-", str(snapshot.get("report_id") or "REPORT")).strip("-")
        slug = re.sub(r"[^a-z0-9]+", "-", self.report_type.lower()).strip("-")
        period = snapshot.get("as_of_date") or "_".join(
            part for part in (snapshot.get("date_from"), snapshot.get("date_to")) if part
        )
        period = re.sub(r"[^0-9A-Za-z_-]+", "-", str(period or "current")).strip("-")
        return f"{report_id}-{slug}-{period}.xlsx"

    def _xlsx_formats(self, workbook):
        return {
            "title": workbook.add_format({"bold": True, "font_size": 13}),
            "label": workbook.add_format({"bold": True}),
            "header": workbook.add_format({"bold": True, "bg_color": "#EEEEEE", "border": 1}),
        }

    def _xlsx_sheet_name(self, key, used):
        base = (SHEET_NAME_FORBIDDEN.sub(" ", str(key)).strip() or "Data")[:31]
        name = base
        index = 2
        while name.lower() in used:
            suffix = f" ({index})"
            name = base[: 31 - len(suffix)] + suffix
            index += 1
        used.add(name.lower())
        return name

    def _xlsx_write_cell(self, sheet, row, column, value, formats):
        """Write one cell; return True when the stored text had to be cut."""
        if isinstance(value, bool):
            sheet.write_string(row, column, _("Yes") if value else _("No"))
            return False
        if isinstance(value, float) and not math.isfinite(value):
            # NaN/inf would make Excel repair the file; keep the raw value visible as text.
            sheet.write_string(row, column, _xlsx_text(value))
            return False
        if isinstance(value, (int, float)):
            # No number format: the stored value stays exactly what the report
            # service returned, including rates that a 2-decimal display would hide.
            sheet.write_number(row, column, value)
            return False
        text, truncated = _xlsx_text_parts(value)
        sheet.write_string(row, column, text)
        return truncated

    def _xlsx_list_sheet(self, workbook, key, values, used, formats):
        name = self._xlsx_sheet_name(key, used)
        sheet = workbook.add_worksheet(name)
        if len(values) > MAX_XLSX_ROWS:
            raise UserError(_(
                "Section '%(section)s' returns %(rows)s rows, above the %(limit)s-row export limit. "
                "Narrow the period or filters.",
                section=key,
                rows=len(values),
                limit=MAX_XLSX_ROWS,
            ))
        if not values:
            sheet.write_string(0, 0, _xlsx_text(_("No rows.")))
            return {"section": key, "type": "list", "rows": 0, "columns": 0, "dropped": [],
                    "truncated_cells": 0, "nested_cells": 0, "nested_truncated": 0}
        if not isinstance(values[0], dict):
            sheet.write_string(0, 0, "value", formats["header"])
            truncated_cells = 0
            for row, item in enumerate(values, start=1):
                cell = item if _is_scalar(item) else json.dumps(item, default=str)
                truncated_cells += int(self._xlsx_write_cell(sheet, row, 0, cell, formats))
            sheet.freeze_panes(1, 0)
            return {"section": key, "type": "list", "rows": len(values), "columns": 1, "dropped": [],
                    "truncated_cells": truncated_cells, "nested_cells": 0, "nested_truncated": 0}

        columns = []
        for item in values:
            for column, cell in item.items():
                if column not in columns and _is_scalar(cell):
                    columns.append(column)
        dropped = columns[MAX_XLSX_COLUMNS:]
        columns = columns[:MAX_XLSX_COLUMNS]
        if not columns:
            # Every value in this section is nested: keep the whole row as JSON
            # instead of pointing the reader at a payload that may be capped.
            sheet.write_string(0, 0, NESTED_COLUMN, formats["header"])
            truncated_cells = nested_truncated = 0
            for row, item in enumerate(values, start=1):
                text = json.dumps(item, default=str)
                if self._xlsx_write_cell(sheet, row, 0, text, formats):
                    truncated_cells += 1
                    nested_truncated += 1
            sheet.freeze_panes(1, 0)
            return {"section": key, "type": "list", "rows": len(values), "columns": 1, "dropped": dropped,
                    "truncated_cells": truncated_cells, "nested_cells": len(values),
                    "nested_truncated": nested_truncated}

        kept = set(columns)
        has_extras = any(any(column not in kept for column in item) for item in values)
        for column_index, column in enumerate(columns):
            sheet.write_string(0, column_index, _xlsx_text(column), formats["header"])
        if has_extras:
            sheet.write_string(0, len(columns), NESTED_COLUMN, formats["header"])

        truncated_cells = nested_cells = nested_truncated = 0
        for row, item in enumerate(values, start=1):
            for column_index, column in enumerate(columns):
                truncated_cells += int(self._xlsx_write_cell(sheet, row, column_index, item.get(column), formats))
            if has_extras:
                extras = {column: cell for column, cell in item.items() if column not in kept}
                if extras:
                    nested_cells += 1
                    # Nested structures and scalar columns past the limit travel
                    # together, so a workbook below the row limit loses nothing.
                    text = json.dumps(extras, default=str)
                    if self._xlsx_write_cell(sheet, row, len(columns), text, formats):
                        truncated_cells += 1
                        nested_truncated += 1
                else:
                    sheet.write_string(row, len(columns), "")
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, len(values), len(columns) + int(has_extras) - 1)
        return {"section": key, "type": "list", "rows": len(values),
                "columns": len(columns) + int(has_extras), "dropped": dropped,
                "truncated_cells": truncated_cells, "nested_cells": nested_cells,
                "nested_truncated": nested_truncated}

    def _xlsx_dict_sheet(self, workbook, key, value, used, formats):
        name = self._xlsx_sheet_name(key, used)
        sheet = workbook.add_worksheet(name)
        if len(value) > MAX_XLSX_ROWS:
            raise UserError(_(
                "Section '%(section)s' returns %(rows)s rows, above the %(limit)s-row export limit. "
                "Narrow the period or filters.",
                section=key,
                rows=len(value),
                limit=MAX_XLSX_ROWS,
            ))
        if not value:
            sheet.write_string(0, 0, _xlsx_text(_("Empty.")))
            return {"section": key, "type": "dict", "rows": 0, "columns": 0, "dropped": [],
                    "truncated_cells": 0, "nested_cells": 0, "nested_truncated": 0}
        sheet.write_string(0, 0, "key", formats["header"])
        sheet.write_string(0, 1, "value", formats["header"])
        truncated_cells = nested_cells = nested_truncated = 0
        for row, (sub_key, sub_value) in enumerate(value.items(), start=1):
            sheet.write_string(row, 0, _xlsx_text(sub_key))
            if _is_scalar(sub_value):
                truncated_cells += int(self._xlsx_write_cell(sheet, row, 1, sub_value, formats))
            else:
                nested_cells += 1
                if self._xlsx_write_cell(sheet, row, 1, json.dumps(sub_value, default=str), formats):
                    truncated_cells += 1
                    nested_truncated += 1
        sheet.freeze_panes(1, 0)
        return {"section": key, "type": "dict", "rows": len(value), "columns": 2, "dropped": [],
                "truncated_cells": truncated_cells, "nested_cells": nested_cells,
                "nested_truncated": nested_truncated}

    def _xlsx_summary_sheet(self, sheet, snapshot, filename, sections, formats):
        company = self.env["res.company"].browse(snapshot.get("company_id") or self.company_id.id)
        currency = self.env["res.currency"].browse(
            snapshot.get("currency_id") or company.currency_id.id
        )
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 3, 38)
        sheet.write_string(0, 0, _xlsx_text(_("Finance report export")), formats["title"])
        rows = [
            (_("Report"), f"{snapshot.get('report_id') or ''} - {self._label(self.report_type)}"),
            (_("File"), filename),
            (_("Company"), company.display_name),
            (_("Currency"), currency.name),
            (_("Period"), self._period_label(snapshot)),
            (_("Filters"), self._filter_label()),
            (_("Generated at"), fields.Datetime.to_string(fields.Datetime.now())),
            (_("Generated by"), self.env.user.display_name),
        ]
        row = 2
        for label, content in rows:
            sheet.write_string(row, 0, _xlsx_text(label), formats["label"])
            sheet.write_string(row, 1, _xlsx_text(content))
            row += 1
        row += 1
        sheet.write_string(row, 0, _xlsx_text(_("Sections")), formats["label"])
        row += 1
        for column, header in enumerate((_("Section"), _("Type"), _("Rows"), _("Columns"), _("Nested cells"))):
            sheet.write_string(row, column, _xlsx_text(header), formats["header"])
        row += 1
        for section in sections:
            sheet.write_string(row, 0, _xlsx_text(section["section"]))
            sheet.write_string(row, 1, _xlsx_text(section["type"]))
            sheet.write_number(row, 2, section["rows"])
            sheet.write_number(row, 3, section["columns"])
            sheet.write_number(row, 4, section.get("nested_cells", 0))
            row += 1
        row += 1
        notes = [
            _("Read-only projection of posted journal items and partial reconciliations; no entry is created."),
            _("Numeric cells keep the exact value returned by the report service; no display format rounds them."),
            _("Text that starts with =, +, -, @, tab or carriage return is prefixed with an apostrophe "
              "and stored as text, so it is never evaluated as a formula."),
            _("Rows are not truncated: a section above %(limit)s rows is refused instead.", limit=MAX_XLSX_ROWS),
            _("Nested values (lists or objects) and scalar columns beyond the column limit are written as "
              "JSON in the '%(column)s' column of their sheet, so the workbook stays complete below the "
              "row limit.", column=NESTED_COLUMN),
            _("A cell above %(limit)s characters is cut in the cell and counted in the disclosure below.",
              limit=MAX_XLSX_CELL_CHARS),
            _("The JSON payload is capped at %(limit)s characters. When the cap applies it stays valid JSON "
              "and names its omitted sections in '__truncation__'; those sections keep their own sheet here.",
              limit=MAX_JSON_CHARS),
        ]
        for section in sections:
            if section.get("nested_truncated") or section.get("truncated_cells"):
                notes.append(_(
                    "Section '%(section)s': %(truncated)s of %(total)s cells exceeded %(limit)s characters "
                    "and were cut in the cell; nested cells affected: %(nested)s.",
                    section=section["section"],
                    truncated=section["truncated_cells"],
                    total=section["rows"],
                    limit=MAX_XLSX_CELL_CHARS,
                    nested=section.get("nested_truncated", 0),
                ))
            if section["dropped"]:
                notes.append(_(
                    "Section '%(section)s' has more than %(limit)s scalar columns; these are not separate "
                    "columns but their values remain in '%(column)s': %(columns)s.",
                    section=section["section"],
                    limit=MAX_XLSX_COLUMNS,
                    column=NESTED_COLUMN,
                    columns=", ".join(section["dropped"]),
                ))
        for note in notes:
            sheet.write_string(row, 0, _xlsx_text(note))
            row += 1

    def _xlsx_payload(self, snapshot, filename):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        try:
            summary = workbook.add_worksheet("Summary")
            formats = self._xlsx_formats(workbook)
            used = {"summary"}
            sections = []
            for key, value in snapshot.items():
                if key in META_KEYS:
                    continue
                if isinstance(value, list):
                    sections.append(self._xlsx_list_sheet(workbook, key, value, used, formats))
                elif isinstance(value, dict):
                    sections.append(self._xlsx_dict_sheet(workbook, key, value, used, formats))
            self._xlsx_summary_sheet(summary, snapshot, filename, sections, formats)
        finally:
            workbook.close()
        return output.getvalue()
