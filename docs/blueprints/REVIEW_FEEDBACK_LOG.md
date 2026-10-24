# Log Catatan Review & Keputusan Desain Master Data & Simulasi FMCG
**Distributor:** PT Manado Distribusi Utama (Fiktif)  
**Wilayah Operasional:** Kota Manado & Seluruh Provinsi Sulawesi Utara (15 Kab/Kota)  
**Dokumen Referensi:** `docs/blueprints/master_data_mapping_and_seed_plan.md`, `docs/blueprints/pjp_and_outlet_distribution_model.md`, `docs/blueprints/historical_simulation_and_turnover_model.md`  

---

## 1. Kronologi Review & Arahan Pengguna (User Feedback Log)

### Sesi Review 1 — Tipologi Armada, Struktur SDM, & Rute Kunjungan
- **Feedback Pengguna:**
  1. *Tipologi Armada:* Wajib menambahkan kolom tipe operasional riil logistik distributor FMCG: CDDL (6-Roda Long), CDD (6-Roda Std), CDEL (4-Roda Long), CDE (4-Roda Std), L300, Traga, Gran Max Box (GM BOX), Gran Max Blind Van (GM BV), dan Gran Max Bak Terbuka (GM OPEN).
  2. *Roster Karyawan:* Menambah profil owner/management, cashier, accounting staff, tax staff, dan sales supervisor. Total karyawan harus mencapai 20-25 orang, termasuk helper delivery dan fulfillment staff (warehouse).
  3. *Diligent PJP & Outlet:* Sebaran outlet dan rute harus dirancang tekun (diligent) agar salesman tidak hanya memiliki 2-3 kunjungan per hari atau cross-channel yang tidak efisien.
- **Tindakan Agen Antigravity:**
  - Menambahkan model `id.fleet.type` dan data XML 9 tipe armada operasional lengkap dengan dimensi kargo (p×l×t), tonase, dan kubikasi riil pabrikan.
  - Memperluas struktur personel menjadi roster 24 orang (`employees_24.csv`) lengkap dengan pembagian divisi dan cost center.
  - Menyusun cetak biru rute kunjungan harian [pjp_and_outlet_distribution_model.md](pjp_and_outlet_distribution_model.md) dengan target call harian (MT 8-10, GT 20-22, Canvass 25-30).

---

### Sesi Review 2 — Administrasi Sulawesi Utara & Geografi Rute
- **Feedback Pengguna:**
  1. *Kecamatan Kawangkoan:* Wajib mencantumkan Kawangkoan sebagai sentra perdagangan Minahasa.
  2. *Klasifikasi Wilayah:* Maesa termasuk dalam kota (Bitung), Bitung masuk luar kota (hinterland/port).
  3. *Unit Wilayah Administrasi:* Pembagian rute distribusi mostly berbasis Kecamatan, bukan serta-merta Kabupaten/Kota.
  4. *Penanggung Jawab Key Account:* Akun Modern Trade biasanya di-handle oleh Sales Supervisor atau Branch Manager.
- **Tindakan Agen Antigravity:**
  - Menambahkan model `id.district` (Kecamatan) dan `id.subdistrict` (Kelurahan & Kode Pos) pada `id_base`.
  - Mendaftarkan dataset 18 kecamatan kunci se-Sulut (`id_district_data.xml`) termasuk Kawangkoan, Bitung Maesa, Tomohon, Tondano, dan Manado.
  - Menugaskan akun Modern Trade (12 Key Accounts) di bawah supervisi khusus `SLS-01` (Key Account Executive / Spv).

---

### Sesi Review 3 — Cakupan 15 Kab/Kota Se-Sulut, Rekalibrasi Modern Trade, & Matriks 150 SKU
- **Feedback Pengguna:**
  1. *Cakupan Administrasi:* Data tidak boleh hanya sampling. Harus memuat lengkap seluruh 15 daerah administrasi Provinsi Sulawesi Utara (4 Kota dan 11 Kabupaten).
  2. *Rekalibrasi Modern Trade (MT):* Jumlah outlet MT sebelumnya terlalu banyak (25 outlet) namun omsetnya terlalu kecil. Instruksi: susutkan kuantitas outlet MT yang di-cover, naikkan omset per account agar mencerminkan pareto distributor FMCG.
  3. *Katalog SKU:* Total SKU harus terdefinisi tepat 150 SKU dengan rincian sebaran per brand, kategori, dan prinsipal nasional.
- **Tindakan Agen Antigravity:**
  - Menambahkan model `id.city` dan dataset `id_city_data.xml` yang memuat seluruh 15 Kabupaten/Kota di Sulawesi Utara (BPS 7101–7174).
  - Menyusutkan Modern Trade menjadi **12 Key Accounts** (Indomaret DC, Alfamidi DC, FreshMart Group, MultiMart Group, Golden Swalayan, Jumbo Swalayan, Transmart) dengan kontribusi omset naik menjadi **Rp 2,1 BIO IDR / bulan (38.2%)** dari total omset Rp 5,5 BIO IDR.
  - Menata tepat **150 Master SKU** pada 4 Principal Nasional:
    - Mayora Indah: 44 SKU (Food 18, RTD 16, Confectionery 10)
    - Santos Jaya Abadi / Kapal Api: 32 SKU (Food 24, RTD 8)
    - Unilever Indonesia: 42 SKU (Home Care 16, Personal Care 20, Food 6)
    - Wings Food: 32 SKU (Food 22, RTD 10)

