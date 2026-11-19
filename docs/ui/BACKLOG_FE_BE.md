# Backlog Frontend (PWA) dan Backend — inventarisasi ulang

Disusun 2026-11-19 setelah fase 3B-19 (main `9502838`). Sumber: `pwa/contracts/openapi.json`, `addons/id_mobile_api`, `addons/id_base`, `addons/id_approval`, `pwa/src`, `docs/ui/DS_RECONCILIATION.md` (K1–K33). Setiap klaim backend bertanda berkas; yang tidak sempat dibuktikan ditulis **[perlu verifikasi]**.

Ringkasan satu paragraf: UI PWA hampir habis dikerjakan di sisi tampilan, tetapi **backend baru melayani 6 dari 15 tipe command dan snapshot-nya belum membawa data yang sudah diasumsikan layar (jam/jarak outlet, piutang, extra call, riwayat order, promo, delivery, flag fitur)**. Akibatnya sebagian layar yang sudah jadi (kartu outlet berjam/jarak, peringatan limit kredit, Extra call, Display & stok, Delivery) belum menampilkan data nyata di LIVE. Urutan kerja yang disarankan ada di bagian 4.

---

## 1. Backlog frontend (PWA)

Prioritas: **P0** blok bisnis, **P1** nilai tinggi dan bisa jalan sekarang, **P2** perapian.

| ID | Pekerjaan | Prioritas | Butuh backend? |
|---|---|---|---|
| FE-1 | Komponen `UnitQty` (badge satuan karton/pack/pcs) | P1 | Tidak |
| FE-2 | Komponen serupa: `Money`, `SyncStatusChip`, `SkuLine`, `StockBadge`, `Timestamp`, `MetaItem`, `DiscountBadge` | P1–P2 | Tidak |
| FE-3 | Modul Extra call: lengkapi (status, penandaan, tanpa direktori) | P1 | Ya (BE-3) |
| FE-4 | Modul NOO (registrasi outlet baru) | P1 | Ya (BE-4) |
| FE-5 | Saran order di POS | P1 | Sebagian (BE-6) |
| FE-6 | Penyederhanaan layar Absen/Check-in | P1 | Tidak |
| FE-7 | Layar Outlet_kosong aktif | P0 | Ya (BE-5) |
| FE-8 | Sisa Kunjungan_hub (faktur, tagihan, "Mulai penagihan") | P1 | Ya (BE-7) |
| FE-9 | Tata letak lama di layar persetujuan/koreksi (K32) | P2 | Tidak |
| FE-10 | Peninjauan tablet dan aksesibilitas | P2 | Tidak |

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

| Komponen | Fungsi | Usulan tampilan | Pengganti |
|---|---|---|---|
| `Money` | Rupiah konsisten (Rp, titik ribuan, negatif merah, `—` untuk kosong), opsi `compact` (1,2 jt) | Teks tabular, tanda minus eksplisit, tanpa desimal; `emphasis` untuk total | 6 formatter `Intl` + `money()` |
| `SyncStatusChip` | Satu pemetaan status → nada + label ("Tersimpan di perangkat", "Terkirim", "Menunggu approval", "Ditolak", "Gagal") | `Chip` bernada + ikon kecil; label tetap penanda | Pemetaan status di 12 berkas |
| `SkuLine` | Baris SKU seragam: nama, kode, `UnitQty`, harga, badge diskon | Dua baris: nama + jumlah (kiri), jumlah rupiah (kanan); kode SKU sub | `pos-line`, baris Ringkasan/Koreksi/Delivery |
| `StockBadge` | Ketersediaan: Tersedia / Menipis / Habis | `Chip` ok/warn/bad; ambang menipis dari backend (par) | Teks "Habis" di POS |
| `Timestamp` | Waktu kejadian `HH.mm.ss` + tanggal relatif ("Hari ini", "Kemarin") | Teks kecil mute; tanda "WITA" hanya bila perlu | `when()` di Riwayat/Antrean, "Tersimpan di perangkat" |
| `MetaItem` | Pasangan ikon + teks pendek (jam, jarak, piutang, telepon) | Baris meta kartu DS (`ui-ocard__m`) | Meta di kartu outlet, Beranda |
| `DiscountBadge` | Diskon baris/program: `−5%`, `−Rp 2.000`, nama program | Chip kecil nada info; program ditampilkan di bottom sheet | Teks diskon di POS/Ringkasan |
| `EmptyState` | Keadaan kosong DS (ikon, judul, teks, aksi) | Sudah ada sebagai `.ui-empty` di Outlet_kosong; jadikan komponen | Teks "Tidak ada …" polos |
| `Stepper`/`DayStep` | Langkah bernomor (hari kerja, hub kunjungan) | Sudah ada `DayStep`; angkat ke `ui/` | `DayStep` lokal |

