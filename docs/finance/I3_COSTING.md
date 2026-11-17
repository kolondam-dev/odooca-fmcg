# I3 — Diagnostik HPP dan valuasi stok

Status: **alat diagnostik read-only; sudah dibaca pada database disposable CI,
belum pada database demo.** Paket ini sudah di-merge ke `main` (`2fb6172`,
PR #140) dan production sudah men-deploy commit itu (`bab86712`, SUCCESS,
registry loaded), tetapi diagnostik pada database demo belum dijalankan. Hasil
pertama pada database demo akan dicatat di dokumen ini setelah dijalankan
pemilik/agen deploy. Katalog `REPORT_CATALOG.csv` tidak berubah oleh paket ini;
seluruh 58 ID tetap `BELUM_DITERIMA`.

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

## Lingkup perusahaan

`collect(env, company=None)` selalu membaca untuk **satu perusahaan**: `env.company`
atau argumen `company`. Tanpa itu, sesi yang boleh membaca dua perusahaan dapat
mencampur nilai keduanya ke dalam total yang diberi label satu perusahaan.

Yang di-scope:

- context `allowed_company_ids=[company.id]` untuk seluruh pembacaan, sehingga
  `env.company` dan properti company-dependent mengikuti perusahaan itu;
- domain `company_id = company.id` pada `stock.move` dan fallback
  `stock.valuation.layer`, termasuk hitungan per kategori dan sisa stok;
- properti kategori (`property_cost_method`, `property_valuation`) dan
  `standard_price` produk, yang keduanya company-dependent;
- keluaran memuat `company_id`, nama perusahaan, dan mata uangnya.

### Regresi dua perusahaan (native Odoo)

`FINANCE_I3_COMPANY_SCOPE_DB=<nama-db>` menambahkan regresi pada sesi shell yang
sama dengan diagnostik read-only. Fixture membuat dua perusahaan yang
sama-sama dapat dibaca dan menambahkan keduanya ke `company_ids` user (tanpa itu
`env.companies` kosong dan `qty_available` native bernilai 0). Satu kategori
bersama memakai metode berbeda per perusahaan (`fifo` vs `average`); satu produk
bersama berharga 0 (A) dan 7 (B). **Kedua** pergerakan dibuat lebih dulu: A
kuantitas 2 bernilai 100, B kuantitas 4 bernilai 250, masing-masing dengan quant
internal.

Setelah kedua fixture ada, `collect()` dipanggil dari konteks yang memuat **kedua**
perusahaan, sehingga penyempitan harus dilakukan oleh `collect()` sendiri:

| | A | B |
|---|---|---|
| pergerakan bernilai | 1 | 1 |
| `value_total` | 100 | 250 |
| `remaining_moves` | 1 | 1 |
| `remaining_qty_total` | 2 | 4 |
| `remaining_value_total` | 100 (`fifo`) | 28 (`average`: 4 × 7) |
| metode kategori | `fifo` | `average` |

Kontrol negatif menjalankan agregat yang sama **tanpa** domain perusahaan dan
menuntut hasil campuran 2 pergerakan / 350. Jadi jika isolasi pada jalur produksi
dihapus, assertion regresi gagal. Semua fixture dibuat di dalam savepoint lalu
di-rollback; variabel DB wajib disebut agar regresi tidak pernah berjalan tanpa
sengaja pada database demo.

```bash
docker exec -e FINANCE_I3_COMPANY_SCOPE_DB=fmcg -i odoo \
  /opt/deploy/init.sh shell --no-http \
  < scripts/ops/verify_finance_i3_costing.py
```

Job `init-test` menjalankan satu perintah ini dan menuntut dua penanda:
`FINANCE_I3_COSTING_RUN=PASS` dan `FINANCE_I3_COMPANY_SCOPE=PASS`.

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
- [F] Regresi native dua perusahaan lulus di `init-test` run `43796734869`
  (commit `6813020`, 2026-11-16): A (`company_id=2`) 1 pergerakan, `value_total`
  100, `remaining_qty_total` 2, `remaining_value_total` 100, metode `fifo`;
  B (`company_id=3`) 1 pergerakan, `value_total` 250, `remaining_qty_total` 4,
  `remaining_value_total` 28, metode `average`. Kontrol negatif tanpa domain
  perusahaan menghasilkan 2 pergerakan / 350, jadi isolasi yang hilang akan
  menggagalkan regresi.
- [F] Diagnostik `FINANCE_I3_COSTING_RUN=PASS` dan regresi
  `FINANCE_I3_COMPANY_SCOPE=PASS` dijalankan dalam satu sesi shell pada
  `init-test`, dan seluruh 23 check PR lulus pada commit `6813020`.

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
