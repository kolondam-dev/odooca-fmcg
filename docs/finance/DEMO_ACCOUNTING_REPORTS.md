# Demo accounting: OCA `account_financial_report`

Tanggal: 12 November 2026. Perusahaan demo: **PT Manado Distribusi Utama**
(company ID 1, chart `id`, IDR). Dokumen ini mencatat penyalaan laporan
keuangan untuk presentasi, bukan penerimaan FIN01–58.

## Scope yang disetujui pemilik

[F] Pemilik menyetujui pemasangan **hanya** `account_financial_report` untuk
kebutuhan demo hari ini. Modul lain tetap di luar scope:

- `id_finance_foundation` dan `id_finance_reporting` **tidak** dipasang;
  laporan custom FIN04–09/37/38/51/57 belum punya view/menu sehingga tidak
  dapat diklik.
- `partner_statement` dan `account_tax_balance` belum diminta; keduanya tetap
  kandidat, bukan bagian demo ini.
- `REPORT_CATALOG.csv` tidak berubah: seluruh 58 report ID tetap
  `BELUM_DITERIMA`.

## Perubahan deploy

1. `INIT_MODULES` di `deploy/init.sh` ditambah `account_financial_report`.
   Build baru (tanpa seed) langsung menginstalnya.
2. Blok bermark `install_account_financial_report_v1` memasang modul pada
   database yang **sudah berjalan**, tanpa `FORCE_UPGRADE` dan tanpa
   meng-upgrade seluruh `INIT_MODULES`. Mark membuat deploy berikutnya
   idempoten.

[F] Modul sudah tersedia di image karena root `Dockerfile` mengambil seluruh
repo pada `oca.lock`: `account-financial-reporting 19.0
f48b4ea777c444256aa1c215ec3117d604b5feff`. Tidak perlu menambah repo OCA atau
membangun image dengan pin baru.

## Modul dan laporan

[F] Manifest pada pin tersebut: `account_financial_report` v19.0.0.0.26,
lisensi AGPL-3, `depends: account, date_range, report_xlsx`, `installable`.
Dua dependensi terakhir ikut terpasang otomatis dari pin
`reporting-engine` dan `server-ux`.

Setelah terpasang, menu muncul di **Accounting/Invoicing → Reporting → OCA
accounting reports**:

| Laporan | Fungsi demo |
|---|---|
| General Ledger | Mutasi per akun dan saldo berjalan |
| Journal Ledger | Buku jurnal per jurnal/dokumen |
| Trial Balance | Neraca saldo debit/kredit per akun |
| Open Items | Outstanding AR/AP per tanggal |
| Aged Partner Balance | Aging piutang/utang per partner |
| VAT Report | Laporan PPN; lihat caveat di bawah |

Semua wizard mendukung filter periode/partner/akun dan export XLSX (melalui
`report_xlsx`) serta PDF (QWeb).

## Data demo

[F] Audit runtime I0 (5 November 2026) mencatat pada PT Manado Distribusi
Utama: 1.324 invoice pelanggan posted, 35 bill posted, 2.619 journal entry
posted, chart `id`, currency IDR. Angka tersebut adalah snapshot; jumlah
terkini belum diperiksa ulang [BU].

[F] Semua modul dijalankan dengan `--without-demo=true`, sehingga data demo
berasal dari seed/dump, bukan data contoh Odoo. Environment baru tanpa
`SEED_URL`/dump akan menghasilkan laporan kosong.

## Verifikasi dan batas

- [F] Profil CI `reports` sudah menginstal `account_financial_report` bersama
  `account_tax_balance`, `partner_statement`, `id_finance_reporting`, dan
  `account_invoice_start_end_dates` pada database disposable.
- [BU] Instalasi pada database demo yang sudah berisi 1.324 invoice dan 2.619
  journal entry belum dijalankan. Jalur yang diuji CI adalah instalasi pada
  database disposable, bukan upgrade database seed.
- [BU] Export XLSX/PDF dan tampilan browser pada database demo belum diuji.
- [BU] Mapping PPN belum divalidasi; VAT Report jangan disajikan sebagai angka
  resmi. Audit I0 mencatat 0 referensi pajak custom terisi.
- [A] Label menu berbahasa Inggris ("OCA accounting reports") karena berasal
  dari modul OCA; belum ada terjemahan Indonesia untuk label tersebut.

## Checklist demo

1. Buka Invoicing → Customers → Invoices, filter Posted.
2. Buka satu invoice: jurnal, pajak, dan pembayaran terkait.
3. Accounting → Reporting → OCA accounting reports → Trial Balance; pastikan
   total debit = total kredit.
4. General Ledger untuk akun piutang atau kas; tunjukkan saldo berjalan.
5. Aged Partner Balance untuk piutang; tunjukkan bucket umur.
6. Export satu laporan ke XLSX dan PDF (uji sebelum presentasi).
7. Lanjutkan ke dashboard moneter yang sudah terpasang untuk AR aging dan
   funnel.

## Risiko deploy

- Menambah `INIT_MODULES` tanpa blok bermark tidak akan menginstal apa pun
  pada database yang mark `upgrade_modules_v3`-nya sudah ada. Blok
  `install_account_financial_report_v1` menutup celah itu.
- `FORCE_UPGRADE=1` tetap meng-upgrade seluruh `INIT_MODULES`; hindari tepat
  sebelum presentasi.
- `RESET_DB` mengembalikan data ke seed dan menghapus perubahan manual.
