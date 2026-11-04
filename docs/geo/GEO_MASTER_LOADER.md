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
| `res.company` | Isi provinsi kosong pada company aktif dengan wilayah partner terverifikasi; tanpa relasi wilayah wajib `GEO_PROVINCE_COMPANY_IDS` eksplisit |
| `id.city` | Hanya kode Kemendagri dalam CSV kanonikal Sulut, aktif, provinsi kosong |
| `id.district` | Hanya identitas kecamatan kanonikal aktif dengan parent Sulut; recompute related kosong bila city berprovinsi Sulut |
| `id.coverage.area` | Hanya empat XMLID area seed Sulut, aktif, provinsi kosong |
| `res.partner` | Hanya wilayah aktif yang terverifikasi pada CSV/parent; provinsi kosong dan negara kosong/Indonesia |

Provinsi yang sudah terisi **tidak ditimpa**, termasuk konflik pada identitas Sulut.
Record arsip, wilayah luar Sulut, negara lain dan identitas tak dikenal dipertahankan.
Company tanpa bukti wilayah dilaporkan `companies_unverified`; operator dapat memilih
ID company secara eksplisit lewat `GEO_PROVINCE_COMPANY_IDS=1,2`. Flag ini tidak
mengizinkan penimpaan provinsi terisi atau perubahan company arsip/negara lain.
ID hanya bermakna di database target; tentukan dari inventaris operator, jangan menyalin ID dari contoh.

FK `district_id` dan `subdistrict_id` partner tidak ditulis. Untuk village-only,
provinsi dibaca dari hierarki tanpa melengkapi FK. Relasi district/village yang
bertentangan dilewati. Dry-run memakai cakupan dan aturan yang sama tanpa write/commit.
Report `*_preserved`, `*_unverified` dan `partners_without_geo` menjelaskan record
tertahan; jumlah ini bukan jumlah perubahan dan tidak harus nol pada putaran kedua.
Loader master juga mempertahankan `state_id` city yang sudah terisi. Konflik
memerlukan keputusan data-fix terpisah. D3=A tetap tanpa constraint keras.

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

Semua kode Sulut berawalan `71.`, sehingga hitungan dapat dibatasi ke dataset tanpa
memasukkan wilayah provinsi lain. Query berikut baca-saja dan boleh dijalankan pada
koneksi `default_transaction_read_only=on`.

```sql
-- 1) Kelengkapan dataset: baris harus sama dengan kode unik (15 / 171 / 1839)
SELECT 'city' AS level, count(*) AS baris, count(DISTINCT kode_kemendagri) AS kode_unik
FROM id_city WHERE kode_kemendagri LIKE '71.%'
UNION ALL
SELECT 'district', count(*), count(DISTINCT kode_kemendagri)
FROM id_district WHERE kode_kemendagri LIKE '71.%'
UNION ALL
SELECT 'village', count(*), count(DISTINCT kode_kemendagri)
FROM id_subdistrict WHERE kode_kemendagri LIKE '71.%';

-- 2) Duplikat kode (harus 0 baris)
SELECT 'city' AS level, kode_kemendagri, count(*) FROM id_city
WHERE kode_kemendagri LIKE '71.%' GROUP BY 2 HAVING count(*) > 1
UNION ALL
SELECT 'district', kode_kemendagri, count(*) FROM id_district
WHERE kode_kemendagri LIKE '71.%' GROUP BY 2 HAVING count(*) > 1
UNION ALL
SELECT 'village', kode_kemendagri, count(*) FROM id_subdistrict
WHERE kode_kemendagri LIKE '71.%' GROUP BY 2 HAVING count(*) > 1;

-- 3) Provinsi kota/kecamatan/coverage area (harus 0)
SELECT count(*) FROM id_city WHERE kode_kemendagri LIKE '71.%' AND state_id IS NULL;
SELECT count(*) FROM id_district WHERE kode_kemendagri LIKE '71.%' AND state_id IS NULL;
SELECT count(*) FROM id_coverage_area WHERE state_id IS NULL;

-- 4) Company: provinsi ada di partner_id.state_id (res_company tidak punya kolom state_id)
SELECT c.id, c.name, p.state_id IS NOT NULL AS punya_provinsi
FROM res_company c JOIN res_partner p ON p.id = c.partner_id
WHERE c.active ORDER BY c.id;

-- 5) Partner: FK kecamatan wajib utuh; provinsi kosong dilaporkan, bukan diperbaiki otomatis
SELECT count(*) AS total,
       count(*) FILTER (WHERE state_id IS NULL) AS tanpa_provinsi,
       count(*) FILTER (WHERE state_id IS NOT NULL) AS berprovinsi
FROM res_partner WHERE district_id IS NOT NULL;

-- 6) Identitas legacy tetap dan hanya 2 tanpa kode
SELECT count(*) FROM id_subdistrict WHERE code LIKE 'KEL-%';   -- 19
SELECT count(*) FROM id_district WHERE code LIKE 'KEC-%';      -- 18
SELECT count(*) FROM id_subdistrict WHERE is_legacy AND kode_kemendagri IS NULL; -- 2

-- 7) Mark terpasang
SELECT name, at FROM id_meta.marks
WHERE name IN ('geo_master_v1', 'geo_province_v1');
```

Catatan tafsir:

- Jangan memakai `count(*) ... WHERE kode_kemendagri IS NOT NULL` tanpa batas `71.%`
  bila database juga memuat wilayah provinsi lain.
- `partners_unverified` pada keluaran skrip adalah penghitung cakupan identitas, bukan
  jumlah provinsi kosong; angka `partners: 0` berarti tidak ada yang perlu diisi.
- Company tanpa relasi wilayah hanya dapat diisi lewat `GEO_PROVINCE_COMPANY_IDS`
  eksplisit, dan tetap tidak menimpa provinsi yang sudah terisi.

Hasil verifikasi produksi 2026-11-04 (15/171/1.839 lengkap, 354/354 partner
berprovinsi, 0/2 company berprovinsi) tercatat di
`docs/reviews/GEO_BACKFILL_LIVE_2026-11-04.md`.

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
