# I0 — paket ledger native dan keamanan laporan

Basis: main `3a96a493c9ae4a4dff0cbba67a8d7e71e754b7ad`, merge PR90.
Branch `agen/finance-i0-ledger-security`. Menindaklanjuti permintaan pemilik agar
PR berisi paket pekerjaan lebih utuh, bukan satu skenario kecil.

## Cakupan satu PR

1. Isolasi Trial Balance OCA tanpa account_ids/journal_ids, dua company sama-sama
   readable; account universe dan angka eksplisit wajib tepat per company.
2. Periode kosong sebelum opening; tidak menyamakan source tak terbaca dengan nol.
3. Native Finance Reader: report positif, penolakan create/write, foreign AML dan
   company palsu. Accountant dengan dua company: pergantian scope positif.
4. Native Sales dan mobile evidence/driver: report dan posting ditolak, tanpa sudo.
   Tidak ada grup `group_mobile_driver`; driver memakai grup backend existing
   `id_mobile_api.group_mobile_evidence`, bukan nama grup rekaan atau fallback lemah.
5. Global record-rule menghilangkan akun cash: oracle angka harus menolak, rollback,
   lalu baseline kembali lulus. Ini membuktikan evaluator cakupan, bukan kemampuan
   bawaan OCA mendeteksi semua record-rule-incomplete source otomatis.
6. Dua company native tambahan (nominal 1× dan 7×): customer invoice/refund,
   vendor bill/refund, `account.payment.action_post()` dan partial reconciliation
   native; settlement bulan berikut; ledger OCA harus cocok angka eksplisit.
7. Rekonstruksi residual Juli dari AML + tanggal partial allocation sesudah
   settlement Agustus, bukan membaca residual saat ini dan melabelinya historis.
8. Unreconcile mengubah residual, bukan nilai GL; rollback wajib memulihkan full
   settlement. Partner diarsipkan tidak boleh menghapus saldo historis.

## Angka kontrol native (company C; D = 7×)

Fixture tanpa pajak: service line tanpa produk/stok, tax_ids kosong secara eksplisit.
Tidak ada angka fixture yang menjadi ketentuan pajak bisnis atau filing resmi.

- Opening 30 Juni: cash100 / equity100.
- Juli: invoice100; customer refund20; receipt60. AR net20, revenue net80.
- Juli: bill80; vendor refund10; pembayaran30. AP net40, expense net70.
- Closing Juli: cash130, AR20, AP-40, revenue-80, expense70, equity-100.
- Agustus: receipt20 dan pembayaran40; cash110, AR/AP0; revenue/expense/equity sama.

Expected per akun untuk opening/debit/credit/closing ditulis eksplisit dalam runner
sebelum pemanggilan report. Invoice asli, credit notes dan payments memiliki AML
posted; rekonsiliasi memakai `.reconcile()`, bukan memaksa flag residual/reconciled.
Payment memakai cash account eksplisit sehingga fixture tidak mengklaim bank match
atau money-in-transit production. Credit-note lifecycle koreksi resmi belum diuji.

## Eksekusi dan bukti

Addon baru **`id_finance_reporting`** (19.0.1.0.0, LGPL-3) menjadi boundary
server-side Trial Balance: hanya accounting readonly/user/manager; company wajib
eksplisit, aktif dalam context, dan milik user. Guard dipasang sebelum `_get_data`
dan `_get_report_values`, tanpa sudo atau duplikasi algoritma OCA. Sumber OCA
wizard ACL pada pin proyek memberi CRUD kepada base.group_user; sumber sale
memberi salesman read account/AML, sehingga wizard/menu bukan boundary cukup.
XLSX OCA memanggil report `_get_report_values` yang sama; render-data negatives
diuji, tetapi artifact XLSX/PDF end-to-end belum menjadi klaim paket ini.
Tidak mengubah akses AML native milik Sales; hanya report Trial Balance yang
dibatasi. Report OCA lain memerlukan gate terpisah sebelum aktivasi.

Runner `scripts/ops/verify_finance_ledger_security.py` hanya menerima
`finance_i0_reports_disposable`. Profil reports memasang id_mobile_api agar grup
driver/evidence asli tersedia. CI menjalankan lima profil, golden minimal PR90,
lalu paket extended ini. Wajib sentinel `FINANCE_LEDGER_SECURITY=PASS` dan JSON
per skenario. Artifact `finance-i0-candidate-evidence/ledger-security.log`.
Semua company/user/dokumen hanya fixture CI dan di-rollback; company/user sets
sebelum/sesudah wajib identik. Tidak ada commit atau DB demo yang disentuh.

Lokal: tes konsistensi angka, residual cutoff, database guard, Ruff/manifest/YAML.
Runtime Odoo/PostgreSQL nyata wajib dibuktikan CI exact HEAD, bukan tes lokal saja.

## Batas penerimaan

Belum menutup FIN01–58, I0 keseluruhan atau FIN02 penuh. Scope tidak mencakup
UI/export/PDF/XLSX, endpoint HTTP/RPC actor sessions, timing volume, FX/year-close,
as-of report open-items OCA, effective FIFO/valuation ownership/HPP, mapped COA demo,
atau official tax acceptance. Company tambahan tidak dibuat pada database demo.
Perilaku yang gagal di CI tetap HOLD dan harus diperbaiki tanpa melonggarkan oracle.
