#!/usr/bin/env python3
"""Runner Pembuktian Runtime Penuh Dataset Kanonikal FMCG pada Odoo 19 Disposable.

Membuktikan secara deterministik dari database kosong / disposable terisolasi:
1. Pemuatan penuh dataset kanonikal: 1.324 SO, 1.281 DO tervalidasi, 9 retur, 1.276 faktur Juli, 967 AR, 4 AP, 30 OPEX.
2. Cut-off waktu dua fase: Penutupan Juli 2026 (31 Juli EOD) vs Post-Transaksi 1 Agustus 2026 (48 DO & 48 Faktur).
3. Audit kepatuhan penuh terhadap Oracle Kanonikal Independen (bukan output loader) per SKU, kuantitas, nominal GL/COGS.
4. Deep state snapshot presisi tinggi (stock.quant, stock.move, stock.move.line, account.move, account.move.line, balances).
5. Zero-drift idempotensi pada replay Run 2.
6. Penolakan mutlak fallback default salesperson (Admin/Root).
7. Safety guard menolak database selain target disposable yang sah.
"""

from collections import defaultdict
import contextlib
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

try:
    REPO_ROOT = Path(__file__).resolve().parents[2]
except NameError:
    if Path("/opt/scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path("/opt")
    elif Path("scripts/load_canonical_perpetual.py").exists():
        REPO_ROOT = Path.cwd()
    else:
        REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/opt"))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REG_PATH = REPO_ROOT / "data" / "registers"
if not REG_PATH.exists() and Path("/opt/data/registers").exists():
    REG_PATH = Path("/opt/data/registers")

from scripts.load_canonical_perpetual import (  # noqa: E402
    CanonicalPerpetualAdapter,
    read_register_csv,
    verify_canonical_fingerprints,
)


def _safe_fields(model) -> dict:
    if model is None:
        return {}
    if hasattr(model, "_fields"):
        return model._fields
    return {}


def _iter_records(res) -> list:
    if not res:
        return []
    if isinstance(res, (list, tuple, set)):
        return list(res)
    if hasattr(res, "_ids"):
        return [res.browse(i) for i in res._ids]
    if hasattr(res, "ids"):
        return [res.browse(i) for i in res.ids]
    return [res]


def assert_disposable_database(env):
    """Safety guard ketat: menolak database selain target disposable yang sah.

    Aturan:
    1. Menolak mutlak substring kata terlarang (prod, production, live, railway, master, official, main).
    2. Wajib cocok dengan nama disposable yang diizinkan secara eksplisit.
    """
    cr = getattr(env, "cr", None)
    db_name = getattr(cr, "dbname", "") or ""

    # 1. Tolak mutlak indikator operasional / produksi
    forbidden = ["prod", "production", "live", "railway", "master", "official", "main"]
    for f in forbidden:
        if f in db_name.lower():
            raise RuntimeError(
                f"[SAFETY-ABORT] Target database '{db_name}' memuat kata terlarang '{f}'! "
                f"Eksekusi dibatalkan untuk melindungi integritas operasional."
            )

    # 2. Hanya izinkan nama database disposable yang sah
    exact_allowed = {"fmcg_full_disposable", "ci_db", "test_disposable"}
    is_pattern_allowed = (
        db_name.startswith("disposable_")
        or db_name.endswith("_disposable")
        or "_disposable_" in db_name
    )
    if db_name not in exact_allowed and not is_pattern_allowed:
        raise RuntimeError(
            f"[SAFETY-ABORT] Target database '{db_name}' bukan database disposable yang diizinkan! "
            f"Diperlukan database bertanda disposable eksplisit (misal: 'fmcg_full_disposable')."
        )
    return db_name


def introspect_runtime_environment(env) -> dict:
    """Mengumpulkan snapshot lengkap konfigurasi dan lingkungan eksekusi."""
    meta = {}
    cr = getattr(env, "cr", None)
    meta["database"] = getattr(cr, "dbname", "unknown")

    # Commit SHA
    commit_sha = os.environ.get("GITHUB_SHA")
    if not commit_sha:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                commit_sha = res.stdout.strip()
        except Exception:
            pass
    if not commit_sha:
        commit_sha = "unknown"
    meta["commit_sha"] = commit_sha

    # Image info & Run ID
    meta["image_info"] = os.environ.get("ODOO_IMAGE_DIGEST") or os.environ.get("ODOO_IMAGE") or "fmcg-odoo:ci"
    meta["github_run_id"] = os.environ.get("GITHUB_RUN_ID") or "local"

    # Modules with versions
    installed_modules = {}
    if "ir.module.module" in env:
        Module = env["ir.module.module"].sudo()
        mods = _iter_records(Module.search([("state", "=", "installed")]))
        for m in mods:
            installed_modules[m.name] = getattr(m, "installed_version", "installed") or "installed"
    meta["installed_modules_count"] = len(installed_modules)
    meta["installed_modules"] = installed_modules
    meta["fmcg_modules"] = {k: v for k, v in installed_modules.items() if k.startswith("id_")}

    # Company & Timezone
    comp = getattr(env, "company", None)
    meta["company_id"] = getattr(comp, "id", None)
    meta["company_name"] = getattr(comp, "name", "")
    user = getattr(env, "user", None)
    meta["user_timezone"] = getattr(user, "tz", None) or "Asia/Makassar"
    meta["business_timezone"] = "Asia/Makassar (WITA, UTC+8)"

    # Valuation configuration
    val_config = {}
    if "product.category" in env:
        Cat = env["product.category"].sudo()
        cats = _iter_records(Cat.search([]))
        for c in cats:
            c_name = getattr(c, "name", str(c.id))
            val_config[c_name] = {
                "property_cost_method": getattr(c, "property_cost_method", "standard"),
                "property_valuation": getattr(c, "property_valuation", "manual_periodic"),
            }
    meta["valuation_categories"] = val_config

    # Canonical dataset fingerprints
    meta["canonical_hashes"] = verify_canonical_fingerprints(REG_PATH)
    return meta


class FullDatasetCanonicalOracle:
    """Oracle independen yang menurunkan ekspektasi dinamis dari CSV register kanonikal."""

    def __init__(self, reg_path):
        self.reg_path = Path(reg_path)
        self.opening_rows = read_register_csv(self.reg_path / "initial_stock_20260701.csv")
        self.po_headers = read_register_csv(self.reg_path / "inbound_po_intransit_june_headers.csv")
        self.po_lines = read_register_csv(self.reg_path / "inbound_po_intransit_june_lines.csv")
        self.so_rows = read_register_csv(self.reg_path / "perpetual_sales_orders.csv")
        self.order_lines = read_register_csv(self.reg_path / "perpetual_order_lines.csv")
        self.deliveries = read_register_csv(self.reg_path / "perpetual_deliveries.csv")
        self.rejections = read_register_csv(self.reg_path / "perpetual_order_rejections.csv")
        self.invoices = read_register_csv(self.reg_path / "perpetual_invoices.csv")
        self.ar_collections = read_register_csv(self.reg_path / "perpetual_ar_collections.csv")
        self.ap_payments = read_register_csv(self.reg_path / "perpetual_ap_payments.csv")
        self.opex_payroll = read_register_csv(self.reg_path / "perpetual_opex_payroll.csv")

    def get_july_closing_expectations(self) -> dict:
        """Ekspektasi pada saat Cut-off 31 Juli 2026 akhir hari dihitung dinamis dari CSV."""
        tot_open_cartons = sum(int(r.get("qty_cartons_on_hand", 0)) for r in self.opening_rows)
        tot_open_units = sum(int(r.get("qty_units_on_hand", 0)) for r in self.opening_rows)

        tot_po_cartons = sum(int(r.get("qty_cartons", 0)) for r in self.po_lines)
        tot_po_units = sum(int(r.get("qty_cartons", 0)) * int(r.get("carton_qty", 1)) for r in self.po_lines)

        tot_rejections_cartons = sum(int(r.get("qty_cartons", 0)) for r in self.rejections)
        tot_rejections_units = sum(int(r.get("qty_cartons", 0)) * int(r.get("carton_qty", 1)) for r in self.rejections)

        do_date_map = {d["do_number"]: d["scheduled_delivery_date"] for d in self.deliveries}
        so_do_map = {d["so_number"]: d["do_number"] for d in self.deliveries}

        july_deliv_cartons = 0
        july_deliv_units = 0
        aug_deliv_cartons = 0
        aug_deliv_units = 0
        for ol in self.order_lines:
            so = ol["so_number"]
            do_num = so_do_map.get(so)
            do_date = do_date_map.get(do_num, "")
            qty_c = int(ol.get("qty_cartons", 0))
            qty_u = qty_c * int(ol.get("carton_qty", 1))
            if do_date <= "2026-07-31":
                july_deliv_cartons += qty_c
                july_deliv_units += qty_u
            else:
                aug_deliv_cartons += qty_c
                aug_deliv_units += qty_u

        physical_cartons_july = tot_open_cartons + tot_po_cartons - july_deliv_cartons
        reserved_cartons_july = aug_deliv_cartons
        available_cartons_july = physical_cartons_july - reserved_cartons_july

        physical_units_july = tot_open_units + tot_po_units - july_deliv_units
        reserved_units_july = aug_deliv_units
        available_units_july = physical_units_july - reserved_units_july

        # Invoices
        july_inv = [inv for inv in self.invoices if inv["date_invoice"] <= "2026-07-31"]
        aug_inv = [inv for inv in self.invoices if inv["date_invoice"] > "2026-07-31"]
        july_do = [do for do in self.deliveries if do["scheduled_delivery_date"] <= "2026-07-31"]
        aug_do = [do for do in self.deliveries if do["scheduled_delivery_date"] > "2026-07-31"]

        july_inv_dpp = sum(Decimal(i["dpp_amount"]) for i in july_inv)
        july_inv_ppn = sum(Decimal(i["ppn_11_amount"]) for i in july_inv)
        july_inv_total = sum(Decimal(i["total_invoice_with_ppn"]) for i in july_inv)

        aug_inv_dpp = sum(Decimal(i["dpp_amount"]) for i in aug_inv)
        aug_inv_ppn = sum(Decimal(i["ppn_11_amount"]) for i in aug_inv)
        aug_inv_total = sum(Decimal(i["total_invoice_with_ppn"]) for i in aug_inv)

        # COGS Nominal
        july_sos = [
            so for so in self.so_rows
            if do_date_map.get(so_do_map.get(so["so_number"], ""), "") <= "2026-07-31"
        ]
        july_cogs = sum(Decimal(str(round(float(so["cogs_dpp"]), 2))) for so in july_sos)
        aug_sos = [
            so for so in self.so_rows
            if do_date_map.get(so_do_map.get(so["so_number"], ""), "") > "2026-07-31"
        ]
        aug_cogs = sum(Decimal(str(round(float(so["cogs_dpp"]), 2))) for so in aug_sos)

        july_ol = [
            ol for ol in self.order_lines
            if do_date_map.get(so_do_map.get(ol["so_number"], ""), "") <= "2026-07-31"
        ]

        return {
            "so_count": len(self.so_rows),
            "do_validated_july": len(july_do) + len(self.po_headers),
            "do_pending_august": len(aug_do),
            "outbound_moves_july": len(july_ol),
            "invoices_july_posted": len(july_inv),
            "invoices_august_pending": len(aug_inv),
            "july_inv_dpp": str(july_inv_dpp),
            "july_inv_ppn": str(july_inv_ppn),
            "july_inv_total": str(july_inv_total),
            "aug_inv_dpp": str(aug_inv_dpp),
            "aug_inv_ppn": str(aug_inv_ppn),
            "aug_inv_total": str(aug_inv_total),
            "july_cogs_nominal": str(july_cogs),
            "aug_cogs_nominal": str(aug_cogs),
            "ar_collections_count": len(self.ar_collections),
            "ap_payments_count": len(self.ap_payments),
            "opex_count": len(self.opex_payroll),
            "quarantine_count": len(self.rejections),
            "opening_sku_count": len(self.opening_rows),
            "physical_on_hand_cartons_july": physical_cartons_july,
            "reserved_cartons_july": reserved_cartons_july,
            "available_cartons_july": available_cartons_july,
            "quarantine_cartons_july": tot_rejections_cartons,
            "physical_units_july": physical_units_july,
            "reserved_units_july": reserved_units_july,
            "available_units_july": available_units_july,
            "quarantine_units_july": tot_rejections_units,
        }

    def get_august_opening_expectations(self) -> dict:
        """Ekspektasi setelah carry-forward 1 Agustus 2026 selesai diproses."""
        july_exp = self.get_july_closing_expectations()
        physical_cartons_aug = july_exp["physical_on_hand_cartons_july"] - july_exp["reserved_cartons_july"]
        physical_units_aug = july_exp["physical_units_july"] - july_exp["reserved_units_july"]
        total_cogs = Decimal(july_exp["july_cogs_nominal"]) + Decimal(july_exp["aug_cogs_nominal"])
        return {
            "so_count": len(self.so_rows),
            "do_total_validated": len(self.deliveries) + len(self.po_headers),
            "outbound_moves_total": len(self.order_lines),
            "invoices_total_posted": len(self.invoices),
            "ar_collections_total": len(self.ar_collections),
            "ap_payments_total": len(self.ap_payments),
            "opex_total": len(self.opex_payroll),
            "quarantine_total": len(self.rejections),
            "opening_sku_total": len(self.opening_rows),
            "physical_on_hand_cartons_august": physical_cartons_aug,
            "reserved_cartons_august": 0,
            "available_cartons_august": physical_cartons_aug,
            "quarantine_cartons_august": july_exp["quarantine_cartons_july"],
            "physical_units_august": physical_units_aug,
            "reserved_units_august": 0,
            "available_units_august": physical_units_aug,
            "quarantine_units_august": july_exp["quarantine_units_july"],
            "total_cogs_nominal": str(total_cogs),
            "total_inv_dpp": str(Decimal(july_exp["july_inv_dpp"]) + Decimal(july_exp["aug_inv_dpp"])),
            "total_inv_ppn": str(Decimal(july_exp["july_inv_ppn"]) + Decimal(july_exp["aug_inv_ppn"])),
            "total_inv_amount": str(Decimal(july_exp["july_inv_total"]) + Decimal(july_exp["aug_inv_total"])),
        }

    def get_expected_stock_multiset(self, cutoff_date="2026-07-31") -> tuple[dict, dict, dict]:
        """Menghitung multiset persediaan per-(SKU, Lot) dan reservasi per-SKU secara dinamis dari CSV register."""
        do_date_map = {d["do_number"]: d["scheduled_delivery_date"] for d in self.deliveries}
        so_do_map = {d["so_number"]: d["do_number"] for d in self.deliveries}

        expected_phys = {}
        expected_res_by_sku = {}
        expected_quar = {}

        # 1. Opening stock
        for r in self.opening_rows:
            sku = r["sku_code"]
            lot = r["lot_number"]
            units = float(r.get("qty_units_on_hand") or (int(r["qty_cartons_on_hand"]) * int(r["carton_qty"])))
            expected_phys[(sku, lot)] = expected_phys.get((sku, lot), 0.0) + units

        # 2. Inbound PO transit
        for r in self.po_lines:
            sku = r["sku_code"]
            lot = r["lot_number"]
            units = float(int(r["qty_cartons"]) * int(r["carton_qty"]))
            expected_phys[(sku, lot)] = expected_phys.get((sku, lot), 0.0) + units

        # 3. Deliveries & Reservations
        for ol in self.order_lines:
            so = ol["so_number"]
            do_num = so_do_map.get(so)
            do_date = do_date_map.get(do_num, "")
            sku = ol["sku_code"]
            lot = ol["lot_number"]
            units = float(int(ol["qty_cartons"]) * int(ol["carton_qty"]))
            if do_date <= cutoff_date:
                expected_phys[(sku, lot)] = expected_phys.get((sku, lot), 0.0) - units
            else:
                expected_res_by_sku[sku] = expected_res_by_sku.get(sku, 0.0) + units

        # 4. Quarantine rejections
        for r in self.rejections:
            sku = r["sku_code"]
            lot = r["lot_number"]
            units = float(int(r["qty_cartons"]) * int(r["carton_qty"]))
            expected_quar[(sku, lot)] = expected_quar.get((sku, lot), 0.0) + units

        return expected_phys, expected_res_by_sku, expected_quar


def capture_deep_state_snapshot(env) -> dict:
    """Mengambil deep snapshot presisi tinggi untuk memverifikasi zero drift penuh."""
    snap = {}

    # 1. stock.quant
    quants = []
    if "stock.quant" in env:
        Quant = env["stock.quant"].sudo()
        for q in _iter_records(Quant.search([])):
            quants.append((
                q.id,
                getattr(q.product_id, "id", None),
                getattr(q.location_id, "id", None),
                getattr(q.lot_id, "id", None),
                round(float(getattr(q, "quantity", 0.0) or 0.0), 4),
                round(float(getattr(q, "reserved_quantity", 0.0) or 0.0), 4),
                getattr(q.company_id, "id", None),
            ))
    quants.sort()
    snap["quants"] = quants
    snap["quants_count"] = len(quants)

    # 2. stock.move.line
    move_lines = []
    if "stock.move.line" in env:
        SML = env["stock.move.line"].sudo()
        for sml in _iter_records(SML.search([])):
            move_lines.append((
                sml.id,
                getattr(sml.move_id, "id", None),
                getattr(sml.product_id, "id", None),
                getattr(sml.lot_id, "id", None),
                getattr(sml.location_id, "id", None),
                getattr(sml.location_dest_id, "id", None),
                getattr(sml.product_uom_id, "id", None),
                round(float(getattr(sml, "quantity", 0.0) or 0.0), 4),
                str(getattr(sml, "date", "") or ""),  # full ISO timestamp
                getattr(sml.company_id, "id", None),
                str(getattr(sml, "state", "")),
            ))
    move_lines.sort()
    snap["move_lines"] = move_lines
    snap["move_lines_count"] = len(move_lines)

    # 3. stock.move
    moves = []
    if "stock.move" in env:
        StockMove = env["stock.move"].sudo()
        for sm in _iter_records(StockMove.search([])):
            am_sing = getattr(getattr(sm, "account_move_id", None), "id", getattr(sm, "account_move_id", None))
            ac_raw = getattr(sm, "account_move_ids", None)
            ac_ids = tuple(sorted([getattr(m, "id", m) for m in _iter_records(ac_raw) if getattr(m, "id", m)]))
            moves.append((
                sm.id,
                getattr(sm.picking_id, "id", None),
                getattr(sm.sale_line_id, "id", None),
                getattr(sm.origin_returned_move_id, "id", None),
                getattr(sm.product_id, "id", None),
                getattr(sm.location_id, "id", None),
                getattr(sm.location_dest_id, "id", None),
                str(getattr(sm.state, "id", sm.state)),
                round(float(getattr(sm, "product_uom_qty", 0.0) or 0.0), 4),
                round(float(getattr(sm, "quantity", 0.0) or 0.0), 4),
                str(getattr(sm, "date", "") or ""),  # full timestamp
                getattr(sm.company_id, "id", None),
                am_sing,
                ac_ids,
            ))
    moves.sort()
    snap["moves"] = moves
    snap["moves_count"] = len(moves)

    # 4. stock.picking
    pickings = []
    if "stock.picking" in env:
        Picking = env["stock.picking"].sudo()
        for sp in _iter_records(Picking.search([])):
            pickings.append((
                sp.id,
                getattr(sp, "name", ""),
                getattr(sp.partner_id, "id", None),
                getattr(sp.picking_type_id, "id", None),
                str(getattr(sp, "scheduled_date", "") or ""),
                str(getattr(sp, "date_done", "") or ""),
                str(getattr(sp, "state", "")),
                getattr(sp.company_id, "id", None),
            ))
    pickings.sort()
    snap["pickings"] = pickings
    snap["pickings_count"] = len(pickings)

    # 5. sale.order
    orders = []
    if "sale.order" in env:
        SaleOrder = env["sale.order"].sudo()
        for so in _iter_records(SaleOrder.search([])):
            sp_user = getattr(so, "user_id", None)
            orders.append((
                so.id,
                getattr(so, "name", ""),
                getattr(so.partner_id, "id", None),
                str(getattr(so, "date_order", "") or ""),
                str(getattr(so, "state", "")),
                getattr(sp_user, "id", sp_user),
                str(round(float(getattr(so, "amount_total", 0.0) or 0.0), 2)),
                getattr(so.company_id, "id", None),
                str(getattr(so, "fmcg_seed_batch", "") or ""),
            ))
    orders.sort()
    snap["orders"] = orders
    snap["orders_count"] = len(orders)

    # 6. account.move
    account_moves = []
    if "account.move" in env:
        AM = env["account.move"].sudo()
        for m in _iter_records(AM.search([])):
            account_moves.append((
                m.id,
                getattr(m, "name", ""),
                str(getattr(m, "date", "") or ""),
                str(getattr(m, "move_type", "")),
                str(getattr(m, "state", "")),
                getattr(m.partner_id, "id", None),
                str(round(float(getattr(m, "amount_untaxed", 0.0) or 0.0), 2)),
                str(round(float(getattr(m, "amount_tax", 0.0) or 0.0), 2)),
                str(round(float(getattr(m, "amount_total", 0.0) or 0.0), 2)),
                str(round(float(getattr(m, "amount_residual", 0.0) or 0.0), 2)),
                getattr(m.company_id, "id", None),
                str(getattr(m, "ref", "") or ""),
                str(getattr(m, "fmcg_seed_batch", "") or ""),
            ))
    account_moves.sort()
    snap["account_moves"] = account_moves
    snap["account_moves_count"] = len(account_moves)

    # 7. account.move.line
    aml_records = []
    gl_balances = defaultdict(lambda: {"debit": Decimal("0.0"), "credit": Decimal("0.0")})
    if "account.move.line" in env:
        AML = env["account.move.line"].sudo()
        for line in _iter_records(AML.search([])):
            acc = line.account_id
            acc_code = getattr(acc, "code", "") or ""
            d_val = Decimal(str(round(float(getattr(line, "debit", 0.0) or 0.0), 2)))
            c_val = Decimal(str(round(float(getattr(line, "credit", 0.0) or 0.0), 2)))
            res_val = Decimal(str(round(float(getattr(line, "amount_residual", 0.0) or 0.0), 2)))
            gl_balances[acc_code]["debit"] += d_val
            gl_balances[acc_code]["credit"] += c_val
            aml_records.append((
                line.id,
                getattr(line.move_id, "id", None),
                getattr(line.product_id, "id", None),
                acc_code,
                str(d_val),
                str(c_val),
                str(res_val),
                str(getattr(line, "date", "") or ""),
                getattr(line, "reconciled", False),
                getattr(line.company_id, "id", None),
            ))
    aml_records.sort()
    snap["aml_records"] = aml_records
    snap["aml_count"] = len(aml_records)
    snap["gl_balances"] = {
        k: {"debit": str(v["debit"]), "credit": str(v["credit"])}
        for k, v in sorted(gl_balances.items())
    }

    # 8. account.payment
    payments = []
    if "account.payment" in env:
        Payment = env["account.payment"].sudo()
        for p in _iter_records(Payment.search([])):
            payments.append((
                p.id,
                getattr(p, "name", ""),
                getattr(p.partner_id, "id", None),
                str(getattr(p, "date", "") or ""),
                str(round(float(getattr(p, "amount", 0.0) or 0.0), 2)),
                str(getattr(p, "payment_type", "")),
                str(getattr(p, "state", "")),
                getattr(p.company_id, "id", None),
            ))
    payments.sort()
    snap["payments"] = payments
    snap["payments_count"] = len(payments)

    return snap


def verify_anti_fallback_salespersons(env):
    """Memastikan tidak ada pesanan penjualan yang jatuh ke default fallback Admin."""
    if "sale.order" not in env:
        return
    SaleOrder = env["sale.order"].sudo()
    admin_users = []
    if "res.users" in env:
        ResUsers = env["res.users"].sudo()
        admin_users = [u.id for u in _iter_records(ResUsers.search([("login", "in", ["admin", "root"])]))]

    sos = _iter_records(SaleOrder.search([]))
    for so in sos:
        user_val = getattr(so, "user_id", None)
        sp_id = getattr(user_val, "id", user_val)
        assert sp_id is not None, f"SO '{so.name}' tidak memiliki salesperson (None)!"
        assert sp_id not in admin_users, (
            f"VIOLATION ANTI-FALLBACK: SO '{so.name}' memiliki salesperson Admin/Root (ID: {sp_id})!"
        )


def resolve_canonical_locations(env):
    """Menyelesaikan lokasi gudang internal dan karantina secara deterministik tanpa substring fuzzy atau fallback ID."""
    StockLocation = env["stock.location"].sudo()
    wh_stock_loc = None
    if "stock.warehouse" in env:
        whs = _iter_records(env["stock.warehouse"].sudo().search([]))
        fmcg_whs = [w for w in whs if getattr(w, "lot_stock_id", None) and "other" not in str(getattr(w, "name", "")).lower()]
        if fmcg_whs:
            wh_stock_loc = fmcg_whs[0].lot_stock_id
    if not wh_stock_loc:
        candidates = _iter_records(StockLocation.search([("usage", "=", "internal")]))
        for name in ("WH/Stock", "Stock", "Gudang Utama Maumbi"):
            matched = [c for c in candidates if str(getattr(c, "name", "")).strip() == name]
            if matched:
                wh_stock_loc = matched[0]
                break
    if not wh_stock_loc:
        raise LookupError("[canonical_locations] Lokasi gudang internal utama tidak ditemukan!")

    quar_candidates = _iter_records(StockLocation.search([
        ("name", "=", "Karantina FMCG Maumbi"),
        ("usage", "=", "internal"),
    ]))
    if not quar_candidates:
        raise LookupError("[canonical_locations] Lokasi karantina 'Karantina FMCG Maumbi' tidak ditemukan!")
    quarantine_loc = quar_candidates[0]

    return wh_stock_loc, quarantine_loc


def audit_database_against_oracle_july(env, oracle: FullDatasetCanonicalOracle):
    """Mengaudit database Odoo aktual secara menyeluruh terhadap ekspektasi Oracle Cut-off 31 Juli 2026."""
    july_exp = oracle.get_july_closing_expectations()
    wh_stock_loc, quarantine_loc = resolve_canonical_locations(env)
    exp_phys, exp_res_by_sku, exp_quar = oracle.get_expected_stock_multiset(cutoff_date="2026-07-31")

    # 1. Stock Quants Multiset (Fisik per SKU+Lot, Reservasi per SKU, dan Karantina per SKU+Lot)
    if "stock.quant" in env:
        Quant = env["stock.quant"].sudo()
        internal_quants = _iter_records(Quant.search([("location_id", "=", wh_stock_loc.id)]))
        quarantine_quants = _iter_records(Quant.search([("location_id", "=", quarantine_loc.id)]))

        actual_phys = {}
        actual_res_by_sku = {}
        for q in internal_quants:
            sku = getattr(getattr(q, "product_id", None), "default_code", "") or ""
            lot = getattr(getattr(q, "lot_id", None), "name", "") or ""
            qty = round(float(getattr(q, "quantity", 0.0) or 0.0), 4)
            res = round(float(getattr(q, "reserved_quantity", 0.0) or 0.0), 4)
            if qty != 0.0 or (sku, lot) in exp_phys:
                actual_phys[(sku, lot)] = actual_phys.get((sku, lot), 0.0) + qty
            if res > 0.0:
                actual_res_by_sku[sku] = actual_res_by_sku.get(sku, 0.0) + res

        # 1a. Audit kuantitas fisik internal exact per-(SKU, Lot)
        for (sku, lot), expected_qty in exp_phys.items():
            act_qty = actual_phys.get((sku, lot), 0.0)
            assert act_qty == expected_qty, (
                f"Audit Fisik Mismatch pada SKU '{sku}', Lot '{lot}'! Expected {expected_qty}, got {act_qty}"
            )
        for (sku, lot), act_qty in actual_phys.items():
            if (sku, lot) not in exp_phys and act_qty != 0.0:
                raise AssertionError(f"Audit Fisik Menemukan SKU/Lot Tak Dikenal: SKU '{sku}', Lot '{lot}' qty={act_qty}!")

        tot_phys_units = sum(actual_phys.values())
        exp_phys_units = float(july_exp["physical_units_july"])
        assert tot_phys_units == exp_phys_units, (
            f"Audit Fisik Gudang Juli Gagal! Expected {exp_phys_units} units, got {tot_phys_units}"
        )

        # 1b. Audit kuantitas reservasi exact per-SKU (untuk 48 DO carry-forward 1 Agustus)
        for sku, expected_res in exp_res_by_sku.items():
            act_res = actual_res_by_sku.get(sku, 0.0)
            assert act_res == expected_res, (
                f"Audit Reservasi Mismatch pada SKU '{sku}'! Expected {expected_res}, got {act_res}"
            )
        for sku, act_res in actual_res_by_sku.items():
            if sku not in exp_res_by_sku and act_res != 0.0:
                raise AssertionError(f"Audit Reservasi Menemukan SKU Tak Terduga: SKU '{sku}' reserved={act_res}!")

        tot_res_units = sum(actual_res_by_sku.values())
        exp_res_units = float(july_exp["reserved_units_july"])
        assert tot_res_units == exp_res_units, (
            f"Audit Reservasi Stok Juli Gagal! Expected {exp_res_units} units, got {tot_res_units}"
        )

        # 1c. Audit kuantitas karantina exact per-(SKU, Lot)
        actual_quar = {}
        for q in quarantine_quants:
            sku = getattr(getattr(q, "product_id", None), "default_code", "") or ""
            lot = getattr(getattr(q, "lot_id", None), "name", "") or ""
            qty = round(float(getattr(q, "quantity", 0.0) or 0.0), 4)
            if qty != 0.0 or (sku, lot) in exp_quar:
                actual_quar[(sku, lot)] = actual_quar.get((sku, lot), 0.0) + qty

        for (sku, lot), expected_qty in exp_quar.items():
            act_qty = actual_quar.get((sku, lot), 0.0)
            assert act_qty == expected_qty, (
                f"Audit Karantina Mismatch pada SKU '{sku}', Lot '{lot}'! Expected {expected_qty}, got {act_qty}"
            )
        for (sku, lot), act_qty in actual_quar.items():
            if (sku, lot) not in exp_quar and act_qty != 0.0:
                raise AssertionError(f"Audit Karantina Menemukan SKU/Lot Tak Dikenal: SKU '{sku}', Lot '{lot}' qty={act_qty}!")

        tot_quar_units = sum(actual_quar.values())
        exp_quar_units = float(july_exp["quarantine_units_july"])
        assert tot_quar_units == exp_quar_units, (
            f"Audit Karantina Juli Gagal! Expected {exp_quar_units} units, got {tot_quar_units}"
        )

    # 2. Sale Orders
    if "sale.order" in env:
        sos = _iter_records(env["sale.order"].sudo().search([]))
        assert len(sos) == july_exp["so_count"], (
            f"Audit SO Gagal! Expected {july_exp['so_count']}, got {len(sos)}"
        )
        for so in sos:
            assert so.state in ("sale", "done"), f"SO {so.name} state invalid: {so.state}"

    # 3. Stock Pickings (DO tervalidasi Juli + PO Inbound + Retur Karantina vs Pending Agustus)
    if "stock.picking" in env:
        done_picks = _iter_records(env["stock.picking"].sudo().search([("state", "=", "done")]))
        expected_done = july_exp["do_validated_july"] + july_exp["quarantine_count"]  # 1281 + 9 = 1290
        assert len(done_picks) == expected_done, (
            f"Audit DO Validated Juli Gagal! Expected {expected_done}, got {len(done_picks)}"
        )
        pending_picks = _iter_records(env["stock.picking"].sudo().search([("state", "!=", "done")]))
        assert len(pending_picks) == july_exp["do_pending_august"], (
            f"Audit DO Pending Agustus Gagal! Expected {july_exp['do_pending_august']}, got {len(pending_picks)}"
        )

    # 4. Customer Invoices (Faktur Penjualan Komersial Juli)
    if "account.move" in env:
        AM = env["account.move"].sudo()
        out_invoices = _iter_records(AM.search([("move_type", "=", "out_invoice")]))
        assert len(out_invoices) == july_exp["invoices_july_posted"], (
            f"Audit Faktur Juli Gagal! Expected {july_exp['invoices_july_posted']}, got {len(out_invoices)}"
        )

        # Audit ketat cut-off: NOL faktur out_invoice bertanggal Agustus
        aug_invoices = _iter_records(AM.search([("date", ">", "2026-07-31"), ("move_type", "=", "out_invoice")]))
        assert len(aug_invoices) == 0, (
            f"VIOLATION CUT-OFF: Ditemukan {len(aug_invoices)} faktur Agustus pada database penutupan Juli!"
        )

        for inv in out_invoices:
            assert inv.state == "posted", f"Invoice {inv.name} state invalid: {inv.state}"
            assert str(inv.date) <= "2026-07-31", f"Invoice {inv.name} tanggal melintasi batas cut-off: {inv.date}"
            assert getattr(inv, "fmcg_seed_batch", None) == "CANONICAL_JULY_2026_PERPETUAL"

        tot_dpp = sum(Decimal(str(round(float(getattr(i, "amount_untaxed", 0.0) or 0.0), 2))) for i in out_invoices)
        expected_dpp = Decimal(july_exp["july_inv_dpp"])
        assert tot_dpp == expected_dpp, (
            f"Audit DPP Faktur Juli Mismatch! Expected {expected_dpp}, got {tot_dpp}"
        )

        tot_ppn = sum(Decimal(str(round(float(getattr(i, "amount_tax", 0.0) or 0.0), 2))) for i in out_invoices)
        expected_ppn = Decimal(july_exp["july_inv_ppn"])
        assert tot_ppn == expected_ppn, (
            f"Audit PPN Faktur Juli Mismatch! Expected {expected_ppn}, got {tot_ppn}"
        )

        tot_gross = sum(Decimal(str(round(float(getattr(i, "amount_total", 0.0) or 0.0), 2))) for i in out_invoices)
        expected_gross = Decimal(july_exp["july_inv_total"])
        assert tot_gross == expected_gross, (
            f"Audit Total Faktur Juli Mismatch! Expected {expected_gross}, got {tot_gross}"
        )

    # 5. Saldo COGS Nominal & Relasi Singular Stock Move Non-Vacuous
    if "account.move.line" in env:
        AML = env["account.move.line"].sudo()
        all_lines = _iter_records(AML.search([]))
        cogs_lines = [
            ln for ln in all_lines
            if getattr(getattr(ln, "account_id", None), "code", "") == "510000"
            and str(getattr(ln, "date", "")) <= "2026-07-31"
        ]
        tot_cogs_debit = sum(Decimal(str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2))) for ln in cogs_lines)
        exp_cogs = Decimal(july_exp["july_cogs_nominal"])
        assert tot_cogs_debit == exp_cogs, (
            f"Audit COGS Nominal Juli Mismatch! Expected Rp {exp_cogs}, got Rp {tot_cogs_debit}"
        )

    if "stock.move" in env:
        SM = env["stock.move"].sudo()
        # Non-vacuous check: boolean check 'not m.origin_returned_move_id' tahan terhadap empty recordset
        done_out_moves = [
            m for m in _iter_records(SM.search([("state", "=", "done")]))
            if not getattr(m, "origin_returned_move_id", False)
            and not getattr(m, "is_inventory", False)
            and getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
        ]
        expected_out_moves = july_exp["outbound_moves_july"]  # 2650 customer delivery moves pada 1281 DO tervalidasi
        assert len(done_out_moves) == expected_out_moves, (
            f"Audit Outbound Moves Juli Gagal! Expected {expected_out_moves}, got {len(done_out_moves)}"
        )
        for m in done_out_moves:
            am = getattr(m, "account_move_id", None)
            assert am, f"Stock move pengiriman {m.id} ({getattr(m, 'name', '')}) wajib memiliki binding singular account_move_id!"
            assert getattr(am, "state", "") == "posted", f"Account move {getattr(am, 'name', '')} pada move {m.id} belum posted!"
            lines = _iter_records(getattr(am, "line_ids", []))
            codes = {getattr(getattr(ln, "account_id", None), "code", "") for ln in lines}
            assert "510000" in codes, f"Account move {am.name} pada move {m.id} tidak memiliki debit COGS 510000!"
            assert "113000" in codes, f"Account move {am.name} pada move {m.id} tidak memiliki credit Persediaan 113000!"

    # 6. Pembayaran AR / AP / OPEX
    if "account.payment" in env:
        Payment = env["account.payment"].sudo()
        ar_pays = _iter_records(Payment.search([("payment_type", "=", "inbound")]))
        assert len(ar_pays) == july_exp["ar_collections_count"], (
            f"Audit AR Payments Gagal! Expected {july_exp['ar_collections_count']}, got {len(ar_pays)}"
        )
        ap_pays = _iter_records(Payment.search([("payment_type", "=", "outbound")]))
        assert len(ap_pays) == july_exp["ap_payments_count"], (
            f"Audit AP Payments Gagal! Expected {july_exp['ap_payments_count']}, got {len(ap_pays)}"
        )

    # 7. Saldo GL Seimbang & Batas Waktu
    if "account.move" in env and "account.move.line" in env:
        AM = env["account.move"].sudo()
        posted_moves = _iter_records(AM.search([("state", "=", "posted")]))
        for m in posted_moves:
            m_lines = _iter_records(m.line_ids)
            d_sum = sum(Decimal(str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2))) for ln in m_lines)
            c_sum = sum(Decimal(str(round(float(getattr(ln, "credit", 0.0) or 0.0), 2))) for ln in m_lines)
            assert d_sum == c_sum, f"Jurnal {m.name} tidak seimbang! Debit: {d_sum}, Credit: {c_sum}"

        AML = env["account.move.line"].sudo()
        crossing_aml = _iter_records(AML.search([("date", ">", "2026-07-31")]))
        assert len(crossing_aml) == 0, (
            f"VIOLATION CUT-OFF: Ditemukan {len(crossing_aml)} baris jurnal bertanggal Agustus pada penutupan Juli!"
        )


