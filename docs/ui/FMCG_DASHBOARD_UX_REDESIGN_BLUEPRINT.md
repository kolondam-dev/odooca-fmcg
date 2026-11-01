# FMCG Dashboard UX/UI Redesign Blueprint: Pengorganisasian View, Filter Grouping, Visual Ergonomics & Narasi Bisnis

**Tanggal:** 2026-11-01  
**Status:** Design Proposal & Architectural Blueprint  
**Objektif:** Mentransformasi tampilan dashboard FMCG dari layout "kotak-kotak monoton berantakan" menjadi antarmuka analitik enterprise yang bersih, ergonomis, terstandardisasi, dan menyajikan narasi bisnis yang runtut.

---

## 1. Dekonstruksi Masalah Desain Eksisting: Mengapa Tampilan Saat Ini Mengganggu?

Berdasarkan tinjauan kritis terhadap implementasi dashboard saat ini (`id_dashboard_sales`, `id_dashboard_monetary`, dan `id_dashboard_wms`), berikut adalah diagnosa teknis dan ergonomi visual atas keluhan pengguna:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 DEFECT ANATOMI DESAIN LAMA                                       │
│                                                                                                  │
│ [Filter Bar]                                                                                     │
│  [Day|Wk|Mo] [<] 2026-07-01 [>] Salesman: [Chip1] [Chip2] [Chip3] [Chip4] Channel: [GT] [MT]...│
│  ❌ Baris wrap panjang tanpa pengelompokan; 10 salesman membuat filter bar meledak 3-4 baris.    │
│  ❌ Tiga dashboard menggunakan tiga kontrol filter yang saling bertolak belakang (Mode vs Native) │
│                                                                                                  │
│ [Scorecard Grid: Kotak-kotak Monoton & Ikon Raksasa]                                             │
│  ┌───────────────┬───────────────┬───────────────┬───────────────┐                               │
│  │ [■40px] OMZET │ [■40px] DISKON│ [■40px] NETTO │ [■40px] DO    │                               │
│  │   Rp 6,06 M   │    Rp 281 jt  │   Rp 5,78 M   │    1.276      │ ❌ Ikon blok solid 40x40      │
│  │   ▲ 12% vs pr │    4.6% gross │   ▲ 11% vs pr │    ▲ 5% vs pr │    terlalu dominan & agresif  │
│  │   1324 orders │   diskon nota │   DPP ex-tax  │   delivery dt │ ❌ Hairline keliling monoton  │
│  └───────────────┴───────────────┴───────────────┴───────────────┘ ❌ Teks meta berjejal rapat   │
│                                                                                                  │
│ [Whitespace & Rhythm]                                                                            │
│  • Padding section sempit (12px 16px), border 1px abu-abu di setiap sisi menciptakan "efek sel" │
│  • Tidak ada hirarki spasial antara angka makro, grafik tren, dan antrean aksi operasional       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1. Visual Fatigue akibat "Kotak-Kotak Monoton" & Ikon Raksasa
* **Cognitive Competition:** Kotak ikon berwarna pekat (Navy, Blue, Emerald, Amber, Red) berukuran 40×40px dengan latar solid menjadi elemen paling kontras di layar. Mata pengguna secara tidak sadar ditarik ke **ikon**, bukan ke **angka bisnis** dan **tren delta**.
* **Misaligned Baseline:** Grid kartu memadukan 4 elemen teks bertingkat (*Title, Value, Delta, Meta*) dengan panjang baris yang berbeda-beda. Ketika satu kartu memiliki meta teks 2 baris sedangkan kartu lain 1 baris, kartu terlihat "pincang" dan tidak teralign rapi.
* **Border Overload:** Penggunaan hairline border 1px di setiap pembagi sel menciptakan ilusi lembar spreadsheet tua (*cage effect*), mengorbankan estetika modern Odoo 19.

