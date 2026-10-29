# Rencana Runner Full Dataset Disposable dan Protokol Cut-Off Dua Periode

**Status:** Diajukan oleh `antigravity` agent (2026-10-29).  
**Konteks Baseline:** Dokumen `full_dataset_runner_and_cutoff_plan.md` pernah dirujuk pada catatan handoff/riwayat agen terdahulu, tetapi setelah diaudit secara menyeluruh di git history dan working tree, berkas tersebut belum pernah di-commit ke repositori. Dokumen ini menyusun proposal kanonikal lengkap berdasarkan source code aktual, register beku (`fae5835`), dan kontrak invariant `docs/reviews/SEED_INVARIANT_CONTRACT.md`.

---

## 1. Rekonsiliasi Historis: 14 Kunjungan vs 48 Transaksi Carry-Forward Agustus

### 1.1 Asal-Usul Angka 14 Invoice vs 48 Invoice Aktual
Pada iterasi awal (commit `dee5179`), dataset mencakup 419 SO gabungan multi-prinsipal. Pada 31 Juli 2026, tercatat tepat **14 kunjungan outlet** yang menghasilkan pesanan untuk pengiriman H+1 (1 Agustus 2026), sehingga dilaporkan sebagai "14 invoice Agustus".

Pada commit `fae5835`, pemilik menetapkan aturan ketat **SO-PRINCIPAL**:
> *"Setiap SO hanya berisi SKU dari tepat satu principal_code pada master produk; campuran prinsipal menggagalkan gate."*

Ketika 14 kunjungan outlet pada 31 Juli tersebut dipecah secara murni per prinsipal:
- 14 kunjungan outlet menghasilkan **48 Sales Orders single-prinsipal** bertanggal `2026-07-31`.
- Masing-masing menghasilkan **48 Surat Jalan (DO)** terjadwal tanggal `2026-08-01`.
- Masing-masing menghasilkan **48 Faktur Penjualan (Invoice)** bertanggal `2026-08-01`.
- Nilai total: DPP Rp 187.858.691,40; PPN 11% Rp 20.664.456,06; Grand Total Rp 208.523.147,46.
- Kuantitas fisik yang dipesan: **1.038 karton**.

### 1.2 Ringkasan Matriks Dokumen Kanonikal (15 CSV Beku)
| Kategori Dokumen | Periode Juli 2026 | Carry-Forward 1 Agustus 2026 | Total Seluruh Dataset |
|---|---|---|---|
| **Sales Order (SO)** | 1.324 (seluruh SO dipesan Juli) | 0 (tidak ada SO baru 1 Ags) | **1.324** |
| **Surat Jalan (DO)** | 1.276 (terkirim & selesai Juli) | 48 (terkirim 1 Agustus) | **1.324** |
| **Inbound PO (Kapal)** | 5 (transit Juni, terima Juli) | 0 | **5** |
| **Retur Karantina** | 9 (seluruhnya di Juli) | 0 | **9** |
| **Faktur Komersial** | 1.276 (buku penjualan Juli) | 48 (buku penjualan Agustus) | **1.324** |
| **Pembayaran AR** | 967 (alokasi faktur Juli) | 0 (faktur Ags belum jatuh tempo) | **967** |
| **Pembayaran AP** | 4 (alokasi PO Juni/Juli) | 0 (1 PO terbuka Rp 2,89 M) | **4** |
| **Beban Operasional & Gaji** | 30 (operasional Juli) | 0 | **30** |

---

## 2. Kebijakan Waktu Bisnis & Timezone (WITA / Asia/Makassar)

1. **Timezone Operasional:**
   - Seluruh operasi bisnis distributor Manado mengacu pada **WITA (`Asia/Makassar`, UTC+8)**.
   - Konversi UTC:
     * Opening Juli: `2026-07-01 00:00:00 WITA` = `2026-06-30 16:00:00 UTC`.
     * Operasional Gudang: Pukul `08:00:00 WITA` = `00:00:00 UTC`.
     * Closing Juli: `2026-07-31 23:59:59 WITA` = `2026-07-31 15:59:59 UTC`.
     * Opening Agustus: `2026-08-01 00:00:00 WITA` = `2026-07-31 16:00:00 UTC`.
2. **Kemandirian Tanggal Transaksi:**
   - Tanggal SO, Surat Jalan (DO), Faktur, dan Pembayaran tidak boleh disamakan secara paksa:
     * SO dibuat pada tanggal kunjungan salesman (`date_order`).
     * DO tervalidasi pada tanggal pengiriman fisik barang (`scheduled_date` / `date_done`).
     * Faktur komersial mengikat tanggal tagihan sah (`invoice_date` / `date`).
     * HPP dibukukan pada saat pengiriman fisik (DO) terjadi, bukan ditarik ke tanggal SO atau diundur ke tanggal pembayaran.
