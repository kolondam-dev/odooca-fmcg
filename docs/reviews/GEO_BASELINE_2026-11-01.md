# Baseline Master Wilayah & Geo — 2026-11-01

**Cabang:** `agen/geo-master-upgrade` (basis `origin/main` = `13b2ee0`, 2026-11-01 19:21 +07:00)
**Status:** baseline read-only. Belum ada perubahan DB, seed, atau transaksi.
**Keputusan pemilik:** D1=B (171 kecamatan + 1.839 desa), D2=A (GeoJSON di `Text`), D3=A (provinsi: laporan
+ data-fix, tanpa constraint keras), D4=A (koordinat outlet: laporan saja), D5=B **hanya** untuk kelurahan
yang tidak mengganggu transaksi/histori — implementasi: 17 kelurahan dipetakan, 2 dibiarkan legacy.

## 1. Baseline repo (terukur dari kode & data, [F])

| Objek | Nilai | Bukti |
|---|---:|---|
| `id.city` ter-seed | 15 | `addons/id_base/data/id_city_data.xml` |
| `id.district` ter-seed | 18 | `addons/id_base/data/id_district_data.xml` |
| `id.subdistrict` ter-seed | 19 | `addons/id_base/data/id_district_data.xml` |
| Paket master tersedia | 1 / 15 / 171 / 1.839 | `data/master/*.csv` (build sebelum PR ini) |
| `id.city.state_id` terisi | 0 / 15 | XML tidak menulis `state_id` |
| `id.district.city_id` terisi | 0 / 18 | XML hanya menulis field teks `city` |
| `id.district.geojson_polygon` terisi | 0 / 18 | field hanya didefinisikan (`fmcg_dimension.py:94`), tidak pernah ditulis |
| `res.partner` dengan `district_id` | 354 | `data/seed/partners_354.csv` (18 kecamatan) |
| `res.partner` dengan `subdistrict_id` | 354 | 18 kelurahan berbeda (1 record `KEL-MND-WNS` tanpa partner) |
| `state_id` company | kosong | `deploy/init.sh` `company_profile_v2` tidak menulis `state_id` |
| `state_id` partner | [BU] | `load_fmcg_seed.py` mengisi sejak `2ab1431`, tetapi mark `seed_master_v4` mencegah seed ulang |
| `id.coverage.area.state_id` | kosong | tidak diisi XML/seed |

Master provinsi sudah tersedia di Odoo core: `base.state_id_sa` = Sulawesi Utara, kode `SA`
(`odoo/addons/base/data/res.country.state.csv`). Jadi masalahnya adalah pengisian, bukan data hilang. [F]

## 2. Baseline kualitas geometri

| Metrik | Build lama | Build baru (PR-1) |
|---|---:|---:|
| `sulut_districts.geojson` | 178 KB | 1.325 KB |
| Median titik poligon kecamatan | 19 | 268 |
| Tumpang tindih antar-kecamatan | 126,5 km² | 1,07 km² |
| Kecamatan ⊂ kab/kota | tidak diukur | 100% |
| Total luas kab/kota | — | ±14.599 km² |
| Desa valid | 1.839/1.839 | 1.839/1.839 |
| `qa_flag = periksa_lokasi` | 19 | 19 (3 di antaranya salah letak di sumber) |

Point-in-polygon 354 outlet terhadap kecamatan yang ditugaskan: **35 di luar** dengan poligon lama,
**44 di luar** dengan poligon baru. Koordinat outlet bersifat sintetis, sehingga angka ini adalah bukti
deteksi, bukan vonis kualitas data lapangan. [F hitungan; [A] penyebab]

## 3. Baseline gate seed yang mengikat perubahan wilayah

| Gate | Aturan | Konsekuensi |
|---|---|---|
| `MASTER-SYNC` | field bersama `data/seed/partners_354.csv` = `data/registers/customer_registry_354.csv` | setiap perubahan kode wilayah harus di kedua file |
| `MASTER-GEO` | kode di registry harus resolve ke pasangan district/village di `id_district_data.xml` | kode baru wajib ada di XML |
| `REPORT-RECON` | `canonical_financial_reconciliation_july_2026.json` mem-pin sha256 `customer_registry_354.csv` | mengubah registry memaksa regenerasi artefak rekonsiliasi |