### 1.2. Filter Chaos: Tanpa Grouping & Tidak Konsisten Lintas Halaman
* **Sales:** Menggunakan tombol segmented mode (`day/week/month`), tombol navigasi geser, input date native, lalu deretan tombol chip horizontal untuk salesman dan channel. Jika ada 10 salesman, baris filter meledak menjadi 3 baris tak beraturan.
* **Monetary:** Tombol quick drilldown ditempatkan di dalam header filter, diikuti chip area dan salesman. Tidak memiliki kontrol filter tanggal sama sekali.
* **WMS:** Menggunakan elemen HTML native `<select>` dropdown konvensional, tanpa filter tanggal.
* **Dampak:** Pengguna mengalami disorientasi kognitif saat berpindah halaman karena pola interaksi (*mental model*) berubah drastis di setiap modul.

### 1.3. Ketiadaan Narasi Bisnis (Information Flow Broken)
Komponen dilempar ke layar tanpa alur logis. Dashboard yang baik harus membimbing pengguna melalui **3 Babak Narasi FMCG**:
1. **Babak 1: "Bagaimana kondisi bisnis kita saat ini?"** (High-level Pulse).
2. **Babak 2: "Mengapa angka tersebut terjadi?"** (Drivers & Variance Analysis: Principal, Channel, Rayon).
3. **Babak 3: "Apa yang harus kita tindaklanjuti hari ini?"** (Actionable Exception Queues).

---

## 2. Blueprint Redesain: Standarisasi Arsitektur Visual & Ergonomi

### 2.1. Refined Metric Cards: Minimalis, Proporsional, & Bernafas (*Generous Whitespace*)

Alih-alih blok kotak pekat 40px, kartu metrik direstrukturisasi menjadi komponen yang bersih dengan rasio kontras lembut:

```
┌─────────────────────────────────────────────────────────────┐
│  REFINED METRIC CARD (NEW DESIGN)                           │
│                                                             │
│  NET REVENUE (DPP)               [ ☵ Rp ]  <- Soft Tint     │
│                                               Badge (24px)  │
│  Rp 5,78 M                       [ ▲ 11.2% ] <- Pill Delta  │
│                                                              │
│  Target Bulanan: Rp 5,50 M (105%) · 1.324 Order             │
└─────────────────────────────────────────────────────────────┘
```

* **Pembersihan Ikon:** Ikon diubah menjadi *Subtle Header Badge* berukuran 24×24px dengan latar belakang transparan/soft-tint (`rgba(color, 0.08)`) dan warna glyph yang selaras. Ikon diposisikan di sudut kanan atas sebagai penanda kontekstual, bukan dominator visual.
* **Tipografi Angka:** Angka nilai (*Value*) diperbesar ke `1.625rem (26px)`, menggunakan font berbobot medium-bold dengan fitur `font-variant-numeric: tabular-nums` agar sejajar secara matematika.
* **Pill Delta:** Indikator tren (`▲ 11.2%`) dibungkus dalam *pill badge* lembut (hijau/merah transparan) sejajar dengan angka, memberikan sinyal status instan tanpa mengacaukan teks meta.
* **Kerapian Spasial:** Kartu berdiri sendiri di atas permukaan kartu putih bersih dengan radius halus `4px` (menghilangkan rounded ekstrim tapi tidak kaku seperti tabel excel mentah), padding lega `18px 20px`, dan bayangan mikro `0 1px 3px rgba(0,0,0,0.05)`.

---

### 2.2. Unified Grouped Filter Bar (Standarisasi 3 Klaster Lintas Modul)

