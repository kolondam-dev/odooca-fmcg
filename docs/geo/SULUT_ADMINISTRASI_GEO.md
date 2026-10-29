# Master Data Wilayah Administrasi Sulawesi Utara (Provinsi 71)

Hierarki lengkap: **1 provinsi → 15 kab/kota (11 kab + 4 kota) → 171 kecamatan → 1.839 desa/kelurahan
(332 kelurahan + 1.507 desa)**, dengan kode wilayah, kode pos, titik pusat (lat/lng) dan poligon.

Dibangun ulang oleh `scripts/generate_sulut_master.py`. Skrip lama (`generate_sulut_geojson.py`) membuat
poligon berupa kotak dari angka manual, bukan batas wilayah nyata, sehingga digantikan.

## Menjalankan ulang

```bash
pip install shapely            # >= 2.0
python scripts/generate_sulut_master.py             # unduh sumber (jika belum ada) lalu bangun
python scripts/generate_sulut_master.py --refresh   # unduh ulang semua sumber
python scripts/generate_sulut_master.py --strict    # exit 1 jika ada temuan kritis (untuk CI)
python scripts/generate_sulut_master.py --no-repair # jangan perbaiki geometri tidak valid dari sumber
```

Sumber diunduh dari `raw.githubusercontent.com` ke `data/raw/` (cache; tidak disertakan di zip).
`data/master/SOURCES.csv` mencatat URL, ukuran, dan SHA-256 setiap file sumber.

## Isi

| File | Isi |
|---|---|
| `data/master/sulut_provinsi.csv` | 1 baris |
| `data/master/sulut_kab_kota.csv` | 15 baris |
| `data/master/sulut_kecamatan.csv` | 171 baris |
| `data/master/sulut_desa_kelurahan.csv` | 1.839 baris, termasuk `kodepos` |
| `data/master/sulut_wilayah_semua_level.csv` | semua 2.026 wilayah dalam satu tabel (`level`, `kode_induk`) |
| `data/master/sulut_kodepos.csv` | kode wilayah → kode pos (1.839 baris) |
| `data/master/sulut_poligon_{provinsi,kab_kota,kecamatan,desa_kelurahan}.csv` | poligon dalam WKT |
| `data/geo/sulut_provinsi.geojson`, `sulut_kab_kota.geojson`, `sulut_districts.geojson`, `sulut_villages.geojson` | poligon GeoJSON (nama file sama dengan skrip lama) |
| `data/master/SOURCES.csv` | sumber, URL, lisensi, checksum |
| `data/master/validation_report.{md,json}`, `validation_anomali.csv` | hasil validasi dan daftar anomali |

### Kolom penting

- `kode_kemendagri` — kode berformat titik (`71.01.05.2001`); `kode_nodot` — tanpa titik (`7101052001`).
- `jenis` — Kabupaten/Kota; Kelurahan/Desa (digit pertama segmen terakhir: `1` = Kelurahan, `2` = Desa).
- `lat_sentral`, `lng_sentral` — centroid dari sumber. **Pada wilayah berbentuk melengkung atau berpulau,
  centroid bisa jatuh di luar poligonnya** (lihat `centroid_sumber_di_dalam_poligon`: 3 kab/kota, 14 kecamatan,
  114 desa/kelurahan). Gunakan `lat_titik_dalam`, `lng_titik_dalam` (dihitung dengan
  `representative_point()`) bila butuh titik yang pasti berada di dalam wilayah.
- `luas_km2_approx` — dihitung dari poligon yang sudah disederhanakan (equal-area); hanya untuk sanity check.
- `qa_persen_di_dalam_induk`, `qa_flag` — lihat bagian Kualitas data.
- `src_*` — ID sumber (S1/S2/S3) yang merujuk ke `SOURCES.csv` untuk setiap kelompok kolom.
- Poligon CSV: `wkt_epsg4326_lng_lat` (urutan lng lat, 6 desimal). Sel poligon provinsi (40.910 karakter) melebihi
  batas 32.767 karakter per sel di Excel; buka file poligon dengan QGIS, PostGIS, atau `shapely.from_wkt`.

## Sumber