Karena itu strategi D5=B dipilih **tanpa mengubah CSV**: record legacy dipertahankan, `kode_kemendagri`
diisi pada record yang sama, `code` tetap `KEC-*`/`KEL-*`.

## 4. Pemetaan 19 kelurahan legacy

17 dari 19 cocok 1:1 (nama identik setelah membuang dekorasi dalam tanda kurung, kecamatan sama):
`KEL-MND-CLC`, `KEL-MND-WNS`, `KEL-MND-SKB`, `KEL-MND-BAH`, `KEL-MND-TKB`, `KEL-MND-PLD`, `KEL-MND-TMT`,
`KEL-MND-PKB`, `KEL-BTG-BTM`, `KEL-MNH-RNG`, `KEL-MNH-SDG`, `KEL-MNT-AMA`, `KEL-MNS-BYG`, `KEL-MND-PKW`,
`KEL-MND-KRM`, `KEL-BTG-MDU`, `KEL-BTG-ATB`.

2 tidak dipetakan (keputusan pemilik: biarkan legacy):

| Kode | Nama | Alasan |
|---|---|---|
| `KEL-BTG-GRW` | Girian Weru | master hanya punya `Girian Weru Satu` dan `Girian Weru Dua` (1:2); 6 koordinat partner jatuh di `Girian Indah`/`Girian Permai` |
| `KEL-TMH-PSL` | Paslaten Satu | satu-satunya `Paslaten Satu` di Kemendagri berada di Tomohon Timur, sedangkan record legacy di Tomohon Tengah; 16 koordinat partner berada di Tomohon Tengah |

Tidak ada model transaksi yang menyimpan FK kecamatan/kelurahan; `perpetual_sales_orders.csv` dan
`pjp_july_2026_matrix.csv` hanya memuat kolom `district` berupa nama dan tidak dibaca loader kanonikal. [F]

## 5. Baseline DB live

Snapshot DB live **belum diambil** pada sesi ini: sandbox tidak memiliki kredensial Railway/Odoo. [BU]
Perintah yang harus dijalankan pemilik/antigravity untuk melengkapi baseline:

```bash
python3 scripts/ops/odoo_snapshot.py --url https://<host> --db <db> --user admin --out snapshot-geo-baseline.md
```

Yang perlu dicatat dari snapshot: jumlah `id.city`/`id.district`/`id.subdistrict`, `res.partner` per
`state_id`, `res.partner` tanpa `state_id`, distribusi partner per `district_id`, dan ada/tidaknya
`geojson_polygon` terisi.

## 6. Kriteria penerimaan program (dipakai PR-2 s/d PR-4)

1. `id.city` = 15, `id.district` = 171, `id.subdistrict` = 1.839 (+ record legacy yang tidak dipetakan),
   0 duplikat `kode_kemendagri`.
2. `state_id` terisi 100% untuk company, 354 partner, 15 city, 171 district, dan seluruh coverage area.
3. 171 district punya poligon valid; total luas provinsi 14.000–15.200 km²; overlap kecamatan < 5 km²;
   kecamatan ⊂ kabupaten ≥ 99,9%.
4. 354 partner tetap terhubung ke district (0 broken FK); jumlah partner tidak berubah.
5. Tidak ada perubahan saldo/transaksi; `tests.test_seed_invariants` lulus.
6. `ruff check .`, `python scripts/check_manifests.py`, `python -m unittest tests.test_geo_master_data`
   lulus; CI hijau pada SHA yang sama dengan PR.
7. Modul terinstal di DB kosong; loader + fix provinsi idempoten di DB kosong dan DB lama.
8. Laporan audit coverage dihasilkan; outlet di luar polygon terdaftar tanpa auto-edit.

## 7. Risiko yang masih terbuka

- Nama legacy berdekorasi (`Calaca (Pasar 45)`, `Bahu (FreshMart Bahu Mall)`) berbeda dari nama master;
  pencocokan harus memakai kode, bukan nama.
- Kode pos legacy berbeda dari master untuk 9 dari 17 kelurahan; 40 dari 354 zip partner juga berbeda dari
  kode pos desa canonical. Tidak diperbaiki otomatis (D4=A). [F]
- `noupdate="1"` pada XML geo: perubahan XML tidak memperbarui record lama saat `-u`; jalur utama adalah
  script migrasi. [F]
- Polygon 1,3 MB tidak boleh dikirim lewat RPC record biasa; gunakan endpoint ringan/aset statis. [A]
