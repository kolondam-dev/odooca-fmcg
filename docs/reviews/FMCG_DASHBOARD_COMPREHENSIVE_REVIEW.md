# FMCG Distribution Dashboard: End-to-End Comprehensive Review, Gap Analysis & Strategic Architecture Plan

**Tanggal:** 2026-11-01  
**Peran:** Data Analyst Profesional · ERP Implementor · FMCG Distribution Business Expert  
**Target Platform:** Odoo 19 CE + OCA 19.0 (PT Manado Distribusi Utama / FMCG Demo Environment)  
**Status Lingkungan Teruji:** Live Production Demo (`https://odooca-fmcg-demo.up.railway.app`) & Codebase Repository  

---

## 1. Executive Summary & Problem Framing: Mengapa Dashboard Terasa "Kurang Sreg"?

Sebagai praktisi yang menggabungkan perspektif **Data Analyst**, **ERP Implementor**, dan **Pelaku Bisnis Distribusi FMCG**, evaluasi terhadap implementasi dashboard saat ini (`id_dashboard_sales`, `id_dashboard_monetary`, dan `id_dashboard_wms`) menunjukkan bahwa fondasi teknis OWL 2 dan Odoo 19 sudah terpasang dengan rapi. Namun, ada alasan fundamental mengapa dashboard ini terasa **"kurang sreg"** bagi seorang pemilik distributor (Owner) maupun pengambil keputusan di lapangan:

1. **Disconnected Silos, Bukan "Control Tower" Terpadu:**  
   Dashboard saat ini terpecah menjadi 3 pulau tersendiri (Sales, Monetary, WMS). Dalam bisnis distribusi FMCG di Indonesia (seperti di Sulawesi Utara), operasional penjualan, gudang, dan keuangan adalah satu siklus kausalitas harian yang tidak terpisahkan:  
   $$\text{PJP Visit} \longrightarrow \text{Taking Order (SO)} \longrightarrow \text{Picking/Packing (DO)} \longrightarrow \text{Delivery \& Bukti Terima} \longrightarrow \text{Faktur (AR)} \longrightarrow \text{Setoran Kas (Closing)}$$  
   Ketika seorang Direktur/Branch Manager membuka sistem di pagi hari, mereka tidak ingin berpindah-pindah 3 modul berbeda hanya untuk menjawab pertanyaan: *"Bagaimana kinerja kita kemarin, berapa kebocoran barang/uang di jalan, dan apa risiko terbesar hari ini?"*

2. **Hilangnya Dimensi "Principal" Sebagai Jantung Bisnis Distributor Multi-Principal:**  
   Distributor FMCG adalah perpanjangan tangan Principal (Mayora, Unilever, Wings, Danone, dsb.). Kontrak PKS, margin, target omzet (*sell-in* vs *sell-out*), plafon kredit, hingga diskon/promo semuanya berputar di sekitar **Principal**. Pada dashboard yang ada saat ini, filter dan visualisasi utama hanya membagi berdasarkan Salesman dan Channel (atau Kategori Produk), namun tidak menempatkan **Principal** sebagai dimensi komparasi tingkat pertama.

3. **Angka Statis Tanpa "Actionable Exception Queue":**  
   Dashboard yang ada saat ini bersifat *laporan pasif* (hanya menampilkan angka dan grafik), bukan *kokpit operasional*. Jika dashboard menunjukkan "Piutang Jatuh Tempo Rp 2,5 Miliar" atau "LPO 2.0 (Target ≥ 4.0)", apa yang harus dilakukan oleh user? Dashboard FMCG kelas enterprise harus menyediakan **Exception Queues**: daftar outlet yang terkena *Credit Hold*, faktur pending validasi kasir, batch barang kritis yang harus segera dibuatkan program *bundling/promo*, serta SO yang tertahan stok.

