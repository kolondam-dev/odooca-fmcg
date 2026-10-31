# 📋 Dokumen Draft Prompt Siap Dispatch per Agen

Dokumen ini berisi draft prompt lengkap dan siap *copy-paste* untuk Anda berikan kepada masing-masing agen (`opencode`, `claude-dev`, dan agen spesialis lainnya) sesuai pembagian kerja yang disepakati.

---

## 📑 DAFTAR ISI DISPATCH

1. [Agen 1: `claude-dev` — Stack A: Modul Promo & Diskon Governance (`id_promo_governance`)](#prompt-1-claude-dev--stack-a-promo--discount-governance)
2. [Agen 2: `claude-dev` — Stack A: Native Pricelist Matrix & Reminder Jatuh Tempo](#prompt-2-claude-dev--stack-a-native-pricelist-matrix)
3. [Agen 3: `opencode` — Stack B: Dashboard 1 & 2 (Executive Overview & Sales Productivity)](#prompt-3-opencode--stack-b-dashboard-executive--sales-productivity)
4. [Agen 4: `opencode` — Stack B: Dashboard 3 & 4 (Monetary AR Aging & Warehouse Logistics)](#prompt-4-opencode--stack-b-dashboard-monetary--warehouse-logistics)
5. [Agen 5: `opencode` / `claude-dev` — Stack B: Dashboard 5 (Territorial Map & GeoJSON Polygon Sulut)](#prompt-5-opencode--stack-b-territorial-map--outlet-universe)
6. [Agen 6: `claude-dev` / `claude-design` — Stack C: PWA Multi-UoM Taking Order & Offline Flow](#prompt-6-claude-dev--stack-c-pwa-multi-uom-taking-order)

---

### PROMPT 1: `claude-dev` — Stack A: Promo & Discount Governance
**Target Modul:** `addons/id_promo_governance` (atau ekstensi `id_base`)  
**Tujuan:** Membangun tata kelola promo prinsipal dan distributor yang memiliki metadata lengkap, approval bertingkat, dan dapat ditagihkan kembali (*traceable claim*).

```markdown
Anda bertindak sebagai agen `claude-dev` pada repositori `odooca-fmcg` (Odoo 19 CE + OCA untuk distributor FMCG PT Manado Distribusi Utama di Manado).
Patuhi seluruh aturan AGENTS.md (branch agen/<topik>, verifikasi ruff & manifest, commit signature di baris terakhir).

TUGAS:
Bangun modul tata kelola promosi dan diskon FMCG (`id_promo_governance`) yang terhubung dengan modul penjualan dan analitik.

SPESIFIKASI & METADATA PROMO:
1. Model `id.promo.program`:
   - Metadata Dokumen: Nomor MoU/Perjanjian Dagang, Tanggal Dokumen, Tanggal Berlaku (Start Date & End Date).
   - Sumber Anggaran (`budget_source`): 'principal' (100% klaim prinsipal), 'distributor' (biaya promosi lokal MDU), atau 'joint_50_50' (sharing 50:50).
   - Prinsipal Pemilik (`principal_id` -> id.principal).
   - Akun Perantara Klaim / Analitik (`claim_account_id` -> account.account default 1104xx Piutang Klaim Promosi).
   - Bukti Approval Prinsipal: File lampiran MoU/Surat Otorisasi Prinsipal, Nama Approver Prinsipal, Jabatan.
2. Mekanisme Wizard Penentuan Target SKU:
   - Filter berjenjang: Berdasarkan Prinsipal, Kategori Produk, Brand, Sub-Brand, atau SKU Spesifik (Many2many product.product).
3. Approval Workflow:
   - State: `draft` -> `pending_approval` (Sales SPV / Branch Manager) -> `approved` -> `active` -> `expired`.
   - Hanya promo `approved` dan `active` yang dapat diterapkan pada Sales Order.
4. Integrasi Penjualan & Keterlacakan (Traceability):
   - Di Sales Order Line / Invoice Line: Rekam `promo_program_id`, `promo_budget_source`, dan nilai diskon nominal.
   - Buat laporan ringkasan klaim (Claim Report / Debit Note) yang mengelompokkan total diskon promosi per nomor MoU dan per prinsipal untuk penagihan kas masuk dari prinsipal.

OUTPUT & VERIFIKASI:
- Model, views (form, tree, search), security ACL (`ir.model.access.csv`), dan menu di bawah Sales / Konfigurasi Promo.
- Jalankan verifikasi: `python -m ruff check .` dan `python scripts/check_manifests.py`.
- Buat entri di `agent-log/claude-dev.log` dan `docs/HANDOFF.md`.
```

---

### PROMPT 2: `claude-dev` — Stack A: Native Pricelist Matrix
**Target Modul:** `id_base` / Konfigurasi Native `product.pricelist`  
**Tujuan:** Menyusun matriks harga bertingkat (Channel x Coverage Area x Tier) dengan tanggal berlaku dan reminder jatuh tempo.

```markdown
Anda bertindak sebagai agen `claude-dev` pada repositori `odooca-fmcg`.
Patuhi aturan AGENTS.md.

TUGAS:
Konfigurasikan dan fungsikan sistem master harga native Odoo (`product.pricelist`) yang menggabungkan Channel, Wilayah Coverage, dan Tier Pembelian untuk persiapan transaksi periode berikutnya.

SPESIFIKASI:
1. Struktur Matriks Harga FMCG:
   - Base Price: Harga Jual Standar Produk (`list_price`).
   - Calculated Price Matrix:
     * Modern Trade (MT): Margin khusus DC/Supermarket, TOP 30-45 hari.
     * General Trade (GT) Tier 1: Tunai / TOP 7 hari, diskon dasar 3%-5%.
     * Retail (RTL) Warung/Kios: Harga eceran kartonan/renceng tunai canvass.
     * Institusional (Horeka): Harga kontrak khusus volume besar.
2. Masa Berlaku & Reminder Jatuh Tempo:
   - Setiap baris aturan harga (`product.pricelist.item`) wajib memiliki `date_start` dan `date_end`.
   - Tambahkan automated scheduled action / cron reminder (atau field komputasi status):
     Memberikan alert / tag "Mendekati Jatuh Tempo" jika tanggal akhir harga berlaku <= 7 hari ke depan.
3. Wizard Update Harga Berkala:
   - Fitur update kenaikan/penyesuaian harga periodik (misal: penyesuaian harga bumbu/kopi serentak per brand atau prinsipal) tanpa mengubah riwayat harga lama.

OUTPUT & VERIFIKASI:
- Script konfigurasi / XML data pricelist resmi MDU.
- Unit test / model extension yang memvalidasi reminder reminder jatuh tempo.
- Verifikasi ruff dan manifest check lolos 100%.
```

---

### PROMPT 3: `opencode` — Stack B: Dashboard Executive & Sales Productivity
**Target Modul:** `addons/id_dashboard_sales` (atau `id_ui`)  
**Tujuan:** Memperkaya dashboard default dan membangun Dashboard Produktivitas Salesman FMCG.

```markdown
Anda bertindak sebagai agen `opencode` (spesialis UI/UX, analytics, dan visualisasi frontend/backend Odoo 19).
Patuhi AGENTS.md (commit signature terakhir: `task managed by opencode at <ISO8601 +07:00>`).

TUGAS:
Bangun Dashboard Produktivitas Sales FMCG (Sales Productivity Dashboard) di backend Odoo 19 untuk memonitor performa tim lapangan PT Manado Distribusi Utama.

SPESIFIKASI DASHBOARD:
1. Redesign Default Sales KPI Cards:
   - Total Omset Kotor, Total Diskon Diberikan, Omset Bersih, Total DO Terkirim.
   - Gunakan palet warna modern FMCG (Deep Navy #001a57, Vibrant Blue #004ecc, Emerald #16a34a, Amber #d97706).
2. Metrik Produktivitas Sales Lapangan (Per Salesman & Per Channel):
   - **PJP Call Compliance Ratio:** Rasio outlet yang dikunjungi vs rencana rute harian PJP.
   - **Effective Call (EC) Ratio:** Rasio kunjungan yang menghasilkan pesanan (Order).
   - **Lines per Order (LPO):** Rata-rata ragam SKU per nota (target FMCG: >= 4 SKU/order).
   - **SKU Sold per Salesman:** Sebaran penetrasi SKU per brand dan per prinsipal.
   - **Fulfillment-to-Invoice Ratio:** Rasio nilai Sales Order yang berhasil terkirim dan tertagih di faktur.
3. Filter Interaktif:
   - Filter tanggal (Harian, Mingguan, Bulanan Juli s/d Oktober 2026).
   - Filter Salesman (Christian Wowor, Andre, Meidy, Steven, Novry).
   - Filter Channel (MT, GT, RTL, INST).

OUTPUT & VERIFIKASI:
- OWL Component Dashboard Odoo 19 atau View Pivot/Graph terintegrasi dengan action window.
- Bebas error linter dan responsif pada desktop maupun tablet.
- Catat pekerjaan di `agent-log/opencode.log` dan `docs/HANDOFF.md`.
```

---

### PROMPT 4: `opencode` — Stack B: Dashboard Monetary & Warehouse Logistics
**Target Modul:** `addons/id_dashboard_monetary` / `id_dashboard_wms`  
**Tujuan:** Dashboard monitoring Piutang (AR Aging) dan Operasional Gudang Maumbi (FEFO, Reject Rate).

```markdown
Anda bertindak sebagai agen `opencode` pada repositori `odooca-fmcg`.
Patuhi aturan AGENTS.md.

TUGAS:
Bangun 2 dashboard operasional finansial dan logistik di Odoo 19 backend:

BAGIAN 1: DASHBOARD MONETARY & AR MONITORING
1. Funnel Finansial:
   - Target Omset (Rp 5.5 BIO) -> Omset Terealisasi -> Total Piutang (AR) -> Realisasi Penagihan Kas (Collection).
2. Matriks Aging Piutang FMCG:
   - Belum Jatuh Tempo (*Not Due*).
   - Overdue 1 - 7 hari (Peringatan Awal).
   - Overdue 8 - 14 hari (Tahan Pesanan Baru / Credit Hold).
   - Overdue 15 - 30 hari (Audit Supervisor).
   - Overdue > 30 hari (Penanganan Khusus / Bad Debt).
3. Breakdown AR Due:
   - Per Salesman penanggung jawab.
   - Per Wilayah / Area (Manado Urban, Bitung, Tomohon, Minut).
   - Top 10 Customer dengan saldo piutang terbesar.

BAGIAN 2: DASHBOARD WAREHOUSE & LOGISTICS
1. Status Persediaan per Kategori (Food, RTD/Beverage, Home Care, Personal Care, Confectionery).
2. Monitoring Kedaluwarsa (Expired Date / FEFO):
   - Critical (< 30 hari ke ED) -> Alert retur ke prinsipal.
   - Warning (30 - 90 hari ke ED) -> Prioritas program bundling diskon.
   - Good Stock (> 90 hari ke ED).
3. Order Fulfillment & Delivery Rate:
   - Order Delivery Rate (DO delivered vs total scheduled DO).
   - Rejection Breakdown berdasarkan 4 alasan standar:
     * Kemasan basah/penyok transit
     * Produk mendekati ED
     * Salah kirim SKU/qty
     * Toko tutup / menolak nota
4. Rasio Biaya Pengiriman per Armada (Fuel & Helper Cost vs Nilai DO Terkirim).

OUTPUT & VERIFIKASI:
- Action view, graph, chart visualisasi Odoo 19.
- Data binding yang langsung membaca tabel account_move, sale_order, stock_picking, dan stock_quant live.
- Log entri di `agent-log/opencode.log` dan `docs/HANDOFF.md`.
```

---

### PROMPT 5: `opencode` — Stack B: Territorial Map & Outlet Universe
**Target Modul:** `addons/id_territorial_map` (atau OWL Leaflet/GeoJSON)  
**Tujuan:** Dashboard spasial interaktif sebaran 354 outlet di Sulawesi Utara dengan data poligon wilayah.

```markdown
Anda bertindak sebagai agen `opencode` pada repositori `odooca-fmcg`.
Patuhi aturan AGENTS.md.

TUGAS:
Bangun Territorial Dashboard Spasial interaktif di Odoo backend untuk memetakan sebaran outlet, cakupan area, dan omset regional PT Manado Distribusi Utama.

SPESIFIKASI:
1. Visualisasi Peta (Leaflet / OpenStreetMap / GeoJSON):
   - Muat polygon batas wilayah kabupaten/kota di Sulawesi Utara (Kota Manado, Kota Tomohon, Kota Bitung, Kabupaten Minahasa Utara, dll).
   - Bedakan layer polygon: Active Covered Area (65%) vs Opportunity Gap (35% unserved).
2. Pinpoint Outlet Universe:
   - Tampilkan seluruh 354 outlet aktif dengan pin berkode warna berdasarkan channel:
     * Modern Trade (MT): Biru Tua
     * General Trade (GT): Hijau
     * Retail (RTL): Amber / Kuning
     * Institusional (INST): Ungu
3. Interaksi On-Click Pinpoint:
   - Klik pada pin outlet membuka popup / panel ringkasan:
     * Nama Toko & Kontak PIC (mengambil data child contact res.partner yang sudah diinjeksi).
     * Channel & Jadwal Kunjungan PJP (misal: Senin - Christian Wowor).
     * Total Omset Pembelian Juli - Oktober 2026.
     * Saldo Piutang Berjalan (Outstanding AR) & Status Limit Kredit.
     * Tombol shortcut langsung menuju record partner di Odoo.
4. Filter Dinamis:
   - Filter per Kabupaten/Kota, per Salesman PJP, dan per Status Piutang (Lancar vs Overdue).

OUTPUT & VERIFIKASI:
- Backend view action Odoo 19 yang mulus tanpa dependensi library eksternal berbayar.
- Jalankan ruff check dan verifikasi performa rendering peta.
- Catat di `agent-log/opencode.log` dan `docs/HANDOFF.md`.
```

---

### PROMPT 6: `claude-dev` / `claude-design` — Stack C: PWA Multi-UoM Taking Order
**Target Modul:** `pwa/src/`  
**Tujuan:** Refinement alur order sales lapangan di PWA dengan kalkulator multi-UoM (Karton vs Pcs/Renceng), konversi rasio dinamis, dan keranjang belanja mobile-first.

```markdown
Anda bertindak sebagai agen frontend/fullstack (`claude-dev` / `claude-design`) pada aplikasi PWA `pwa/` repositori `odooca-fmcg`.
Patuhi arsitektur offline-first, Zod schema validation, dan zero-drift contract policy.

TUGAS:
Sempurnakan antarmuka Taking Order (Order Dialog & Catalog) di PWA agar mendukung seleksi satuan bertingkat (Multi-UoM) secara intuitif dan mobile-first.

SPESIFIKASI:
1. Selector Multi-UoM pada Katalog & Keranjang:
   - Setiap produk dapat dipesan dalam satuan **Karton** (CTN) maupun satuan eceran dasar (**Pcs**, **Renceng**, **Pack**, atau **Sachet**).
   - Tampilkan rasio konversi nyata pada kartu produk (contoh: *1 Karton = 120 Pcs*, *1 Box = 12 Pcs*).
   - Harga otomatis terhitung berdasarkan satuan yang dipilih dan jumlah kuantitas.
2. Mobile First Shopping Cart UX:
   - Sticky order summary bar di bagian bawah sebelum submit (menampilkan total item, total karton ekuivalen, dan subtotal estimasi).
   - Integrasi kamera bukti fisik (CameraViewfinder) yang langsung mengambil foto display toko / rak saat order ditandatangani.
3. Validasi & Integritas Data Offline:
   - Pastikan pesanan tersimpan aman di IndexedDB perangkat saat offline.
   - Sinkronisasi payload order ke outbox engine dengan format multi-UoM yang valid.

PENGUJIAN & VERIFIKASI:
- Jalankan `npm run contracts:check`
- Jalankan `npm run typecheck`
- Jalankan `npm run test` (seluruh 18 test suite Vitest wajib hijau)
- Jalankan `npm run build:demo`
- Catat pekerjaan di `agent-log/` dan `docs/HANDOFF.md`.
```
