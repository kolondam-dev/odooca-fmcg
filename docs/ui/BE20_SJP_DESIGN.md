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


## 8. BE-20d: penerimaan penagihan (rancangan revisi, belum diimplementasikan)

Tujuan: kolektor mengirim hasil penagihan satu SJP lewat command offline-aman. Server mencatat penerimaan berstatus `posted` dan menandai baris SJP. **Tidak ada pembayaran, rekonsiliasi, atau perubahan saldo faktur** (itu BE-20e); `collection_v2` tetap OFF. Keputusan pemilik D10 (2026-11-25) ada di 8.8; dua hal turunannya (Q5 dan Q6) masih menunggu jawaban.

### 8.1 Kontrak command `collection.receipt.submit`

```json
{ "client_uuid": "<uuid v4>", "type": "collection.receipt.submit",
  "payload": { "sheet_id": 12, "occurred_at": "2026-11-25T10:15:00+08:00",
    "lines": [ { "line_id": 301, "invoice_id": 8841, "outcome": "paid|partial|unpaid",
                 "amount": 1250000, "expected_balance": 1250000,
                 "method": "cash|transfer|giro",
                 "transfer": { "reference": "", "proof_evidence_uuid": "" },
                 "giro": { "number": "", "bank": "", "due_date": "2026-12-05" },
                 "unpaid_reason": "closed|no_cash|dispute|absent|other", "note": "" } ] } }
```
- Dikunci server: kolektor = pengguna sesi, perusahaan = perusahaan sesi. `outlet_id` (bila dikirim) hanya petunjuk tampilan, tidak pernah dipakai sebagai kunci atau otorisasi.
- **Identitas** = SJP + baris + faktur + kolektor + perusahaan, dimuat dari DB. `line_id` duplikat dalam payload, `invoice_id` tidak cocok dengan baris, atau baris bukan milik `sheet_id` = malformed (`UserError`, tidak dicatat).
- **Akses lintas pemilik** (SJP kolektor lain/perusahaan lain/tidak ada) = satu pesan generik "SJP tidak ditemukan" (`AccessError`), tidak dicatat dan tidak mengungkap dokumen.
- `amount` dalam mata uang perusahaan, dibulatkan sesuai mata uang. `paid`: `amount == saldo terkunci`; `partial`: `0 < amount < saldo`; `unpaid`: `amount == 0` dan `unpaid_reason` wajib. `document_return` diturunkan server (`paid`/`partial` -> `copy`, `unpaid` -> `original`).
- **Satu hari penyelesaian (D10-Q1):** command hanya diterima pada hari bisnis WITA yang sama dengan `collect_date` SJP. `occurred_at` wajib ber-zona waktu, jatuh pada `collect_date` WITA, tidak di masa depan (toleransi 5 menit); `submitted_at` diisi server. Tidak ada penanda `late` dan tidak ada sinkron lintas hari. Command yang tiba setelah hari itu = `rejected` persisten ("melewati hari penyelesaian"), lihat 8.3a.
- **Metode terima (D10-Q2):** `cash` | `transfer` | `giro`. `transfer`: wajib `reference` dan/atau bukti (`proof_evidence_uuid`, memakai evidence mobile yang ada); tujuan hanya rekening perusahaan, tidak pernah rekening karyawan; uang tidak dipegang kolektor. `giro`: wajib nomor, bank, tanggal jatuh tempo/cair. Pada 20d metode hanya **dicatat** dan menentukan jalur validasi di 20e; belum ada pembayaran. Kontrak memuat ketiganya sejak awal agar tidak terjadi perubahan kontrak di tengah.

### 8.2 Hasil command dan batas transaksi

Tiga kelas hasil, dibedakan tegas:
1. **Ditolak tanpa catatan** (`UserError`/`AccessError`): malformed, akses lintas pemilik/perusahaan, aktor tidak berwenang. Exception keluar dari savepoint dispatcher sehingga tidak ada efek dan tidak ada log command (perilaku sekarang).
2. **Business rejection yang terotorisasi dan persisten** (status `rejected`): SJP milik aktor tetapi tidak lagi `issued`, saldo berubah (`expected_balance` basi), baris atau faktur sudah punya penerimaan aktif/pending, tanggal tidak sah. Dicatat sebagai satu `id.mobile.command` berstatus `rejected` dengan pesan Indonesia; **tidak ada receipt dan tidak ada outcome tersisa**.
3. **Diterima** (`accepted`): receipt dan seluruh baris tertulis.

