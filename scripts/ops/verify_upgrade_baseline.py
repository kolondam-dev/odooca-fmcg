#!/usr/bin/env python3
"""Runner Prioritas 3: Upgrade Modul dari Baseline Persisten + Replay Idempotensi.

Membuktikan bahwa sistem FMCG Odoo 19 aman melewati siklus upgrade versi modul:

Fase BASELINE (dijalankan sebelum upgrade, di dalam `odoo shell`):
  1. Memuat dataset kanonikal penuh pada database disposable: closing Juli 2026
     (fase 1) lalu carry-forward 1 Agustus 2026 (fase 2) melalui
     `CanonicalPerpetualAdapter` produksi.
  2. Menjalankan audit produksi `audit_database_against_oracle_july` pada state
     closing Juli dan `audit_database_against_oracle_august` pada state pasca-1
     Agustus (oracle independen, bukan output loader).
  3. Mengambil deep state snapshot presisi tinggi + digest SHA-256 seluruh entitas
     bisnis dan multiset baris AML Juli (bukti imutabilitas historis).
  4. Menyuntikkan dua drift terkontrol agar upgrade benar-benar melakukan kerja
     perbaikan [A]:
       - version skew: `ir.module.module.latest_version` diturunkan ke versi rilis
         sebelumnya sehingga database menyerupai baseline rilis lama;
       - schema drift: satu kolom modul yang tabelnya kosong dihapus, sehingga
         `-u` wajib membuat ulang kolom tersebut via `_auto_init`;
       - view drift: satu record `ir.ui.view` + xmlid-nya dihapus, sehingga `-u`
         wajib memuat ulang XML view.
  5. Menulis `upgrade_baseline_state.json` ke direktori output.

Fase VERIFY (dijalankan setelah `odoo -u id_base,id_mobile_api` nyata):
  1. Memvalidasi kontrak proses upgrade: exit code 0 dan tidak ada indikasi
     registry corruption pada log (dokumentasi `--check-log`).
  2. Memvalidasi registry modul: state `installed`, `latest_version` kembali sama
     dengan versi manifest kode, `installed_version` terisi.
  3. Memvalidasi DDL: setiap field stored milik modul `id_*` memiliki kolom nyata
     (termasuk kolom yang sengaja dihapus pada fase baseline).
  4. Memvalidasi relasi foreign key: tidak ada baris orphan pada seluruh field
     many2one milik modul `id_*`.
  5. Memvalidasi view XML: seluruh xmlid view modul ter-resolve, arch tidak kosong,
     dan XML valid (termasuk view yang sengaja dihapus pada fase baseline).
  6. Memvalidasi hook integritas akuntansi: override HPP `id_base` aktif pada
     registry, faktur komersial seed tidak membawa baris HPP duplikat, dan setiap
     delivery outbound selesai memiliki jurnal valuasi native STJ posted.
  7. Menjalankan replay `CanonicalPerpetualAdapter.run_all()` dan membuktikan
     zero-creation (seluruh counter pembuatan = 0) serta minimum skip terpenuhi.
  8. Membandingkan digest deep state snapshot dengan baseline: zero-drift mutlak.
  9. Membuktikan imutabilitas closing Juli dan menjalankan ulang
     `audit_database_against_oracle_august` + anti-fallback salesperson.
 10. Menulis `upgrade_runtime_report.json` dan `upgrade_runtime_summary.md`.

Safety guard database disposable identik dengan runner full dataset
(`assert_disposable_database`): nama operasional (`prod`, `production`, `live`,
`railway`, `master`, `official`, `main`) ditolak keras.
"""

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET

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

from scripts.load_canonical_perpetual import CanonicalPerpetualAdapter  # noqa: E402
from scripts.ops.verify_disposable_full import (  # noqa: E402
    FullDatasetCanonicalOracle,
    _iter_records,
    assert_disposable_database,
    audit_database_against_oracle_august,
    audit_database_against_oracle_july,
    capture_deep_state_snapshot,
    introspect_runtime_environment,
    verify_anti_fallback_salespersons,
)

UPGRADE_MODULES = ("id_base", "id_mobile_api")
UPGRADE_MODULE_CSV = ",".join(UPGRADE_MODULES)

BASELINE_STATE_FILENAME = "upgrade_baseline_state.json"
BASELINE_REPORT_FILENAME = "upgrade_baseline_report.json"
VERIFY_REPORT_FILENAME = "upgrade_runtime_report.json"
VERIFY_SUMMARY_FILENAME = "upgrade_runtime_summary.md"

BASELINE_STATE_SCHEMA_VERSION = 1

# Counter pembuatan yang WAJIB nol pada replay pasca-upgrade.
CREATION_COUNTERS = (
    "opening_quants",
    "po_created",
    "po_bills_created",
    "so_created",
    "invoices_created",
    "ar_payments_created",
    "ap_payments_created",
    "discount_moves_created",
    "opex_moves_created",
    "quarantine_rejections",
)

# Minimum counter skip kanonikal yang WAJIB terpenuhi pada replay pasca-upgrade.
EXPECTED_SKIP_MINIMUMS = {
    "skipped_opening_quants": 150,
    "skipped_po": 5,
    "skipped_so": 1324,
    "skipped_invoices": 1324,
    "skipped_ar": 967,
    "skipped_ap": 4,
    "skipped_opex": 30,
    "skipped_quarantine": 9,
}

SNAPSHOT_KEYS = (
    "quants",
    "move_lines",
    "moves",
    "pickings",
    "orders",
    "account_moves",
    "aml_records",
    "gl_balances",
    "payments",
)

# Drift terkontrol: kolom non-kritis pada tabel modul yang kosong di baseline.
SCHEMA_DRIFT_TARGETS = (
    ("id.mobile.office", "id_mobile_office", "radius"),
)

# Drift terkontrol: xmlid view yang dihapus agar `-u` memuat ulang XML view.
VIEW_DRIFT_XMLIDS = ("id_mobile_api.view_mobile_office_form",)


# ---------------------------------------------------------------------------
# Guard & kontrak proses upgrade (murni, dapat diuji unit tanpa Odoo)
# ---------------------------------------------------------------------------


class _DatabaseNameTarget:
    """Shim minimal agar guard `assert_disposable_database` dapat dipakai tanpa env Odoo."""

    def __init__(self, dbname: str):
        self.cr = type("_CursorShim", (), {"dbname": dbname})()


