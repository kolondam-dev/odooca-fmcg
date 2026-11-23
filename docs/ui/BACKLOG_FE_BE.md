# Backlog Frontend (PWA) dan Backend — inventarisasi ulang

Disusun 2026-11-19 setelah fase 3B-19 (main `9502838`). Sumber: `pwa/contracts/openapi.json`, `addons/id_mobile_api`, `addons/id_base`, `addons/id_approval`, `pwa/src`, `docs/ui/DS_RECONCILIATION.md` (K1–K33). Setiap klaim backend bertanda berkas; yang tidak sempat dibuktikan ditulis **[perlu verifikasi]**.

Ringkasan satu paragraf: UI PWA hampir habis dikerjakan di sisi tampilan, tetapi **backend baru melayani 6 dari 15 tipe command dan snapshot-nya belum membawa data yang sudah diasumsikan layar (jam/jarak outlet, piutang, extra call, riwayat order, promo, delivery, flag fitur)**. Akibatnya sebagian layar yang sudah jadi (kartu outlet berjam/jarak, peringatan limit kredit, Extra call, Display & stok, Delivery) belum menampilkan data nyata di LIVE. Urutan kerja yang disarankan ada di bagian 4.

---

## 1. Backlog frontend (PWA)

Prioritas: **P0** blok bisnis, **P1** nilai tinggi dan bisa jalan sekarang, **P2** perapian.

| ID    | Pekerjaan                                                                                                     | Prioritas | Butuh backend?  |
| ----- | ------------------------------------------------------------------------------------------------------------- | --------- | --------------- |
| FE-1  | Komponen `UnitQty` (badge satuan karton/pack/pcs)                                                             | P1        | Tidak           |
| FE-2  | Komponen serupa: `Money`, `SyncStatusChip`, `SkuLine`, `StockBadge`, `Timestamp`, `MetaItem`, `DiscountBadge` | P1–P2     | Tidak           |
| FE-3  | Modul Extra call: lengkapi (status, penandaan, tanpa direktori)                                               | P1        | Ya (BE-3)       |
| FE-4  | Modul NOO (registrasi outlet baru)                                                                            | P1        | Ya (BE-4)       |
| FE-5  | Saran order di POS                                                                                            | P1        | Sebagian (BE-6) |
| FE-6  | Penyederhanaan layar Absen/Check-in                                                                           | P1        | Tidak           |
| FE-7  | Layar Outlet_kosong aktif                                                                                     | P0        | Ya (BE-5)       |
| FE-8  | Sisa Kunjungan_hub (faktur, tagihan, "Mulai penagihan")                                                       | P1        | Ya (BE-7)       |
| FE-9  | Tata letak lama di layar persetujuan/koreksi (K32)                                                            | P2        | Tidak           |
| FE-10 | Peninjauan tablet dan aksesibilitas                                                                           | P2        | Tidak           |

### FE-1. Komponen `UnitQty` — badge satuan

**Masalah hari ini.** Jumlah dalam satuan campuran tampil sebagai teks panjang dan tidak seragam: `stockText()` → "41 krt · 6 pak", `tierText()` → "4 krt 2 pak", `"${qty} ${unit}"` di layar Delivery, dan "{pcs} pcs · {n} Karton" di POS. Tersebar di `OrderScreen`, `DisplayStockScreen`, `OrderCorrections`, `DeliveryTaskEditor`, `OrderResult`.

**Usulan tampilan.** Satu komponen, satu bentuk: `[ikon-karton] 1  [ikon-pack] 2  [@] 3` — tiga badge kecil, hanya tingkat yang bernilai > 0 yang tampil, urutan tetap karton → pack → pcs.

- Ikon karton: Phosphor `package`; ikon pack/inner: `stack` (atau `cube` yang sudah ada); eaches/pcs: glyph teks **@** (sesuai permintaan). Dua ikon baru ditambah ke `Icon.tsx` (saat ini hanya `box`).
- Angka memakai `tabular-nums`; badge netral (abu) untuk stok, tinta untuk jumlah dipesan, merah untuk kekurangan; warna bukan satu-satunya penanda (ikon + angka tetap).
- **Aksesibilitas:** wadah `role="img"` atau teks tersembunyi "1 karton, 2 pack, 3 pcs"; legenda satuan (arti ikon) tersedia sekali per layar lewat ikon info/tooltip, bukan di tiap baris.
- Varian: `size="sm"` (baris daftar), `size="md"` (kartu), `tone` (`mute | ink | bad | ok`), `zero="Habis"` (bila semua nol).
- API: `<UnitQty pcs={total} packaging={p} />` (pecah otomatis memakai rasio SKU, logika `stockText` dipindah ke `domain/`) dan `<UnitQty carton={…} pack={…} pcs={…} />` (nilai eksplisit untuk baris order/pengiriman).
- Kasus tepi: `pack === carton` (tanpa tingkat pack), stok pecahan karton (basis karton dari snapshot), nol, negatif/selisih; lebar sempit (<360px) → badge turun baris, bukan terpotong.
- Pakai di: POS kartu SKU, baris keranjang, Ringkasan, Display & stok, Koreksi order, Hasil kirim, baris pengiriman/POD, Closing trip, Riwayat.
- Tes: vitest `splitUnits` (semua kombinasi rasio), e2e satu layar per konsumen, penjaga: dilarang `"krt"`/`"pak"` literal di komponen setelah migrasi.

### FE-2. Item serupa yang layak dikomponenkan

Bukti duplikasi (hitungan `grep` di `pwa/src`): `Intl.NumberFormat` 6 kali di 5 berkas; pemetaan status `needs_approval/accepted/rejected` di 12 berkas; `money(` dipakai 59 kali di 13 berkas; `.toFixed(` 18 kali di 8 berkas; `tone: "ok"` 19 kali.

