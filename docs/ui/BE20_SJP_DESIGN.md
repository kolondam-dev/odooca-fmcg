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