Ketiga dashboard disatukan dengan **Satu Standar Filter Bar Terpadu** yang dibagi ke dalam 3 klaster fungsional yang jelas:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ UNIFIED FMCG FILTER BAR                                                                                     │
├───────────────────────────────┬─────────────────────────────────┬──────────────────────────────┬────────────┤
│ 1. KLASTER PERIODE            │ 2. KLASTER TERITORI & TIM       │ 3. KLASTER PRODUK & SALURAN  │ 4. AKSI    │
│ [ Harian | Mingguan | Bulanan]│ [ Rayon / Area ▾ ]              │ [ Principal ▾ ]              │ [ ⟲ Reset ]│
│ [ < ] [ Juli 2026 ] [ > ]     │ [ Salesman (Semua / 6) ▾ ]      │ [ Channel (Semua / 4) ▾ ]    │            │
└───────────────────────────────┴─────────────────────────────────┴──────────────────────────────┴────────────┘
```

1. **Klaster 1: Dimensi Waktu (Time & Period):**
   * Sakelar mode terpadu: `Harian`, `Mingguan`, `Bulanan`.
   * Date Picker terintegrasi dengan tombol navigasi cepat panah kiri/kanan (`<` `>`).
2. **Klaster 2: Dimensi Teritori & Tim Lapangan (Territory & Field):**
   * Dropdown multi-select kompak dengan badge hitungan: misalnya `Area (Semua)` atau `Salesman (2 Terpilih)`.
   * Menghilangkan tumpukan chip horizontal yang berantakan, menggantinya dengan menu *compact popover selector*.
3. **Klaster 3: Dimensi Produk & Saluran (Product & Channel):**
   * Multi-select Principal (Mayora, Unilever, Wings, Kapal Api).
   * Multi-select Channel (General Trade, Modern Trade, Retail, Institusional).
4. **Klaster 4: Aksi Cepat (Quick Actions):**
   * Tombol *Reset Filter* dan *Refresh Data* di sisi kanan.

---

### 2.3. Rekonstruksi Hirarki Menu Odoo (Clean & Logical Hierarchy)

Penyusunan menu disederhanakan agar tidak terjadi duplikasi dan memiliki hirarki yang jelas bagi setiap pemangku kepentingan:

```
FMCG Distribution (Root App)
│
├── 📊 Dashboards
│   ├── 🏢 Owner Control Tower           (Action: action_fmcg_control_tower) [New Landing]
│   ├── 📈 Sales & Field Productivity    (Action: action_sales_productivity)
│   ├── 💳 Monetary & Credit Control     (Action: action_monetary_dashboard)
│   └── 🚚 Warehouse & Logistics         (Action: action_wms_dashboard)
│
├── 👥 Penjualan (Commercial)
│   ├── Pesanan Penjualan (SO)
│   ├── Rencana Kunjungan (PJP)
│   └── Master Outlet & Channel
│
├── 💰 Keuangan & AR (Finance)
│   ├── Faktur Terbuka & Aging
│   ├── Monitoring Plafon Kredit
│   └── Setoran Kasir & Rekonsiliasi
│
├── 📦 Gudang & Persediaan (WMS)
│   ├── Monitoring Ketahanan FEFO
│   ├── Pengiriman Barang (DO)
│   └── Analisis Tolakan & Retur
│
└── ⚙️ Master Data & Konfigurasi
    ├── Prinsipal & Brand
    ├── Wilayah Administrasi & Rayon
    └── Tipe Armada & Kendaraan
