from odoo import fields, models


class IdChannel(models.Model):
    _name = "id.channel"
    _description = "FMCG Distribution Channel"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Channel Name", required=True)
    code = fields.Char(string="Code", required=True, copy=False)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Channel code must be unique!"),
    ]


class IdTier(models.Model):
    _name = "id.tier"
    _description = "Customer Tier / Classification"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Tier Name", required=True)
    code = fields.Char(string="Code", required=True, copy=False)
    discount_percent = fields.Float(string="Base Discount (%)", digits=(5, 2), default=0.0)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Tier code must be unique!"),
    ]


class IdCoverageArea(models.Model):
    _name = "id.coverage.area"
    _description = "FMCG Distribution Coverage Area"
    _order = "name"

    name = fields.Char(string="Area Name", required=True)
    code = fields.Char(string="Area Code", required=True, copy=False)
    category = fields.Selection(
        [
            ("urban", "Dalam Kota (Urban)"),
            ("hinterland", "Dataran Tinggi (Hinterland)"),
            ("port", "Pelabuhan & Industri"),
            ("rural", "Luar Kota (Rural)"),
        ],
        string="Area Type",
        default="urban",
        required=True,
    )
    city = fields.Char(string="City / Regency")
    state_id = fields.Many2one("res.country.state", string="Province")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Coverage Area code must be unique!"),
    ]


class IdFleetType(models.Model):
    _name = "id.fleet.type"
    _description = "FMCG Operational Fleet Type"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Tipe Operasional", required=True)
    code = fields.Char(string="Kode", required=True, copy=False)
    wheel_count = fields.Integer(string="Jumlah Roda", default=4)
    capacity_cbm = fields.Float(string="Kapasitas Kubikasi (m³)", digits=(5, 2))
    capacity_ton = fields.Float(string="Kapasitas Tonase (Ton)", digits=(5, 2))
    description = fields.Text(string="Deskripsi / Karakteristik Rute")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Fleet type code must be unique!"),
    ]


class IdCity(models.Model):
    _name = "id.city"
    _description = "Kabupaten / Kota"
    _order = "name"

    name = fields.Char(string="Kabupaten / Kota", required=True)
    code = fields.Char(string="Kode Wilayah / BPS", copy=False)
    state_id = fields.Many2one("res.country.state", string="Provinsi")
    type = fields.Selection([("kota", "Kota"), ("kabupaten", "Kabupaten")], string="Tipe", default="kabupaten")
    is_out_of_town = fields.Boolean(string="Luar Kota", default=False)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "City code must be unique!"),
    ]


class IdDistrict(models.Model):
    _name = "id.district"
    _description = "Kecamatan (District)"
    _order = "city_id, name"

    name = fields.Char(string="Nama Kecamatan", required=True)
    code = fields.Char(string="Kode Kecamatan", copy=False)
    city_id = fields.Many2one("id.city", string="Kabupaten / Kota")
    city = fields.Char(string="Nama Kota / Regency (Teks)")
    state_id = fields.Many2one("res.country.state", string="Provinsi")
    coverage_area_id = fields.Many2one("id.coverage.area", string="Zona Coverage")
    geojson_polygon = fields.Text(string="GeoJSON Boundary Polygon")
    active = fields.Boolean(default=True)



class IdSubdistrict(models.Model):
    _name = "id.subdistrict"
    _description = "Kelurahan / Desa"
    _order = "district_id, name"

    name = fields.Char(string="Nama Kelurahan / Desa", required=True)
    code = fields.Char(string="Kode Kelurahan", copy=False)
    district_id = fields.Many2one("id.district", string="Kecamatan", required=True, ondelete="cascade")
    postal_code = fields.Char(string="Kode Pos", index=True)
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    active = fields.Boolean(default=True)