Mekanisme dua batas (perubahan generik di dispatcher `id_mobile_api`):
- Handler **tidak mengembalikan tuple `rejected` setelah menulis**. Untuk kelas 2 handler melempar `CommandRejected(message, reference)` (turunan `Exception`, bukan `UserError`) dari dalam savepoint, sehingga seluruh mutasi bisnis di-rollback oleh savepoint.
- Dispatcher menangkap `CommandRejected` **di luar savepoint** dan baru kemudian membuat baris `id.mobile.command` berstatus `rejected` dalam transaksi luar. Hasilnya: nol efek bisnis, tepat satu log.
- Retry dengan UUID dan payload identik membaca log dan mengembalikan hasil `rejected` yang sama tanpa mengeksekusi ulang. UUID sama dengan payload berbeda tetap `MobileReadConflict`.
- Pemetaan `IntegrityError 23505` **menurut `constraint_name`**: indeks UUID command (`UNIQUE(user_id, client_uuid)`) tetap menjadi "Command submission raced; retry the same UUID"; indeks penerimaan (8.3) diubah menjadi `CommandRejected`; constraint lain naik sebagai error. Dilarang menyamakan semua 23505.
- Tipe command lama yang mengembalikan tuple tetap tidak berubah; jalur `CommandRejected` hanya dipakai handler baru.

### 8.3a Penyelesaian satu hari dan penutupan SJP yang tidak selesai (D10-Q1)

Praktik FMCG: semua transaksi diselesaikan pada hari yang sama (kecuali kasbon dan kanvas yang punya penanganan khusus di luar SJP ini). Konsekuensinya:
- Kolektor wajib sinkron begitu sinyal kembali atau saat tiba di kantor, pada hari yang sama.
- **Penutupan akhir hari (job terjadwal, batas WITA, parameter jam, Q5):** untuk SJP `issued` dengan `collect_date` lewat: baris tanpa penerimaan ditandai `lapsed` (hasil baru, bukan `unpaid`, agar terbedakan dari tidak tertagih yang dilaporkan kolektor) dan melepas `active_claim`, sehingga faktur kembali menjadi kandidat tanpa lubang atau loop. SJP tanpa satu pun penerimaan menjadi `expired`; SJP dengan penerimaan lanjut ke validasi (20e) dan hanya baris `lapsed`-nya yang dilepas.
- **Penerimaan yang sudah tersinkron (pending) tidak dibatalkan** oleh penutupan ini: proteksi 8.3 tetap berlaku sampai tervalidasi/ditolak. Yang "dibatalkan accordingly" hanyalah baris yang tidak pernah dilaporkan.
- Command yang terlambat tiba setelah penutupan = `rejected` persisten dengan pesan jelas; HP boleh membuang antrean itu (tidak loop).
- **Uang nyata yang sudah diterima tetapi tidak sempat tersinkron** tidak boleh masuk lewat command offline. Jalurnya pengecualian manual oleh `group_ar_control` (BE-20e), tercatat dengan alasan dan pelaku. Detail menunggu Q5.

### 8.3 Proteksi penerimaan pending lintas SJP (kebijakan eksplisit)

Kebijakan: **satu penerimaan pending per faktur (per perusahaan, lintas semua SJP)**; penerimaan partial berganda atas faktur yang sama tidak diizinkan dan tidak ada reservasi saldo kumulatif. "Pending" = receipt `posted` atau `cashier_validated`. Dilepas hanya oleh `accounting_validated` (saldo sudah turun lewat pembayaran native) atau `rejected` (BE-20e), tidak oleh perubahan status SJP.

