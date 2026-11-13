# Lisensi modul finance — keputusan dan kewajiban

Tanggal: 13 November 2026 (WIB). Keputusan pemilik: **B — produk
AGPL-compliant** ([OWNER_DECISIONS.md](OWNER_DECISIONS.md)).
Dokumen ini tinjauan engineering, **bukan nasihat hukum**. Review legal wajib
sebelum kontrak klien pertama.

## Matriks lisensi yang berlaku

| Modul | Sumber | Lisensi | Dipakai untuk |
|---|---|---|---|
| Odoo 19 CE | `odoo/odoo` | LGPL-3 | inti |
| `account_financial_report` | OCA `account-financial-reporting` pin `f48b4ea` | AGPL-3 | FIN01–FIN03, FIN07–FIN09 |
| `partner_statement` | OCA `account-financial-reporting` pin `f48b4ea` | AGPL-3 | I5, belum menjadi dependensi |
| `account_tax_balance` | OCA `account-financial-reporting` pin `f48b4ea` | AGPL-3 | I6, belum menjadi dependensi |
| `account_usability` | OCA `account-financial-tools` pin `c23fd09` | AGPL-3 | dependensi `id_finance_foundation` |
| `account_invoice_start_end_dates` | OCA `account-closing` pin `8ce0077` | LGPL-3 | FIN37 |
| `mis_builder` | OCA `mis-builder` pin `7d519f3` | AGPL-3 | I4, belum menjadi dependensi |
| `account_asset_management` | OCA `account-financial-tools` pin `c23fd09` | AGPL-3 | FIN36, belum menjadi dependensi |
| `account_credit_control` | OCA `credit-control` pin `153ffd6` | AGPL-3 | I5, belum menjadi dependensi |
| `account_reconcile_oca` | OCA `account-reconcile` pin `14ddec2` | AGPL-3 | I5, belum menjadi dependensi |
| `payroll` | OCA `payroll` pin `58f8a39` | LGPL-3 | FIN56 |
| `id_*` (custom) | repo ini | LGPL-3 di manifest | lihat analisis turunan |

Lisensi di atas diverifikasi dari `__manifest__.py` pada SHA pin, bukan dari
ingatan atau dokumentasi umum.

## Analisis karya turunan

Dua modul custom **mewarisi langsung** kelas OCA AGPL-3:

| Modul | Kelas yang diwarisi | Berkas |
|---|---|---|
| `id_finance_reporting` | `report.account_financial_report.trial_balance` | `models/trial_balance.py` |
| `id_finance_foundation` | `report.account_financial_report.general_ledger`, `.journal_ledger`, `.open_items`, `.aged_partner_balance` | `models/report_boundary.py` |

Konsekuensi: secara teknis keduanya adalah karya turunan AGPL-3, sementara
manifest-nya masih menyatakan LGPL-3. Inkonsistensi ini **dicatat, bukan
diperbaiki diam-diam** di PR ini.

Modul custom lain yang tidak mewarisi kelas AGPL (mis. `id_mobile_api`,
dashboard, PWA) tidak otomatis menjadi turunan hanya karena berbicara lewat
HTTP atau memanggil ORM; PWA dan dashboard tetap terpisah.

## Kewajiban yang menyala

AGPL-3 §13 menambah kewajiban pada GPL: pengguna yang berinteraksi lewat
jaringan harus **ditawari Corresponding Source**.

| Skenario | Distribusi? | Kewajiban |
|---|---|---|
| Operasional internal PT Manado Distribusi Utama | umumnya tidak | simpan notice/lisensi; tidak ada publikasi ke luar |
| Demo ke calon klien lewat browser | pengguna jaringan | tawarkan source; risiko rendah bila demo terbatas, bukan nol |
| Instalasi on-premise di klien | ya | sertakan source + lisensi + notice |
| SaaS multi-distributor | ya (§13 aktif) | tawarkan source kepada pengguna layanan |

## Rencana perbaikan

1. PR lisensi terpisah: ubah `license` pada dua modul turunan menjadi AGPL-3,
   tambahkan berkas `LICENSE`/`NOTICE` dan cara memperoleh source.
2. `scripts/check_manifests.py` saat ini **mewajibkan** `license == "LGPL-3"`
   untuk semua addon, sehingga perubahan metadata tidak bisa dilakukan tanpa
   memperbarui gate tersebut. Ini disengaja: perubahan lisensi harus terlihat
   di review, bukan efek samping.
3. Modul baru yang mewarisi kelas AGPL wajib langsung AGPL-3.
4. Sebelum kontrak klien pertama: review legal atas skenario distribusi yang
   dipilih dan teks penawaran source.

## Yang tidak diubah dokumen ini

- Tidak ada perubahan `license` di manifest pada PR ini.
- Tidak ada perubahan dependensi, `oca.lock`, atau aktivasi demo.
- Tidak ada klaim kepatuhan hukum; status katalog tetap `BELUM_DITERIMA`.
