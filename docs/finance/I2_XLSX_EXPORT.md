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
| `addons/id_finance_reporting/i18n/id.po` | 27 entri baru (20 paket awal + 7 koreksi P2) |

Versi modul: `19.0.1.5.1`.

## Bentuk workbook

- **Summary** — report ID dan nama, nama berkas, company, currency, periode,
  filter, waktu dan pembuat, daftar bagian beserta jumlah baris/kolom/sel
  bersarang, dan catatan batas.
- **Satu sheet per bagian** snapshot (kunci `rows`, `documents`, `totals`,
  dst.). Daftar berisi objek menjadi tabel dengan header kolom skalar; daftar
  skalar menjadi satu kolom `value`; objek menjadi pasangan `key`/`value`.
- Nama sheet disanitasi terhadap `[]:*?/\`, dipotong 31 karakter, dan diberi
  akhiran bila bentrok.
- Angka ditulis sebagai sel numerik dengan nilai persis dari layanan laporan.
  Tidak ada format tampilan yang membulatkan, karena laju kurs juga diekspor.
- Header dibekukan dan autofilter dipasang pada tabel.

## Kontrak kelengkapan

Koreksi P2 (review #5902486524) menghapus janji bahwa data bersarang "tersedia
di payload JSON": payload dibatasi 200.000 karakter, sehingga janji itu bisa
menunjuk ke data yang sudah hilang. Sekarang:

- **Kolom `__nested`.** Setiap baris yang punya nilai bersarang (daftar/objek),
  atau kolom skalar di atas batas 40 kolom, menulis sisanya sebagai satu sel
  JSON di kolom `__nested` pada sheet yang sama. Bagian yang seluruh barisnya
  bersarang memakai `__nested` sebagai satu-satunya kolom. Workbook tetap
  lengkap di bawah batas baris tanpa bergantung pada payload.
- **Sel di atas 32.000 karakter** dipotong di dalam sel dengan penanda
  `... (truncated)`, dan **Summary** menyebut bagian, jumlah sel, serta jumlah
  sel bersarang yang terdampak. Tidak ada pemotongan tanpa jejak.
- **Payload JSON selalu valid.** Bila snapshot melebihi 200.000 karakter,
  payload tidak lagi dipotong mentah. Bagian utuh dimasukkan selama muat,
  lalu objek `__truncation__` menyebut `included_sections`,
  `omitted_sections`, dan batasnya. Bagian yang dihilangkan dari payload tetap
  punya sheet lengkap di workbook.
- **Summary** menyatakan ketiga hal di atas, bukan lagi mengarahkan pembaca ke
  payload.

## Guard formula injection

Teks selalu ditulis dengan `write_string`, jadi Excel menyimpannya sebagai
string dan tidak mengevaluasinya. Lapisan kedua: nilai yang diawali `=`, `+`,
`-`, `@`, tab, atau carriage return diberi awalan apostrof
(`'=SUM(1+1)`). Kedua lapisan diperlukan karena ekspor ulang CSV/TSV atau
importer yang mem-parse teks bisa mempromosikan data menjadi formula.

Tambahan pertahanan:

- karakter kontrol yang tidak sah untuk XML (`\x00`–`\x08`, `\x0b`, `\x0c`,
  `\x0e`–`\x1f`) dibuang sebelum ditulis;
- teks dibatasi 32.000 karakter (batas sel Excel) dengan penanda pemotongan di
  dalam sel dan hitungan per bagian di **Summary**;
- baris **tidak** dipotong diam-diam. Bagian dengan lebih dari 20.000 baris
  ditolak dengan `UserError` yang menyebut nama bagian dan jumlah baris;
- kolom skalar di atas 40 tidak menjadi kolom sendiri, nilainya tetap ada di
  `__nested` dan namanya disebut di **Summary**;
- payload JSON di atas 200.000 karakter tetap valid dan menyebut bagian yang
  dihilangkan; datanya ada di workbook;
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
**Status: PASS pada CI exact-SHA `fe26a28`, run `43584001640`, job
`132414505091` (langkah `I2 exposure`, PASS), dengan kelima workflow PR #131
hijau pada commit yang sama (CI, Upgrade Runtime Verification, Finance I0
candidate spike, Seed supervision, PWA quality).**

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

### Koreksi P2 — regresi kelengkapan

`check_xlsx_completeness` memakai snapshot sintetis berisi 400 baris × ~610
karakter (di atas batas payload 200.000 karakter, jauh di bawah batas 20.000
baris), dengan nilai bersarang di bagian **terakhir** snapshot:

- `xlsx_payload_cap_valid_json` — payload hasil `_payload_json` tetap dapat
  di-parse `json.loads`; `__truncation__` menyebut `rows` sebagai bagian yang
  dihilangkan dan `tail` sebagai bagian yang masih dimuat; snapshot kecil tetap
  identik byte-per-byte.
- `xlsx_nested_completeness` — workbook memuat kolom `__nested`, label dan
  nilai bersarang bagian terakhir (`NESTED-TAIL-MARKER`,
  `NESTED-TAIL-VALUE`), dan **tidak** lagi memuat kalimat "available in the
  JSON payload".
- `xlsx_cell_truncation_disclosed` — sel bersarang di atas 32.000 karakter
  diberi penanda `(truncated)` dan **Summary** menyebut bagian, jumlah sel,
  serta sel bersarang yang terdampak.

`check_wizard_runs` juga mem-parse `result_json` dengan `json.loads` untuk 8/8
jenis laporan, sehingga payload yang tidak valid akan menggagalkan CI.

Keluaran `completeness` yang tercatat pada run di atas:

```
{"case": "xlsx_payload_cap_valid_json", "result": "PASS"}
{"case": "xlsx_nested_completeness", "result": "PASS"}
{"case": "xlsx_cell_truncation_disclosed", "result": "PASS"}
```

Komponen `xlsx` tetap 12 PASS + 1 `ACCESS_DENIED` (penolakan Sales yang
memang diharapkan), `runs` 8/8 PASS, `sanitization` 2/2 PASS, `surface` 9/9
PASS, `roles` 1 izin + 5 penolakan sesuai harapan, dan
`FINANCE_I2_EXPOSURE=PASS`.

## Yang belum dibuktikan (tetap `BELUM_DITERIMA`)

- [BU] XLSX dibuka di Excel/LibreOffice pada desktop dan tablet; pemeriksaan
  saat ini memvalidasi struktur OOXML dan isi sel, bukan tampilan aplikasi.
- [BU] Export pada volume demo (1.324 invoice) dan pengukuran waktu.
- [BU] PDF atau padanan terdokumentasi untuk laporan yang menuntut PDF.
- [BU] Tie-out angka per report ID terhadap oracle independen di database demo.
- [BU] Sign-off Finance Controller + QA.

Catatan batas yang sudah diungkapkan, bukan klaim kelengkapan tanpa syarat:

- satu sel Excel dibatasi 32.000 karakter; sel yang melewatinya dipotong dan
  dihitung per bagian di **Summary**;
- payload JSON dibatasi 200.000 karakter; bagian yang tidak muat disebut di
  `__truncation__`, dan datanya tetap ada di sheet bagian tersebut.

`docs/finance/REPORT_CATALOG.csv` tidak diubah oleh paket ini; seluruh 58 ID
tetap `BELUM_DITERIMA`.
