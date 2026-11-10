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
- [F] Aritmetika ADR dapat dieksekusi: `tests/test_finance_i2c_adr_formulas.py`
  (11 tes) mengunci formula FIN37 dan FIN38. Ini satu-satunya perubahan non-docs
  pada PR ini dan sifatnya test murni tanpa ORM/database.
- [F] Basis audit awal: `main` `6ff44a77af89bc67670622c112679fd94475a520` (pasca
  PR #107). Audit OCA selalu dibaca pada SHA pin, bukan HEAD cabang.
- [F] Delta `main` pasca-`6ff44a7`: PR #105 masuk sebagai
  `d9d6423852715dc3b53ff046b37e0c0a9d947c7e`. Perubahan tersebut menyentuh
  `data/registers/periods/2026-08/**`, `scripts/ops/seed_planner.py`,
  `scripts/ops/seed_v2_gates.py`, `scripts/ops/generate_period_pack.py`, dan tes
  seed. **Tidak ada perubahan** pada `addons/id_finance_reporting`,
  `addons/id_finance_foundation`, maupun `oca.lock`
  (`git diff --name-only 6ff44a7 d9d6423 -- addons/id_finance_reporting addons/id_finance_foundation oca.lock`
  mengembalikan kosong). Karena itu seluruh temuan sumber di bawah tetap valid
  tanpa diuji ulang; yang berubah hanya basis integrasi branch.

## Audit kandidat pada pin proyek

Semua pembacaan dilakukan pada SHA yang tercatat, bukan pada HEAD cabang.

| Kandidat | Sumber dan versi | Lisensi / dependensi | Ketersediaan |
|---|---|---|---|
| `account_asset_management` | `OCA/account-financial-tools` @ `c23fd09977c870eb3db071fca5958b83f699bc4a`, versi `19.0.1.0.3` | AGPL-3; depends `account`, `report_xlsx_helper`; excludes `account_asset`; python `python-dateutil` | [F] Ada di repo pada SHA pin, **tetapi belum ada di `oca.lock` dan belum ada di image** |
| `report_xlsx_helper` | `OCA/reporting-engine` @ `b9e8c6cdd2d106614eddaf81bd78f487ae35db45` | AGPL-3 | [F] Ada di repo; closure `account_asset_management` tersedia |
| `account_cutoff_base` | — | — | [F] Tidak ada di tree `OCA/account-closing` 19.0 (hanya `account_fiscal_year_closing`, `account_invoice_start_end_dates`) dan tidak ada di `account-financial-tools` pin. Pengganti metadata periode: `account_invoice_start_end_dates` (baris berikut). |
| `account_multicurrency_revaluation` | — | — | [F] Tidak ada di `account-financial-tools` 19.0 (25 addon diperiksa) |
| `payroll` | `OCA/payroll` @ `58f8a39799383ef98d50097f81f4abcc6dd03782`, versi `19.0.1.0.2` | LGPL-3; depends `hr_holidays`, `mail` | [F] Ter-pin di `oca.lock`; tree hanya berisi addon `payroll` — `payroll_account` tidak ada |
| Loan / lease / interest | — | — | [F] Tidak ada kandidat pada repo yang di-pin |
| `account_invoice_start_end_dates` | `OCA/account-closing` @ `8ce0077fd0762d49e928ea7520555341d7936a9e`, versi `19.0.1.0.0` | LGPL-3; depends `account` | [F] Ada di repo pada SHA tersebut, **belum di `oca.lock`** |

Bukti metadata jadwal pada SHA pin (`account_invoice_start_end_dates`):

- [F] `account.move.line` mendapat field `start_date` dan `end_date`
  (`fields.Date(index=True)`) serta `must_have_dates`
  (`related="product_id.must_have_dates"`).
- [F] `@api.constrains("start_date", "end_date", "display_type", "product_id", "parent_state")`
  menolak: hanya `start_date` tanpa `end_date`, hanya `end_date` tanpa
  `start_date`, dan `start_date > end_date`. Jadi pasangan tanggal valid
  dijamin konsisten oleh modul, bukan oleh asumsi laporan.

Bukti FX pada model inti Odoo 19 (`odoo/odoo` 19.0 `addons/account`):

- [F] `account.partial.reconcile` memiliki `exchange_move_id`,
  `debit_amount_currency`, `credit_amount_currency`, `amount`, `max_date`.
- [F] `account.move.line._prepare_exchange_difference_move_vals()` membuat
  jurnal selisih kurs memakai `company.currency_exchange_journal_id`,
  `company.income_currency_exchange_account_id`, dan
  `company.expense_currency_exchange_account_id`.
- [F] Karena itu realized FX punya bukti posting yang bisa dibaca
  (`exchange_move_id`), bukan hanya selisih agregat `amount_currency` vs
  `balance`.

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
3. [A] **Penilaian lisensi sebelum menambah dependensi.** Modul OCA
   `account_asset_management` berlisensi AGPL-3, sedangkan addon custom repo
   memakai LGPL-3. Menjadikannya dependensi langsung menimbulkan pertanyaan
   kewajiban lisensi (distribusi, penyediaan source, dan kompatibilitas
   AGPL-3 dengan LGPL-3) yang **harus dinilai pemilik repo atau penasihat
   hukum**. Metadata manifest AGPL-3/LGPL-3 saja **tidak cukup** untuk
   menetapkan kesimpulan hukum kategoris, dan dokumen ini tidak menetapkannya.
   Yang dapat dinyatakan di sini hanya: ada risiko/kewajiban yang perlu
   keputusan eksplisit sebelum `depends` ditambahkan. Alternatif tanpa
   dependensi (membaca tabel lewat SQL/reflection) **ditolak** karena rapuh dan
   menyembunyikan kontrak.

**Bila pin ditolak:** `FIN36` turun ke status BLOCKED dengan ADR pengganti,
bukan ditandai N/A dan bukan diisi angka rekaan.

### ADR-I2c-02 — FIN37 custom, jadwal dari metadata `start_date`/`end_date`

**Keputusan:** jadwal accrual/prepayment/deferred dibangun sebagai
**rekonstruksi baca-saja** dari AML posted pada akun beban dibayar dimuka /
akrual. Periode jasa **tidak** disimpulkan dari tanggal dokumen; periode diambil
dari field metadata jadwal yang eksplisit.

**Sumber metadata jadwal (berjenjang, fail-closed):**

1. **Sumber utama — `account_invoice_start_end_dates`**
   (`OCA/account-closing` @ `8ce0077fd0762d49e928ea7520555341d7936a9e`,
   versi `19.0.1.0.0`, LGPL-3, depends `account`). Modul ini menambahkan field
   `start_date` dan `end_date` (`fields.Date(index=True)`) langsung pada
   `account.move.line`, plus `must_have_dates` related ke
   `product_id.must_have_dates`. Modul juga memasang `@api.constrains` pada
   `start_date`/`end_date` yang menolak tanggal tidak lengkap, tanggal mulai
   setelah tanggal akhir, dan kombinasi tidak valid. Jadi pasangan tanggal itu
   adalah metadata otoritatif pada level baris, bukan turunan tanggal dokumen.
2. **Tidak ada fallback alokasi.** Bila baris tidak memiliki `start_date` dan
   `end_date` yang valid, baris tersebut **hanya** menjadi exception bernominal
   `missing_schedule_metadata`. Laporan **tidak** mengalokasikan periode untuk
   baris itu dengan asumsi apa pun (bukan 12 bulan, bukan pro-rata, bukan
   tanggal dokumen).
3. **Tidak ada fallback ketiga.** Tanggal dokumen (`date`) atau `date_maturity`
   **tidak** boleh dipakai sebagai pengganti periode jasa.

**Klarifikasi atas inkonsistensi sebelumnya.** Versi ADR sebelumnya menyebut
"parameter jadwal yang disetujui" sebagai fallback, yang ambigu karena dapat
dibaca sebagai alokasi buatan. Keputusan final: **parameter jadwal tidak
menghasilkan alokasi pada FIN37.** Semua baris tanpa metadata tanggal menjadi
exception bernominal, titik. Parameter kontrak bertanggal hanya dipakai pada
`FIN55` (amortization pinjaman/sewa), bukan pada FIN37.

**Konsekuensi dependensi:** opsi 1 memerlukan pin `account-closing` +
`account_invoice_start_end_dates`. Modulnya LGPL-3 (bukan AGPL-3), sehingga
risiko lisensinya berbeda dari ADR-I2c-01; tetap dicatat sebagai keputusan
pemilik. Bila pin ditolak, FIN37 tetap berjalan dengan **seluruh** baris
menjadi exception `missing_schedule_metadata` — laporan tetap jujur dan tidak
mengarang jadwal, tetapi nilai kegunaannya turun dan itu harus dinyatakan
sebagai keterbatasan, bukan ditutupi.

**Alasan:** `account_cutoff_base` tidak tersedia pada pin mana pun yang diaudit,
sehingga tidak ada mesin cutoff yang bisa dibaca; `account_invoice_start_end_dates`
adalah sumber metadata periode yang benar-benar ada pada tree 19.0.

**Batas yang harus dijaga:**

- Setiap baris pengakuan harus berasal dari AML posted; modul tidak boleh
  membuat jurnal sendiri (menghindari double posting).
- Total pengakuan periode + saldo tersisa = saldo akun kontrol.
- Baris tanpa `start_date`/`end_date` wajib muncul sebagai exception bernominal
  di output, bukan dibuang diam-diam.
- Distribusi pengakuan per periode harus deterministik dari rentang tanggal
  (termasuk pembulatan hari terakhir) dan tidak memakai pro-rata omzet.

### ADR-I2c-03 — FIN38 custom, dari `amount_currency` vs `balance`, dengan realized dari partial reconcile

**Keputusan:** unrealized dan realized FX dihitung dari dua sumber berbeda yang
tidak boleh dijumlahkan menjadi satu angka.

**Sumber dan identitas:**

1. **Unrealized** — berasal **hanya dari posisi terbuka**. Untuk setiap AML
   posted pada akun moneter non-fungsional, sisa valuta asing dihitung dari
   `amount_residual_currency` dan sisa fungsional dari `amount_residual`.
   Selisih revaluasi = `amount_residual_currency × kurs_as_of − amount_residual`.
   Baris yang sudah residual nol tidak menyumbang unrealized.

2. **Realized** — berasal **hanya dari `account.partial.reconcile`** yang sudah
   terjadi, memakai field native `debit_move_id`, `credit_move_id`, `amount`,
   `debit_amount_currency`, `credit_amount_currency`, `max_date`, dan
   `exchange_move_id` (semua terverifikasi ada pada `account.partial.reconcile`
   di `odoo/odoo` 19.0).

**Formula operasional per partial.**

Untuk setiap `p` pada `account.partial.reconcile` dengan `p.max_date <= as_of`,
dengan `debit_leg = p.debit_move_id` dan `credit_leg = p.credit_move_id`:

```
# Kurs efektif yang melekat pada tiap kaki (mata uang fungsional per 1 unit valuta).
rate_debit  = debit_leg.balance  / debit_leg.amount_currency
rate_credit = credit_leg.balance / credit_leg.amount_currency

# Nilai fungsional valuta yang dilepas, menurut kurs baris masing-masing.
# debit_amount_currency > 0 dan credit_amount_currency < 0 pada partial normal,
# sehingga nilai kredit dikembalikan ke magnitudo positif.
functional_debit  = p.debit_amount_currency  * rate_debit
functional_credit = -p.credit_amount_currency * rate_credit

realized_partial = functional_debit - functional_credit
```

**Mengapa bukan `amount − amount`.** `p.amount` selalu dalam mata uang
perusahaan dan selalu positif, sehingga kedua kaki melepas carrying fungsional
yang sama besar — memakai `p.amount` di kedua sisi akan selalu menghasilkan nol.
Selisih kurs lahir dari **perbedaan kurs** yang melekat pada tiap baris, dan
itulah yang dihitung formula di atas. Kesetaraan dengan inti Odoo: Odoo
menghitung `debit_exchange_amount = partial_debit_amount − partial_amount` pada
`_prepare_reconcile_vals`, yaitu `−realized_partial` pada konvensi tanda di sini
(Odoo menghitung koreksi yang harus diposting ke kaki debit).

**Sign convention.** `realized_partial > 0` = **kerugian** (loss): nilai
fungsional yang dilepas lebih besar dari yang diterima. `realized_partial < 0` =
**keuntungan** (gain). Tanda konsisten dengan `_get_exchange_account()` pada inti
Odoo, yang memilih `expense_currency_exchange_account_id` bila `amount > 0` dan
`income_currency_exchange_account_id` bila `amount <= 0`.

**Contoh numerik (wajib menjadi test case):**

| Kasus | Faktur | Pembayaran | `realized_partial` | Arti |
|---|---|---:|---:|---|
| A | 100 USD @ 15.000 → 1.500.000 | 100 USD @ 16.000 → 1.600.000 | **−100.000** | Gain 100.000 |
| B | 100 USD @ 16.000 → 1.600.000 | 100 USD @ 15.000 → 1.500.000 | **+100.000** | Loss 100.000 |
| C | 100 USD @ 15.000, bayar 40 USD @ 16.000 | partial 40 | **−40.000** | Gain parsial |
| D | 100.000 IDR (mata uang fungsional) | 100.000 IDR | **0** | Tanpa FX |

**Perlakuan kasus khusus (semua wajib diuji):**

| Kasus | Perlakuan |
|---|---|
| **Partial settlement sebelum full reconcile** | Dihitung per partial (`p.max_date <= as_of`); tidak menunggu `full_reconcile_id`. Realized dapat muncul walau baris belum lunas. |
| **Multi-partial** | Dijumlahkan per partial (`Σ realized_partial`), bukan dihitung dari selisih saldo agregat. Untuk tiap baris: `Σ |p.amount| ≤ |balance|`; bila terlampaui, seluruh baris menjadi exception `over_reconciled`, bukan dipotong diam-diam. |
| **Write-off** | Baris write-off tidak punya pasangan `amount_currency` yang setara. Diperlakukan sebagai pengurangan carrying **tanpa** realized FX, dilaporkan terpisah sebagai `write_off` agar tidak menciptakan gain/loss palsu. |
| **Reversal** | Partial pada move yang di-reverse diidentifikasi lewat `reversed_entry_id`/`reversal_move_ids`. Pasangan partial yang saling membatalkan di-net ke nol **per pasangan** lebih dulu; realized baru dijumlahkan setelah netting. |
| **Tanpa `exchange_move_id`** | Tetap dihitung dari formula. `exchange_move_id` adalah **bukti posting**, bukan syarat perhitungan. Selisih antara nilai formula dan jurnal exchange (bila ada) menjadi exception bernominal. |
| **Kaki mata uang fungsional** | `amount_currency == balance`, sehingga `rate = 1`; kontribusinya nol dan tidak menciptakan selisih. Tidak dikecualikan dari loop. |
| **`amount_currency == 0` pada kaki non-fungsional** | Data tidak lengkap; baris menjadi exception `missing_currency_amount`, formula tidak dijalankan untuk partial itu. |

**Tie-out wajib.** Untuk setiap pasangan (akun, mata uang):

```
Σ realized_partial   (dari partial yang exchange_move_id-nya terisi)
  ==  Σ -balance pada baris akun exchange gain/loss milik exchange_move_id tersebut
```

Tie-out memakai **negatif** `balance` karena jurnal exchange diposting dari sudut
pandang kaki aset/liabilitas: koreksi yang mengurangi carrying aset muncul
sebagai lawan pada akun gain/loss. Rumus tanda ini yang wajib diuji, dan
selisihnya **wajib nol**; bila tidak nol, laporan gagal (bukan disapu ke
rounding).

Untuk partial **tanpa** `exchange_move_id` (belum/never fully reconciled), tidak
ada jurnal pembanding; nilai formula dilaporkan sebagai
`realized_unposted_evidence` yang terpisah dan **tidak** masuk tie-out. Dengan
begitu tie-out hanya membandingkan hal yang memang punya bukti posting.

Akun `income_currency_exchange_account_id` dan
`expense_currency_exchange_account_id` **dikecualikan dari basis** unrealized
agar tidak double count dengan realized.

**Alasan:** `account_multicurrency_revaluation` tidak ada pada pin; tidak ada
sumber OCA yang bisa direkonsiliasi. Formula di atas diturunkan dari perilaku
nyata `_prepare_exchange_difference_move_vals()` dan
`_get_exchange_account()` pada `odoo/odoo` 19.0, sehingga dapat diuji ulang
terhadap jurnal yang benar-benar diposting Odoo.

**Bukti eksekusi formula:** `tests/test_finance_i2c_adr_formulas.py` mengunci
aritmetika di atas (test case A–D, multi-partial, mata uang fungsional, alokasi
jadwal, dan penolakan rentang terbalik). Jalankan
`python -m unittest tests.test_finance_i2c_adr_formulas -v`; 11 tes harus lulus.
Tanpa test ini, formula ADR hanya prosa dan tidak boleh dianggap kontrak.

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
| `FIN37` | pengakuan periode + saldo tersisa = saldo akun kontrol; setiap baris memakai `account.move.line.start_date`/`end_date`; baris tanpa metadata muncul sebagai `missing_schedule_metadata` bernominal dan **tidak** dialokasikan; tidak ada jurnal buatan modul |
| `FIN38` | unrealized hanya dari `amount_residual_currency` posisi terbuka; realized per partial dari `debit_amount_currency × rate_debit − credit_amount_currency × rate_credit`; test case A–D (gain 100.000, loss 100.000, gain parsial 40.000, nol) wajib cocok; tie-out `Σ realized == Σ −balance` pada akun exchange gain/loss untuk partial ber-`exchange_move_id`; selisih ≠ 0 = gagal |
| `FIN55` | `opening + drawdowns + interest − payments = closing`; tie-out ke akun liabilitas |
| `FIN56` | total slip disetujui = beban GL terkait; pembayaran/utang pajak terpisah; exception bernominal |

Counterexample wajib: mutasi seimbang (tamper) ditolak, rollback savepoint
memulihkan baseline, role tanpa hak accounting ditolak, dan perusahaan lain
ditolak.

## Rencana pemecahan PR

| Urutan | Isi | Gate |
|---|---|---|
| 1 (dokumen ini) | Discovery + ADR | Review pemilik; belum ada kode |
| 2 | Pin `account_asset_management` + spike install/upgrade + penilaian lisensi | CI profile hijau, ADR-I2c-01 disetujui |
| 3 | `FIN37` + `FIN38` custom (paling sedikit dependensi eksternal) | Oracle native + unit; FIN37 perlu keputusan pin `account-closing` atau berjalan dengan exception |
| 4 | `FIN55` custom | Oracle native + kebijakan bertanggal |
| 5 | `FIN36` membaca OCA | Oracle native + coverage aset |
| 6 | `FIN56` bridge payroll/expense | Profil CI dengan `hr_expense`+`payroll` pada DB runner |

Urutan 3–6 dapat ditukar; urutan 2 harus lebih dulu bila `FIN36` ingin memakai
OCA. Setiap PR tetap wajib CI hijau exact SHA dan tidak menandai katalog
`ACCEPTED`.

## Gate yang masih terbuka

- [BU] Penilaian lisensi AGPL-3 untuk `account_asset_management` (ADR-I2c-01)
  dan pin `account_invoice_start_end_dates` LGPL-3 untuk FIN37, keduanya oleh
  pemilik repo atau penasihat hukum.
- [BU] Spike install/upgrade `account_asset_management` pada DB disposable.
- [BU] Profil CI yang memasang `hr_expense` dan `payroll` pada
  `finance_i0_reports_disposable`.
- [BU] Sign-off Finance Controller atas parameter kontrak `FIN55` dan definisi
  "slip disetujui" pada `FIN56`.
- [F] `REPORT_CATALOG.csv` `FIN05`–`FIN09` masih `BELUM_DITERIMA`; gate export
  XLSX/PDF, browser geometry, volume/performance `I8`, dan sign-off Finance
  Controller untuk I2b tetap pekerjaan terpisah.