### FE-3. Modul Extra call

**Sudah ada:** `ExtraCallScreen` (cari di `snapshot.extra_call_outlets`, alasan, catatan) mengirim `sales.extra_call.request`.

**Kekurangan:**
1. Backend belum ada (BE-3) dan snapshot belum membawa `extra_call_outlets`; tanpa direktori, layar jatuh ke ketik nama bebas — tidak boleh di LIVE (mendorong data sampah). Usulan: tanpa direktori, tombol dinonaktifkan dan tawarkan **NOO**.
2. Tidak ada umpan balik status (Menunggu / Disetujui / Ditolak). Usulan: baris di Antrean/Riwayat dengan `SyncStatusChip` dan, bila disetujui, outlet muncul di daftar Outlet bertanda **Extra** (chip), terpisah dari PJP (sesuai teks layar "tercatat terpisah di laporan harian").
3. Kebijakan persetujuan belum diputuskan: otomatis (outlet dalam master salesman) vs perlu approval supervisor (di luar wilayah). **Perlu keputusan pemilik.**
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
- **Keputusan pemilik:** apakah boleh kunjungan/order sebelum disetujui (usulan: boleh kunjungan survei + foto, order hanya setelah disetujui); siapa menyetujui; apakah NOO otomatis masuk PJP besok.
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

**Pembagian kerja:** *fakta di server, aturan di klien.* Alasannya: stok toko hanya ada di klien saat offline, sehingga hitungan akhir harus di klien; server cukup mengirim fakta ringkas per outlet (kecil: ≤ 7 SKU × ±40 outlet) dalam snapshot. Saat ini backend **tidak mengirim `order_history` sama sekali** dan hanya `top_sku`/`max_order` (`mobile_workday.py:135-166`) → BE-6.

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

| Method | Path | Status | Catatan |
|---|---|---|---|
| GET | `/api/v1/me/bootstrap` | ADA (PARSIAL) | Peran ditentukan dengan menebak `"driver"` di login/jabatan (`mobile_workday.py:116-120`); tidak mengirim `features`. |
| GET | `/api/v1/sync/snapshot` | ADA (PARSIAL) | Lihat 2.3. |
| GET | `/api/v1/outlets/{id}/image` | ADA | Dibatasi outlet pada assignment hari ini. |
| POST | `/api/v1/evidence` | ADA | `evidence_api.py`; ada tes. |
| GET | `/api/v1/evidence/{client_uuid}/{variant}` | ADA | idem. |
| POST | `/api/v1/sync/commands` | ADA (PARSIAL) | Hanya 6 dari 15 tipe command (2.2). |

Tidak ada endpoint lain. Tidak ada pencarian outlet, pagination, atau endpoint status command (PWA harus menebak status dari antrean/sinkron).

### 2.2 Tipe command (`mobile_command.py:17-24` `SUPPORTED_COMMANDS`; kontrak `openapi.json` memuat 15)

| Command | Status | Catatan |
|---|---|---|
| `sales.order.submit` | ADA | Lihat temuan BE-8 (diskon, versi snapshot). |
| `sales.visit.check_in` / `check_out` | ADA | Validasi scope outlet, hari Minggu, tanggal GPS; radius sisi server **[perlu verifikasi]**. |
| `delivery.pod.submit`, `delivery.proof.submit`, `delivery.trip.close` | ADA (PARSIAL) | Handler ada, tetapi snapshot tidak melayani tugas pengiriman (BE-2). |
| `sales.extra_call.request` | **KOSONG** | Tidak ada di backend. |
| `hris.attendance.capture` | **KOSONG** | Absen hanya lokal di PWA. |
| `hris.leave.request` | **KOSONG** | |
| `field_expense.request`, `field_expense.realization.submit` | **KOSONG** | |
| `sales.order.revise` | **KOSONG** | |
| `collection.receipt.submit`, `collection.settlement.submit` | **KOSONG** | Termasuk modul penagihan. |
| `delivery.cash_deposit.submit` | **KOSONG** | |
| `outlet.register.request` (NOO) | **KOSONG** | Belum ada di kontrak PWA juga. |

