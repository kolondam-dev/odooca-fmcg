from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    principal_id = fields.Many2one("id.principal", string="Principal", index=True)
    fmcg_category = fields.Selection(
        [
            ("biscuit_wafer", "Biscuit & Wafer"),
            ("confectionery", "Chocolate & Confectionery"),
            ("coffee_powder", "Coffee & Powdered Beverage"),
            ("coffee_hot", "Coffee & Hot Beverages"),
            ("noodles_food", "Instant Noodles & Foods"),
            ("beverages_rtd", "Ready to Drink (RTD) & Beverage"),
            ("coffee_wings", "Coffee"),
            ("foods_savory", "Foods & Savory"),
            ("home_care", "Home Care & Hygiene"),
            ("personal_care", "Personal Care & Beauty"),
            ("food", "Food & Grocery"),
            ("rtd", "Ready-To-Drink"),
            ("dairy", "Dairy"),
            ("other", "Other"),
        ],
        string="Principal Category / Divisi",
        index=True,
    )
    brand_id = fields.Many2one("id.brand", string="Brand", index=True, domain="[('principal_id', '=?', principal_id)]")
    sub_brand_id = fields.Many2one(
        "id.sub.brand",
        string="Sub-Brand",
        index=True,
        domain="[('brand_id', '=?', brand_id)]",
    )
    inner_qty = fields.Integer(
        string="Unit Dasar per Inner / Renceng / Pack",
        default=1,
        help="Jumlah satuan dasar sesuai base_uom dalam satu kemasan menengah.",
    )
    carton_qty = fields.Integer(
        string="Unit Dasar per Karton",
        default=1,
        help="Jumlah satuan dasar sesuai base_uom yang terkandung dalam satu karton.",
    )
    fmcg_base_uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan Dasar FMCG",
        copy=False,
        ondelete="restrict",
        help="Label satuan terkecil per SKU; nilainya setara 1 unit inventaris Odoo yang sudah ada.",
    )
    fmcg_inner_uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan Inner FMCG",
        copy=False,
        ondelete="restrict",
        help="Satuan kemasan menengah per SKU, bila SKU memiliki inner/renceng/pack.",
    )
    fmcg_carton_uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan Karton FMCG",
        copy=False,
        ondelete="restrict",
        help="Satuan karton per SKU dengan faktor konversi spesifik SKU.",
    )
    base_weight_g = fields.Float(
        string="Gramasi Base (g)",
        compute="_compute_base_weight_g",
        inverse="_inverse_base_weight_g",
        store=True,
        digits=(12, 1),
        help="Berat bersih satuan dasar dalam satuan gram (terkoneksi dua arah dengan weight dalam kg).",
    )
    carton_length_cm = fields.Float(string="Panjang Karton (cm)", digits=(12, 1))
    carton_width_cm = fields.Float(string="Lebar Karton (cm)", digits=(12, 1))
    carton_height_cm = fields.Float(string="Tinggi Karton (cm)", digits=(12, 1))
    carton_volume_cbm = fields.Float(
        string="Volume Karton (m³)",
        compute="_compute_carton_volume_cbm",
        store=True,
        digits=(12, 4),
        help="Kubikasi kemasan karton m³ (dihitung otomatis dari P x L x T / 1.000.000).",
    )
    carton_weight_kg = fields.Float(string="Berat Karton (kg)", digits=(12, 2))
    carton_barcode = fields.Char(string="Barcode Karton", copy=False, index=True)

    def write(self, vals):
        ratio_fields = {"inner_qty", "carton_qty"}
        if ratio_fields.intersection(vals):
            for product in self:
                if not product.fmcg_carton_uom_id:
                    continue
                new_inner = vals.get("inner_qty", product.inner_qty)
                new_carton = vals.get("carton_qty", product.carton_qty)
                if new_inner != product.inner_qty or new_carton != product.carton_qty:
                    raise ValidationError(
                        f"Rasio kemasan {product.display_name} sudah dipakai sebagai UoM transaksi. "
                        "Perubahan harus melalui migrasi UoM terkontrol."
                    )
        return super().write(vals)

    def _fmcg_get_or_create_uom(self, name, relative_uom, factor):
        """Get an immutable Odoo 19 UoM node for one exact packaging ratio."""
        Uom = self.env["uom.uom"].sudo()
        domain = [
            ("name", "=", name),
            ("relative_uom_id", "=", relative_uom.id),
            ("relative_factor", "=", factor),
        ]
        uom = Uom.search(domain, limit=1)
        if not uom:
            uom = Uom.create({
                "name": name,
                "relative_uom_id": relative_uom.id,
                "relative_factor": factor,
                "active": True,
            })
        return uom

    def configure_fmcg_packaging_uoms(self, base_uom, inner_qty, carton_qty):
        """Attach SKU-specific Odoo 19 packaging UoMs without changing inventory UoM.

        The product inventory UoM deliberately remains untouched so existing stock
        quantities and transaction references retain their current canonical unit.
        """
        self.ensure_one()
        if not base_uom:
            raise ValidationError("Satuan dasar FMCG wajib ditentukan.")
        if inner_qty < 1 or carton_qty < 1 or carton_qty % inner_qty:
            raise ValidationError(
                "Rasio kemasan tidak valid: carton_qty harus merupakan kelipatan inner_qty."
            )
        if base_uom == self.uom_id or base_uom.factor != self.uom_id.factor:
            raise ValidationError(
                "Satuan label dasar FMCG harus memiliki faktor 1:1 terhadap UoM inventaris produk."
            )
        if self.fmcg_carton_uom_id and (
            self.fmcg_base_uom_id != base_uom
            or self.inner_qty != inner_qty
            or self.carton_qty != carton_qty
        ):
            raise ValidationError(
                f"Konfigurasi kemasan {self.display_name} sudah digunakan. "
                "Perubahan rasio memerlukan migrasi UoM terkontrol."
            )

        expected_inner = False
        if inner_qty > 1:
            expected_inner = self._fmcg_get_or_create_uom(
                f"Inner ({inner_qty} {base_uom.name})",
                base_uom,
                inner_qty,
            )

        carton_reference = expected_inner or base_uom
        carton_factor = carton_qty // inner_qty if expected_inner else carton_qty
        expected_carton = self._fmcg_get_or_create_uom(
            f"Karton ({carton_qty} {base_uom.name})",
            carton_reference,
            carton_factor,
        )

        # Never mutate an existing UoM's conversion factor: it may already be used
        # by posted documents. A changed master ratio must be handled as a migration.
        for field_name, expected in (
            ("fmcg_base_uom_id", base_uom),
            ("fmcg_inner_uom_id", expected_inner),
            ("fmcg_carton_uom_id", expected_carton),
        ):
            current = self[field_name]
            if current and current != expected:
                raise ValidationError(
                    f"Konfigurasi {field_name} untuk {self.display_name} sudah ada dan berbeda. "
                    "Perubahan rasio memerlukan migrasi terkontrol, bukan overwrite loader."
                )

        self.write({
            "inner_qty": inner_qty,
            "carton_qty": carton_qty,
            "fmcg_base_uom_id": base_uom.id,
            "fmcg_inner_uom_id": expected_inner.id if expected_inner else False,
            "fmcg_carton_uom_id": expected_carton.id,
            "uom_ids": [(4, uom.id) for uom in (base_uom, expected_inner, expected_carton) if uom],
        })
        return True

    @api.depends("weight")
    def _compute_base_weight_g(self):
        for record in self:
            record.base_weight_g = (record.weight or 0.0) * 1000.0

    def _inverse_base_weight_g(self):
        for record in self:
            record.weight = (record.base_weight_g or 0.0) / 1000.0

    @api.depends("carton_length_cm", "carton_width_cm", "carton_height_cm")
    def _compute_carton_volume_cbm(self):
        for record in self:
            if record.carton_length_cm and record.carton_width_cm and record.carton_height_cm:
                record.carton_volume_cbm = round(
                    (record.carton_length_cm * record.carton_width_cm * record.carton_height_cm) / 1_000_000.0,
                    4,
                )
            else:
                record.carton_volume_cbm = 0.0