```

---

## 3. Storyboarding Narasi Bisnis per Dashboard (The 3-Act Structure)

### 3.1. Dashboard 1: Sales & Commercial (`id_dashboard_sales`)

* **Narasi Utama:** *"Apakah tim penjualan mencapai target omzet secara berkualitas (pemerataan SKU dan kepatuhan kunjungan) tanpa mengorbankan margin melalui diskon berlebih?"*
* **Alur Visual (Top to Bottom):**
  1. **Babak 1 — Commercial Pulse (4 Hero Cards):**  
     `Net Revenue (DPP)` · `Pencapaian vs Target (%)` · `Rasio Diskon (%)` · `Lines per Order (LPO) vs Target (≥4.0)`
  2. **Babak 2 — Variance Diagnostics (Grafik Berdampingan):**  
     * Kiri: Grafik Tren Pendapatan Harian (SVG Bar Chart).  
     * Tengah: Komparasi Omzet per Principal & Brand (Pareto Kontribusi).  
     * Kanan: Produktivitas per Salesman (Omzet vs LPO Gauge).  
  3. **Babak 3 — Field Penetration & Exceptions (Tabel Aksi):**  
     * Matriks Penetrasi SKU: Brand vs Channel (Deteksi brand mana yang mandek di GT/MT).  
     * Antrean Kunjungan Rendah: Outlet PJP yang belum dikunjungi salesman minggu ini.

---

### 3.2. Dashboard 2: Monetary, AR & Credit Control (`id_dashboard_monetary`)

* **Narasi Utama:** *"Berapa banyak uang yang beredar di luar, seberapa besar risiko gagal bayar (bad debt), dan apakah kas berhasil dicairkan sesuai jadwal jatuh tempo?"*
* **Alur Visual (Top to Bottom):**
  1. **Babak 1 — Liquidity & Safety Pulse (4 Hero Cards):**  
     `Total Piutang Beredar` · `Piutang Jatuh Tempo (Overdue %)` · `Risiko Macet (>30 Hari)` · `Kas Masuk (Collection Rate)`
  2. **Babak 2 — Aging Structure & Financial Funnel (Visual Distribution):**  
     * Bar Proporsi Umur Piutang (Current, 1–7 Hari, 8–14 Hari, 15–30 Hari, >30 Hari) dengan rekomendasi status operasional.  
     * Corong Konversi Keuangan: Target $\to$ Faktur Terbit $\to$ Piutang Berjalan $\to$ Kas Cair di Bank.  
  3. **Babak 3 — Credit Risk Action Queue (Tabel Interaktif):**  
     * **Top Outlet di Ambang Batas Plafon (Credit Hold Queue):** Tabel outlet dengan utilisasi >100% atau jatuh tempo >8 hari. Dilengkapi tombol aksi: *[Buka Permohonan Override]* atau *[Tahan Faktur Baru]*.  
     * **Money in Transit (MIT):** Daftar uang setoran pengiriman yang masih dipegang driver/salesman dan belum divalidasi kasir.

---

### 3.3. Dashboard 3: Warehouse & Logistics (`id_dashboard_wms`)

* **Narasi Utama:** *"Apakah barang di gudang berputar dengan aman sesuai prinsip FEFO tanpa risiko kedaluwarsa, dan seberapa efisien pengiriman sampai ke tangan outlet?"*
* **Alur Visual (Top to Bottom):**
  1. **Babak 1 — Warehouse & Delivery Pulse (4 Hero Cards):**  
     `Nilai Persediaan Gudang` · `Stok Kritis FEFO (<30 Hari)` · `Tingkat Pemenuhan DO (%)` · `Rasio Biaya Armada Logistik (%)`
  2. **Babak 2 — Supply Health & Pareto Tolakan (Visual Distribution):**  
     * Bar Ketahanan Kadaluwarsa FEFO: Kritis (<30h: Retur Principal) vs Waspada (30–90h: Bundling Promo) vs Aman (>90h).  
     * Pareto Alasan Tolakan Pengantaran: Toko Tutup, Salah Barang, Kemasan Pecah/Bocor, Masalah Pembayaran.  
  3. **Babak 3 — Dispatch & Fleet Action Queue (Tabel Interaktif):**  
     * **Lot Kritis Memerlukan Tindakan:** Daftar batch/lot yang harus segera dibuatkan program promo di `id_promo_governance` atau retur vendor.  
     * **Efisiensi Armada per Kendaraan:** Komparasi Tonase, Kubikasi (CBM), Biaya BBM/Trip terhadap Nilai DO Terkirim.

---

## 4. Rencana Kerja Implementasi & Transformasi Kode

Perbaikan akan dieksekusi secara terstruktur:

1. **Refactoring CSS/SCSS (Design System):**  
   * Ganti `.id-*-sheet`, `.id-*-scorecards`, dan `.id-*-icon` dengan arsitektur class modern: `.fmcg-kpi-card`, `.fmcg-kpi-badge`, `.fmcg-filter-group`.  
   * Hapus styling 40x40 solid kotak dan ganti dengan micro-badges transparan.  
   * Tambahkan spacing proporsional (margin 24px, gap 16px, padding kartu 18px 20px).
2. **Refactoring XML Templates:**  
   * Standarisasi struktur header dan filter bar pada ketiga file XML (`sales_productivity.xml`, `monetary_dashboard.xml`, `wms_dashboard.xml`).  
   * Restrukturisasi scorecard menjadi grid 4-kolom yang proporsional dengan keselarasan baseline.
3. **Refactoring JS & Backend Models:**  
   * Menyelaraskan *state* filter agar mendukung model popover/dropdown multi-select.  
   * Memastikan seluruh endpoint agregasi mendukung evaluasi tanggal `as_of_date` untuk analisis retrospektif.
4. **Restrukturisasi Menu di `id_base`:**  
   * Mendaftarkan menu dashboard terpadu di `addons/id_base/views/menu_views.xml`.