4. **Temporal Inconsistency & Hardcoded Traps pada Data Mechanism:**  
   Analisis live probe membuktikan adanya *temporal drift*: SQL view moneter dan WMS mengikat kalkulasi ke `CURRENT_DATE` PostgreSQL tanpa parameter tanggal jangkar (*anchor date*), sementara Sales Dashboard memiliki filter tanggal tersendiri. Akibatnya, pada dataset historis (Juli 2026), dashboard moneter melaporkan **100% piutang berstatus macet (>30 hari)** dan dashboard WMS melaporkan **0 lot kritis** karena tanggal lot telah melewati batas atau belum diisi pada seed master.

---

## 2. End-to-End Component Analysis

### 2.1. Sales Productivity Dashboard (`id_dashboard_sales`)

* **Data Mechanism:**  
  * Menggunakan aggregation service Python (`id.sales.productivity`) yang membaca via ORM Odoo (`search_fetch` dan `_read_group`), sehingga *record rules* dan multi-company terisolasi dengan aman.  
  * Mendukung mode waktu fleksibel: `day`, `week`, `month` dengan tombol navigasi *shift* dan batas kalender WITA (`Asia/Makassar`).  
  * **Kelemahan Data Mechanism:** Melakukan kalkulasi LPO (*Lines per Order*) dan *posted invoiced quantity* secara iteratif di Python memori (`for line in lines...`). Untuk volume transaksi distributor besar (>50.000 baris order/bulan), iterasi ini akan memicu latensi tinggi dan konsumsi RAM besar pada instance Railway.
* **Presentasi & UI Flow:**  
  * Layout mengadopsi format *single-sheet spreadsheet* dengan hairline border, ikon tonal berlatar warna (navy, blue, emerald, amber, red), grafik tren SVG batang harian, dan matriks penetrasi SKU.  
  * Komparasi terhadap periode sebelumnya ($\Delta$ vs *previous period*) ditampilkan secara komprehensif pada setiap scorecard.  
* **Evaluasi Aspek Bisnis FMCG:**  
  * *LPO (Lines per Order)* dan *SKU Penetration* adalah KPI standar emas prinsipal (menghindari salesman hanya menjual produk *fast-moving*).  
  * **Gap Kritis:** Metrik PJP (*Call Compliance* & *Effective Call*) saat ini berstatus `N/A: No PJP plan exists for this period`. Di FMCG, jika data PJP tidak ada, yang dibutuhkan adalah visibilitas *Active Outlet (AO)* dan *Strike Rate* langsung dari histori transaksi faktur vs master outlet.

---

### 2.2. Monetary & Accounts Receivable Dashboard (`id_dashboard_monetary`)

* **Data Mechanism:**  
  * Mengandalkan SQL View PostgreSQL (`id_ar_aging`, `id_ar_customer_balance`, `id_monetary_funnel_stage`) yang membaca tabel live `account_move` dan `account_payment`.  
  * **Bug Fatal Teridentifikasi:**  
    1. **Parameter Mismatch:** Frontend JS memanggil RPC `get_data(area_ids=..., salesman_ids=...)`, sedangkan method Python di `id.monetary.dashboard` hanya menerima `(area_id=None, salesman_id=None)` tanpa `**kwargs`. Begitu pengguna mengklik chip filter Wilayah atau Salesman, antarmuka langsung **CRASH** dengan error:  
       `TypeError: MonetaryDashboard.get_data() got an unexpected keyword argument 'area_ids'`  
    2. **Hardcoded `CURRENT_DATE` Trap:** View `id_ar_aging` menghitung bucket menggunakan `CURRENT_DATE - am.invoice_date_due`. Karena demo dijalankan pada November 2026 sedangkan transaksi terjadi di Juli 2026, seluruh faktur bergeser ke bucket `overdue_over_30` (100% macet). Tidak ada filter tanggal/periode di UI Moneter, berbeda dengan Sales Dashboard.
