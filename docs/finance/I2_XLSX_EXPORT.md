# I2-2 — Export XLSX wizard laporan

Status: **implementasi + bukti disposable; belum penerimaan katalog.**
Branch: `Opencode-finance-i2-2-xlsx` dari `main` `3c143c6`.

## Masalah yang diselesaikan

Katalog mewajibkan setiap report ID punya `screen; source drilldown;
XLSX/PDF or documented equivalent; frozen close evidence`. Sebelum paket ini
wizard I2 hanya menghasilkan pratinjau HTML dan payload JSON, sehingga butir
XLSX belum terpenuhi dan pengguna tidak bisa membawa angka keluar dari Odoo.

## Yang ditambahkan

| Berkas | Isi |
|---|---|
| `addons/id_finance_reporting/wizards/finance_report_wizard.py` | `action_export_xlsx`: membangun workbook dari snapshot yang sama dengan pratinjau, menyimpan `result_xlsx` + `result_filename`, mengembalikan tautan `/web/content` |
| `addons/id_finance_reporting/views/finance_report_wizard_views.xml` | Tombol **Export XLSX** di footer form |
| `scripts/ops/verify_finance_i2_exposure.py` | `check_xlsx_export`: helper guard, guard level workbook, 8 jenis laporan, pembersihan workbook basi, izin baca/tolak |
| `addons/id_finance_reporting/i18n/id.po` | 20 entri baru |

Versi modul: `19.0.1.5.0`.

## Bentuk workbook

- **Summary** — report ID dan nama, nama berkas, company, currency, periode,
  filter, waktu dan pembuat, daftar bagian beserta jumlah baris/kolom, dan
  catatan batas.
- **Satu sheet per bagian** snapshot (kunci `rows`, `documents`, `totals`,
  dst.). Daftar berisi objek menjadi tabel dengan header kolom skalar; daftar
  skalar menjadi satu kolom `value`; objek menjadi pasangan `key`/`value`.
- Nama sheet disanitasi terhadap `[]:*?/\`, dipotong 31 karakter, dan diberi
  akhiran bila bentrok.
- Angka ditulis sebagai sel numerik dengan nilai persis dari layanan laporan.
  Tidak ada format tampilan yang membulatkan, karena laju kurs juga diekspor.
- Header dibekukan dan autofilter dipasang pada tabel.

## Guard formula injection

Teks selalu ditulis dengan `write_string`, jadi Excel menyimpannya sebagai
string dan tidak mengevaluasinya. Lapisan kedua: nilai yang diawali `=`, `+`,
`-`, `@`, tab, atau carriage return diberi awalan apostrof
(`'=SUM(1+1)`). Kedua lapisan diperlukan karena ekspor ulang CSV/TSV atau
importer yang mem-parse teks bisa mempromosikan data menjadi formula.

Tambahan pertahanan:

- karakter kontrol yang tidak sah untuk XML (`\x00`–`\x08`, `\x0b`, `\x0c`,
  `\x0e`–`\x1f`) dibuang sebelum ditulis;
- teks dibatasi 32.000 karakter (batas sel Excel) dan penanda pemotongan
  ditulis eksplisit;
- baris **tidak** dipotong diam-diam. Bagian dengan lebih dari 20.000 baris
  ditolak dengan `UserError` yang menyebut nama bagian dan jumlah baris;
- kolom skalar di atas 40 dicatat namanya di sheet **Summary** sebagai
  pengecualian, bukan dihilangkan tanpa jejak;
- nilai bersarang di dalam baris (daftar/objek) tetap tersedia di payload JSON
  dan disebutkan di **Summary**;
- menjalankan ulang laporan menghapus workbook lama (`result_xlsx = False`)
  supaya unduhan tidak pernah menyajikan snapshot basi.

## Batas yang dijaga

- Tidak ada posting, mutasi, atau pembuatan jurnal. Workbook dibangun dari
  snapshot read-only yang sama dengan pratinjau.
- Scope server tetap berlaku: `action_export_xlsx` memanggil `_dispatch()` yang
  memanggil `_snapshot`, sehingga pemeriksaan grup akuntansi dan company tidak
  bisa dilewati dengan menekan tombol ekspor.
- Tidak ada dependency Python baru: `xlsxwriter` sudah menjadi requirement
  Odoo 19 (`requirements.txt`).
- PDF belum ada; dokumen ini tidak mengklaim PDF.

## Bukti yang dijalankan

`scripts/ops/verify_finance_i2_exposure.py` pada
`finance_i0_reports_disposable`, langkah CI `I2 exposure`.
**Status: PASS pada CI exact-SHA
`b23cf09` (`b23cf09` pada run `43556711792`, job `132331093982`),
dengan 12/12 check PR hijau.**

Keluaran `FINANCE_I2_EXPOSURE` memuat komponen `xlsx`:

```
{"case": "xlsx_formula_guard_helper", "result": "PASS"}
{"case": "xlsx_formula_guard_workbook", "result": "PASS"}
{"case": "xlsx_export_audit_trail", "result": "PASS"}
{"case": "xlsx_export_partner_ledger", "result": "PASS"}
{"case": "xlsx_export_open_items", "result": "PASS"}
{"case": "xlsx_export_aged_partner_balance", "result": "PASS"}
{"case": "xlsx_export_combined_trial_balance", "result": "PASS"}
{"case": "xlsx_export_sales_purchase_register", "result": "PASS"}
{"case": "xlsx_export_accrual_schedule", "result": "PASS"}
{"case": "xlsx_export_fx_revaluation", "result": "PASS"}
{"case": "xlsx_cleared_on_rerun", "result": "PASS"}
{"case": "reader_can_export_xlsx", "result": "PASS"}
{"case": "sales_export_denied", "result": "ACCESS_DENIED"}
```

Rincian setiap kasus:

- `xlsx_formula_guard_helper` — `=`, `+`, `-`, `@`, tab dan carriage return
  diberi awalan apostrof; teks biasa, nilai kosong, karakter kontrol, dan teks
  40.000 karakter diperiksa.
- `xlsx_formula_guard_workbook` — jurnal fixture dengan `ref =SUM(1+1)` dan
  label `@cmd|' /C calc'!A0`, `-7.5+1` diekspor; berkas adalah ZIP/XLSX valid,
  setiap part XML well-formed, tidak ada elemen `<f>`, ketiga trigger tersimpan
  dengan apostrof, dan `7.5` tersimpan sebagai `<v>7.5</v>` (sel numerik).
- `xlsx_export_<report_type>` — 8/8 jenis laporan menghasilkan workbook dengan
  sheet **Summary**.
- `xlsx_cleared_on_rerun` — menjalankan ulang menghapus workbook lama.
- `reader_can_export_xlsx` — Finance Reader bisa mengekspor.
- `sales_export_denied` — Sales ditolak pada pembuatan wizard/ekspor.

## Yang belum dibuktikan (tetap `BELUM_DITERIMA`)

- [BU] XLSX dibuka di Excel/LibreOffice pada desktop dan tablet; pemeriksaan
  saat ini memvalidasi struktur OOXML dan isi sel, bukan tampilan aplikasi.
- [BU] Export pada volume demo (1.324 invoice) dan pengukuran waktu.
- [BU] PDF atau padanan terdokumentasi untuk laporan yang menuntut PDF.
- [BU] Tie-out angka per report ID terhadap oracle independen di database demo.
- [BU] Sign-off Finance Controller + QA.

`docs/finance/REPORT_CATALOG.csv` tidak diubah oleh paket ini; seluruh 58 ID
tetap `BELUM_DITERIMA`.
