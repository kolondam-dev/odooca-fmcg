# Rekonsiliasi Design System ↔ PWA ↔ Backend

Dibuat oleh `claude-design`, 2026-11-08. Sumber: mockup 62 layar + bundle DS, kode `pwa/` (cabang `agen/pwa-ui-tokens-atoms`), kontrak `pwa/src/domain/contracts.ts` (13 command), backend `addons/id_mobile_api/models/mobile_command.py` (6 command), skema snapshot di `contracts.ts`.

Aturan keputusan pemilik: **DS adalah acuan**. Kode PWA lama dan implementasi backend menyesuaikan, bukan sebaliknya. Penandaan: [F] terverifikasi di kode · [A] asumsi · [BU] belum diuji.

## 1. Ringkasan

| Area                                          | Status PWA                       | Hambatan utama                                                               | Siapa menyesuaikan     |
| --------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------- | ---------------------- |
| Token, atom, header, nav                      | Selesai                          | Warna navy mockup (#0B1F4D) ≠ PWA (#001A57)                                  | DS (ikut PWA)          |
| Login, Beranda, Absen                         | Selesai (peta/foto bergaya lama) | Label & alur absen berubah                                                   | PWA (sudah)            |
| Outlet, Check-in, Hub kunjungan               | Selesai                          | Jam/jarak/tagihan kartu belum ada datanya                                    | Backend (snapshot)     |
| Order (POS, stok, katalog, diskon, ringkasan) | **Belum**                        | Diskon baris/footer, foto SKU, stok sistem, SKU riwayat tidak ada di kontrak | Backend + kontrak      |
| Penagihan (transfer/bukti/tidak tertagih)     | **Belum**                        | Tidak ada command AR di backend                                              | Backend (command baru) |
| Hasil kirim, riwayat, koreksi SO              | **Belum**                        | `sales.order.revise` ada di kontrak PWA, tidak di backend                    | Backend                |
| Delivery (DO, POD, TTD, serah terima)         | **Belum**                        | POD ada di backend; tanda tangan & penagihan toko belum                      | PWA + backend          |
| HRIS, cuti, uang lapangan                     | **Belum**                        | `hris.*` dan `field_expense.*` tidak ada di backend                          | Backend                |
| Sinkron harian, Antrean, Riwayat              | Sebagian (Chip)                  | Langkah sync DS (5 item) ≠ satu tombol PWA                                   | PWA + backend          |

Cakupan kode: layar yang sudah mengikuti DS = Login, Beranda (3 keadaan), Absen masuk/pulang, Outlet, Check-in, Hub kunjungan (+ sheet Selesai). Sisanya (± 40 layar mockup) masih memakai tata letak lama.

## 2. Konflik dan utang, dengan rekomendasi

### K1. Warna navy

- DS/mockup: #0B1F4D untuk navbar. PWA: `--c-nav` #001A57 (kartu hari, logo), `--c-ink` #0B1F4D (teks).
- [F] PWA sudah memakai dua nilai itu dengan peran berbeda.
- **Rekomendasi:** PWA jadi acuan. Regenerasi bundle DS: navbar = `--c-nav`. Tidak ada perubahan backend.

### K2. Urutan hari kerja: Absen → Sinkron → Kunjungan

- DS: tiga langkah di Beranda; sinkron 5 item (Outlet & PJP, Produk/harga/stok, Tagihan AR, SKU riwayat, Program diskon & budget) dengan progres per item, gagal/ulang, "Lanjut offline".
- PWA: absen lalu satu tombol "Sinkronkan data harian" yang memanggil `MorningSimulation.open()` (satu paket snapshot); tidak ada progres per item.
- **Rekomendasi PWA:** pecah `open()` menjadi tahap bernama (outlet, produk, tagihan, riwayat, diskon) dan tampilkan progres dari event tahap, tanpa mengubah paket.
- **Rekomendasi backend:** pertahankan satu endpoint `/api/v1/sync/snapshot`; tambahkan bagian opsional (`ar`, `order_history`, `discount_programs`) agar tahap AR/diskon dapat gagal terpisah. Sampai bagian itu ada, langkah terkait tampil "Segera tersedia".

### K3. Gerbang order: tagihan dulu

- Keputusan (tabel keputusan rencana): order terbuka bila tagihan tersimpan ATAU ada alasan tidak tertagih.
- PWA kini: order tidak menunggu tagihan (kartu Tagihan = "Segera tersedia").
- **Backend:** perlu command `collection.receipt.submit` (ada di kontrak PWA, tidak di backend) dan command alasan tidak tertagih (baru: mis. `collection.skip`). Snapshot perlu daftar tagihan jatuh tempo per outlet.
- **PWA:** gerbang dinyalakan lewat flag kapabilitas dari `bootstrap` (bukan hard-code) agar versi tanpa AR tetap jalan.

### K4. Order, diskon, stok, katalog

- DS: POS dengan stepper, stok sistem vs tersedia, katalog SKU berfoto, diskon baris dan footer, ringkasan, hasil kirim.
- Kontrak: `products[]` punya harga/stok/kemasan (carton/pack/unit) tetapi **tanpa foto SKU, tanpa diskon, tanpa riwayat order per toko, tanpa budget diskon**. Backend `sales.order.submit` ada; `sales.order.revise` tidak.
- **Rekomendasi:** (a) foto SKU: tambah `image_url` pola sama dengan outlet (`/api/v1/products/<id>/image`), PWA memakai placeholder sampai ada. (b) diskon: simpan sebagai `lines[].discount` + `discount_reason` di payload `sales.order.submit` dan `approval` di respons; backend memvalidasi terhadap budget program. (c) riwayat SKU per toko: bagian snapshot `order_history`. (d) `sales.order.revise`: implementasi backend sebelum layar Koreksi SO diaktifkan.

### K5. Foto toko di Check-in

- Mockup memuat slot "Foto lokasi toko" terpisah. Keputusan: satu paket foto bergeotag; slot itu menjadi status lokasi otomatis.
- **Aksi DS:** ubah layar Checkin di bundle (status lokasi, bukan slot foto).
- Backend tidak berubah: `sales.visit.check_in` sudah menerima paket evidence tunggal.

### K6. Penamaan "Open session / Close session"

- PWA lama memakai tab; DS memakai hub dengan aksi. [F] Tab sudah dihapus; test memakai "Buat order di outlet" / "Selesai kunjungan".
- Istilah "DO" dipertahankan di UI (keputusan). `docs/GLOSSARY.md` perlu satu baris untuk "Hub kunjungan".

### K7. Kartu outlet: jam, jarak, tagihan

- DS kartu menampilkan jam kunjungan, jarak, tagihan. Snapshot punya `time`, `distance` (string) dan `commercial`; kartu belum memakainya karena demo kosong/tak terstruktur.
- **Backend:** isi `time`/`distance` dari PJP dan lokasi terakhir; tambahkan `ar_due_total` agar chip tagihan dapat tampil.
- **PWA:** tampilkan bila ada; jarak dihitung klien dari fix GPS (tanpa route/ETA, sesuai keputusan).

### K8. Peta dan foto bukti masih gaya lama

- [F] `CheckinMap`, `VisitPhotoField`, `EvidenceCapture`, `CameraViewfinder` belum DS. Kamera sengaja gelap khusus.
- **Rekomendasi:** bangun ulang sebagai atom `MapPanel` dan `PhotoSlot` (pratinjau, ulangi, status kedaluwarsa) tanpa mengubah paket evidence (hash, watermark). Pertahankan test `visit-evidence`.

### K9. TaskForm monolit (1022 baris)

- Masih dipakai: Order, Extra call, Proof (POD), Uang lapangan, Cuti, Profil. Satu komponen dengan banyak cabang.
- **Rekomendasi:** pecah per layar (seperti AttendanceScreen) saat layar itu dibangun ulang; hapus TaskForm setelah cabang terakhir keluar. Urutan: Order → Extra call → Proof → Uang lapangan → Cuti → Profil.

### K10. Kontrak PWA melebihi backend

- [F] Kontrak 13 command; backend 6. Tidak ada di backend: `sales.order.revise`, `sales.extra_call.request`, `collection.receipt.submit`, `hris.attendance.capture`, `hris.leave.request`, `field_expense.request`, `field_expense.realization.submit`.
- Dampak: absen masuk/pulang hanya tersimpan lokal ("Bukti tersimpan lokal. Pengiriman resmi menunggu API evidence & snapshot peta"); layar HRIS/uang lapangan tidak bisa menyelesaikan siklus.
- **Rekomendasi backend, prioritas:** (1) `hris.attendance.capture` (absen adalah pintu hari kerja), (2) `sales.extra_call.request`, (3) `collection.receipt.submit`, (4) `sales.order.revise`, (5) `field_expense.*`, (6) `hris.leave.request`. Setiap command: handler idempoten per `client_uuid`, kode penolakan bisnis, dan fixture seed.

### K11. Utang CSS dan test

- [F] Selector lama belum dihapus: `.topbar`, `.greeting`, `.quick-*`, `.morning-card`, `.login-*`, `.card-row`, `.sheet*` (dipakai TaskForm). 33 selector < 12 px (daftar di HANDOFF) dan teks 10.85–11.99 px sudah dinaikkan; sisanya per layar.
- [F] 13 e2e yang merah pada hari Minggu diperbaiki di PR #100 (akar: jam fixture Minggu vs `page.clock`, layar penuh menutupi navigasi, snapshot kustom tanpa tanggal bisnis, selektor lama). Tes backend tidak lagi dilewati hari Minggu (tanggal bisnis uji deterministik).
- Proyek **tablet** berjalan di CI; perangkat nyata belum diuji.

### K13. Order POS, Ringkasan, Hasil kirim, Display & stok (Fase 2)

Diterapkan: `OrderScreen` (POS dengan stepper per satuan, cari, kunci principal, SKU sheet, lembar Diskon order, Ringkasan, Catatan/No PO), `OrderResult` (status bertahap dari item antrean), `DisplayStockScreen` (foto display + stok toko, prasyarat order), kartu Hub "Display & stok toko". `OrderSheet` lama dihapus.

| #   | Selisih DS vs backend/kontrak                                                                                                                                | Adaptasi PWA sekarang                                                                                                                  | Rekomendasi backend                                                                                                                                           |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1  | DS: beberapa satuan per SKU sekaligus (4 krt + 2 pak). Kontrak: 1 baris per SKU, 1 satuan, qty 1-999; SKU ganda ditolak.                                     | Keranjang multi-satuan dilebur ke total pcs, dikirim sebagai satuan terbesar yang habis membagi (34 pak). Melebihi 999 -> galat jelas. | Terima `lines[]` dengan SKU sama beda satuan, atau `qty_pcs`; naikkan batas qty.                                                                              |
| B2  | DS: diskon per baris, bertingkat (5%+1%), program promo dengan budget, diskon footer dalam Rp. Kontrak: satu `discount_request {percent, reason}` per order. | Hanya lembar "Diskon order" (persen + alasan) yang dikirim; diskon baris/Rp/program TIDAK ditampilkan agar tak ada UI palsu.           | Tambah `lines[].discounts[{source, percent/amount, program_id}]`, `footer_discount`, daftar `programs[]` + budget di snapshot, dan validasi budget di server. |
| B3  | DS: peringatan limit kredit "menunggu approval". Snapshot hanya `credit_limit`, tanpa piutang berjalan.                                                      | Callout bila total order > `credit_limit` (perkiraan, [A]).                                                                            | Tambah `ar_outstanding`/`ar_due_total` per outlet; server menentukan `needs_approval` karena limit.                                                           |
| B4  | DS: foto SKU. Snapshot tanpa gambar.                                                                                                                         | Placeholder "Foto SKU belum tersedia" di SKU sheet.                                                                                    | `image_url` per produk (`/api/v1/products/<id>/image`).                                                                                                       |
| B5  | DS: Display & stok toko (foto + hitung stok di toko) sebagai langkah. Tidak ada command backend; foto display tidak ada di payload order.                    | Disimpan sebagai draf lokal per outlet; foto wajib sebelum order dikirim (aturan lama dipertahankan).                                  | Command `sales.display_stock.submit` (evidence + `stock[]`), dan kaitkan ke kunjungan.                                                                        |
| B6  | DS: daftar SKU stok toko berdasar riwayat order. Snapshot tanpa riwayat.                                                                                     | 8 SKU pertama katalog (opsional).                                                                                                      | `order_history` per outlet di snapshot (K4c).                                                                                                                 |
| B7  | DS Hasil kirim: tahap Approval SPV, tombol hubungi SPV, konfirmasi admin. Receipt hanya `status`, `reference`, `message`.                                    | Tahap: tersimpan lokal, terkirim, approval (dari status receipt). Tanpa tombol hubungi.                                                | Receipt/endpoint status order: `approval{status, approver, decided_at, reason}`, `confirmed_at`; kontak SPV pada profil.                                      |
| B8  | Stok DS membedakan "stok sistem" dan "tersedia". Kontrak: satu `stock`.                                                                                      | Satu angka stok, polling 20 dtk.                                                                                                       | Pisahkan `stock_on_hand` dan `stock_available` (dikurangi reservasi).                                                                                         |

Catatan teknis: draf lama (`quantities`/`units`) dibaca ke keranjang baru (kompatibel). Tes: `tests/order-cart.test.ts` (8 kasus peleburan satuan), e2e order disesuaikan.

### K14. Kontrak order v2 (Fase 3A) — keputusan pemilik: proses bisnis mockup WAJIB dipatuhi

> **Gerbang kontrak (review PR #109):** PWA hanya mengirim `sales.order.submit`/`revise` v2 bila snapshot membawa `features.order_pricing_v2 === true`. Demo = true; live = OFF sampai backend menyelesaikan kontrak v2 + tes integrasi lalu menyalakan flag di snapshot. Kuantitas tidak valid (>999, negatif, desimal, malformed) diblokir, tidak dipotong.
> Kontrak lama (`pricing_version: 1`, satu satuan per SKU, satu `discount_request`) dinyatakan usang. PWA kini mengirim `pricing_version: 2`; kontrak v1 tetap dibaca hanya untuk item antrean/riwayat lama. **Backend wajib menyesuaikan** (hutang dikerjakan segera setelah PR terkait merge).

| Elemen                                   | Bentuk v2 (payload `sales.order.create` dan `sales.order.revise`)                                                                                                                       | Status PWA                                                                               | Tugas backend                                                                                                                                          |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| Multi-satuan (B1)                        | `lines[] = {product_id, tiers:[{uom, qty}], discounts?:[...]}`; 1 baris per SKU, satuan unik, qty 1–999                                                                                 | Selesai (`order-discount.ts`, `order-cart.ts`)                                           | Terima `tiers`; hitung pcs per satuan dari kemasan                                                                                                     |
| Diskon baris bertingkat (B2)             | `discounts[]` berurutan: `{kind:"program",program_id,percent}` lalu `{kind:"tactical",percent,reason}`; tiap tingkat memotong sisa harga                                                | Selesai; lembar Diskon_baris                                                             | Validasi urutan, hitung berantai, `tactical` ⇒ approval                                                                                                |
| Diskon footer Rp (B2)                    | `footer_discounts[]`: `{kind:"program",program_id,amount}` / `{kind:"tactical",amount,reason}`, dihitung setelah diskon baris                                                           | Selesai; lembar Diskon_footer                                                            | Idem; jumlah ≤ total setelah diskon baris                                                                                                              |
| Program promo berbudget (B2)             | `snapshot.discount_programs[]`: `{id,name,scope:line                                                                                                                                    | footer,principal?,product_ids?,max_percent?,max_amount?,budget_remaining}`               | PWA menampilkan sisa budget dan memvalidasi lokal; data demo dari mock                                                                                 | Sediakan di snapshot harian; kurangi budget saat order diterima |
| Total                                    | `observed_total` = total setelah semua diskon (bilangan bulat Rp, pembulatan per tingkat `round`)                                                                                       | Selesai                                                                                  | Hitung ulang identik; tolak bila beda                                                                                                                  |
| Limit kredit (B3)                        | `outlet.commercial.credit_limit` dan `ar_outstanding`; sisa = limit − AR; callout "Limit kredit terlampaui · order menunggu approval"                                                   | PWA memakai `ar_outstanding` bila ada                                                    | Isi `ar_outstanding` di snapshot; keputusan final di server                                                                                            |
| Foto SKU (B4)                            | `product.image_url` (`/api/v1/products/<id>/image`) + `image_version`; PWA mengunduh sekali, simpan offline (Cache Storage), unduh ulang hanya bila versi berubah; fallback placeholder | Selesai (`sku-photo.ts`, 5 tes)                                                          | Endpoint gambar + `image_version`; tanggung jawab backend bila foto kosong                                                                             |
| Riwayat order untuk Display_stok (B5/B6) | `snapshot.order_history[] = {outlet_id, product_ids[]}`                                                                                                                                 | PWA memakai bila ada; tanpa itu jatuh ke SKU katalog + pemberitahuan                     | Sediakan dataset; command `record_display_stock` (outlet, visit, evidence, items per satuan) **belum ada**, hingga itu Display & stok tetap draf lokal |
| Stok sistem vs tersedia (B8)             | Mockup menampilkan "Stok sistem" (angka gudang, satuan campuran "41 krt · 6 pak") di kartu SKU dan Katalog; stok aktual toko hanya di Display_stok                                      | PWA menampilkan stok sistem dalam satuan campuran                                        | `stock_on_hand`/`stock_available` bila ingin dibedakan                                                                                                 |
| Koreksi order (Koreksi_so)               | `OrderRevision` menerima `pricing_version 2`                                                                                                                                            | Layar Koreksi order baru (Ubah baris order, Ubah diskon, Catatan untuk SPV, Kirim ulang) | Terima revisi v2                                                                                                                                       |

Catatan: `normalizeLine` (peleburan satuan) dihapus; tidak ada lagi pembulatan ke satuan terbesar.

### K15. Fase 3B — Extra call dan Selesai kunjungan

| Layar             | PWA (selesai)                                                                                                                                                                                                                                          | Utang backend / keputusan                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Extra_call        | Layar penuh: cari outlet, "Dipilih", Alasan (select), Catatan, "Tambahkan ke daftar hari ini". Payload `sales.extra_call.request`: `outlet_id?`, `outlet_name`, `reason_code`, `reason`, `note?`.                                                      | Snapshot belum punya daftar outlet di luar PJP: tambah `extra_call_outlets[{id,name,address}]` (opsional; tanpa itu PWA memakai nama bebas). Backend wajib menerima `outlet_id`, `reason_code`, `note` dan memasukkan extra call yang disetujui ke daftar hari ini + laporan harian terpisah.                                                                                                                |
| Selesai_kunjungan | Layar penuh (bukan bottom sheet): stepper, Ada order/Tanpa order, ringkasan Tagihan/Order/Display & stok, catatan min. 5 karakter tanpa order, foto penutup wajib (paket bukti). Hasil kirim: `order_requested` bila ada order, selain itu `no_order`. | Mockup tidak punya alasan "Outlet tutup/Kontak tidak tersedia"; PWA tidak lagi mengirim `outlet_closed`/`unavailable` (enum kontrak tetap valid, alasan masuk catatan). Ringkasan Tagihan baru memakai `ar_outstanding`; rincian lunas/parsial menunggu klaster Penagihan (butuh dataset faktur terbuka per outlet). Status Display & stok baru "Foto"; chip "Stok" menunggu command `record_display_stock`. |

### K16. Fase 3B — Kamera dan Uang lapangan

| Layar                                              | PWA (selesai)                                                                                                                                                                                                                                                                                                                                                                                                                      | Utang backend / keputusan                                                                                                                                                                                                                                                                                           |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Kamera_viewfinder / pratinjau / kedaluwarsa / luar | CameraViewfinder memakai desain DS gelap: judul, kartu stempel (waktu WITA, ±akurasi, koordinat, outlet), shutter + ganti kamera, pratinjau "Ulangi / Gunakan foto" (foto baru dipakai setelah "Gunakan foto"), kedaluwarsa bila foto diambil >60 detik setelah fix lokasi (tombol Gunakan nonaktif, "Ambil ulang"), blokir shutter di luar radius geofence ("Di luar area · N m dari batas"). Slot foto putus-putus (`ev__slot`). | Server tetap menjadi validator resmi (hash/EXIF/lokasi); jendela 60 dtk dan radius berasal dari kontrak outlet. Kartu mockup menampilkan SHA-256 ringkas; PWA menghitung hash saat disimpan (paket bukti) sehingga kartu hanya menyebut "hash dihitung saat disimpan".                                              |
| Uang_lapangan                                      | Layar penuh: Saldo (uang muka cair yang belum direalisasi) + "Ajukan"; daftar "Pengajuan & realisasi" dengan chip Menunggu/Disetujui/Direalisasi/Ditolak; baris membuka layar Realisasi (editor lama dipindah ke komponen DS, logika tidak berubah).                                                                                                                                                                               | Saldo dihitung lokal dari uang muka simulasi; backend perlu menyediakan saldo uang lapangan per karyawan.                                                                                                                                                                                                           |
| Ajukan_uang                                        | Kategori mockup: BBM, Makan, Nginap, Darurat → kontrak `fuel`, `meal`, `lodging`, `emergency` (enum lama tetap diterima untuk antrean lama). Nominal, Keterangan, Foto nota opsional. Scope `trip`, `trip_id` = trip DO pertama atau `FIELD-<tanggal bisnis>`.                                                                                                                                                                     | Mockup tidak punya KM awal, tanggal rencana, H-1 BBM terencana, scope DO/toko: dipindah ke realisasi (KM sebelum/sesudah + foto odometer) atau diturunkan server. Backend wajib menerima 4 kategori baru, `trip_id` hari-kerja, policy approval BBM (sebelumnya `fuel_emergency` = SPV+BM) dan `evidence` opsional. |

### K12. Lokalisasi dan format

- DS: Indonesia, Rp, WITA, jam `HH.mm`. PWA mencampur `:` dan `.` (mis. LiveClock). **Rekomendasi:** satu util format di `domain/format.ts`, tes unit.

## 3. Urutan integrasi yang disarankan

1. **Selesai:** token → atom → shell (header, nav) → Login/Beranda/Absen → Outlet/Check-in/Hub → Order POS/Ringkasan/Hasil kirim/Display & stok (K13).
2. **Berikutnya (PWA saja, tanpa menunggu backend):** peta+foto (K8), Selesai kunjungan (penyempurnaan), Lainnya/Antrean/Riwayat.
3. **Butuh backend dulu:** K2 (progres sync), K3 (penagihan), K4/K13 B1-B8 (multi-satuan, diskon baris/program, foto SKU, riwayat, display & stok, approval), K10 (command yang hilang), K7 (jam/jarak/AR).
4. **Delivery:** DO, detail, POD (sudah ada backend), TTD (PWA), penagihan toko (K3).
5. **Pembersihan:** hapus CSS lama dan TaskForm (K9, K11), jalankan tablet.

## 4. Keputusan yang perlu pemilik hanya bila bertentangan dengan rekomendasi di atas

Tidak ada keputusan yang menunggu. Semua rekomendasi memakai prinsip: DS menang, fitur tanpa dukungan backend tampil "Segera tersedia" dan dinyalakan lewat kapabilitas dari server, bukan hard-code.
