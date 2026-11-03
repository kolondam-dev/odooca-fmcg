# PR79 correction by codex

Original source finding: STRtree predicate reversed. Use covered_by; sort containers. Ten geometry tests cover assigned/other interior and boundary, outside-all controls, direct polygon oracle and input immutability. Regenerated report:44 outside assigned,38 in another district,6 outside all. Inputs unchanged. Main ca8b49c integrated; final CI pending. User authorizes correction and merge after PASS. No deployment.

Original PR79 addenda retained below; main HANDOFF and logs stay byte-identical.

## 2026-11-03T08:24:05+07:00 — claude-dev — PR-4: audit coverage outlet vs poligon kecamatan (laporan)
**Branch:** `agen/geo-coverage-audit` (basis `origin/main` = `69149f6`)
**Status:** siap PR; menunggu PR-3 (#78) untuk rujukan loader

### Perubahan:
- `scripts/ops/audit_geo_coverage.py` (baru, baca-saja): menguji 354 outlet `data/seed/partners_354.csv` terhadap 171 poligon `data/geo/sulut_districts.geojson` (shapely + STRtree). Menghasilkan markdown dan JSON opsional; `--fail-on-outside` tersedia untuk gate opsional.
- `docs/reviews/GEO_COVERAGE_AUDIT_2026-11-03.md` (baru): laporan 44 outlet di luar poligon — Kawangkoan 4, Wenang 11, Wanea 29 — dan **0** yang jatuh ke poligon kecamatan lain. Semua 44 berada di luar seluruh poligon Sulut (koordinat sintetis).
- `tests/test_geo_coverage_audit.py` (baru, 7 uji): angka baseline, 0 konflik pemetaan, laporan yang di-commit identik dengan generator, masukan tidak berubah (sha256), mode tanpa geometri.

### Keputusan yang dijaga:
- [F] D4=A: temuan dilaporkan, **tidak ada** auto-edit koordinat outlet maupun kode pos.
- [F] Pemetaan kode legacy diambil dari seed `id_district_data.xml` (ada di `main`) dan dicek silang dengan `data/master/legacy_geo_mapping.csv` (PR-3) bila tersedia — laporan identik sebelum/sesudah PR-3 mendarat.
- [F] Temuan kode pos (informasi): 40 dari 354 zip partner dan 9 dari 17 kode pos kelurahan legacy berbeda dari master.
- [A] Tidak ada perubahan `data/seed`, `data/registers`, `data/master`, poligon, atau DB.

### Verifikasi lokal:
- [F] `ruff check .` PASS; `python scripts/check_manifests.py` PASS (10 addon).
- [F] `python -m unittest tests.test_geo_coverage_audit` 7/7 PASS (termasuk dengan dan tanpa `legacy_geo_mapping.csv`).
- [BU] CI PR-4 belum dijalankan.



[2026-11-03T08:24:05+07:00] [INFO] PR-4 audit coverage outlet vs poligon kecamatan
- scripts/ops/audit_geo_coverage.py (baru, baca-saja): 354 outlet diuji terhadap 171 poligon; 44 di luar (Kawangkoan 4, Wenang 11, Wanea 29), tidak ada yang jatuh ke poligon kecamatan lain.
- Pemetaan kode legacy diambil dari seed id_district_data.xml dan dicek silang dengan data/master/legacy_geo_mapping.csv bila ada; 0 konflik.
- Temuan kode pos dilaporkan tanpa diubah: 40 dari 354 zip partner dan 9 dari 17 kode pos kelurahan legacy berbeda dari master (D4=A).
- docs/reviews/GEO_COVERAGE_AUDIT_2026-11-03.md dihasilkan skrip; tests/test_geo_coverage_audit.py 7/7 PASS termasuk uji laporan tidak basi dan masukan tidak berubah.
- Tidak ada perubahan data seed/registry/DB; tidak merge/deploy.
- Task managed by claude-dev agent at 2026-11-03T08:24:05+07:00
