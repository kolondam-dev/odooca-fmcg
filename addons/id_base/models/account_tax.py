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

    def _get_tax_details(
        self,
        price_unit,
        quantity,
        precision_rounding=0.01,
        rounding_method="round_per_line",
        product=None,
        product_uom=None,
        special_mode=False,
        manual_tax_amounts=None,
        filter_tax_function=None,
        document_tax_mode=None,
    ):
        """Memastikan data dasar pajak (tax_base_amount / base) dan tax_amount disesuaikan ke DPP Nilai Lain (11/12)."""
        res = super()._get_tax_details(
            price_unit,
            quantity,
            precision_rounding=precision_rounding,
            rounding_method=rounding_method,
            product=product,
            product_uom=product_uom,
            special_mode=special_mode,
            manual_tax_amounts=manual_tax_amounts,
            filter_tax_function=filter_tax_function,
            document_tax_mode=document_tax_mode,
        )
        if not isinstance(res, dict):
            return res

        taxes_data = res.get("taxes_data")
        has_tax_04 = False
        if isinstance(taxes_data, list):
            for t_data in taxes_data:
                t_rec = t_data.get("tax")
                if not t_rec and "tax_id" in t_data and hasattr(self, "browse"):
                    t_rec = self.browse(t_data["tax_id"])
                if (
                    t_rec
                    and hasattr(t_rec, "_is_tax_code_04_dpp_nilai_lain")
                    and t_rec._is_tax_code_04_dpp_nilai_lain()
                ):
                    has_tax_04 = True
                    if "base" in t_data:
                        t_data["base"] = t_data["base"] * 11.0 / 12.0
                    expected_tax = t_data.get("base", 0.0) * (t_rec.amount / 100.0)
                    t_data["tax_amount"] = expected_tax

        elif isinstance(taxes_data, dict):
            for t_id, t_data in taxes_data.items():
                t_rec = t_data.get("tax") or (self.browse(t_id) if hasattr(self, "browse") else None)
                if (
                    t_rec
                    and hasattr(t_rec, "_is_tax_code_04_dpp_nilai_lain")
                    and t_rec._is_tax_code_04_dpp_nilai_lain()
                ):
                    has_tax_04 = True
                    if "base" in t_data:
                        t_data["base"] = t_data["base"] * 11.0 / 12.0
                    expected_tax = t_data.get("base", 0.0) * (t_rec.amount / 100.0)
                    t_data["tax_amount"] = expected_tax

        if has_tax_04:
            tot_tax = 0.0
            if isinstance(taxes_data, list):
                tot_tax = sum(td.get("tax_amount", 0.0) for td in taxes_data)
            elif isinstance(taxes_data, dict):
                tot_tax = sum(td.get("tax_amount", 0.0) for td in taxes_data.values())

            if "total_excluded" in res:
                res["total_included"] = res["total_excluded"] + tot_tax
            if "raw_total_excluded" in res and "raw_total_included" in res:
                res["raw_total_included"] = res["raw_total_excluded"] + tot_tax
            if "total_excluded_currency" in res and "total_included_currency" in res:
                res["total_included_currency"] = res["total_excluded_currency"] + tot_tax
            if "raw_total_excluded_currency" in res and "raw_total_included_currency" in res:
                res["raw_total_included_currency"] = res["raw_total_excluded_currency"] + tot_tax

        return res

    def compute_all(
        self,
        price_unit,
        currency=None,
        quantity=1.0,
        product=None,
        partner=None,
        is_refund=False,
        handle_price_include=True,
        include_caba_tags=False,
        **kwargs,
    ):
        """Override compute_all untuk menjamin integritas DPP Nilai Lain (11/12) dan PPN 12%."""
        res = super().compute_all(
            price_unit,
            currency=currency,
            quantity=quantity,
            product=product,
            partner=partner,
            is_refund=is_refund,
            handle_price_include=handle_price_include,
            include_caba_tags=include_caba_tags,
            **kwargs,
        )
        if not isinstance(res, dict) or "taxes" not in res:
            return res

        has_04 = False
        for t in res["taxes"]:
            t_id = t.get("id")
            t_rec = self.browse(t_id) if (t_id and hasattr(self, "browse")) else None
            if t_rec and hasattr(t_rec, "_is_tax_code_04_dpp_nilai_lain") and t_rec._is_tax_code_04_dpp_nilai_lain():
                has_04 = True
                orig_base = t.get("base", 0.0)
                t["base"] = orig_base * 11.0 / 12.0
                t["amount"] = t["base"] * (t_rec.amount / 100.0)

        if has_04:
            total_tax = sum(t.get("amount", 0.0) for t in res["taxes"])
            res["total_included"] = res.get("total_excluded", 0.0) + total_tax

        return res