| ID | Sumber | Dipakai untuk | Lisensi |
|---|---|---|---|
| S1 | [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah) `db/wilayah.sql` | kode & nama wilayah (header: Kepmendagri No 300.2.2-2138 Tahun 2025) | MIT |
| S2 | [cahyadsn/wilayah_kodepos](https://github.com/cahyadsn/wilayah_kodepos) `db/wilayah_kodepos.sql` | kode pos desa/kelurahan | MIT |
| S3 | [cahyadsn/wilayah_boundaries](https://github.com/cahyadsn/wilayah_boundaries) `db/{prov,kab,kec,kel}` | poligon + centroid semua level (README: Kepmendagri No 300.2.2-2430 Tahun 2025) | MIT |

Commit yang diperiksa saat pengembangan: `wilayah_boundaries` `68e93c0` (2026-10-23), `wilayah_kodepos`
`ba84971` (2026-07-17).

**Keterbatasan sumber yang harus diketahui:**

- Ketiga repositori dikelola satu pemelihara komunitas, bukan instansi pemerintah. Repositori tidak menyebut
  asal data primer poligon maupun kode pos. Bukan data resmi BIG/BPS/Pos Indonesia. Untuk keperluan hukum,
  perpajakan, atau batas sengketa, verifikasi ke sumber resmi.
- README S3 menyatakan poligon **disederhanakan** (resolusi rendah). Batas bersama antar-wilayah tidak
  persis berimpit.
- Kode di sini adalah kode Kemendagri. Kode BPS pada level kecamatan ke bawah bisa berbeda dan **tidak
  dimuat** karena tidak ada di sumber yang diperiksa.

## Kualitas data (hasil validasi)

Jumlah di semua level cocok dengan tabel README S3 (1 / 11 / 4 / 171 / 332 / 1.507). Kode di S1, S2, S3
saling cocok (2.026 kode, tanpa selisih nama). Kode pos terisi 1.839/1.839 (269 kode pos unik, semua `95xxx`).
Semua poligon valid setelah perbaikan dan lolos tulis-baca WKT/GeoJSON. Uji 9 titik acuan
(balai kota Manado, Tahuna, Melonguane, dst.) jatuh di kab/kota yang benar.

`qa_flag`:

| Nilai | Arti | Jumlah |
|---|---|---|
| `ok` | ≥ 90% luas berada di dalam poligon induk | kab/kota 9, kecamatan 162, desa/kel 1.489 |
| `batas_tidak_presisi` | 50–90% di dalam induk (efek penyederhanaan, umumnya pesisir) | kecamatan 1, desa/kel 330 |
| `periksa_lokasi` | < 50% di dalam induk; lokasi poligon patut dicek | desa/kel 19 |
| `geometri_diperbaiki` | geometri tidak valid di sumber ("nested shells": pulau kecil ≤ 0,01 km² tertelan poligon utama; 1 self-intersection), diperbaiki dengan union bagian poligon | kab/kota 6, kecamatan 8, desa/kel 1 |

Dari 19 `periksa_lokasi`, hanya 3 yang titik dalamnya berada di kecamatan lain
(`71.01.10.2020`, `71.07.10.2006`, `71.71.06.1005`), kemungkinan salah letak di sumber. Sisanya jatuh di
pesisir di luar poligon kecamatan yang kasar. Rinciannya di `validation_anomali.csv`, termasuk 12 pasangan
kecamatan yang tumpang tindih > 5% (terbesar Sario–Wanea 30%).

**Saran pemakaian:** untuk memetakan outlet ke wilayah, lakukan point-in-polygon pada poligon desa/kelurahan,
lalu cadangkan ke jarak terdekat ke `lat/lng_titik_dalam` bila titik jatuh di celah. Hindari menjumlahkan luas
anak untuk menebak luas induk (rasio luas anak/induk berkisar 0,83–1,23).

## Perubahan dari skrip lama

- Poligon kotak diganti poligon sumber. Provinsi dan semua kab/kota kini berupa MultiPolygon (kepulauan
  terpisah).
- **Kode kab/kota lama tertukar:** Minahasa Tenggara adalah `7107` (skrip lama `7109`) dan Kep. Siau Tagulandang
  Biaro adalah `7109` (skrip lama `7107`).
- Kode buatan sendiri (`KEC-MND-WNG`, `KEL-MND-CLC`) diganti kode Kemendagri; properti GeoJSON `bps_code`
  diganti `code` / `code_compact`. Ubah konsumen yang masih memakai kode lama.
- Cakupan: 18 kecamatan dan 12 kelurahan terpilih → seluruh 171 kecamatan dan 1.839 desa/kelurahan.
- Ke-18 nama kecamatan dan 12 nama kelurahan di skrip lama ada di sumber (kecuali dekorasi
  "Bitung Timur (Pasar Tua)" yang di sumber hanya "Bitung Timur"). Namun kode pos lama hanya cocok dengan S2
  untuk 5 dari 12 kelurahan (Wenang Selatan, Bahu, Tikala Baru, Paal Dua, Airmadidi Atas); 7 lainnya berbeda
  (mis. Calaca 95112 vs 95121, Sario Kotabaru 95114 vs 95113, Paniki Bawah 95258 vs 95256). Tanpa sumber resmi
  Pos Indonesia belum bisa dipastikan sisi mana yang benar. Nama kelurahan tidak unik (mis. "Bahu" ada 3,
  "Sendangan" ada 5), jadi cocokkan dengan kode, bukan nama.
- Properti `crs` di GeoJSON dihapus (RFC 7946: koordinat selalu WGS 84, urutan lng, lat).