* **Presentasi & UI Flow:**  
  * Menampilkan scorecard total piutang, rasio jatuh tempo, visualisasi segmen *aging bar* (5 warna), corong keuangan (Target $\to$ Realisasi $\to$ Piutang $\to$ Kas), dan tabel Top 10 Customer Exposure.  
* **Evaluasi Aspek Bisnis FMCG:**  
  * Konsep *Credit Hold* otomatis pada umur piutang 8–14 hari sangat sesuai dengan playbook FMCG Indonesia.  
  * **Gap Kritis:** Tidak menampilkan **Money in Transit (MIT)**. Di FMCG Manado/Sulut, uang tunai atau bukti transfer yang dibawa oleh driver/salesman di jalan setelah serah terima barang adalah risiko kebocoran kas nomor satu sebelum tervalidasi oleh kasir saat *daily closing*.

---

### 2.3. Warehouse & Logistics Dashboard (`id_dashboard_wms`)

* **Data Mechanism:**  
  * Menggunakan SQL Views (`id_wms_stock_category`, `id_wms_expiry`, `id_wms_delivery`, `id_wms_fleet_cost`, `id_wms_reject`).  
  * **Blindspot Data Teridentifikasi:**  
    1. **Lot Expiry Mandul:** View `id_wms_expiry` mensyaratkan `lot.expiration_date IS NOT NULL`. Di master data seed saat ini, seluruh record `stock.lot` memiliki nilai `expiration_date: False`. Akibatnya, visualisasi FEFO selalu bernilai Rp 0 dan tabel monitoring kosong.  
    2. **Fleet Cost Mandul:** View `id_wms_fleet_cost` melakukan `JOIN` ke tabel `id_delivery_trip_cost`. Jika admin logistik belum menginput biaya trip (BBM/helper) secara manual per kendaraan, seluruh grafik efisiensi armada kosong.  
    3. **Tidak Ada Filter Periode/Tanggal:** Metrik pengiriman mengagregasi seluruh data sepanjang masa tanpa batas bulan/minggu.
* **Presentasi & UI Flow:**  
  * Menyajikan metrik nilai persediaan fisik, stok kritis FEFO (<30 hari), tingkat pemenuhan DO, rasio biaya armada, distribusi ketahanan stok FEFO, dan tabel rincian tolakan pengantaran.  
* **Evaluasi Aspek Bisnis FMCG:**  
  * Membedakan rekomendasi aksi FEFO (Retur Principal vs Program Promo/Bundling) adalah wawasan bisnis yang sangat tepat untuk FMCG food/beverage.  
  * **Gap Kritis:** Tidak menampilkan **Stock on Delivery (SOD)**. Barang yang sudah keluar dari gudang (DO tervalidasi) tetapi kendaraannya masih dalam perjalanan belum tercatat status *live*-nya antara stok gudang vs tangan customer.

---

## 3. Matriks Klasifikasi Kebutuhan Berdasarkan Disiplin / Layer

Dalam arsitektur ERP FMCG standar industri, dashboard tidak boleh dibuat *one-size-fits-all*. Kebutuhan harus dibagi ke dalam 4 kompartemen disiplin:

