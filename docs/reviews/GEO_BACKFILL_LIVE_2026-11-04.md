# Verifikasi Live Backfill Master Wilayah Sulut — 2026-11-04

**Tujuan:** membuktikan apakah backfill PR-3/PR-4 sudah benar-benar berjalan pada
database produksi Railway, dan apakah hasilnya memenuhi acceptance criteria.
**Sifat:** verifikasi baca-saja. Tidak ada penulisan data, mark, atau konfigurasi.

## 1. Ringkasan

| Item | Nilai |
|---|---|
| Project / environment | `pleasant-caring` / `production` |
| Service Odoo | `odooca-fmcg` |
| Deployment yang menjalankan backfill | `35ea2443`, commit `70f345fe` (merge PR #78), dibuat 2026-11-03T14:11:32Z |
| Loader dieksekusi | 2026-11-03T14:15:51Z |
| Province fixer dieksekusi | 2026-11-03T14:16:01Z |
| Mark `geo_master_v1` | 2026-11-03 14:15:58.994075+00 |
| Mark `geo_province_v1` | 2026-11-03 14:16:01.658203+00 |
| Deployment live saat verifikasi | `d92c9fa1`, commit `2b7cdd2e` (2026-11-04T07:50:17Z, SUCCESS) |
| Tindak lanjut dieksekusi | 2026-11-04T10:08:05Z isi provinsi company 1; 2026-11-04T10:09:54Z arsip company 2 |

[F] Backfill berjalan otomatis lewat `deploy/init.sh` pada deployment pertama setelah
PR #78 di-merge — bukan tindakan manual, dan bukan pekerjaan yang masih tertunda.

## 2. Bukti log loader

```
[geo_loader] cities: dibuat=0 diperbarui=15 tetap=0
[geo_loader] districts: dibuat=153 diperbarui=18 tetap=0
[geo_loader] villages: dibuat=1822 diperbarui=19 tetap=0
[geo_loader] kode dataset ditemukan: {'cities': 15, 'districts': 171, 'villages': 1839}
[geo_loader] selesai dan di-commit.
```

Angka konsisten dengan dataset: 153 + 18 = 171 kecamatan; 1.822 desa baru + 17 desa
lama ber-`kode_kemendagri` = 1.839 kode dataset (2 record legacy tetap tanpa kode).

## 3. Bukti log province fixer

```
[geo_province] companies: 0
[geo_province] companies_preserved: 0
[geo_province] companies_unverified: 2
[geo_province] coverage_areas: 4
[geo_province] districts: 0
[geo_province] partners: 0
[geo_province] partners_preserved: 276
[geo_province] partners_unverified: 78
[geo_province] partners_village_only: 0
[geo_province] partners_without_geo: 407
[geo_province] cities_preserved: 15
```

Catatan tafsir: `partners_unverified`/`partners_preserved` adalah penghitung **cakupan
identitas** menurut predikat skrip, bukan jumlah provinsi kosong. Angka `partners: 0`
berarti tidak ada provinsi yang perlu diisi (semua partner sudah berprovinsi), bukan
berarti partner tidak diproses.

## 4. Bukti query database (read-only)

Sesi dijalankan dengan `default_transaction_read_only=on`; tidak ada DDL/DML.

| Pemeriksaan | Hasil |
|---|---|
| Kode dataset kota ditemukan | 15 / 15, hilang 0 |
| Kode dataset kecamatan ditemukan | 171 / 171, hilang 0 |
| Kode dataset desa/kelurahan ditemukan | 1.839 / 1.839, hilang 0 |
| Duplikat `kode_kemendagri` (3 level) | 0 |
| Kode di luar dataset pada 3 level | 0 |
| Total record `id.subdistrict` | 1.841 = 1.839 kanonik + 2 legacy |
| `is_legacy` tanpa `kode_kemendagri` | 2 (`KEL-BTG-GRW`, `KEL-TMH-PSL`) |
| Kode legacy dipertahankan | 19 `KEL-*` (subdistrict), 18 `KEC-*` (district) |
| `id.city`/`id.district` dalam dataset tanpa `state_id` | 0 / 0 |
| `id.coverage.area` tanpa `state_id` | 0 |
| Partner seed `CUST-*` cocok di DB | 354 / 354 |
| Partner seed dengan `district_id` | 354 / 354 |
| Partner seed dengan `state_id` | 354 / 354 |
| Partner seed dengan `state_id` kosong | 0 |
| Company aktif | 2 |
| Company aktif berprovinsi | 0 |
| Company aktif tanpa provinsi | 2 |

## 5. Status acceptance criteria

| Kriteria | Status | Bukti |
|---|---|---|
| 15 kota / 171 kecamatan / 1.839 desa | **Terpenuhi** | §4 |
| 0 duplikat `kode_kemendagri` | **Terpenuhi** | §4 |
| `state_id` 100% kota/kecamatan/coverage area | **Terpenuhi** | §4 |
| 354 partner tetap punya FK kecamatan | **Terpenuhi** | 354/354 |
| `state_id` 100% pada 354 partner | **Terpenuhi** | 354/354 |
| `state_id` 100% pada company | **Terpenuhi** | 1/1 company aktif setelah tindak lanjut §6 |
| Identitas legacy stabil | **Terpenuhi** | §4 |
| Tidak ada perubahan saldo/transaksi | [BU] | Tidak ada baseline sebelum/sesudah; skrip hanya menulis tabel geo, dan sesi verifikasi ini read-only |
| `tests.test_seed_invariants` | [F] hijau di CI, bukan dijalankan ulang pada DB live | Riwayat CI PR #78/#79 |
| Loader + province fixer idempoten | [F] diuji unit/native; re-run live tidak dijalankan | Mark mencegah eksekusi ulang otomatis |
| Laporan audit coverage tanpa auto-edit | **Terpenuhi** | `docs/reviews/GEO_COVERAGE_AUDIT_2026-11-03.md` |

## 6. Tindak lanjut yang dieksekusi

### 6.1 Dua company aktif tanpa provinsi

| ID | Nama | Alamat | Negara | Catatan |
|---|---|---|---|---|
| 1 | PT Manado Distribusi Utama | Jl. AA Maramis No. 88, Interchange Maumbi, Manado 95371 | ID | Company operasional; provinsi seharusnya Sulawesi Utara |
| 2 | STAGING TEST Company | kosong | kosong | Sisa company uji dengan 2 user aktif |

[F] `res_company` tidak memiliki kolom `state_id`; provinsi company dibaca dari
`partner_id.state_id`. [F] Keduanya dilaporkan `companies_unverified` karena tidak
memiliki relasi wilayah terverifikasi (`district_id` kosong).

**Keputusan pemilik 2026-11-04:** isi provinsi company 1, arsipkan company 2.

**Company 1 — diisi lewat script resmi** (`GEO_PROVINCE_COMPANY_IDS=1`, dry-run lebih
dulu):

```
[geo_province] DRY-RUN companies: 1
[geo_province] DRY-RUN companies_unverified: 1
[geo_province] DRY-RUN selesai; tidak ada perubahan yang di-commit.
```

Penerapan menghasilkan `[geo_province] companies: 1` dan
`[geo_province] selesai dan di-commit.`; query ulang menunjukkan
`state_name = Sulawesi Utara` untuk company 1.

**Company 2 — diarsipkan lewat `scripts/ops/archive_staging_company.py`** (baru,
dry-run default, guard dokumen/user/nama):

```
[archive_staging] mode: apply
[archive_staging] documents: {'account.move': 0, 'account.payment': 0, 'sale.order': 0, 'purchase.order': 0, 'stock.picking': 0}
[archive_staging] users: ['staging.capture.1', 'staging.capture.2']
[archive_staging] users_deactivated: ['staging.capture.1', 'staging.capture.2']
[archive_staging] result: archived
[archive_staging] active_companies_after: 1
```

Odoo menolak arsip selama company masih default company user aktif, sehingga dua user
uji `staging.*` dinonaktifkan lebih dulu; tidak ada dokumen akuntansi, penjualan,
pembelian, atau stok pada company tersebut.

**Hasil akhir:** 1 company aktif, 1 berprovinsi, 0 tanpa provinsi.

### 6.2 Butir yang sudah diputuskan, bukan utang

- 2 kelurahan legacy tanpa kode Kemendagri (D5=B).
- 44 outlet di luar poligon kecamatan yang ditugaskan, hanya dilaporkan (D4=A).
- `partners_unverified: 78` adalah penghitung cakupan identitas, bukan provinsi kosong.

## 7. Metode

1. Status deployment dan commit live dibaca dari Railway (`describe-service`,
   `list-deployments`).
2. Jejak eksekusi dibaca dari log deploy dengan filter `geo_master_v1`,
   `geo_province_v1`, dan `geo_loader`.
3. Isi database diperiksa lewat koneksi read-only (`default_transaction_read_only=on`)
   memakai kredensial peran Odoo yang disuntikkan Railway CLI; tidak ada nilai rahasia
   yang dicetak.
4. Query verifikasi yang dipakai didokumentasikan di `docs/geo/GEO_MASTER_LOADER.md` §7
   dan diotomatiskan oleh `scripts/ops/verify_geo_backfill.py` (perbandingan himpunan
   kode, bukan sekadar hitungan).

## 8. Rekomendasi

1. Tidak perlu mengulang loader: mark sudah terpasang dan dataset sudah lengkap.
2. Tidak perlu menjalankan `fix_geo_province.py` lagi untuk cakupan saat ini; bila ada
   company baru tanpa provinsi, gunakan dry-run lalu `GEO_PROVINCE_COMPANY_IDS` eksplisit.
3. Pertahankan `scripts/ops/archive_staging_company.py` sebagai jalur arsip company uji:
   script menolak bila ada dokumen, nama tidak tunggal, atau user bukan `staging.*`.

## 9. Koreksi pasca-review supervisor (HEAD `299f2f9`)

| Temuan | Koreksi |
|---|---|
| P2: guard arsip melewatkan stok/reservasi atau move tanpa picking | `DOCUMENT_MODELS` ditambah `stock.move`, `stock.move.line`, `stock.scrap`, `mrp.production`; `stock.quant` dihitung bila `quantity != 0` **atau** `reserved_quantity != 0` |
| P2: query jumlah kode tidak membuktikan kelengkapan dataset | Verifikasi diganti menjadi perbandingan himpunan: `scripts/ops/verify_geo_backfill.py` melaporkan `missing`, `extra`, dan `duplicates` per level; kode karangan yang menggantikan kode kanonik kini gagal |
| P3: laporan berisi 1.227 byte NUL | Berkas ditulis ulang sebagai UTF-8 tanpa NUL; `git diff` kembali terbaca sebagai teks |

Regresi untuk ketiga butir: `tests/test_geo_ops_guards.py` (11 test) mencakup guard
stok/reservasi dan kasus tukar-kode dengan jumlah baris tetap sama.
