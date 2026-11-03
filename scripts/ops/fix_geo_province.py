#!/usr/bin/env python3
"""Isi `state_id` (provinsi) yang kosong pada data Sulawesi Utara.

Dijalankan di dalam Odoo shell:

    odoo shell -c /tmp/odoo.conf -d <db> --no-http < scripts/ops/fix_geo_province.py

Konteks: `deploy/init.sh` (`company_profile_v2`) dan seed lama tidak pernah menulis
provinsi, sehingga `state_id` kosong pada company, partner outlet, coverage area,
dan `id.city`. Master provinsi sudah ada di Odoo core: `base.state_id_sa`
("Sulawesi Utara", kode `SA`).

Cakupan: hanya state_id kosong pada identitas aktif yang terverifikasi dari
kode master Sulut. Provinsi terisi, negara lain, record arsip dan identitas tidak
terverifikasi dipertahankan. Tidak mengubah district_id/subdistrict_id partner.
Area dibatasi XMLID seed Sulut. Company memakai wilayah partner yang terverifikasi,
atau ID operator eksplisit (tetap tidak menimpa state_id yang terisi).

Variabel lingkungan:
    GEO_PROVINCE_DRY_RUN=1       hitung tanpa menulis
    GEO_PROVINCE_COMPANY_IDS=1,2 target company eksplisit tanpa relasi wilayah
"""

import os
import sys

PROVINCE_XMLID = "base.state_id_sa"


def env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


class ProvinceFixer:
    def __init__(self, env, dry_run=False):
        self.env = env
        self.dry_run = dry_run
        self.province = env.ref(PROVINCE_XMLID, raise_if_not_found=False)
        self.report = {}

    def _scope(self):
        """Canonical identities, never a blanket province/name assumption."""
        import csv
        from pathlib import Path

        candidates = [Path("data/master"), Path("/opt/data/master")]
        if "__file__" in globals():
            candidates.append(Path(__file__).resolve().parents[2] / "data/master")
        root = next((p for p in candidates if (p / "sulut_kab_kota.csv").is_file()), None)
        if root is None:
            raise RuntimeError("[geo_province] canonical Sulut master not found")
        def codes(filename):
            with (root / filename).open(encoding="utf-8-sig", newline="") as handle:
                return [row["kode_kemendagri"] for row in csv.DictReader(handle)]
        cities = self.env["id.city"].sudo().search([
            ("active", "=", True), ("kode_kemendagri", "in", codes("sulut_kab_kota.csv"))])
        cities = cities.filtered(lambda r: not r.state_id or r.state_id == self.province)
        self.districts = self.env["id.district"].sudo().search([
            ("active", "=", True), ("city_id", "in", cities.ids),
            ("kode_kemendagri", "in", codes("sulut_kecamatan.csv"))])
        self.villages = self.env["id.subdistrict"].sudo().search([
            ("active", "=", True), ("district_id", "in", self.districts.ids),
            ("kode_kemendagri", "in", codes("sulut_desa_kelurahan.csv"))])
        self.cities = cities

    def _fill(self, records, key):
        # Existing states (including conflicts) and archived records are not corrected implicitly.
        eligible = records.filtered(lambda r: r.active and not r.state_id)
        self.report[key] = len(eligible)
        self.report[key + "_preserved"] = len(records) - len(eligible)
        if eligible and not self.dry_run:
            eligible.write({"state_id": self.province.id})

    def _partner_in_scope(self, partner):
        if partner.country_id and partner.country_id != self.province.country_id:
            return False
        if partner.subdistrict_id:
            if partner.subdistrict_id not in self.villages:
                return False
            if partner.district_id and partner.district_id != partner.subdistrict_id.district_id:
                return False
            return True
        return partner.district_id in self.districts

    def _companies(self):
        raw_ids = os.environ.get("GEO_PROVINCE_COMPANY_IDS", "").strip()
        try:
            explicit = {int(v.strip()) for v in raw_ids.split(",") if v.strip()}
            if any(v <= 0 for v in explicit):
                raise ValueError("nonpositive company ID")
        except ValueError as exc:
            raise ValueError("[geo_province] invalid GEO_PROVINCE_COMPANY_IDS") from exc
        companies = self.env["res.company"].sudo().with_context(active_test=False).search([])
        scoped = companies.filtered(lambda r: r.active and
            (not r.country_id or r.country_id == self.province.country_id) and
            (r.id in explicit or self._partner_in_scope(r.partner_id)))
        self.report["companies_unverified"] = len(companies - scoped)
        self._fill(scoped, "companies")

    def _cities(self):
        self._fill(self.cities, "cities")

    def _districts(self):
        # Only verified, active Sulut districts whose stored relation needs recomputation.
        stale = self.districts.filtered(lambda r: not r.state_id and r.city_id.state_id == self.province)
        self.report["districts"] = len(stale)
        if stale and not self.dry_run:
            self.env.add_to_compute(self.districts._fields["state_id"], stale)
            self.env.flush_all()

    def _coverage_areas(self):
        Area = self.env["id.coverage.area"].sudo()
        verified = Area.browse()
        for xmlid in ("area_mnd_urban", "area_tmh_hinterland", "area_btg_port", "area_minut_rural"):
            record = self.env.ref("id_base." + xmlid, raise_if_not_found=False)
            if record:
                verified |= record
        self._fill(verified, "coverage_areas")

    def _partners(self):
        Partner = self.env["res.partner"].sudo().with_context(active_test=False, tracking_disable=True)
        candidates = Partner.search(["|", ("district_id", "!=", False), ("subdistrict_id", "!=", False)])
        scoped = candidates.filtered(lambda r: r.active and self._partner_in_scope(r))
        self.report["partners_unverified"] = len(candidates - scoped)
        # Read village-only geography without assigning district_id or changing any geographic FK.
        self.report["partners_village_only"] = len(scoped.filtered(lambda r: not r.district_id))
        self._fill(scoped, "partners")
        self.report["partners_without_geo"] = Partner.search_count(
            [("district_id", "=", False), ("subdistrict_id", "=", False)])

    def run(self):
        if not self.province:
            raise RuntimeError(f"[geo_province] province {PROVINCE_XMLID} not found")
        self._scope()
        self._companies()
        self._cities()
        self._districts()
        self._coverage_areas()
        self._partners()
        if not self.dry_run:
            self.env.flush_all()
        return self.report


def print_report(report, dry_run):
    prefix = "[geo_province] DRY-RUN" if dry_run else "[geo_province]"
    for key in sorted(report):
        print(f"{prefix} {key}: {report[key]}")
    print(f"{prefix} provinsi: {PROVINCE_XMLID}")


def main(env):
    dry_run = env_flag("GEO_PROVINCE_DRY_RUN")
    report = ProvinceFixer(env, dry_run=dry_run).run()
    print_report(report, dry_run)
    if dry_run:
        print("[geo_province] DRY-RUN selesai; tidak ada perubahan yang di-commit.")
        return report
    env.cr.commit()
    print("[geo_province] selesai dan di-commit.")
    return report


if "env" in globals():
    try:
        main(globals()["env"])
    except Exception:
        globals()["env"].cr.rollback()
        import traceback

        traceback.print_exc()
        raise
elif __name__ == "__main__":  # pragma: no cover - dijalankan di luar Odoo shell
    sys.exit("[geo_province] skrip ini harus dijalankan di dalam Odoo shell (objek 'env' tidak ada).")
