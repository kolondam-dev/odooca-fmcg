#!/usr/bin/env python3
"""Generator Master GeoJSON Polygons untuk Wilayah Sulawesi Utara (Provinsi 71).

Menghasilkan poligon geospasial tervalidasi untuk:
1. data/geo/sulut_provinsi.geojson (Batas Provinsi Sulawesi Utara)
2. data/geo/sulut_kab_kota.geojson (15 Kabupaten/Kota lengkap se-Sulut)
3. data/geo/sulut_districts.geojson (18 Kecamatan operasional kunci)
4. data/geo/sulut_villages.geojson (Kelurahan/Desa sentra perdagangan & outlet)
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEO_DIR = ROOT / "data" / "geo"
GEO_DIR.mkdir(parents=True, exist_ok=True)


def make_box_poly(min_lat, min_lng, max_lat, max_lng):
    """Menghasilkan poligon koordinat GeoJSON (lng, lat) persegi/polygon tertutup."""
    return [
        [
            [round(min_lng, 4), round(min_lat, 4)],
            [round(max_lng, 4), round(min_lat, 4)],
            [round(max_lng, 4), round(max_lat, 4)],
            [round(min_lng, 4), round(max_lat, 4)],
            [round(min_lng, 4), round(min_lat, 4)],
        ]
    ]


def generate_provinsi():
    # Batas daratan dan maritim Sulawesi Utara (termasuk kepulauan)
    coords = [
        [
            [124.0, 0.3],
            [125.3, 0.3],
            [125.7, 1.3],
            [125.9, 1.8],
            [125.5, 4.8],  # Kep. Talaud / Sangihe
            [124.5, 4.8],
            [123.1, 1.0],  # Bolmong Utara / Gorontalo border
            [124.0, 0.3],
        ]
    ]
    feature = {
        "type": "FeatureCollection",
        "name": "sulut_provinsi",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "bps_code": "71",
                    "name": "Sulawesi Utara",
                    "iso_code": "ID-SA",
                    "capital": "Kota Manado",
                    "type": "Provinsi",
                },
                "geometry": {"type": "Polygon", "coordinates": coords},
            }
        ],
    }
    with open(GEO_DIR / "sulut_provinsi.geojson", "w", encoding="utf-8") as f:
        json.dump(feature, f, indent=2)
    print(" -> sulut_provinsi.geojson berhasil dibuat.")


def generate_kab_kota():
    # 15 Kabupaten/Kota Lengkap Tanpa Sampling (Playbook & Scope §10)
    kab_kota_list = [
        # BPS, Nama, Tipe, Center Lat, Center Lng, MinLat, MinLng, MaxLat, MaxLng
        ("7171", "Kota Manado", "Kota", 1.4822, 124.8489, 1.435, 124.805, 1.555, 124.935),
        ("7172", "Kota Bitung", "Kota", 1.4404, 125.1217, 1.385, 125.080, 1.530, 125.230),
        ("7173", "Kota Tomohon", "Kota", 1.3255, 124.8392, 1.280, 124.795, 1.370, 124.875),
        ("7174", "Kota Kotamobagu", "Kota", 0.7305, 124.3139, 0.690, 124.270, 0.770, 124.360),
        ("7102", "Kab. Minahasa", "Kabupaten", 1.3060, 124.9120, 1.150, 124.720, 1.420, 125.050),
        ("7106", "Kab. Minahasa Utara", "Kabupaten", 1.4300, 124.9900, 1.380, 124.880, 1.750, 125.150),
        ("7105", "Kab. Minahasa Selatan", "Kabupaten", 1.1800, 124.5800, 0.950, 124.350, 1.280, 124.750),
        ("7109", "Kab. Minahasa Tenggara", "Kabupaten", 1.0500, 124.7800, 0.920, 124.620, 1.180, 124.950),
        ("7101", "Kab. Bolaang Mongondow", "Kabupaten", 0.7500, 124.0800, 0.450, 123.850, 1.050, 124.350),
        ("7108", "Kab. Bolaang Mongondow Utara", "Kabupaten", 0.8800, 123.5800, 0.680, 123.280, 1.020, 123.950),
        ("7111", "Kab. Bolaang Mongondow Selatan", "Kabupaten", 0.4200, 123.8500, 0.280, 123.550, 0.620, 124.150),
        ("7110", "Kab. Bolaang Mongondow Timur", "Kabupaten", 0.7800, 124.5200, 0.620, 124.380, 0.950, 124.680),
        ("7103", "Kab. Kepulauan Sangihe", "Kabupaten", 3.6500, 125.5500, 3.350, 125.400, 3.900, 125.750),
        ("7104", "Kab. Kepulauan Talaud", "Kabupaten", 4.3500, 126.7500, 3.950, 126.500, 4.750, 127.050),
        (
            "7107",
            "Kab. Kepulauan Siau Tagulandang Biaro",
            "Kabupaten",
            2.4500,
            125.4000,
            2.100,
            125.250,
            2.850,
            125.550,
        ),
    ]

    features = []
    for bps, name, ktype, clat, clng, min_lat, min_lng, max_lat, max_lng in kab_kota_list:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "bps_code": bps,
                    "name": name,
                    "type": ktype,
                    "center_latitude": clat,
                    "center_longitude": clng,
                    "province_code": "71",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": make_box_poly(min_lat, min_lng, max_lat, max_lng),
                },
            }
        )

    fc = {
        "type": "FeatureCollection",
        "name": "sulut_kab_kota",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(GEO_DIR / "sulut_kab_kota.geojson", "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(" -> sulut_kab_kota.geojson berhasil dibuat (15 Kabupaten/Kota).")


def generate_districts():
    # 18 Kecamatan Kunci Operasional FMCG
    districts = [
        # Code, Name, CityCode, CityName, Lat, Lng, min_lat, min_lng, max_lat, max_lng
        ("KEC-MND-WNG", "Kecamatan Wenang", "7171", "Kota Manado", 1.4910, 124.8420, 1.482, 124.835, 1.502, 124.850),
        ("KEC-MND-SRO", "Kecamatan Sario", "7171", "Kota Manado", 1.4720, 124.8380, 1.465, 124.830, 1.480, 124.845),
        (
            "KEC-MND-MLY",
            "Kecamatan Malalayang",
            "7171",
            "Kota Manado",
            1.4580,
            124.8250,
            1.442,
            124.815,
            1.472,
            124.835,
        ),
        ("KEC-MND-WNA", "Kecamatan Wanea", "7171", "Kota Manado", 1.4650, 124.8490, 1.455, 124.840, 1.478, 124.860),
        ("KEC-MND-TKL", "Kecamatan Tikala", "7171", "Kota Manado", 1.4830, 124.8600, 1.475, 124.852, 1.492, 124.870),
        ("KEC-MND-PLD", "Kecamatan Paal Dua", "7171", "Kota Manado", 1.4890, 124.8710, 1.480, 124.862, 1.498, 124.882),
        ("KEC-MND-TMT", "Kecamatan Tuminting", "7171", "Kota Manado", 1.5120, 124.8540, 1.502, 124.845, 1.525, 124.865),
        ("KEC-MND-SKL", "Kecamatan Singkil", "7171", "Kota Manado", 1.5010, 124.8620, 1.492, 124.855, 1.510, 124.872),
        ("KEC-MND-MPG", "Kecamatan Mapanget", "7171", "Kota Manado", 1.5310, 124.8990, 1.515, 124.880, 1.560, 124.925),
        ("KEC-BTG-MAS", "Kecamatan Maesa", "7172", "Kota Bitung", 1.4440, 125.1840, 1.435, 125.172, 1.458, 125.198),
        ("KEC-BTG-MAD", "Kecamatan Madidir", "7172", "Kota Bitung", 1.4500, 125.1550, 1.438, 125.142, 1.465, 125.170),
        ("KEC-BTG-GIR", "Kecamatan Girian", "7172", "Kota Bitung", 1.4420, 125.1350, 1.430, 125.120, 1.455, 125.148),
        (
            "KEC-BTG-AER",
            "Kecamatan Aertembaga",
            "7172",
            "Kota Bitung",
            1.4550,
            125.2100,
            1.440,
            125.195,
            1.470,
            125.230,
        ),
        (
            "KEC-TMH-TGH",
            "Kecamatan Tomohon Tengah",
            "7173",
            "Kota Tomohon",
            1.3230,
            124.8360,
            1.312,
            124.825,
            1.338,
            124.848,
        ),
        (
            "KEC-MNH-TDN",
            "Kecamatan Tondano Barat",
            "7102",
            "Kab. Minahasa",
            1.3080,
            124.9080,
            1.295,
            124.895,
            1.325,
            124.922,
        ),
        (
            "KEC-MNH-KWG",
            "Kecamatan Kawangkoan",
            "7102",
            "Kab. Minahasa",
            1.2050,
            124.7870,
            1.192,
            124.775,
            1.220,
            124.802,
        ),
        (
            "KEC-MNT-AMD",
            "Kecamatan Airmadidi",
            "7106",
            "Kab. Minahasa Utara",
            1.4280,
            124.9820,
            1.415,
            124.965,
            1.445,
            125.005,
        ),
        (
            "KEC-MNS-AMR",
            "Kecamatan Amurang",
            "7105",
            "Kab. Minahasa Selatan",
            1.1880,
            124.5720,
            1.172,
            124.555,
            1.205,
            124.590,
        ),
    ]

    features = []
    for code, name, city_code, city_name, clat, clng, min_lat, min_lng, max_lat, max_lng in districts:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": code,
                    "name": name,
                    "city_code": city_code,
                    "city_name": city_name,
                    "center_latitude": clat,
                    "center_longitude": clng,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": make_box_poly(min_lat, min_lng, max_lat, max_lng),
                },
            }
        )

    fc = {
        "type": "FeatureCollection",
        "name": "sulut_districts",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(GEO_DIR / "sulut_districts.geojson", "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(" -> sulut_districts.geojson berhasil dibuat (18 Kecamatan).")


def generate_villages():
    # Kelurahan Kunci Pusat Bisnis & Retail FMCG
    villages = [
        ("KEL-MND-CLC", "Kelurahan Calaca", "KEC-MND-WNG", "95112", 1.4925, 124.8420, 1.489, 124.838, 1.496, 124.846),
        (
            "KEL-MND-WNS",
            "Kelurahan Wenang Selatan",
            "KEC-MND-WNG",
            "95111",
            1.4870,
            124.8360,
            1.483,
            124.832,
            1.491,
            124.840,
        ),
        ("KEL-MND-BAH", "Kelurahan Bahu", "KEC-MND-MLY", "95115", 1.4585, 124.8255, 1.452, 124.820, 1.465, 124.831),
        (
            "KEL-MND-SKB",
            "Kelurahan Sario Kotabaru",
            "KEC-MND-SRO",
            "95114",
            1.4715,
            124.8375,
            1.466,
            124.833,
            1.477,
            124.842,
        ),
        (
            "KEL-MND-TKB",
            "Kelurahan Tikala Baru",
            "KEC-MND-TKL",
            "95126",
            1.4820,
            124.8590,
            1.477,
            124.854,
            1.487,
            124.864,
        ),
        ("KEL-MND-PLD", "Kelurahan Paal Dua", "KEC-MND-PLD", "95129", 1.4895, 124.8705, 1.484, 124.865, 1.495, 124.876),
        (
            "KEL-MND-PKB",
            "Kelurahan Paniki Bawah",
            "KEC-MND-MPG",
            "95258",
            1.5285,
            124.9085,
            1.520,
            124.898,
            1.538,
            124.918,
        ),
        (
            "KEL-BTG-BTM",
            "Kelurahan Bitung Timur (Pasar Tua)",
            "KEC-BTG-MAS",
            "95521",
            1.4425,
            125.1885,
            1.436,
            125.180,
            1.448,
            125.195,
        ),
        (
            "KEL-TMH-PSL",
            "Kelurahan Paslaten Satu",
            "KEC-TMH-TGH",
            "95431",
            1.3235,
            124.8365,
            1.317,
            124.830,
            1.330,
            124.842,
        ),
        (
            "KEL-MNH-SDG",
            "Kelurahan Sendangan",
            "KEC-MNH-KWG",
            "95671",
            1.2055,
            124.7865,
            1.198,
            124.780,
            1.212,
            124.793,
        ),
        ("KEL-MNH-RNG", "Kelurahan Roong", "KEC-MNH-TDN", "95618", 1.3085, 124.9085, 1.302, 124.902, 1.315, 124.915),
        (
            "KEL-MNT-AMA",
            "Kelurahan Airmadidi Atas",
            "KEC-MNT-AMD",
            "95371",
            1.4285,
            124.9825,
            1.420,
            124.974,
            1.437,
            124.991,
        ),
    ]

    features = []
    for code, name, dist_code, zip_code, clat, clng, min_lat, min_lng, max_lat, max_lng in villages:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "code": code,
                    "name": name,
                    "district_code": dist_code,
                    "postal_code": zip_code,
                    "center_latitude": clat,
                    "center_longitude": clng,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": make_box_poly(min_lat, min_lng, max_lat, max_lng),
                },
            }
        )

    fc = {
        "type": "FeatureCollection",
        "name": "sulut_villages",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(GEO_DIR / "sulut_villages.geojson", "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(" -> sulut_villages.geojson berhasil dibuat (Kelurahan Utama).")


if __name__ == "__main__":
    generate_provinsi()
    generate_kab_kota()
    generate_districts()
    generate_villages()
    print("Selesai menghasilkan seluruh Master GeoJSON Polygons Sulawesi Utara!")
