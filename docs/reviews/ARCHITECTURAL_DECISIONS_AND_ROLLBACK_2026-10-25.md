# DOKUMENTASI KEPUTUSAN ARSITEKTUR & PANDUAN ROLLBACK (2026-10-25)

**Konteks Dokumen:** Arsip resmi sesi konsultasi arsitektur perihal rekonsiliasi PJP, okupansi armada kubikasi/tonase, inventory turnover granular, saldo awal 1 Juli, PO in-transit, kategorisasi produk FMCG, penghindaran angka genap, perpajakan DPP & PPN 11%, dan mitigasi jebakan SVL (*Stock Valuation Layer*) Odoo 19.

---

## 1. Ringkasan Percakapan & Keputusan Desain (Turn Summary)

### A. Okupansi Armada Per Hari (Kubikasi & Tonase)
1. **Karakteristik FMCG Manado:** Portofolio produk distributor FMCG memiliki densitas rata-rata $\approx 180\text{ kg}/m^3$, bersifat ***Space-Constrained*** (box kendaraan penuh volume kubikasi jauh sebelum menyentuh batas tonase sasis).
2. **Hasil Audit Okupansi 27 Hari Kerja Juli 2026:**
   * `DB 8345 MK` (Canter CDD 17.2 CBM / 6.0 Ton): Rata-rata 48,9% CBM, 25,2% Ton (MT DC & Grosir Pareto).
   * `DB 8456 FB` (L300 Box 5.4 CBM / 1.5 Ton): Rute Urban Barat (Wenang, Sario, Malalayang) padat ($6,4\text{ }m^3$/hari $\to$ 118,4% *single trip*). **Solusi:** Dioperasikan secara **2 ritase per hari** (ritase pagi 59% CBM + ritase siang 59% CBM) serta dibantu unit cadangan `DB 8678 CD` pada hari puncak.
   * `DB 8567 TR` (Traga Box 6.1 CBM / 1.8 Ton): Rute Urban Timur (Tikala, Paal Dua, Tuminting, Singkil, Mapanget) mencapai 76,3% CBM dan 46,5% Ton.
   * `DB 8910 TK` (Elf CDE 10.0 CBM / 3.5 Ton): Rute Luar Kota (Tomohon, Tondano, Kawangkoan) 31,1% CBM dan 16,0% Ton (cadangan torsi tanjakan ekstrem Kinilow-Tinoor).
   * `DB 8123 QA` (Gran Max BV 3.6 CBM / 0.75 Ton): Canvass Kios Urban (65,4% CBM, 56,4% Ton).
   * `DB 8234 QX` (Gran Max Box 4.7 CBM / 1.0 Ton): Canvass Kios Sub-Urban (41,5% CBM, 35,1% Ton).

### B. Saldo Awal Stok & PO In-Transit
1. **Saldo Awal 1 Juli 2026 (00:00:00 WITA):**
   * Di-setup dari akumulasi PO pengapalan Juni yang sudah dibongkar di Maumbi sebelum 1 Juli.
   * Memastikan bahwa Sales Order (SO) hari pertama (1 Juli) **hanya bisa memesan SKU yang fisik barangnya sudah berstatus on-hand**.
2. **PO In-Transit (Pengapalan Juni Tiba 1-4 Juli 2026):**
   * Menjelaskan lonjakan stok (*stock surge*) yang memicu krisis overstok gudang (107,4% kapasitas) pada minggu pertama Juli:
     - Wings (PO-2026-06-01): Sandar Bitung 28 Juni, GRN Maumbi 1 Juli (Rp 1,85 Miliar).
     - Kapal Api (PO-2026-06-02): Sandar Bitung 27 Juni, GRN Maumbi 1 Juli (Rp 1,45 Miliar).
     - Mayora (PO-2026-06-03 & 04): Sandar Bitung 29 Juni & 1 Juli, GRN Maumbi 2 & 3 Juli (Rp 3,30 Miliar).
     - Unilever (PO-2026-06-05): Sandar Bitung 2 Juli, GRN Maumbi 4 Juli (Rp 2,90 Miliar).
   * Jatuh tempo pembayaran hutang principal (AP) jatuh pada akhir Juli hingga awal Agustus sesuai TOP masing-masing.

### C. Sebaran Proporsi Order per Prinsipal
Mengikuti pola *market basket* distributor FMCG regional Sulawesi Utara:
* **Wings Group:** 34% (Fast-moving volume terbesar: Mie Sedaap, Daia, SoKlin, Floridina).
* **Mayora Indah:** 28% (Roma Kelapa/Malkist, Beng-Beng, Torabika).
* **Kapal Api Group:** 20% (Kopi Kapal Api Special, Kopi ABC, Good Day).
* **Unilever Indonesia:** 18% (Rinso, Royco, Bango, Lifebuoy).

