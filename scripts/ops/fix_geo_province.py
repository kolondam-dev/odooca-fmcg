#!/usr/bin/env python3
"""Isi `state_id` (provinsi) yang kosong pada data Sulawesi Utara.

Dijalankan di dalam Odoo shell:

    odoo shell -c /tmp/odoo.conf -d <db> --no-http < scripts/ops/fix_geo_province.py

Konteks: `deploy/init.sh` (`company_profile_v2`) dan seed lama tidak pernah menulis
provinsi, sehingga `state_id` kosong pada company, partner outlet, coverage area,
dan `id.city`. Master provinsi sudah ada di Odoo core: `base.state_id_sa`
("Sulawesi Utara", kode `SA`).

Cakupan (idempoten, hanya menulis bila berbeda):

- `res.company` (semua perusahaan aktif) -> Sulawesi Utara
- `id.city` (semua) -> Sulawesi Utara
- `id.district`: `state_id` adalah related stored dari `city_id.state_id`; record
  yang masih kosong dipaksa hitung ulang (tanpa menulis field related langsung)
- `id.coverage.area` (semua) -> Sulawesi Utara
- `res.partner` yang punya `district_id`/`subdistrict_id` Sulut -> provinsi wilayahnya

Partner tanpa wilayah Sulut (mis. prinsipal/vendor luar daerah) **tidak** disentuh;
hanya dilaporkan jumlahnya.

Variabel lingkungan:

    GEO_PROVINCE_DRY_RUN=1   hitung perubahan tanpa menulis ke DB
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

    def _write(self, records, values, key):
        if not records:
            self.report[key] = 0
            return 0
        self.report[key] = len(records)
        if not self.dry_run:
            records.write(values)
        return len(records)

    def _companies(self):
        Company = self.env["res.company"].sudo().with_context(active_test=False)
        records = Company.search([]).filtered(lambda record: record.state_id != self.province)
        return self._write(records, {"state_id": self.province.id}, "companies")

    def _cities(self):
        City = self.env["id.city"].sudo().with_context(active_test=False)
        records = City.search([]).filtered(lambda record: record.state_id != self.province)
        return self._write(records, {"state_id": self.province.id}, "cities")

    def _districts(self):
        """`state_id` related stored: hitung ulang record yang masih kosong."""
        District = self.env["id.district"].sudo().with_context(active_test=False)
        stale = District.search([("city_id", "!=", False), ("state_id", "=", False)])
        self.report["districts"] = len(stale)
        if stale and not self.dry_run:
            self.env.add_to_compute(District._fields["state_id"], stale)
            self.env.flush_all()
        return len(stale)

    def _coverage_areas(self):
        Area = self.env["id.coverage.area"].sudo().with_context(active_test=False)
        records = Area.search([]).filtered(lambda record: record.state_id != self.province)
        return self._write(records, {"state_id": self.province.id}, "coverage_areas")

    def _partners(self):
        Partner = self.env["res.partner"].sudo().with_context(active_test=False, tracking_disable=True)
        with_village_only = Partner.search([("district_id", "=", False), ("subdistrict_id", "!=", False)])
        self.report["partners_village_only"] = len(with_village_only)
        attached = Partner.browse()
        for partner in with_village_only:
            district = partner.subdistrict_id.district_id
            if not district:
                continue
            if not self.dry_run:
                partner.write({"district_id": district.id})
            attached |= partner

        # `attached` melengkapi hasil search saat dry-run (penulisan belum terjadi).
        candidates = Partner.search([("district_id", "!=", False)]) | attached
        stale = candidates.filtered(
            lambda record: record.state_id != (record.district_id.city_id.state_id or self.province)
        )
        self.report["partners"] = len(stale)
        if stale and not self.dry_run:
            # Semua kecamatan pada master ini berada di Sulawesi Utara; filter di atas
            # memakai provinsi sebagai fallback saat city belum punya provinsi.
            stale.write({"state_id": self.province.id})
        self.report["partners_without_geo"] = Partner.search_count(
            [("district_id", "=", False), ("subdistrict_id", "=", False)]
        )

    def run(self):
        if self.province is None:
            raise RuntimeError(f"[geo_province] provinsi {PROVINCE_XMLID} tidak ditemukan")
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
