# Laporan Rekonsiliasi Finansial & Persediaan Kanonikal FMCG Manado (Juli 2026)
**Periode:** 1 Juli 2026 s/d 31 Juli 2026 (dengan Carry-Forward Agustus)
**Generator:** Otomatis diturunkan dari seluruh artefak register di `data/registers/`
**Aturan Angka:** Menggunakan komputasi `Decimal` presisi (2 desimal) tanpa angka genap buatan.

---

### 1. Rekonsiliasi Pesanan Penjualan (Sales Order Booked Juli 2026)
- **Total SO Terbit (Booked):** 419 SO
- **Total Gross Order (DPP):** Rp 6,065,892,600.00
- **Total Potongan / Diskon Dagang:** Rp 281,242,486.00
- **Total Net Order (DPP):** Rp 5,784,650,114.00
- **Total Biaya Pokok Pesanan (COGS):** Rp 5,138,995,000.00
- **Jumlah Baris Order (Order Lines):** 2,738 baris
- **Kesesuaian Line Math ke SO:**
  * Sum Order Lines DPP: Rp 6,065,892,600.00 (Identik 100%)
  * Sum Order Lines COGS: Rp 5,138,995,000.00 (Identik 100%)

---

### 2. Rekonsiliasi Pengiriman DO Fisik & Retur Karantina
- **Total Delivery Orders (DO):** 419 DO
- **Nilai Bruto Barang Berangkat (Gross DO DPP):** Rp 6,065,892,600.00
- **Retur / Penolakan Handling Transit:** Rp 2,279,200.00 (9 kejadian / 9 karton)
- **Nilai Bersih Barang Diterima Customer (Delivered Net DPP):** Rp 6,063,613,400.00
- **Nilai Buku Retur Masuk Aset Karantina (Rejection COGS):** Rp 1,963,200.00

---

### 3. Pemisahan Periode: Realisasi Terfaktur Juli (Cut-off 31 Juli)
- **Jumlah Faktur Komersial Sah Juli:** 405 Faktur
- **Penjualan Bersih Terfaktur (Invoiced DPP):** Rp 5,594,622,485.00
- **PPN Keluaran 11% (UU HPP No. 7/2021):** Rp 615,408,473.33
- **Total Piutang Faktur Terbit (DPP + PPN):** Rp 6,210,030,958.33
- **Beban Pokok Penjualan Bersih (Accepted COGS):** Rp 4,969,777,800.00
- **Laba Kotor Komersial (Gross Profit):** Rp 624,844,685.00 (11.17%)
- **Beban Operasional & Penggajian Karyawan:** Rp 394,350,000.00
  * Logistik Armada & Rutin: Rp 95.850.000,00 (27 hari kerja operasional @ Rp 3,55 Jt)
  * Gaji Pokok 24 Personel Roster (31 Juli): Rp 185.000.000,00
  * Lembur Overstok Shift Malam (31 Juli): Rp 68.500.000,00
  * Sewa Fasilitas Gudang Tambahan (31 Juli): Rp 45.000.000,00
- **Laba Bersih Operasional Sah (Accrual Juli):** Rp 230,494,685.00 (4.12%)

---

### 4. Carry-Forward ke Periode Agustus 2026 (SO 31 Juli -> DO & Faktur 1 Agustus)
- **Jumlah Pesanan Carry-Forward:** 14 SO / DO / Faktur
- **Nilai DO Terkirim Carry-Forward:** Rp 197,030,000.00
- **Nilai Invoiced DPP Carry-Forward:** Rp 187,858,691.40
- **PPN 11% Carry-Forward:** Rp 20,664,456.06
- **Total Tagihan Carry-Forward:** Rp 208,523,147.46
- **COGS Terakui di Periode Agustus:** Rp 167,254,000.00

---

### 5. Rekonsiliasi Kas, Diskon Pembayaran Awal, & Piutang Usaha (AR)
- **Total Transaksi Pelunasan Kas Juli:** 320 transaksi
- **Total Kas Tertagih Bersih (Basis DPP):** Rp 3,434,177,723.54
- **Total Diskon Pembayaran Awal (Early Cash Discount 1%):** Rp 10,056,419.06
- **Total Penyelesaian Piutang DPP Terkoleksi:** Rp 3,444,234,142.60
- **Total Kas Tertagih Bruto (Termasuk PPN 11%):** Rp 3,813,043,479.21
- **Saldo Piutang Usaha Akhir Juli (Open AR 31 Juli):**
  * Basis DPP: Rp 2,150,388,342.40 (85 Faktur)
  * Basis Total Tagihan Bruto (dengan PPN): Rp 2,386,931,060.06
- **Jembatan Rekonsiliasi Piutang DPP:**
  `Kas DPP (Rp 3,434,177,723.54) + Early Discount (Rp 10,056,419.06) + Open AR DPP (Rp 2,150,388,342.40) = Rp 5,594,622,485.00` (Match 100% terhadap Invoiced DPP Juli).

---

