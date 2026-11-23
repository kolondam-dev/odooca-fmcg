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

## 5. Pertanyaan terbuka

1. Satu SJP per kolektor per tanggal, atau boleh beberapa SJP per hari?
2. `unpaid`: faktur tetap pada SJP berikutnya otomatis, atau harus digenerate ulang oleh AR admin?
3. Apakah kasir dan accounting dua langkah berurutan (kasir dulu), dan bolehkah satu orang memegang keduanya (segregasi tugas)?
4. Cetak SJP: PDF (QWeb) wajib pada 20b atau menyusul?
