#!/usr/bin/env python3
"""odoo_snapshot.py - potret READ-ONLY sebuah instance Odoo (XML-RPC), untuk diagnosis jarak jauh.

Hanya memakai pustaka standar Python 3. Tidak ada panggilan tulis (hanya search_count/search_read/fields_get).
Kata sandi diminta lewat prompt tersembunyi (getpass); tidak disimpan, tidak dicetak, tidak dikirim ke mana pun
selain ke server Odoo yang Anda tunjuk. Variabel lingkungan ODOO_PASSWORD hanya untuk uji otomatis.
Keluaran berisi data bisnis (jumlah, contoh baris, nama menu), BUKAN kata sandi atau token. NPWP/VAT disamarkan.

Contoh:
  python3 scripts/ops/odoo_snapshot.py --url https://odooca-fmcg-demo.up.railway.app --db railway --user admin --out snapshot.md
Proyek lain: ganti --url/--db, dan isi --expect-modules / --extra-models / --menu-root sesuai proyek.
"""

import argparse
import collections
import datetime
import getpass
import json
import os
import socket
import sys
import xmlrpc.client

DEFAULT_EXPECT = (
    "id_base,id_ui,id_ui_shell,id_ui_form,l10n_id,l10n_id_efaktur_coretax,sale_management,sale_stock,purchase,stock,"
    "stock_account,account,product_expiry,stock_picking_batch,fleet,hr,hr_attendance,hr_holidays,mis_builder,"
    "account_financial_report,queue_job,fastapi,sale_financial_risk,account_credit_control"
)
DEFAULT_MODELS = (
    "res.partner,product.template,product.product,uom.uom,product.category,product.pricelist,id.principal,id.brand,"
    "id.sub.brand,id.channel,id.tier,id.coverage.area,id.fleet.type,id.city,id.district,id.subdistrict,hr.employee,"
    "hr.department,hr.job,fleet.vehicle,stock.warehouse,stock.location,stock.picking,stock.lot,sale.order,"
    "sale.order.line,purchase.order,account.move,account.payment,res.users"
)
LIMIT = 20000


class Odoo:
    def __init__(self, url, db, user, password, timeout):
        socket.setdefaulttimeout(timeout)
        self.url, self.db, self.user, self.password = url.rstrip("/"), db, user, password
        try:
            self.common = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/common", allow_none=True)
            self.version_info = self.common.version()
            self.uid = self.common.authenticate(db, user, password, {})
        except xmlrpc.client.Fault as e:
            first = str(e.faultString).strip().splitlines()[-1][:160] if e.faultString else str(e)[:160]
            raise SystemExit(f"Server menolak permintaan (kemungkinan nama database '{db}' salah): {first}") from None
        except (OSError, xmlrpc.client.ProtocolError) as e:
            raise SystemExit(f"Tidak bisa terhubung ke {self.url}: {type(e).__name__}: {str(e)[:120]}") from None
        if not self.uid:
            raise SystemExit("Autentikasi GAGAL (login/sandi/database salah). Tidak ada data diambil.")
        self.models = xmlrpc.client.ServerProxy(self.url + "/xmlrpc/2/object", allow_none=True)
        self._fields = {}
        self._exists = {}

    def call(self, model, method, args=None, kw=None):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, args or [], kw or {})

    def exists(self, model):
        if model not in self._exists:
            self._exists[model] = bool(self.call("ir.model", "search_count", [[("model", "=", model)]]))
        return self._exists[model]

    def fields(self, model):
        if model not in self._fields:
            self._fields[model] = self.call(
                model, "fields_get", [], {"attributes": ["type", "string", "relation", "store"]}
            )
        return self._fields[model]

    def count(self, model, domain=None):
        return self.call(model, "search_count", [domain or []])

    def rows(self, model, domain=None, fields=None, limit=LIMIT, order=None):
        kw = {"fields": fields or [], "limit": limit}
        if order:
            kw["order"] = order
        return self.call(model, "search_read", [domain or []], kw)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |")
    return out


def mask_vat(v):
    return v if not v else ("*" * max(len(v) - 4, 0)) + v[-4:]


def label(v):
    return v[1] if isinstance(v, (list, tuple)) and len(v) == 2 else v


