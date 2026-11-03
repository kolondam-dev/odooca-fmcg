# Audit Coverage Outlet vs Poligon Kecamatan — Sulawesi Utara

**Dibuat oleh:** `scripts/ops/audit_geo_coverage.py` (baca-saja)
**Keputusan terkait:** D4=A — temuan dilaporkan, **tidak** ada auto-edit koordinat outlet.
**Sumber:** `data/seed/partners_354.csv`, `data/geo/sulut_districts.geojson`; pemetaan kode legacy dari `addons/id_base/data/id_district_data.xml`, dicek silang dengan `data/master/legacy_geo_mapping.csv` bila tersedia.

## 1. Ringkasan

| Metrik | Nilai |
|---|---:|
| Outlet diuji | 354 |
| Outlet dengan kode kecamatan terpetakan | 354 |
| Outlet di luar poligon kecamatan yang ditugaskan | **44** |
| — di luar seluruh poligon Sulut | 44 |
| — berada di dalam poligon kecamatan lain | 0 |
| Outlet tanpa pemetaan kode | 0 |
| Sumber pemetaan kode legacy | `id_district_data.xml` |

Koordinat outlet bersifat sintetis (data demo), jadi angka ini adalah bukti bahwa deteksi bekerja, bukan vonis kualitas data lapangan.

## 2. Sebaran temuan per kecamatan

| Kode Kemendagri | Kecamatan | Outlet di luar |
|---|---|---:|
| `71.02.12` | Kawangkoan | 4 |
| `71.71.04` | Wenang | 11 |
| `71.71.07` | Wanea | 29 |

## 3. Daftar outlet di luar poligon