| Komponen            | Fungsi                                                                                                              | Usulan tampilan                                                            | Pengganti                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------- |
| `Money`             | Rupiah konsisten (Rp, titik ribuan, negatif merah, `—` untuk kosong), opsi `compact` (1,2 jt)                       | Teks tabular, tanda minus eksplisit, tanpa desimal; `emphasis` untuk total | 6 formatter `Intl` + `money()`                        |
| `SyncStatusChip`    | Satu pemetaan status → nada + label ("Tersimpan di perangkat", "Terkirim", "Menunggu approval", "Ditolak", "Gagal") | `Chip` bernada + ikon kecil; label tetap penanda                           | Pemetaan status di 12 berkas                          |
| `SkuLine`           | Baris SKU seragam: nama, kode, `UnitQty`, harga, badge diskon                                                       | Dua baris: nama + jumlah (kiri), jumlah rupiah (kanan); kode SKU sub       | `pos-line`, baris Ringkasan/Koreksi/Delivery          |
| `StockBadge`        | Ketersediaan: Tersedia / Menipis / Habis                                                                            | `Chip` ok/warn/bad; ambang menipis dari backend (par)                      | Teks "Habis" di POS                                   |
| `Timestamp`         | Waktu kejadian `HH.mm.ss` + tanggal relatif ("Hari ini", "Kemarin")                                                 | Teks kecil mute; tanda "WITA" hanya bila perlu                             | `when()` di Riwayat/Antrean, "Tersimpan di perangkat" |
| `MetaItem`          | Pasangan ikon + teks pendek (jam, jarak, piutang, telepon)                                                          | Baris meta kartu DS (`ui-ocard__m`)                                        | Meta di kartu outlet, Beranda                         |
| `DiscountBadge`     | Diskon baris/program: `−5%`, `−Rp 2.000`, nama program                                                              | Chip kecil nada info; program ditampilkan di bottom sheet                  | Teks diskon di POS/Ringkasan                          |
| `EmptyState`        | Keadaan kosong DS (ikon, judul, teks, aksi)                                                                         | Sudah ada sebagai `.ui-empty` di Outlet_kosong; jadikan komponen           | Teks "Tidak ada …" polos                              |
| `Stepper`/`DayStep` | Langkah bernomor (hari kerja, hub kunjungan)                                                                        | Sudah ada `DayStep`; angkat ke `ui/`                                       | `DayStep` lokal                                       |

### FE-3. Modul Extra call

**Sudah ada:** `ExtraCallScreen` (cari di `snapshot.extra_call_outlets`, alasan, catatan) mengirim `sales.extra_call.request`.

**Kekurangan:**

1. Backend belum ada (BE-3) dan snapshot belum membawa `extra_call_outlets`; tanpa direktori, layar jatuh ke ketik nama bebas — tidak boleh di LIVE (mendorong data sampah). Usulan: tanpa direktori, tombol dinonaktifkan dan tawarkan **NOO**.
2. Tidak ada umpan balik status (Menunggu / Disetujui / Ditolak). Usulan: baris di Antrean/Riwayat dengan `SyncStatusChip` dan, bila disetujui, outlet muncul di daftar Outlet bertanda **Extra** (chip), terpisah dari PJP (sesuai teks layar "tercatat terpisah di laporan harian").
3. **Diputuskan: persetujuan Extra call oleh Supervisor.** Kategori `extra_call` (Tier 1 Supervisor, SLA 2 jam) sudah ada di `id_approval`; yang belum ada model sasarannya (BE-16) dan command (BE-3).
4. Tombol "Tambahkan ke daftar hari ini" menyiratkan langsung ada di daftar, padahal bisa menunggu approval; ganti label menjadi "Ajukan extra call" bila approval wajib.
5. Aksesibel dari Outlet_kosong dan dari Outlet (sudah).

### FE-4. Modul NOO (registrasi outlet baru) — belum ada

Tidak ada form, tipe command, maupun mockup DS. Usulan:

- **Pintu masuk:** Outlet (tombol di toolbar bersama Extra call), Outlet_kosong, dan tautan "Outlet belum terdaftar?" di Extra call.
- **Bentuk:** layar penuh bertahap (3 langkah, gaya `DayStep`), draf tersimpan offline:
  1. **Identitas:** nama toko, nama pemilik/PIC, telepon (validasi 08…/+62…), kanal/jenis (dari daftar), jam buka (opsional).
  2. **Lokasi dan foto:** alamat (otomatis dari GPS, dapat diedit), kelurahan/kota, koordinat GPS dengan aturan akurasi yang sama dengan check-in, foto depan toko (paket bukti yang sama dengan `Evidence`), foto tambahan opsional.
  3. **Ringkasan dan kirim:** tinjau, syarat pembayaran awal (default Tunai/COD, tanpa kredit sampai disetujui), tombol "Ajukan outlet baru".
- **Cegah duplikat:** sebelum kirim, cek lokal outlet serupa (nama mirip dan jarak < 50 m) dari `outlets` + `extra_call_outlets`; tampilkan `Callout` warn "Mirip: Toko X (30 m)" dengan opsi "Gunakan outlet ini" atau "Tetap daftarkan baru". Server tetap memeriksa duplikat.
- **Status:** `SyncStatusChip` di Riwayat (Menunggu approval / Disetujui / Ditolak + alasan). Outlet disetujui muncul di sinkron berikutnya.
- **Diputuskan: persetujuan NOO oleh Branch Manager.** Kategori approval belum ada (BE-17): `new_outlet`, Tier 1 Branch Manager, usulan SLA 24 jam. **Masih terbuka:** apakah boleh kunjungan/order sebelum disetujui (usulan: boleh kunjungan survei + foto, order hanya setelah disetujui) dan apakah outlet disetujui otomatis masuk PJP berikutnya.
- **Command:** `outlet.register.request` (payload: client_uuid, nama, pic, telepon, kanal, alamat, lat/lng + akurasi, foto bukti (`evidence.id`, `packageHash`), syarat bayar awal). Menambah `Command` di `openapi.json` dan zod.

### FE-5. Saran order di POS