def dist(o, model, field, domain=None, top=8):
    fl = o.fields(model)
    if field not in fl:
        return f"(field `{field}` TIDAK ADA di {model})"
    rows = o.rows(model, domain, [field])
    c = collections.Counter(label(r[field]) or "(kosong)" for r in rows)
    note = " (terpotong)" if len(rows) >= LIMIT else ""
    return ", ".join(f"{k}: {v}" for k, v in c.most_common(top)) + note


def fill(o, model, fields, domain=None):
    """Persentase terisi per field; menandai field yang tidak ada di model."""
    fl = o.fields(model)
    total = o.count(model, domain)
    rows = []
    for f in fields:
        if f not in fl:
            rows.append((f, "FIELD TIDAK ADA", "-"))
            continue
        t = fl[f]["type"]
        dom = list(domain or [])
        dom.append((f, "!=", 0) if t in ("float", "integer", "monetary") else (f, "!=", False))
        try:
            n = o.count(model, dom)
            rows.append((f, f"{n}/{total}", f"{(100 * n / total):.0f}%" if total else "-"))
        except Exception as e:  # noqa: BLE001
            rows.append((f, "tidak bisa dihitung", str(e)[:50]))
    return md_table(["field", "terisi", "%"], rows)


def section(title, fn, o, out, js):
    out.append(f"\n## {title}\n")
    try:
        lines, data = fn(o)
        out.extend(lines)
        if data is not None:
            js[title] = data
    except Exception as e:  # noqa: BLE001
        out.append(f"_(bagian gagal: {type(e).__name__}: {str(e)[:300]})_")
        js[title] = {"error": str(e)[:300]}


def s_server(o):
    v = o.version_info
    return (
        [
            f"- server: `{v.get('server_version')}` | protokol {v.get('protocol_version')} | url `{o.url}` | db `{o.db}` | login `{o.user}` (uid {o.uid})",
            f"- waktu snapshot (lokal): {datetime.datetime.now().isoformat(timespec='seconds')}",
        ],
        v,
    )


def s_modules(o, expect):
    mods = o.rows("ir.module.module", [], ["name", "state", "latest_version", "application", "shortdesc"])
    by = collections.Counter(m["state"] for m in mods)
    inst = sorted(m["name"] for m in mods if m["state"] == "installed")
    apps = sorted(f"{m['shortdesc']} ({m['name']})" for m in mods if m["state"] == "installed" and m["application"])
    exp = [x.strip() for x in expect.split(",") if x.strip()]
    missing = [x for x in exp if x not in inst]
    present = {m["name"]: m for m in mods}
    lines = [
        f"- status: {dict(by)}",
        f"- TERINSTAL ({len(inst)}): " + ", ".join(inst),
        "- APLIKASI (tile di app switcher) terinstal: " + ("; ".join(apps) or "(tidak ada)"),
        f"- DIHARAPKAN tetapi BELUM terinstal ({len(missing)}): "
        + (
            ", ".join(f"`{x}`[{present[x]['state'] if x in present else 'tidak ada di addons_path'}]" for x in missing)
            or "(tidak ada)"
        ),
    ]
    for name in ("id_base", "id_ui", "id_ui_shell", "id_ui_form"):
        if name in present:
            lines.append(f"- `{name}`: state={present[name]['state']} versi={present[name]['latest_version']}")
    return lines, {"by_state": dict(by), "installed": inst, "missing": missing}


def s_company(o):
    lines = []
    comp = o.rows(
        "res.company",
        [],
        ["name", "country_id", "currency_id", "vat", "chart_template"]
        if "chart_template" in o.fields("res.company")
        else ["name", "country_id", "currency_id", "vat"],
    )
    for c in comp:
        lines.append(
            f"- perusahaan: **{c['name']}** | negara: {label(c['country_id'])} | mata uang: {label(c['currency_id'])} | chart: {c.get('chart_template')} | vat: {mask_vat(c.get('vat'))}"
        )
    langs = o.rows("res.lang", [("active", "=", True)], ["code", "name"], limit=50)
    lines.append("- bahasa AKTIF: " + ", ".join(f"{lg['code']}" for lg in langs))
    u = o.rows("res.users", [("id", "=", o.uid)], ["lang", "tz"])[0]
    lines.append(f"- bahasa & zona waktu user ini: lang=`{u['lang']}` tz=`{u['tz']}`")
    prm = o.rows("ir.config_parameter", [("key", "in", ["web.base.url", "web.base.url.freeze"])], ["key", "value"])
    lines.append("- parameter: " + ", ".join(f"{p['key']}={p['value']}" for p in prm))
    return lines, {"langs": [lg["code"] for lg in langs]}


