#!/usr/bin/env python3
"""Generator Master Data Wilayah Administrasi Sulawesi Utara (Provinsi 71).

Pengganti ``generate_sulut_geojson.py`` lama. Skrip lama membuat poligon berupa
kotak (bounding box) dari angka yang ditulis manual, sehingga tidak mewakili batas
wilayah sebenarnya. Skrip ini mengambil data terbuka lalu menyusunnya per level:

    Provinsi (1) -> Kabupaten/Kota (15) -> Kecamatan (171) -> Desa/Kelurahan (1.839)

Sumber data (semuanya berlisensi MIT, lihat data/master/SOURCES.csv):
    S1  cahyadsn/wilayah             kode + nama wilayah (Kepmendagri 300.2.2-2138/2025)
    S2  cahyadsn/wilayah_kodepos     kode pos per desa/kelurahan
    S3  cahyadsn/wilayah_boundaries  poligon (disederhanakan) + titik sentral (centroid)

Keluaran:
    data/master/sulut_provinsi.csv, sulut_kab_kota.csv, sulut_kecamatan.csv,
                sulut_desa_kelurahan.csv   -> atribut + kode + kode pos + lat/lng
    data/master/sulut_wilayah_semua_level.csv -> satu tabel hierarki (semua level)
    data/master/sulut_kodepos.csv             -> kode wilayah -> kode pos
    data/master/sulut_poligon_<level>.csv     -> poligon dalam WKT (EPSG:4326, lng lat)
    data/master/SOURCES.csv                   -> daftar sumber, URL, checksum, lisensi
    data/master/validation_report.{json,md}   -> hasil validasi
    data/geo/sulut_<level>.geojson            -> poligon dalam GeoJSON (lng, lat)

Pemakaian:
    pip install shapely
    python scripts/generate_sulut_master.py            # unduh (jika belum ada) + bangun
    python scripts/generate_sulut_master.py --refresh  # paksa unduh ulang sumber
    python scripts/generate_sulut_master.py --strict   # exit 1 jika ada temuan kritis
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict

try:
    import numpy as np
    import shapely
    from shapely.geometry import MultiPolygon, Point, Polygon, mapping
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    from shapely.validation import explain_validity, make_valid
except ImportError:  # pragma: no cover
    sys.exit("Butuh shapely>=2.0: pip install shapely")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
MASTER_DIR = ROOT / "data" / "master"
GEO_DIR = ROOT / "data" / "geo"

PROV = "71"
GH = "https://raw.githubusercontent.com/cahyadsn"
KEL_PARTS = ["71.%02d" % i for i in range(1, 12)] + ["71.71", "71.72", "71.73", "71.74"]

# Jumlah wilayah menurut tabel README cahyadsn/wilayah_boundaries (baris provinsi 71).
EXPECTED = {"provinsi": 1, "kabupaten": 11, "kota": 4, "kecamatan": 171,
            "kelurahan": 332, "desa": 1507}

LEVELS = ["provinsi", "kab_kota", "kecamatan", "desa_kelurahan"]
LEVEL_BY_SEGMENTS = {1: "provinsi", 2: "kab_kota", 3: "kecamatan", 4: "desa_kelurahan"}
GEOJSON_NAME = {"provinsi": "sulut_provinsi", "kab_kota": "sulut_kab_kota",
                "kecamatan": "sulut_districts", "desa_kelurahan": "sulut_villages"}

EARTH_R_KM = 6371.0088
OVERLAP_FLAG = 0.05        # tumpang tindih > 5% luas poligon terkecil dianggap temuan
CONTAIN_FLAG = 0.90        # < 90% luas anak berada di dalam induk -> 'batas_tidak_presisi'
CONTAIN_SEVERE = 0.50      # < 50% -> 'periksa_lokasi'
# Rentang koordinat Sulut: ~0.2-5.7 LU (Pulau Miangas, Talaud, di ~5.56 LU) dan 122.8-127.2 BT.
BBOX_LAT = (0.0, 6.0)
BBOX_LNG = (122.5, 128.0)


# --------------------------------------------------------------------------- sumber
def source_list():
    s = [
        dict(id="S1", level="semua", name="wilayah.sql", repo="cahyadsn/wilayah",
             url=f"{GH}/wilayah/master/db/wilayah.sql", local="wilayah/wilayah.sql",
             provides="kode wilayah, nama wilayah",
             reference="Kepmendagri No 300.2.2-2138 Tahun 2025 (menurut header file)"),
        dict(id="S2", level="desa_kelurahan", name="wilayah_kodepos.sql",
             repo="cahyadsn/wilayah_kodepos",
             url=f"{GH}/wilayah_kodepos/main/db/wilayah_kodepos.sql",
             local="wilayah_kodepos/wilayah_kodepos.sql",
             provides="kode pos 5 digit per desa/kelurahan",
             reference="Kepmendagri No 300.2.2-2138 Tahun 2025 (menurut README); asal data "
                       "kode pos primer tidak disebutkan repositori"),
    ]
    b = f"{GH}/wilayah_boundaries/main/db"
    s.append(dict(id="S3", level="kab_kota", name="wilayah_boundaries_kab_71.sql",
                  repo="cahyadsn/wilayah_boundaries", url=f"{b}/kab/wilayah_boundaries_kab_71.sql",
                  local="wilayah_boundaries/kab_71.sql",
                  provides="poligon (disederhanakan) + centroid kab/kota",
                  reference="README: Kepmendagri No 300.2.2-2430 Tahun 2025; asal geometri "
                            "primer tidak disebutkan repositori"))
    s.append(dict(id="S3", level="kecamatan", name="wilayah_boundaries_kec_71.sql",
                  repo="cahyadsn/wilayah_boundaries", url=f"{b}/kec/wilayah_boundaries_kec_71.sql",
                  local="wilayah_boundaries/kec_71.sql",
                  provides="poligon (disederhanakan) + centroid kecamatan", reference="idem"))
    for part in KEL_PARTS:
        s.append(dict(id="S3", level="desa_kelurahan", name=f"wilayah_boundaries_kel_{part}.sql",
                      repo="cahyadsn/wilayah_boundaries",
                      url=f"{b}/kel/71/wilayah_boundaries_kel_{part}.sql",
                      local=f"wilayah_boundaries/kel_{part}.sql",
                      provides=f"poligon + centroid desa/kelurahan ({part})", reference="idem"))
    return s


PROV_CANDIDATES = [5, 1, 2, 3, 4, 6, 7, 8]  # file prov berisi banyak provinsi; 71 ada di prov_5


def fetch(url: str, dest: pathlib.Path, refresh: bool) -> None:
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sulut-master-generator/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            dest.write_bytes(data)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"Gagal mengunduh {url}: {last}")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- parser
def unq(s: str) -> str:
    return s.replace("''", "'").replace("\\'", "'")


RE_WILAYAH = re.compile(r"^\s*\('(71(?:\.\d{2}){0,2}(?:\.\d{4})?)'\s*,\s*'((?:[^']|'')*)'\)")
RE_KODEPOS = re.compile(r"^\s*\('(71(?:\.\d{2}){0,2}(?:\.\d{4})?)'\s*,\s*(NULL|'(\d*)')\)")
RE_BOUND = re.compile(
    r"^\s*\('(71(?:\.\d{2}){0,2}(?:\.\d{4})?)'\s*,\s*'((?:[^']|'')*)'\s*,\s*"
    r"(-?[\d.eE+-]+|NULL)\s*,\s*(-?[\d.eE+-]+|NULL)\s*,\s*(NULL|'(\[.*\])')\s*(?:,\s*\d+\s*)?\)")


def parse_wilayah(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = RE_WILAYAH.match(line)
            if m:
                out[m.group(1)] = unq(m.group(2))
    return out


def parse_kodepos(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = RE_KODEPOS.match(line)
            if m:
                out[m.group(1)] = m.group(3) or ""
    return out


def parse_boundaries(path):
    """Kembalikan {kode: dict(nama, lat, lng, path)} untuk baris Sulut."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = RE_BOUND.match(line)
            if not m:
                continue
            kode, nama, lat, lng, _, p = m.groups()
            out[kode] = dict(
                nama=unq(nama),
                lat=None if lat == "NULL" else float(lat),
                lng=None if lng == "NULL" else float(lng),
                path=p,
            )
    return out


