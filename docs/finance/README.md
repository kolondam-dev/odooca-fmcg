# Finance, Accounting & Tax — gap analysis dan implementation plan

Tanggal analisis: 4 November 2026 (WIB). Baseline: `f65b41a0cdbd7fb0a2d9776410bdf63285ca61e3`.
Status: **rencana implementasi; modul finance belum diaktifkan di demo** kecuali
`account_financial_report` yang disetujui pemilik untuk presentasi (lihat
[demo accounting](DEMO_ACCOUNTING_REPORTS.md)).

Permintaan pemilik: paket lengkap Finance/Accounting/Tax Indonesia dengan OCA dan custom bila dibutuhkan; wajib mencakup HPP, General Ledger, Trial Balance, MIS dan laporan standar lainnya. Kelengkapan diukur melalui katalog dan rekonsiliasi, bukan banyaknya menu atau jumlah addon.

## Paket dokumen

1. [Gap analysis](GAP_ANALYSIS.md): bukti source, celah, severity dan pemilihan OCA/custom.
2. [Katalog laporan wajib](REPORT_CATALOG.csv): daftar terstruktur dengan ID, sumber, iterasi, oracle dan status bukti.
3. [Rencana iterasi](IMPLEMENTATION_PLAN.md): urutan pekerjaan, dependensi, gate dan rollout.
4. [Kontrak penerimaan](ACCEPTANCE_CONTRACT.md): angka kontrol, skenario negatif, keamanan dan bukti siap pakai.
5. [Audit runtime I0 dan containment](I0_RUNTIME_AUDIT.md): hasil implementasi awal,
   keputusan scope demo pemilik, matriks sumber dan gate yang masih terbuka.
6. [Demo accounting: OCA account_financial_report](DEMO_ACCOUNTING_REPORTS.md):
   scope yang disetujui pemilik, menu laporan, data demo, batas verifikasi.
7. [Golden ledger minimal I0](I0_GOLDEN_LEDGER.md): oracle dua company/dua periode
   terhadap Trial Balance OCA aktual dan batas pembuktiannya.
8. [Paket ledger native dan keamanan](I0_LEDGER_SECURITY.md): isolasi tanpa filter,
   role/company negatives, invoice/refund/payment/reconcile dan kontrol historis.
9. [Fondasi I1](I1_FOUNDATION.md), [Paket I2a core ledgers](I2A_LEDGERS_CORE.md),
   dan [Paket I2b AR/AP subledger](I2B_ARAP_SUBLEDGER.md): peran/navigasi
   keuangan, profil aktivasi versioned, oracle native I2a (`FIN01`, `FIN02`,
   `FIN03`, `FIN04`, `FIN51`, `FIN57`), serta partner ledger AR/AP, open items
   as-of, dan aging bertanda (`FIN05`–`FIN09`).
10. [I2 exposure](I2_EXPOSURE.md): wizard laporan, ACL, menu **Finance
    Reports**, dan bukti peran Sales/Driver ditolak. Ini lapisan yang membuat
    model laporan bisa dipakai, bukan penerimaan katalog.
11. [Keputusan pemilik](OWNER_DECISIONS.md) dan [lisensi](LICENSING.md):
    model AGPL-compliant, scope `FIN55`/`FIN56`/payroll, serta batas aktivasi
    demo bertahap.

## Tiga putaran penyusunan rencana

- Putaran 1 — inventarisasi source dan gap: pisahkan repo tersedia, manifest ada, addon aktif, menu terlihat dan proses diterima. Snapshot database lama bukan inventaris live.
- Putaran 2 — perluasan coverage dan oracle: tambahkan laporan standar, penghubung HPP/stok/GL, statements/MIS, tax dan konsolidasi; setiap laporan harus punya ID dan oracle.
- Putaran 3 — uji kelayakan urutan: pecah aktivasi, perubahan ledger, pelaporan dan tax menjadi PR kecil; tentukan rollback, blocker dan keputusan pemilik. Ini pemeriksaan dokumen oleh penulis, bukan review independen atau tes runtime.

Baseline aplikasi memiliki bukti tes native/dashboard dan perpetual accounting dari PR82/83; bukti itu tidak otomatis menerima paket laporan OCA atau kepatuhan Coretax. Semua baris katalog mulai dari `BELUM_DITERIMA`; kemampuan existing harus dipromosikan melalui bukti per laporan, bukan reset atau repost ledger.

Branch ini hanya dokumentasi. Implementasi berikutnya dibuat pada branch per iterasi dari main terbaru. Merge/deploy/instalasi produksi masing-masing mengikuti otorisasi yang berlaku; dokumen ini tidak mengeksekusinya.