**Rekomendasi tampilan (pilihan terbaik):** kartu **"Saran untuk outlet ini"** yang dapat diciutkan, di atas daftar produk — bukan mengisi kotak isian otomatis, dan bukan tombol yang menyembunyikannya sepenuhnya.

- **Mengapa kartu:** (a) kotak isian yang terisi otomatis memicu order tidak sengaja dan mengaburkan siapa yang memutuskan jumlah; (b) tombol pemanggil saja menyembunyikan fitur sehingga jarang dipakai; (c) kartu terlihat, bisa diabaikan tanpa efek, dan satu ketukan menambahkan.
- **Isi kartu:** maksimal 5–7 baris. Tiap baris: nama SKU, **chip alasan** (Rutin, Stok toko kosong, Promo, Wajib listing, Baru), jumlah saran dalam `UnitQty`, tombol **+** (tambah ke keranjang). Header: "Saran (5 SKU) · Tambah semua" dan ikon info "Dari mana saran ini?".
- **Perilaku:** keadaan awal terbuka saat keranjang kosong, ciut otomatis setelah ada isi; menambah **tidak mengunci** — kotak isian tetap bisa diubah; baris di keranjang yang berasal dari saran diberi penanda kecil "saran"; saran yang sudah ditambahkan berubah jadi centang. Opsional kedua: teks bayangan (placeholder) pada kotak isian SKU memuat jumlah saran, tanpa mengisi nilai.
- **Pengukuran:** simpan per baris `suggestion: accepted | edited | ignored` pada payload order (opsional, tidak memblokir) untuk menyetel aturan.

**Logika bisnis (aturan, tahap 1, dapat dijelaskan, bukan model):**

1. Kandidat = SKU dalam cakupan hari ini (`products`), aktif, stok sistem > 0.
2. Fakta per outlet–SKU dari server: jumlah (pcs) 3 order terakhir, tanggal order terakhir, rata-rata interval antar order, frekuensi 90 hari, penanda wajib-listing kanal, penanda promo aktif.
3. Fakta di klien (offline, saat kunjungan): **stok aktual di toko** dari langkah Display & stok (K13), bila diisi.
4. Jumlah saran = `max(0, target − stok_toko)` dengan `target` = median 3 order terakhir (proksi konsumsi per siklus); bila stok toko belum dihitung → median penuh, hanya jika hari sejak order terakhir ≥ 0,8 × interval rata-rata (sudah waktunya).
5. Dibulatkan ke kelipatan pack (atau karton bila kebiasaan order karton), dibatasi stok sistem, dan **dibatasi sisa kredit** (limit − piutang, sesuai `credit_mode`); bila terpotong, baris diberi catatan.
6. Urutan prioritas: wajib listing → promo → rutin jatuh tempo → stok toko kosong → rekomendasi baru (best seller kanal); outlet tanpa riwayat (NOO) memakai best seller kanal sebagai paket awal.
7. Alasan setiap saran wajib terlihat (chip) — tidak boleh ada saran tanpa penjelasan.

**Pembagian kerja:** _fakta di server, aturan di klien._ Alasannya: stok toko hanya ada di klien saat offline, sehingga hitungan akhir harus di klien; server cukup mengirim fakta ringkas per outlet (kecil: ≤ 7 SKU × ±40 outlet) dalam snapshot. Saat ini backend **tidak mengirim `order_history` sama sekali** dan hanya `top_sku`/`max_order` (`mobile_workday.py:135-166`) → BE-6.

**Keputusan pemilik:** kebijakan target/par (median 3 order atau par manual per kanal), kelipatan minimum order, apakah SKU wajib listing ada di master (belum terlihat di model).

### FE-6. Penyederhanaan layar Absen/Check-in

**Hari ini (dari kode):** `MorningSession` → "Absen masuk" → `AttendanceScreen` dengan footer **[Perbarui lokasi] [Ambil selfie]** → kamera → footer **[Absen masuk]** + **[Ulangi foto]** → kembali ke `MorningSession` → **[Sinkronkan data harian]**; plus ikon info aturan geofence dan **Absen pulang** di dua tempat (kartu `MorningSession` dan `AttendanceScreen`). Total hingga 6 tombol berbeda untuk satu hari kerja.

**Usulan (3 tombol bermakna, sisanya otomatis):**

1. **Lokasi otomatis:** ambil lokasi saat layar dibuka dan pantau terus; hapus tombol "Perbarui lokasi", ganti dengan ikon segarkan kecil di baris Lokasi (sekunder) dan pembaruan otomatis tiap N detik selama akurasi belum cukup.
2. **Satu tombol utama bertahap:** "Ambil selfie" (kamera langsung terbuka) → setelah foto, tombol utama berubah menjadi **"Absen masuk"/"Absen pulang"**; "Ulangi foto" menjadi tautan teks pada pratinjau, bukan tombol penuh.
3. **Sinkron data harian otomatis** begitu absen masuk tersimpan dan jaringan ada (kartu progres sudah ada); tombol hanya muncul sebagai **"Coba lagi"** saat gagal. Langkah 2 "Sinkron data harian" di `DayStep` tetap sebagai indikator, bukan tombol.
4. **Absen pulang hanya satu pintu** (kartu hari kerja di Beranda/MorningSession); `AttendanceScreen` dipakai sebagai layar proses.
5. Aturan geofence cukup `Callout`/ikon info yang sudah ada; tombol "Mengerti" di sheet dapat diganti tombol tutup standar.
6. Absen di luar area: tetap izinkan dengan alasan (kebijakan sekarang) tetapi tampilkan satu `Callout` warn, bukan dua.

Hasil: dari ±6 tombol menjadi 2 tombol utama (Selfie → Absen) + 1 tautan. Risiko: pemantauan lokasi otomatis memakai baterai → batasi ke layar absen dan hentikan saat kamera terbuka. Tes: e2e alur absen masuk/pulang yang sudah ada diperbarui; tambah tes sinkron otomatis dan kegagalan.

