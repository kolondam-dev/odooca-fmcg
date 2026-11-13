# I2 exposure — wizard, ACL, menu dan bukti peran

Status: **implementasi + bukti disposable; belum penerimaan katalog.**
Branch: `Opencode-finance-i2-exposure` dari `main` `4f61086`.

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
- **Tanpa data rekaan.** Laporan yang sumbernya kosong menampilkan "No rows.",
  bukan nol atau angka pengganti.

## Bukti yang dijalankan

`scripts/ops/verify_finance_i2_exposure.py` pada
`finance_i0_reports_disposable`:

1. 8 jenis laporan dijalankan lewat wizard; `report_id` harus sesuai
   (`FIN04`, `FIN05`, `FIN07`, `FIN08`, `FIN37`, `FIN38`, `FIN51`, `FIN57`),
   HTML tidak kosong, dan JSON valid.
2. Menu `Finance Reports` berada di bawah aplikasi Finance dan dibatasi
   `group_finance_reader`; setiap menu membuka action yang benar.
3. Finance Reader berhasil menjalankan audit trail.
4. Sales dan Driver ditolak pada wizard (ACL) **dan** pada pemanggilan
   `_snapshot` langsung (scope server).
5. Reader tidak bisa membaca company lain.

Fixture (company, akun, partner, user) dibuat di dalam savepoint dan
di-rollback; skrip memeriksa tidak ada kebocoran company/user.

## Yang belum dibuktikan (tetap `BELUM_DITERIMA`)

- [BU] Export XLSX/PDF dan guard formula injection.
- [BU] Geometri browser desktop/tablet dan uji visual.
- [BU] Tie-out angka per report ID terhadap oracle independen di database demo
  (oracle angka sudah ada di paket I2a/I2b/I2c, tetapi bukan penerimaan UI).
- [BU] Aktivasi `id_finance_foundation` di database demo (menunggu CI hijau
  pada SHA yang sama).
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
