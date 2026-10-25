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

### 5. Rekonsiliasi Kas, Diskon Pembayaran Awal, & Piutang Usaha
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

### 6. Rekonsiliasi Fisik Persediaan & Gudang Maumbi (Per 31 Juli 2026 EOD)
- **Stok Fisik Aktual On-Hand di Gudang:** 53,837 Karton
- **Stok Teralokasi / Dipesan (Reserved untuk Kirim 1 Agustus):** 1,038 Karton
- **Stok Tersedia untuk Dijual Bebas (Available for Sale):** 52,799 Karton
- **Stok Karantina Kerusakan Transit (Bad Stock Gudang):** 9 Karton
- **Nilai Aset Persediaan Karantina (Rejection COGS):** Rp 1,963,200.00
- **Valuasi Buku Persediaan Fisik Akhir (DPP Cost):** Rp 9,001,139,000.00
- **Puncak Okupansi Fasilitas Gudang Maumbi:** 104.2% (Krisis awal Juli akibat kedatangan 5 kontainer Juni)

---

### 7. Verifikasi Checksum SHA-256 Seluruh Artefak Input
```json
{
  "customer_registry_354.csv": "fad4914dd3c8ccfa376e397615a61818d78948b3eedf6d95a0bbba6e6d4e1544",
  "initial_stock_20260701.csv": "aa17b574ec1eabb6c82cad406370f83f024299b87ced3eed1725855fda6d4277",
  "inbound_po_intransit_june_headers.csv": "9fd864f1bc006ec08d985c1475ae31f88b5339775882e85a56def81efce0c861",
  "inbound_po_intransit_june_lines.csv": "9925eb2cf04e91612ada8ead6b321a361e0dad35e4c18db102b343760e679a97",
  "pjp_july_2026_matrix.csv": "94145987f3df31ae2bd71b11e330557265e8e03d6b9ab00195d60d337f7e7654",
  "perpetual_sales_orders.csv": "93e4d63d0fc871ab0ea65f2dd8e7c01c637b257d29fdd65d26e20516b4a567ee",
  "perpetual_order_lines.csv": "fff911127e3b300b22470edcc3850e835a540d6a73c6180b66fb99d103a82af6",
  "perpetual_deliveries.csv": "0c101a9099b98a01d3c9de369cd1cbbab1553effb7da989c36e49a337384e206",
  "perpetual_order_rejections.csv": "72323faeefbd290a109e8ec56fbbe35ee9204bdf280d5f96a1aedfc47faf6dad",
  "perpetual_invoices.csv": "cec3225547d7285c8d7e6d0b4ebabf9b32b1d277e3e71c2a44907c38a3a81668",
  "perpetual_ar_collections.csv": "45e95cd27fd40c0ef9561240a1f6fb8167cb8eeb567350cd5deed0ee51b98faf",
  "perpetual_ap_payments.csv": "af6ea537f1797b21d7aae8407390fe1d90b65e9d6cc6f5e5041e4069905f5229",
  "perpetual_opex_payroll.csv": "fa81bbc78918a942bd85aeb0d24f8c612bed3ce426fc09b35c3df7445b46c489",
  "perpetual_daily_stock_cards.csv": "8e5efb57a43d6746f4edb50361bd9c0ff93522f57dbd34e8dedc71cabf36cb9a",
  "perpetual_stock_event_ledger.csv": "d3e5a567f0b8e4f132fb323cb2248d078f48921ac76e5682b5c3430b65cda4b8"
}
```