def assert_upgrade_target_database(db_name: str) -> str:
    """Guard database disposable untuk runner upgrade (satu sumber kebenaran dengan runner penuh)."""
    if not db_name or not str(db_name).strip():
        raise RuntimeError("[SAFETY-ABORT] Nama database target upgrade kosong!")
    return assert_disposable_database(_DatabaseNameTarget(str(db_name).strip()))


def assert_upgrade_target_env(env) -> str:
    """Guard database disposable untuk lingkungan Odoo shell aktif."""
    cr = getattr(env, "cr", None)
    db_name = getattr(cr, "dbname", "") or ""
    return assert_upgrade_target_database(db_name)


def resolve_addons_root(addons_root=None) -> Path:
    """Menentukan direktori addon id_* (container `--addons-path` atau repo)."""
    if addons_root:
        return Path(addons_root)
    for candidate in (Path("/opt/id-addons"), REPO_ROOT / "addons", Path("addons")):
        if (candidate / "id_base" / "__manifest__.py").exists():
            return candidate
    raise RuntimeError(
        "[upgrade] Tidak dapat menemukan direktori addon id_* (dicari: /opt/id-addons, addons/)."
    )


def read_manifest_version(module_name: str, addons_root=None) -> str:
    """Membaca versi manifest kode untuk satu modul id_*."""
    manifest = resolve_addons_root(addons_root) / module_name / "__manifest__.py"
    if not manifest.exists():
        raise RuntimeError(f"[upgrade] Manifest modul '{module_name}' tidak ditemukan: {manifest}")
    try:
        payload = ast.literal_eval(manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"[upgrade] Manifest '{manifest}' tidak dapat diparse: {exc}") from exc
    version = str(payload.get("version", "") or "")
    if not version:
        raise RuntimeError(f"[upgrade] Manifest '{manifest}' tidak memuat kunci 'version'!")
    return version


def expected_module_versions(addons_root=None, modules=UPGRADE_MODULES) -> dict:
    """Versi manifest kode yang wajib terpasang pasca-upgrade."""
    return {name: read_manifest_version(name, addons_root=addons_root) for name in modules}


def build_upgrade_command(
    db_name: str,
    modules=UPGRADE_MODULES,
    odoo_conf="/tmp/odoo.conf",
    addons_path=None,
    data_dir="/var/lib/odoo",
) -> list:
    """Membangun argv perintah upgrade Odoo nyata (`odoo -u ... --stop-after-init -d <db>`)."""
    assert_upgrade_target_database(db_name)
    argv = ["odoo", "-c", str(odoo_conf), "-d", str(db_name)]
    if addons_path:
        argv.extend(["--addons-path", str(addons_path)])
    if data_dir:
        argv.extend(["--data-dir", str(data_dir)])
    argv.extend(["-u", ",".join(modules), "--stop-after-init", "--log-level=info"])
    return argv


_CORRUPTION_PATTERNS = (
    re.compile(r" (ERROR|CRITICAL) "),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"Registry loading failed", re.IGNORECASE),
    re.compile(r"psycopg2\.errors\."),
    re.compile(r"could not load module", re.IGNORECASE),
)


def detect_registry_corruption(log_text: str) -> list:
    """Mendeteksi baris log yang menandakan kegagalan registry/skema saat upgrade."""
    findings = []
    for line_no, line in enumerate((log_text or "").splitlines(), 1):
        for pattern in _CORRUPTION_PATTERNS:
            if pattern.search(line):
                findings.append(f"line {line_no}: {line.strip()[:300]}")
                break
    return findings


def validate_upgrade_exit_code(returncode: int, log_text: str) -> dict:
    """Kontrak proses upgrade: exit code 0 DAN log bebas indikasi registry corruption.

    Selain itu log wajib memuat penanda registry benar-benar dimuat
    (`Modules loaded.`), sehingga exit 0 palsu (mis. abort konfigurasi dini)
    tidak lolos sebagai bukti upgrade.
    """
    findings = detect_registry_corruption(log_text)
    if int(returncode) != 0:
        raise RuntimeError(
            f"[UPGRADE-FAIL] Perintah upgrade Odoo keluar dengan kode {returncode} "
            f"(wajib 0). Temuan log: {findings[:10] or 'tidak ada pola corruption, periksa log lengkap'}"
        )
    if findings:
        raise RuntimeError(
            "[UPGRADE-FAIL] Proses upgrade exit 0 tetapi log memuat indikasi registry/skema "
            f"corruption ({len(findings)} baris):\n" + "\n".join(findings[:20])
        )
    if not re.search(r"Modules loaded\.", log_text or ""):
        raise RuntimeError(
            "[UPGRADE-FAIL] Log upgrade tidak memuat penanda 'Modules loaded.'; proses exit 0 "
            "tidak membuktikan registry modul benar-benar dimuat/di-upgrade."
        )
    return {
        "status": "PASS",
        "exit_code": int(returncode),
        "corruption_findings": [],
        "modules_loaded_marker": True,
        "log_lines": len((log_text or "").splitlines()),
    }


def previous_release_version(version: str) -> str:
    """Menurunkan versi manifest ke versi rilis sebelumnya (simulasi version skew)."""
    parts = str(version or "").split(".")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return "19.0.0.0.0"
    if len(nums) < 5:
        return "19.0.0.0.0"
    for idx in (3, 4):
        if nums[idx] > 0:
            nums[idx] -= 1
            for tail in range(idx + 1, len(nums)):
                nums[tail] = 0
            return ".".join(str(n) for n in nums)
    return "19.0.0.0.0"


def digest_payload(payload) -> str:
    """Digest SHA-256 stabil terhadap tipe (tuple/list) untuk payload snapshot."""
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_digest(snapshot: dict) -> dict:
    """Digest per entitas deep state snapshot."""
    digests = {}
    for key in SNAPSHOT_KEYS:
        if key not in snapshot:
            continue
        digests[key] = digest_payload(snapshot[key])
    return digests


def compare_snapshot_digests(baseline_digests: dict, current_digests: dict) -> dict:
    """Membandingkan digest baseline vs pasca-upgrade; gagal jika ada drift apa pun."""
    missing = sorted(set(baseline_digests) - set(current_digests))
    if missing:
        raise AssertionError(f"[UPGRADE-DRIFT] Entitas baseline tidak dapat dibaca ulang: {missing}")
    drifted = sorted(
        key for key, value in baseline_digests.items() if current_digests.get(key) != value
    )
    if drifted:
        raise AssertionError(
            f"[UPGRADE-DRIFT] Snapshot pasca-upgrade berbeda dari baseline pada entitas: {drifted}"
        )
    return {"status": "PASS", "entities": sorted(baseline_digests), "drifted_entities": []}