def audit_database_against_oracle_august(env, oracle: FullDatasetCanonicalOracle, prior_july_aml_snapshot=None):
    """Mengaudit database Odoo aktual setelah carry-forward 1 Agustus 2026 selesai diproses."""
    aug_exp = oracle.get_august_opening_expectations()
    wh_stock_loc, quarantine_loc = resolve_canonical_locations(env)
    exp_phys, _, exp_quar = oracle.get_expected_stock_multiset(cutoff_date="2026-08-01")

    # 1. Stock Quants Multiset (Reservasi Nol & Fisik Berkurang Bersih)
    if "stock.quant" in env:
        Quant = env["stock.quant"].sudo()
        internal_quants = _iter_records(Quant.search([("location_id", "=", wh_stock_loc.id)]))
        quarantine_quants = _iter_records(Quant.search([("location_id", "=", quarantine_loc.id)]))

        actual_phys = {}
        actual_res_by_sku = {}
        for q in internal_quants:
            sku = getattr(getattr(q, "product_id", None), "default_code", "") or ""
            lot = getattr(getattr(q, "lot_id", None), "name", "") or ""
            qty = round(float(getattr(q, "quantity", 0.0) or 0.0), 4)
            res = round(float(getattr(q, "reserved_quantity", 0.0) or 0.0), 4)
            if qty != 0.0 or (sku, lot) in exp_phys:
                actual_phys[(sku, lot)] = actual_phys.get((sku, lot), 0.0) + qty
            if res > 0.0:
                actual_res_by_sku[sku] = actual_res_by_sku.get(sku, 0.0) + res

        # 1a. Audit kuantitas fisik internal exact per-(SKU, Lot)
        for (sku, lot), expected_qty in exp_phys.items():
            act_qty = actual_phys.get((sku, lot), 0.0)
            assert act_qty == expected_qty, (
                f"Audit Fisik Agustus Mismatch pada SKU '{sku}', Lot '{lot}'! Expected {expected_qty}, got {act_qty}"
            )
        for (sku, lot), act_qty in actual_phys.items():
            if (sku, lot) not in exp_phys and act_qty != 0.0:
                raise AssertionError(f"Audit Fisik Agustus Menemukan SKU/Lot Tak Dikenal: SKU '{sku}', Lot '{lot}' qty={act_qty}!")

        tot_phys_units = sum(actual_phys.values())
        exp_phys_units = float(aug_exp["physical_units_august"])
        assert tot_phys_units == exp_phys_units, (
            f"Audit Fisik Gudang Agustus Mismatch! Expected {exp_phys_units} units, got {tot_phys_units}"
        )

        # 1b. Audit kuantitas reservasi nol bersih untuk seluruh SKU
        assert len(actual_res_by_sku) == 0, (
            f"Audit Reservasi Agustus Gagal! Ditemukan SKU dengan reservasi aktif: {actual_res_by_sku}"
        )

        # 1c. Audit kuantitas karantina exact per-(SKU, Lot)
        actual_quar = {}
        for q in quarantine_quants:
            sku = getattr(getattr(q, "product_id", None), "default_code", "") or ""
            lot = getattr(getattr(q, "lot_id", None), "name", "") or ""
            qty = round(float(getattr(q, "quantity", 0.0) or 0.0), 4)
            if qty != 0.0 or (sku, lot) in exp_quar:
                actual_quar[(sku, lot)] = actual_quar.get((sku, lot), 0.0) + qty

        for (sku, lot), expected_qty in exp_quar.items():
            act_qty = actual_quar.get((sku, lot), 0.0)
            assert act_qty == expected_qty, (
                f"Audit Karantina Agustus Mismatch pada SKU '{sku}', Lot '{lot}'! Expected {expected_qty}, got {act_qty}"
            )

    # 2. Total Pickings (1.324 DO + 5 PO + 9 Retur Karantina = 1.338 Pickings tervalidasi)
    if "stock.picking" in env:
        done_picks = _iter_records(env["stock.picking"].sudo().search([("state", "=", "done")]))
        expected_done = aug_exp["do_total_validated"] + aug_exp["quarantine_total"]  # 1329 + 9 = 1338
        assert len(done_picks) == expected_done, (
            f"Audit DO Total Validated Gagal! Expected {expected_done}, got {len(done_picks)}"
        )
        pending_picks = _iter_records(env["stock.picking"].sudo().search([("state", "!=", "done")]))
        assert len(pending_picks) == 0, (
            f"Audit DO Pending Setelah Agustus Gagal! Expected 0, got {len(pending_picks)}"
        )

    # 3. Total Invoices (1.324 faktur komersial diposting)
    if "account.move" in env:
        AM = env["account.move"].sudo()
        out_invoices = _iter_records(AM.search([("move_type", "=", "out_invoice")]))
        assert len(out_invoices) == aug_exp["invoices_total_posted"], (
            f"Audit Total Faktur Gagal! Expected {aug_exp['invoices_total_posted']}, got {len(out_invoices)}"
        )

        aug_invoices = _iter_records(AM.search([("date", ">", "2026-07-31"), ("move_type", "=", "out_invoice")]))
        assert len(aug_invoices) == 48, (
            f"Audit Faktur Agustus Gagal! Expected 48, got {len(aug_invoices)}"
        )

        tot_dpp = sum(Decimal(str(round(float(getattr(i, "amount_untaxed", 0.0) or 0.0), 2))) for i in out_invoices)
        expected_dpp = Decimal(aug_exp["total_inv_dpp"])
        assert tot_dpp == expected_dpp, (
            f"Audit Total DPP Faktur Mismatch! Expected {expected_dpp}, got {tot_dpp}"
        )

        tot_ppn = sum(Decimal(str(round(float(getattr(i, "amount_tax", 0.0) or 0.0), 2))) for i in out_invoices)
        expected_ppn = Decimal(aug_exp["total_inv_ppn"])
        assert tot_ppn == expected_ppn, (
            f"Audit Total PPN Faktur Mismatch! Expected {expected_ppn}, got {tot_ppn}"
        )

    # 4. Total COGS Nominal & Relasi Singular Stock Move Non-Vacuous
    if "account.move.line" in env:
        AML = env["account.move.line"].sudo()
        all_lines = _iter_records(AML.search([]))
        cogs_lines = [
            ln for ln in all_lines
            if getattr(getattr(ln, "account_id", None), "code", "") == "510000"
        ]
        tot_cogs_debit = sum(Decimal(str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2))) for ln in cogs_lines)
        exp_cogs = Decimal(aug_exp["total_cogs_nominal"])
        assert tot_cogs_debit == exp_cogs, (
            f"Audit Total COGS Nominal Mismatch! Expected Rp {exp_cogs}, got Rp {tot_cogs_debit}"
        )

    if "stock.move" in env:
        SM = env["stock.move"].sudo()
        done_out_moves = [
            m for m in _iter_records(SM.search([("state", "=", "done")]))
            if not getattr(m, "origin_returned_move_id", False)
            and not getattr(m, "is_inventory", False)
            and getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
        ]
        expected_out_moves = aug_exp["outbound_moves_total"]  # 2738 customer delivery moves pada 1324 DO total
        assert len(done_out_moves) == expected_out_moves, (
            f"Audit Outbound Moves Total Gagal! Expected {expected_out_moves}, got {len(done_out_moves)}"
        )
        for m in done_out_moves:
            am = getattr(m, "account_move_id", None)
            assert am, f"Stock move pengiriman {m.id} ({getattr(m, 'name', '')}) wajib memiliki binding singular account_move_id!"
            assert getattr(am, "state", "") == "posted", f"Account move {getattr(am, 'name', '')} pada move {m.id} belum posted!"
            lines = _iter_records(getattr(am, "line_ids", []))
            codes = {getattr(getattr(ln, "account_id", None), "code", "") for ln in lines}
            assert "510000" in codes, f"Account move {am.name} pada move {m.id} tidak memiliki debit COGS 510000!"
            assert "113000" in codes, f"Account move {am.name} pada move {m.id} tidak memiliki credit Persediaan 113000!"

    # 5. Immutabilitas Penutupan Historis Juli (Exact Multiset Matching)
    if prior_july_aml_snapshot is not None and "account.move.line" in env:
        AML = env["account.move.line"].sudo()
        current_july_aml_multiset = sorted([
            (
                ln.id,
                getattr(getattr(ln, "move_id", None), "id", None),
                getattr(getattr(ln, "account_id", None), "code", "") or "",
                getattr(getattr(ln, "product_id", None), "id", None),
                str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2)),
                str(round(float(getattr(ln, "credit", 0.0) or 0.0), 2)),
                str(getattr(ln, "date", "") or ""),
                str(round(float(getattr(ln, "amount_residual", 0.0) or 0.0), 2)),
                getattr(ln, "reconciled", False),
                getattr(getattr(ln, "company_id", None), "id", None),
            )
            for ln in _iter_records(AML.search([("date", "<=", "2026-07-31")]))
        ])
        assert current_july_aml_multiset == prior_july_aml_snapshot, (
            "VIOLATION HISTORICAL CLOSING: Rekonsiliasi multiset baris AML Juli berubah setelah carry-forward Agustus!"
        )


