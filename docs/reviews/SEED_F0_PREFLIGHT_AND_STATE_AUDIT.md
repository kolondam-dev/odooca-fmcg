# Laporan Preflight Live Database, Audit Rekonsiliasi Juli, dan Keputusan K1–K9 (Fase F0)

**Penulis:** antigravity · **Tanggal:** 2026-11-05 · **Basis:** `main` `13c43d3` (PR #92)
**Status Dokumen:** Laporan pembuktian read-only Fase F0 (`docs/blueprints/SEED_AGUSTUS_NOVEMBER_ANALISIS_DAN_PLAN.md` Bab 10).
**Penandaan:** [F] fakta bersumber · [A] asumsi · [BU] belum diuji/diverifikasi (AGENTS.md butir 6).

---

## 1. Tujuan dan Ruang Lingkup F0

Fase F0 adalah gerbang pertama dari rencana kelanjutan seeding transaksi FMCG Manado dari 1 Agustus hingga 5 November 2026 (hari kerja ke-81), serta fondasi mesin harian mulai 6 November 2026.

Sesuai kontrak dan plan PR #92, tugas F0 mencakup:
1. **Pencatatan Keputusan Pemilik K1–K9:** Mengunci ketetapan K1–K4 yang disahkan pada 5 November 2026 (Bab 9A), serta mendokumentasikan rekomendasi default K5–K9.
2. **Preflight Read-Only Database Live Railway:** Menghubungi database produksi `pleasant-caring` (`railway`) melalui koneksi PostgreSQL baca-saja (`default_transaction_read_only=on`) untuk membuktikan kondisi nyata: dokumen, stok, kas/bank, dan fixture sisa (G-05).
3. **Rekonsiliasi Penutupan Juli Kanonikal:** Membangun berkas pembukaan kanonikal `data/registers/state_20260801.json` dengan presisi 100% terhadap 15 register beku dan `canonical_financial_reconciliation_july_2026.json`.

---

## 2. Pencatatan Keputusan Pemilik (K1–K9)

### 2.1 Keputusan yang Disahkan (Bab 9A Plan PR #92) [F]

| # | Parameter | Keputusan Pemilik | Konsekuensi Implementasi |
|---|---|---|---|
| **K1** | Batas Periode Seed & Mesin Harian | **Kamis, 5 November 2026** (hari kerja ke-81) adalah batas akhir period pack. Mesin harian manual (`scripts/ops/seed_day.py`) berlaku mulai **6 November 2026+**. | DO 6 November berstatus carry-forward siap kirim. Planner murni yang sama dipakai untuk offline pack (Agu–5 Nov) dan live daily engine (6 Nov+). |
| **K2** | Rekonsiliasi Juli Beku vs Narasi | **Juli beku 100% imutabel** (15 register dan 13.540 baris AML tidak disentuh). Kalibrasi hanya pada perilaku Agustus+: biaya (katalog OPEX bulanan), retur/tolakan (nota kredit + karantina), dan normalisasi diskon. | Titik naratif lama "Juli krisis margin 0,9%" dilepas; skrip demo membaca margin bersih Juli nyata 4,12%. Target margin Agu–Okt diselaraskan: 4,12% → ±2,5% → ±3,7% → ±5,0%. |
| **K3** | Jalur Deploy ke Railway | **Opsi A: Tambah ke database live bertahap per hari kerja (micro-slicing presisi), tanpa timpa/restore DB.** | Setiap hari kerja adalah 1 slice transaksi atomik (`Decimal`, zero-drift). Backup berkala per blok bulan. |
| **K4** | Campuran Principal | **Opsi A: Campuran principal organik dari Juli beku.** | Titik awal Wings 23% / Mayora 29% / Santos 21% / Unilever 27%. Tanpa mandat buatan 34/28/20/18. Perubahan proporsi hanya didorong pergeseran permintaan nyata. |
| **Diskon** | Normalisasi Diskon | Diskon berjenjang dinormalkan (4,64% → ±2,5% → 2,0%). | Pengungkit kenaikan laba kotor Agustus–Oktober. |
| **Pemicu** | Eksekusi Mesin Harian | **Perintah shell via `odoo shell`**, dijalankan operator/antigravity atas permintaan pemilik (bukan UI wizard). | Skrip `seed_day.py` dengan default dry-run, digest validasi, dan flag `--apply` eksplisit. |
| **Dokumen Live** | Order dari PWA / Demo Live | **Diterima sebagai fakta hidup.** | Stok tersedia dikurangi reservasi dokumen live. Mesin seed tidak mengubah atau menghapus transaksi live. |

### 2.2 Usulan dan Rekomendasi Default K5–K9 [A]

| # | Parameter | Usulan Default F0 | Landasan dan Alasan Teknis |
|---|---|---|---|
| **K5** | Saldo Kas/Modal Awal & Target Moneter | **Saldo modal awal Rp5.000.000.000,00** dicatat per 1 Juli (atau 1 Agustus) pada ekuitas/modal disetor ke akun Bank (`BNK1`). Target omzet bulanan dinilai dari **DPP net** setelah diskon baris sebelum tolakan dengan pita **±3%**. Target November ditambahkan ke `id.monetary.target` (Rp6,5 M pro-rata). | Tanpa modal awal, arus kas Juli adalah minus Rp3,163 M saat 31 Juli, dan langsung menolak pelunasan AP Unilever Rp2,9 M pada 8 Agustus. Modal Rp5 M menjamin kas kumulatif harian selalu positif (`CASH-NONNEG`). |
| **K6** | Katalog Biaya OPEX & Payroll | Biaya logistik harian proporsional ritase armada; pemeliharaan armada, listrik gudang, penyusutan aset, dan administrasi bank mengikuti rincian blueprint. **Gaji dibayarkan tanggal 30** (atau hari kerja terakhir sebelumnya). | Memenuhi R7, memulihkan defisit OPEX Juli (-Rp150 jt), dan membentuk grafik laba bersih yang realistis. |
| **K7** | Skenario Operasional Khusus | **Tolakan/retur bertahap** (Agustus ~2,4%, September ~1,8%, Oktober ~0,8%); barang rusak dipindah ke karantina lalu dihapus (scrap); aging AR membentuk bucket 1–30 / 31–60 hari; **1 kasus gagal bayar (kredit macet) di Oktober** untuk outlet GT. | Mendukung materi demo mitigasi risiko kredit dan proses retur PWA/Odoo. |
| **K8** | PPN Masukan (Vendor Bill) | Faktur vendor menggunakan pajak yang sama dengan konfigurasi PPN Odoo: **`12% (Non-Luxury Good)`** (DPP nilai lain 11/12, tarif efektif 11%). | Menjamin akun PPN Masukan dan PPN Keluaran sinkron di SPT Masa PPN dan laporan akuntansi. |
| **K9** | Perilaku Bayar & Batas Kredit | Mulai 1 Agustus, aturan limit kredit berstatus **strict dipatuhi**. Pelanggaran limit di Juli dijelaskan sebagai toleransi krisis sementara. | Mencegah anomali G-19 (33 dari 59 outlet melampaui kredit limit tanpa penjelasan operasional). |

---

## 3. Hasil Audit Preflight Live Database Railway (`railway`)

Pemeriksaan dilakukan secara langsung terhadap instance produksi Railway via koneksi TCP proxy PostgreSQL:
- **Host / Port:** `crossover.proxy.rlwy.net:52064`
- **Database:** `railway`
- **Mode Sesi:** `default_transaction_read_only=on`, `statement_timeout=60000`
- **Skrip Pemeriksa:** `scripts/ops/seed_f0_inspect_live.py` & `scripts/ops/seed_f0_analyze_stock_live.py`

### 3.1 Status Perusahaan & Pengguna [F]
- **Perusahaan Aktif:** 1 perusahaan aktif, yaitu **Company 1: PT Manado Distribusi Utama** (mata uang IDR, ID 12).
- **Perusahaan Arsip:** Company 2 (`STAGING TEST Company`) berhasil diarsipkan (`active = false`), sesuai tindak lanjut PR #87.
- **Pengguna:** 16 pengguna aktif, mencakup `sales1`, `sls-01` s.d `sls-03`, `cvs-01` s.d `cvs-02`, `driver-01`, `spv-sales`, `spv-wh`, `bm-01`, `staff-fin`, dan `admin`. Dua pengguna `staging.capture.*` nonaktif.

### 3.2 Transaksi Penjualan (Sale Orders) [F]
- **Total Sale Orders:** 1.327 order.
- **SO Kanonikal Juli:** Tepat **1.324 SO** (`client_order_ref LIKE 'SO-202607-%'`), tanggal order 2026-07-01 s.d 2026-07-31, DPP Rp5.784.650.114,00, total dengan PPN Rp6.420.961.626,52. Seluruh angka cocok persis sampai digit desimal terakhir dengan register beku.
- **SO Live PWA / Uji:** Tepat **3 order** bertanggal 2026-11-04 yang dibuat oleh user `admin`:
  1. `S06407` (Grosir Kauditan Makmur, Benn-Beng Reguler 20g, status: `cancel`).
  2. `S06408` (Grosir Kauditan Makmur, Benn-Beng Maxx 32g, status: `cancel`).
  3. `S06409` (Jumbbo Swalayan Pasar 45, status: `draft`, nilai 0).
- **Dampak Dokumen Live:** Ketiga SO live berstatus cancel/draft sehingga tidak menghasilkan mutasi stok ataupun piutang. Ini mengonfirmasi bahwa database live berada dalam kondisi bersih dan terlindungi dari benturan transaksi.

### 3.3 Transaksi Pembelian (Purchase Orders) [F]
- **Total PO:** Tepat **5 Purchase Orders** (`P00001` s.d `P00005`), seluruhnya berstatus `purchase` (confirmed).
- Sesuai dengan PO in-transit Juni:
  1. `P00001`: PT Sayapp Mas Utamma (Wings), Rp1.849.772.800,00 DPP.
  2. `P00002`: PT Santos Jaya Abadii (Santos), Rp1.449.737.600,00 DPP.
  3. `P00003`: PT Mayyora Indahh Tbk (Mayora), Rp699.826.000,00 DPP.
  4. `P00004`: PT Mayyora Indahh Tbk (Mayora), Rp2.598.138.400,00 DPP.
  5. `P00005`: PT Unilevr Indonezia Tbk (Unilever), Rp2.899.971.200,00 DPP.
- Total PO Inbound: Rp9.497.446.000,00 DPP.

### 3.4 Pengiriman & Surat Jalan (Stock Pickings) [F]
- **Tipe 1 (Incoming Receipts):** 14 picking berstatus `done` (13 untuk kontainer in-transit Juni + 1 saldo awal).
- **Tipe 2 (Delivery Orders):** Tepat **1.324 picking** berstatus `done`:
  - 1.276 pengiriman dilakukan pada rentang 2 s.d 31 Juli 2026.
  - 48 pengiriman carry-forward diselesaikan pada **1 Agustus 2026** (`WH/OUT/06358` s.d `WH/OUT/06405`).
- Seluruh pengiriman kanonikal Juli dan carry-forward 1 Agustus telah tereksekusi penuh di live server.

### 3.5 Faktur Penjualan & Piutang Terbuka (Accounts Receivable) [F]
- **Faktur Penjualan (Customer Invoices):** 1.324 faktur posted:
  - 1.276 faktur bertanggal Juli 2026.
  - 48 faktur carry-forward bertanggal 1 Agustus 2026.
  - 2 faktur draft tanpa nilai (terkait SO draft uji).
- **Piutang Terbuka (Open AR Invoices):**
  - Jumlah faktur belum lunas: **357 faktur**.
  - Total DPP terbuka: **Rp2.323.328.944,20**.
  - Total residual (termasuk PPN): **Rp2.578.895.128,04**.
  - Rincian: 309 faktur Juli (DPP Rp2.135.470.252,80) + 48 faktur 1 Agustus (DPP Rp187.858.691,40).
  - **Kesesuaian:** 100,0000% identik dengan `canonical_financial_reconciliation_july_2026.json`.

### 3.6 Hutang Dagang (Accounts Payable) [F]
- **Total Tagihan Vendor:** 35 bill vendor posted.
- **Hutang Terbuka:** Tepat **1 bill vendor** yang belum lunas: PO `P00005` (PT Unilevr Indonezia Tbk) senilai **Rp2.899.971.200,00 DPP**, jatuh tempo 8 Agustus 2026.
- 4 bill vendor lainnya (Wings, Santos, Mayora x2) senilai Rp6.597.474.800,00 telah dilunasi di bulan Juli.

### 3.7 Pembayaran & Saldo Kas/Bank (Cash & Bank Audit) [F]
- **Pelunasan Piutang (AR Collections):** 967 pembayaran inbound berstatus `paid` senilai total **Rp3.828.651.752,29**.
- **Pembayaran Hutang (AP Payments):** 4 pembayaran outbound berstatus `paid` senilai total **Rp6.597.474.800,00**.
- **Mekanisme Akuntansi Odoo 19:**
  - Odoo tidak langsung mengkredit akun Kas/Bank likuid saat register payment, melainkan menggunakan akun kliring transit:
    * `Outstanding Receipts` (`asset_current`): Debit Rp3.828.651.752,29.
    * `Outstanding Payments` (`asset_current`): Credit Rp6.597.474.800,00.
  - Selisih kliring likuiditas = −Rp2.768.823.047,71.
  - Ditambah beban OPEX payroll yang dibukukan lewat jurnal entry sebesar Rp394.350.000,00, posisi kas kumulatif Juli tanpa saldo modal awal adalah **−Rp3.163.173.047,71** (tepat membuktikan temuan G-06).

### 3.8 Audit Persediaan Fisik & Penyelesaian Gap G-05 [F]
Pemeriksaan kuantitatif terhadap tabel `stock_quant` dan lokasi gudang:
- **Lokasi `WH/Stock` (Internal):**
  - Total kuantitas tersimpan: **3.691.042 pcs**.
  - Jumlah SKU: 150 produk (100% lengkap).
  - Jumlah Lot aktif: 236 lot.
  - Konversi ke karton (berdasarkan `carton_qty` di master produk): **67.799 karton**.
- **Dekonstruksi Angka 67.799 Karton (Menjawab Tuntas G-05):**
  $$\text{Stok Fisik Live} = 67.799\text{ karton}$$
  $$\text{Sisa Stok Kanonikal Juli} = 53.837 - 1.038\text{ (48 DO terkirim 1 Agu)} = 52.799\text{ karton}$$
  $$\text{Selisih} = 67.799 - 52.799 = \mathbf{15.000\text{ karton}}$$
  $$\mathbf{15.000\text{ karton}} = 100\text{ karton} \times 150\text{ SKU}$$
  Ini adalah **fixture mobile staging 30 Oktober 2026** (HANDOFF baris 1590) yang disuntikkan sebelum pemuatan kanonikal dan belum dibersihkan.
- **Lokasi Karantina (`WH/Stock/Karantina FMCG Maumbi`):** 8 quant, 320 pcs = 9 karton reject (Rp1.963.200,00 COGS).
- **Rekomendasi Penanganan untuk Seeding Lanjutan:**
  - Pada lingkungan disposable (sandbox CI/lokal), seeding Agustus–November berjalan di atas keadaan murni kanonikal (52.799 karton available).
  - Pada database live Railway, kuota 100 karton × 150 SKU fixture mobile staging dapat disesuaikan lewat 1 jurnal penyesuaian persediaan balik (Inventory Adjustment minus 100 karton per SKU) bertanggal 31 Juli sebelum eksekusi pack Agustus, atau diperlakukan sebagai safety stock cadangan demo PWA.

---

## 4. Keadaan Penutupan Kanonikal: `state_20260801.json`

Berkas acuan `data/registers/state_20260801.json` telah dibangun secara deterministik oleh `scripts/ops/generate_state_20260801.py` dan divalidasi oleh suite pengujian `tests/test_state_20260801.py` (4 tests PASS).

### 4.1 Ringkasan Invariant Penutupan per 1 Agustus 2026 00:00:00 [F]

```json
{
  "as_of_datetime": "2026-08-01T00:00:00+07:00",
  "summary": {
    "total_physical_cartons": 53837,
    "total_reserved_cartons": 1038,
    "total_available_cartons": 52799,
    "total_quarantine_cartons": 9,
    "open_july_invoices_count": 309,
    "open_july_invoices_dpp": "2135470252.80",
    "carry_forward_august_invoices_count": 48,
    "carry_forward_august_invoices_dpp": "187858691.40",
    "total_open_ar_count": 357,
    "total_open_ar_dpp": "2323328944.20",
    "open_po_count": 1,
    "open_po_dpp": "2899971200.00",
    "pending_carry_forward_dos_count": 48
  },
  "last_sequences": {
    "last_so_number": "SO-202607-1324",
    "last_do_number": "DO-202607-1324",
    "last_invoice_number": "INV-202607-1324",
    "last_ar_payment_id": "PAY-AR-00967",
    "last_ap_payment_id": "PAY-AP-04",
    "last_rejection_id": "REJ-202607-009",
    "last_event_id": "EVT-005741"
  }
}
```

### 4.2 Keselarasan Kontrak Seed v2 & Generator Lanjutan
1. **Titik Sambung Nomor Urut:**
   - Order Penjualan Agustus mulai dari `SO-202608-0001`.
   - Surat Jalan Agustus mulai dari `DO-202608-0001` (48 DO carry-forward 1 Agustus menggunakan alokasi reservasi Juli).
   - Faktur Penjualan Agustus mulai dari `INV-202608-0001`.
   - Pelunasan Piutang mulai dari `PAY-AR-00968`.
   - Pembayaran Hutang mulai dari `PAY-AP-05`.
   - PO Pembelian Baru mulai dari `PO-2026-08-01`.
   - Event Kartu Stok mulai dari `EVT-005742`.
2. **Keterikatan Stok (STOCK-NONNEG):** Saldo pembukaan pack Agustus mewarisi saldo per SKU dan lot persis dari `state_20260801.json`.
3. **Keterikatan Kontinuitas (PERIOD-CONTINUITY):** Diverifikasi lulus otomatis terhadap deklarasi pembukaan generator.

---

## 5. Ringkasan Status Gate Keluar F0

| Kriteria Gate Keluar F0 | Status | Bukti |
|---|---|---|
| Keputusan K1–K4 dicatat mengikat | **LENGKAP** | Bab 2.1; disahkan di Bab 9A PR #92 |
| Rekomendasi K5–K9 terdefinisi rasional | **LENGKAP** | Bab 2.2; usulan default [A] siap pakai |
| Preflight read-only live DB Railway | **PASS** | Bab 3; skrip `seed_f0_inspect_live.py` & bukti query read-only |
| Analisis & dekonstruksi sisa fixture G-05 | **SELESAI** | Bab 3.8; selisih persis 15.000 karton (100 karton × 150 SKU) |
| Rekonsiliasi Juli kanonikal 100% cocok | **PASS** | Bab 4; 53.837 fisik / 1.038 reservasi / 9 karantina / 357 piutang |
| Berkas `data/registers/state_20260801.json` | **TERBIT** | Divalidasi oleh `tests/test_state_20260801.py` (4 tests PASS) |
| Kesiapan menuju F1 (Kontrak v2 & Gates) | **SIAP** | Pondasi baseline telah terkunci |

Fase F0 selesai dengan sukses tanpa mutasi data server, tanpa dump di git, dan tanpa menyimpan kredensial.