def s_accounting(o):
    if not o.exists("account.account"):
        return ["_(modul account tidak terinstal)_"], None
    lines = [f"- akun: {o.count('account.account')} | jurnal: {o.count('account.journal')}"]
    taxes = o.rows("account.tax", [], ["name", "amount", "type_tax_use", "active"], limit=40)
    lines.append("- pajak (maks 40):")
    lines += md_table(
        ["nama", "persen", "jenis", "aktif"], [(t["name"], t["amount"], t["type_tax_use"], t["active"]) for t in taxes]
    )
    return lines, {"accounts": o.count("account.account"), "taxes": len(taxes)}


def s_menus(o, root_kw):
    menus = o.call(
        "ir.ui.menu",
        "search_read",
        [[]],
        {
            "fields": ["name", "parent_id", "sequence", "action", "web_icon"],
            "limit": 5000,
            "order": "sequence, id",
            "context": {"active_test": True},
        },
    )
    kids = collections.defaultdict(list)
    for m in menus:
        kids[m["parent_id"][0] if m["parent_id"] else 0].append(m)
    roots = kids[0]
    lines = [f"- total menu: {len(menus)} | menu tingkat atas (muncul di app switcher): {len(roots)}"]
    lines += md_table(
        ["menu tingkat atas", "jumlah anak langsung", "ikon", "aksi"],
        [(m["name"], len(kids[m["id"]]), "ya" if m["web_icon"] else "TIDAK", (m["action"] or "")[:40]) for m in roots],
    )

    def walk(m, depth, acc):
        act = f" -> {m['action']}" if m["action"] else ""
        acc.append("  " * depth + f"- {m['name']}{act}")
        if depth < 4:
            for ch in kids[m["id"]]:
                walk(ch, depth + 1, acc)

    for m in roots:
        if root_kw and root_kw.lower() in m["name"].lower():
            acc = []
            walk(m, 0, acc)
            lines += ["", f"### Pohon menu `{m['name']}`:"] + acc
    return lines, {"roots": [m["name"] for m in roots]}


def s_models(o, models):
    rows = []
    for m in [x.strip() for x in models.split(",") if x.strip()]:
        if o.exists(m):
            try:
                rows.append((m, o.count(m)))
            except Exception as e:  # noqa: BLE001
                rows.append((m, f"err {str(e)[:40]}"))
        else:
            rows.append((m, "MODEL TIDAK ADA"))
    return md_table(["model", "jumlah"], rows), dict(rows)


def s_partners(o, sample):
    if not o.exists("res.partner"):
        return ["_(tidak ada)_"], None
    fl = o.fields("res.partner")
    dom = (
        [("ref", "=like", "CUST-%")]
        if o.count("res.partner", [("ref", "=like", "CUST-%")])
        else ([("customer_rank", ">", 0)] if "customer_rank" in fl else [])
    )
    n = o.count("res.partner", dom)
    lines = [
        f"- outlet/customer (domain `{dom}`): **{n}**",
        f"- per channel: {dist(o, 'res.partner', 'channel_id', dom)}",
        f"- per tier: {dist(o, 'res.partner', 'tier_id', dom)}",
        f"- per kecamatan: {dist(o, 'res.partner', 'district_id', dom)}",
        f"- per kota (city): {dist(o, 'res.partner', 'city', dom)}",
        f"- per provinsi: {dist(o, 'res.partner', 'state_id', dom)}",
        f"- per negara: {dist(o, 'res.partner', 'country_id', dom)}",
        "",
        "Kelengkapan field pada outlet:",
    ]
    lines += fill(
        o,
        "res.partner",
        [
            "street",
            "city",
            "state_id",
            "country_id",
            "zip",
            "vat",
            "partner_latitude",
            "partner_longitude",
            "property_payment_term_id",
            "user_id",
            "credit_limit",
            "ref",
            "channel_id",
            "tier_id",
            "coverage_area_id",
            "district_id",
            "subdistrict_id",
            "category_id",
            "pic_name",
        ],
        dom,
    )
    want = [
        f
        for f in [
            "ref",
            "name",
            "street",
            "city",
            "state_id",
            "country_id",
            "channel_id",
            "tier_id",
            "district_id",
            "subdistrict_id",
            "credit_limit",
            "credit_mode",
            "property_payment_term_id",
            "user_id",
            "partner_latitude",
            "partner_longitude",
            "vat",
        ]
        if f in fl
    ]
    lines += ["", f"Contoh {sample} outlet pertama (VAT disamarkan):"]
    for r in o.rows("res.partner", dom, want, limit=sample, order="id"):
        r = dict(r)
        r["vat"] = mask_vat(r.get("vat"))
        lines.append("- " + json.dumps({k: label(v) for k, v in r.items() if k != "id"}, ensure_ascii=False))
    return lines, {"outlets": n}