3. **Pemisahan Laporan As-Of:**
   - Transaksi 1 Agustus 2026 tidak boleh bocor ke Laporan Laba Rugi maupun Neraca per 31 Juli 2026.
   - Saldo Piutang Usaha per 31 Juli hanya mengakui 1.276 faktur Juli. 48 faktur Agustus baru diakui pada tanggal 1 Agustus 2026.

---

## 3. Arsitektur Runner Disposable (`verify_disposable_full.py`)

### 3.1 Prinsip Desain
1. **Safety Fail-Closed:**
   - Runner memverifikasi nama database target: wajib memuat substring disposable (misal `disposable`, `ci`, `test`, `exp`) dan menolak database produksi/operasional secara mutlak.
2. **Audit Metadata Lingkungan:**
   - Mencatat Git Commit SHA, Odoo Image ID/Digest, daftar modul terpasang beserta versinya, konfigurasi valuasi stok kategori produk (`cost_method=fifo`, `valuation=real_time`), company ID, timezone, dan hash 15 CSV kanonikal.
3. **Menggunakan Loader Produksi:**
   - Mengeksekusi `CanonicalPerpetualAdapter` dari `scripts/load_canonical_perpetual.py` tanpa bypass aturan.
4. **Alur Deterministi Dua Fase:**
   - **Fase A (Closing Juli 2026):** Memuat master, opening stock 150 SKU, 5 PO inbound, 1.324 SO, memvalidasi 1.276 DO Juli, memuat 9 retur karantina, menerbitkan 1.276 Faktur Juli, 967 Pembayaran AR, 4 Pembayaran AP, dan 30 OPEX. Pada fase ini, 48 DO Agustus tetap dalam status pending/reserved (1.038 karton tereservasi).
   - **Audit Checkpoint Juli:** Memverifikasi saldo stok (53.837 on-hand, 1.038 reserved, 52.799 available) dan GL Juli terhadap Oracle Kanonikal.
   - **Fase B (Opening Agustus 2026):** Memvalidasi 48 DO carry-forward Agustus ke status `done`, menerbitkan 48 Faktur Agustus. Memverifikasi reservasi stok turun menjadi 0,0 dan fisik menjadi 52.799 karton.
   - **Fase C (Uji Replay / Idempotensi Run 2):** Menjalankan ulang seluruh loader. Memverifikasi 0 record baru dibuat (100% skipped) dan deep snapshot zero-drift.
   - **Fase D (Audit Oracle Independen):** Menghitung ekspektasi langsung dari 15 CSV register tanpa membaca ringkasan loader, membandingkan multiset baris, akun, debit/kredit, dan relasi dokumen.

---

## 4. Pengujian Upgrade Modul & Isolasi COGS

1. **Upgrade Path:**
   - Database disposable yang telah berisi master/seed diuji dengan perintah upgrade Odoo:
     `odoo -d <dbname> -u id_base,id_ui_form --stop-after-init`
   - Memverifikasi bahwa schema ORM, data register, dan integritas move lines tidak terganggu oleh proses upgrade.
2. **Isolasi Supresi COGS:**
   - Menguji pembuatan invoice biasa (ordinary non-seed invoice):
     * Wajib membukukan HPP native jika delivery belum membukukan HPP.
     * Supresi COGS hanya berlaku secara sempit pada invoice berpenanda `is_fmcg_seed_invoice = True` dan `fmcg_seed_batch = 'CANONICAL_JULY_2026_PERPETUAL'`.
3. **Injeksi Kegagalan & Rollback Boundary:**
   - Mensimulasikan kegagalan write di tengah batch transaksi; membuktikan bahwa rollback transaction boundary bekerja bersih tanpa partial commit atau quant leak.

---

## 5. Pelaporan & Otomasi CI

1. **Workflow GitHub Actions Mandiri:**
   - Berkas: `.github/workflows/full-dataset-runtime.yml`.
   - Trigger: `workflow_dispatch` (manual) dan push pada branch khusus.
   - Timeout terukur: 45 menit.
   - Menjalankan container disposable `fmcg-odoo:ci` dengan PostgreSQL 16 bersih.
   - Mengunggah artefak laporan: `full_dataset_runtime_report.json` dan `full_dataset_runtime_summary.md`.

