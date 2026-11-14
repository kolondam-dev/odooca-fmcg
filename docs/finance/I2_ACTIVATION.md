# I2-3 — Blok aktivasi laporan keuangan di database demo

Status: **staged di `deploy/init.sh`; belum dieksekusi pada database demo.**
Branch: `Opencode-finance-i2-3-activation` dari `main` `99ad910`.
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

Status: **[BU] menunggu run CI pada PR ini**; hasil exact-SHA ditempel di PR
dan di `docs/HANDOFF.md` setelah selesai.

## Rollback

Tidak ada rollback otomatis. Untuk menghentikan aktivasi, pemilik/agen deploy
membuat blok bermark baru yang menonaktifkan menu atau melepas grup; mark yang
sudah ada dan entri log agen tidak boleh dihapus manual. Modul tidak dilepas
dari DB demo tanpa keputusan pemilik, karena pencopotan modul menyentuh data
akuntansi.

## Yang belum dibuktikan

- [BU] Eksekusi blok pada database demo (Railway) dan pemeriksaan menu dengan
  login admin demo.
- [BU] Geometri browser desktop/tablet; tie-out angka per report ID;
  sign-off Finance Controller + QA.
- [BU] Export PDF atau padanan terdokumentasi (XLSX sudah dibuktikan di
  `docs/finance/I2_XLSX_EXPORT.md`).
- [BU] `finance_activation.attest` tetap manual/operator; profil
  `finance_reports_v1` tidak dipanggil oleh `init.sh`.

`docs/finance/REPORT_CATALOG.csv` tidak diubah oleh paket ini; seluruh 58 ID
tetap `BELUM_DITERIMA`.
