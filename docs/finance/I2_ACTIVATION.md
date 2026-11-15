# I2-3 — Blok aktivasi laporan keuangan di database demo

Status: **diekskusi pada database demo production (Railway) pada deploy
`main` `50866b8`; bukti read-only di bawah.** Branch asal:
`Opencode-finance-i2-3-activation` dari `main` `99ad910`; merge `50866b8`.
Keputusan pemilik: modul + admin demo sebagai Finance Reader.

## Masalah yang diselesaikan

Paket I2 membuat wizard laporan, ACL dan menu **Finance Reports**, tetapi tidak
pernah dipasang di database demo. `INIT_MODULES` sengaja tidak memuat
`id_finance_*`, dan `group_finance_reader` tidak diberikan otomatis kepada
siapa pun. Tanpa blok aktivasi, menu tetap tidak terlihat walaupun modul sudah
ada di image.

## Yang ditambahkan

Dua blok bermark di `deploy/init.sh`, masing-masing idempoten dan hanya berjalan
sekali per database:

| Mark | Isi | Sifat |
|---|---|---|
| `activate_finance_reports_v1` | `odoo -i id_finance_reporting,id_finance_foundation --stop-after-init` | gagal → mark tidak diset, boot berhenti |
| `demo_finance_reader_v1` | berikan `id_finance_foundation.group_finance_reader` kepada `base.user_admin` | hanya admin demo; user dan grup lain tidak diubah |

Blok diletakkan setelah `upgrade_modules_v3` dan
`install_account_financial_report_v1` (prasyarat `account_financial_report`
dan `stock_account`), sebelum seed dan postinit.

## Batas yang dijaga

- **Tidak** mengubah `INIT_MODULES`, chart of accounts, metode costing,
  valuasi, seed, atau data transaksi.
- **Tidak** memakai `RESET_DB`, tidak menghapus mark, tidak menjalankan
  migrasi data.
- **Tidak** mengaktifkan bahasa `id_ID`; UI lain tidak berubah.
- Grup Finance Reader hanya untuk `base.user_admin`; pengguna demo lain tetap
  tidak melihat menu tersebut.
- Instalasi yang gagal menghentikan boot (fail-closed) supaya aplikasi tidak
  berjalan dengan menu setengah terpasang; mark tidak diset sehingga boot
  berikutnya mengulang.

## Urutan deploy (wajib)

1. PR I2-2 (`id_finance_reporting` 19.0.1.5.0, export XLSX) **merge lebih
   dulu**. Blok ini memakai `-i`, jadi versi yang terpasang adalah versi yang
   ada di image saat deploy pertama.
2. PR I2-3 (dokumen ini) merge.
3. Deploy `main` oleh agen deploy/pemilik. Log harus memuat
   `activate_finance_reports_v1: memasang` dan `demo_finance_reader_v1:
   memberikan` tepat satu kali, lalu pada restart berikutnya
   `sudah ada; lewati`.
4. Jika DB demo **sudah** terpasang versi modul lebih lama, jangan mengubah
   blok ini; buat blok upgrade bertanda baru
   (`upgrade_finance_reports_v2`) sesuai pola `upgrade_modules_v3`.

## Bukti yang dijalankan

CI job `init-test` (`ci.yml`) menjalankan `deploy/init.sh` pada DB kosong,
restart, lalu memeriksa:

- log boot pertama memuat kedua penanda, dan log gabungan memuat masing-masing
  **tepat satu kali** (blok tidak berjalan ulang saat restart);
- `ir_module_module` mencatat `id_finance_reporting` dan
  `id_finance_foundation` berstatus `installed`;
- `scripts/ops/verify_finance_activation_demo.py` (dijalankan via
  `odoo shell`, read-only) memastikan admin demo memiliki grup Finance Reader,
  grup itu masih meng-*implikasi* `account.group_account_readonly`, menu
  **Finance Reports** dibatasi ke grup reader, menu laporan custom menunjuk
  action yang benar, dan tidak ada user lain yang mendapat grup tersebut.

**Status: PASS pada exact-SHA `038d42f`, 12/12 check PR hijau.**

- `init-test` (run `43570682742`, job `132374227786`), langkah
  *Aktivasi finance bertanda dan idempoten*:
  `INIT_FINANCE_ACTIVATION=PASS` dengan
  `{"admin": "admin", "menu": "Finance/Finance Reports", "modules":
  {"id_finance_foundation": "installed", "id_finance_reporting": "installed"},
  "other_reader_users": [], "reader_group": "Finance Reader",
  "report_menu_action": "Journal Items Audit Trail (FIN04)"}`.
