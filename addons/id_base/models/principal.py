from odoo import fields, models


class IdPrincipal(models.Model):
    _name = "id.principal"
    _description = "FMCG Principal"
    _order = "name"

    name = fields.Char(string="Principal Name", required=True)
    code = fields.Char(string="Code", required=True, copy=False)
    partner_id = fields.Many2one("res.partner", string="Legal Partner / Vendor", ondelete="restrict")
    pks_number = fields.Char(string="PKS Number")
    pks_start = fields.Date(string="PKS Start Date")
    pks_end = fields.Date(string="PKS End Date")
    pic_name = fields.Char(string="Key Contact / PIC")
    pic_phone = fields.Char(string="PIC Phone")
    pic_email = fields.Char(string="PIC Email")
    brand_ids = fields.One2many("id.brand", "principal_id", string="Brands")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Principal code must be unique!"),
    ]


class IdBrand(models.Model):
    _name = "id.brand"
    _description = "FMCG Brand"
    _order = "name"

    name = fields.Char(string="Brand Name", required=True)
    code = fields.Char(string="Code", required=True)
    principal_id = fields.Many2one("id.principal", string="Principal", required=True, ondelete="cascade")
    sub_brand_ids = fields.One2many("id.sub.brand", "brand_id", string="Sub-Brands")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("principal_code_uniq", "unique(principal_id, code)", "Brand code must be unique per principal!"),
    ]


class IdSubBrand(models.Model):
    _name = "id.sub.brand"
    _description = "FMCG Sub-Brand / Product Line"
    _order = "name"

    name = fields.Char(string="Sub-Brand Name", required=True)
    code = fields.Char(string="Code")
    brand_id = fields.Many2one("id.brand", string="Brand", required=True, ondelete="cascade")
    principal_id = fields.Many2one(
        "id.principal",
        string="Principal",
        related="brand_id.principal_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)