def s_products(o, sample):
    if not o.exists("product.template"):
        return ["_(tidak ada)_"], None
    fl = o.fields("product.template")
    dom = [("default_code", "!=", False)]
    n = o.count("product.template", dom)
    lines = [
        f"- produk ber-kode: **{n}** dari {o.count('product.template')} template",
        f"- per principal: {dist(o, 'product.template', 'principal_id', dom)}",
        f"- per brand (top): {dist(o, 'product.template', 'brand_id', dom, 6)}",
        f"- per divisi: {dist(o, 'product.template', 'fmcg_category', dom)}",
        f"- per UoM: {dist(o, 'product.template', 'uom_id', dom)}",
        f"- per tipe: {dist(o, 'product.template', 'type', dom)}",
        "",
        "Kelengkapan field pada produk:",
    ]
    lines += fill(
        o,
        "product.template",
        [
            "principal_id",
            "brand_id",
            "sub_brand_id",
            "fmcg_category",
            "inner_qty",
            "carton_qty",
            "barcode",
            "list_price",
            "standard_price",
            "weight",
            "volume",
            "is_storable",
            "uom_po_id",
            "taxes_id",
            "categ_id",
        ],
        dom,
    )
    if o.exists("uom.uom"):
        u = o.rows("uom.uom", [], ["name"], limit=60)
        lines.append(
            "- UoM yang ada: "
            + ", ".join(sorted(x["name"] if isinstance(x["name"], str) else str(x["name"]) for x in u))
        )
    for m in ("product.uom", "product.packaging"):
        if o.exists(m):
            lines.append(f"- model kemasan `{m}`: {o.count(m)} baris")
    want = [
        f
        for f in [
            "default_code",
            "name",
            "principal_id",
            "brand_id",
            "fmcg_category",
            "uom_id",
            "inner_qty",
            "carton_qty",
            "list_price",
            "categ_id",
            "type",
        ]
        if f in fl
    ]
    lines += ["", f"Contoh {sample} produk pertama:"]
    for r in o.rows("product.template", dom, want, limit=sample, order="id"):
        lines.append("- " + json.dumps({k: label(v) for k, v in r.items() if k != "id"}, ensure_ascii=False))
    return lines, {"products": n}


def s_users(o):
    fl = o.fields("res.users")
    gf = "group_ids" if "group_ids" in fl else ("groups_id" if "groups_id" in fl else None)
    rows = o.rows("res.users", [], ["login", "name", "active", "lang", "share"] + ([gf] if gf else []), limit=200)
    lines = [f"- jumlah user: {len(rows)} (internal: {sum(1 for r in rows if not r['share'])})"]
    lines += md_table(
        ["login", "nama", "aktif", "lang", "internal", "jml grup"],
        [
            (r["login"], r["name"], r["active"], r["lang"], not r["share"], len(r.get(gf) or []) if gf else "?")
            for r in rows[:30]
        ],
    )
    return lines, {"users": len(rows)}


def s_hr_fleet(o):
    lines = []
    if o.exists("hr.employee"):
        lines.append(
            f"- karyawan: {o.count('hr.employee')} | per departemen: {dist(o, 'hr.employee', 'department_id')} | per jabatan: {dist(o, 'hr.employee', 'job_id', None, 6)}"
        )
    else:
        lines.append("- modul HR (hr.employee) TIDAK terinstal")
    if o.exists("fleet.vehicle"):
        lines.append(
            f"- kendaraan (fleet.vehicle): {o.count('fleet.vehicle')} | per model: {dist(o, 'fleet.vehicle', 'model_id', None, 6)}"
        )
    else:
        lines.append("- modul Fleet (fleet.vehicle) TIDAK terinstal")
    if o.exists("stock.warehouse"):
        wh = o.rows("stock.warehouse", [], ["name", "code"])
        lines.append(
            "- gudang: "
            + ", ".join(f"{w['name']}[{w['code']}]" for w in wh)
            + f" | lokasi internal: {o.count('stock.location', [('usage', '=', 'internal')])}"
        )
    else:
        lines.append("- modul Inventory (stock.warehouse) TIDAK terinstal")
    return lines, None