def assert_replay_zero_creation(stats: dict) -> dict:
    """Kontrak replay idempotensi: tidak ada record baru dan minimum skip kanonikal terpenuhi."""
    created = {key: int(stats.get(key, 0) or 0) for key in CREATION_COUNTERS}
    nonzero = {key: value for key, value in created.items() if value}
    if nonzero:
        raise AssertionError(
            f"[UPGRADE-REPLAY] Replay pasca-upgrade membuat record baru (wajib 0): {nonzero}"
        )
    skipped = {key: int(stats.get(key, 0) or 0) for key in EXPECTED_SKIP_MINIMUMS}
    shortfall = {
        key: {"expected_min": minimum, "actual": skipped[key]}
        for key, minimum in EXPECTED_SKIP_MINIMUMS.items()
        if skipped[key] < minimum
    }
    if shortfall:
        raise AssertionError(
            f"[UPGRADE-REPLAY] Minimum skip kanonikal tidak terpenuhi pada replay: {shortfall}"
        )
    return {
        "status": "PASS",
        "created_counters": created,
        "skipped_counters": skipped,
        "total_created": 0,
    }


def load_baseline_state(state_path, expected_database=None) -> dict:
    """Memuat state baseline persisten dan memvalidasi identitas database."""
    path = Path(state_path)
    if not path.exists():
        raise RuntimeError(f"[UPGRADE] State baseline tidak ditemukan: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != BASELINE_STATE_SCHEMA_VERSION:
        raise RuntimeError(
            f"[UPGRADE] Versi skema state baseline tidak didukung: {state.get('schema_version')}"
        )
    if expected_database and state.get("database") != expected_database:
        raise RuntimeError(
            f"[UPGRADE] State baseline milik database '{state.get('database')}' tetapi target "
            f"upgrade adalah '{expected_database}'. Ditolak (fail-closed)."
        )
    if not state.get("snapshot_digests"):
        raise RuntimeError("[UPGRADE] State baseline tidak memuat snapshot_digests!")
    return state


# ---------------------------------------------------------------------------
# Inventaris & verifikasi integritas pasca-upgrade
# ---------------------------------------------------------------------------


def _commit(env):
    cr = getattr(env, "cr", None)
    if cr is not None and callable(getattr(cr, "commit", None)):
        cr.commit()


def _module_table_columns(cr, table: str, cache: dict) -> set:
    if table in cache:
        return cache[table]
    cr.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    columns = {row[0] for row in cr.fetchall()}
    cache[table] = columns
    return columns


def inventory_module_registry(env, expected_versions=None) -> dict:
    """Mengumpulkan state registry `ir.module.module` untuk modul upgrade."""
    expected_versions = expected_versions or expected_module_versions()
    Module = env["ir.module.module"].sudo()
    inventory = {}
    for name in UPGRADE_MODULES:
        module = Module.search([("name", "=", name)], limit=1)
        if not module:
            raise AssertionError(f"[UPGRADE-REGISTRY] Modul '{name}' tidak terdaftar pada ir.module.module!")
        inventory[name] = {
            "state": str(getattr(module, "state", "") or ""),
            "latest_version": str(getattr(module, "latest_version", "") or ""),
            "installed_version": str(getattr(module, "installed_version", "") or ""),
            "manifest_version": str(expected_versions.get(name, "")),
        }
    return inventory


def assert_module_registry_integrity(env, expected_versions=None) -> dict:
    """Registry pasca-upgrade wajib installed dan versinya kembali sinkron dengan manifest kode."""
    expected_versions = expected_versions or expected_module_versions()
    inventory = inventory_module_registry(env, expected_versions=expected_versions)
    failures = []
    for name, info in inventory.items():
        if info["state"] != "installed":
            failures.append(f"{name}: state '{info['state']}' (wajib 'installed')")
        if info["latest_version"] != info["manifest_version"]:
            failures.append(
                f"{name}: latest_version '{info['latest_version']}' != manifest '{info['manifest_version']}'"
            )
        if not info["installed_version"]:
            failures.append(f"{name}: installed_version kosong")
    if failures:
        raise AssertionError("[UPGRADE-REGISTRY] " + "; ".join(failures))
    return {"status": "PASS", "modules": inventory}


def is_column_backed_field(field) -> bool:
    """True hanya untuk field stored yang disimpan sebagai kolom PostgreSQL nyata.

    Dikecualikan: field non-stored, field relasional many2many/one2many (disimpan
    di tabel relasi), dan Binary `attachment=True` (disimpan sebagai ir.attachment).
    Pengecualian ini mencegah negatif palsu pada pemeriksaan DDL.
    """
    if not getattr(field, "store", False):
        return False
    if getattr(field, "type", None) in ("many2many", "one2many"):
        return False
    if getattr(field, "attachment", False):
        return False
    return bool(getattr(field, "column_type", None))


def assert_schema_integrity(env) -> dict:
    """Setiap field stored milik modul id_* wajib memiliki kolom nyata di PostgreSQL."""
    modules = set(UPGRADE_MODULES)
    cr = env.cr
    column_cache = {}
    checked = 0
    missing = []
    for model_name, model in env.registry.models.items():
        if not getattr(model, "_auto", False):
            continue
        table = getattr(model, "_table", None)
        if not table:
            continue
        module_fields = [
            (fname, field)
            for fname, field in getattr(model, "_fields", {}).items()
            if getattr(field, "_module", None) in modules and is_column_backed_field(field)
        ]
        if not module_fields:
            continue
        columns = _module_table_columns(cr, table, column_cache)
        for fname, field in module_fields:
            checked += 1
            if fname not in columns:
                missing.append(f"{model_name}.{fname} (kolom '{table}.{fname}' hilang)")
    if missing:
        raise AssertionError(
            f"[UPGRADE-DDL] {len(missing)} kolom modul tidak ada pasca-upgrade: {missing[:20]}"
        )
    return {
        "status": "PASS",
        "checked_fields": checked,
        "checked_tables": len(column_cache),
        "missing_columns": [],
    }


def assert_foreign_key_integrity(env) -> dict:
    """Tidak boleh ada baris orphan pada field many2one milik modul id_*."""
    modules = set(UPGRADE_MODULES)
    cr = env.cr
    checked = 0
    orphans = []
    for model_name, model in env.registry.models.items():
        if not getattr(model, "_auto", False):
            continue
        table = getattr(model, "_table", None)
        if not table:
            continue
        for fname, field in getattr(model, "_fields", {}).items():
            if getattr(field, "_module", None) not in modules:
                continue
            if getattr(field, "type", None) != "many2one":
                continue
            if not getattr(field, "store", False) or getattr(field, "company_dependent", False):
                continue
            ref_model = env.registry.models.get(getattr(field, "comodel_name", None))
            ref_table = getattr(ref_model, "_table", None) if ref_model is not None else None
            if not ref_table:
                continue
            cr.execute(
                f'SELECT count(*) FROM "{table}" t LEFT JOIN "{ref_table}" r '
                f'ON t."{fname}" = r.id WHERE t."{fname}" IS NOT NULL AND r.id IS NULL'
            )
            orphan_count = int(cr.fetchone()[0])
            checked += 1
            if orphan_count:
                orphans.append(f"{model_name}.{fname}: {orphan_count} baris orphan -> {ref_table}")
    if orphans:
        raise AssertionError(
            f"[UPGRADE-FK] Relasi many2one modul memuat baris orphan: {orphans[:20]}"
        )
    return {"status": "PASS", "checked_relations": checked, "orphans": []}


def assert_view_xml_integrity(env, required_xmlids=None) -> dict:
    """Seluruh xmlid view modul wajib ter-resolve, arch tidak kosong, dan XML valid."""
    ModelData = env["ir.model.data"].sudo()
    View = env["ir.ui.view"].sudo()
    rows = _iter_records(
        ModelData.search([("module", "in", list(UPGRADE_MODULES)), ("model", "=", "ir.ui.view")])
    )
    invalid = []
    checked = 0
    for row in rows:
        xmlid = f"{row.module}.{row.name}"
        view = View.browse(row.res_id)
        if not view.exists():
            invalid.append(f"{xmlid}: record ir.ui.view id {row.res_id} hilang")
            continue
        arch = getattr(view, "arch_db", None) or getattr(view, "arch", None) or ""
        arch_text = arch if isinstance(arch, str) else str(arch)
        if not arch_text.strip():
            invalid.append(f"{xmlid}: arch kosong")
            continue
        try:
            ET.fromstring(arch_text)
        except ET.ParseError as exc:
            invalid.append(f"{xmlid}: XML tidak valid ({exc})")
            continue
        checked += 1

    restored = []
    for xmlid in required_xmlids or ():
        record = env.ref(xmlid, raise_if_not_found=False)
        if not record:
            invalid.append(f"{xmlid}: xmlid wajib tidak ter-resolve pasca-upgrade (drift tidak dipulihkan)")
        else:
            restored.append(xmlid)

    if invalid:
        raise AssertionError(f"[UPGRADE-VIEW] Integritas view XML gagal: {invalid[:20]}")
    return {
        "status": "PASS",
        "checked_views": checked,
        "restored_drift_views": restored,
    }


def assert_hpp_hook_integrity(env) -> dict:
    """Hook HPP id_base wajib aktif dan tidak menduplikasi HPP pada faktur seed."""
    AccountMove = env["account.move"]
    method = getattr(AccountMove, "_stock_account_prepare_realtime_out_lines_vals", None)
    method_module = (
        getattr(method, "__module__", "")
        or getattr(getattr(method, "__func__", None), "__module__", "")
        or ""
    )
    if "id_base" not in method_module:
        raise AssertionError(
            "[UPGRADE-HPP] Override `_stock_account_prepare_realtime_out_lines_vals` dari id_base "
            f"tidak aktif pada registry (module method: '{method_module}')!"
        )
    for field_name in ("is_fmcg_seed_invoice", "fmcg_seed_batch"):
        if field_name not in getattr(AccountMove, "_fields", {}):
            raise AssertionError(f"[UPGRADE-HPP] Field hook '{field_name}' tidak terdaftar pada registry!")
    if not hasattr(AccountMove, "_is_seed_commercial_invoice_with_posted_delivery_cogs"):
        raise AssertionError(
            "[UPGRADE-HPP] Validator `_is_seed_commercial_invoice_with_posted_delivery_cogs` hilang!"
        )

    Aml = env["account.move.line"].sudo()
    StockMove = env["stock.move"].sudo()
    seed_field = "move_id.is_fmcg_seed_invoice"

    seed_invoices = int(AccountMove.sudo().search_count([("is_fmcg_seed_invoice", "=", True)]))
    cogs_account = env["account.account"].sudo().search([("code", "=", "510000")], limit=1)
    duplicate_hpp_lines = 0
    if cogs_account:
        duplicate_hpp_lines = int(
            Aml.search_count([
                (seed_field, "=", True),
                ("move_id.move_type", "=", "out_invoice"),
                ("move_id.state", "=", "posted"),
                ("account_id", "=", cogs_account.id),
            ])
        )
    outbound_domain = [
        ("state", "=", "done"),
        ("location_id.usage", "=", "internal"),
        ("location_dest_id.usage", "=", "customer"),
    ]
    outbound_moves = int(StockMove.search_count(outbound_domain))
    missing_cogs = int(StockMove.search_count(outbound_domain + [("account_move_id", "=", False)]))
    non_stj_cogs = int(
        StockMove.search_count(outbound_domain + [("account_move_id.state", "!=", "posted")])
    )

    failures = []
    if seed_invoices <= 0:
        failures.append("tidak ada faktur komersial seed yang terdeteksi")
    if duplicate_hpp_lines != 0:
        failures.append(f"faktur seed membawa {duplicate_hpp_lines} baris HPP 510000 duplikat (wajib 0)")
    if outbound_moves <= 0:
        failures.append("tidak ada delivery outbound selesai yang terdeteksi")
    if missing_cogs != 0:
        failures.append(f"{missing_cogs} delivery outbound tanpa jurnal valuasi native")
    if non_stj_cogs != 0:
        failures.append(f"{non_stj_cogs} delivery outbound tanpa jurnal valuasi posted")
    if failures:
        raise AssertionError("[UPGRADE-HPP] " + "; ".join(failures))
    return {
        "status": "PASS",
        "method_module": method_module,
        "seed_invoices": seed_invoices,
        "duplicate_hpp_lines": duplicate_hpp_lines,
        "outbound_moves": outbound_moves,
        "outbound_missing_cogs": missing_cogs,
        "outbound_non_posted_cogs": non_stj_cogs,
    }


def capture_july_aml_multiset(env) -> list:
    """Multiset baris AML Juli <= 2026-07-31 untuk bukti imutabilitas closing."""
    if "account.move.line" not in env:
        return []
    Aml = env["account.move.line"].sudo()
    rows = sorted([
        (
            line.id,
            getattr(getattr(line, "move_id", None), "id", None),
            getattr(getattr(line, "account_id", None), "code", "") or "",
            getattr(getattr(line, "product_id", None), "id", None),
            str(round(float(getattr(line, "debit", 0.0) or 0.0), 2)),
            str(round(float(getattr(line, "credit", 0.0) or 0.0), 2)),
            str(getattr(line, "date", "") or ""),
            str(round(float(getattr(line, "amount_residual", 0.0) or 0.0), 2)),
            getattr(line, "reconciled", False),
            getattr(getattr(line, "company_id", None), "id", None),
        )
        for line in _iter_records(Aml.search([("date", "<=", "2026-07-31")]))
    ])
    return rows


def assert_july_closing_immutable(env, expected_digest: str) -> dict:
    """Closing Juli wajib identik secara digest setelah upgrade + replay + carry-forward."""
    rows = capture_july_aml_multiset(env)
    actual = digest_payload(rows)
    if actual != expected_digest:
        raise AssertionError(
            "[UPGRADE-IMMUTABLE] Multiset baris AML closing Juli berubah setelah upgrade/replay!"
        )
    return {"status": "PASS", "july_aml_lines": len(rows), "digest": actual}


def repair_schema_drift_targets(env) -> dict:
    """Memverifikasi bahwa drift skema terkontrol benar-benar dipulihkan oleh `-u`."""
    cr = env.cr
    column_cache = {}
    repaired = []
    unresolved = []
    for _model, table, column in SCHEMA_DRIFT_TARGETS:
        columns = _module_table_columns(cr, table, column_cache)
        entry = {"table": table, "column": column, "present": column in columns}
        if entry["present"]:
            repaired.append(entry)
        else:
            unresolved.append(entry)
    if unresolved:
        raise AssertionError(
            f"[UPGRADE-DDL] Drift skema tidak dipulihkan oleh upgrade: {unresolved}"
        )
    return {"status": "PASS", "repaired_columns": repaired}


# ---------------------------------------------------------------------------
# Fase baseline: muat dataset, audit, snapshot, dan suntik drift terkontrol
# ---------------------------------------------------------------------------


def _output_dir(output_dir=None) -> Path:
    if output_dir:
        return Path(output_dir)
    if Path("/tmp").is_dir() and os.access("/tmp", os.W_OK):
        return Path("/tmp")
    return Path(REPO_ROOT)


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _write_summary(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _record_counts(snapshot: dict) -> dict:
    return {
        "quants": snapshot.get("quants_count", 0),
        "move_lines": snapshot.get("move_lines_count", 0),
        "moves": snapshot.get("moves_count", 0),
        "pickings": snapshot.get("pickings_count", 0),
        "orders": snapshot.get("orders_count", 0),
        "account_moves": snapshot.get("account_moves_count", 0),
        "aml": snapshot.get("aml_count", 0),
        "payments": snapshot.get("payments_count", 0),
    }


def inject_previous_release_skew(env, expected_versions=None) -> dict:
    """Menurunkan `latest_version` modul agar database menyerupai baseline rilis sebelumnya."""
    expected_versions = expected_versions or expected_module_versions()
    Module = env["ir.module.module"].sudo()
    injected = {}
    for name, manifest_version in expected_versions.items():
        module = Module.search([("name", "=", name)], limit=1)
        if not module:
            raise RuntimeError(f"[upgrade] Modul '{name}' tidak ditemukan untuk injeksi version skew!")
        previous = previous_release_version(manifest_version)
        if previous == manifest_version:
            raise RuntimeError(
                f"[upgrade] Versi rilis sebelumnya untuk '{name}' tidak lebih rendah dari manifest!"
            )
        previous_latest = str(getattr(module, "latest_version", "") or "")
        module.write({"latest_version": previous})
        injected[name] = {
            "latest_version_before": previous_latest,
            "latest_version_skewed": previous,
            "manifest_version": manifest_version,
        }
    _commit(env)
    return injected


def inject_schema_drift(env) -> list:
    """Menghapus kolom non-kritis pada tabel modul yang kosong agar `-u` wajib membuatnya ulang."""
    cr = env.cr
    injected = []
    for model_name, table, column in SCHEMA_DRIFT_TARGETS:
        cr.execute(f'SELECT count(*) FROM "{table}"')
        row_count = int(cr.fetchone()[0])
        cr.execute(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table, column),
        )
        column_info = cr.fetchone()
        entry = {
            "model": model_name,
            "table": table,
            "column": column,
            "row_count": row_count,
            "present_before": column_info is not None,
            "injected": False,
            "skip_reason": None,
        }
        if column_info is None:
            entry["skip_reason"] = "kolom sudah tidak ada sebelum upgrade"
        elif row_count != 0:
            entry["skip_reason"] = "tabel tidak kosong; penghapusan kolom dibatalkan demi keamanan data"
        else:
            cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
            cr.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                (table, column),
            )
            entry["injected"] = cr.fetchone() is None
            if not entry["injected"]:
                entry["skip_reason"] = "DROP COLUMN tidak berefek"
        injected.append(entry)
    _commit(env)
    return injected


