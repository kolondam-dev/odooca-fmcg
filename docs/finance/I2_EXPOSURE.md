# I2 exposure — wizard, ACL, menu dan bukti peran

Status: **implementasi + bukti disposable; belum penerimaan katalog.**
Branch: `Opencode-finance-i2-exposure`, disinkronkan dengan `main` `488bd87`
(merge `fab0cbc`).

## Masalah yang diselesaikan

Seluruh model laporan I2 (`FIN04`–`FIN09`, `FIN37`, `FIN38`, `FIN51`, `FIN57`)
adalah `AbstractModel` dengan metode `@api.model _snapshot(...)`. Model seperti
ini tidak punya record, tidak punya view, dan tidak bisa dibuka dari menu.
Sebelum paket ini:

- `id_finance_reporting` tidak punya `security/ir.model.access.csv`, `views/`,
  maupun menu — addon terpasang tetapi tidak ada satu pun laporan yang bisa
  diakses pengguna;
- tidak ada cara menjalankan `_snapshot` dari UI tanpa `odoo shell`;
- belum ada bukti bahwa peran non-keuangan ditolak pada lapisan tampilan.

## Yang ditambahkan

| Berkas | Isi |
|---|---|
| `addons/id_finance_reporting/wizards/finance_report_wizard.py` | `TransientModel` `id.finance.report.wizard`: 8 jenis laporan, filter terbatas, dispatch ke `_snapshot`, pratinjau HTML + payload JSON |
| `addons/id_finance_reporting/views/finance_report_wizard_views.xml` | Satu form view + 8 `ir.actions.act_window` (satu per report ID group) |
| `addons/id_finance_reporting/security/ir.model.access.csv` | Baca untuk 12 model abstrak, CRUD wizard, grup `account.group_account_readonly` |
| `addons/id_finance_foundation/views/finance_menu.xml` | Submenu **Finance Reports** berisi 8 entri, grup `group_finance_reader` |
| `scripts/ops/verify_finance_i2_exposure.py` | Bukti CI: wizard berjalan untuk 8 jenis laporan, menu/action/view ada, Sales/Driver ditolak |
| `.github/workflows/finance-i0-spike.yml` | Langkah `I2 exposure` pada database disposable |

Versi: `id_finance_reporting` `19.0.1.4.0`, `id_finance_foundation`
`19.0.1.1.0`.

## Batas desain yang dijaga

- **Tidak ada posting atau mutasi.** Wizard hanya membaca `account.move.line`
  posted/draft sesuai filter dan merekonstruksi hasil di memori.
- **Scope tetap di server.** Setiap `_snapshot` memanggil `_check_scope`, yang
  memakai `_check_finance_scope` OCA (grup akuntansi + company aktif). ACL
  hanya lapisan pertama; peran Sales/Driver juga ditolak saat memanggil
  service secara langsung.
- **Payload dibatasi.** Tabel pratinjau maksimum 300 baris/24 kolom, sel
  dipotong 200 karakter, JSON dipotong 200.000 karakter. Pemotongan
  ditampilkan, bukan disamarkan sebagai angka penuh.
- **Semua teks di-escape.** Pratinjau memakai `html.escape`; tidak ada HTML
  dari data pengguna yang dirender mentah.
- **Markup disanitasi di server.** `result_html` memakai `sanitize=True`.
  `readonly=True` hanya mengunci widget, sementara grup Accounting Readonly
  punya create/write pada model transient ini; tanpa sanitasi, penulisan
  langsung lewat ORM bisa menyimpan `<script>`/`onerror`. Tag laporan
  (`div`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `p`, `pre`) tetap
  diizinkan sehingga tabel tidak hilang.
- **Tanpa data rekaan.** Laporan yang sumbernya kosong menampilkan "No rows.",
  bukan nol atau angka pengganti.

## Bukti yang dijalankan