### FE-7 sampai FE-10

- **FE-7 Outlet_kosong:** UI sudah ada; tes e2e `fixme` (K28). Dibuka oleh penanda "PJP kosong sah" (BE-5); tombol NOO nonaktif "Segera tersedia" sampai FE-4.
- **FE-8 Sisa Kunjungan_hub:** daftar faktur berkotak centang, total tagihan jatuh tempo, "Wajib ditagih hari ini", "Mulai penagihan", stepper 4 tahap, Order "Terkunci" — menunggu data piutang (BE-7). Peringatan limit kredit yang sekarang hanya membandingkan `ar_outstanding` dengan `credit_limit`; harus mengikuti `credit_mode` backend (strict/limit/limit_due/approval, termasuk faktur jatuh tempo) — butuh `credit_mode` dan jumlah faktur jatuh tempo di snapshot.
- **FE-9** Layar `DiscountApproval`, `DeliveryApproval`, `OrderCorrections`, form penagihan masih bertata letak lama selain tombol (K32).
- **FE-10** Tablet diperiksa lewat e2e saja; belum ada audit visual tablet, kontras, dan pembaca layar menyeluruh.

**Catatan jujur untuk fase yang sudah merge:** kartu outlet berjam/jarak (3B-14) dan peringatan limit kredit tidak akan tampil di LIVE sampai backend mengisi `time`/`distance` dan `ar_outstanding` (lihat BE-2).

---

## 2. Backlog backend

### 2.1 Endpoint HTTP (`addons/id_mobile_api/controllers`)

| Method | Path                                       | Status        | Catatan                                                                                                               |
| ------ | ------------------------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------- |
| GET    | `/api/v1/me/bootstrap`                     | ADA (PARSIAL) | Peran ditentukan dengan menebak `"driver"` di login/jabatan (`mobile_workday.py:116-120`); tidak mengirim `features`. |
| GET    | `/api/v1/sync/snapshot`                    | ADA (PARSIAL) | Lihat 2.3.                                                                                                            |
| GET    | `/api/v1/outlets/{id}/image`               | ADA           | Dibatasi outlet pada assignment hari ini.                                                                             |
| POST   | `/api/v1/evidence`                         | ADA           | `evidence_api.py`; ada tes.                                                                                           |
| GET    | `/api/v1/evidence/{client_uuid}/{variant}` | ADA           | idem.                                                                                                                 |
| POST   | `/api/v1/sync/commands`                    | ADA (PARSIAL) | Hanya 6 dari 15 tipe command (2.2).                                                                                   |

Tidak ada endpoint lain. Tidak ada pencarian outlet, pagination, atau endpoint status command (PWA harus menebak status dari antrean/sinkron).

### 2.2 Tipe command (`mobile_command.py:17-24` `SUPPORTED_COMMANDS`; kontrak `openapi.json` memuat 15)

| Command                                                               | Status        | Catatan                                                                                     |
| --------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------- |
| `sales.order.submit`                                                  | ADA           | Lihat temuan BE-8 (diskon, versi snapshot).                                                 |
| `sales.visit.check_in` / `check_out`                                  | ADA           | Validasi scope outlet, hari Minggu, tanggal GPS; radius sisi server **[perlu verifikasi]**. |
| `delivery.pod.submit`, `delivery.proof.submit`, `delivery.trip.close` | ADA (PARSIAL) | Handler ada, tetapi snapshot tidak melayani tugas pengiriman (BE-2).                        |
| `sales.extra_call.request`                                            | **KOSONG**    | Tidak ada di backend.                                                                       |
| `hris.attendance.capture`                                             | **KOSONG**    | Absen hanya lokal di PWA.                                                                   |
| `hris.leave.request`                                                  | **KOSONG**    |                                                                                             |
| `field_expense.request`, `field_expense.realization.submit`           | **KOSONG**    |                                                                                             |
| `sales.order.revise`                                                  | **KOSONG**    |                                                                                             |
| `collection.receipt.submit`, `collection.settlement.submit`           | **KOSONG**    | Termasuk modul penagihan.                                                                   |
| `delivery.cash_deposit.submit`                                        | **KOSONG**    |                                                                                             |
| `outlet.register.request` (NOO)                                       | **KOSONG**    | Belum ada di kontrak PWA juga.                                                              |

Command tidak didukung dijawab `UserError("Unsupported command type")` (`mobile_command.py:120-121`); PWA harus memastikan tidak mengantrekan tipe tersebut di LIVE selain lewat flag.

### 2.3 Snapshot (`_snapshot_payload`, `mobile_workday.py:168-255`) vs yang dibutuhkan PWA

| Bidang yang diharapkan PWA                          | Backend             | Dampak                                                                                                          |
| --------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------- |
| `outlets[].time`, `distance`                        | selalu `""`         | Kartu outlet tanpa jam/jarak; tidak ada urutan kunjungan (outlet diurutkan `id`, bukan urutan PJP).             |
| `outlets[].commercial.ar_outstanding`               | tidak dikirim       | Peringatan limit kredit dan piutang tidak tampil.                                                               |
| `commercial.credit_mode`, jumlah faktur jatuh tempo | tidak dikirim       | Mode `strict`/`limit_due` backend (`id_base/models/sale_order.py:136-166`) tak terwakili.                       |
| `deliveries`                                        | **hard-coded `[]`** | Peran Delivery tidak mendapat tugas. `DeliveryTask`/`CollectionTask` ada di OpenAPI tetapi tidak ada sumbernya. |
| `extra_call_outlets`                                | tidak dikirim       | Layar Extra call tanpa direktori.                                                                               |
| `order_history`                                     | tidak dikirim       | Display & stok tanpa riwayat SKU; tidak ada dasar saran order.                                                  |
| `discount_programs`                                 | tidak dikirim       | `order_pricing_v2` tidak mungkin; `id_promo_governance` belum dipetakan.                                        |
| `features` (5 flag)                                 | tidak dikirim       | Semua flag v2 mati di LIVE; backend tidak punya tombol untuk menyalakan.                                        |
| Harga/stok per satuan                               | hanya basis karton  | Cukup untuk kontrak v2, tetapi stok live ikut dalam hash versi (BE-1).                                          |

