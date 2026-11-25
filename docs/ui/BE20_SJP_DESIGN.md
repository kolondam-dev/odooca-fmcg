# BE-20 — Surat Jalan Penagihan (SJP): keputusan pemilik dan rancangan

Status: RANCANGAN (belum ada kode). Keputusan pemilik 2026-11-23 di bawah; sisanya usulan agen untuk dikoreksi.

## 1. Keputusan pemilik (D8)

1. **Pembuat SJP:** finance / AR admin. Daftar tagihan terbentuk otomatis dari AR terbuka; tombol **Generate SJP** dengan pilihan **tanggal jatuh tempo** (hari ini atau batas tanggal) lalu opsi **salesman / rute**.
2. **Pelaksana penagihan:** salesman, delivery, supervisor, branch manager.
3. **Hasil penagihan:** `paid`, `partially paid`, `unpaid`. Penerimaan **wajib diposting dulu**, lalu **divalidasi kasir dan accounting**.
4. **Setoran:** uang disetor ke **admin kasir**; rekap SJP dan **copy faktur / faktur asli bila tak tertagih** diserahkan ke **finance AR control**.

## 2. Usulan model (addon baru `id_ar_collection`, bergantung `id_base`, `account`; terhubung ke `id_mobile_api` lewat registry opsional seperti `id_approval`)

- `id.collection.sheet` (SJP): `name` (sequence per perusahaan), `company_id`, `collect_date`, `due_until` (tanggal jatuh tempo maks), `collector_id` (res.users), `route` (opsional, memakai `res.partner.delivery_route`), `state`, `line_ids`, `generated_by`.
  Status: `draft` → `issued` (dicetak/diserahkan) → `returned` (kolektor menyerahkan rekap) → `reconciled` (AR control menutup) | `cancelled`.
- `id.collection.sheet.line`: `move_id` (faktur), `partner_id`, `due_date`, `amount_due` (snapshot saat generate), `outcome` (`pending|paid|partial|unpaid`), `collected_amount`, `unpaid_reason`, `document_return` (`none|copy|original`), `receipt_id`.
  Satu faktur hanya boleh ada di satu SJP aktif (constraint), kecuali SJP sebelumnya `cancelled`/`reconciled` dengan sisa.
- `id.collection.receipt`: dibuat dari command mobile. Status: `posted` (diposting kolektor, wajib) → `cashier_validated` (uang diterima kasir) → `accounting_validated` (membuat dan merekonsiliasi `account.payment`) | `rejected` (dengan alasan). Tanpa jalan pintas: faktur tidak berkurang sebelum validasi accounting.
- Grup: `group_ar_admin` (generate/batalkan SJP), `group_collector` (mengirim penerimaan), `group_collection_cashier`, `group_collection_accounting`, `group_ar_control` (tutup SJP). Kewenangan terima uang terpisah dari posting (blueprint mobile).

## 3. Generate SJP

Wizard: pilih `due_until` (default hari bisnis WITA) dan filter salesman/rute. Sumber: faktur pelanggan terposting yang belum lunas dengan `invoice_date_due <= due_until`, perusahaan sesi, belum ada di SJP aktif. Pengelompokan per kolektor memakai penugasan outlet harian (`id.mobile.workday.outlet_ids`) dan `delivery_route`; faktur tanpa kolektor muncul sebagai "belum ditugaskan" agar AR admin memilih manual.

## 4. Fase dan PR kecil

| Fase | Isi | Bergantung |
|---|---|---|
| BE-20b | Addon, model SJP + line, wizard Generate, grup, view daftar/form, tes Odoo | — |
| BE-20c | Snapshot membaca SJP kolektor hari itu (`collection_sheet`), menggantikan `collect_today` bila ada SJP (fallback tetap) | 20b |
| BE-20d | Command `collection.receipt.submit` (posting) + idempotensi + idempotent konflik saldo | 20b, 20c |
| BE-20e | Validasi kasir → accounting, pembuatan `account.payment`, rekonsiliasi, penutupan SJP oleh AR control, command `collection.settlement.submit` | 20d |
| FE-8b | Kartu SJP di PWA, "Mulai penagihan", hasil paid/partial/unpaid, flag `collection_v2` | 20c–20d |

Flag `collection_v2` tetap OFF di LIVE sampai 20e lulus review.

## 5. Keputusan pemilik D9 (jawaban atas pertanyaan terbuka, 2026-11-23)