| Ref | Nama | Kecamatan (kode) | Latitude | Longitude | Di dalam poligon lain |
|---|---|---|---:|---:|---|
| `CUST-GT-69` | Grosir Kawangkoan Permai | Kawangkoan (`71.02.12`) | 1.204444 | 124.780651 | — |
| `CUST-RTL-241` | Kios Tante Pingkan Bawah Pohon | Kawangkoan (`71.02.12`) | 1.203594 | 124.782101 | — |
| `CUST-RTL-244` | Warung Tante Engelin Pondok Damai | Kawangkoan (`71.02.12`) | 1.204194 | 124.780301 | — |
| `CUST-RTL-246` | Warung Tin Tikungan | Kawangkoan (`71.02.12`) | 1.203294 | 124.779101 | — |
| `CUST-GT-03` | Grosir Sinar Terang Calaca | Wenang (`71.71.04`) | 1.498496 | 124.843184 | — |
| `CUST-GT-04` | Toko Pinaesaan Calaca | Wenang (`71.71.04`) | 1.497096 | 124.843884 | — |
| `CUST-GT-25` | Grosir Megamas Abadi | Wenang (`71.71.04`) | 1.498496 | 124.843184 | — |
| `CUST-RTL-002` | Warung Om Oce Lorong 2 | Wenang (`71.71.04`) | 1.497946 | 124.843734 | — |
| `CUST-RTL-006` | Warung Dani Ujung Lorong | Wenang (`71.71.04`) | 1.496146 | 124.841334 | — |
| `CUST-RTL-007` | Kios Berkat Ventje Bawah Pohon | Wenang (`71.71.04`) | 1.497646 | 124.844634 | — |
| `CUST-RTL-010` | Kios Filadelfia Meylan Pondok Damai | Wenang (`71.71.04`) | 1.498246 | 124.842834 | — |
| `CUST-RTL-015` | Kios Ko Deasy Pasar | Wenang (`71.71.04`) | 1.497946 | 124.843734 | — |
| `CUST-RTL-019` | Warung Kasih Erna Lorong 1 | Wenang (`71.71.04`) | 1.496146 | 124.841334 | — |
| `CUST-RTL-020` | Kios Filadelfia Jacky Lorong 2 | Wenang (`71.71.04`) | 1.497646 | 124.844634 | — |
| `CUST-RTL-023` | Kios Ci Vicky Pintu Masuk | Wenang (`71.71.04`) | 1.498246 | 124.842834 | — |
| `CUST-GT-16` | Toko Pelita Jaya Wanea | Wanea (`71.71.07`) | 1.483210 | 124.835742 | — |
| `CUST-GT-17` | Toko Anugerah Kasih Karombasan | Wanea (`71.71.07`) | 1.485660 | 124.832592 | — |
| `CUST-GT-18` | Grosir Rukun Damai Ranotana | Wanea (`71.71.07`) | 1.484260 | 124.833292 | — |
| `CUST-GT-19` | Grosir Teling Sentosa Wanea | Wanea (`71.71.07`) | 1.482860 | 124.833992 | — |
| `CUST-GT-20` | Toko Pakowa Sejahtera Wanea | Wanea (`71.71.07`) | 1.485310 | 124.834692 | — |
| `CUST-GT-21` | Grosir Tingkulu Jaya Wanea | Wanea (`71.71.07`) | 1.483910 | 124.835392 | — |
| `CUST-GT-22` | Toko Winangun Berkat | Wanea (`71.71.07`) | 1.482510 | 124.832242 | — |
| `CUST-GT-23` | Toko Bumi Nyiur Permai | Wanea (`71.71.07`) | 1.484960 | 124.832942 | — |
| `CUST-GT-26` | Toko Karombasan Baru | Wanea (`71.71.07`) | 1.484610 | 124.835042 | — |
| `CUST-GT-32` | Toko Ranotana Jaya | Wanea (`71.71.07`) | 1.483910 | 124.835392 | — |
| `CUST-MT-07` | MultiiMart Sam Ratulangi | Wanea (`71.71.07`) | 1.483360 | 124.833092 | — |
| `CUST-RTL-066` | Warung Pingkan Tikungan | Wanea (`71.71.07`) | 1.483960 | 124.835492 | — |
| `CUST-RTL-067` | Kios Berkat Toar Jembatan | Wanea (`71.71.07`) | 1.485460 | 124.834892 | — |
| `CUST-RTL-068` | Kios Gloria Lumimuut Kompleks | Wanea (`71.71.07`) | 1.483060 | 124.834292 | — |
| `CUST-RTL-069` | Warung Kasih Engelin Pasar | Wanea (`71.71.07`) | 1.484560 | 124.833692 | — |
| `CUST-RTL-070` | Kios Filadelfia Marietje Depan SD | Wanea (`71.71.07`) | 1.486060 | 124.833092 | — |
| `CUST-RTL-071` | Kios Tante Tin Dekat Mesjid | Wanea (`71.71.07`) | 1.483660 | 124.832492 | — |
| `CUST-RTL-072` | Warung Om Oce Puncak | Wanea (`71.71.07`) | 1.485160 | 124.835792 | — |
| `CUST-RTL-073` | Kios Ci Utu Lorong 1 | Wanea (`71.71.07`) | 1.482760 | 124.835192 | — |
| `CUST-RTL-074` | Warung Tante Meyke Lorong 2 | Wanea (`71.71.07`) | 1.484260 | 124.834592 | — |
| `CUST-RTL-075` | Kios Ko Ferry Lorong 3 | Wanea (`71.71.07`) | 1.485760 | 124.833992 | — |
| `CUST-RTL-076` | Warung Dani Dekat Gereja | Wanea (`71.71.07`) | 1.483360 | 124.833392 | — |
| `CUST-RTL-077` | Kios Berkat Ventje Pintu Masuk | Wanea (`71.71.07`) | 1.484860 | 124.832792 | — |
| `CUST-RTL-078` | Kios Gloria Novry Ujung Lorong | Wanea (`71.71.07`) | 1.482460 | 124.832192 | — |
| `CUST-RTL-079` | Warung Kasih Ritha Bawah Pohon | Wanea (`71.71.07`) | 1.483960 | 124.835492 | — |
| `CUST-RTL-080` | Kios Filadelfia Meylan Perempatan | Wanea (`71.71.07`) | 1.485460 | 124.834892 | — |
| `CUST-RTL-081` | Kios Tante Hein Jalan Salib | Wanea (`71.71.07`) | 1.483060 | 124.834292 | — |
| `CUST-RTL-082` | Warung Om Vonny Pondok Damai | Wanea (`71.71.07`) | 1.484560 | 124.833692 | — |
| `CUST-RTL-083` | Kios Ci Meiske Samping Lapangan | Wanea (`71.71.07`) | 1.486060 | 124.833092 | — |

## 4. Temuan lain (D4=A: dilaporkan, tidak diubah)

- Konflik pemetaan kode legacy antara CSV dan seed XML: **0** (harus 0).
- Kode pos partner berbeda dari kode pos kanonik desa/kelurahan: **40** dari 354 outlet.
- Kode pos record legacy di seed berbeda dari master: **9** dari 17 kelurahan terpetakan.

Rincian kode pos ada di berkas JSON bila `--json` dipakai; tidak ada nilai yang ditulis ulang.

## 5. Cara membaca dan menindaklanjuti

1. Temuan ini **tidak** mengubah data apa pun. Loader `scripts/ops/load_geo_master.py` hanya mengisi koordinat kelurahan yang masih kosong.
2. Outlet di luar poligon dapat berarti: koordinat sintetis, poligon sumber yang belum presisi, atau outlet memang di perbatasan. Keputusan lapangan tetap milik pemilik data.
3. Bila koordinat nyata tersedia, perbarui `data/seed/partners_354.csv` lewat PR terpisah beserta regenerasi artefak rekonsiliasi.

## 6. Reproduksi

```bash
python scripts/ops/audit_geo_coverage.py
python -m unittest tests.test_geo_coverage_audit -v
```
