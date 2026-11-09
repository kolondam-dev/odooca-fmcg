# Paket I2c — Discovery dan ADR sumber (FIN36–38, FIN55–56)

## Scope dan status

- [F] Dokumen ini adalah **discovery + ADR**, bukan implementasi. Tidak ada
  perubahan kode, `oca.lock`, `deploy/init.sh`, `INIT_MODULES`, data demo, atau
  status `REPORT_CATALOG.csv`. `FIN36`–`FIN38`, `FIN55`–`FIN56` tetap
  `BELUM_DITERIMA`.
- [F] Cakupan report ID: `FIN36` (Fixed Asset register / depreciation), `FIN37`
  (Accrual / Prepayment / Deferred schedules), `FIN38` (Foreign Currency / FX
  revaluation), `FIN55` (Loan / lease / interest liability schedules), `FIN56`
  (Payroll / employee reimbursement to GL).
- [F] Basis: `main` `6ff44a77af89bc67670622c112679fd94475a520` (pasca PR #107).
- [A] Pola arsitektur mengikuti I2a/I2b: **baca sumber native/OCA dan rekonsiliasi
  ke GL**, jangan membangun buku besar kedua. Bila sumber tidak ada, custom hanya
  untuk lapisan jadwal/bridge dengan oracle yang sama.

## Audit kandidat pada pin proyek

Semua pembacaan dilakukan pada SHA yang tercatat, bukan pada HEAD cabang.

| Kandidat | Sumber dan versi | Lisensi / dependensi | Ketersediaan |
|---|---|---|---|
| `account_asset_management` | `OCA/account-financial-tools` @ `c23fd09977c870eb3db071fca5958b83f699bc4a`, versi `19.0.1.0.3` | AGPL-3; depends `account`, `report_xlsx_helper`; excludes `account_asset`; python `python-dateutil` | [F] Ada di repo pada SHA pin, **tetapi belum ada di `oca.lock` dan belum ada di image** |
| `report_xlsx_helper` | `OCA/reporting-engine` @ `b9e8c6cdd2d106614eddaf81bd78f487ae35db45` | AGPL-3 | [F] Ada di repo; closure `account_asset_management` tersedia |
| `account_cutoff_base` | — | — | [F] Tidak ada di tree `OCA/account-closing` 19.0 (hanya `account_fiscal_year_closing`, `account_invoice_start_end_dates`) dan tidak ada di `account-financial-tools` pin |
| `account_multicurrency_revaluation` | — | — | [F] Tidak ada di `account-financial-tools` 19.0 (25 addon diperiksa) |
| `payroll` | `OCA/payroll` @ `58f8a39799383ef98d50097f81f4abcc6dd03782`, versi `19.0.1.0.2` | LGPL-3; depends `hr_holidays`, `mail` | [F] Ter-pin di `oca.lock`; tree hanya berisi addon `payroll` — `payroll_account` tidak ada |
| Loan / lease / interest | — | — | [F] Tidak ada kandidat pada repo yang di-pin |

Bukti model aset pada SHA pin (`account_asset_management`):

- [F] `account.asset` menyimpan `state`, `method`, `method_number`,
  `method_period`, `method_time`, `date_start`, `date_remove`, `purchase_value`,
  `salvage_value`, `depreciation_base`, `value_residual`, `value_depreciated`,
  `depreciation_line_ids`, `account_move_line_ids`, `company_id`, `currency_id`.
- [F] `account.asset.line` (kelas `AccountAssetLine`) menyimpan `type`
  (`create` = Depreciation Base, `depreciate` = Depreciation, `remove` = Asset
  Removal), `parent_state`, `amount`, `remaining_value`, `depreciated_value`,
  `line_date`, `move_id`, `move_check`, `company_id`, `currency_id`.

Implikasi: register aset **dapat direkonstruksi** dari `account.asset.line` +
`move_id` tanpa menulis ulang mesin depresiasi. Ini memenuhi kriteria
"opening + additions − disposals − depreciation = closing" dengan bukti posting.

Bukti payroll pada SHA pin:

- [F] `hr.payslip` **tidak** mereferensikan `account.move` maupun `move_id`;
  addon `payroll` tidak memposting ke GL.
- [F] Profil CI `native` memasang `hr_expense` dan `payroll`, tetapi pada
  database **terpisah** (`finance_i0_native_disposable`), bukan pada
  `finance_i0_reports_disposable` tempat runner I2a/I2b berjalan.

Implikasi: `FIN56` tidak bisa "membaca posting payroll" karena tidak ada. Bridge
harus membandingkan **sumber payroll/expense yang disetujui** terhadap akun
beban dan utang di GL, dengan pembayaran dan liabilitas pajak dipisah.

## Keputusan (ADR)

### ADR-I2c-01 — FIN36 memakai OCA, dengan prasyarat pin

**Keputusan:** `FIN36` membaca `account.asset.line` dari
`account_asset_management`; tidak membangun register aset custom.

**Alasan:** modul tersedia pada SHA pin, berstatus `Mature`, dan sudah menyimpan
provenance posting (`move_id`, `move_check`, `parent_state`) yang diperlukan
untuk tie-out GL.

**Prasyarat sebelum implementasi:**

1. Tambah `account-financial-tools` ke `oca.lock` (sudah ada) **dan** aktifkan
   `account_asset_management` pada image/profil; saat ini belum.
2. Spike install + upgrade pada DB disposable, termasuk konflik `excludes:
   ["account_asset"]` dan dependensi `report_xlsx_helper`.
3. [A] Keputusan lisensi: modul OCA berlisensi AGPL-3 sedangkan addon custom
   repo memakai LGPL-3. Menjadi dependensi langsung membuat karya gabungan.
   Perlu keputusan pemilik repo sebelum `depends` ditambahkan. Alternatif tanpa
   dependensi (membaca tabel lewat SQL/reflection) **ditolak** karena rapuh dan
   menyembunyikan kontrak.

**Bila pin ditolak:** `FIN36` turun ke status BLOCKED dengan ADR pengganti,
bukan ditandai N/A dan bukan diisi angka rekaan.

### ADR-I2c-02 — FIN37 custom, rekonstruksi dari AML posted

**Keputusan:** jadwal accrual/prepayment/deferred dibangun sebagai **rekonstruksi
baca-saja** dari `account.move.line` posted pada akun beban dibayar dimuka /
akrual, memakai rentang `date_start`–`date_end` per jadwal. Tidak ada posting
otomatis oleh modul baru.

**Alasan:** `account_cutoff_base` tidak tersedia pada pin mana pun yang diaudit,
sehingga tidak ada mesin cutoff yang bisa dibaca.

**Batas yang harus dijaga:**

- Setiap baris pengakuan harus berasal dari AML posted; modul tidak boleh
  membuat jurnal sendiri (menghindari double posting).
- Total pengakuan periode + saldo tersisa harus sama dengan saldo akun kontrol.
- Jadwal tanpa rentang tanggal valid menjadi exception eksplisit, bukan
  diasumsikan 12 bulan.

### ADR-I2c-03 — FIN38 custom, dari `amount_currency` vs `balance`

**Keputusan:** unrealized dan realized FX direkonstruksi dari selisih
`amount_currency` dan `balance` pada AML posted, dipisah per akun dan mata uang.

**Alasan:** `account_multicurrency_revaluation` tidak ada pada pin; tidak ada
sumber OCA yang bisa direkonsiliasi.

**Batas yang harus dijaga:**

- Realized (dari partial reconcile) dan unrealized (saldo terbuka) **tidak**
  dijumlahkan menjadi satu angka.
- Selisih kurs yang sudah diposting ke akun laba/rugi kurs tidak dihitung dua
  kali: baris akun FX dikecualikan dari basis dan direkonsiliasi terpisah.
- Perusahaan tanpa transaksi valuta asing menjadi kasus kosong yang sah, bukan
  N/A otomatis.

### ADR-I2c-04 — FIN55 custom amortization schedule

**Keputusan:** jadwal pinjaman/sewa dibangun dari saldo liabilitas GL plus
parameter kontrak (pokok awal, penarikan, bunga, pembayaran) yang disetujui
Finance Controller.

**Alasan:** tidak ada kandidat OCA pada repo yang di-pin.

**Batas yang harus dijaga:**

- Identitas `opening principal + drawdowns + interest/remeasurement − payments =
  closing liabilities` wajib tie ke akun liabilitas GL.
- Parameter kontrak adalah kebijakan bertanggal dengan sumber, bukan konstanta
  kode (aturan `docs/DEVELOPMENT.md` §2.3).
- Bunga akrual vs bunga dibayar dipisah.

### ADR-I2c-05 — FIN56 bridge payroll/expense ke GL

**Keputusan:** bridge custom yang membandingkan sumber payroll `hr.payslip`
(disetujui) dan `hr.expense` terhadap akun beban dan utang di GL.

**Alasan:** `payroll` tidak memposting ke GL dan `payroll_account` tidak ada pada
pin, sehingga tidak ada jalur "payroll → journal" yang bisa dibaca.

**Batas yang harus dijaga:**

- Slip yang belum disetujui tidak dihitung sebagai beban.
- Pembayaran gaji, utang pajak, dan potongan dipisah; tidak di-net menjadi satu
  angka.
- Selisih antara sumber payroll dan GL dilaporkan sebagai exception dengan
  nominal, bukan disapu ke rounding.
- **Tidak** membuat jurnal payroll rekaan untuk menutup selisih.

## Kontrak oracle native

Runner baru `scripts/ops/verify_finance_i2c_schedules.py` mengikuti pola I2b:
berjalan hanya pada `finance_i0_reports_disposable`, di dalam savepoint, dan
**tidak** memanggil helper produksi. Oracle membaca `account.move.line` posted,
`account.partial.reconcile`, `account.asset.line` (bila FIN36 aktif), dan
`hr.payslip`/`hr.expense` (bila FIN56 aktif) secara langsung.

| Report | Identitas yang diuji |
|---|---|
| `FIN36` | `opening + additions − disposals − depreciation = closing`; setiap baris depresiasi punya `move_id` posted; tie-out ke akun akumulasi depresiasi |
| `FIN37` | pengakuan periode + saldo tersisa = saldo akun kontrol; tidak ada jurnal buatan modul |
| `FIN38` | realized dan unrealized terpisah; baris akun FX dikecualikan dari basis; tie-out per akun/mata uang |
| `FIN55` | `opening + drawdowns + interest − payments = closing`; tie-out ke akun liabilitas |
| `FIN56` | total slip disetujui = beban GL terkait; pembayaran/utang pajak terpisah; exception bernominal |

Counterexample wajib: mutasi seimbang (tamper) ditolak, rollback savepoint
memulihkan baseline, role tanpa hak accounting ditolak, dan perusahaan lain
ditolak.

## Rencana pemecahan PR

| Urutan | Isi | Gate |
|---|---|---|
| 1 (dokumen ini) | Discovery + ADR | Review pemilik; belum ada kode |
| 2 | Pin `account_asset_management` + spike install/upgrade + keputusan lisensi | CI profile hijau, ADR-I2c-01 disetujui |
| 3 | `FIN37` + `FIN38` custom (paling sedikit dependensi eksternal) | Oracle native + unit |
| 4 | `FIN55` custom | Oracle native + kebijakan bertanggal |
| 5 | `FIN36` membaca OCA | Oracle native + coverage aset |
| 6 | `FIN56` bridge payroll/expense | Profil CI dengan `hr_expense`+`payroll` pada DB runner |

Urutan 3–6 dapat ditukar; urutan 2 harus lebih dulu bila `FIN36` ingin memakai
OCA. Setiap PR tetap wajib CI hijau exact SHA dan tidak menandai katalog
`ACCEPTED`.

## Gate yang masih terbuka

- [BU] Keputusan lisensi AGPL-3 (ADR-I2c-01) oleh pemilik repo.
- [BU] Spike install/upgrade `account_asset_management` pada DB disposable.
- [BU] Profil CI yang memasang `hr_expense` dan `payroll` pada
  `finance_i0_reports_disposable`.
- [BU] Sign-off Finance Controller atas parameter kontrak `FIN55` dan definisi
  "slip disetujui" pada `FIN56`.
- [F] `REPORT_CATALOG.csv` `FIN05`–`FIN09` masih `BELUM_DITERIMA`; gate export
  XLSX/PDF, browser geometry, volume/performance `I8`, dan sign-off Finance
  Controller untuk I2b tetap pekerjaan terpisah.
