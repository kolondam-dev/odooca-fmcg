# Rekonsiliasi Design System ↔ PWA ↔ Backend

Dibuat oleh `claude-design`, 2026-11-08. Sumber: mockup 62 layar + bundle DS, kode `pwa/` (cabang `agen/pwa-ui-tokens-atoms`), kontrak `pwa/src/domain/contracts.ts` (13 command), backend `addons/id_mobile_api/models/mobile_command.py` (6 command), skema snapshot di `contracts.ts`.

Aturan keputusan pemilik: **DS adalah acuan**. Kode PWA lama dan implementasi backend menyesuaikan, bukan sebaliknya. Penandaan: [F] terverifikasi di kode · [A] asumsi · [BU] belum diuji.

## 1. Ringkasan

| Area | Status PWA | Hambatan utama | Siapa menyesuaikan |
|---|---|---|---|
| Token, atom, header, nav | Selesai | Warna navy mockup (#0B1F4D) ≠ PWA (#001A57) | DS (ikut PWA) |
| Login, Beranda, Absen | Selesai (peta/foto bergaya lama) | Label & alur absen berubah | PWA (sudah) |
| Outlet, Check-in, Hub kunjungan | Selesai | Jam/jarak/tagihan kartu belum ada datanya | Backend (snapshot) |
| Order (POS, stok, katalog, diskon, ringkasan) | **Belum** | Diskon baris/footer, foto SKU, stok sistem, SKU riwayat tidak ada di kontrak | Backend + kontrak |
| Penagihan (transfer/bukti/tidak tertagih) | **Belum** | Tidak ada command AR di backend | Backend (command baru) |
| Hasil kirim, riwayat, koreksi SO | **Belum** | `sales.order.revise` ada di kontrak PWA, tidak di backend | Backend |
| Delivery (DO, POD, TTD, serah terima) | **Belum** | POD ada di backend; tanda tangan & penagihan toko belum | PWA + backend |
| HRIS, cuti, uang lapangan | **Belum** | `hris.*` dan `field_expense.*` tidak ada di backend | Backend |
| Sinkron harian, Antrean, Riwayat | Sebagian (Chip) | Langkah sync DS (5 item) ≠ satu tombol PWA | PWA + backend |

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
- [F] 23 e2e gagal di baseline (collection/delivery:180, expense ×6, next-policy ×6, sales-delivery-rules ×4, review-regressions POD ×2, route-workflow:11, visits:98, ux:217, field:273). Perlu pemilik terpisah; ini bukan akibat DS.
- Proyek **tablet** belum dijalankan pada perubahan DS.

### K12. Lokalisasi dan format
- DS: Indonesia, Rp, WITA, jam `HH.mm`. PWA mencampur `:` dan `.` (mis. LiveClock). **Rekomendasi:** satu util format di `domain/format.ts`, tes unit.

## 3. Urutan integrasi yang disarankan

1. **Selesai:** token → atom → shell (header, nav) → Login/Beranda/Absen → Outlet/Check-in/Hub.
2. **Berikutnya (PWA saja, tanpa menunggu backend):** peta+foto (K8), Order POS dengan data yang ada (stepper, katalog, ringkasan, tanpa diskon/foto), Hasil kirim, Selesai kunjungan, Lainnya/Antrean/Riwayat.
3. **Butuh backend dulu:** K2 (progres sync), K3 (penagihan), K4 (diskon, foto SKU, riwayat), K10 (command yang hilang), K7 (jam/jarak/AR).
4. **Delivery:** DO, detail, POD (sudah ada backend), TTD (PWA), penagihan toko (K3).
5. **Pembersihan:** hapus CSS lama dan TaskForm (K9, K11), jalankan tablet.

## 4. Keputusan yang perlu pemilik hanya bila bertentangan dengan rekomendasi di atas

Tidak ada keputusan yang menunggu. Semua rekomendasi memakai prinsip: DS menang, fitur tanpa dukungan backend tampil "Segera tersedia" dan dinyalakan lewat kapabilitas dari server, bukan hard-code.