Command tidak didukung dijawab `UserError("Unsupported command type")` (`mobile_command.py:120-121`); PWA harus memastikan tidak mengantrekan tipe tersebut di LIVE selain lewat flag.

### 2.3 Snapshot (`_snapshot_payload`, `mobile_workday.py:168-255`) vs yang dibutuhkan PWA

| Bidang yang diharapkan PWA | Backend | Dampak |
|---|---|---|
| `outlets[].time`, `distance` | selalu `""` | Kartu outlet tanpa jam/jarak; tidak ada urutan kunjungan (outlet diurutkan `id`, bukan urutan PJP). |
| `outlets[].commercial.ar_outstanding` | tidak dikirim | Peringatan limit kredit dan piutang tidak tampil. |
| `commercial.credit_mode`, jumlah faktur jatuh tempo | tidak dikirim | Mode `strict`/`limit_due` backend (`id_base/models/sale_order.py:136-166`) tak terwakili. |
| `deliveries` | **hard-coded `[]`** | Peran Delivery tidak mendapat tugas. `DeliveryTask`/`CollectionTask` ada di OpenAPI tetapi tidak ada sumbernya. |
| `extra_call_outlets` | tidak dikirim | Layar Extra call tanpa direktori. |
| `order_history` | tidak dikirim | Display & stok tanpa riwayat SKU; tidak ada dasar saran order. |
| `discount_programs` | tidak dikirim | `order_pricing_v2` tidak mungkin; `id_promo_governance` belum dipetakan. |
| `features` (5 flag) | tidak dikirim | Semua flag v2 mati di LIVE; backend tidak punya tombol untuk menyalakan. |
| Harga/stok per satuan | hanya basis karton | Cukup untuk kontrak v2, tetapi stok live ikut dalam hash versi (BE-1). |

### 2.4 Temuan yang harus diperbaiki

| ID | Temuan | Keparahan | Bukti |
|---|---|---|---|
| BE-1 | **Versi snapshot memuat stok hidup.** `sales.order.submit` menghitung ulang snapshot dan menolak bila versi beda (`mobile_command.py:~198-202`); versi = hash seluruh payload termasuk `stock`. Setiap pergerakan stok membuat order offline ditolak "Stale catalog snapshot version" (409), dan setiap order memicu perhitungan snapshot penuh. | Tinggi | `mobile_workday.py` (digest), `mobile_command.py` |
| BE-2 | `deliveries: []` dan jam/jarak kosong (lihat 2.3). Peran Delivery tidak berfungsi end-to-end di LIVE. | Tinggi | `mobile_workday.py` |
| BE-3 | Extra call tidak ada (command, model, persetujuan, direktori). | Tinggi | grep `extra_call` kosong |
| BE-4 | NOO tidak ada (command, model outlet baru berstatus draf, persetujuan, aturan duplikat). | Tinggi | — |
| BE-5 | **PJP kosong ditolak di backend juga:** `_current_assignment` melempar "Assign at least one product and scheduled outlet" (`mobile_workday.py:~96-98`) dan snapshot memberi 422 `configuration_unavailable`. Selain itu, bila tidak ada assignment hari ini, backend **menyalin otomatis** dari hari kerja terakhir (`mobile_workday.py:~71-92`) — artinya "PJP kosong" tidak pernah terjadi dan salesman bisa mengunjungi outlet kemarin tanpa jadwal. | Tinggi (keputusan) | `mobile_workday.py` |
| BE-6 | Tidak ada fakta untuk saran order (riwayat order per outlet–SKU, interval, wajib listing, promo). | Sedang | — |
| BE-7 | Piutang: tidak ada `ar_outstanding`, daftar faktur, jadwal penagihan. Data dasar sudah ada di Odoo (`res.partner.credit`, `account.move` faktur terbuka dan `invoice_date_due`), sehingga **pembacaan** `ar` dapat dibuat sekarang dari akuntansi bawaan; yang benar-benar baru adalah **jadwal penagihan/kolektor**. | Sedang | `id_base/models/sale_order.py` |
| BE-8 | **Diskon baris tanpa pengajuan:** `discount` per baris dari klien diterima apa adanya dan hanya order dengan `discount_request.percent > 0` ditandai `needs_approval`; `action_confirm` hanya memblokir harga di bawah HPP, bukan diskon taktikal (`id_approval/models/sale_order.py:172-190`). Baris dengan `discount: 0` ikut tertimpa diskon order (`float(...) or discount_pct`). **[perlu verifikasi dengan tes]** — jika benar, salesman dapat memberi diskon tanpa persetujuan. | Tinggi | `mobile_command.py:~277-283` |
| BE-9 | Peran dari `"driver" in login` (`mobile_workday.py:116-120`) — rapuh dan bisa disalahgunakan; gunakan grup. | Sedang | idem |
| BE-10 | Satu SKU atau outlet bermasalah menggagalkan **seluruh** snapshot (422) sehingga satu data master buruk memblokir semua salesman; perlu isolasi (lewati + laporkan). | Sedang | `mobile_workday.py` (`raise UserError`) |
| BE-11 | `openapi.json` `CatalogRow` (`product_id`, `price_per_carton`, …) berbeda dari payload `catalog_version: 2` yang dikirim (`id`, `sku_code`, `price`, `stock`). **[perlu verifikasi]** apakah gerbang `contracts:check` memakai skema yang benar; kontrak dan implementasi tidak boleh punya dua wujud. | Sedang | `openapi.json` vs `mobile_workday.py` |
| BE-12 | Tidak ada endpoint/ruang status command; PWA tidak bisa menampilkan hasil persetujuan (Extra call, NOO, diskon, kredit) selain lewat respons awal. | Sedang | — |
| BE-13 | Kebijakan tidak bisa dipakai klien: `credit_mode` (4 mode), faktur jatuh tempo, hari Minggu libur — klien hanya melihat penolakan setelah kirim. Kirim sebagai fakta snapshot. | Rendah | — |