def inject_view_drift(env) -> list:
    """Menghapus record view + xmlid-nya agar `-u` wajib memuat ulang XML view."""
    ModelData = env["ir.model.data"].sudo()
    injected = []
    for xmlid in VIEW_DRIFT_XMLIDS:
        module, _, name = xmlid.partition(".")
        view = env.ref(xmlid, raise_if_not_found=False)
        data_row = ModelData.search([("module", "=", module), ("name", "=", name)], limit=1)
        entry = {
            "xmlid": xmlid,
            "present_before": bool(view) or bool(data_row),
            "injected": False,
            "skip_reason": None,
        }
        if not view and not data_row:
            entry["skip_reason"] = "xmlid sudah tidak ada sebelum upgrade"
        else:
            if view:
                view.unlink()
            if data_row:
                data_row.unlink()
            entry["injected"] = not bool(env.ref(xmlid, raise_if_not_found=False))
            if not entry["injected"]:
                entry["skip_reason"] = "penghapusan view/xmlid tidak berefek"
        injected.append(entry)
    _commit(env)
    return injected


def capture_persistent_baseline(env, output_dir=None) -> dict:
    """Memuat dataset kanonikal penuh + audit, lalu menyimpan baseline persisten untuk upgrade."""
    out = _output_dir(output_dir)
    started = time.time()
    report = {
        "title": "BASELINE PERSISTEN DATASET KANONIKAL SEBELUM UPGRADE MODUL",
        "phase": "baseline",
        "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "INITIALIZING",
        "environment": {},
    }
    try:
        db_name = assert_upgrade_target_env(env)
        print(f" -> [Safety Guard PASS] Baseline database disposable '{db_name}'.")
        meta = introspect_runtime_environment(env)
        report["environment"] = meta
        oracle = FullDatasetCanonicalOracle(REG_PATH)
        expected_versions = expected_module_versions()

        print("\n[Baseline 1/4] Memuat closing Juli 2026 (fase 1) melalui loader produksi...")
        t0 = time.time()
        adapter_july = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-07-31",
            enforce_invoice_cutoff=True,
        )
        adapter_july.run_all()
        _commit(env)
        audit_database_against_oracle_july(env, oracle)
        july_rows = capture_july_aml_multiset(env)
        july_digest = digest_payload(july_rows)
        report["phase1_closing_july"] = {
            "duration_seconds": round(time.time() - t0, 2),
            "stats": dict(adapter_july.stats),
            "july_aml_lines": len(july_rows),
        }
        print(f" -> [Baseline 1/4 PASS] Audit closing Juli valid; {len(july_rows)} baris AML Juli.")

        print("\n[Baseline 2/4] Memuat carry-forward 1 Agustus 2026 (fase 2)...")
        t0 = time.time()
        adapter_august = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter_august.run_all()
        _commit(env)
        audit_database_against_oracle_august(env, oracle)
        verify_anti_fallback_salespersons(env)
        report["phase2_opening_august"] = {
            "duration_seconds": round(time.time() - t0, 2),
            "stats": dict(adapter_august.stats),
        }
        print(" -> [Baseline 2/4 PASS] Audit pasca-1 Agustus valid; HPP/anti-fallback valid.")

        print("\n[Baseline 3/4] Mengambil deep state snapshot & inventaris integritas pra-upgrade...")
        snapshot = capture_deep_state_snapshot(env)
        schema_before = assert_schema_integrity(env)
        fk_before = assert_foreign_key_integrity(env)
        views_before = assert_view_xml_integrity(env)
        hpp_before = assert_hpp_hook_integrity(env)
        report["pre_upgrade_integrity"] = {
            "schema": schema_before,
            "foreign_keys": fk_before,
            "views": views_before,
            "hpp_hook": hpp_before,
            "counts": _record_counts(snapshot),
        }

        print("\n[Baseline 4/4] Menyuntikkan version skew + drift skema/view terkontrol...")
        version_skew = inject_previous_release_skew(env, expected_versions=expected_versions)
        schema_drift = inject_schema_drift(env)
        view_drift = inject_view_drift(env)
        report["injected_drift"] = {
            "version_skew": version_skew,
            "schema_drift": schema_drift,
            "view_drift": view_drift,
        }

        state = {
            "schema_version": BASELINE_STATE_SCHEMA_VERSION,
            "phase": "persistent-baseline",
            "database": db_name,
            "commit_sha": meta.get("commit_sha"),
            "image_info": meta.get("image_info"),
            "github_run_id": meta.get("github_run_id"),
            "business_timezone": meta.get("business_timezone"),
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "expected_versions": expected_versions,
            "module_registry": inventory_module_registry(env, expected_versions=expected_versions),
            "record_counts": _record_counts(snapshot),
            "snapshot_digests": snapshot_digest(snapshot),
            "july_aml_digest": july_digest,
            "july_aml_lines": len(july_rows),
            "canonical_hashes": meta.get("canonical_hashes", {}),
            "version_skew_injected": version_skew,
            "schema_drift_injected": schema_drift,
            "view_drift_injected": view_drift,
            "view_drift_xmlids": list(VIEW_DRIFT_XMLIDS),
        }
        state_path = out / BASELINE_STATE_FILENAME
        _write_json(state_path, state)
        report["baseline_state_path"] = str(state_path)
        report["status"] = "SUCCESS"
        report["total_duration_seconds"] = round(time.time() - started, 2)
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(f" -> [Baseline PASS] State persisten disimpan: {state_path}")
        print("UPGRADE_BASELINE_PHASE=SUCCESS")
    except Exception as exc:  # noqa: BLE001
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["total_duration_seconds"] = round(time.time() - started, 2)
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(f"\n[FATAL] Fase baseline gagal: {exc}\n{traceback.format_exc()}", file=sys.stderr)
        raise
    finally:
        try:
            _write_json(out / BASELINE_REPORT_FILENAME, report)
            _write_summary(out / "upgrade_baseline_summary.md", _baseline_summary(report))
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Gagal menulis laporan baseline: {exc}", file=sys.stderr)
    return report