### 6. Rekonsiliasi Pembayaran Hutang Usaha Prinsipal (AP)
- **Total Pesanan Pembelian In-Transit Juni (5 PO):** Rp 9,497,446,000.00
- **Total Realisasi Pembayaran AP Juli (4 PO):** Rp 6,597,474,800.00
  * PO-2026-06-01 (PT Wings Group): Rp 1.849.772.800,00 (Lunas 22 Juli 2026)
  * PO-2026-06-02 (PT Santos Jaya Abadi): Rp 1.449.737.600,00 (Lunas 29 Juli 2026)
  * PO-2026-06-03 (PT Mayora Indah Tbk - Biskuit): Rp 699.826.000,00 (Lunas 31 Juli 2026)
  * PO-2026-06-04 (PT Mayora Indah Tbk - Kopi & Wafer): Rp 2.598.138.400,00 (Lunas 31 Juli 2026)
- **Saldo Hutang Usaha Belum Jatuh Tempo (Open AP 31 Juli):** Rp 2,899,971,200.00
  * PO-2026-06-05 (PT Unilever Indonesia Tbk): Rp 2.899.971.200,00 (Jatuh tempo 8 Agustus 2026)
- **Jembatan Rekonsiliasi Hutang Usaha (AP):**
  `AP Dibayar Juli (Rp 6,597,474,800.00) + Open AP Juli (Rp 2,899,971,200.00) = Rp 9,497,446,000.00` (Match 100% terhadap Total PO In-Transit Juni).

---

### 7. Rekonsiliasi Fisik Persediaan & Gudang Maumbi (Per 31 Juli 2026 EOD)
- **Stok Fisik Aktual On-Hand di Gudang:** 53,837 Karton
- **Stok Teralokasi / Dipesan (Reserved untuk Kirim 1 Agustus):** 1,038 Karton
- **Stok Tersedia untuk Dijual Bebas (Available for Sale):** 52,799 Karton
- **Stok Karantina Kerusakan Transit (Bad Stock Gudang):** 9 Karton
- **Valuasi Persediaan Fisik Dijual Bebas (Saleable Physical DPP):** Rp 9,001,139,000.00
- **Nilai Aset Persediaan Karantina (Quarantine Asset Value COGS):** Rp 1,963,200.00
- **Total Valuasi Persediaan Gudang (Saleable + Quarantine):** Rp 9,003,102,200.00
- **Puncak Okupansi Fasilitas Gudang Maumbi:** 104.2% (Krisis awal Juli akibat kedatangan 5 kontainer Juni)

---

### 8. Verifikasi Checksum SHA-256 Seluruh Artefak Input (Kanonikal LF)
```json
{
  "customer_registry_354.csv": "9303e7fd9aab35134e481611545a9c8704f6e36b66e3e6c10ddf43c386250fb3",
  "initial_stock_20260701.csv": "6a4539fb978eab00c60ac071f222574a054cfbcff5bfc19e999fd9a3275e6408",
  "inbound_po_intransit_june_headers.csv": "3643efa63031fac441e68bfb5118ece350415056ffd92f6df1d8bd61d1d6852d",
  "inbound_po_intransit_june_lines.csv": "fec4f7491fc3b29bfaccac0b98dd7281a304e329c7d3b267753549f35d70a91c",
  "pjp_july_2026_matrix.csv": "f17fc52b03575b82498062d6dc89baad2c5235a4e09ff3f15524f4a359e3a67e",
  "perpetual_sales_orders.csv": "021e9d0ca67b10f0e07333200f0ecbdb47288cf14d9541b2812bcd8763e68a7c",
  "perpetual_order_lines.csv": "4db5f9ebea936ab1c1564755cbf5f1e98f1ae20db2c673d16372ad9f72cba3f2",
  "perpetual_deliveries.csv": "0da359c91f6634c0275aeee0d2d6eaafffdf9adf32d2e097d516de85f8d7f62f",
  "perpetual_order_rejections.csv": "33e9faa8d2abea7363e3edcc3084e1f433aa25ef96ba48373c6a2a0324d4705f",
  "perpetual_invoices.csv": "2d1d301ab78564f7f64f1faf0f035ad6f830b93b870cd7e38dae57454710d566",
  "perpetual_ar_collections.csv": "701e39b6b5979aeb692a67c1cbe7ef1ae388b05d5a2941f0179ab779c87a554d",
  "perpetual_ap_payments.csv": "7a5083096ac0d96795c24972f33946d58989f7a3b1567b2fe649d08f585467f3",
  "perpetual_opex_payroll.csv": "48017137991dac72f66d785cae67c132603c315f3d93cbd7a09a40daddf60625",
  "perpetual_daily_stock_cards.csv": "7acef464308e5a1dec4f3dc7c8ef4e3357c65405308237197d559252890c8dab",
  "perpetual_stock_event_ledger.csv": "9c62515640dcd7e875ba30d0e17d03d97961301c6e832cd2267b3f81bf514415"
}
```