`scripts/ops/verify_finance_i2_exposure.py` pada
`finance_i0_reports_disposable`. **Status: PASS pada CI exact-SHA
`fab0cbca13c1c120b2dddbdf6ed41a5a28af8319`** (setelah sinkronisasi `main`),
run `43371935122` (langkah `I2 exposure`), dengan seluruh **12/12 check PR
hijau** pada SHA tersebut. Bukti sanitasi pertama kali lulus di SHA ini.

1. 8 jenis laporan dijalankan lewat wizard; `report_id` harus sesuai
   (`FIN04`, `FIN05`, `FIN07`, `FIN08`, `FIN37`, `FIN38`, `FIN51`, `FIN57`),
   HTML tidak kosong, dan JSON valid.
2. Menu `Finance Reports` berada di bawah aplikasi Finance dan dibatasi
   `group_finance_reader`; setiap menu membuka action yang benar.
3. Finance Reader berhasil menjalankan audit trail.
4. Sales dan Driver ditolak pada wizard (ACL) **dan** pada pemanggilan
   `_snapshot` langsung (scope server).
5. Reader tidak bisa membaca company lain.
6. Penulisan HTML langsung lewat ORM oleh Finance Reader tidak menyimpan
   markup aktif, sementara tabel laporan tetap utuh.

Keluaran CI (`FINANCE_I2_EXPOSURE`): 8/8 `wizard_run_*` PASS, 9/9
`menu_action_*` + view PASS, `reader_can_run` PASS, `sales_wizard_denied`,
`sales_service_denied`, `driver_wizard_denied`, `driver_service_denied`,
`reader_foreign_company_denied` semuanya `ACCESS_DENIED`, dan
`fixture_rollback` PASS.

Bukti sanitasi (`sanitization`, review #5886476944) — PASS pada `fab0cbc`:

- `reader_direct_write_sanitized` — Finance Reader menulis `<script>`,
  `onerror`, dan `href="javascript:"` langsung lewat ORM; hasil baca tidak
  memuat ketiganya.
- `reader_preview_keeps_table` — hasil laporan yang sah tetap memuat
  `<table>`, jadi sanitasi tidak memotong tampilan.

Satu kegagalan pada percobaan pertama: `ir.ui.menu.groups_id` sudah berganti
nama menjadi `group_ids` di Odoo 19; skrip diperbaiki (`34452fe`) dan run
ulang hijau. Langkah install/upgrade wizard tidak pernah gagal.

Fixture (company, akun, partner, user) dibuat di dalam savepoint dan
di-rollback; skrip memeriksa tidak ada kebocoran company/user.

## Yang belum dibuktikan (tetap `BELUM_DITERIMA`)

- [BU] Export XLSX/PDF dan guard formula injection.
- [BU] Geometri browser desktop/tablet dan uji visual.
- [BU] Tie-out angka per report ID terhadap oracle independen di database demo
  (oracle angka sudah ada di paket I2a/I2b/I2c, tetapi bukan penerimaan UI).
- [BU] Aktivasi `id_finance_foundation` di database demo; prasyarat CI
  disposable sudah hijau pada `fab0cbc`, aktivasi belum dijalankan.
- [BU] Sign-off Finance Controller + QA per report ID.
- [BU] Layar native list/pivot; saat ini pratinjau form + JSON.

`docs/finance/REPORT_CATALOG.csv` **tidak diubah** oleh paket ini. Semua 58 ID
tetap `BELUM_DITERIMA`.

## Urutan lanjutan

1. PR I2-2: export XLSX untuk 5 model custom + guard formula injection.
2. PR I2-3: blok aktivasi `id_finance_foundation` bertanda versi di
   `deploy/init.sh`, idempoten, tanpa `RESET_DB`.
3. PR I2-4: tie-out + browser + matriks bukti per report ID.
4. Setelah itu I3 (HPP/valuasi) memakai jalur menu yang sama.
