# Paket I2b — AR/AP Subledger, Open Items & Signed Aging

## Scope dan status

- [F] Branch: `agen/finance-i2b-arap-subledger` dari baseline `main`
  `df0c1bd441ee8532d76350544219e96efae95da5` (pasca PR #98 dan PR #101).
- [F] Cakupan report ID paket I2b (sub-paket kedua dari iterasi `I2`):
  - **`FIN05`** — Partner Ledger AR (`id.finance.partner.ledger`, `partner_type="customer"`).
  - **`FIN06`** — Partner Ledger AP (`id.finance.partner.ledger`, `partner_type="supplier"`).
  - **`FIN07`** — Open Items AR/AP as of date (`id.finance.open.items`).
  - **`FIN08`** — Aged Receivable (`id.finance.aged.partner.balance`, `partner_type="customer"`).
  - **`FIN09`** — Aged Payable (`id.finance.aged.partner.balance`, `partner_type="supplier"`).
- [F] Model baru berada di `addons/id_finance_reporting/models/subledger_reports.py`
  dengan aritmetika murni tanpa ORM di
  `addons/id_finance_reporting/models/ledger_subledger.py`.
- [F] Paket ini **tidak** mengubah `deploy/init.sh`, `INIT_MODULES`, Company 1,
  chart of accounts, metode costing, maupun data demo Railway, dan **tidak**
  menandai baris `REPORT_CATALOG.csv` `FIN05`–`FIN09` sebagai `ACCEPTED`.
  Gate export XLSX/PDF, browser geometry, volume/performance `I8`, dan sign-off
  Finance Controller tetap terbuka.

## Keputusan desain

1. **AR dan AP tidak pernah di-net.** Pengelompokan partner ledger dan open items
   memakai kunci `(partner_id, account_type)`. Pilihan `partner_type="all"`
   mengembalikan dua kelompok terpisah, sehingga saldo piutang tidak pernah
   mengurangi saldo utang.
2. **Saldo open items direkonstruksi dari partial reconciliation bertanggal.**
   Untuk setiap baris kontrol:
   - `residual = balance + Σ(partial.amount, max_date ≤ as_of)` untuk sisi kredit;
   - `residual = balance − Σ(partial.amount, max_date ≤ as_of)` untuk sisi debit.
   `amount_residual` saat ini **tidak** dipakai untuk laporan as-of. Ini mencegah
   pembayaran Agustus menutup faktur yang masih terbuka pada 14/25/31 Juli.
   Formula ini setara dengan rekonstruksi OCA pada pin
   `f48b4ea777c444256aa1c215ec3117d604b5feff`: OCA menambahkan kembali partial
   dengan `max_date > date_at` ke `amount_residual` berjalan.
3. **Aging bertanda dan harus tie-out.** Bucket `current`, `days_1_30`,
   `days_31_60`, `days_61_90`, `days_91_120`, dan `older` menyimpan saldo
   bertanda (piutang positif, utang negatif). `bucket_sum` wajib sama dengan
   `total_residual` open items; `gl_tie_out` membandingkan total subledger dengan
   total saldo akun kontrol pada tanggal/periode yang sama.
4. **Baris tanpa partner adalah exception eksplisit.** Baris partnerless tidak
   dibuang. Laporan menyertakan `partnerless_residual` dan
   `partnerless_line_ids`, sementara partner ledger menampilkan baris
   `partner_id = 0` dengan `partnerless = True`.
5. **Batas query fail-closed.** Setiap `_snapshot` memakai
   `_check_scope(company_id, journal_ids, account_ids)` dari
   `id.finance.ledger.mixin`, `_bounded` dengan `LIMIT = 20000`, periode
   `<= 367` hari untuk partner ledger, satu tanggal as-of untuk open items, dan
   validasi mitra lintas-perusahaan (`AccessError`).

## Perilaku laporan

| Report | Input utama | Output kunci |
|---|---|---|
| `FIN05` / `FIN06` | `company_id`, `date_from`, `date_to`, `partner_type`, `journal_ids`, `partner_ids`, `only_posted_moves` | `rows` per `(partner, account_type)`, `opening_balance`, `debit`, `credit`, `closing_balance`, `by_account_type`, `gl_tie_out` |
| `FIN07` | `company_id`, `as_of_date`, `date_from` opsional, `partner_type`, `journal_ids`, `partner_ids` | residual per baris, total per akun, `partnerless_residual`, `partnerless_line_ids`, `closed_line_ids`, `gl_tie_out` |
| `FIN08` / `FIN09` | sama dengan `FIN07` plus `bucket_edges` | bucket bertanda per partner/akun, `bucket_sum`, `unexplained_difference`, `balanced`, `gl_tie_out` |

## Angka kontrol independen

Fixture disposable dua perusahaan (`scale=1` dan `scale=7`) dari
`build_i2a_fixture` pada database `finance_i0_reports_disposable`:

| Pemeriksaan (`scale=1`) | Opening | Debit | Credit | Closing |
|---|---:|---:|---:|---:|
| `FIN05` AR Juli | 0 | 110 | 82 | 28 |
| `FIN06` AP Juli — total | 0 | 53 | 100 | -47 |
| `FIN06` AP Juli — partner bernama | 0 | 41 | 88 | -47 |
| `FIN06` AP Juli — partnerless | 0 | 12 | 12 | 0 |
| `FIN05` AR Agustus | 28 | 0 | 28 | 0 |
| `FIN06` AP Agustus | -47 | 47 | 0 | 0 |

| Open items as-of | AR | AP |
|---|---:|---:|
| 2026-07-14 | 110 | -88 |
| 2026-07-25 | 28 | -59 (termasuk partnerless -12) |
| 2026-07-31 | 28 | -47 |
| 2026-08-31 | 0 | 0 |

Aging 2026-07-31: `FIN08` `days_1_30 = 28`; `FIN09` `days_1_30 = -47`.

## Oracle dan counterexample native

`scripts/ops/verify_finance_i2_arap_subledger.py` berjalan hanya pada
`finance_i0_reports_disposable`, di dalam savepoint, dan tidak memanggil helper
produksi. Oracle membaca `account.move.line` posted serta
`account.partial.reconcile` secara langsung. OCA `open_items` dan
`aged_partner_balance` dirender lewat `_get_report_values` nyata dan
dibandingkan dengan oracle yang sama.

Skenario yang diuji:
- Partner ledger Juli/Agustus untuk AR dan AP pada `scale=1` dan `scale=7`,
  termasuk pemisahan `all` dan baris partnerless.
- Open items pada 14/25/31 Juli dan 31 Agustus, termasuk pembuktian bahwa
  `amount_residual` saat ini akan salah menjadi 0 untuk posisi 14 Juli.
- Aging pada 14/25/31 Juli dengan bucket bertanda, coverage per partner, dan
  tie-out ke total open items/GL kontrol.
- OCA `open_items` pada 14 dan 31 Juli; OCA `aged_partner_balance` pada 25 dan
  31 Juli dengan konfigurasi interval 30/60/90/120.
- Role negative: Finance Reader ditolak untuk perusahaan lain, jurnal perusahaan
  lain, dan partner perusahaan lain; Sales/Driver ditolak pada ketiga model.
- Mutasi seimbang (tamper) ditolak oleh oracle partner ledger, open items, dan
  aging, lalu rollback savepoint memulihkan baseline.
- Unreconcile probe: `remove_move_reconcile()` membuka kembali baris bertanggal
  dan total kontrol AR tetap 28, lalu rollback memulihkan rekonsiliasi.

## Gate yang masih terbuka

- [BU] Eksekusi CI native exact-SHA pada workflow `Finance I0 candidate spike`
  (`.github/workflows/finance-i0-spike.yml`) untuk commit HEAD branch
  `agen/finance-i2b-arap-subledger`; langkah baru mencetak
  `FINANCE_I2B_ARAP_SUBLEDGER=PASS`.
- [BU] Bukti export XLSX/PDF, browser geometry desktop/tablet, volume/performance
  `I8`, dan sign-off Finance Controller sebelum status katalog dapat mencapai
  `ACCEPTED`.
- [BU] Paket `I2c` (`FIN36–FIN38`, `FIN55–FIN56`) tetap terpisah.
