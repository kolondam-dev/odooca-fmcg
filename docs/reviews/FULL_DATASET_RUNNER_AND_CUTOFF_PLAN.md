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
- Memetakan 14 pelanggan unik, 4 prinsipal nasional (`MYR`, `KPA`, `ULV`, `WNG`), dan tim salesman kanonikal.
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
   - Tanggal SO, Surat Jalan (DO), Faktur, dan Pembayaran tidak disamakan secara paksa:
     * SO dibuat pada tanggal kunjungan salesman (`date_order`).
     * DO tervalidasi pada tanggal pengiriman fisik barang (`scheduled_date` / `date_done`).
     * Faktur komersial mengikat tanggal tagihan sah (`invoice_date` / `date`).
     * HPP dibukukan pada saat pengiriman fisik (DO) terjadi, bukan ditarik ke tanggal SO atau diundur ke tanggal pembayaran.
3. **Pemisahan Laporan As-Of:**
   - Transaksi 1 Agustus 2026 tidak boleh bocor ke Laporan Laba Rugi maupun Neraca per 31 Juli 2026.
   - Saldo Piutang Usaha per 31 Juli hanya mengakui 1.276 faktur Juli. 48 faktur Agustus baru diakui pada tanggal 1 Agustus 2026.
   - Penutupan historis Juli terbukti imutabel: re-audit baris jurnal Juli setelah pemrosesan 1 Agustus memastikan saldo dan hitungan AML Juli tidak mengalami perubahan.

---

## 3. Arsitektur Runner Disposable (`verify_disposable_full.py`)

### 3.1 Prinsip Desain
1. **Safety Fail-Closed:**
   - Menolak mutlak substring kata terlarang operasional/produksi (`prod`, `production`, `live`, `railway`, `master`, `official`, `main`).
   - Wajib cocok dengan nama database disposable eksplisit (`fmcg_full_disposable`, `ci_db`, `test_disposable`, atau pola regex `_disposable`).
2. **Audit Metadata Lingkungan:**
   - Mencatat Git Commit SHA (`GITHUB_SHA`), Docker Image ID/Digest (`ODOO_IMAGE`), GitHub Run ID, daftar modul terpasang beserta versinya (`installed_version`), konfigurasi valuasi stok kategori produk, company ID, timezone, dan hash 15 CSV kanonikal.
3. **Menggunakan Loader Produksi:**
   - Mengeksekusi `CanonicalPerpetualAdapter` dari `scripts/load_canonical_perpetual.py` tanpa bypass aturan.
4. **Alur Deterministi Dua Fase:**
   - **Fase 1 (Closing Juli 2026):** Memuat master, opening stock 150 SKU, 5 PO inbound, 1.324 SO, memvalidasi 1.276 DO Juli, memuat 9 retur karantina, menerbitkan 1.276 Faktur Juli, 967 Pembayaran AR, 4 Pembayaran AP, dan 30 OPEX. Pada fase ini, 48 DO Agustus tetap dalam status pending/reserved (1.038 karton tereservasi).
   - **Audit Checkpoint Juli:** Memverifikasi saldo stok (53.837 on-hand, 1.038 reserved, 52.799 available) dan GL Juli terhadap Oracle Kanonikal secara dinamis.
   - **Fase 2 (Post-Transaksi 1 Agustus 2026):** Memvalidasi 48 DO carry-forward Agustus ke status `done`, menerbitkan 48 Faktur Agustus. Memverifikasi reservasi stok turun menjadi 0,0 dan fisik menjadi 52.799 karton. Re-verifikasi as-of closing Juli membuktikan saldo historis tidak terdistorsi.
   - **Fase 3 (Uji Replay / Idempotensi Run 2):** Menjalankan ulang seluruh loader. Memverifikasi 0 record baru dibuat (100% skipped) dan deep snapshot zero-drift.
   - **Audit Oracle Independen Dinamis:** Menghitung ekspektasi langsung secara dinamis dari baris CSV register tanpa hardcode angka, membuktikan responsivitas terhadap perubahan data sumber (lulus supervisor mutation probe).

### 3.2 Deep State Snapshot Presisi Tinggi
- Menyimpan presisi penuh datetime (tanpa pemotongan 10 karakter).
- `stock.move.line`: mencakup `product_id`, `lot_id`, `location_id`, `location_dest_id`, `product_uom_id`, `quantity`, `date`, `company_id`, `state`.
- `stock.move`: mencakup relasi `picking_id`, `sale_line_id`, `origin_returned_move_id`, `account_move_ids`.
- `account.move.line`: mencakup `product_id`, `company_id`, `date`, `amount_residual`, `reconciled`.
- Sensitivitas snapshot terbukti menangkap perubahan lokasi, produk, maupun pergeseran jam yang melintasi tengah malam WITA.

---

## 4. Status Tiga Prioritas & Pemisahan Scope Upgrade

