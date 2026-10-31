import base64
import csv
import io
from odoo import fields, models
from odoo.exceptions import UserError


class CoreTaxExportWizard(models.TransientModel):
    _name = "coretax.export.wizard"
    _description = "Wizard Ekspor Faktur Pajak CoreTax DJP"

    date_from = fields.Date(
        string="Dari Tanggal",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Sampai Tanggal",
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    partner_ids = fields.Many2many(
        "res.partner",
        string="Filter Pelanggan (Opsional)",
        domain="[('customer_rank', '>', 0)]",
    )
    export_file = fields.Binary(string="Berkas CSV CoreTax", readonly=True)
    export_filename = fields.Char(string="Nama Berkas", readonly=True)
    total_invoices = fields.Integer(string="Total Faktur", readonly=True)
    total_dpp = fields.Float(string="Total DPP (Rp)", readonly=True)
    total_ppn = fields.Float(string="Total PPN (Rp)", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Selesai")],
        default="draft",
        string="Status",
    )

    def action_generate_coretax_csv(self):
        self.ensure_one()
        domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
            ("company_id", "=", self.company_id.id),
        ]
        if self.partner_ids:
            domain.append(("commercial_partner_id", "in", self.partner_ids.ids))

        invoices = self.env["account.move"].search(domain, order="invoice_date, id")
        if not invoices:
            raise UserError(
                f"Tidak ditemukan faktur Posted pada {self.date_from} s/d {self.date_to}."
            )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

        # Header resmi format e-Faktur / CoreTax DJP
        writer.writerow([
            "KD_JENIS_TRANSAKSI",
            "FG_PENGGANTI",
            "NOMOR_FAKTUR",
            "MASA_PAJAK",
            "TAHUN_PAJAK",
            "TANGGAL_FAKTUR",
            "NPWP",
            "NAMA",
            "ALAMAT_LENGKAP",
            "JUMLAH_DPP",
            "JUMLAH_PPN",
            "JUMLAH_PPNBM",
            "ID_KETERANGAN_TAMBAHAN",
            "FG_UANG_MUKA",
            "UANG_MUKA_DPP",
            "UANG_MUKA_PPN",
            "UANG_MUKA_PPNBM",
            "REFERENSI",
        ])

        total_dpp = 0.0
        total_ppn = 0.0
        count = 0

        for inv in invoices:
            partner = inv.commercial_partner_id or inv.partner_id
            dpp = inv.amount_untaxed or 0.0
            ppn = inv.amount_tax or 0.0
            total_dpp += dpp
            total_ppn += ppn
            count += 1

            # Pastikan nomor faktur pajak ada
            if not inv.l10n_id_tax_invoice_number:
                inv.action_generate_nsfp()

            nsfp = (inv.l10n_id_tax_invoice_number or "").replace(".", "").replace("-", "")
            tax_date = inv.l10n_id_tax_invoice_date or inv.invoice_date or fields.Date.today()
            npwp = (partner.vat or "00.000.000.0-000.000").replace(".", "").replace("-", "")
            address = f"{partner.street or ''} {partner.city or ''}".strip() or "Manado"

            writer.writerow([
                inv.l10n_id_tax_transaction_code or "01",
                "0",  # Faktur Normal (Bukan Pengganti)
                nsfp,
                tax_date.month,
                tax_date.year,
                tax_date.strftime("%d/%m/%Y"),
                npwp,
                partner.name or "Pelanggan",
                address,
                int(round(dpp)),
                int(round(ppn)),
                0,    # PPnBM
                "",   # Keterangan Tambahan
                "0",  # Uang Muka
                0,
                0,
                0,
                inv.name or "",
            ])
            inv.l10n_id_coretax_exported = True

        csv_data = output.getvalue().encode("utf-8")
        filename = f"CoreTax_DJP_{self.date_from.strftime('%Y%m%d')}_{self.date_to.strftime('%Y%m%d')}.csv"

        self.write({
            "export_file": base64.b64encode(csv_data),
            "export_filename": filename,
            "total_invoices": count,
            "total_dpp": total_dpp,
            "total_ppn": total_ppn,
            "state": "done",
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "coretax.export.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