def run_real_negative_mutations_on_database(env, oracle: FullDatasetCanonicalOracle) -> dict:
    """Menguji penolakan mutasi negatif aktual langsung pada database menggunakan transaction savepoint.

    Membuktikan secara deterministik pada database PostgreSQL nyata bahwa auditor produksi menolak:
    1. Pertukaran kuantitas fisik antar-SKU (+5 / -5).
    2. Substitusi lot_id ke dummy probe lot 999.
    3. Pertukaran kuantitas reservasi antar-SKU (+5 / -5).
    4. Pemutusan relasi singular account_move_id pada outbound delivery move.
    5. Modifikasi nilai seimbang pada baris AML (COGS debit +500k, Stock credit +500k).
    6. Injeksi faktur komersial Agustus pada penutupan Juli (cross-cutoff leak).
    """
    results = {}
    Quant = env["stock.quant"].sudo() if "stock.quant" in env else None
    StockLot = env["stock.lot"].sudo() if "stock.lot" in env else None
    SM = env["stock.move"].sudo() if "stock.move" in env else None
    AM = env["account.move"].sudo() if "account.move" in env else None
    AML = env["account.move.line"].sudo() if "account.move.line" in env else None

    cr = getattr(env, "cr", None)
    has_sp = cr and hasattr(cr, "savepoint") and callable(getattr(cr, "savepoint"))

    @contextlib.contextmanager
    def _db_savepoint():
        if has_sp:
            with cr.savepoint():
                yield
        elif hasattr(env, "_take_snapshot") and hasattr(env, "_restore_snapshot"):
            snap = env._take_snapshot()
            try:
                yield
            finally:
                env._restore_snapshot(snap)
        else:
            raise RuntimeError("[negative_mutations] Cursor savepoint() tidak tersedia pada environment!")

    # 1. Mutasi: SKU Physical On-Hand Swap (+5 di SKU A, -5 di SKU B)
    if Quant is not None:
        int_quants = [
            q for q in _iter_records(Quant.search([]))
            if getattr(getattr(q, "location_id", None), "usage", "") == "internal"
            and "karantina" not in str(getattr(getattr(q, "location_id", None), "name", "")).lower()
            and float(getattr(q, "quantity", 0.0) or 0.0) >= 10.0
        ]
        if len(int_quants) >= 2:
            q1, q2 = int_quants[0], int_quants[1]
            try:
                with _db_savepoint():
                    q1.write({"quantity": float(q1.quantity) + 5.0})
                    q2.write({"quantity": float(q2.quantity) - 5.0})
                    audit_database_against_oracle_july(env, oracle)
                    raise RuntimeError("Mutasi SKU physical swap lolos audit tanpa penolakan!")
            except AssertionError as exc:
                results["probe_1_sku_physical_swap"] = {
                    "status": "REJECTED_AS_EXPECTED",
                    "description": f"Tukar fisik +5 di {getattr(q1.product_id, 'default_code', '')} dan -5 di {getattr(q2.product_id, 'default_code', '')}",
                    "rejection_message": str(exc),
                }
                print(f"   [Probe 1 PASS] SKU Physical Swap (+5/-5) sukses ditolak: {exc}")

    # 2. Mutasi: Dummy Lot Substitution (lot 999)
    if Quant is not None and StockLot is not None:
        target_q = next((
            q for q in _iter_records(Quant.search([]))
            if getattr(getattr(q, "location_id", None), "usage", "") == "internal"
            and "karantina" not in str(getattr(getattr(q, "location_id", None), "name", "")).lower()
            and float(getattr(q, "quantity", 0.0) or 0.0) > 0.0
        ), None)
        if target_q:
            try:
                with _db_savepoint():
                    dummy_lot = StockLot.search([("name", "=", "LOT-PROBE-999")], limit=1)
                    if not dummy_lot:
                        dummy_lot = StockLot.create({
                            "name": "LOT-PROBE-999",
                            "product_id": target_q.product_id.id,
                        })
                    target_q.write({"lot_id": dummy_lot.id})
                    audit_database_against_oracle_july(env, oracle)
                    raise RuntimeError("Mutasi lot substitution lolos audit tanpa penolakan!")
            except AssertionError as exc:
                results["probe_2_lot_substitution"] = {
                    "status": "REJECTED_AS_EXPECTED",
                    "description": f"Substitusi lot_id ke LOT-PROBE-999 pada {getattr(target_q.product_id, 'default_code', '')}",
                    "rejection_message": str(exc),
                }
                print(f"   [Probe 2 PASS] Lot Substitution (LOT-PROBE-999) sukses ditolak: {exc}")

    # 3. Mutasi: Reserved SKU Swap (+5 di SKU A, -5 di SKU B)
    if Quant is not None:
        res_quants = [
            q for q in _iter_records(Quant.search([]))
            if getattr(getattr(q, "location_id", None), "usage", "") == "internal"
            and float(getattr(q, "reserved_quantity", 0.0) or 0.0) >= 10.0
        ]
        if len(res_quants) >= 2:
            rq1, rq2 = res_quants[0], res_quants[1]
            try:
                with _db_savepoint():
                    rq1.write({"reserved_quantity": float(rq1.reserved_quantity) + 5.0})
                    rq2.write({"reserved_quantity": float(rq2.reserved_quantity) - 5.0})
                    audit_database_against_oracle_july(env, oracle)
                    raise RuntimeError("Mutasi reserved SKU swap lolos audit tanpa penolakan!")
            except AssertionError as exc:
                results["probe_3_reserved_sku_swap"] = {
                    "status": "REJECTED_AS_EXPECTED",
                    "description": f"Tukar reservasi +5 di {getattr(rq1.product_id, 'default_code', '')} dan -5 di {getattr(rq2.product_id, 'default_code', '')}",
                    "rejection_message": str(exc),
                }
                print(f"   [Probe 3 PASS] Reserved SKU Swap (+5/-5) sukses ditolak: {exc}")

    # 4. Mutasi: Unlink account_move_id on Outbound Customer Delivery Move
    if SM is not None:
        out_mv = next((
            m for m in _iter_records(SM.search([("state", "=", "done")]))
            if not getattr(m, "origin_returned_move_id", False)
            and not getattr(m, "is_inventory", False)
            and getattr(getattr(m, "location_dest_id", None), "usage", "") == "customer"
            and getattr(m, "account_move_id", None)
        ), None)
        if out_mv:
            try:
                with _db_savepoint():
                    out_mv.write({"account_move_id": False})
                    audit_database_against_oracle_july(env, oracle)
                    raise RuntimeError("Mutasi pemutusan account_move_id lolos audit tanpa penolakan!")
            except AssertionError as exc:
                results["probe_4_cogs_binding_unlink"] = {
                    "status": "REJECTED_AS_EXPECTED",
                    "description": f"Unlink account_move_id pada stock.move ID {out_mv.id}",
                    "rejection_message": str(exc),
                }
                print(f"   [Probe 4 PASS] COGS Binding Unlink sukses ditolak: {exc}")

    # 5. Mutasi: Balanced AML Value Tampering (+500k debit COGS 510000, +500k credit Persediaan 113000)
    if AML is not None and AM is not None:
        cogs_ln = next((
            ln for ln in _iter_records(AML.search([]))
            if getattr(getattr(ln, "account_id", None), "code", "") == "510000"
            and float(getattr(ln, "debit", 0.0) or 0.0) > 0.0
        ), None)
        if cogs_ln:
            mv_id = getattr(getattr(cogs_ln, "move_id", None), "id", None)
            stk_ln = next((
                ln for ln in _iter_records(AML.search([("move_id", "=", mv_id)]))
                if getattr(getattr(ln, "account_id", None), "code", "") == "113000"
                and float(getattr(ln, "credit", 0.0) or 0.0) > 0.0
            ), None)
            if stk_ln:
                try:
                    with _db_savepoint():
                        if has_sp and hasattr(env, "cr") and hasattr(env.cr, "execute"):
                            env.cr.execute(
                                "UPDATE account_move_line SET debit = debit + 500000.0 WHERE id = %s",
                                [cogs_ln.id],
                            )
                            env.cr.execute(
                                "UPDATE account_move_line SET credit = credit + 500000.0 WHERE id = %s",
                                [stk_ln.id],
                            )
                            if hasattr(env, "invalidate_all"):
                                env.invalidate_all()
                        else:
                            cogs_ln.write({"debit": float(cogs_ln.debit) + 500000.0})
                            stk_ln.write({"credit": float(stk_ln.credit) + 500000.0})
                        audit_database_against_oracle_july(env, oracle)
                        raise RuntimeError("Mutasi balanced AML tampering lolos audit tanpa penolakan!")
                except AssertionError as exc:
                    results["probe_5_balanced_aml_tampering"] = {
                        "status": "REJECTED_AS_EXPECTED",
                        "description": "Tambah Rp 500.000 seimbang pada debit 510000 & credit 113000",
                        "rejection_message": str(exc),
                    }
                    print(f"   [Probe 5 PASS] Balanced AML Tampering (+Rp 500k) sukses ditolak: {exc}")

    # 6. Mutasi: Injeksi Faktur Agustus pada Database Juli (Cross-Cutoff Leak)
    if AM is not None:
        try:
            with _db_savepoint():
                partner = env["res.partner"].search([], limit=1) if "res.partner" in env else None
                jnl = env["account.journal"].search([("type", "=", "sale")], limit=1) if "account.journal" in env else None
                inv_vals = {
                    "name": "INV/ILLEGAL/2026/08",
                    "move_type": "out_invoice",
                    "date": "2026-08-01",
                    "invoice_date": "2026-08-01",
                    "amount_untaxed": 1000000.0,
                    "amount_tax": 110000.0,
                    "amount_total": 1110000.0,
                    "fmcg_seed_batch": "CANONICAL_JULY_2026_PERPETUAL",
                }
                if partner:
                    inv_vals["partner_id"] = getattr(partner, "id", partner)
                if jnl:
                    inv_vals["journal_id"] = getattr(jnl, "id", jnl)
                AM.create(inv_vals)
                audit_database_against_oracle_july(env, oracle)
                raise RuntimeError("Injeksi faktur Agustus lolos audit tanpa penolakan!")
        except AssertionError as exc:
            results["probe_6_cross_cutoff_invoice"] = {
                "status": "REJECTED_AS_EXPECTED",
                "description": "Injeksi out_invoice bertanggal 2026-08-01 ke database penutupan Juli",
                "rejection_message": str(exc),
            }
            print(f"   [Probe 6 PASS] Cross-Cutoff Invoice Injection sukses ditolak: {exc}")

    # Verifikasi ulang baseline: pastikan database kembali bersih 100% setelah seluruh probe di-rollback
    audit_database_against_oracle_july(env, oracle)
    print("   [Baseline Verified] Database terbukti bersih dan identik setelah seluruh mutasi di-rollback.")
    return results