def _baseline_summary(report: dict) -> str:
    env_meta = report.get("environment", {}) or {}
    phase1 = report.get("phase1_closing_july", {}) or {}
    phase2 = report.get("phase2_opening_august", {}) or {}
    drift = report.get("injected_drift", {}) or {}
    return f"""# Ringkasan Baseline Persisten Sebelum Upgrade Modul

- **Status:** {report.get('status')}
- **Database:** `{env_meta.get('database', 'unknown')}`
- **Commit SHA:** `{env_meta.get('commit_sha', 'unknown')}`
- **Image:** `{env_meta.get('image_info', 'unknown')}`
- **Durasi total:** {report.get('total_duration_seconds', '-')} detik

## Fase
| Fase | Durasi | Ringkasan |
|---|---|---|
| Fase 1 Closing Juli 2026 | {phase1.get('duration_seconds', '-')} s | {phase1.get('july_aml_lines', '-')} baris AML Juli |
| Fase 2 Carry-Forward 1 Agustus 2026 | {phase2.get('duration_seconds', '-')} s | audit pasca-1 Agustus PASS |

## Drift Terkontrol yang Disuntikkan [A]
- Version skew: {json.dumps(drift.get('version_skew', {}), default=str)}
- Schema drift: {json.dumps(drift.get('schema_drift', []), default=str)}
- View drift: {json.dumps(drift.get('view_drift', []), default=str)}
""" + (
        f"\n## Kegagalan\n- `{report.get('error')}`\n```\n{report.get('traceback', '')}\n```\n"
        if report.get("status") != "SUCCESS" else ""
    )