1. **Banyak SJP:** SJP boleh digenerate banyak (per kolektor/rute/tanggal) untuk fleksibilitas (salesman absen, penagihan di depan / advance collection). Satu faktur hanya pada satu SJP aktif (draf/diterbitkan); setelah SJP dibatalkan atau dikembalikan faktur kembali ke daftar kandidat. Model: SJP 1..n baris, satu faktur dapat punya banyak baris dari waktu ke waktu.
2. **Unpaid:** faktur tak tertagih otomatis kembali menjadi kandidat (daftar terbuka secara default).
3. **Kasir dan accounting:** dua langkah berurutan; role gabungan diperbolehkan (satu user memegang keduanya berurutan), idealnya beda role dan beda orang.
4. **Cetak PDF SJP:** wajib sejak BE-20b (QWeb `id_ar_collection.report_collection_sheet`).

Status: BE-20b diimplementasikan (addon `id_ar_collection`: model SJP + baris, wizard Generate, grup `group_ar_admin`/`group_ar_control`, tampilan, PDF, tes Odoo). Grup kasir/accounting dan transisi `returned`/`reconciled` menyusul di BE-20e. Catatan: perlindungan faktur dengan penerimaan yang menunggu validasi (agar tidak ditagih ganda) dikerjakan bersama penerimaan di BE-20d/e.

## 6. Invarian server BE-20b (setelah review PR #194)

- **Satu faktur, satu SJP aktif:** kolom tersimpan `active_claim` pada baris (true bila SJP draf/diterbitkan) dengan indeks unik parsial `id_collection_sheet_line_one_active_claim (move_id) WHERE active_claim`. Guard atomik DB; berlaku untuk create, reaktivasi `action_draft`, dan dua sesi paralel. Pesan bisnis dari pre-check ORM; indeks menjadi pagar terakhir.
- **Mesin status di server:** `state` tidak dapat ditulis lewat `create`/`write`; hanya `_apply_state` (privat, tidak terjangkau RPC; bukan flag context) yang memvalidasi tabel transisi. Aksi publik BE-20b: terbit, batal, kembali ke draf. `returned`/`reconciled` hanya lewat seam privat sampai BE-20e.
- **Immutability:** setelah diterbitkan, perusahaan/tanggal/jatuh tempo/kolektor/rute/baris tidak berubah (hanya `note`); baris tidak dapat di-write langsung, ditambah atau dihapus kecuali pada SJP draf; `amount_due` adalah snapshot milik server; kolom hasil penagihan hanya lewat seam `_apply_outcome`. Saat terbit: kolektor internal, aktif, anggota perusahaan; faktur masih terposting, terbuka, perusahaan sama.
- **Mata uang:** SJP hanya mendukung faktur bermata uang perusahaan. Wizard mengecualikan faktur mata uang asing (jumlahnya ditampilkan) dan baris untuk faktur asing ditolak, sehingga total tidak pernah menjumlah lintas mata uang. Dukungan multi-mata-uang (per mata uang atau konversi bertanggal) adalah keputusan terpisah.

## 7. BE-20c: snapshot SJP untuk kolektor

`GET /sync/snapshot` memuat `collection_sheets {sheets[], truncated}` (addon `id_ar_collection` memperluas `id.mobile.workday._snapshot_payload`). Ruang lingkup dikunci server tanpa selector HTTP: kolektor = pengguna sesi, perusahaan = perusahaan penugasan, `collect_date` = hari bisnis WITA, status `issued`. Draf, dikembalikan, ditutup, dibatalkan, SJP kolektor lain, hari lain, dan perusahaan lain tidak ikut. Baris: referensi faktur, pelanggan (commercial partner), `outlet_id` PJP hari itu (null di luar PJP), jatuh tempo, `overdue`, `amount_due` (snapshot SJP) dan `balance` (sisa sekarang), hasil, dokumen. Volatil: di luar digest versi dan tidak masuk command/evidence (`include_volatile=False`). Batas 10 SJP dan 300 baris per SJP ditandai `truncated`; `line_count` dan `amount_total` tetap angka dokumen. PWA (FE-8b) belum membacanya; kontrak zod opsional dan `openapi.json` diekspor.


## 8. BE-20d: penerimaan penagihan (rancangan, belum diimplementasikan)