---

### Sesi Review 4 — Narasi Kausalitas Bisnis Presisi (Juli s/d 24 Oktober 2026)
- **Feedback Pengguna:**
  1. *Kondisi Awal Juli:* Stok awal Rp 10 BIO (carry-over Juni Rp 2 BIO + Inbound PO Juni Rp 5,75 BIO). Gudang terokupansi over 5% secara data (105% rated), namun secara visual menampung 2x lipat (lorong penuh, stacking amburadul, FEFO lumpuh).
  2. *Krisis Cashflow & Payables:* Hutang dagang (AP) jatuh tempo sangat tinggi (Rp 4 BIO JT Juli, Rp 5,5 BIO split 50:50 Juli dan awal Agustus).
  3. *Manuver Push Order & Diskon:* Coverage baru 50% (272 outlet), salesman dipaksa push order ke pareto outlet (MT dan GT grosir), suntikan diskon taktis hingga 5% di akhir Juli.
  4. *Kinerja Juli:* Omset Rp 5,5 BIO tercapai, tetapi akibat overtime gudang/logistik dan diskon tinggi, net profit margin tertekan ke **0.9%**.
  5. *Hangover Agustus:* Omset drop -23% (Rp 4,235 BIO) karena market jenuh dan konsumen minus cash pasca tahun ajaran baru. **Zero inbound** (gudang flushing stok), pembayaran AP baru ditahan. PO baru dirilis Week 3 Agustus (lead time kapal kontainer tiba awal September). Buka coverage baru +6% (+16 outlet). Margin melega ke **2.5%**.
  6. *Konsolidasi September:* Omset melandai -6.5% (Rp 3,96 BIO). Kontainer tiba di Bitung, disiplin FEFO berjalan, coverage tumbuh +8% (313 outlet). Margin meluas ke **3.7%**.
  7. *Rebound Oktober MTD (s/d 24 Okt):* Omset melesat menembus Rp 5,3 BIO MTD, 354 outlet aktif (coverage 65%), utilisasi armada mencapai rata-rata **89%** (memunculkan sinyal kebutuhan armada baru), net margin optimal **5.0%**.
  8. *Ketentuan Finansial:* Seluruh angka dalam simulasi dinyatakan **DILUAR PPN (DPP Net)**.
  9. *Keputusan Granularitas:*
     - Menggunakan **Daily Granular Transactions**: menghasilkan 3.762 faktur harian riil (35-42 faktur/hari) dengan lot FEFO dan mutasi kas bank.
     - Beban Operasional (OPEX) dicatat langsung sebagai **Vendor Bills di modul Accounting Odoo** (`account.move`).

---

## 2. Struktur Berkas yang Dihasilkan

| Nama Berkas | Lokasi di Repository | Deskripsi & Fungsi |
| :--- | :--- | :--- |
| `master_data_mapping_and_seed_plan.md` | `docs/blueprints/` | Cetak biru hierarki master data, 15 Kab/Kota, 150 SKU, 354 outlet, 24 staf, 9 armada |
| `pjp_and_outlet_distribution_model.md` | `docs/blueprints/` | Pemodelan rute kunjungan PJP Senin–Sabtu, rasio call density, loading delivery H+1 |
| `historical_simulation_and_turnover_model.md` | `docs/blueprints/` | Cetak biru simulasi transaksi historis dan perputaran persediaan Juli–Oktober 2026 |
| `REVIEW_FEEDBACK_LOG.md` | `docs/blueprints/` | Dokumentasi riwayat review, feedback, dan keputusan desain arsitektur |
| `products_150.csv` | `data/seed/` | 150 Master SKU FMCG terdefinisi lengkap |
| `partners_354.csv` | `data/seed/` | 354 Partner Outlet aktif se-Sulut |
| `employees_24.csv` | `data/seed/` | Roster 24 personil distributor FMCG |
| `vehicles_9.csv` | `data/seed/` | 9 Unit armada logistik dengan dimensi dan KIR |
| `inbound_po_historical.csv` | `data/seed/` | 11 Inbound PO Kontainer Bitung & jadwal AP |
| `sales_orders_historical.csv` | `data/seed/` | 3.762 Transaksi faktur harian riil (Juli–24 Okt 2026) |
| `sales_order_lines_historical.csv` | `data/seed/` | 8.513 Baris line items detail transaksi penjualan |
| `opex_vendor_bills.csv` | `data/seed/` | 20 Vendor Bills beban operasional bulanan |
| `daily_logistics_metrics.csv` | `data/seed/` | 97 Hari log okupansi gudang & utilisasi armada |
| `historical_simulation_summary.json` | `data/seed/` | Ringkasan rekonsiliasi finansial terkalibrasi presisi |
| `generate_fmcg_seed.py` | `scripts/` | Skrip penghasil master seed dataset |
| `generate_historical_simulation.py` | `scripts/` | Skrip penghasil simulasi transaksi historis |
| `load_fmcg_seed.py` | `scripts/` | Loader master data ke Odoo shell |
| `load_historical_simulation.py` | `scripts/` | Loader transaksi historis ke Odoo shell |