# ---------------------------------------------------------------------------
# Fase verify: integritas pasca-upgrade + replay zero-drift + audit oracle
# ---------------------------------------------------------------------------


def run_upgrade_baseline_verification(env, baseline_state_path=None, output_dir=None) -> dict:
    """Memverifikasi integritas pasca-upgrade dan replay idempotensi zero-drift."""
    out = _output_dir(output_dir)
    started = time.time()
    report = {
        "title": "PEMBUKTIAN UPGRADE MODUL DARI BASELINE PERSISTEN + REPLAY IDEMPOTENSI",
        "phase": "verify",
        "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "INITIALIZING",
        "environment": {},
        "checks": {},
    }
    try:
        db_name = assert_upgrade_target_env(env)
        print(f" -> [Safety Guard PASS] Verify database disposable '{db_name}'.")
        meta = introspect_runtime_environment(env)
        report["environment"] = meta

        state_path = baseline_state_path or (out / BASELINE_STATE_FILENAME)
        state = load_baseline_state(state_path, expected_database=db_name)
        report["baseline_state"] = {
            "path": str(state_path),
            "captured_at": state.get("captured_at"),
            "commit_sha": state.get("commit_sha"),
            "record_counts": state.get("record_counts", {}),
        }

        # 1. Kontrak proses upgrade nyata (exit code + log).
        exit_code_raw = os.environ.get("UPGRADE_EXIT_CODE")
        log_path = Path(os.environ.get("UPGRADE_LOG_PATH", "/tmp/upgrade_odoo.log"))
        if exit_code_raw is None:
            report["checks"]["upgrade_process"] = {
                "status": "NOT_PROVIDED",
                "note": "UPGRADE_EXIT_CODE tidak disediakan; jalankan lewat workflow upgrade-runtime.",
            }
            print(" -> [WARN] Kontrak proses upgrade tidak disediakan (mode manual).")
        else:
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            contract = validate_upgrade_exit_code(int(exit_code_raw), log_text)
            contract["log_path"] = str(log_path)
            report["checks"]["upgrade_process"] = contract
            print(
                f" -> [Upgrade Process PASS] exit={contract['exit_code']} "
                f"log_lines={contract['log_lines']} corruption=0"
            )

        # 2. Registry modul & versi manifest.
        registry = assert_module_registry_integrity(env, expected_versions=state["expected_versions"])
        report["checks"]["module_registry"] = registry
        version_summary = ", ".join(
            f"{name}={info['latest_version']}" for name, info in registry["modules"].items()
        )
        print(f" -> [Registry PASS] {version_summary}")

        # 3. Integritas DDL & pemulihan drift skema terkontrol.
        schema = assert_schema_integrity(env)
        drift_repair = repair_schema_drift_targets(env)
        schema["drift_repair"] = drift_repair
        report["checks"]["schema"] = schema
        print(
            f" -> [DDL PASS] {schema['checked_fields']} kolom modul terverifikasi; "
            f"drift dipulihkan={len(drift_repair['repaired_columns'])}"
        )

        # 4. Integritas relasi foreign key.
        fk = assert_foreign_key_integrity(env)
        report["checks"]["foreign_keys"] = fk
        print(f" -> [FK PASS] {fk['checked_relations']} relasi many2one bebas orphan.")

        # 5. Integritas view XML + pemulihan drift view terkontrol.
        views = assert_view_xml_integrity(env, required_xmlids=state.get("view_drift_xmlids"))
        report["checks"]["views"] = views
        print(
            f" -> [View XML PASS] {views['checked_views']} view valid; "
            f"drift dipulihkan={views['restored_drift_views']}"
        )

        # 6. Hook integritas akuntansi HPP.
        hpp = assert_hpp_hook_integrity(env)
        report["checks"]["hpp_hook"] = hpp
        print(
            f" -> [HPP Hook PASS] {hpp['seed_invoices']} faktur seed, "
            f"{hpp['duplicate_hpp_lines']} baris HPP duplikat, {hpp['outbound_moves']} move outbound."
        )

        # 7. Replay idempotensi zero-creation.
        print("\n[Replay] Menjalankan ulang CanonicalPerpetualAdapter.run_all() pasca-upgrade...")
        t0 = time.time()
        adapter = CanonicalPerpetualAdapter(
            env,
            reg_path=REG_PATH,
            cutoff_date="2026-08-01",
            enforce_invoice_cutoff=True,
        )
        adapter.run_all()
        _commit(env)
        replay = assert_replay_zero_creation(adapter.stats)
        replay["duration_seconds"] = round(time.time() - t0, 2)
        replay["stats_raw"] = dict(adapter.stats)
        report["checks"]["replay_idempotency"] = replay
        print(
            f" -> [Replay PASS] 0 record baru; skip SO={replay['skipped_counters']['skipped_so']}, "
            f"invoice={replay['skipped_counters']['skipped_invoices']} ({replay['duration_seconds']} s)."
        )

        # 8. Zero-drift deep state snapshot terhadap baseline.
        snapshot = capture_deep_state_snapshot(env)
        digests = snapshot_digest(snapshot)
        drift = compare_snapshot_digests(state["snapshot_digests"], digests)
        drift["counts"] = _record_counts(snapshot)
        report["checks"]["zero_drift"] = drift
        print(f" -> [Zero-Drift PASS] {len(drift['entities'])} entitas identik dengan baseline.")

        # 9. Imutabilitas closing Juli.
        immutable = assert_july_closing_immutable(env, state["july_aml_digest"])
        report["checks"]["july_immutability"] = immutable
        print(f" -> [Immutabilitas PASS] {immutable['july_aml_lines']} baris AML Juli tidak berubah.")

        # 10. Audit produksi independen pasca-upgrade.
        oracle = FullDatasetCanonicalOracle(REG_PATH)
        audit_database_against_oracle_august(env, oracle)
        verify_anti_fallback_salespersons(env)
        report["checks"]["oracle_audit_august"] = {"status": "PASS"}
        report["checks"]["anti_fallback_salespersons"] = {"status": "PASS"}
        print(" -> [Audit Oracle PASS] Kuantitas, reservasi, GL, dan salesperson valid.")

        report["status"] = "SUCCESS"
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["total_duration_seconds"] = round(time.time() - started, 2)
        print("\nUPGRADE_REPLAY_ZERO_DRIFT=PASS")
        print("UPGRADE_VERIFY_PHASE=SUCCESS")
    except Exception as exc:  # noqa: BLE001
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["total_duration_seconds"] = round(time.time() - started, 2)
        print(f"\n[FATAL] Fase verify gagal: {exc}\n{traceback.format_exc()}", file=sys.stderr)
        raise
    finally:
        try:
            _write_json(out / VERIFY_REPORT_FILENAME, report)
            _write_summary(out / VERIFY_SUMMARY_FILENAME, _verify_summary(report))
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Gagal menulis laporan verify: {exc}", file=sys.stderr)
    return report


