from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IdPromoSKUWizard(models.TransientModel):
    _name = "id.promo.sku.wizard"
    _description = "Wizard Penentuan Target SKU Promosi FMCG"

    program_id = fields.Many2one(
        "loyalty.program",
        string="Program Promosi",
        required=True,
    )
    principal_id = fields.Many2one(
        "id.principal",
        string="Filter Prinsipal",
    )
    brand_id = fields.Many2one(
        "id.brand",
        string="Filter Brand",
        domain="[('principal_id', '=?', principal_id)]",
    )
    sub_brand_id = fields.Many2one(
        "id.sub.brand",
        string="Filter Sub-Brand",
        domain="[('brand_id', '=?', brand_id)]",
    )
    categ_id = fields.Many2one(
        "product.category",
        string="Filter Kategori Produk",
    )
    product_ids = fields.Many2many(
        "product.product",
        string="Daftar SKU Terpilih",
        help="Daftar produk SKU yang akan mendapatkan alokasi program promo ini",
    )
    selected_count = fields.Integer(
        string="Jumlah SKU",
        compute="_compute_selected_count",
    )

    @api.depends("product_ids")
    def _compute_selected_count(self):
        for rec in self:
            rec.selected_count = len(rec.product_ids)

    @api.onchange("principal_id", "brand_id", "sub_brand_id", "categ_id")
    def _onchange_filter_products(self):
        domain = [("sale_ok", "=", True)]
        if self.principal_id:
            domain.append(("principal_id", "=", self.principal_id.id))
        if self.brand_id:
            domain.append(("brand_id", "=", self.brand_id.id))
        if self.sub_brand_id:
            domain.append(("sub_brand_id", "=", self.sub_brand_id.id))
        if self.categ_id:
            domain.append(("categ_id", "child_of", self.categ_id.id))

        products = self.env["product.product"].search(domain)
        self.product_ids = [(6, 0, products.ids)]

    def action_apply_skus_to_promo(self):
        self.ensure_one()
        if not self.product_ids:
            raise UserError(_("Pilih minimal satu SKU produk untuk diterapkan ke aturan promosi!"))

        program = self.program_id
        # Temukan atau buat loyalty.rule pada program
        rule = program.rule_ids[:1]
        if not rule:
            rule = self.env["loyalty.rule"].create({
                "program_id": program.id,
                "reward_point_amount": 1,
            })

        rule.write({
            "product_ids": [(6, 0, self.product_ids.ids)],
        })

        notif_msg = _("%(count)s SKU produk berhasil dikaitkan ke aturan promo %(promo)s") % {
            "count": len(self.product_ids),
            "promo": program.name,
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Target SKU Berhasil Diterapkan"),
                "message": notif_msg,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