### 2.4 Temuan yang harus diperbaiki

| ID    | Temuan                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Keparahan          | Bukti                                             |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ------------------------------------------------- |
| BE-1  | **Versi snapshot memuat stok hidup.** `sales.order.submit` menghitung ulang snapshot dan menolak bila versi beda (`mobile_command.py:~198-202`); versi = hash seluruh payload termasuk `stock`. Setiap pergerakan stok membuat order offline ditolak "Stale catalog snapshot version" (409), dan setiap order memicu perhitungan snapshot penuh.                                                                                                                                       | Tinggi             | `mobile_workday.py` (digest), `mobile_command.py` |
| BE-2  | `deliveries: []` dan jam/jarak kosong (lihat 2.3). Peran Delivery tidak berfungsi end-to-end di LIVE.                                                                                                                                                                                                                                                                                                                                                                                  | Tinggi             | `mobile_workday.py`                               |
| BE-3  | Extra call tidak ada (command, model, persetujuan, direktori).                                                                                                                                                                                                                                                                                                                                                                                                                         | Tinggi             | grep `extra_call` kosong                          |
| BE-4  | NOO tidak ada (command, model outlet baru berstatus draf, persetujuan, aturan duplikat).                                                                                                                                                                                                                                                                                                                                                                                               | Tinggi             | —                                                 |
| BE-5  | **PJP kosong ditolak di backend juga:** `_current_assignment` melempar "Assign at least one product and scheduled outlet" (`mobile_workday.py:~96-98`) dan snapshot memberi 422 `configuration_unavailable`. Selain itu, bila tidak ada assignment hari ini, backend **menyalin otomatis** dari hari kerja terakhir (`mobile_workday.py:~71-92`) — artinya "PJP kosong" tidak pernah terjadi dan salesman bisa mengunjungi outlet kemarin tanpa jadwal.                                | Tinggi (keputusan) | `mobile_workday.py`                               |
| BE-6  | Tidak ada fakta untuk saran order (riwayat order per outlet–SKU, interval, wajib listing, promo).                                                                                                                                                                                                                                                                                                                                                                                      | Sedang             | —                                                 |
| BE-7  | Piutang: tidak ada `ar_outstanding`, daftar faktur, jadwal penagihan. Data dasar sudah ada di Odoo (`res.partner.credit`, `account.move` faktur terbuka dan `invoice_date_due`), sehingga **pembacaan** `ar` dapat dibuat sekarang dari akuntansi bawaan; yang benar-benar baru adalah **jadwal penagihan/kolektor**.                                                                                                                                                                  | Sedang             | `id_base/models/sale_order.py`                    | **Bagian baca selesai (PR BE-7): `outlet_receivables`; jadwal penagihan/kolektor dan command `collection.*` tetap terbuka.**
| BE-8  | **Diskon baris tanpa pengajuan:** `discount` per baris dari klien diterima apa adanya dan hanya order dengan `discount_request.percent > 0` ditandai `needs_approval`; `action_confirm` hanya memblokir harga di bawah HPP, bukan diskon taktikal (`id_approval/models/sale_order.py:172-190`). Baris dengan `discount: 0` ikut tertimpa diskon order (`float(...) or discount_pct`). **[perlu verifikasi dengan tes]** — jika benar, salesman dapat memberi diskon tanpa persetujuan. | Tinggi             | `mobile_command.py:~277-283`                      |
| BE-9  | Peran dari `"driver" in login` (`mobile_workday.py:116-120`) — rapuh dan bisa disalahgunakan; gunakan grup.                                                                                                                                                                                                                                                                                                                                                                            | Sedang             | idem                                              |
| BE-10 | Satu SKU atau outlet bermasalah menggagalkan **seluruh** snapshot (422) sehingga satu data master buruk memblokir semua salesman; perlu isolasi (lewati + laporkan).                                                                                                                                                                                                                                                                                                                   | Sedang             | `mobile_workday.py` (`raise UserError`)           |
| BE-11 | `openapi.json` `CatalogRow` (`product_id`, `price_per_carton`, …) berbeda dari payload `catalog_version: 2` yang dikirim (`id`, `sku_code`, `price`, `stock`). **[perlu verifikasi]** apakah gerbang `contracts:check` memakai skema yang benar; kontrak dan implementasi tidak boleh punya dua wujud.                                                                                                                                                                                 | Sedang             | `openapi.json` vs `mobile_workday.py`             |
| BE-12 | Tidak ada endpoint/ruang status command; PWA tidak bisa menampilkan hasil persetujuan (Extra call, NOO, diskon, kredit) selain lewat respons awal.                                                                                                                                                                                                                                                                                                                                     | Sedang             | —                                                 |
| BE-13 | Kebijakan tidak bisa dipakai klien: `credit_mode` (4 mode), faktur jatuh tempo, hari Minggu libur — klien hanya melihat penolakan setelah kirim. Kirim sebagai fakta snapshot.                                                                                                                                                                                                                                                                                                         | Rendah             | —                                                 |

Temuan tambahan dari audit tata kelola approval (`addons/id_approval`, ditambahkan 2026-11-19):