| Disiplin / POV | Necessary (Wajib Mutlak) | Nice to Have (Bernilai Tambah) | Not Necessary / Redundant (Hindari) |
|---|---|---|---|
| **1. Executive / Owner Control Tower** | • Gross vs Net DPP Revenue<br>• Gross Margin (%) per Principal<br>• Overdue AR Exposure & Bad Debt Risk<br>• Cash Collection Rate vs Target<br>• Kebocoran Operasional (MIT & Retur) | • Peta Geo-sebaran Omzet Wilayah Manado/Minahasa/Bitung<br>• Run-rate proyeksi akhir bulan | • Log teknis sistem<br>• Detail nomor mesin/rangka armada<br>• Daftar ribuan transaksi tanpa filter ranking |
| **2. Sales & Commercial** | • Omzet per Salesman & per Principal<br>• Active Outlet (AO) & Effective Call Rate<br>• Lines per Order (LPO) vs Target (≥ 4.0 SKU)<br>• SKU Penetration Matrix (Brand vs Channel)<br>• Diskon/Promo yang diberikan per Principal | • PJP Geo-tracking live route<br>• Perbandingan target vs realisasi bulanan | • Saldo piutang glondongan tanpa nama outlet<br>• Biaya depresiasi aset gudang |
| **3. Finance & Credit Control** | • AR Aging 5-Bucket (Current s/d >30 Hari)<br>• Top 10 Credit Limit Exposure & Credit Hold<br>• Money in Transit (MIT) belum tervalidasi kasir<br>• Faktur gantung / Dispute invoice<br>• Rekonsiliasi setoran tunai vs mutasi bank | • DSO (Days Sales Outstanding) tren grafik<br>• Proyeksi *cash-in* 7 hari ke depan | • Rincian lokasi rak/bin gudang fisik<br>• Volume kubikasi truk pengiriman |
| **4. Warehouse & Logistics** | • FEFO Expiry Bucket (<30d, 30-90d, >90d)<br>• Delivery Fulfillment Rate (DO to Invoice)<br>• Stock on Delivery (SOD) posisi mengambang<br>• Alasan Rejeksi/Tolakan Pengiriman (Toko Tutup, Salah Barang, Rusak)<br>• Biaya BBM & Helper per Ritase / Drop | • Utilisasi Kubikasi & Tonase Armada (%)<br>• Visualisasi zonasi gudang / slotting fast moving | • Margin keuntungan per SKU (akses restricted untuk tim logistik)<br>• Nilai PPh 21 / e-Bupot pajak |

---

## 4. Analisis Gap & Rekomendasi Solusi Brilian

### Gap 1: Dashboard Terfragmentasi vs Kebutuhan "Owner Control Tower"
* **Masalah:** Direktur/Owner harus melompat ke tiga layar berbeda untuk memahami denyut nadi perusahaan.  
* **Solusi Brilian:** Bangun **"Executive Cockpit / Control Tower"** sebagai tampilan depan terpadu (`id_dashboard_control_tower` atau landing utama di `/odoo/dashboards`). Layar ini memuat **3 Row Filosofis FMCG**:
  * **Row 1 — The Commercial Engine:** Revenue Netto, Pencapaian Target Bulanan, Margin Kotor %, dan Diskon Terpakai.
  * **Row 2 — The Liquidity & Risk Guard:** Total Piutang, Piutang Overdue, Money in Transit (Uang di Jalan), dan Bad Debt Risk.
  * **Row 3 — The Supply & Fulfillment Muscle:** Nilai Stok Gudang, Stok Kritis FEFO (<30 hari), DO Fulfillment Rate, dan Stock on Delivery (Barang di Jalan).

### Gap 2: Filter yang Belum Terstandardisasi (Inconsistent Slicing)
* **Masalah:** Sales Dashboard menggunakan filter tanggal `day/week/month` dengan *anchor picker*. Monetary Dashboard tidak memiliki filter tanggal (selalu menganggap hari ini). WMS Dashboard hanya memfilter kategori produk dan armada tanpa filter tanggal.  
* **Solusi Brilian:** Ciptakan **Unified FMCG Filter Bar Component** yang seragam di ketiga dashboard:
  1. **Dimensi Waktu:** Preset Periode (Hari Ini, Minggu Ini, Bulan Ini, Custom Date Range dengan dukungan Backdating/Anchor Date).
  2. **Dimensi Komersial:** Principal Selector (Mayora, Kapal Api, Torabika, dsb.) $\to$ Channel (MT, GT, Retail, Inst).
  3. **Dimensi Teritori & Tim:** Coverage Area (Manado Tengah, Bitung, Minahasa, Tomohon) $\to$ Salesman / Armada.

