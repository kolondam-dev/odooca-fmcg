# I3 — Diagnostik HPP dan valuasi stok

Status: **alat diagnostik read-only dan rencana; belum dijalankan pada database
demo.** Hasil pertama akan dicatat di dokumen ini setelah dijalankan pemilik/agen
deploy. Katalog `REPORT_CATALOG.csv` tidak berubah oleh paket ini; seluruh 58 ID
tetap `BELUM_DITERIMA`.

## Masalah yang diselesaikan

Laporan HPP tidak bisa diterima hanya karena menu atau angka saldo ada. HPP
ditentukan oleh dua properti per kategori produk yang tidak tampil di layar
daftar produk:

| Properti | Nilai | Akibat |
|---|---|---|
| `property_cost_method` | `standard`, `fifo`, `average` | Dasar nilai keluar: biaya standar, lapisan pertama masuk, atau rata-rata bergerak |
| `property_valuation` | `periodic`, `real_time` | `real_time` membuat stock valuation layer dan jurnal per pergerakan; `periodic` hanya menilai saat tutup buku/manual |

Odoo 19 membuat kategori **baru** dengan `periodic` secara default, sedangkan
data demo dibangun dengan FIFO + `real_time`. Dua kategori yang terlihat sama di
UI bisa berbeda metode. Tanpa membaca kedua field itu, laporan HPP bisa tampak
benar untuk satu kategori dan salah untuk kategori lain.

## Profil demo yang diasumsikan

`DEMO_PROFILE = {"cost_method": "fifo", "valuation": "real_time"}` — ini
**asumsi** ([A]) dari cara data demo disusun, bukan hasil baca database. Skrip
melaporkan setiap penyimpangan, bukan menerimanya diam-diam.

## Yang diukur skrip

`scripts/ops/verify_finance_i3_costing.py` (read-only, tanpa `write`/`create`):

- jumlah kategori dan sebaran `cost_method` serta `valuation`;
- daftar kategori yang menyimpang dari profil demo, dengan metode aktualnya;
- kategori `real_time` yang belum punya satu pun stock valuation layer — tanda
  valuasi belum pernah terbentuk;
- total `value`/`remaining_value` layer, jumlah layer dengan `remaining_qty`
  negatif, dan layer yang menyisakan stok dengan nilai nol;
- jumlah produk storable dengan `standard_price` nol.

Keluaran berupa satu baris `FINANCE_I3_COSTING={...}` (JSON) dan
`FINANCE_I3_COSTING_RUN=PASS`. Label `PASS` di sini berarti **pembacaan
selesai**, bukan penerimaan angka HPP.

## Cara menjalankan

Di sandbox/CI (database disposable):

```bash
docker exec -i odoo /opt/deploy/init.sh shell --no-http \
  < scripts/ops/verify_finance_i3_costing.py
```

Di database demo production, pemilik/agen deploy menjalankan perintah yang sama
di dalam container; skrip tidak menulis apa pun. Logika agregasi juga diuji
tanpa Odoo lewat `python scripts/ops/verify_finance_i3_costing.py --self-test`
(berjalan di job `static`), dan pembacaan registry diuji di job `init-test`.

## Cara membaca hasil

1. `deviations` kosong → seluruh kategori memakai FIFO + `real_time`. Lanjut ke
   tie-out angka HPP.
2. Ada `deviations` → jangan mengubah apa pun dulu. Catat kategori dan metode
   aktualnya, lalu putuskan: menyelaraskan kategori ke profil demo, atau
   menerima metode campuran dan menyatakan itu di laporan.
3. `real_time_without_layers` tidak kosong → valuasi kategori itu belum punya
   bukti; HPP-nya belum bisa diterima meski jurnal ada.
4. `zero_cost_products` besar → biaya standar produk belum diisi; FIFO tetap
   memakai nilai masuk, tetapi laporan berbasis biaya standar akan menyesatkan.

## Keputusan yang menunggu

| Opsi | Isi | Konsekuensi |
|---|---|---|
| A | Pertahankan FIFO + `real_time` untuk seluruh kategori | Paling dekat dengan data demo; butuh disiplin lot/expiry dan layer yang rapi |
| B | Pindah ke `standard` + `periodic` | Sederhana untuk demo, tetapi HPP tidak terbentuk per pergerakan dan selisih harus dijurnal manual |
| C | Campuran, dinyatakan per kategori | Fleksibel, tetapi setiap laporan harus menyebut metode per kategori dan tie-out menjadi lebih mahal |

Rekomendasi sementara: **A**, dengan syarat hasil diagnostik bersih. Untuk
distributor FMCG dengan expiry dan lot, `real_time` memberi jejak yang bisa
diaudit; memilih B akan menghapus jejak itu dan memindahkan beban ke jurnal
manual. Rekomendasi ini baru berlaku setelah angka aktual dibaca, bukan
sebelumnya.

## Yang belum dibuktikan

- [BU] Eksekusi pada database demo production dan hasil `FINANCE_I3_COSTING`.
- [BU] Tie-out HPP per report ID terhadap oracle independen.
- [BU] Perlakuan selisih kurs, landed cost, dan return terhadap layer.
- [BU] Sign-off Finance Controller.

## Batas paket ini

- Tidak ada perubahan metode costing, valuasi, kategori, produk, atau jurnal.
- Tidak ada perubahan `deploy/init.sh`, `INIT_MODULES`, atau data seed.
- Skrip hanya membaca; `--self-test` tidak menyentuh database sama sekali.
