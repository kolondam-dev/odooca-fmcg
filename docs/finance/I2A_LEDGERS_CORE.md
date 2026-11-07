# Paket I2a — Core Ledgers, Audit Trail, Combined TB & Sales/Purchase Register

## Scope dan status

- [F] Branch: `agen/finance-i2-ledgers-core` dari baseline `main` `0a6f3c76c2cd3c578087d7f0c968c38ef4044434` (pasca PR #99).
- [F] Cakupan report ID paket I2a (sub-paket pertama dari iterasi `I2`):
  - **`FIN01`** — General Ledger (`report.account_financial_report.general_ledger` pada OCA `account_financial_report` pin `f48b4ea777c444256aa1c215ec3117d604b5feff`).
  - **`FIN02`** — Trial Balance (`report.account_financial_report.trial_balance` pada OCA `account_financial_report`).
  - **`FIN03`** — Journal Ledger / buku jurnal (`report.account_financial_report.journal_ledger` pada OCA `account_financial_report`).
  - **`FIN04`** — Journal items audit / audit trail (`id.finance.audit.trail` pada `addons/id_finance_reporting`).
  - **`FIN51`** — Multi-company combined Trial Balance (`id.finance.combined.trial.balance` pada `addons/id_finance_reporting`; secara eksplisit `combined != consolidated`).
  - **`FIN57`** — Sales and purchase register (`id.finance.sales.purchase.register` pada `addons/id_finance_reporting`).
- [F] Paket ini **tidak** mengubah `deploy/init.sh`, `INIT_MODULES`, Company 1, chart of accounts, metode costing, maupun data demo Railway, dan **tidak** menandai baris `REPORT_CATALOG.csv` sebagai `ACCEPTED` (gate browser/XLSX/PDF export, full-volume performance I8, dan UAT Finance Controller tetap terbuka).

## Temuan source OCA dan perbaikan batas keamanan / filter

1. **Journal filter pada OCA General Ledger (`FIN01`):**
   - [F] Pada `account_financial_report` (`f48b4ea777c444256aa1c215ec3117d604b5feff`), `GeneralLedgerReportWizard._prepare_report_general_ledger()` menyalin `self.account_journal_ids.ids` ke `data["journal_ids"]`, tetapi `GeneralLedgerReport._get_report_values()` (`report/general_ledger.py` baris 803–854) tidak pernah membaca `data["journal_ids"]` dan hanya meneruskan `data["domain"]` (`extra_domain`) ke `_get_initial_balance_data` serta `_get_period_ml_data`.
   - [F] Agar filter jurnal konsisten di seluruh `FIN01`, `FIN02`, `FIN03`, dan `FIN04`, `GeneralLedger._get_report_values` di `addons/id_finance_foundation/models/report_boundary.py` menyalin `data` (tanpa memutasi dict pemanggil) dan menambahkan `("journal_id", "in", list(payload["journal_ids"]))` ke `payload["domain"]` ketika `journal_ids` diberikan.
2. **Isolasi filter lintas-perusahaan (`journal_ids` / `account_ids`):**
   - [F] `TrialBalanceReport._check_filter_company` di `addons/id_finance_reporting/models/trial_balance.py` (dipanggil pula oleh `check_scope` di `addons/id_finance_foundation/models/report_boundary.py` dan `id.finance.ledger.mixin`) menolak `journal_ids` atau `account_ids` yang bukan milik `company_id` aktif dengan `AccessError` sebelum query laporan dieksekusi.

## Desain model baru di `addons/id_finance_reporting`

1. **`id.finance.audit.trail` (`FIN04`):**
   - Memeriksa `_check_scope(company_id, journal_ids, account_ids)` dan batas periode (`<= 366` hari) serta batas baris (`LIMIT = 20000`, fail-closed dengan `UserError`, tanpa silent truncation).
   - Mengambil `account.move.line` posted (atau posted+draft bila diminta eksplisit) beserta daftar terpisah `draft_aml_ids_in_period`.
   - Mencatat provenance pembalikan/modifikasi (`reversed_entry_id`, `reversal_move_ids`, `is_reversal`, `is_reversed`, `create_uid`, `create_date`, `write_uid`, `write_date`, `matching_number`, `full_reconcile_id`) dan menandai baris tanpa partner pada akun reconcilable (`partnerless_reconcilable_aml_ids`).
2. **`id.finance.combined.trial.balance` (`FIN51`):**
   - Memvalidasi `_check_scope(cid)` untuk **setiap** perusahaan di `company_ids` (menolak jika salah satu perusahaan tidak aktif atau tidak diizinkan bagi user).
   - Memanggil `report.account_financial_report.trial_balance._get_data` per entitas, mencatat mata uang fungsional entitas serta kurs konversi `res.currency._get_conversion_rate` pada `rate_date`, menerjemahkan saldo ke `presentation_currency_id`, dan menggabungkan per kode akun melalui `combine_trial_balances` (`addons/id_finance_reporting/models/ledger_compare.py`).
   - Menyertakan metadata eksplisit `"scope": "combined_multi_entity_trial_balance_not_consolidated"` dan `"eliminations_applied": False`.
3. **`id.finance.sales.purchase.register` (`FIN57`):**
   - Memeriksa `_check_scope(company_id, journal_ids)` dan mengambil dokumen `out_invoice`, `out_refund`, `in_invoice`, `in_refund`.
   - Mengekstrak setiap dokumen dan baris AML tepat satu kali (`duplicate_move_ids == []`, `duplicate_line_ids == []`), memisahkan saldo DPP (`base_balance_gl`), pajak (`tax_balance_gl`), dan kontrol AR/AP (`control_balance_gl`).
   - Merekonsiliasi total register terhadap seluruh baris `account.move.line` posted pada akun pendapatan/beban/pajak di periode tersebut (`gl_tie_out`), memisahkan jurnal non-invoice (`non_register_gl_lines`) sehingga `unexplained_difference == 0`.

## Angka kontrol independen (`scripts/ops/verify_finance_i2_ledgers_core.py`)

Fixture disposable 2 perusahaan (`scale=1` dan `scale=7`) × 3 periode (`2026-05` kosong, `2026-07` transaksi lengkap + draft noise, `2026-08` pelunasan akhir) pada database `finance_i0_reports_disposable`:

| Akun | Juli Opening | Juli Debit | Juli Credit | Juli Closing | Agustus Opening | Agustus Debit | Agustus Credit | Agustus Closing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `cash` | 100 | 75 | 30 | 145 | 145 | 28 | 47 | 126 |
| `ar` | 0 | 110 | 82 | 28 | 28 | 0 | 28 | 0 |
| `ap` | 0 | 53 | 100 | -47 | -47 | 47 | 0 | 0 |
| `revenue` | 0 | 20 | 115 | -95 | -95 | 0 | 0 | -95 |
| `tax_output` | 0 | 2 | 10 | -8 | -8 | 0 | 0 | -8 |
| `expense` | 0 | 92 | 22 | 70 | 70 | 0 | 0 | 70 |
| `tax_input` | 0 | 8 | 1 | 7 | 7 | 0 | 0 | 7 |
| `equity` | -100 | 0 | 0 | -100 | -100 | 0 | 0 | -100 |

Skenario dan counterexample yang diuji di `scripts/ops/verify_finance_i2_ledgers_core.py`:
- Periode kosong (`2026-05-01..2026-05-31`), saldo awal sebelum periode (`2026-06-30`), faktur/retur pelanggan & tagihan/retur pemasok dengan PPN 10%, pembayaran parsial Juli & pelunasan Agustus, jurnal umum tanpa partner pada akun pendapatan, serta akrual AP tanpa partner + pembalikan `_reverse_moves` (terbukti masuk grup `Missing Partner` `id=0` di `FIN01` dan terdeteksi di `FIN04`).
- Filter jurnal penjualan (`I2A_JULY_SALE_JOURNAL`) konsisten di `FIN01`, `FIN02`, `FIN03`, dan `FIN04`.
- Unreconcile probe (`remove_move_reconcile()`) + rollback: membatalkan rekonsiliasi mengubah residual invoice tetapi tidak mengubah saldo `FIN01`/`FIN02`.
- `FIN51` menggabungkan Company A (`1×`) dan Company B (`7×`) menjadi `8×` dalam IDR serta menguji translasi ke USD dengan kurs eksplisit `0.5`.
- Counterexample keamanan: `Finance Reader` diizinkan membaca laporan Company A tetapi ditolak (`AccessError`) saat mengakses Company B, saat menyuntikkan `journal_id` Company B, atau saat meminta `[comp_a, comp_b]` di `FIN51`; peran `Sales` dan `Driver` (`id_mobile_api.group_mobile_evidence`) tanpa `sudo` ditolak di keenam laporan.
- Counterexample mutasi seimbang (`tamper_balanced`): jurnal seimbang tambahan ditolak oleh oracle `FIN01`, `FIN02`, `FIN03`, `FIN04`, dan `FIN57`, lalu di-rollback via savepoint dan baseline terverifikasi pulih.

## Gate yang masih terbuka

- [BU] Eksekusi CI native exact-SHA pada workflow `Finance I0 candidate spike` (`.github/workflows/finance-i0-spike.yml`) untuk commit HEAD branch `agen/finance-i2-ledgers-core`.
- [BU] Paket `I2b` (`FIN05–FIN09`: Partner Ledger AR/AP, Open Items AR/AP, Aged Receivable/Payable) dan `I2c` (`FIN36–FIN38`, `FIN55–FIN56`).
- [BU] Bukti export PDF/XLSX, browser geometry desktop/tablet, volume/performance `I8`, dan sign-off Finance Controller sebelum status katalog dapat mencapai `ACCEPTED`.