### Gap 3: Kerapuhan SQL Views Terhadap `CURRENT_DATE`
* **Masalah:** Kalkulasi `CURRENT_DATE - am.invoice_date_due` di level PostgreSQL SQL View membuat data historis tidak dapat diaudit secara retrospektif (misalnya melihat posisi aging per 31 Juli 2026).  
* **Solusi Brilian:** Ubah SQL View atau kueri agregasi di ORM agar mendukung parameter tanggal evaluasi (`evaluation_date` / `as_of_date`). Jika parameter tidak diisi, gunakan `CURRENT_DATE`; jika diisi (misal simulasi per 31 Juli 2026), umur piutang dan ketahanan FEFO dihitung relatif terhadap tanggal evaluasi tersebut.

### Gap 4: Angka Statis vs "Actionable Exception Queues"
* **Masalah:** Ketika ada 15 outlet over-limit atau 5 lot mendekati kadaluwarsa, user tidak memiliki tombol langsung untuk mengambil tindakan.  
* **Solusi Brilian:** Setiap kartu peringatan bahaya (*Red Tone*) harus memiliki aksi satu-klik:
  * Klik pada **"Credit Hold Outlets"** $\to$ Membuka wizard persetujuan kredit (*Approval Workflow*) atau daftar blokir order.
  * Klik pada **"Stok Kritis FEFO (<30 Hari)"** $\to$ Membuka form pembuatan draft *Return to Vendor* (Principal) atau pembuatan Program Promo Bundling di `id_promo_governance`.
  * Klik pada **"Faktur Tertolak (Reject)"** $\to$ Membuka antrean investigasi logistik (apakah toko tutup untuk dijadwal ulang, atau barang cacat untuk dikarantina).

---

## 5. Rencana Perbaikan Teknis & Quick Wins (Immediate Fixes)

Untuk mengembalikan kesehatan modul di repository dan production Railway:

1. **Fix Parameter Mismatch di Monetary Dashboard:**  
   Perbaiki method signature di `addons/id_dashboard_monetary/models/monetary_dashboard.py` agar menerima `area_ids=None, salesman_ids=None, **kwargs` dan selaraskan dengan pemanggilan dari `monetary_dashboard.js`.
2. **Koreksi Data Seed Lot Expiry:**  
   Perbarui script seed master / data loader agar setiap `stock.lot` memiliki nilai `expiration_date` yang realistis (sebagian <30 hari, sebagian 30-90 hari, dan mayoritas >90 hari) sehingga visualisasi FEFO di WMS langsung hidup.
3. **Tambahkan Seed Trip Cost & Retur Realistis:**  
   Injeksi catatan pengeluaran armada di `id.delivery.trip.cost` dan beberapa sampel alasan penolakan di `stock_picking.fmcg_reject_reason` agar grafik rasio biaya logistik dan pareto tolakan pengantaran menyajikan data informatif bagi manajemen.
4. **Perlindungan Margin Server-Side:**  
   Pastikan field biaya/margin kotor dilindungi oleh `groups="sales_team.group_sale_manager,account.group_account_manager,base.group_system"` di layer backend Python, bukan sekadar disembunyikan via CSS.

---

## 6. Kesimpulan & Nilai Tambah

Dengan mentransformasikan dashboard dari sekadar **kumpulan grafik terisolasi** menjadi **Sistem Kemudi Terpadu (Actionable FMCG Cockpit)** yang berpusat pada hierarki **Principal $\times$ Territory $\times$ Outlets**, manajemen distributor FMCG di Manado akan memperoleh kontrol penuh atas 3 pilar penentu profitabilitas: **pertumbuhan omzet berdisiplin (LPO & Penetrasi), keamanan kas (Anti-Bad Debt & MIT Control), dan efisiensi rantai pasok (FEFO & Utilisasi Armada)**.
