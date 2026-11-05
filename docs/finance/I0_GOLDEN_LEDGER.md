# I0 lanjutan — golden ledger minimal

Basis: main `6af00a9e8fcd164941ebbbd35db98df7e70754ac` (merge PR89).
Branch: `agen/finance-i0-golden-ledger`. Tidak mengaktifkan modul pada database demo.

## Bukti sebelumnya

PR89 PASS terbatas pada audit awal dan containment legacy, HEAD `c3a7a79`;
12 job PR unik hijau, 207 tes Odoo, RPC legacy ditolak dan ledger identik,
lima profil kandidat install/upgrade disposable, persistent upgrade zero-drift.
Merged ke main, **bukan** acceptance I0 penuh atau FIN01–58.

## Fixture dan oracle

`scripts/ops/verify_finance_golden_ledger.py` hanya menerima nama DB persis
`finance_i0_reports_disposable`. Runner memakai Odoo ORM nyata dan memanggil
`report.account_financial_report.trial_balance._get_data` produksi OCA pada pin
proyek, bukan salinan engine report. Dua company baru dengan delapan akun
masing-masing; company B memiliki nominal tujuh kali A sebagai kontrol kebocoran
company. Semua fixture di-rollback melalui savepoint, tidak ada commit.

Expected di bawah ditentukan sebelum report dijalankan; satuan nominal IDR
sintetis, **bukan** tarif/kebijakan pajak. Semua dokumen merupakan general journal
entry: label sale/credit/purchase hanya narasi ledger, belum native invoice/refund.

| Akun A | Opening Juli | Debit Juli | Kredit Juli | Closing Juli / Opening Agustus | Closing Agustus |
|---|---:|---:|---:|---:|---:|
| Cash | 100 | 60 | 25 | 135 | 133 |
| AR | 0 | 110 | 82 | 28 | 0 |
| AP | 0 | 25 | 55 | -30 | 0 |
| Revenue | 0 | 20 | 100 | -80 | -80 |
| Output tax control | 0 | 2 | 10 | -8 | -8 |
| Expense | 0 | 50 | 0 | 50 | 50 |
| Input tax control | 0 | 5 | 0 | 5 | 5 |
| Equity | -100 | 0 | 0 | -100 | -100 |

Agustus hanya receipt AR28 dan pembayaran AP30. Periode opening, debit/kredit,
closing setiap akun dibandingkan angka eksplisit; himpunan akun harus tepat.
Draft noise999 tidak boleh masuk mode posted; mode draft-inclusive wajib berubah
sesuai expected. Mutation balanced cash/equity +1/-1 wajib ditolak oracle, rollback,
lalu baseline OCA kembali lulus. Ini bukan tes constraint balance saja.

## Gate

Workflow spike melakukan install+upgrade profil reports lebih dulu, lalu shell
runner dan sentinel `FINANCE_GOLDEN_LEDGER=PASS`; log menjadi artifact CI.
Tes lokal hanya memeriksa konsistensi expected, ketajaman assertion dan penolakan
DB operasional. Tidak menggantikan runtime OCA/PostgreSQL.

**Belum ditutup:** native invoice/refund/payment reconciliation, historical AR/AP,
partnerless exceptions, HPP/stock/landed cost/ownership, FX/assets/accrual/close,
official tax source, mapped COA demo, role/company negatives, export/visual dan UAT.
Company scope positif di report superuser bukan pengujian record rules user.
Fixture kecil ini adalah tahap awal golden dataset kontrak §C, bukan keseluruhannya.
FIN02 tetap BELUM_DITERIMA sampai seluruh acceptance report terbukti.
