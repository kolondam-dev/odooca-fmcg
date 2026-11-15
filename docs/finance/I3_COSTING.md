# I3 — Diagnostik HPP dan valuasi stok

Status: **alat diagnostik read-only; sudah dibaca pada database disposable CI,
belum pada database demo.** Hasil pertama pada database demo akan dicatat di
dokumen ini setelah dijalankan pemilik/agen deploy. Katalog
`REPORT_CATALOG.csv` tidak berubah oleh paket ini; seluruh 58 ID tetap
`BELUM_DITERIMA`.

## Masalah yang diselesaikan

Laporan HPP tidak bisa diterima hanya karena menu atau angka saldo ada. HPP
ditentukan oleh dua properti per kategori produk yang tidak tampil di layar
daftar produk:

| Properti | Nilai | Akibat |
|---|---|---|
| `property_cost_method` | `standard`, `fifo`, `average` | Dasar nilai keluar: biaya standar, lapisan pertama masuk, atau rata-rata bergerak |
| `property_valuation` | `periodic`, `real_time` | `real_time` memberi nilai per pergerakan dan jurnalnya; `periodic` hanya menilai saat tutup buku/manual |

Odoo 19 membuat kategori **baru** dengan `periodic` secara default. [A] Data demo
diasumsikan dibangun dengan FIFO + `real_time`, tetapi asumsi itu belum
diverifikasi pada database demo. Dua kategori yang terlihat sama di UI bisa
berbeda metode. Tanpa membaca kedua field itu, laporan HPP bisa tampak benar
untuk satu kategori dan salah untuk kategori lain.

## Profil demo yang diasumsikan

`DEMO_PROFILE = {"cost_method": "fifo", "valuation": "real_time"}` — ini
**asumsi** ([A]) dari cara data demo disusun, bukan hasil baca database. Skrip
melaporkan setiap penyimpangan, bukan menerimanya diam-diam.

[A] Asumsi itu sudah bertentangan dengan satu pengamatan: pada database
disposable CI (2026-11-15) seluruh **46 kategori** terbaca `standard` +
`periodic`, yaitu default Odoo 19, bukan FIFO + `real_time`. Itu bukan bukti
tentang database demo, tetapi cukup untuk menolak menganggap profil demo sebagai
fakta sampai dijalankan di sana.

## Model valuasi di Odoo 19

Odoo 19 menghapus model `stock.valuation.layer` yang dipakai versi sebelumnya.
Nilai stok sekarang melekat pada pergerakan stok: `stock.move.value`,
`remaining_qty`, dan `remaining_value`, dengan riwayat perubahan manual di
`product.value`. Skrip membaca `stock.move`; bila suatu database masih punya
`stock.valuation.layer`, model itu yang dibaca. Pengamatan ini muncul dari CI
2026-11-15: bagian layer melaporkan `available: false` karena modelnya tidak ada
di Odoo 19.

## Yang diukur skrip

`scripts/ops/verify_finance_i3_costing.py` (read-only, tanpa `write`/`create`):

- jumlah kategori dan sebaran `cost_method` serta `valuation`;
- daftar kategori yang menyimpang dari profil demo, dengan metode aktualnya;
- kategori `real_time` yang belum punya satu pun pergerakan bernilai — tanda
  valuasi belum pernah terbentuk;
- dari `stock.move`: jumlah pergerakan selesai yang bernilai, total `value`,
  pergerakan yang masih menyisakan stok (`remaining_qty = True`), total
  `remaining_qty`/`remaining_value`, jumlah yang `remaining_qty` negatif, dan
  jumlah yang menyisakan stok dengan nilai nol (atau padanan layer pada database
  pra-19);
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
3. `real_time_without_valuation` tidak kosong → valuasi kategori itu belum punya
   bukti; HPP-nya belum bisa diterima meski jurnal ada.
4. `zero_cost_products` besar → biaya standar produk belum diisi; FIFO tetap
   memakai nilai masuk, tetapi laporan berbasis biaya standar akan menyesatkan.

## Keputusan yang menunggu

| Opsi | Isi | Konsekuensi |
|---|---|---|
| A | Pertahankan FIFO + `real_time` untuk seluruh kategori | Paling dekat dengan data demo; butuh disiplin lot/expiry dan jejak nilai yang rapi |
| B | Pindah ke `standard` + `periodic` | Sederhana untuk demo, tetapi HPP tidak terbentuk per pergerakan dan selisih harus dijurnal manual |
| C | Campuran, dinyatakan per kategori | Fleksibel, tetapi setiap laporan harus menyebut metode per kategori dan tie-out menjadi lebih mahal |

Rekomendasi sementara: **A**, dengan syarat hasil diagnostik bersih. Untuk
distributor FMCG dengan expiry dan lot, `real_time` memberi jejak yang bisa
diaudit; memilih B akan menghapus jejak itu dan memindahkan beban ke jurnal
manual. Rekomendasi ini baru berlaku setelah angka aktual dibaca, bukan
sebelumnya. Catatan: database CI sudah menunjukkan default Odoo 19 (`standard` +
`periodic`) untuk 46/46 kategori, jadi memilih B berarti menerima keadaan
default, bukan mengubah ke arah yang lebih sederhana.

## Yang sudah dibuktikan

- [F] Logika agregasi lulus `--self-test` di job `static` CI.
- [F] Pembacaan registry berjalan di database disposable CI (`init-test` run
  `43681641152`, 2026-11-15, commit `e0b5602`): 46 kategori, seluruhnya
  `standard` + `periodic`; `stock_account` terpasang; sumber valuasi terbaca
  `stock.move (Odoo 19)`.
- [F] Database disposable itu tidak punya pergerakan stok, sehingga
  `done_valued_moves` = 0 dan total bernilai 0. CI membuktikan jalur baca dan
  bentuk keluaran, bukan angka HPP.
- [F] Pada Odoo 19 model `stock.valuation.layer` tidak ada; skrip membaca
  `stock.move.value` dan tetap punya jalur baca layer untuk database pra-19.
- [F] `install-test` dan `init-test` hijau pada commit integrasi `e0b5602`
  setelah PR #138 (jam uji deterministik `id_mobile_api`) masuk `main`.

## Yang belum dibuktikan

- [BU] Eksekusi pada database demo production dan hasil `FINANCE_I3_COSTING`.
- [BU] Angka `stock.move` pada database yang benar-benar punya pergerakan dan
  nilai; database disposable CI kosong.
- [BU] Tie-out HPP per report ID terhadap oracle independen.
- [BU] Perlakuan selisih kurs, landed cost, dan return terhadap nilai pergerakan.
- [BU] Sign-off Finance Controller.

## Batas paket ini

- Tidak ada perubahan metode costing, valuasi, kategori, produk, atau jurnal.
- Tidak ada perubahan `deploy/init.sh`, `INIT_MODULES`, atau data seed.
- Skrip hanya membaca; `--self-test` tidak menyentuh database sama sekali.