def _verify_summary(report: dict) -> str:
    checks = report.get("checks", {}) or {}
    env_meta = report.get("environment", {}) or {}
    process = checks.get("upgrade_process", {}) or {}
    registry = checks.get("module_registry", {}) or {}
    schema = checks.get("schema", {}) or {}
    fk = checks.get("foreign_keys", {}) or {}
    views = checks.get("views", {}) or {}
    hpp = checks.get("hpp_hook", {}) or {}
    replay = checks.get("replay_idempotency", {}) or {}
    drift = checks.get("zero_drift", {}) or {}
    immutable = checks.get("july_immutability", {}) or {}
    ok = report.get("status") == "SUCCESS"

    module_rows = "".join(
        f"| `{name}` | {info.get('state')} | {info.get('latest_version')} "
        f"| {info.get('manifest_version')} |\n"
        for name, info in (registry.get("modules", {}) or {}).items()
    )
    skipped_rows = "".join(
        f"| `{key}` | {value} |\n" for key, value in (replay.get("skipped_counters", {}) or {}).items()
    )
    text = f"""# Ringkasan Pembuktian Upgrade Modul dari Baseline Persisten + Replay Idempotensi

- **Status:** {report.get('status')}
- **Database:** `{env_meta.get('database', 'unknown')}`
- **Commit SHA:** `{env_meta.get('commit_sha', 'unknown')}`
- **Image:** `{env_meta.get('image_info', 'unknown')}`
- **Durasi verify:** {report.get('total_duration_seconds', '-')} detik
- **Timezone bisnis:** `Asia/Makassar (WITA, UTC+8)`

## 1. Kontrak Proses Upgrade Nyata
- Status: **{process.get('status', 'NOT_PROVIDED')}**
- Exit code: `{process.get('exit_code', '-')}`
- Baris log diperiksa: `{process.get('log_lines', '-')}`
- Temuan registry corruption: `{process.get('corruption_findings', [])}`

## 2. Registry Modul
| Modul | State | Latest Version | Manifest |
|---|---|---|---|
{module_rows}
## 3. Integritas Skema, Relasi, dan View XML
- Kolom modul diverifikasi: **{schema.get('checked_fields', '-')}** (hilang: {len(schema.get('missing_columns', []))})
- Kolom drift skema dipulihkan: **{len((schema.get('drift_repair', {}) or {}).get('repaired_columns', []))}**
- Relasi many2one diperiksa: **{fk.get('checked_relations', '-')}** (orphan: {len(fk.get('orphans', []))})
- View XML valid: **{views.get('checked_views', '-')}** (dipulihkan: {views.get('restored_drift_views', [])})

## 4. Hook Integritas Akuntansi HPP
- Override modul: `{hpp.get('method_module', '-')}`
- Faktur komersial seed: **{hpp.get('seed_invoices', '-')}**
- Baris HPP duplikat pada faktur seed: **{hpp.get('duplicate_hpp_lines', '-')}** (wajib 0)
- Delivery outbound selesai: **{hpp.get('outbound_moves', '-')}** (tanpa COGS: {hpp.get('outbound_missing_cogs', '-')})

## 5. Replay Idempotensi
- Total record baru dibuat: **{replay.get('total_created', '-')}**
- Durasi replay: {replay.get('duration_seconds', '-')} detik
| Counter Skip | Nilai |
|---|---|
{skipped_rows}
## 6. Zero-Drift & Imutabilitas
- Entitas snapshot identik: **{len(drift.get('entities', []))}**
- Entitas drift: {drift.get('drifted_entities', [])}
- Baris AML Juli tidak berubah: **{immutable.get('july_aml_lines', '-')}**

## 7. Audit Oracle Independen
- Audit `audit_database_against_oracle_august`: **{'PASS' if ok else 'FAIL / INCOMPLETE'}**
- Anti-fallback salesperson: **{'PASS' if ok else 'FAIL / INCOMPLETE'}**
"""
    if not ok and report.get("error"):
        text += f"\n## 8. Kegagalan\n- `{report.get('error')}`\n```\n{report.get('traceback', '')}\n```\n"
    return text