| ID    | Temuan                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Keparahan          | Bukti                                                                                   |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------- |
| BE-14 | **Order PWA berstatus `needs_approval` tetapi tidak pernah membuat permintaan approval.** Handler hanya mengisi catatan diskon dan membalas status; tidak ada pemanggilan `action_request_*` atau pembuatan `fmcg.approval.request`. Permintaan baru lahir bila orang membuka SO di Odoo dan menekan tombolnya. Selain itu `action_request_tactical_discount_approval` mewajibkan akun analitik yang tidak diisi jalur mobile. Hasilnya order menunggu tanpa pemberitahuan ke penyetuju. | Tinggi             | `mobile_command.py` (tidak ada pemanggilan), `id_approval/models/sale_order.py:131-150` |
| BE-15 | **Mesin tier tidak punya zona bebas dan tidak kumulatif.** Tier 1 diskon taktikal dimulai dari `min_discount = 0,01`, jadi diskon berapa pun > 0 memicu approval Supervisor. Dasar tier hanya `max_line_discount` satu order; tidak menghitung diskon bertumpuk (program + baris + footer order) dan tidak mengakumulasi per outlet/salesman/periode.                                                                                                                                    | Tinggi (kebijakan) | `approval_category_data.xml:86-125`, `approval_request.py:156-175`                      |
| BE-16 | Kategori `extra_call` sudah ada (Tier 1 Supervisor, SLA 2 jam) tetapi model sasarannya `fmcg.pjp.visit` **tidak ada** di backend (hanya disebut di pilihan `res_model`).                                                                                                                                                                                                                                                                                                                 | Tinggi             | `approval_category.py:21`, `approval_category_data.xml:241-255`                         |
| BE-17 | Kategori approval untuk **NOO tidak ada**.                                                                                                                                                                                                                                                                                                                                                                                                                                               | Tinggi             | `approval_category_data.xml` (11 kategori, tidak ada outlet baru)                       |

### 2.5 Cakupan tes backend

`id_mobile_api/tests`: `test_commands_api` (15), `test_read_api` (19), `test_evidence_api` (8), `test_existing_demo` (10), `test_pjp_loader_boundaries` (9), `test_staging` (5). Terlihat ada tes versi stale dan tanggal usang; **tidak terlihat** tes untuk: stok berubah di antara snapshot dan submit (BE-1), diskon baris tanpa pengajuan (BE-8), PJP kosong/salin otomatis (BE-5), dan command tidak didukung. Jumlah di atas hitungan `def test` per berkas, bukan hasil eksekusi.

---

## 3. Keputusan pemilik

### 3.1 Sudah diputuskan (2026-11-19)

| #   | Keputusan                                                                                                  | Catatan                                                                                      |
| --- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| D1  | Extra call disetujui **Supervisor**                                                                        | Kategori sudah ada; model sasaran dan command belum (BE-3, BE-16).                           |
| D2  | NOO disetujui **Branch Manager**                                                                           | Kategori belum ada (BE-17).                                                                  |
| D3  | Approval hanya untuk yang **secara kumulatif melebihi tier** yang diatur di tata kelola pengajuan/approval | Tier sudah ada tetapi tidak kumulatif dan tanpa zona bebas (BE-15); rekomendasi di bagian 5. |
| D4  | Detik pada waktu kejadian (K12), PJP kosong sah (K28)                                                      | Sudah dikerjakan/dicatat (K33).                                                              |

### 3.2 PJP: apa, kenapa, dan mengapa keputusan ini saya butuhkan

**Apa itu PJP.** PJP (rencana kunjungan tetap) adalah daftar outlet yang menjadi tugas seorang salesman pada hari tertentu, beserta cakupan kerjanya: gudang, daftar harga, SKU yang boleh dijual, dan kantor untuk absen. Di backend ia berwujud satu record `id.mobile.workday` per salesman per tanggal (`outlet_ids`, `product_ids`, `warehouse_id`, `pricelist_id`, `office_id`). Saat ini PJP hanya berupa kumpulan outlet: **tidak ada urutan kunjungan dan tidak ada jam rencana** (outlet diurutkan menurut id; kolom `time` dan `distance` dikirim kosong).

**Untuk apa PJP dipakai sistem.**

1. **Pagar akses:** snapshot hanya memuat outlet, SKU, dan harga dalam PJP; `sales.visit.check_in`, `sales.visit.check_out`, dan `sales.order.submit` menolak outlet di luar PJP ("tidak termasuk dalam scope assignment aktif hari ini"). Ini yang mencegah salesman memesan atas nama outlet orang lain.
2. **Paket kerja pagi offline:** stok gudang, harga, dan outlet yang diunduh saat sinkron pagi bergantung pada PJP; tanpa PJP tidak ada paket.
3. **Dasar laporan:** kepatuhan rute, kunjungan terencana vs Extra call, call rate, dan efektivitas kunjungan membandingkan realisasi dengan PJP. Extra call "tercatat terpisah" justru karena ada PJP sebagai pembandingnya.
4. **Dasar target dan penagihan:** target kunjungan harian, rute penagihan, dan saran order per outlet berangkat dari daftar outlet yang akan dikunjungi.

**Mengapa saya butuh keputusan soal PJP kosong.** Backend sekarang melakukan dua hal yang saling bertentangan dengan keputusan Anda "PJP kosong sah, salesman hanya Extra call/NOO":

- Bila **tidak ada PJP hari ini**, backend **menyalin diam-diam** PJP dari hari kerja terakhir (`mobile_workday.py` ~baris 71–92). Salesman tampak punya rute, padahal tidak pernah dijadwalkan. Laporan kepatuhan menjadi palsu (kunjungan "terencana" yang tidak ada rencananya) dan supervisor tidak tahu PJP belum diunggah.
- Bila **PJP ada tetapi tanpa outlet**, backend melempar galat (422 `configuration_unavailable`).

Jadi layar Outlet_kosong tidak akan pernah muncul di LIVE kecuali perilaku ini diubah, dan kontrak snapshot (penanda "PJP kosong sah") belum bisa dirancang sebelum aturan penyalinan ditetapkan. Kasus nyata yang memicunya: PJP mingguan terlambat diunggah pada hari Senin, cuti, libur, atau salesman baru.

**Pilihan perilaku (yang perlu Anda pilih):**

