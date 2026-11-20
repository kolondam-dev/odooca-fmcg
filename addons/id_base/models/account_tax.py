# Part of odooca-fmcg. License LGPL-3.
"""Ekstensi account.tax untuk kepatuhan PMK 131/2024 (Kode 04 DPP Nilai Lain 11/12)."""

from odoo import models


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _is_tax_code_04_dpp_nilai_lain(self):
        """Memeriksa apakah record pajak merupakan Pajak Kode 04 DPP Nilai Lain (PMK 131/2024, 12%)."""
        self.ensure_one()
        code_field = str(getattr(self, "l10n_id_tax_transaction_code", "") or "")
        if code_field == "04":
            return True
        name = str(getattr(self, "name", "") or "").lower()
        desc = str(getattr(self, "description", "") or "").lower()
        combined = f"{name} {desc}"
        return (
            getattr(self, "type_tax_use", "") == "sale"
            and abs(float(getattr(self, "amount", 0.0) or 0.0) - 12.0) < 0.01
            and any(term in combined for term in ("04", "nilai lain", "kode 04", "kode_04"))
        )

    def _eval_tax_amount_price_excluded(self, batch, raw_base, evaluation_context):
        """Evaluasi nominal pajak price-excluded dengan penyesuaian dasar pengenaan pajak (DPP Nilai Lain 11/12)."""
        self.ensure_one()
        if self._is_tax_code_04_dpp_nilai_lain() and self.amount_type == "percent":
            # PMK 131/2024: DPP Nilai Lain = (11/12) x commercial DPP.
            # Nominal PPN 12% = 12% x (11/12) x commercial DPP = commercial DPP x 11%.
            dpp_nilai_lain = raw_base * 11.0 / 12.0
            return dpp_nilai_lain * (self.amount / 100.0)
        if hasattr(super(), "_eval_tax_amount_price_excluded"):
            return super()._eval_tax_amount_price_excluded(batch, raw_base, evaluation_context)
        return raw_base * (self.amount / 100.0)

    def _eval_tax_amount_price_included(self, batch, raw_base, evaluation_context):
        """Evaluasi nominal pajak price-included dengan penyesuaian DPP Nilai Lain 11/12."""
        self.ensure_one()
        if self._is_tax_code_04_dpp_nilai_lain() and self.amount_type == "percent":
            effective_rate = (11.0 / 12.0) * (self.amount / 100.0)
            return raw_base - (raw_base / (1.0 + effective_rate))
        if hasattr(super(), "_eval_tax_amount_price_included"):
            return super()._eval_tax_amount_price_included(batch, raw_base, evaluation_context)
        return super()._eval_tax_amount_price_included(batch, raw_base, evaluation_context)

    def _get_tax_details(self, *args, **kwargs):
        """Report DPP Nilai Lain while preserving Odoo's rounded tax amounts."""
        details = super()._get_tax_details(*args, **kwargs)
        for tax_data in details["taxes_data"]:
            tax = tax_data["tax"]
            if tax.amount_type == "percent" and tax._is_tax_code_04_dpp_nilai_lain():
                tax_data["base_amount"] *= 11.0 / 12.0
        return details