Tujuan: kolektor mengirim hasil penagihan satu SJP lewat command offline-aman. Server mencatat penerimaan berstatus `posted` dan menandai baris SJP. **Tidak ada pembayaran, rekonsiliasi, atau perubahan saldo faktur** (itu BE-20e); `collection_v2` tetap OFF.

### 8.1 Kontrak command `collection.receipt.submit`

```json
{ "client_uuid": "<uuid v4>", "type": "collection.receipt.submit",
  "payload": { "sheet_id": 12, "occurred_at": "2026-11-25T10:15:00+08:00",
    "lines": [ { "line_id": 301, "invoice_id": 8841, "outcome": "paid|partial|unpaid",
                 "amount": 1250000, "expected_balance": 1250000,
                 "unpaid_reason": "closed|no_cash|dispute|absent|other", "note": "" } ] } }
```
- Dikunci server: kolektor = pengguna sesi, perusahaan = perusahaan sesi. `outlet_id` (bila dikirim) hanya petunjuk tampilan dan **tidak pernah** dipakai sebagai kunci atau otorisasi.
- **Identitas penerimaan** = SJP + baris + faktur + kolektor + perusahaan. Server memuat baris dari DB lalu menegaskan: `line.sheet_id = sheet_id`, `line.move_id = invoice_id`, `sheet.collector_id = user`, `sheet.company_id = company`, `sheet.state = issued`. Ketidakcocokan apa pun = `UserError` (tidak dicatat, bukan retry-able).
- `amount` adalah angka perusahaan (IDR, dibulatkan sesuai mata uang). `paid`: `amount == saldo faktur sekarang`; `partial`: `0 < amount < saldo`; `unpaid`: `amount == 0` dan `unpaid_reason` wajib. `document_return` diturunkan server (`paid`/`partial` → `copy`, `unpaid` → `original`), nilai klien diabaikan. Metode terima: tunai saja pada 20d (lihat pertanyaan Q2).
- Seluruh baris dalam satu command diproses **semua-atau-tidak-sama-sekali** (savepoint dispatcher yang ada). Satu baris yang gagal membatalkan seluruh command.
- Hari: kolektor boleh mengirim untuk SJP `issued` miliknya walau `collect_date` sudah lewat (sinkronisasi offline); command tidak memakai `_assert_day`. Lihat Q1 untuk batas hari.

### 8.2 Idempotensi dan retry/offline

- Lapisan 1 (sudah ada): `UNIQUE(user_id, client_uuid)` pada `id.mobile.command` + sidik jari kanonik. Retry dengan UUID dan payload sama mengembalikan hasil lama tanpa efek samping; UUID sama dengan payload berbeda = `MobileReadConflict`.
- Lapisan 2 (baru, penentu): indeks unik parsial `(sheet_line_id) WHERE state NOT IN ('rejected','cancelled')` pada `id.collection.receipt.line`. Menjamin **satu penerimaan aktif per baris SJP** meskipun dua UUID berbeda (perangkat ganda, antrean ganda, retry dengan UUID baru). Pre-check ORM memberi pesan bisnis; indeks menjadi pagar terakhir; `IntegrityError 23505` dipetakan menjadi hasil bisnis, bukan 500.
- Hasil bisnis yang **dicatat** di log command (status `rejected`, pesan Indonesia, tidak mengulang efek) agar antrean offline tidak berputar: baris sudah punya penerimaan aktif (`Sudah ada penerimaan <RCP> untuk baris ini`), saldo berubah, SJP tidak lagi `issued`. Kesalahan malformed/otorisasi tetap `UserError`/`AccessError` (tidak dicatat).

### 8.3 Proteksi saldo dan penagihan ganda

- Penguncian: `SELECT ... FOR UPDATE` pada baris SJP (urut `id`) dan faktur terkait sebelum membaca saldo; saldo dibaca ulang di dalam kunci (`amount_residual`, mata uang perusahaan).
- `expected_balance` dari klien dibandingkan dengan saldo terkunci. Berbeda (mis. pelunasan lewat jalur lain, kredit note) = `rejected` "saldo berubah, sinkronkan ulang"; tidak menebak jumlah.
- `amount` tidak boleh melebihi saldo terkunci **dikurangi penerimaan menunggu validasi atas faktur yang sama**. Karena satu faktur hanya satu SJP aktif (indeks 20b) dan satu penerimaan aktif per baris, penerimaan menunggu pada faktur itu paling banyak satu; penjumlahan tetap dihitung sebagai pagar tambahan.
- Sisa dari `partial`: baris tetap `partial`; sisanya kembali menjadi kandidat SJP berikutnya setelah SJP ini ditutup (BE-20e), bukan ditagih ulang pada SJP yang sama (Q3).
- Penerimaan `posted` belum mengurangi `amount_residual`. Snapshot (FE-8b) harus menampilkan "menunggu validasi" dan tidak menghitung faktur itu lagi sebagai "wajib ditagih": 20d menambahkan `receipt_state` dan `receipt_amount` pada baris snapshot SJP.