def s_transactions(o):
    lines = []
    for model, df, af in (
        ("sale.order", "date_order", "amount_untaxed"),
        ("purchase.order", "date_order", "amount_untaxed"),
        ("account.move", "date", "amount_untaxed"),
    ):
        if not o.exists(model):
            lines.append(f"- `{model}`: model TIDAK ada")
            continue
        fl = o.fields(model)
        rows = o.rows(model, [], [f for f in (df, af, "state", "move_type") if f in fl], limit=LIMIT)
        if not rows:
            lines.append(f"- `{model}`: 0 baris")
            continue
        st = collections.Counter(r.get("state") for r in rows)
        mt = collections.Counter(r.get("move_type") for r in rows) if "move_type" in fl else None
        dates = sorted(str(r[df])[:10] for r in rows if r.get(df))
        per_month = collections.defaultdict(float)
        for r in rows:
            if r.get(df):
                per_month[str(r[df])[:7]] += r.get(af) or 0
        lines.append(
            f"- `{model}`: {len(rows)} baris | state {dict(st)}"
            + (f" | move_type {dict(mt)}" if mt else "")
            + (f" | tanggal {dates[0]}..{dates[-1]}" if dates else "")
        )
        if per_month:
            lines.append(
                "  - total per bulan (" + af + "): " + ", ".join(f"{k}: {v:,.0f}" for k, v in sorted(per_month.items()))
            )
    return lines, None


def main():
    ap = argparse.ArgumentParser(description="Potret read-only instance Odoo via XML-RPC")
    ap.add_argument("--url", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--out", help="tulis laporan Markdown ke berkas ini (selain layar)")
    ap.add_argument("--json", help="tulis data terstruktur ke berkas JSON ini")
    ap.add_argument("--expect-modules", default=DEFAULT_EXPECT)
    ap.add_argument("--extra-models", default="")
    ap.add_argument("--menu-root", default="FMCG", help="nama (sebagian) menu tingkat atas yang diuraikan pohonnya")
    ap.add_argument("--sample", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    pw = os.environ.get("ODOO_PASSWORD") or getpass.getpass(f"Kata sandi Odoo untuk '{a.user}' (tidak ditampilkan): ")
    o = Odoo(a.url, a.db, a.user, pw, a.timeout)
    pw = None
    out, js = [f"# Snapshot Odoo - {a.url} (db {a.db})"], {}
    models = DEFAULT_MODELS + ("," + a.extra_models if a.extra_models else "")
    section("1. Server", s_server, o, out, js)
    section("2. Modul", lambda x: s_modules(x, a.expect_modules), o, out, js)
    section("3. Perusahaan, bahasa, parameter", s_company, o, out, js)
    section("4. Akuntansi", s_accounting, o, out, js)
    section("5. Menu", lambda x: s_menus(x, a.menu_root), o, out, js)
    section("6. Jumlah data per model", lambda x: s_models(x, models), o, out, js)
    section("7. Outlet / customer", lambda x: s_partners(x, a.sample), o, out, js)
    section("8. Produk", lambda x: s_products(x, a.sample), o, out, js)
    section("9. User", s_users, o, out, js)
    section("10. HR, armada, gudang", s_hr_fleet, o, out, js)
    section("11. Transaksi", s_transactions, o, out, js)
    out += [
        "\n## 12. Langkah manual tambahan (tidak dijalankan skrip ini)\n",
        '- Log boot `[init]` dan seed: `railway logs --service <nama-service> | grep -E "\\[init\\]|seed|ERROR|Traceback"` (tempel baris yang relevan).',
        "- Penanda init di DB (butuh akses psql): `railway connect Postgres` lalu `select * from id_meta.marks order by at;` dan `select * from id_meta.reset_log;`.",
    ]
    text = "\n".join(out)
    print(text)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
        print(f"\n[ditulis ke {a.out}, {len(text)} karakter]", file=sys.stderr)
    if a.json:
        json.dump(js, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