| Opsi                                | Perilaku                                                                                                            | Dampak                                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| A. Salin tetap, tetapi **ditandai** | Salin dari hari terakhir dengan `carry_over: true`                                                                  | Operasional jalan terus. PWA menampilkan `Callout` "PJP carry-over, belum dijadwalkan"; laporan memisahkan kunjungan carry-over dari terencana. |
| B. Kosong sah (sesuai D4)           | Tanpa PJP berarti paket tanpa outlet, penanda `pjp_empty: true`, tetap membawa stok/harga/promo/piutang             | Laporan kepatuhan akurat; salesman bergantung pada Extra call (D1) dan NOO (D2); lebih banyak beban Supervisor pada hari PJP telat.             |
| C. Hibrida (rekomendasi saya)       | Default **B**; Supervisor dapat mengaktifkan carry-over per salesman/tanggal (satu ketukan) sebagai keputusan sadar | Akurasi laporan terjaga, operasional tidak macet bila PJP telat, dan ada jejak siapa yang mengizinkan.                                          |

**Hal tambahan yang saya sarankan sekalian** (agar PJP layak jadi dasar laporan): tambahkan model PJP dengan **urutan dan jam rencana** per outlet (menggantikan sekadar `outlet_ids`), dan jadikan `fmcg.pjp.visit` (BE-16) sebagai satu model kunjungan untuk kunjungan terencana **dan** Extra call dengan jenis kunjungan sebagai pembeda. Dengan begitu kartu outlet berjam/jarak (3B-14) mendapat datanya dan Extra call punya rumah.

### 3.3 Keputusan yang masih terbuka

2. NOO: boleh kunjungan survei dan/atau order sebelum disetujui Branch Manager; apakah otomatis masuk PJP. **Dijawab pemilik (2026-11-22): NOO dapat disubmit tanpa order terlebih dahulu; approval oleh Supervisor lalu Branch Manager (rantai dua tier, bukan hanya Branch Manager).** Kunjungan/order sebelum disetujui dan masuk PJP otomatis belum dijawab.
3. Saran order: target (median 3 order vs par manual), kelipatan minimum, sumber SKU wajib listing.
4. Kredit: apakah PWA memblokir order untuk mode `strict` (faktur jatuh tempo) atau hanya memperingatkan. **Dijawab pemilik (2026-11-22): PWA memblokir pada mode `strict`.** Perlu field `credit_mode` dan jumlah faktur jatuh tempo pada snapshot (backlog baru BE-19/FE-12; lihat bagian bawah).
5. Angka batas Tier 0 dan tier per principal (diisi lewat konfigurasi backend, bukan keputusan kode).
6. Jam rencana PJP ("08.30") tanpa detik — asumsi saat ini.

## 4. Urutan kerja yang disarankan

1. **Backend P0 (kontrak dan korektif):** BE-1 (versi snapshot tanpa stok), BE-9, BE-8 (setelah tes), BE-11, `features` pada bootstrap/snapshot, `outlets[].time/distance/urutan`, `deliveries`.
2. **Frontend paralel, tanpa backend:** FE-1 `UnitQty`, FE-2 (`Money`, `SyncStatusChip`, `Timestamp`, `EmptyState`), FE-6 absen.
3. **Backend P1:** BE-7 bagian baca (`ar`, faktur terbuka, `credit_mode`), BE-5 setelah keputusan 1, BE-6 (fakta saran), `order_history`.
4. **Approval (baru):** BE-14 segera (order lapangan menunggu tanpa pemberitahuan), BE-15/BE-18 (angka batas lewat konfigurasi); lalu FE-11.
5. **Frontend P1 setelah data siap:** FE-5 saran order, FE-7 Outlet_kosong, FE-8 sisa hub.
6. **Backend P1 command:** `sales.extra_call.request` (BE-3), `outlet.register.request` (BE-4), `hris.attendance.capture`, kemudian `hris.leave.request`, `field_expense.*`, `collection.*`, `delivery.cash_deposit.submit`, `sales.order.revise`.
7. **Frontend setelah command:** FE-3 lengkap, FE-4 NOO.
8. P2: FE-9, FE-10.

## 5. Tata kelola approval kumulatif — kondisi dan rekomendasi

### 5.1 Yang sudah ada di `id_approval` (dari kode)

| Kategori                                                            | Tier (data awal)                                              | Dasar tier                                                   |
| ------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ |
| Diskon taktikal                                                     | T1 Supervisor ≤ 3%; T2 Branch Manager > 3–7%; T3 Direksi > 7% | % diskon baris tertinggi satu order                          |
| Harga di bawah HPP                                                  | T1 Branch Manager; T2 Direksi/Pemilik                         | otomatis bila harga bersih < standar                         |
| Limit kredit / ToP                                                  | T1 dan T2 (nominal)                                           | nominal                                                      |
| Extra call                                                          | T1 Supervisor, SLA 2 jam                                      | tanpa kriteria; **model sasaran `fmcg.pjp.visit` tidak ada** |
| SKU baru, promo baru, biaya operasional, cuti 2-line, early inbound | tersedia                                                      | —                                                            |
| NOO                                                                 | **tidak ada**                                                 | —                                                            |

Mesin (`approval_request.py:156-175`) membangun rantai **berjenjang**: semua tier yang `min`-nya terlampaui ikut menjadi langkah berurutan (diskon 5% → Supervisor lalu Branch Manager). Tier ditentukan oleh **satu permintaan**, bukan akumulasi.

### 5.2 Kesenjangan terhadap keputusan D3 ("hanya yang kumulatif melebihi tier")

1. **Tidak ada zona bebas approval.** `min_discount` Tier 1 = 0,01, sehingga diskon sekecil apa pun butuh approval Supervisor.
2. **Tidak kumulatif.** Diskon dari program, baris, dan footer order tidak digabung; riwayat diskon outlet/salesman tidak diakumulasi.
3. **Jalur PWA tidak membuat permintaan approval** (BE-14), jadi aturan yang ada pun tidak berjalan untuk order lapangan.
4. NOO dan model Extra call belum ada (BE-16, BE-17).

### 5.3 Rekomendasi desain

