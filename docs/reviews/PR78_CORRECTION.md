# PR78 correction by codex

Province writes restricted to empty states on verified active canonical Sulut identities. Other provinces/countries, archived/unverified records preserved. Company without verified partner geography requires GEO_PROVINCE_COMPANY_IDS; no partner geography FK writes. Loader preserves existing city province too. Native regressions cover mixed region, unknown/archive, dry-run, idempotence, explicit company and conflicting city province. Main ca8b49c and corrected PR79 head4fbc8e5 integrated; 33 local geo tests PASS. Final native CI pending. Both PR histories are retained; merging this integration will make corrected PR79 reachable from main too. User authorizes correction and merge after PASS. No deployment.

Original PR78 addenda retained below; main HANDOFF and logs stay byte-identical.

## 2026-11-03T08:12:30+07:00 — claude-dev — PR-3: backfill master wilayah Sulut + provinsi (15/171/1.839)
**Branch:** `agen/geo-master-loader` (basis `origin/main` = `69149f6`)
**Status:** PR [#78](https://github.com/kolondam-dev/odooca-fmcg/pull/78); CI 12/13 hijau pada `83296b0` (static, invariant-tests, seed-invariants, install-test 5m27s, init-test 5m15s, pwa-*); `upgrade-runtime` menyusul

### Perubahan:
- `scripts/ops/load_geo_master.py` (baru): loader idempoten `id.city`/`id.district`/`id.subdistrict` dari `data/master/*.csv` + `data/geo/sulut_districts.geojson`. Mengisi `kode_kemendagri`, `city_id`, `district_id`, koordinat, `area_km2`, bbox, `geojson_polygon`, `geom_source/quality/updated_at`. Tidak pernah mengganti `code` legacy (`KEC-*`/`KEL-*`) maupun nama record lama; `postal_code`/lat/lng kelurahan yang sudah terisi dipertahankan (D4=A).
- `scripts/ops/fix_geo_province.py` (baru): mengisi `state_id` Sulut pada company, `id.city`, `id.district` (related stored dihitung ulang), `id.coverage.area`, dan partner yang punya wilayah Sulut. Partner luar daerah tidak disentuh (D3=A: data-fix + laporan, tanpa constraint keras).
- `data/master/legacy_geo_mapping.csv` (baru, 37 baris): satu-satunya sumber pemetaan identitas legacy; 18 kecamatan + 17 kelurahan `mapped`, 2 kelurahan `legacy` (`KEL-BTG-GRW`, `KEL-TMH-PSL`) sesuai D5=B.
- `addons/id_base/data/id_district_data.xml`: `area_km2` untuk 17 kelurahan terpetakan, agar instalasi baru dan backfill DB lama konvergen (tanpa mengubah kode/nama/kode pos).
- `deploy/init.sh`: blok `geo_master_v1` dan `geo_province_v1` setelah `seed_pjp_workdays_v1`, sebelum Odoo dijalankan; mark hanya diset bila skrip sukses.
- `docs/geo/GEO_MASTER_LOADER.md` (baru): runbook (dry-run, env flag, idempotensi, verifikasi SQL, rollback, batasan). `docs/DEVELOPMENT.md` §7 diperbarui.
- `id_base` versi `19.0.1.3.0`.

### Verifikasi lokal:
- [F] `ruff check .` PASS; `python scripts/check_manifests.py` PASS (10 addon).
- [F] `python -m unittest tests.test_geo_master_data tests.test_geo_master_loader` 23/23 PASS (11 di antaranya kontrak loader baru: mapping, hierarki, bbox == seed XML, QA flag, area).
- [F] `python scripts/ops/verify_seed_invariants.py` PASS; `bash -n deploy/init.sh` PASS.
- [F] `addons/id_base/tests/test_geo_master_loader.py` (4 metode native: hierarki, identitas legacy+geometri, idempotensi loader, idempotensi fix provinsi) lulus di CI `install-test` (`83296b0`, 5m27s).
- [A] Loader tidak menyentuh `res.partner`, transaksi, akuntansi, stok, atau `data/registers`; 354 partner tetap memakai `district_id`/`subdistrict_id` lama.



[2026-11-03T08:13:02+07:00] [INFO] PR-3 backfill master wilayah Sulut + provinsi
- Loader idempoten scripts/ops/load_geo_master.py: 15 kota / 171 kecamatan / 1.839 desa dari data/master + geojson; kode dan nama legacy tidak diubah.
- scripts/ops/fix_geo_province.py mengisi state_id company, id.city, id.district (related stored), coverage area, dan partner Sulut; partner luar daerah tidak disentuh.
- data/master/legacy_geo_mapping.csv (37 baris) menjadi satu-satunya sumber pemetaan legacy; 17 kelurahan mapped, 2 legacy (KEL-BTG-GRW, KEL-TMH-PSL) sesuai D5=B.
- Seed id_district_data.xml mendapat area_km2 untuk 17 kelurahan terpetakan agar instalasi baru dan backfill konvergen.
- deploy/init.sh: mark geo_master_v1 dan geo_province_v1 setelah seed_pjp_workdays_v1; mark hanya diset bila skrip sukses.
- Verifikasi lokal: ruff PASS, 10 manifest PASS, 22 unittest (12 data + 11 loader + 1 lama) PASS, verify_seed_invariants PASS, bash -n PASS.
- Uji native addons/id_base/tests/test_geo_master_loader.py (4 metode) menunggu CI install-test; belum merge/deploy.
- Task managed by claude-dev agent at 2026-11-03T08:13:02+07:00

[2026-11-03T08:44:17+07:00] [INFO] PR-3 CI hijau (12/13) dan koreksi perintah runbook
- CI SHA 83296b0: static, invariant-tests (4m47s), seed-invariants, install-test (5m27s), init-test (5m15s), pwa-* PASS; hanya upgrade-runtime yang masih berjalan.
- install-test menjalankan 4 metode TestGeoMasterLoader (hierarki, identitas legacy+geometri, idempotensi loader, idempotensi provinsi) tanpa ERROR/Traceback.
- Runbook docs/geo/GEO_MASTER_LOADER.md dikoreksi: perintah docker compose exec dibungkus sh -c agar \ diekspansi di dalam kontainer, bukan oleh shell host.
- Tidak ada perubahan kode program pada commit koreksi ini.
- Task managed by claude-dev agent at 2026-11-03T08:44:17+07:00