# ---------------------------------------------------------------------------
# CLI: kontrak log upgrade (dipakai workflow sebelum fase verify)
# ---------------------------------------------------------------------------


def _cli(argv) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Runner Prioritas 3: upgrade modul dari baseline persisten + replay idempotensi."
    )
    parser.add_argument("--check-log", help="Path log proses `odoo -u` untuk divalidasi.")
    parser.add_argument("--exit-code", type=int, help="Exit code proses `odoo -u`.")
    parser.add_argument("--db", help="Nama database target upgrade (wajib disposable).")
    args = parser.parse_args(argv)

    if not args.check_log:
        parser.error("--check-log wajib diisi untuk mode kontrak log upgrade.")

    try:
        db_name = assert_upgrade_target_database(args.db or "")
        log_path = Path(args.check_log)
        if not log_path.exists():
            raise RuntimeError(f"[UPGRADE-FAIL] Log upgrade tidak ditemukan: {log_path}")
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        result = validate_upgrade_exit_code(args.exit_code if args.exit_code is not None else -1, log_text)
        result["database"] = db_name
        result["log_path"] = str(log_path)
        print("UPGRADE_LOG_CONTRACT=" + json.dumps(result, default=str))
        print("UPGRADE_PROCESS_CONTRACT=PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[UPGRADE-FAIL] {exc}", file=sys.stderr)
        print("UPGRADE_PROCESS_CONTRACT=FAILED")
        return 1


def _run_in_shell(shell_env):
    phase = (os.environ.get("UPGRADE_PHASE") or "verify").strip().lower()
    output_dir = os.environ.get("UPGRADE_OUTPUT_DIR") or None
    if phase == "baseline":
        capture_persistent_baseline(shell_env, output_dir=output_dir)
    elif phase == "verify":
        run_upgrade_baseline_verification(shell_env, output_dir=output_dir)
    else:
        raise RuntimeError(
            f"[upgrade] UPGRADE_PHASE tidak dikenal: '{phase}' (pilih 'baseline' atau 'verify')."
        )


if "env" in globals():
    _run_in_shell(globals()["env"])
elif __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
