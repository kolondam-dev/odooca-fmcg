# Runbook: Backfill Master Wilayah Sulut

**Cakupan:** `scripts/ops/load_geo_master.py` (master wilayah) dan
`scripts/ops/fix_geo_province.py` (provinsi `state_id`).
**Konteks keputusan:** `docs/reviews/GEO_BASELINE_2026-11-01.md` §4 dan §6.
**Dataset & provenance:** `docs/geo/SULUT_ADMINISTRASI_GEO.md`.

Dokumen ini menjelaskan **apa yang diubah**, **apa yang tidak pernah diubah**, dan cara
menjalankan/mengulang kedua skrip tanpa merusak data operasional.

## 1. Mengapa perlu skrip, bukan hanya upgrade modul

Seed `addons/id_base/data/id_city_data.xml` dan `id_district_data.xml` memakai
`noupdate="1"`. Artinya:

| Kondisi | Efek |
|---|---|
| DB kosong + `-i id_base` | 15 kota, 18 kecamatan, 19 kelurahan ter-seed dari XML |
| DB lama + `-u id_base` | record geo **tidak** diperbarui (noupdate) |
| DB lama + skrip ini | hierarki dilengkapi menjadi 15 / 171 / 1.839, field baru diisi |

Jadi instalasi baru tetap butuh skrip untuk melengkapi 153 kecamatan dan 1.820
desa/kelurahan sisanya; instalasi lama butuh skrip untuk mengisi `kode_kemendagri`,
`city_id`, geometri, dan `state_id` pada record yang sudah ada.

## 2. Sumber kebenaran

| Berkas | Isi | Dipakai untuk |
|---|---|---|
| `data/master/sulut_kab_kota.csv` | 15 kabupaten/kota | `id.city` |
| `data/master/sulut_kecamatan.csv` | 171 kecamatan | `id.district` |
| `data/master/sulut_desa_kelurahan.csv` | 1.839 desa/kelurahan | `id.subdistrict` |
| `data/master/legacy_geo_mapping.csv` | 37 record legacy `KEC-*`/`KEL-*` | identitas record lama |
| `data/geo/sulut_districts.geojson` | 171 poligon kecamatan | `geojson_polygon`, bbox, `geom_*` |

`legacy_geo_mapping.csv` adalah **satu-satunya** sumber pemetaan identitas. Loader tidak
pernah menebak dari nama. Dua kelurahan berstatus `legacy` (tanpa `kode_kemendagri`):

| Kode | Nama | Alasan |
|---|---|---|
| `KEL-BTG-GRW` | Girian Weru | master hanya punya Girian Weru Satu/Dua (1:2) |
| `KEL-TMH-PSL` | Paslaten Satu | satu-satunya Paslaten Satu ada di Tomohon Timur |

Keduanya tetap ada, ditandai `is_legacy = True`, dan tidak diberi kode Kemendagri.

## 3. Apa yang ditulis `load_geo_master.py`

| Model | Field |
|---|---|
| `id.city` | `kode_kemendagri`, `type`, `state_id`, `latitude`, `longitude`, `area_km2` (nama/kode hanya saat create) |
| `id.district` | `kode_kemendagri`, `city_id`, `city` (teks), `latitude`, `longitude`, `area_km2`, `bbox_xmin/ymin/xmax/ymax`, `geojson_polygon`, `geom_source`, `geom_quality`, `geom_updated_at` |
| `id.subdistrict` | `kode_kemendagri`, `district_id`, `area_km2`, `is_legacy`, `postal_code`/`latitude`/`longitude` **hanya bila masih kosong** |

Jaminan yang diuji otomatis (`tests/test_geo_master_loader.py`,
`addons/id_base/tests/test_geo_master_loader.py`):

1. **Idempoten.** Putaran kedua: `created = 0`, `updated = 0` untuk ketiga level.
2. **Identitas legacy stabil.** `code` (`KEC-*`/`KEL-*`) dan `name` record lama tidak diubah.
3. **Nilai operasional tidak ditimpa.** `postal_code`, `latitude`, `longitude` kelurahan
   yang sudah terisi dipertahankan (keputusan D4=A: laporan, bukan auto-ubah).
4. **Tidak menyentuh** `res.partner`, transaksi, akuntansi, stok, `data/registers`, atau CSV seed.
5. **Hierarki utuh.** Setiap kecamatan punya `city_id`; setiap desa punya `district_id`.
6. **Gagal keras bila dataset tidak sesuai kontrak** (15/171/1.839, kode duplikat, geojson
   tidak lengkap) — lebih baik berhenti daripada menulis data separuh.

`geom_updated_at` hanya berubah bila poligon/bbox benar-benar berubah, sehingga backfill
ulang tidak menghasilkan diff palsu.

## 4. Apa yang ditulis `fix_geo_province.py`

| Model | Aksi |
|---|---|
| `res.company` | `state_id = base.state_id_sa` |
| `id.city` | `state_id = Sulawesi Utara` |
| `id.district` | `state_id` related stored → dipaksa hitung ulang bila kosong (`env.add_to_compute`) |
| `id.coverage.area` | `state_id = Sulawesi Utara` |
| `res.partner` | hanya partner yang punya `district_id`/`subdistrict_id` Sulut |

Partner tanpa wilayah Sulut (prinsipal/vendor luar daerah) **tidak** disentuh; jumlahnya
hanya dilaporkan sebagai `partners_without_geo`.

Tidak ada constraint keras pada `state_id` (keputusan D3=A): provinsi adalah data-fix +
laporan, bukan aturan yang memblokir input.

## 5. Menjalankan manual