- **Indeks DB:** `id.collection.receipt.line`: unik parsial `(sheet_line_id) WHERE state IN pending` dan unik parsial `(move_id) WHERE state IN pending` (`move_id` sudah memuat perusahaan). Pre-check ORM memberi pesan bisnis; indeks menjadi pagar terakhir.
- **Lifecycle guard pada SJP:** `cancel`, `draft`, dan regenerate ditolak bila ada receipt pending pada SJP itu (uang sudah diterima harus lewat validasi, bukan hilang). Transisi `returned` (BE-20e) diperbolehkan tetapi **tidak melepas proteksi**; proteksi hanya mengikuti status receipt.
- **Generate dan baris SJP:** kandidat wizard, `_validate_invoice` (draf baru, reaktivasi), dan snapshot mengecualikan/menandai faktur dengan receipt pending di SJP mana pun. Snapshot menambah `receipt_state`/`receipt_amount`; FE-8b tidak menghitung faktur itu sebagai "wajib ditagih".
- **Handler:** menolak (`CommandRejected`) faktur yang sudah punya receipt pending walau baris SJP-nya berbeda dan UUID baru.
- **Skenario wajib:** partial pada SJP A; A tidak dapat dibatalkan/dikembalikan-ke-draf; bila A `returned`, faktur tetap tidak bisa masuk SJP B; command UUID baru untuk faktur itu pada SJP lain = `rejected`; setelah receipt `rejected`/`accounting_validated` proteksi lepas dan sisa saldo (bila ada) menjadi kandidat. BE-20e wajib menghormati proteksi yang sama (satu-satunya jalan melepasnya).

### 8.4 Protokol lock dan baca ulang saldo

Urutan lock global deterministik, dipakai semua handler terkait (command 20d, validasi 20e, penutupan SJP):
1. Baris SJP (`id.collection.sheet`) `FOR UPDATE` (lifecycle).
2. Faktur (`account.move`) `FOR NO KEY UPDATE` urut `id` naik, lalu baris receivable terkait (`account.move.line`, akun receivable, belum direkonsiliasi penuh) `FOR UPDATE` urut `id` naik.
3. Baris SJP (`id.collection.sheet.line`) urut `id` naik, lalu pengecekan/penulisan klaim pending (indeks 8.3).

Setelah semua lock didapat: `flush_all()`, `invalidate_all()` (atau invalidate pada move/line terkait), lalu baca ulang `amount_residual` dan pending dari DB di dalam bagian terkunci yang sama; penghitungan saldo dan penulisan receipt satu bagian atomik. Faktur dalam satu command selalu dikunci urut `id`, bukan urut payload, agar multi-faktur tidak deadlock.

**Audit prasyarat (belum dilakukan, tidak ada sumber Odoo di sandbox):** hipotesis bahwa rekonsiliasi native menulis `amount_residual` pada baris receivable dan sisipan `account.partial.reconcile`, sehingga lock baris receivable (langkah 2) berkontensi dengan jalur rekonsiliasi. Ini **tidak diasumsikan**: PR implementasi wajib mengaudit jalur pembayaran/rekonsiliasi Odoo yang dipin (register payment, `reconcile`, write-off, credit note) dan menyesuaikan urutan bila hasil audit berbeda; bukti akhirnya tes dua transaksi (8.6).

### 8.5 Model dan akses (di `id_ar_collection`)

- `id.collection.receipt`: `name` (`RCP/<tahun>/`), `sheet_id`, `collector_id`, `company_id`, `command_uuid`, `occurred_at`, `submitted_at`, `method`, `state` (`posted` di 20d; `cashier_validated`/`accounting_validated`/`rejected` untuk 20e), `amount_total`, `line_ids`.
- `id.collection.receipt.line`: `receipt_id`, `sheet_line_id`, `move_id`, `outcome`, `amount`, `balance_at_submit`, `unpaid_reason`, `document_return`, `transfer_reference`, `proof_evidence_id`, `giro_number`, `giro_bank`, `giro_due_date`, `state` (stored dari header, dasar indeks), `currency_id`.
- Tanpa create/write/unlink untuk pengguna biasa; pembuatan hanya lewat seam privat yang dipanggil handler. Kolektor membaca miliknya; `group_ar_admin`/`group_ar_control` membaca perusahaan sendiri. Baris SJP diperbarui lewat seam `_apply_outcome`. SJP tetap `issued` sampai BE-20e.

