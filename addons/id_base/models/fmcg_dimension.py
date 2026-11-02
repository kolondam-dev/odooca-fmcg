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
    kode_kemendagri = fields.Char(string="Kode Kemendagri", copy=False, index=True)
    state_id = fields.Many2one("res.country.state", string="Provinsi")
    type = fields.Selection([("kota", "Kota"), ("kabupaten", "Kabupaten")], string="Tipe", default="kabupaten")
    is_out_of_town = fields.Boolean(string="Luar Kota", default=False)
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    area_km2 = fields.Float(string="Area (km2)", digits=(12, 3))
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "City code must be unique!")
    _kode_kemendagri_uniq = models.Constraint(
        "UNIQUE(kode_kemendagri)", "Kemendagri code must be unique!"
    )


class IdDistrict(models.Model):
    _name = "id.district"
    _description = "Kecamatan (District)"
    _order = "city_id, name"

    name = fields.Char(string="Nama Kecamatan", required=True)
    code = fields.Char(string="Kode Kecamatan", copy=False)
    kode_kemendagri = fields.Char(string="Kode Kemendagri", copy=False, index=True)
    city_id = fields.Many2one("id.city", string="Kabupaten / Kota")
    city = fields.Char(string="Nama Kota / Regency (Teks)")
    state_id = fields.Many2one(
        "res.country.state", string="Provinsi", related="city_id.state_id", store=True, readonly=True
    )
    coverage_area_id = fields.Many2one("id.coverage.area", string="Zona Coverage")
    geojson_polygon = fields.Text(string="GeoJSON Boundary Polygon")
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    area_km2 = fields.Float(string="Area (km2)", digits=(12, 3))
    bbox_xmin = fields.Float(string="BBox Min Longitude", digits=(10, 7))
    bbox_ymin = fields.Float(string="BBox Min Latitude", digits=(10, 7))
    bbox_xmax = fields.Float(string="BBox Max Longitude", digits=(10, 7))
    bbox_ymax = fields.Float(string="BBox Max Latitude", digits=(10, 7))
    geom_source = fields.Char(string="Geometry Source", readonly=True)
    geom_quality = fields.Char(string="Geometry QA Flag", readonly=True)
    geom_updated_at = fields.Datetime(string="Geometry Updated At", readonly=True)
    active = fields.Boolean(default=True)

    _kode_kemendagri_uniq = models.Constraint(
        "UNIQUE(kode_kemendagri)", "Kemendagri code must be unique!"
    )


class IdSubdistrict(models.Model):
    _name = "id.subdistrict"
    _description = "Kelurahan / Desa"
    _order = "district_id, name"

    name = fields.Char(string="Nama Kelurahan / Desa", required=True)
    code = fields.Char(string="Kode Kelurahan", copy=False)
    kode_kemendagri = fields.Char(string="Kode Kemendagri", copy=False, index=True)
    district_id = fields.Many2one("id.district", string="Kecamatan", required=True, ondelete="cascade")
    postal_code = fields.Char(string="Kode Pos", index=True)
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    area_km2 = fields.Float(string="Area (km2)", digits=(12, 3))
    is_legacy = fields.Boolean(string="Legacy Demo Record", default=False)
    active = fields.Boolean(default=True)

    _kode_kemendagri_uniq = models.Constraint(
        "UNIQUE(kode_kemendagri)", "Kemendagri code must be unique!"
    )