### D. Perbaikan Kategori & Hirarki Produk FMCG
Meniadakan kategori buatan yang saling silang antar-prinsipal, menetapkan nama/istilah FMCG resmi:
* **Mayora:**
  - *Biscuit & Wafer* (Roma, Better, Slai O'lai)
  - *Chocolate & Confectionery* (Beng-Beng, Kopiko, Kis)
  - *Coffee & Powdered Beverage* (Torabika — *bukan RTD*)
* **Wings:**
  - *Instant Noodles & Foods* (Mie Sedaap)
  - *Ready to Drink (RTD) & Beverage* (Floridina, ISOPLUS, Teh Rio)
  - *Fabric & Home Care* (Daia, SoKlin, Ekonomi)
  - *Personal Care & Toiletries* (Nuvo, Giv, Ciptadent)
* **Kapal Api:**
  - *Coffee & Hot Beverages* (Kopi Kapal Api, Kopi ABC, Good Day)
* **Unilever:**
  - *Foods & Savory* (Royco, Bango, SariWangi)
  - *Home Care & Hygiene* (Rinso, Molto, Sunlight)
  - *Personal Care & Beauty* (Lifebuoy, Sunsilk, Clear, Pepsodent, Rexona)

### E. Siklus Dokumen Transaksi: Same-Day vs H+1
* Hari H Pagi (08:00 - 14:00): Sales Order (SO) terbit dari kunjungan salesman PJP.
* Hari H Sore (14:30 - 17:00): Picklist mereservasi stok di rak gudang.
* Hari H Malam (17:00 - 21:00): Packlist / DO dicetak, barang dimuat ke armada.
* H+1 Pagi (07:30): Customer Invoice tercetak bersama Surat Jalan (DO Delivered) saat armada berangkat.

### F. Integritas Angka Finansial: Hindari Angka Genap & Aturan PPN
1. **Tidak Ada Angka Bulat Buatan:** Seluruh transaksi adalah kalkulasi organik:
   $$\text{Subtotal} = \text{Karton} \times (\text{Harga Pcs} \times \text{Isi Karton})$$
2. **DPP di Luar PPN:** Seluruh angka target di plan (Rp 5,50 Miliar Juli, Rp 4,235 Miliar Agustus, dll.) adalah **DPP (Dasar Pengenaan Pajak)**.
3. **Tarif PPN FMCG:** Mengacu ke UU HPP No. 7 Tahun 2021, tarif PPN umum di Indonesia adalah **11%** (belum 12%). Seluruh pencatatan akuntansi persediaan dan COGS berpatokan pada DPP murni.

### G. Protokol Anti-Jebakan SVL (*Stock Valuation Layer*) Odoo 19
**Akar Masalah:**
Memvalidasi dokumen stok/invoice via ORM Odoo pada hari ini menyebabkan `stock.valuation.layer` dan `account.move` terisi `create_date` dan `date` = HARI INI (tanggal eksekusi script). Laporan Neraca & Mutasi Persediaan per 31 Juli 2026 akan kosong (Rp 0).

**Solusi 4 Lapis Backdating:**
1. `stock.picking`: Set `date_done` dan `scheduled_date` ke tanggal historis $D$.
2. `stock.move` & `stock.move.line`: Set `date` ke tanggal historis $D$.
3. `stock.valuation.layer`: Update via SQL direct `UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s`.
4. `account.move` & `account.payment`: Set `date` dan `invoice_date` ke tanggal historis $D$, lalu post secara manual.

---

## 2. Panduan Rollback (Emergency Restore Point)

Jika implementasi pada branch baru mengalami hambatan atau inkonsistensi data, titik kembali (*restore point*) yang aman adalah:

* **Commit Titik Pulih:** `eaf1a47` (*docs(handoff): catat serah terima analisis pjp, drop size, km, biaya dan okupansi armada*)
* **Branch Titik Pulih:** `agen/rekonstruksi-seed-audit`
* **Langkah Rollback Cepat:**
  ```bash
  # Kembali ke branch audit yang stabil
  git checkout agen/rekonstruksi-seed-audit
  git reset --hard eaf1a47
  
  # Verifikasi integritas ledger lokal
  python scripts/ops/verify_ledger.py
  python -m ruff check .
  python scripts/check_manifests.py
  ```

---

Dokumen ini diarsipkan secara permanen sebagai basis referensi implementasi pada branch baru.