### 8.6 Perubahan di `id_mobile_api` dan rencana tes

Perubahan `id_mobile_api` (kecil dan generik): titik perluasan `_supported_commands()` dan `_handle_extension(...)`, kelas `CommandRejected` dengan pencatatan di luar savepoint, dan pemetaan 23505 menurut nama constraint. Planner harus memicu suite Odoo untuk perubahan `id_mobile_api` (bukan hanya addon) dan regresi dispatcher yang ada.

Tes (Odoo, melalui `process_command` produksi, dibuktikan lewat CI exact SHA):
1. Sukses paid/partial/unpaid; `document_return` diturunkan server.
2. Retry UUID sama = hasil sama, satu receipt; UUID sama payload beda = konflik.
3. **Rollback + rejected persisten:** command multi-baris, baris pertama valid sudah ditulis, baris kedua memicu business rejection -> nol receipt/outcome, tepat satu command `rejected`, retry identik mengembalikan hasil sama tanpa efek.
4. Pemetaan 23505 menurut constraint: pelanggaran UUID command bukan penolakan receipt; pelanggaran indeks receipt = `rejected`.
5. Identitas: baris dari SJP/kolektor/perusahaan lain (generik, tidak dicatat), `invoice_id` tak cocok, `outlet_id` palsu diabaikan, **`line_id` duplikat dalam payload** ditolak.
6. UUID berbeda untuk baris/faktur yang sama = `rejected`, satu receipt pending.
7. **Pending lintas SJP:** partial di A; A tidak dapat dibatalkan/draf; A `returned`; faktur tidak masuk SJP B (wizard dan `_validate_invoice`); command UUID baru di B = `rejected`; tidak ada penagihan ganda; proteksi lepas hanya setelah receipt `rejected`/`accounting_validated`.
8. **Dua transaksi nyata (dua cursor, tanpa mock):** (a) command vs command pada faktur yang sama: tepat satu menang; (b) command vs pembayaran/rekonsiliasi native (register payment) pada faktur yang sama, dua urutan: `expected_balance` basi ditolak, tidak ada over-collect, saldo dibaca ulang setelah menunggu lock; (c) multi-faktur dengan urutan payload berlawanan antar transaksi: tidak deadlock.
9. Lifecycle/waktu: SJP `draft/returned/cancelled/expired` = `rejected`; `occurred_at` tanpa zona, masa depan, atau di luar `collect_date` WITA ditolak; command setelah hari penyelesaian = `rejected` persisten (tanpa penanda `late`). Penutupan akhir hari: baris tanpa penerimaan menjadi `lapsed` dan melepas klaim, SJP tanpa penerimaan menjadi `expired`, receipt pending tetap terproteksi, job idempoten. Metode: `transfer` tanpa referensi/bukti dan `giro` tanpa nomor/bank/jatuh tempo ditolak.
10. Jumlah: `paid` != saldo, `partial` >= saldo, `unpaid` > 0, negatif/NaN/presisi ditolak. Tidak ada `account.payment`, `amount_residual` tidak berubah, flag tidak disentuh, tanpa addon command ditolak sebagai tidak didukung.

### 8.7 Urutan implementasi setelah jawaban pemilik

1. PR dispatcher generik di `id_mobile_api` (titik perluasan, `CommandRejected`, 23505 menurut constraint) dengan tes regresi.
2. PR model receipt, indeks, lifecycle guard, kandidat/snapshot, handler, dan tes 1-10.

### 8.8 Keputusan pemilik D10 (2026-11-25)