### 2.5 Cakupan tes backend

`id_mobile_api/tests`: `test_commands_api` (15), `test_read_api` (19), `test_evidence_api` (8), `test_existing_demo` (10), `test_pjp_loader_boundaries` (9), `test_staging` (5). Terlihat ada tes versi stale dan tanggal usang; **tidak terlihat** tes untuk: stok berubah di antara snapshot dan submit (BE-1), diskon baris tanpa pengajuan (BE-8), PJP kosong/salin otomatis (BE-5), dan command tidak didukung. Jumlah di atas hitungan `def test` per berkas, bukan hasil eksekusi.

---

## 3. Keputusan yang dibutuhkan dari pemilik

1. **PJP kosong vs salin otomatis** (BE-5): apakah salin dari hari sebelumnya boleh, atau PJP kosong dibiarkan dan salesman hanya Extra call/NOO.
2. **Extra call:** persetujuan otomatis atau supervisor; batas per hari.
3. **NOO:** boleh kunjungan/order sebelum disetujui; penyetuju; masuk PJP otomatis.
4. **Saran order:** target (median 3 order vs par manual), kelipatan minimum, sumber SKU wajib listing.
5. **Kredit:** apakah PWA harus memblokir order untuk mode `strict` (faktur jatuh tempo) atau hanya memperingatkan.
6. **Diskon baris** (BE-8): apakah benar harus selalu lewat approval.
7. Jam rencana PJP ("08.30") tanpa detik — asumsi saat ini.

## 4. Urutan kerja yang disarankan

1. **Backend P0 (kontrak dan korektif):** BE-1 (versi snapshot tanpa stok), BE-9, BE-8 (setelah tes), BE-11, `features` pada bootstrap/snapshot, `outlets[].time/distance/urutan`, `deliveries`.
2. **Frontend paralel, tanpa backend:** FE-1 `UnitQty`, FE-2 (`Money`, `SyncStatusChip`, `Timestamp`, `EmptyState`), FE-6 absen.
3. **Backend P1:** BE-7 bagian baca (`ar`, faktur terbuka, `credit_mode`), BE-5 setelah keputusan 1, BE-6 (fakta saran), `order_history`.
4. **Frontend P1 setelah data siap:** FE-5 saran order, FE-7 Outlet_kosong, FE-8 sisa hub.
5. **Backend P1 command:** `sales.extra_call.request` (BE-3), `outlet.register.request` (BE-4), `hris.attendance.capture`, kemudian `hris.leave.request`, `field_expense.*`, `collection.*`, `delivery.cash_deposit.submit`, `sales.order.revise`.
6. **Frontend setelah command:** FE-3 lengkap, FE-4 NOO.
7. P2: FE-9, FE-10.