Sesuai arahan audit supervisi ([issuecomment-6490484056](https://github.com/kolondam-dev/odooca-fmcg/pull/39#issuecomment-6490484056)):
1. **Prioritas 1 (Runner Full Dataset Disposable):** **SELESAI** — diimplementasikan dalam `scripts/ops/verify_disposable_full.py` dan diuji via `.github/workflows/full-dataset-runtime.yml`.
2. **Prioritas 2 (Two-Phase Cut-Off Juli & Agustus):** **SELESAI** — parameter `enforce_invoice_cutoff` diimplementasikan, diaudit dengan oracle dinamis, as-of closing Juli imutabel, dan mutasi negatif ditolak.
3. **Prioritas 3 (Upgrade Baseline Persisten):** **SELESAI (PR lanjutan `agen/persisted-baseline-upgrade`)** — jalur upgrade dipisahkan ke PR tersendiri setelah runtime penuh fase 1 & 2 terbukti di lingkungan disposable nyata. Implementasi: `scripts/ops/verify_upgrade_baseline.py` (dua fase: baseline persisten dan verifikasi pasca-upgrade) + `.github/workflows/upgrade-runtime.yml`. Rincian pada Bab 6.

---

## 5. Pelaporan & Otomasi CI

1. **Workflow GitHub Actions Mandiri:**
   - Berkas: `.github/workflows/full-dataset-runtime.yml`.
   - Trigger: `workflow_dispatch`, push branch `agen/full-dataset*`, dan pull request pada path runner/loader/test terkait.
   - Timeout terukur: 45 menit.
   - Bootstrap terisolasi: membuat database `fmcg_base` sebelum container Odoo dimulai, deteksi fail-fast container exit, dan pembuatan template disposable `fmcg_full_disposable`.
   - Mengunggah artefak diagnostik lengkap pada status SUKSES maupun GAGAL (`full_dataset_runtime_report.json`, `full_dataset_runtime_summary.md`, `full_dataset_runtime.log`, `odoo_container.log`).

---

## 6. Prioritas 3: Upgrade Modul dari Baseline Persisten & Replay Idempotensi

**Status:** SELESAI — diimplementasikan 2026-10-30 (agen implementer `claude-dev`). Bukti runtime exact-SHA dilampirkan pada komentar PR.

### 6.1 Ruang Lingkup yang Dibuktikan
| Aspek | Bukti |
|---|---|
| Upgrade nyata | `odoo -u id_base,id_mobile_api --stop-after-init -d fmcg_upgrade_disposable` pada container Odoo 19 + PostgreSQL 16; exit code 0 dan log bebas `ERROR`/`CRITICAL`/`Traceback`/`psycopg2.errors.` |
| Baseline persisten | Database berisi dataset kanonikal penuh (closing Juli + carry-forward 1 Agustus, 1.324 SO / 1.324 faktur / 967 AR / 4 AP / 30 OPEX) sebelum upgrade, dengan deep state snapshot + digest SHA-256. |
| Integritas DDL | Setiap field stored milik `id_base`/`id_mobile_api` wajib memiliki kolom nyata; satu kolom (`id_mobile_office.radius`) sengaja dihapus dan wajib dibuat ulang oleh `-u`. |
| Integritas relasi | Tidak ada baris orphan pada seluruh field many2one milik modul `id_*`. |
| Integritas view XML | Seluruh xmlid view modul ter-resolve, arch non-kosong, dan XML valid; satu view (`id_mobile_api.view_mobile_office_form`) sengaja dihapus dan wajib dimuat ulang oleh `-u`. |
| Hook akuntansi | Override HPP `id_base` aktif pada registry; faktur komersial seed tidak membawa baris HPP 510000 duplikat; setiap delivery outbound selesai memiliki jurnal valuasi native STJ posted. |
| Replay idempotensi | `CanonicalPerpetualAdapter.run_all()` dijalankan ulang pasca-upgrade: seluruh counter pembuatan = 0, minimum skip kanonikal terpenuhi, dan digest snapshot identik 100% dengan baseline (zero-drift). |
| Imutabilitas historis | Multiset baris AML closing Juli identik sebelum dan sesudah upgrade + replay. |
| Audit oracle | `audit_database_against_oracle_august` + anti-fallback salesperson dijalankan ulang pasca-upgrade. |

### 6.2 Drift Terkontrol [A]
Agar upgrade benar-benar melakukan kerja perbaikan (bukan sekadar re-load tanpa perubahan), baseline menyuntikkan tiga drift terkontrol sebelum `-u`:
1. **Version skew:** `ir.module.module.latest_version` diturunkan ke versi rilis sebelumnya; pasca-upgrade wajib kembali sama dengan versi manifest kode.
2. **Schema drift:** kolom `id_mobile_office.radius` dihapus (tabel wajib kosong; jika tidak kosong, injeksi dilewati demi keamanan data).
3. **View drift:** record `ir.ui.view` + xmlid `id_mobile_api.view_mobile_office_form` dihapus.

### 6.3 Alur Workflow `upgrade-runtime.yml`
1. `contract-tests`: unit test kontrak runner (guard, perintah upgrade, kontrak log, replay, digest).
2. Bootstrap `fmcg_base` (init.sh) → template `fmcg_upgrade_disposable`.
3. **Fase A:** baseline persisten — muat fase 1 + audit Juli, muat fase 2 + audit Agustus, snapshot + digest, suntik drift.
4. **Fase B:** `odoo -u id_base,id_mobile_api` nyata → exit code dicatat.
5. **Fase B2:** validasi kontrak log (exit 0, tanpa indikasi registry corruption).
6. **Fase C:** verifikasi registry/DDL/FK/view/HPP + replay zero-drift + imutabilitas Juli + audit oracle.
7. Artefak diagnostik (`upgrade_baseline_state.json`, laporan JSON/MD kedua fase, log upgrade, log container) diunggah pada status apa pun.

### 6.4 Batasan Jujur
- Drift version/skema/view adalah simulasi terkontrol untuk membuktikan jalur perbaikan upgrade; bukan bukti bahwa pernah ada rilis modul lama yang benar-benar dideploy.
- Unit test lokal hanya memvalidasi kontrak logika; pembuktian upgrade wajib berasal dari eksekusi container pada GitHub Actions (exact SHA).