1. **Zona bebas sebagai Tier 0.** Tambahkan aturan "Tanpa approval" dengan batas, mis. `≤ X%` efektif per order (X ditetapkan pemilik, per kanal/principal bila perlu). Di bawah batas, order langsung `accepted`.
2. **Ukuran kumulatif yang konsisten, dihitung di server (otoritatif).** Diskon efektif bertumpuk `1 − Π(1 − dᵢ)` dari program + baris + footer order. Pada aturan, tambahkan atribut: `scope` (order, outlet-bulan, salesman-hari, salesman-bulan), `measure` (% tertimbang nilai atau Rp), dan `window`. Tier ditentukan dari nilai kumulatif **termasuk** permintaan yang sudah disetujui dan yang masih menunggu, ditambah order ini.
3. **Mode rantai bisa diatur** per kategori: `chain` (perilaku sekarang, semua tier berurutan) atau `highest` (langsung ke tier tertinggi yang berlaku) — keduanya sah; pemilik memilih.
4. **Permintaan dibuat saat command diproses** (bukan oleh orang yang membuka SO): `sales.order.submit` menghitung level kumulatif, bila melebihi zona bebas membuat `fmcg.approval.request` otomatis dengan akun analitik bawaan konfigurasi, dan mengembalikan status `needs_approval` + referensi (menutup BE-14). Pemberitahuan ke penyetuju dan status balik ke PWA lewat mekanisme status command (BE-12).
5. **Transparansi ke PWA:** snapshot membawa `approval_tiers` (batas zona bebas, rentang tier, pemakaian kumulatif hari ini/periode untuk salesman dan outlet) sehingga POS menampilkan pratinjau "Diskon 4% → perlu Branch Manager" **sebelum** kirim, sekaligus menutup BE-8 (klien tidak lagi dipercaya soal perlu/tidaknya approval; server tetap menetapkan).
6. **Extra call → Supervisor (D1):** buat model `fmcg.pjp.visit` (outlet, salesman, tanggal, alasan, jenis terencana/extra, status, relasi approval) dan sambungkan kategori `extra_call` yang sudah ada; SLA 2 jam; auto-aktifkan di daftar Outlet saat disetujui.
7. **NOO → Branch Manager (D2):** kategori baru `new_outlet` (res_model `res.partner`), Tier 1 Branch Manager (SLA 24 jam); outlet dibuat `active=False` berstatus menunggu, diaktifkan saat disetujui; syarat bayar awal tunai/COD sampai dievaluasi lewat kategori limit kredit yang sudah ada.

### 5.4 Keputusan pemilik (2026-11-19) dan implikasi desain

| Pertanyaan                | Keputusan                 | Implikasi                                                                                                                                 |
| ------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Zona bebas                | Dibuat **Tier 0**         | Aturan "Tanpa approval" dengan batas % yang dapat dikonfigurasi; di bawah batas order langsung diterima.                                  |
| Ukuran kumulatif          | **Persen** diskon efektif | `measure` = % efektif bertumpuk `1 − Π(1 − dᵢ)`; rupiah tidak dipakai sebagai dasar tier.                                                 |
| Rantai                    | **Berjenjang**            | Perilaku mesin sekarang dipertahankan: semua tier terlampaui menjadi langkah berurutan.                                                   |
| Batas per kanal/principal | **Berbeda per principal** | Aturan tier mendapat dimensi `principal_id` (kosong = default umum); aturan khusus principal menimpa default.                             |
| Diskon program resmi      | **Ikut dihitung**         | Diskon `id_promo_governance` masuk akumulasi bersama diskon baris, footer, dan taktikal. Pengelolaan lebih granular dilakukan di backend. |

Catatan desain: karena batas berbeda per principal dan order dapat memuat beberapa principal, kumulatif dihitung **per principal** (baris dikelompokkan menurut principal produk), lalu tier tertinggi di antara principal menentukan rantai. Ini asumsi saya; mohon dikoreksi bila ingin dihitung per order utuh.

### 5.5 Backlog baru dari bagian ini

| ID    | Pekerjaan                                                                                                                                      | Prioritas                 |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| BE-14 | Pembuatan permintaan approval otomatis dari `sales.order.submit` (tanpa wajib analitik). **Selesai (PR BE-14); tier/akumulasi menunggu BE-15** | P0                        |
| BE-15 | Tier 0 zona bebas; aturan kumulatif (`scope`/`measure`/`window`); mode rantai **Selesai (PR BE-15)**                                           | P0                        |
| BE-16 | Model `fmcg.pjp.visit` + command `sales.extra_call.request` + sambungan kategori                                                               | P1                        |
| BE-17 | Kategori `new_outlet` + command `outlet.register.request` + model status outlet                                                                | P1                        |
| BE-18 | `approval_tiers` pada snapshot (zona bebas, rentang tier, pemakaian kumulatif) **Selesai (PR BE-18)**                                          | P1                        |
| FE-11 | Pratinjau tier di POS ("perlu Branch Manager") dan status approval pada Riwayat/Hasil kirim **Selesai (PR FE-11); status per langkah menunggu BE-12** | P1 (setelah BE-14, BE-18) |

## 6. Tindak lanjut jawaban pemilik 2026-11-22

| ID    | Pekerjaan                                                                                                                                           | Prioritas |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| BE-19 | `commercial.credit_mode` (ikut digest) dan blok `outlet_credit` jumlah/total/tertua faktur jatuh tempo per outlet (di luar digest) **Selesai (PR BE-19)** | P1        |
| FE-12 | Mode kredit `strict`: PWA memblokir tombol Kirim order untuk outlet dengan faktur jatuh tempo, dengan penjelasan dan jalur penagihan **Selesai (PR FE-12); jalur penagihan menunggu BE-7/FE-8** | P1        |
| BE-17 | (diperbarui) kategori `new_outlet` berantai Supervisor → Branch Manager; NOO dapat disubmit tanpa order                                             | P1        |