- `Kontrak Runner Upgrade (unit)` dan
  *Module Upgrade from Persisted Baseline + Replay Zero Drift*
  (run `43570682677`, job `132374214936`, 18m38s) PASS dengan
  `UPGRADE_BASELINE_PHASE=SUCCESS`, `UPGRADE_VERIFY_PHASE=SUCCESS`, dan
  `UPGRADE_REPLAY_ZERO_DRIFT=PASS` — blok aktivasi ikut berjalan pada boot
  `fmcg_base` (DB kosong) tanpa merusak baseline persisten atau replay.
- `deploy/init.sh` ditambahkan ke path trigger `upgrade-runtime.yml`, supaya
  perubahan jalur boot tidak lolos tanpa bukti zero-drift.


## Status produksi (bukti read-only, 2026-11-15)

Diperiksa dari Railway (project `pleasant-caring`, environment `production`,
service `odooca-fmcg`, database demo) tanpa mengubah apa pun:

- [F] Deploy `50866b8` (merge PR #133) berjalan `SUCCESS`; log boot
  `2026-11-14T12:03:09Z` memuat
  `[init] activate_finance_reports_v1: memasang id_finance_reporting dan id_finance_foundation...`
  dan `2026-11-14T12:03:25Z`
  `[init] demo_finance_reader_v1: memberikan peran Finance Reader kepada admin demo...`,
  ditutup `2026-11-14T12:03:27Z`
  `[init] demo_finance_reader_v1: admin memiliki grup Finance Reader`.
- [F] `odoo.modules.loading` mencatat
  `Loading module id_finance_foundation (126/126)` pada
  `2026-11-14T12:03:20Z`, jadi instalasi benar-benar terjadi pada boot itu.
- [F] Deploy berikutnya `16f686a` (merge PR #136) juga `SUCCESS` dan **tidak**
  memuat baris aktivasi lagi — mark bekerja, blok tidak diulang. Registry
  `loaded in 1.295s` pada `2026-11-14T12:50:51Z`.
- [F] `https://odooca-fmcg-demo.up.railway.app/web/login` menjawab HTTP `200`
  pada pemeriksaan 2026-11-15, dan cron (`QRIS Fetch Status`, `Mail: Email
  Queue Manager`) berjalan normal.
- [A] Versi modul yang terpasang adalah `19.0.1.5.1` karena image `50866b8`
  memuat manifest tersebut; angka `latest_version` di `ir_module_module` belum
  dibaca langsung.
- [BU] Login sebagai admin demo lalu membuka **Finance → Finance Reports**,
  menjalankan satu laporan, dan mengunduh XLSX di production belum dilakukan.
- Catatan kebisingan log: `_()` pada level modul memicu
  `no translation language detected, skipping translation` beserta stack
  pada setiap boot. Itu peringatan, bukan kegagalan; kandidat pembersihan
  berikutnya.

## Rollback

Tidak ada rollback otomatis. Untuk menghentikan aktivasi, pemilik/agen deploy
membuat blok bermark baru yang menonaktifkan menu atau melepas grup; mark yang
sudah ada dan entri log agen tidak boleh dihapus manual. Modul tidak dilepas
dari DB demo tanpa keputusan pemilik, karena pencopotan modul menyentuh data
akuntansi.

## Yang belum dibuktikan

- [BU] Login sebagai admin demo di production, membuka menu **Finance
  Reports**, menjalankan laporan, dan mengunduh XLSX; pemeriksaan DB langsung
  (`ir_module_module.latest_version`, keanggotaan grup) juga belum.
- [BU] Geometri browser desktop/tablet; tie-out angka per report ID;
  sign-off Finance Controller + QA.
- [BU] Export PDF atau padanan terdokumentasi (XLSX sudah dibuktikan di
  `docs/finance/I2_XLSX_EXPORT.md`).
- [BU] `finance_activation.attest` tetap manual/operator; profil
  `finance_reports_v1` tidak dipanggil oleh `init.sh`.

`docs/finance/REPORT_CATALOG.csv` tidak diubah oleh paket ini; seluruh 58 ID
tetap `BELUM_DITERIMA`.