def run_full_disposable_verification(env, output_dir=None):
    """Fungsi utama eksekusi pembuktian runtime penuh pada Odoo 19 disposable."""
    if output_dir:
        output_dir = Path(output_dir)
    else:
        # Utamakan /tmp jika berada di lingkungan Linux container (/opt biasanya non-writable untuk user odoo)
        if Path("/tmp").is_dir() and os.access("/tmp", os.W_OK):
            output_dir = Path("/tmp")
        else:
            output_dir = Path(REPO_ROOT)
    t0_global = time.time()
    cr = getattr(env, "cr", None)
    db_name = getattr(cr, "dbname", "unknown") if cr else "unknown"

    meta = {
        "database": db_name,
        "commit_sha": os.environ.get("GITHUB_SHA") or "unknown",
        "image_info": os.environ.get("ODOO_IMAGE_DIGEST") or os.environ.get("ODOO_IMAGE") or "fmcg-odoo:ci",
        "github_run_id": os.environ.get("GITHUB_RUN_ID") or "local",
        "business_timezone": "Asia/Makassar (WITA, UTC+8)",
    }
    report = {
        "title": "PEMBUKTIAN RUNTIME PENUH DATASET KANONIKAL PADA ODOO 19 DISPOSABLE",
        "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": meta,
        "phases": {},
        "status": "INITIALIZING",
    }

    try:
        print("=" * 80)
        print("[verify_disposable_full] MEMULAI PEMBUKTIAN RUNTIME PENUH DISPOSABLE")
        print("=" * 80)

        # 1. Safety Guard
        db_name = assert_disposable_database(env)
        print(f" -> [Safety Guard PASS] Database target '{db_name}' terverifikasi disposable.")

        # 2. Introspeksi Metadata Lingkungan Lengkap
        meta = introspect_runtime_environment(env)
        report["environment"] = meta
        print(f" -> [Environment] Commit SHA: {meta['commit_sha'][:8]} | Timezone: {meta['business_timezone']}")
        print(f" -> [Environment] Modul terinstal: {meta['installed_modules_count']} ({len(meta['fmcg_modules'])} FMCG)")

        oracle = FullDatasetCanonicalOracle(REG_PATH)
        july_exp = oracle.get_july_closing_expectations()
        aug_exp = oracle.get_august_opening_expectations()
        report["oracle_july_expectations"] = july_exp
        report["oracle_august_expectations"] = aug_exp

        # 3. Fase 1: Closing Juli 2026 (Cut-off 31 Juli)
        print("\n" + "=" * 80)
        print("[Fase 1] MENJALANKAN PEMUATAN RUN 1 — CLOSING JULI 2026 (CUT-OFF 31 JULI)")
        print("=" * 80)
        t0_phase1 = time.time()
        adapter_july = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter_july.run_all()
        if hasattr(env, "cr") and callable(getattr(env.cr, "commit", None)):
            env.cr.commit()
        dur_phase1 = time.time() - t0_phase1
        print(f" -> [Fase 1 Selesai] Durasi: {dur_phase1:.2f} detik")

        report["phases"]["phase1_closing_july"] = {
            "duration_seconds": round(dur_phase1, 2),
            "stats": dict(adapter_july.stats),
        }

        # Audit Independen Checkpoint Juli
        print("\n[Audit Checkpoint Juli] Memverifikasi database aktual terhadap Oracle Kanonikal...")
        audit_database_against_oracle_july(env, oracle)
        print(" -> [Audit Checkpoint Juli PASS] 1.324 SO, 1.281 DO tervalidasi, 1.276 Faktur Juli, GL seimbang.")

        # 3B. Runtime Fault-Injection (Negative Mutations Probe) di Database Aktual via cr.savepoint
        print("\n" + "=" * 80)
        print("[Fase 1B] PENGUJIAN MUTASI NEGATIF AKTUAL PADA DATABASE (CR.SAVEPOINT)")
        print("=" * 80)
        t0_mut = time.time()
        mut_results = run_real_negative_mutations_on_database(env, oracle)
        dur_mut = time.time() - t0_mut
        report["phases"]["phase1b_negative_mutations"] = {
            "duration_seconds": round(dur_mut, 2),
            "probes_count": len(mut_results),
            "all_probes_rejected_as_expected": all(v.get("status") == "REJECTED_AS_EXPECTED" for v in mut_results.values()),
        }
        report["runtime_negative_mutations"] = mut_results
        print(f" -> [Fase 1B PASS] Seluruh {len(mut_results)} mutasi negatif nyata terbukti digagalkan oleh audit ({dur_mut:.2f} s)!")

        # Capture snapshot immutable baris AML Juli untuk uji immutabilitas
        prior_july_aml_multiset = []
        if "account.move.line" in env:
            AML = env["account.move.line"].sudo()
            prior_july_aml_multiset = sorted([
                (
                    ln.id,
                    getattr(getattr(ln, "move_id", None), "id", None),
                    getattr(getattr(ln, "account_id", None), "code", "") or "",
                    getattr(getattr(ln, "product_id", None), "id", None),
                    str(round(float(getattr(ln, "debit", 0.0) or 0.0), 2)),
                    str(round(float(getattr(ln, "credit", 0.0) or 0.0), 2)),
                    str(getattr(ln, "date", "") or ""),
                    str(round(float(getattr(ln, "amount_residual", 0.0) or 0.0), 2)),
                    getattr(ln, "reconciled", False),
                    getattr(getattr(ln, "company_id", None), "id", None),
                )
                for ln in _iter_records(AML.search([("date", "<=", "2026-07-31")]))
            ])

        # 4. Fase 2: Post-Transaksi 1 Agustus 2026 (Carry-Forward 48 DO & Faktur)
        print("\n" + "=" * 80)
        print("[Fase 2] MENJALANKAN CARRY-FORWARD — POST-TRANSAKSI 1 AGUSTUS 2026")
        print("=" * 80)
        t0_phase2 = time.time()
        adapter_aug = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_aug.run_all()
        if hasattr(env, "cr") and callable(getattr(env.cr, "commit", None)):
            env.cr.commit()
        dur_phase2 = time.time() - t0_phase2
        print(f" -> [Fase 2 Selesai] Durasi: {dur_phase2:.2f} detik")

        report["phases"]["phase2_opening_august"] = {
            "duration_seconds": round(dur_phase2, 2),
            "stats": dict(adapter_aug.stats),
        }

        # Audit Independen Checkpoint Agustus & Immutabilitas Juli
        print("\n[Audit Checkpoint Agustus] Memverifikasi database aktual terhadap Oracle Kanonikal...")
        audit_database_against_oracle_august(env, oracle, prior_july_aml_snapshot=prior_july_aml_multiset)
        print(" -> [Audit Checkpoint Agustus PASS] 1.329 DO tervalidasi, 1.324 Faktur, Closing Juli terbukti imutabel.")

        # Anti-Fallback Check
        verify_anti_fallback_salespersons(env)
        print(" -> [Anti-Fallback PASS] Seluruh 1.324 SO terikat salesperson kanonikal sah.")

        # Deep State Snapshot Run 1
        print("\n[Snapshot Run 1] Mengambil deep state snapshot lengkap...")
        snap1 = capture_deep_state_snapshot(env)
        report["snapshot_run1"] = {
            "quants_count": snap1["quants_count"],
            "moves_count": snap1["moves_count"],
            "move_lines_count": snap1["move_lines_count"],
            "pickings_count": snap1["pickings_count"],
            "orders_count": snap1["orders_count"],
            "account_moves_count": snap1["account_moves_count"],
            "aml_count": snap1["aml_count"],
            "payments_count": snap1["payments_count"],
        }

        # 5. Fase 3: Idempotensi Replay Penuh (Run 2)
        print("\n" + "=" * 80)
        print("[Fase 3] MENJALANKAN REPLAY RUN 2 (UJI IDEMPOTENSI ZERO-DRIFT)")
        print("=" * 80)
        t0_phase3 = time.time()
        adapter_run2 = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_run2.run_all()
        if hasattr(env, "cr") and callable(getattr(env.cr, "commit", None)):
            env.cr.commit()
        dur_phase3 = time.time() - t0_phase3
        print(f" -> [Fase 3 Selesai] Durasi: {dur_phase3:.2f} detik")

        report["phases"]["phase3_idempotency_run2"] = {
            "duration_seconds": round(dur_phase3, 2),
            "stats": dict(adapter_run2.stats),
        }

        # Deep State Snapshot Run 2
        print("\n[Snapshot Run 2] Mengambil deep state snapshot kedua & memverifikasi zero drift...")
        snap2 = capture_deep_state_snapshot(env)

        assert snap1["quants"] == snap2["quants"], "DRIFT DETECTED pada stock.quant!"
        assert snap1["move_lines"] == snap2["move_lines"], "DRIFT DETECTED pada stock.move.line!"
        assert snap1["moves"] == snap2["moves"], "DRIFT DETECTED pada stock.move!"
        assert snap1["pickings"] == snap2["pickings"], "DRIFT DETECTED pada stock.picking!"
        assert snap1["orders"] == snap2["orders"], "DRIFT DETECTED pada sale.order!"
        assert snap1["account_moves"] == snap2["account_moves"], "DRIFT DETECTED pada account.move!"
        assert snap1["aml_records"] == snap2["aml_records"], "DRIFT DETECTED pada account.move.line!"
        assert snap1["payments"] == snap2["payments"], "DRIFT DETECTED pada account.payment!"
        assert snap1["gl_balances"] == snap2["gl_balances"], "DRIFT DETECTED pada GL balances!"
        print(" -> [Zero-Drift PASS] 100% identik multiset antara Run 1 dan Run 2!")

        report["status"] = "SUCCESS"
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        dur_total = time.time() - t0_global
        report["total_duration_seconds"] = round(dur_total, 2)

    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["total_duration_seconds"] = round(time.time() - t0_global, 2)
        print(f"\n[FATAL ERROR] {exc}\n{traceback.format_exc()}", file=sys.stderr)
        raise

    finally:
        # Tulis berkas JSON machine-readable ke direktori yang writable
        written_json = False
        candidate_dirs = [output_dir]
        if Path("/tmp") not in candidate_dirs:
            candidate_dirs.append(Path("/tmp"))
        if Path(REPO_ROOT) not in candidate_dirs:
            candidate_dirs.append(Path(REPO_ROOT))

        for c_dir in candidate_dirs:
            if not c_dir.is_dir():
                continue
            t_json = c_dir / "full_dataset_runtime_report.json"
            try:
                with open(t_json, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, default=str)
                print(f"\n[Laporan JSON] Disimpan di: {t_json}")
                written_json = True
            except Exception as e:
                print(f"[WARN] Gagal menulis laporan JSON ke {t_json}: {e}", file=sys.stderr)
        if not written_json:
            print("[FATAL] Tidak ada direktori writable untuk menyimpan laporan JSON!", file=sys.stderr)

        # Tulis ringkasan Markdown dengan asersi status yang tepat
        try:
            is_success = report.get("status") == "SUCCESS"
            dur_total = report.get("total_duration_seconds", round(time.time() - t0_global, 2))
            p1_dur = report.get("phases", {}).get("phase1_closing_july", {}).get("duration_seconds", "-")
            p1b_dur = report.get("phases", {}).get("phase1b_negative_mutations", {}).get("duration_seconds", "-")
            p2_dur = report.get("phases", {}).get("phase2_opening_august", {}).get("duration_seconds", "-")
            p3_dur = report.get("phases", {}).get("phase3_idempotency_run2", {}).get("duration_seconds", "-")

            mut_rows = ""
            for p_name, p_data in report.get("runtime_negative_mutations", {}).items():
                mut_rows += f"| `{p_name}` | {p_data.get('description', '-')} | **{p_data.get('status', '-')}** |\n"

            md_summary = f"""# Ringkasan Eksekusi Runtime Penuh Dataset Kanonikal FMCG

- **Status:** {report['status']}
- **Database Target:** `{meta.get('database', 'unknown')}`
- **Commit SHA:** `{meta.get('commit_sha', 'unknown')}`
- **Image Info / Digest:** `{meta.get('image_info', 'unknown')}`
- **Waktu Mulai:** `{report['timestamp_start']}` | **Selesai:** `{report.get('timestamp_end', '-')}`
- **Total Durasi:** `{dur_total:.2f}` detik (~{dur_total/60:.2f} menit)
- **Timezone Bisnis:** `Asia/Makassar (WITA, UTC+8)`

## 1. Rincian Eksekusi per Fase
| Fase Eksekusi | Status / Durasi | Dokumen Kunci Diproses |
|---|---|---|
| **Fase 1: Closing Juli 2026** | {p1_dur} s | {'SELESAI' if 'phase1_closing_july' in report.get('phases', {}) else 'NOT_RUN'} |
| **Fase 1B: Pengujian Mutasi Negatif Nyata** | {p1b_dur} s | {len(report.get('runtime_negative_mutations', {}))} mutasi savepoint diuji |
| **Fase 2: Post-Transaksi 1 Agustus 2026** | {p2_dur} s | {'SELESAI' if 'phase2_opening_august' in report.get('phases', {}) else 'NOT_RUN'} |
| **Fase 3: Idempotensi Run 2** | {p3_dur} s | {'SELESAI' if 'phase3_idempotency_run2' in report.get('phases', {}) else 'NOT_RUN'} |

## 2. Hasil Pengujian Mutasi Negatif Nyata pada Database (cr.savepoint)
| Kode Mutasi Probe | Deskripsi Mutasi / Skenario Counterexample | Status Penolakan |
|---|---|---|
{mut_rows}
## 3. Hasil Audit Saldo & Zero-Drift
- **Audit Oracle Kanonikal:** {'PASS' if is_success else 'FAIL / INCOMPLETE'}
- **Anti-Fallback Salesperson:** {'PASS' if is_success else 'FAIL / INCOMPLETE'}
- **Zero-Drift Idempotensi:** {'PASS' if is_success else 'FAIL / INCOMPLETE'}
- **Saldo GL:** {'100% seimbang (Debit == Credit)' if is_success else 'FAIL / UNVERIFIED'}
"""
            if not is_success and "error" in report:
                md_summary += f"\n## 4. Detail Kegagalan\n- **Error:** `{report['error']}`\n```\n{report.get('traceback', '')}\n```\n"

            for c_dir in candidate_dirs:
                if not c_dir.is_dir():
                    continue
                t_md = c_dir / "full_dataset_runtime_summary.md"
                try:
                    with open(t_md, "w", encoding="utf-8") as f:
                        f.write(md_summary)
                    print(f"[Ringkasan MD] Disimpan di: {t_md}")
                except Exception as e:
                    print(f"[WARN] Gagal menulis ringkasan MD ke {t_md}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Gagal menulis ringkasan Markdown: {e}", file=sys.stderr)

    return report


if __name__ == "__main__":
    if "env" in locals() or "env" in globals():
        run_full_disposable_verification(globals().get("env") or locals().get("env"))
    else:
        print("[verify_disposable_full] Memerlukan lingkungan Odoo shell (variabel 'env').")
        sys.exit(1)