def _depth(a):
    d = 0
    while isinstance(a, list):
        d += 1
        a = a[0] if a else None
    return d


def build_geometry(path_json: str, notes: list):
    """Ubah array [lat,lng] (Polygon atau MultiPolygon) menjadi MultiPolygon shapely (lng,lat)."""
    arr = json.loads(path_json)
    d = _depth(arr)
    if d == 3:
        polys = [arr]
    elif d == 4:
        polys = arr
    else:
        notes.append(f"kedalaman path tak dikenal ({d})")
        return None
    built = []
    for poly in polys:
        rings = []
        for ring in poly:
            pts = []
            for lat, lng in ring:
                pt = (round(lng, 6), round(lat, 6))
                if not pts or pts[-1] != pt:
                    pts.append(pt)
            if len(pts) >= 2 and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) < 4:
                notes.append("ring degenerat dibuang")
                continue
            rings.append(pts)
        if not rings:
            continue
        built.append(Polygon(rings[0], rings[1:]))
    if not built:
        return None
    return MultiPolygon(built)


def polygons_of(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        out = []
        for part in g.geoms:
            out += polygons_of(part)
        return out
    return []


def normalize(g, repair: bool, notes: list):
    """Kembalikan (MultiPolygon|None, valid_di_sumber: bool).

    Geometri tidak valid di sumber umumnya "Nested shells": pulau kecil (<=0,01 km2) yang
    tertelan poligon utama setelah penyederhanaan. Perbaikan = union bagian-bagian poligon
    (bukan make_valid langsung, yang akan membuat lubang), self-intersection ditangani make_valid.
    """
    if g is None:
        return None, True
    valid_src = g.is_valid
    if not valid_src:
        notes.append("geometri tidak valid di sumber: " + explain_validity(g))
        if repair:
            parts = [p if p.is_valid else make_valid(p) for p in g.geoms]
            flat = []
            for p in parts:
                flat += polygons_of(p)
            # set_precision: koordinat hasil perbaikan dibulatkan ke grid 1e-6 derajat (~0,1 m) agar
            # tetap valid setelah ditulis 6 desimal ke WKT/GeoJSON (sliver yang runtuh dibuang).
            g = shapely.set_precision(unary_union(flat), 1e-6)
            notes.append("diperbaiki: union bagian poligon + pembulatan 1e-6")
    ps = polygons_of(g)
    if not ps:
        return None, valid_src
    return MultiPolygon([orient(p, 1.0) for p in ps]), valid_src  # RFC 7946: luar CCW, lubang CW


def area_km2(g) -> float:
    def f(a):
        out = np.empty_like(a, dtype=float)
        out[:, 0] = EARTH_R_KM * np.radians(a[:, 0])
        out[:, 1] = EARTH_R_KM * np.sin(np.radians(a[:, 1]))  # Lambert cylindrical equal-area
        return out

    return shapely.transform(g, f).area


# --------------------------------------------------------------------------- tulis
def fmt(x):
    return ("%.6f" % x).rstrip("0").rstrip(".")


def wkt(g) -> str:
    parts = []
    for p in g.geoms:
        rings = [list(p.exterior.coords)] + [list(i.coords) for i in p.interiors]
        parts.append("(" + ",".join("(" + ",".join(f"{fmt(x)} {fmt(y)}" for x, y in r) + ")"
                                    for r in rings) + ")")
    return "MULTIPOLYGON(" + ",".join(parts) + ")"


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def jenis_desa(kode: str) -> str:
    return {"1": "Kelurahan", "2": "Desa"}.get(kode.split(".")[3][0], "Tidak diketahui")


def jenis_kabkota(kode: str, nama: str) -> str:
    return "Kota" if int(kode.split(".")[1]) >= 71 else "Kabupaten"


def parent_of(kode: str):
    return kode.rsplit(".", 1)[0] if "." in kode else ""


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="unduh ulang semua sumber")
    ap.add_argument("--no-repair", action="store_true",
                    help="jangan perbaiki geometri tidak valid dari sumber (default: diperbaiki)")
    ap.add_argument("--strict", action="store_true", help="exit 1 jika ada temuan kritis")
    args = ap.parse_args()

    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    srcs = source_list()

    # prov: cari file yang memuat provinsi 71
    prov_src = None
    for n in PROV_CANDIDATES:
        url = f"{GH}/wilayah_boundaries/main/db/prov/wilayah_boundaries_prov_{n}.sql"
        dest = RAW_DIR / f"wilayah_boundaries/prov_{n}.sql"
        fetch(url, dest, args.refresh)
        if parse_boundaries(dest).get(PROV):
            prov_src = dict(id="S3", level="provinsi", name=f"wilayah_boundaries_prov_{n}.sql",
                            repo="cahyadsn/wilayah_boundaries", url=url,
                            local=f"wilayah_boundaries/prov_{n}.sql",
                            provides="poligon (disederhanakan) + centroid provinsi (file memuat banyak provinsi)",
                            reference="idem")
            break
        dest.unlink(missing_ok=True)
    if prov_src is None:
        sys.exit("Provinsi 71 tidak ditemukan di file boundaries prov.")
    srcs.insert(2, prov_src)

    print("Mengunduh/memeriksa sumber ...")
    for s in srcs:
        fetch(s["url"], RAW_DIR / s["local"], args.refresh)

    # ---- parse
    wilayah = parse_wilayah(RAW_DIR / "wilayah/wilayah.sql")
    kodepos = parse_kodepos(RAW_DIR / "wilayah_kodepos/wilayah_kodepos.sql")
    bnd = {}
    for s in srcs:
        if s["id"] == "S3":
            bnd.update(parse_boundaries(RAW_DIR / s["local"]))
    print(f" -> S1 {len(wilayah)} wilayah | S2 {len(kodepos)} kode pos | S3 {len(bnd)} poligon")

    # ---- bangun record
    recs = {}
    geom_notes = defaultdict(list)
    for kode in sorted(wilayah, key=lambda k: [int(p) for p in k.split(".")]):
        lvl = LEVEL_BY_SEGMENTS[len(kode.split("."))]
        nama = wilayah[kode]
        r = dict(kode=kode, level=lvl, nama=nama, induk=parent_of(kode),
                 kode_nodot=kode.replace(".", ""), kodepos=kodepos.get(kode, ""),
                 lat=None, lng=None, geom=None, nama_bnd=None, valid_src=True)
        if lvl == "kab_kota":
            r["jenis"] = jenis_kabkota(kode, nama)
        elif lvl == "desa_kelurahan":
            r["jenis"] = jenis_desa(kode)
        elif lvl == "provinsi":
            r["jenis"] = "Provinsi"
        else:
            r["jenis"] = "Kecamatan"
        b = bnd.get(kode)
        if b:
            r["nama_bnd"] = b["nama"]
            r["lat"], r["lng"] = b["lat"], b["lng"]
            if b["path"] and b["path"] != "NULL":
                g = build_geometry(b["path"], geom_notes[kode])
                r["geom"], r["valid_src"] = normalize(g, not args.no_repair, geom_notes[kode])
        recs[kode] = r

    by_level = {lvl: [r for r in recs.values() if r["level"] == lvl] for lvl in LEVELS}

    # ---- turunan geometri
    for r in recs.values():
        g = r["geom"]
        r["contain"] = None
        r["qa"] = []
        if g is None:
            r.update(rep_lat=None, rep_lng=None, luas=None, n_poly=0, n_pts=0, valid=None,
                     centroid_inside=None)
            r["qa"].append("tanpa_poligon")
            continue
        rp = g.representative_point()
        r["rep_lat"], r["rep_lng"] = rp.y, rp.x
        r["luas"] = area_km2(g)
        r["n_poly"] = len(g.geoms)
        r["n_pts"] = sum(len(p.exterior.coords) + sum(len(i.coords) for i in p.interiors)
                         for p in g.geoms)
        r["valid"] = g.is_valid
        r["centroid_inside"] = (g.covers(Point(r["lng"], r["lat"])) if r["lat"] is not None else None)
        if not r["valid_src"]:
            r["qa"].append("geometri_diperbaiki" if not args.no_repair else "geometri_tidak_valid")

    # ---- QA hierarki: berapa % luas poligon berada di dalam poligon induknya
    kec_geoms = [(r["kode"], r["geom"]) for r in by_level["kecamatan"] if r["geom"] is not None]
    kec_tree = STRtree([g for _, g in kec_geoms])
    for lvl in ["kab_kota", "kecamatan", "desa_kelurahan"]:
        for r in by_level[lvl]:
            par = recs.get(r["induk"])
            if r["geom"] is None or par is None or par["geom"] is None:
                continue
            c = r["geom"] if r["geom"].is_valid else make_valid(r["geom"])
            p = par["geom"] if par["geom"].is_valid else make_valid(par["geom"])
            r["contain"] = c.intersection(p).area / c.area if c.area else 0.0
            if r["contain"] < CONTAIN_SEVERE:
                r["qa"].append("periksa_lokasi")
                hit = [kec_geoms[i][0] for i in kec_tree.query(c.representative_point(),
                                                              predicate="intersects")]
                r["kec_lain"] = [k for k in hit if k != r["induk"]]
            elif r["contain"] < CONTAIN_FLAG:
                r["qa"].append("batas_tidak_presisi")
    for r in recs.values():
        r["qa_flag"] = ";".join(r["qa"]) if r["qa"] else "ok"

    SRC_KN, SRC_LL, SRC_POS, SRC_GEO = "S1", "S3", "S2", "S3"

    def r6(x):
        return "" if x is None else round(x, 6)

    def r3(x):
        return "" if x is None else round(x, 3)

    # ---- CSV atribut
    common_tail = ["lat_sentral", "lng_sentral", "centroid_sumber_di_dalam_poligon",
                   "lat_titik_dalam", "lng_titik_dalam", "luas_km2_approx",
                   "qa_persen_di_dalam_induk", "qa_flag", "src_kode_nama", "src_lat_lng"]

    def tail(r):
        ci = r.get("centroid_inside")
        pct = "" if r.get("contain") is None else round(100 * r["contain"], 1)
        return [r6(r["lat"]), r6(r["lng"]), "" if ci is None else str(ci).lower(),
                r6(r.get("rep_lat")), r6(r.get("rep_lng")), r3(r.get("luas")),
                pct, r["qa_flag"], SRC_KN, SRC_LL]

    write_csv(MASTER_DIR / "sulut_provinsi.csv",
              ["kode_kemendagri", "kode_nodot", "nama", "jenis"] + common_tail,
              [[r["kode"], r["kode_nodot"], r["nama"], r["jenis"]] + tail(r) for r in by_level["provinsi"]])

    write_csv(MASTER_DIR / "sulut_kab_kota.csv",
              ["kode_kemendagri", "kode_nodot", "nama", "nama_tanpa_prefix", "jenis", "kode_provinsi"]
              + common_tail,
              [[r["kode"], r["kode_nodot"], r["nama"],
                re.sub(r"^(Kabupaten|Kota)\s+", "", r["nama"]), r["jenis"], r["induk"]] + tail(r)
               for r in by_level["kab_kota"]])

    write_csv(MASTER_DIR / "sulut_kecamatan.csv",
              ["kode_kemendagri", "kode_nodot", "nama", "kode_kab_kota", "nama_kab_kota",
               "jenis_kab_kota"] + common_tail,
              [[r["kode"], r["kode_nodot"], r["nama"], r["induk"], recs[r["induk"]]["nama"],
                recs[r["induk"]]["jenis"]] + tail(r) for r in by_level["kecamatan"]])

    def row_desa(r):
        kec = recs[r["induk"]]
        kab = recs[kec["induk"]]
        return [r["kode"], r["kode_nodot"], r["nama"], r["jenis"], r["kodepos"],
                kec["kode"], kec["nama"], kab["kode"], kab["nama"], kab["jenis"]] + tail(r) + [SRC_POS]

    write_csv(MASTER_DIR / "sulut_desa_kelurahan.csv",
              ["kode_kemendagri", "kode_nodot", "nama", "jenis", "kodepos", "kode_kecamatan",
               "nama_kecamatan", "kode_kab_kota", "nama_kab_kota", "jenis_kab_kota"]
              + common_tail + ["src_kodepos"],
              [row_desa(r) for r in by_level["desa_kelurahan"]])

    write_csv(MASTER_DIR / "sulut_wilayah_semua_level.csv",
              ["kode_kemendagri", "kode_nodot", "level", "jenis", "nama", "kode_induk", "kodepos",
               "lat_sentral", "lng_sentral", "src_kode_nama", "src_lat_lng", "src_kodepos"],
              [[r["kode"], r["kode_nodot"], r["level"], r["jenis"], r["nama"], r["induk"], r["kodepos"],
                r6(r["lat"]), r6(r["lng"]), SRC_KN, SRC_LL, SRC_POS if r["kodepos"] else ""]
               for r in recs.values()])

    write_csv(MASTER_DIR / "sulut_kodepos.csv",
              ["kode_kemendagri", "nama", "kodepos", "kode_kecamatan", "kode_kab_kota", "src_kodepos"],
              [[r["kode"], r["nama"], r["kodepos"], r["induk"], parent_of(r["induk"]), SRC_POS]
               for r in by_level["desa_kelurahan"]])

    # ---- poligon CSV + GeoJSON
    roundtrip_bad = []
    for lvl in LEVELS:
        rows, feats = [], []
        for r in by_level[lvl]:
            g = r["geom"]
            if g is None:
                continue
            w = wkt(g)
            if not shapely.from_wkt(w).is_valid:  # cek hasil tulis, bukan objek di memori
                roundtrip_bad.append(r["kode"])
            rows.append([r["kode"], r["nama"], "MultiPolygon", r["n_poly"], r["n_pts"],
                         str(r["valid_src"]).lower(), str(r["valid"]).lower(), r["qa_flag"],
                         SRC_GEO, w])
            props = {"code": r["kode"], "code_compact": r["kode_nodot"], "name": r["nama"],
                     "type": r["jenis"], "parent_code": r["induk"],
                     "center_latitude": r6(r["lat"]), "center_longitude": r6(r["lng"]),
                     "inside_latitude": r6(r["rep_lat"]), "inside_longitude": r6(r["rep_lng"]),
                     "area_km2_approx": r3(r["luas"]), "qa_flag": r["qa_flag"],
                     "source": "cahyadsn/wilayah_boundaries (S3)"}
            if lvl == "desa_kelurahan":
                kec = recs[r["induk"]]
                props.update(district_code=kec["kode"], district_name=kec["nama"],
                             city_code=kec["induk"], city_name=recs[kec["induk"]]["nama"],
                             postal_code=r["kodepos"])
            if lvl == "kecamatan":
                props.update(city_code=r["induk"], city_name=recs[r["induk"]]["nama"])
            if lvl == "kab_kota":
                props.update(province_code=PROV)
            feats.append({"type": "Feature", "properties": props,
                          "geometry": json.loads(json.dumps(mapping(g)))})
        write_csv(MASTER_DIR / f"sulut_poligon_{lvl}.csv",
                  ["kode_kemendagri", "nama", "geom_type", "jumlah_poligon", "jumlah_titik",
                   "geom_valid_di_sumber", "geom_valid_di_output", "qa_flag", "src_poligon",
                   "wkt_epsg4326_lng_lat"], rows)

        def rnd(c):
            if isinstance(c, (list, tuple)):
                return [rnd(x) for x in c]
            return round(c, 6)

        for ft in feats:
            ft["geometry"]["coordinates"] = rnd(ft["geometry"]["coordinates"])
        fc = {"type": "FeatureCollection", "name": GEOJSON_NAME[lvl], "features": feats}
        with open(GEO_DIR / f"{GEOJSON_NAME[lvl]}.geojson", "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
        print(f" -> {GEOJSON_NAME[lvl]}.geojson & sulut_poligon_{lvl}.csv: {len(feats)} fitur")

    # ---- SOURCES.csv
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    src_rows = []
    for s in srcs:
        p = RAW_DIR / s["local"]
        ts = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
        src_rows.append([s["id"], s["level"], s["name"], s["repo"], f"https://github.com/{s['repo']}",
                         s["url"], s["provides"], "MIT", s["reference"], p.stat().st_size,
                         sha256(p), ts])
    write_csv(MASTER_DIR / "SOURCES.csv",
              ["id", "level", "file", "repo", "repo_url", "file_url", "menyediakan", "lisensi",
               "rujukan_regulasi", "bytes", "sha256", "diunduh_utc"], src_rows)

    # ---- validasi
    report = validate(recs, by_level, geom_notes, bnd, wilayah, kodepos)
    if roundtrip_bad:
        report["temuan_kritis"].append(
            f"{len(roundtrip_bad)} poligon tidak valid setelah ditulis ke WKT (6 desimal): {roundtrip_bad[:5]}")
    report["dibuat_utc"] = now
    with open(MASTER_DIR / "validation_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(MASTER_DIR / "validation_report.md", "w", encoding="utf-8") as f:
        f.write(report_md(report))
    write_csv(MASTER_DIR / "validation_anomali.csv",
              ["kode_kemendagri", "level", "nama", "jenis_anomali", "keterangan"],
              sorted(report["anomali"], key=lambda a: (a[3], a[0])))
    print_summary(report)
    crit = report["temuan_kritis"]
    return 1 if (args.strict and crit) else 0


# --------------------------------------------------------------------------- validasi
def validate(recs, by_level, geom_notes, bnd, wilayah, kodepos):
    rep = {"ringkasan_jumlah": {}, "temuan_kritis": [], "peringatan": [], "info": {}}
    crit, warn = rep["temuan_kritis"], rep["peringatan"]

    # 1. jumlah
    cnt = Counter()
    for r in by_level["kab_kota"]:
        cnt[r["jenis"].lower()] += 1
    for r in by_level["desa_kelurahan"]:
        cnt[r["jenis"].lower()] += 1
    cnt["provinsi"] = len(by_level["provinsi"])
    cnt["kecamatan"] = len(by_level["kecamatan"])
    rep["ringkasan_jumlah"] = {k: {"hasil": cnt.get(k, 0), "diharapkan": v} for k, v in EXPECTED.items()}
    for k, v in EXPECTED.items():
        if cnt.get(k, 0) != v:
            crit.append(f"Jumlah {k}: {cnt.get(k, 0)} (diharapkan {v})")
    if cnt.get("tidak diketahui"):
        warn.append(f"{cnt['tidak diketahui']} desa/kelurahan berawalan kode selain 1/2")

    # 2. himpunan kode S1 vs S3
    missing_poly = sorted(k for k in wilayah if k not in bnd or recs[k]["geom"] is None)
    extra_poly = sorted(k for k in bnd if k not in wilayah)
    if missing_poly:
        crit.append(f"{len(missing_poly)} kode di S1 tanpa poligon di S3: {missing_poly[:10]}")
    if extra_poly:
        warn.append(f"{len(extra_poly)} kode poligon S3 tidak ada di S1: {extra_poly[:10]}")

    # 3. nama S1 vs S3
    mism = [(k, wilayah[k], bnd[k]["nama"]) for k in wilayah
            if k in bnd and wilayah[k].strip().casefold() != bnd[k]["nama"].strip().casefold()]
    rep["info"]["selisih_nama_S1_vs_S3"] = {"jumlah": len(mism), "contoh": mism[:15]}
    if mism:
        warn.append(f"{len(mism)} nama berbeda antara S1 dan S3 (S1 dipakai sebagai nama resmi)")

    # 4. kode pos
    desa = by_level["desa_kelurahan"]
    no_pos = [r["kode"] for r in desa if not r["kodepos"]]
    bad_fmt = [r["kode"] for r in desa if r["kodepos"] and not re.fullmatch(r"\d{5}", r["kodepos"])]
    outside = [(r["kode"], r["kodepos"]) for r in desa
               if r["kodepos"] and re.fullmatch(r"\d{5}", r["kodepos"]) and not r["kodepos"].startswith("95")]
    if no_pos:
        crit.append(f"{len(no_pos)} desa/kelurahan tanpa kode pos: {no_pos[:10]}")
    if bad_fmt:
        crit.append(f"{len(bad_fmt)} kode pos format salah: {bad_fmt[:10]}")
    if outside:
        warn.append(f"{len(outside)} kode pos tidak berawalan 95 (rentang Sulut): {outside[:10]}")
    rep["info"]["kodepos"] = {"desa_kelurahan_dengan_kodepos": len(desa) - len(no_pos),
                              "kodepos_unik": len({r['kodepos'] for r in desa if r['kodepos']}),
                              "kodepos_di_luar_95xxx": outside[:20]}
    multi = defaultdict(set)
    for r in desa:
        multi[r["induk"]].add(r["kodepos"])
    rep["info"]["kecamatan_dengan_>1_kodepos"] = sum(1 for v in multi.values() if len(v) > 1)

    # 5. geometri
    geom_info = {}
    for lvl in LEVELS:
        rs = by_level[lvl]
        have = [r for r in rs if r["geom"] is not None]
        invalid_src = [r["kode"] for r in have if not r["valid_src"]]
        invalid_out = [r["kode"] for r in have if not r["valid"]]
        outside_c = [r["kode"] for r in have if r["centroid_inside"] is False]
        lat_bad = [r["kode"] for r in have
                   if not (BBOX_LAT[0] <= r["geom"].bounds[1] and r["geom"].bounds[3] <= BBOX_LAT[1]
                           and BBOX_LNG[0] <= r["geom"].bounds[0] and r["geom"].bounds[2] <= BBOX_LNG[1])]
        geom_info[lvl] = {"fitur": len(rs), "dengan_poligon": len(have),
                          "tidak_valid_di_sumber": len(invalid_src),
                          "tidak_valid_di_output": len(invalid_out),
                          "centroid_sumber_di_luar_poligon": len(outside_c),
                          "bbox_di_luar_rentang_sulut": len(lat_bad),
                          "kode_tidak_valid_di_sumber": invalid_src[:20],
                          "contoh_centroid_luar": outside_c[:5]}
        if invalid_out:
            crit.append(f"{lvl}: {len(invalid_out)} geometri masih tidak valid di output: {invalid_out[:5]}")
        if invalid_src:
            warn.append(f"{lvl}: {len(invalid_src)} geometri tidak valid di sumber "
                        f"(nested shells/self-intersection; sudah diperbaiki di output kecuali --no-repair)")
        if outside_c:
            warn.append(f"{lvl}: {len(outside_c)} centroid sumber berada di luar poligonnya sendiri "
                        f"(pakai lat/lng_titik_dalam untuk titik yang pasti di dalam)")
        if lat_bad:
            crit.append(f"{lvl}: {len(lat_bad)} poligon di luar rentang koordinat Sulut: {lat_bad[:5]}")
    rep["info"]["geometri"] = geom_info
    rep["info"]["catatan_geometri_sumber"] = {k: v for k, v in geom_notes.items() if v}

    def vg(r):
        g = r["geom"]
        return g if g.is_valid else make_valid(g)

    # 6. containment + overlap + coverage
    containment, overlap, coverage = {}, {}, {}
    anomalies = []
    for lvl in ["kab_kota", "kecamatan", "desa_kelurahan"]:
        rs = [r for r in by_level[lvl] if r["contain"] is not None]
        ratios = [r["contain"] for r in rs]
        worst = sorted((r["contain"], r["kode"], r["nama"]) for r in rs)
        n_sev = sum(1 for x in ratios if x < CONTAIN_SEVERE)
        n_mid = sum(1 for x in ratios if CONTAIN_SEVERE <= x < CONTAIN_FLAG)
        containment[lvl] = {
            "diperiksa": len(ratios),
            "rata2_persen_luas_di_dalam_induk": round(100 * statistics.mean(ratios), 2) if ratios else None,
            "min_persen": round(100 * min(ratios), 2) if ratios else None,
            "batas_tidak_presisi_(50-90persen)": n_mid,
            "periksa_lokasi_(<50persen)": n_sev,
            "terburuk": [(round(100 * a, 1), b, c) for a, b, c in worst[:8]],
        }
        for r in rs:
            if r["contain"] < CONTAIN_SEVERE:
                lain = ",".join(r.get("kec_lain", [])) or "tidak ada kecamatan memuat titik dalam (kemungkinan pesisir)"
                anomalies.append([r["kode"], lvl, r["nama"], "periksa_lokasi",
                                  f"hanya {100 * r['contain']:.1f}% luas di dalam induk {r['induk']}; "
                                  f"titik dalam berada di: {lain}"])
        if n_sev:
            warn.append(f"{lvl}: {n_sev} poligon <{int(CONTAIN_SEVERE * 100)}% luasnya di dalam induk "
                        f"(qa_flag=periksa_lokasi; lihat validation_anomali.csv)")
        if n_mid:
            warn.append(f"{lvl}: {n_mid} poligon {int(CONTAIN_SEVERE * 100)}-{int(CONTAIN_FLAG * 100)}% "
                        f"luasnya di dalam induk (qa_flag=batas_tidak_presisi; akibat penyederhanaan)")
        groups = defaultdict(list)
        for r in by_level[lvl]:
            if r["geom"] is not None:
                groups[r["induk"]].append(r)
        # overlap antar saudara
        n_pairs = n_flag = 0
        top = []
        for par, items in groups.items():
            gs = [vg(r) for r in items]
            tree = STRtree(gs)
            for i, g in enumerate(gs):
                for j in tree.query(g, predicate="intersects"):
                    if j <= i:
                        continue
                    inter = g.intersection(gs[j]).area
                    small = min(g.area, gs[j].area)
                    if small and inter / small > 1e-4:
                        n_pairs += 1
                        ratio = inter / small
                        if ratio > OVERLAP_FLAG:
                            n_flag += 1
                            top.append((round(100 * ratio, 1), items[i]["kode"], items[j]["kode"]))
                            anomalies.append([items[i]["kode"], lvl, items[i]["nama"], "tumpang_tindih",
                                              f"{100 * ratio:.1f}% luas poligon terkecil tumpang tindih dengan "
                                              f"{items[j]['kode']} {items[j]['nama']}"])
        top.sort(reverse=True)
        overlap[lvl] = {"pasangan_saling_tindih_>0.01%": n_pairs,
                        f"pasangan_tindih_>{int(OVERLAP_FLAG * 100)}persen_luas_terkecil": n_flag,
                        "terbesar": top[:8]}
        # cakupan anak thd induk
        ratios_cov = []
        for par, items in groups.items():
            if par in recs and recs[par]["luas"]:
                ratios_cov.append(sum(r["luas"] for r in items) / recs[par]["luas"])
        coverage[lvl] = {"induk_diperiksa": len(ratios_cov),
                         "rasio_luas_anak_per_induk_min": round(min(ratios_cov), 3) if ratios_cov else None,
                         "median": round(statistics.median(ratios_cov), 3) if ratios_cov else None,
                         "max": round(max(ratios_cov), 3) if ratios_cov else None}
        if n_flag:
            warn.append(f"{lvl}: {n_flag} pasangan saudara tumpang tindih >{int(OVERLAP_FLAG * 100)}%")
    rep["anomali"] = anomalies
    rep["info"]["containment"] = containment
    rep["info"]["overlap_saudara"] = overlap
    rep["info"]["cakupan_luas"] = coverage

    prov = by_level["provinsi"][0]
    rep["info"]["luas_km2_approx"] = {
        "provinsi": round(prov["luas"], 1) if prov["luas"] else None,
        "jumlah_kab_kota_terhitung": round(sum(r["luas"] or 0 for r in by_level["kab_kota"]), 1),
        "catatan": "Luas dihitung dari poligon yang sudah disederhanakan; hanya untuk sanity check, "
                   "bukan angka resmi."}
    return rep


def report_md(rep) -> str:
    L = ["# Laporan Validasi Master Wilayah Sulawesi Utara", "", f"Dibuat: {rep['dibuat_utc']}", ""]
    L += ["## Jumlah wilayah", "", "| Jenis | Hasil | Diharapkan |", "|---|---:|---:|"]
    for k, v in rep["ringkasan_jumlah"].items():
        L.append(f"| {k} | {v['hasil']} | {v['diharapkan']} |")
    L += ["", "## Temuan kritis", ""]
    L += [f"- {x}" for x in rep["temuan_kritis"]] or ["- (tidak ada)"]
    L += ["", "## Peringatan", ""]
    L += [f"- {x}" for x in rep["peringatan"]] or ["- (tidak ada)"]
    L += ["", "## Detail", "", "```json", json.dumps(rep["info"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(L)


def print_summary(rep):
    print("\n=== RINGKASAN VALIDASI ===")
    for k, v in rep["ringkasan_jumlah"].items():
        print(f"  {k:10s} {v['hasil']:5d} / {v['diharapkan']}")
    print("Temuan kritis :", len(rep["temuan_kritis"]))
    for x in rep["temuan_kritis"]:
        print("   !", x)
    print("Peringatan    :", len(rep["peringatan"]))
    for x in rep["peringatan"]:
        print("   -", x)
    print(f"Anomali tercatat: {len(rep['anomali'])} (data/master/validation_anomali.csv)")
    print("Laporan lengkap: data/master/validation_report.md")


if __name__ == "__main__":
    sys.exit(main())