- **Q1 Satu hari penyelesaian:** FMCG menganut one-day settlement untuk semua transaksi kecuali kasbon dan kanvas (penanganan khusus). Sinkron wajib tuntas saat sinyal kembali atau saat tiba di kantor; yang tidak tuntas dibatalkan "accordingly" tanpa loop/lubang pada rantai transaksi. Tidak ada sinkron lintas hari. Rancangan: 8.1 dan 8.3a.
- **Q2 Metode terima:** tunai, transfer (hanya ke rekening perusahaan, bukan rekening karyawan; kolektor/sales/delivery wajib verifikasi manual via telepon/WA ke admin finance atas mutasi berdasarkan bukti transfer toko), dan giro. Rancangan: kontrak memuat tiga metode (8.1); validasi berbeda per metode di 20e (8.9).
- **Q3 Sisa partial:** disetujui satu hasil per baris; kasus bayar dua kali dalam sehari jarang. Sisa menjadi kandidat setelah receipt selesai dan penutupan sah.
- **Q4 Pending:** disetujui satu pending per faktur lintas SJP (8.3).

**Masih terbuka (rekomendasi, menunggu pemilik):**
- **Q5 Batas penutupan dan uang yang terlewat:** rekomendasi batas keras pukul 23:59 WITA (tengah malam) dengan jam kantor sebagai target operasional, dan jalur pengecualian manual `group_ar_control` untuk uang yang sudah diterima tetapi tidak sempat tersinkron. Perlu konfirmasi jam batas dan siapa yang berwenang menerima pengecualian.
- **Q6 Giro (diputuskan pemilik: ikuti rekomendasi, perlakuan akuntansi mengikuti best practice):** lihat 8.10.

### 8.9 Dampak ke BE-20e (validasi per metode)

| Metode | Siapa memvalidasi | Langkah |
|---|---|---|
| Tunai | Kasir lalu accounting (D8/D9) | kasir menghitung setoran, accounting membuat dan merekonsiliasi pembayaran |
| Transfer | Admin finance memverifikasi mutasi rekening perusahaan, lalu accounting | langkah verifikasi (menggantikan hitung kasir) dicatat oleh sistem: pelaku, waktu, referensi mutasi; verifikasi telepon/WA tetap manual di luar sistem tetapi hasilnya wajib tercatat |
| Giro | Admin finance, lalu accounting | pencatatan giro (nomor, bank, jatuh tempo) di register giro; accounting memposting penerimaan ke akun giro diterima; pencairan dan penolakan diproses terpisah (8.10) |

Fase implementasi yang diusulkan: 20d mencatat ketiga metode; 20e dimulai dengan tunai, lalu transfer, lalu giro (PR terpisah). `collection_v2` tetap OFF sampai ketiga jalur yang dipakai di lapangan lulus review.

### 8.10 Giro: perlakuan akuntansi (D10-Q6)

Pemilik memutuskan mengikuti rekomendasi dan memakai praktik akuntansi yang lazim. Rancangan (perlu konfirmasi accountant sebelum implementasi 20e giro, [BU]):
1. **Giro diterima:** penerimaan divalidasi accounting dan diposting sebagai pembayaran pelanggan ke akun perantara **Giro Diterima** (giro dalam penyimpanan), bukan ke bank. Piutang faktur berkurang dan proteksi pending (8.3) lepas pada saat ini (`accounting_validated`). Giro tercatat di register: nomor, bank penerbit, tanggal jatuh tempo/cair, status.
2. **Giro cair:** pada atau setelah jatuh tempo, accounting memposting pemindahan **Giro Diterima ke Bank** (jurnal pencairan). Tidak mengubah piutang.
3. **Giro tolak/mundur:** pembayaran di langkah 1 dibalik (faktur terbuka kembali, aging kembali berjalan), giro ditandai tolak dengan alasan, faktur kembali menjadi kandidat SJP.
4. Pagar: giro belum jatuh tempo tidak dapat dicairkan; register giro memantau yang akan jatuh tempo dan yang lewat tanpa pencairan.
Koreksi atas 8.8 versi sebelumnya: pembayaran tidak menunggu pencairan; yang menunggu pencairan adalah pemindahan akun perantara ke bank. Konsekuensi: piutang tampak turun sebelum uang masuk bank, dengan risiko tolak yang ditangani langkah 3 dan register giro.