### 8.4 Model (di `id_ar_collection`)

- `id.collection.receipt`: `name` (`RCP/<tahun>/`), `sheet_id`, `collector_id`, `company_id`, `command_uuid` (unik per kolektor), `occurred_at`, `submitted_at`, `state` (`posted` pada 20d; `cashier_validated`/`accounting_validated`/`rejected`/`cancelled` disiapkan untuk 20e), `amount_total` (stored compute), `line_ids`.
- `id.collection.receipt.line`: `receipt_id`, `sheet_line_id`, `move_id`, `outcome`, `amount`, `balance_at_submit`, `unpaid_reason`, `document_return`, `state` (related/stored dari header untuk indeks parsial), `currency_id`.
- Akses: model tanpa create/write/unlink untuk pengguna biasa; pembuatan hanya lewat seam privat yang dipanggil handler setelah semua pemeriksaan di atas. Kolektor membaca miliknya (rule); `group_ar_admin`/`group_ar_control` membaca perusahaan sendiri. Baris SJP diperbarui lewat seam `_apply_outcome` yang sudah ada (mengisi `outcome`, `collected_amount`, `document_return`, `receipt_id`).
- SJP tetap `issued` sampai BE-20e (`returned`).

### 8.5 Perubahan di `id_mobile_api` (kecil dan generik)

`process_command` memeriksa `SUPPORTED_COMMANDS` dan memakai rantai if/elif. Diubah menjadi titik perluasan: `_supported_commands()` dan `_handle_extension(cmd_type, payload, client_uuid)` (default mengembalikan `None`; addon memperluas). Dispatcher, idempotensi, savepoint dan pemetaan `IntegrityError` tetap satu-satunya. `id_ar_collection` mendaftarkan `collection.receipt.submit`; tanpa addon, tipe itu tetap "Unsupported command type".

### 8.6 Rencana tes (Odoo, dibuktikan lewat CI exact SHA)

1. Kasus sukses paid/partial/unpaid; penerimaan, baris SJP, `document_return` diturunkan server.
2. Retry UUID sama (hasil sama, satu penerimaan); UUID sama payload beda = konflik.
3. UUID berbeda untuk baris yang sama = `rejected`, tetap satu penerimaan aktif; indeks unik dibuktikan dengan SQL langsung.
4. Dua sesi paralel (thread SQL seperti tes 20b) untuk baris yang sama: tepat satu menang.
5. Identitas: `line` dari SJP lain/kolektor lain/perusahaan lain, `invoice_id` tidak cocok, `outlet_id` palsu diabaikan.
6. Saldo berubah (`expected_balance` basi, faktur dilunasi lewat jalur lain) = `rejected`, tanpa efek.
7. Rollback atomik: satu baris invalid dalam command multi-baris membatalkan semuanya (tanpa receipt/baris/jejak outcome).
8. SJP `draft/returned/cancelled` ditolak; SJP lewat hari tetap diterima selama `issued`.
9. Jumlah: `paid` ≠ saldo, `partial` ≥ saldo, `unpaid` > 0, negatif/NaN/presisi mata uang ditolak.
10. Tidak ada `account.payment` dan `amount_residual` tidak berubah; `collection_v2`/flag tidak disentuh; tanpa addon, command ditolak sebagai tidak didukung.

### 8.7 Pertanyaan terbuka untuk pemilik (default dipakai bila tidak dijawab)

- **Q1 Batas hari:** default tidak ada batas selama SJP `issued`; alternatif batas mundur N hari. 
- **Q2 Metode terima:** default tunai saja; transfer/QRIS butuh bukti dan alur kasir berbeda (menyusul).
- **Q3 Sisa partial:** default kembali sebagai kandidat setelah SJP ditutup; alternatif memperbolehkan penerimaan kedua pada baris yang sama (butuh perubahan indeks unik).
