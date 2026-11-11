# Paket I2c — Accrual Schedules (FIN37) & FX Revaluation (FIN38)

## Scope dan status

- [F] Implementasi langkah 3 pada rencana ADR
  `docs/finance/I2C_DISCOVERY_ADR.md` (FIN37 + FIN38), keduanya **custom**
  tanpa dependensi OCA baru.
- [F] Report ID: `FIN37` (`id.finance.accrual.schedule`) dan `FIN38`
  (`id.finance.fx.revaluation`) pada `addons/id_finance_reporting`.
- [F] Aritmetika murni tanpa ORM berada di
  `addons/id_finance_reporting/models/ledger_schedules.py`; lapisan laporan
  yang membatasi query ada di `models/schedule_reports.py`.
- [F] Paket ini **tidak** menandai `REPORT_CATALOG.csv` `FIN37`/`FIN38` sebagai
  `ACCEPTED`, tidak mengubah `oca.lock`, `deploy/init.sh`, `INIT_MODULES`, maupun
  data demo Railway.

## FIN37 — Accrual / Prepayment / Deferred schedules

**Sumber:** `account.move.line` posted yang dibatasi
`account_ids`/`journal_ids`/`partner_ids` dan `date <= as_of`, dengan metadata
periode dari `start_date`/`end_date` (field OCA `account_invoice_start_end_dates`).

**Aturan yang ditegakkan:**

1. Tanpa `start_date` **dan** `end_date` yang valid → baris menjadi exception
   bernominal `missing_schedule_metadata`. **Tidak ada alokasi asumtif**; tanggal
   dokumen (`date`) atau `date_maturity` tidak dipakai sebagai pengganti.
2. `start_date > end_date` → exception `invalid_schedule_range`.
3. Pengakuan straight-line berbasis **hari inklusif** dalam rentang; periode
   bulanan dibentuk dari rentang tersebut dan periode terakhir menyerap selisih
   pembulatan sehingga `Σ periode == balance` tepat.
4. `accounted_total = recognized_total + remaining_total + exception_total` dan
   wajib sama dengan `control_total` (`unexplained_difference == 0`).

**Output kunci:** `rows` (dengan `periods`, `recognized_to_date`, `remaining`),
`exceptions`, `control_total`, `recognized_total`, `remaining_total`,
`exception_total`, `balanced`, `unexplained_difference`,
`schedule_metadata_available`.

`schedule_metadata_available` memberi tahu operator apakah modul metadata
terpasang. Di database disposable saat ini nilainya `false`, sehingga seluruh
baris menjadi exception — perilaku fail-closed yang benar, bukan laporan kosong
yang tampak sehat.

## FIN38 — Foreign Currency / FX revaluation

**Dua komponen yang tidak pernah dijumlahkan menjadi satu angka:**

| Komponen | Sumber | Aturan |
|---|---|---|
| Unrealized | `amount_residual_currency` × kurs as-of − `amount_residual` | Hanya posisi **terbuka**; baris residual nol tidak menyumbang |
| Realized | `account.partial.reconcile` | Per partial, hanya bila `max_date <= as_of` |

**Formula realized per partial** (sesuai ADR-I2c-03):

```
rate_debit  = debit_leg.balance  / debit_leg.amount_currency
rate_credit = credit_leg.balance / credit_leg.amount_currency

realized = debit_amount_currency × rate_debit
         − (−credit_amount_currency × rate_credit)
```

Positif = **loss**, negatif = **gain**; searah dengan `_get_exchange_account()`
pada inti Odoo yang memilih akun expense untuk residual positif.

**Bukti posting dan tie-out:**

- Partial dengan `exchange_move_id` → masuk `realized_rows` dan **tie-out**:
  `Σ realized == Σ signed balance` pada akun exchange gain/loss.
- Partial tanpa `exchange_move_id` → tetap dihitung tetapi dilaporkan sebagai
  `realized_unposted_rows`/`realized_unposted_total` dan **dikeluarkan** dari
  tie-out. Tidak diklaim sebagai realized yang terbukti.
- Akun `income_currency_exchange_account_id` dan
  `expense_currency_exchange_account_id` **dikecualikan** dari basis unrealized
  agar jurnal exchange tidak dihitung dua kali.

Tie-out memakai **signed** balance, bukan `−balance`. Untuk gain −100.000,
Odoo mengkredit akun income exchange sehingga signed balance −100.000; `−balance`
akan menghasilkan +100.000 dan gagal.

## Verifikasi

**Unit (tanpa database):** `tests/test_finance_i2c_schedules.py`, 20 tes —
penolakan metadata hilang/terbalik, pengakuan penuh/parsial/sebelum mulai,
keseimbangan jadwal, empat kasus realized (gain, loss, parsial, mata uang
fungsional), `amount_currency == 0`, pemisahan posted vs unposted, pengecualian
akun exchange, dan tie-out dua arah termasuk regresi `−balance`.

**Native (disposable):** `scripts/ops/verify_finance_i2c_schedules.py` berjalan
pada `finance_i0_reports_disposable` di dalam savepoint. Oracle independen
membaca AML posted, `account.partial.reconcile`, dan akun exchange perusahaan
tanpa memanggil helper produksi. Fixture FX membentuk faktur 100 USD @15.000 dan
pembayaran 100 USD @16.000 yang direkonsiliasi penuh, sehingga Odoo memposting
exchange gain −100.000.

Counterexample wajib: tamper seimbang ditolak FIN37 lalu rollback memulihkan
baseline; Finance Reader ditolak untuk perusahaan/jurnal/partner lain; Sales
ditolak pada kedua model.

## Gate yang masih terbuka

- [BU] CI native exact-SHA untuk runner baru (langkah
  `FINANCE_I2C_SCHEDULES=PASS`).
- [BU] Pin `account_invoice_start_end_dates` agar FIN37 dapat mengalokasikan
  jadwal nyata; tanpa pin, laporan benar tetapi seluruhnya menjadi exception.
- [BU] Verifikasi FIN38 terhadap jurnal exchange native pada data non-sintetis.
- [F] `REPORT_CATALOG.csv` `FIN37`/`FIN38` tetap `BELUM_DITERIMA`.
