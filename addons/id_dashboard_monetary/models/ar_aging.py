# Part of odooca-fmcg. License LGPL-3.
"""Accounts receivable aging matrix for FMCG credit control.

Two read-only SQL views bind directly to ``account_move``:

* ``id.ar.aging`` - one row per open customer invoice with its FMCG aging bucket.
* ``id.ar.customer.balance`` - open balance aggregated per customer, used for the
  top-10 exposure list and the credit-hold decision.

Buckets follow the distributor credit policy:

===================  =====================================================
Bucket               Operational consequence
===================  =====================================================
``not_due``          No action, invoice still within terms.
``overdue_1_7``      Early warning call by the salesperson.
``overdue_8_14``     New orders held (credit hold).
``overdue_15_30``    Supervisor audit of the outlet.
``overdue_over_30``  Special handling / bad debt provisioning.
===================  =====================================================
"""

from odoo import fields, models, tools

AGING_BUCKETS_SQL = """
            CASE
                WHEN am.invoice_date_due IS NULL OR am.invoice_date_due >= CURRENT_DATE THEN 'not_due'
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 1 AND 7 THEN 'overdue_1_7'
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 8 AND 14 THEN 'overdue_8_14'
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 15 AND 30 THEN 'overdue_15_30'
                ELSE 'overdue_over_30'
            END
"""

BUCKET_RANK_SQL = """
            CASE
                WHEN am.invoice_date_due IS NULL OR am.invoice_date_due >= CURRENT_DATE THEN 1
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 1 AND 7 THEN 2
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 8 AND 14 THEN 3
                WHEN (CURRENT_DATE - am.invoice_date_due) BETWEEN 15 AND 30 THEN 4
                ELSE 5
            END
"""

OPEN_INVOICE_WHERE = """
        am.state = 'posted'
        AND am.move_type IN ('out_invoice', 'out_refund')
        AND am.payment_state IN ('not_paid', 'partial')
        AND am.amount_residual_signed <> 0
"""

AGING_SQL = f"""
CREATE OR REPLACE VIEW id_ar_aging AS (
    SELECT am.id AS id,
           am.id AS move_id,
           am.name AS invoice_number,
           am.partner_id AS partner_id,
           COALESCE(am.invoice_user_id, rp.user_id) AS salesman_id,
           rp.coverage_area_id AS area_id,
           am.company_id AS company_id,
           rc.currency_id AS currency_id,
           am.invoice_date AS invoice_date,
           am.invoice_date_due AS date_due,
           am.payment_state AS payment_state,
           am.amount_residual_signed AS amount_residual,
           CASE
               WHEN am.invoice_date_due IS NULL OR am.invoice_date_due >= CURRENT_DATE THEN 0
               ELSE (CURRENT_DATE - am.invoice_date_due)
           END AS days_overdue,
           {AGING_BUCKETS_SQL} AS bucket
      FROM account_move am
      JOIN res_partner rp ON rp.id = am.partner_id
      JOIN res_company rc ON rc.id = am.company_id
     WHERE {OPEN_INVOICE_WHERE}
)
"""

CUSTOMER_BALANCE_SQL = f"""
CREATE OR REPLACE VIEW id_ar_customer_balance AS (
    WITH open_invoice AS (
        SELECT am.id AS move_id,
               am.partner_id AS partner_id,
               am.company_id AS company_id,
               am.amount_residual_signed AS amount_residual,
               COALESCE(am.invoice_user_id, rp.user_id) AS salesman_id,
               rp.coverage_area_id AS area_id,
               am.invoice_date_due AS date_due,
               {BUCKET_RANK_SQL} AS bucket_rank
          FROM account_move am
          JOIN res_partner rp ON rp.id = am.partner_id
         WHERE {OPEN_INVOICE_WHERE}
    )
    SELECT ROW_NUMBER() OVER (ORDER BY SUM(oi.amount_residual) DESC, oi.partner_id) AS id,
           oi.partner_id AS partner_id,
           MAX(oi.area_id) AS area_id,
           MAX(oi.salesman_id) AS salesman_id,
           oi.company_id AS company_id,
           rc.currency_id AS currency_id,
           SUM(oi.amount_residual) AS amount_residual,
           COUNT(*) AS invoice_count,
           MIN(oi.date_due) AS oldest_due_date,
           MAX(GREATEST(COALESCE(CURRENT_DATE - oi.date_due, 0), 0)) AS max_days_overdue,
           CASE MAX(oi.bucket_rank)
               WHEN 5 THEN 'overdue_over_30'
               WHEN 4 THEN 'overdue_15_30'
               WHEN 3 THEN 'overdue_8_14'
               WHEN 2 THEN 'overdue_1_7'
               ELSE 'not_due'
           END AS worst_bucket
      FROM open_invoice oi
      JOIN res_company rc ON rc.id = oi.company_id
     GROUP BY oi.partner_id, oi.company_id, rc.currency_id
)
"""

BUCKET_SELECTION = [
    ("not_due", "Not Due"),
    ("overdue_1_7", "Overdue 1-7 Days (Early Warning)"),
    ("overdue_8_14", "Overdue 8-14 Days (Credit Hold)"),
    ("overdue_15_30", "Overdue 15-30 Days (Supervisor Audit)"),
    ("overdue_over_30", "Overdue > 30 Days (Bad Debt)"),
]


class ArAging(models.Model):
    _name = "id.ar.aging"
    _description = "FMCG Accounts Receivable Aging"
    _auto = False
    _rec_name = "invoice_number"
    _order = "days_overdue desc, amount_residual desc"

    move_id = fields.Many2one("account.move", string="Invoice", readonly=True)
    invoice_number = fields.Char(string="Invoice Number", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    salesman_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    area_id = fields.Many2one("id.coverage.area", string="Coverage Area", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    invoice_date = fields.Date(string="Invoice Date", readonly=True)
    date_due = fields.Date(string="Due Date", readonly=True)
    payment_state = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
            ("in_payment", "In Payment"),
            ("reversed", "Reversed"),
            ("blocked", "Blocked"),
        ],
        string="Payment Status",
        readonly=True,
    )
    days_overdue = fields.Integer(string="Days Overdue", readonly=True)
    bucket = fields.Selection(BUCKET_SELECTION, string="Aging Bucket", readonly=True)
    amount_residual = fields.Monetary(
        string="Outstanding Amount", currency_field="currency_id", readonly=True
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(AGING_SQL)


class ArCustomerBalance(models.Model):
    _name = "id.ar.customer.balance"
    _description = "FMCG Customer Receivable Exposure"
    _auto = False
    _rec_name = "partner_id"
    _order = "amount_residual desc"

    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    salesman_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    area_id = fields.Many2one("id.coverage.area", string="Coverage Area", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    amount_residual = fields.Monetary(
        string="Outstanding Amount", currency_field="currency_id", readonly=True
    )
    invoice_count = fields.Integer(string="Open Invoices", readonly=True)
    oldest_due_date = fields.Date(string="Oldest Due Date", readonly=True)
    max_days_overdue = fields.Integer(string="Max Days Overdue", readonly=True)
    worst_bucket = fields.Selection(BUCKET_SELECTION, string="Worst Bucket", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(CUSTOMER_BALANCE_SQL)