Di kontainer (sama seperti `deploy/init.sh`). Perhatikan: `$PGDATABASE`, `$PGUSER`, dan
`$PGPASSWORD` diekspansi **di dalam** kontainer, jadi perintah dibungkus `sh -c`.

```bash
# 1) Pratinjau: hitung perubahan tanpa menulis
docker compose exec -e GEO_LOAD_DRY_RUN=1 -T odoo \
  sh -c 'odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" --no-http' \
  < scripts/ops/load_geo_master.py

# 2) Terapkan
docker compose exec -T odoo \
  sh -c 'odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" --no-http' \
  < scripts/ops/load_geo_master.py

# 3) Provinsi (pratinjau lalu terapkan)
docker compose exec -e GEO_PROVINCE_DRY_RUN=1 -T odoo \
  sh -c 'odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" --no-http' \
  < scripts/ops/fix_geo_province.py
docker compose exec -T odoo \
  sh -c 'odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" --no-http' \
  < scripts/ops/fix_geo_province.py
```

Kredensial peran Odoo (`PGUSER`/`PGPASSWORD`) harus diset seperti `odoo_run` di
`deploy/init.sh`; jangan memakai superuser Postgres.

### Variabel lingkungan

| Variabel | Default | Efek |
|---|---|---|
| `GEO_LOAD_DRY_RUN` | mati | hitung + cetak laporan, tanpa `commit` |
| `GEO_LOAD_SKIP_POLYGON` | mati | lewati `geojson_polygon` (bbox tetap diisi); untuk DB berukuran besar |
| `GEO_PROVINCE_DRY_RUN` | mati | hitung + cetak laporan, tanpa `commit` |

### Contoh keluaran

```
[geo_loader] cities: dibuat=0 diperbarui=0 tetap=15 (-)
[geo_loader] districts: dibuat=153 diperbarui=18 tetap=0 (geojson_polygon=171, ...)
[geo_loader] villages: dibuat=1820 diperbarui=19 tetap=0 (...)
[geo_loader] kode dataset ditemukan: {'cities': 15, 'districts': 171, 'villages': 1839}
[geo_loader] selesai dan di-commit.
```

Angka pada putaran pertama bergantung pada isi DB: DB kosong membuat semuanya, DB hasil
seed lama memperbarui 18+19 dan membuat sisanya.

## 6. Mark di `deploy/init.sh`

| Mark | Skrip | Urutan |
|---|---|---|
| `geo_master_v1` | `load_geo_master.py` | setelah `seed_pjp_workdays_v1`, sebelum Odoo dijalankan |
| `geo_province_v1` | `fix_geo_province.py` | tepat setelah `geo_master_v1` |

Mark hanya diset bila skrip keluar dengan status 0. Bila gagal, mark tidak diset sehingga
boot berikutnya mencoba lagi — tidak ada keadaan "setengah jalan yang dianggap selesai".
Karena kedua skrip idempoten, mengulang aman.

## 7. Verifikasi setelah backfill

```sql
-- harus 15 / 171 / 1839, tanpa duplikat
SELECT count(*) FROM id_city WHERE kode_kemendagri IS NOT NULL;
SELECT count(*) FROM id_district WHERE kode_kemendagri IS NOT NULL;
SELECT count(*) FROM id_subdistrict WHERE kode_kemendagri IS NOT NULL;

-- provinsi
SELECT count(*) FROM id_city WHERE state_id IS NULL;
SELECT count(*) FROM id_district WHERE state_id IS NULL;
SELECT count(*) FROM id_coverage_area WHERE state_id IS NULL;
SELECT count(*) FROM res_partner WHERE district_id IS NOT NULL AND state_id IS NULL;

-- identitas legacy tetap
SELECT code, kode_kemendagri, is_legacy FROM id_subdistrict
WHERE code IN ('KEL-BTG-GRW', 'KEL-TMH-PSL');
```

Gate repo yang wajib hijau:

```bash
ruff check .
python scripts/check_manifests.py
python -m unittest tests.test_geo_master_data tests.test_geo_master_loader -v
python scripts/ops/verify_seed_invariants.py
bash -n deploy/init.sh
```

## 8. Rollback

Data geo bersifat referensi, bukan transaksi. Bila hasil backfill harus dibatalkan:

1. **Jangan** `DELETE` record yang sudah dipakai `res.partner` (`district_id`/`subdistrict_id`)
   — akan memicu `ondelete` pada partner.
2. Kembalikan hanya field yang diisi skrip (`kode_kemendagri`, `city_id`, geometri, `state_id`)
   dari backup DB, atau pulihkan snapshot sebelum backfill.
3. Hapus mark `geo_master_v1`/`geo_province_v1` hanya bila skrip akan dijalankan ulang
   dengan dataset berbeda:

```sql
DELETE FROM id_meta.marks WHERE name IN ('geo_master_v1', 'geo_province_v1');
```

## 9. Batasan yang diketahui

- Polyline/poligon hanya disimpan untuk kecamatan (`id.district.geojson_polygon`), bukan desa.
  Total ±1,3 MB; jangan dikirim lewat RPC record biasa.
- `id.city` kode `7109` punya nama XML "Kabupaten Kepulauan Siau Tagulandang Biaro" sedangkan
  CSV "Kab. Siau Tagulandang Biaro". Loader **tidak mengganti nama** record yang sudah ada,
  sehingga perbedaan dekoratif ini tidak menimbulkan churn.
- Kode pos legacy berbeda dari master untuk 9 dari 17 kelurahan (D4=A: tidak diperbaiki otomatis).
- Koordinat outlet sintetis: 44 dari 354 berada di luar poligon kecamatan yang ditugaskan.
  Itu bahan laporan audit coverage, bukan dasar auto-edit.
