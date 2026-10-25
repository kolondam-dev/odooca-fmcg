# HANDOFF

## 2026-10-26 — antigravity agent — Tindak Lanjut Penutupan 4 Penghalang Review Supervisi PR #15: Regresi AP, Reproduksibilitas CI, Gate Ledger & Laporan, serta Checksum Kanonikal LF (Status PASS)
**Konteks & Arahan Supervisi:**
Menindaklanjuti secara tuntas 4 temuan penghalang supervisor pada komentar PR #15 (issuecomment-6402401192) atas commit `e45106e`:
1. *[P1][Regresi Pembayaran AP]:* Jadwal pembayaran AP pada `scripts/ops/generate_perpetual_transactions.py` diturunkan langsung secara dinamis dari master `inbound_po_intransit_june_headers.csv`. Keempat pembayaran menunjuk nomor PO riil:
   - PO-2026-06-01: PT Sayap Mas Utama (Wings) Rp 1.849.772.800,00 (lunas 22 Juli 2026)
   - PO-2026-06-02: PT Santos Jaya Abadi (Kapal Api) Rp 1.449.737.600,00 (lunas 29 Juli 2026)
   - PO-2026-06-03: PT Mayora Indah Tbk (Biskuit) Rp 699.826.000,00 (lunas 31 Juli 2026)
   - PO-2026-06-04: PT Mayora Indah Tbk (Kopi & Wafer) Rp 2.598.138.400,00 (lunas 31 Juli 2026)
   - PO-2026-06-05: PT Unilever Indonesia Tbk Rp 2.899.971.200,00 (jatuh tempo 8 Agustus 2026 -> Open AP Juli).
   - Total Realisasi AP Juli: Rp 6.597.474.800,00 (Match 100% terhadap PO sumber; konstanta fiktif dieliminasi).
2. *[P1][Uji Reproduksibilitas Masuk CI & Isolasi Workspace]:*
   - Workflow `.github/workflows/seed-invariants.yml` diubah dari `-p 'test_seed_invariants.py'` menjadi `-p 'test_*.py'`, sehingga seluruh tes otomatis mengawal CI sebelum merge.
   - `tests/test_generator_reproducibility.py` kini menggunakan isolasi `tempfile.TemporaryDirectory` ganda dengan opsi `--output-dir`, menjaga workspace git repo tetap bersih tanpa ditimpa selama pengujian.
   - Hasil generator diverifikasi deterministik antar seed (`PYTHONHASHSEED=1` vs `2`) dan identik 100% dengan committed snapshot repo.
3. *[P1][Gate Invariant Memeriksa Ledger & Laporan Kanonikal]:*
   - `verify_seed_invariants.py` diperluas dengan gate `LEDGER-REPLAY` yang mereplay granular event ledger mutasi fisik, reserved, dan karantina per SKU/lot per tanggal. Memastikan `lot_phys >= 0`, `lot_res >= 0`, `lot_quar >= 0`, `lot_res <= lot_phys`, serta merekonsiliasi saldo penutupan setiap tanggal ke kartu stok harian.
   - Uji mutasi membuktikan mutasi opening physical impact ke -999.999 kini langsung tertangkap dan menggagalkan gate (`LEDGER-REPLAY`).
   - Gate `REPORT-RECON` memvalidasi integritas 15 input checksum dan konsistensi seluruh agregat laporan finansial terhadap register riil.
   - Gate `AP-FK` & `AP-RECON` memvalidasi referensi PO, principal, batas overpayment, dan kesesuaian tanggal pembayaran.
4. *[P1][Provenance Checksum Dibakukan dengan Normalisasi Kanonikal LF]:*
   - Dibakukan kontrak hashing kanonikal `canonical_file_hash` yang menormalisasi byte CRLF/CR ke LF sebelum SHA-256 dihitung.
   - Seluruh 15 file input register menghasilkan SHA-256 yang portabel dan identik 100% antara Windows dan runner Linux CI.
   - Seluruh file CSV dan JSON kanonikal ditulis dengan `\n` LF eksplisit (`lineterminator="\n"`).
5. *Catatan Kalender & Valuasi:*
   - Kalender `scripts/ops/fmcg_calendar.py` menyempurnakan 17 hari libur nasional resmi SKB 3 Menteri No. 1017/2025 (Hari Suci Nyepi dikoreksi ke 19 Maret 2026 dan Hari Raya Idul Adha ditambahkan pada 27 Mei 2026).
   - Valuasi akhir stok dipisahkan eksplisit: *Saleable Physical Valuation* (Rp 9.001.139.000,00) dan *Quarantine Asset Value* (Rp 1.963.200,00) dengan *Total Warehouse Stock Valuation* Rp 9.003.102.200,00.

**Verifikasi Lokal:**
- `python scripts/ops/verify_seed_invariants.py --report invariant-report.json`: Status PASS, 0 violations.
- `python -m unittest discover -s tests -p 'test_*.py' -v`: 39/39 tests PASS.
- `python -m ruff check .`: All checks passed!
- `python scripts/check_manifests.py`: 4 addon ok.

---

## 2026-10-26 — antigravity agent — Tindak Lanjut Lengkap 5 Temuan Supervisi PR #15: Reproduksibilitas Determinisme, Pemisahan Fisik/Reserved/Karantina, Rekonsiliasi Valuasi Retur, Kalender SKB 3 Menteri, & Laporan Kanonikal (Status PASS)
**Konteks & Arahan Supervisi:**
Menindaklanjuti secara menyeluruh 5 temuan supervisi PR #15 pada review commit `dee5179`:
1. *[P1][Regresi Determinisme]:* Mengeliminasi seluruh penggunaan `hash()` Python yang bergantung pada acak salt proses. Menggantinya dengan `deterministic_hash()` berbasis SHA-256. Menyertakan unit test reproduksibilitas lintas proses (`tests/test_generator_reproducibility.py`) yang membuktikan checksum SHA-256 seluruh 20 file dataset artefak identik 100% pada `PYTHONHASHSEED=1` dan `PYTHONHASHSEED=2`.
2. *[P1][Pemisahan Fisik vs Reserved vs Available vs Karantina]:* Mengubah model pergerakan stok: kuantitas fisik on-hand gudang (`physical_stock_cartons`) hanya berkurang saat event pengiriman fisik DO diberangkatkan. Saat SO terbit, kuantitas dialokasikan ke `reserved_stock_cartons` dan membatasi `available_stock = physical - reserved`. Pada cut-off 31 Juli, 14 SO (1.038 karton) yang dijadwalkan kirim 1 Agustus tetap berada di `physical_stock` Gudang Maumbi (53.837 karton) dengan status `reserved`. Menerbitkan event ledger granular `perpetual_stock_event_ledger.csv` dan `.json` (5.741 records).
3. *[P1][Rekonsiliasi Retur ke Valuasi & Gate Invariant]:* 9 kejadian retur (9 karton senilai DPP Rp 2.279.200,00 dan COGS Rp 1.963.200,00) masuk ke Aset Persediaan Karantina Gudang Maumbi. Beban Pokok Pendapatan (COGS) Laba Rugi Juli HANYA membebankan barang yang benar-benar diterima customer (*Accepted COGS* Rp 4.969.777.800,00), sehingga tidak ada double counting antara aset persediaan karantina dan beban laba rugi. Gate `RETURN-RECON` diperluas memvalidasi keberadaan SKU & lot pada baris SO, batas `qty <= delivered_lot_qty`, kesesuaian tanggal retur dengan DO, dan keunikan ID rejeksi.
4. *[P1][Kalender Resmi SKB 3 Menteri 2026]:* Berdasarkan SKB 3 Menteri No. 1017/2025 (Kemenko PMK), Tahun Baru Islam 1448 H jatuh pada 16 JUNI 2026, bukan 16 Juli 2026. Di bulan Juli 2026 tidak ada libur nasional, sehingga 16 Juli adalah hari kerja aktif normal (27 hari kerja operasional Juli). Kalender kanonikal disatukan pada `scripts/ops/fmcg_calendar.py`. Seluruh turunan diregenerasi: PJP matrix menghasilkan 419 call efektif, SO Booked 419 SO, Faktur sah Juli 405 faktur, dan carry-forward Agustus 14 faktur (angka lama tidak dipertahankan).
5. *[P1][Gate Invariant Menyeluruh & Laporan Rekonsiliasi Otomatis]:* Gate `INVOICE-MATH` kini mengikat nilai `do_delivered_dpp` dikurangi diskon proporsional ke invoice DPP. Gate `COLLECTION-MATH` mengikat `invoice_dpp` dan net cash collected. Menerbitkan script generator laporan kanonikal `scripts/ops/generate_financial_reconciliation_report.py` yang menghasilkan `data/registers/canonical_financial_reconciliation_july_2026.json` dan `.md` yang mengikat SHA-256 seluruh register.

**Asumsi Kalibrasi Scope FMCG Manado:**
- *Customer Cohort & Drop Size:* Dengan berlakunya filter cohort customer aktif Juli (177 outlet aktif dari 354 master), drop size per call dikalibrasi (GT Rp 16–26 jt, MT Rp 30–42 jt, INST Rp 15–24 jt, RTL Rp 3,5–6,5 jt) agar target omset distributor FMCG Manado tercapai (~Rp 5,59 BIO DPP terfaktur Juli) dengan utilisasi armada 6 kendaraan (Engkel, L300 Box, Blindvan) secara organik tanpa angka genap buatan.

**Ringkasan Angka Rekonsiliasi Finansial Kanonikal (Derivasi Otomatis Artefak Registers):**
1. *Pesanan Penjualan Terbit (SO Booked Juli 2026):*
   - Total SO Booked: 419 SO
   - Total Gross Order (DPP): Rp 6.065.892.600,00
   - Total Diskon Dagang: Rp 281.242.486,00 (4,64%)
   - Total Net Order (DPP): Rp 5.784.650.114,00
   - Total Biaya Pokok Pesanan (COGS): Rp 5.138.995.000,00
   - Kesesuaian Line Math ke SO: 2.738 baris order line identik 100% (Gross Rp 6.065.892.600,00, COGS Rp 5.138.995.000,00).
2. *Realisasi Pengiriman DO & Retur Karantina:*
   - Total Pengiriman: 419 DO
   - Nilai Bruto DO: Rp 6.065.892.600,00
   - Retur Handling Transit Karantina: Rp 2.279.200,00 (9 kejadian / 9 karton)
   - Nilai Bersih Diterima Customer (Delivered Net DPP): Rp 6.063.613.400,00
   - Nilai Buku Retur Masuk Aset Karantina (Rejection COGS): Rp 1.963.200,00
3. *Pemisahan Periode: Realisasi Terfaktur Juli (Cut-off 31 Juli 2026):*
   - Realisasi Terfaktur Juli: 405 Faktur
   - Penjualan Bersih Terfaktur (Invoiced DPP): Rp 5.594.622.485,00
   - PPN Keluaran 11% (UU HPP No. 7/2021): Rp 615.408.473,33
   - Total Piutang Faktur Bruto (DPP + PPN): Rp 6.210.030.958,33
   - Beban Pokok Penjualan Bersih (Accepted COGS): Rp 4.969.777.800,00
   - Laba Kotor Komersial (Gross Profit): Rp 624.844.685,00 (11,17%)
   - Beban Operasional & Penggajian (27 hari kerja operasional): Rp 394.350.000,00 (Logistik Rp 95,85 Jt + Gaji 24 staf Rp 185 Jt + Lembur Overstok Rp 68,5 Jt + Sewa Gudang Rp 45 Jt)
   - Laba Bersih Operasional Sah (Accrual Juli): Rp 230.494.685,00 (4,12%)
4. *Carry-Forward ke Periode Agustus 2026 (SO 31 Juli -> DO & Faktur 1 Agustus):*
   - Jumlah Pesanan Carry-Forward: 14 SO / DO / Faktur
   - Nilai DO Terkirim Carry-Forward: Rp 197.030.000,00
   - Nilai Invoiced DPP Carry-Forward: Rp 187.858.691,40
   - PPN 11% Carry-Forward: Rp 20.664.456,06
   - Total Tagihan Carry-Forward: Rp 208.523.147,46
   - COGS Terakui di Periode Agustus: Rp 167.254.000,00 (Retur: 0)
5. *Rekonsiliasi Kas, Diskon Pembayaran Awal, & Piutang Usaha:*
   - Transaksi Pelunasan Kas: 320 pembayaran
   - Kas Tertagih Bersih (Basis DPP): Rp 3.434.177.723,54
   - Diskon Pembayaran Awal (Early Cash Discount 1%): Rp 10.056.419,06
   - Saldo Piutang Usaha Akhir Juli (Open AR 31 Juli): Rp 2.150.388.342,40 (85 Faktur)
   - Jembatan Rekonsiliasi DPP: `Kas DPP (Rp 3.434.177.723,54) + Early Discount (Rp 10.056.419,06) + Open AR DPP (Rp 2.150.388.342,40) = Rp 5.594.622.485,00` (Match 100% Invoiced DPP Juli).
   - Basis Bruto Komersial (dengan PPN): `Kas Total (Rp 3.813.043.479,21) + Early Discount (Rp 10.056.419,06) + Open AR Total (Rp 2.386.931.060,06) = Rp 6.210.030.958,33` (Match 100% Tagihan Faktur Juli).
6. *Rekonsiliasi Fisik Persediaan & Gudang Maumbi (31 Juli 2026 EOD):*
   - Stok Fisik Aktual On-Hand di Gudang: 53.837 Karton
   - Stok Teralokasi / Dipesan (Reserved untuk Kirim 1 Agustus): 1.038 Karton
   - Stok Tersedia Bebas Dijual (Available for Sale): 52.799 Karton
   - Stok Karantina Kerusakan Transit (Bad Stock Gudang): 9 Karton
   - Nilai Aset Persediaan Karantina: Rp 1.963.200,00 (Rejection COGS)
   - Valuasi Buku Persediaan Fisik Akhir: Rp 9.001.139.000,00 DPP
   - Puncak Okupansi Gudang Maumbi: 104,2% (Krisis overstok kedatangan 5 kontainer Juni)

**Hasil Diagnostik Sebelum vs Sesudah PR #15 Iterasi 2:**
| Invariant Gate Rule | Baseline PR #14 | PR #15 SHA dee5179 | PR #15 Kini (Iterasi 2) | Status |
| :--- | :---: | :---: | :---: | :--- |
| `MASTER-GEO` | 77 | 0 | 0 | PASSED |
| `COHORT-PJP` | 228 | 0 | 0 | PASSED |
| `COHORT-SO` | 219 | 0 | 0 | PASSED |
| `CALENDAR` | 84 | 0 | 0 | PASSED (SKB 3 Menteri resmi, 27 hari kerja) |
| `EVENT-ORDER` | 331 | 0 | 0 | PASSED (Due date master, rejection date == DO date) |
| `MASTER-TOP` | - | 0 | 0 | PASSED (Invoice TOP == Master TOP) |
| `PERIOD-CUTOFF` | - | 0 | 0 | PASSED (DO Date == Invoice Date) |
| `RETURN-RECON` (Diperluas) | - | 0 | 0 | PASSED (SKU/lot match, qty <= delivered, math) |
| `INVOICE-MATH` (Diperluas) | - | 0 | 0 | PASSED (Delivered net dpp terikat ke invoice dpp) |
| `COLLECTION-MATH` (Baru) | - | - | 0 | PASSED (Payment dpp == Invoice dpp) |
| `LOT-BALANCE` | 770 | 0 | 0 | PASSED |
| `LOT-FEFO` | 0 | 0 | 0 | PASSED |
| **TOTAL VIOLATIONS** | **1.709** | **0** | **0** | **OVERALL STATUS: PASS** |

**Verifikasi:**
- `python -m unittest discover -s tests -p "test_*.py" -v`: 30/30 unit tests lulus (`OK`), mencakup pengujian reproduksibilitas lintas proses dan seluruh uji mutasi celah return/invoice/collection.
- `python scripts/ops/verify_seed_invariants.py --report invariant-report.json`: Status `PASS`, violations `[]` (0).
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.

**Status Ruleset GitHub & Batas Runtime:**
- GitHub Actions branch protection `main-quality-gate` sudah berstatus Active.
- Seluruh 5 CI jobs pada GitHub Actions (seed-invariants, invariant-tests, static, install-test, init-test) lulus.
- Batasan: Perbaikan ini diselesaikan dan divalidasi lokal secara ketat tanpa merge ke main, tanpa merge ke branch base, dan tanpa injeksi database production. Injeksi database runtime Odoo (idempotensi loader `scripts/load_fmcg_seed.py` dan SVL valuation) menjadi tahap pengujian runtime terpisah.

## 2026-10-26 — antigravity agent — Tindak Lanjut Supervisi PR #15: Perbaikan Return Karantina, Master TOP, Kalender Libur, & Rekonsiliasi Finansial Dua Periode (Status PASS)
**Konteks & Arahan Supervisi:**
Menindaklanjuti seluruh 4 temuan supervisi PR #15 (review komentar supervisor) pada branch `agen/fix-seed-invariants`:
1. *[P1][Regresi PR] Skenario Return/Rejection:* Memulihkan pemodelan return/tolakan barang saat DO secara deterministik (~4-5% order GT & MT rusak handling transit, 9 karton senilai Rp 3.079.200 DPP masuk `quarantine_stock`/Bad Stock Gudang Maumbi). Register baru: `data/registers/perpetual_order_rejections.csv` dan `.json`. Invariant diperluas dengan aturan `RETURN-RECON`.
2. *[P1][Celah Lama] Sinkronisasi TOP Master Customer:* Mengambil `payment_term_days` dari master customer (`customer_registry_354.csv`) untuk invoice, tanggal jatuh tempo (`due_date`), dan pelunasan AR. Invariant gate diperluas dengan aturan `MASTER-TOP` yang menolak ketidakcocokan termin faktur dengan master.
3. *[P1][Celah Periode & Rekonsiliasi] Pemisahan Cut-off Juli vs Carry-Forward Agustus:* Memisahkan secara tegas 389 pesanan terkirim dan terfaktur di bulan Juli dengan 14 pesanan tanggal 31 Juli yang terkirim dan terfaktur pada 1 Agustus. Invariant gate diperluas dengan aturan `PERIOD-CUTOFF` (`delivery date == invoice date`).
4. *[P2][Inkonsistensi Kalender Libur]:* Menyelaraskan kalender kerja operasional (`get_next_working_day`), menggeser pengiriman yang jatuh pada hari libur nasional 16 Juli 2026 (Tahun Baru Islam 1448 H / SKB 3 Menteri) dan Minggu ke hari kerja berikutnya. Invariant gate diperluas dengan aturan `CALENDAR` checking `deliv_day["is_working_day"] == True`.
5. *[Scope & Kalibrasi Basket Size]:* Dengan berlakunya filter cohort customer aktif Juli (177 outlet aktif dari 354 master), drop size per call dikalibrasi (GT Rp 16–26 jt, MT Rp 45–60 jt, INST Rp 15–24 jt, RTL Rp 3,5–6,5 jt) agar target omset distributor FMCG Manado tercapai (~Rp 5,35 BIO DPP Juli) secara organik tanpa angka genap buatan.

**Rekonsiliasi Finansial Kanonikal Dua Periode (Juli vs Carry-Forward Agustus 2026):**
1. *Pesanan Penjualan Terbit (Sales Order Juli):*
   - Total SO Booked Juli (403 SO): Gross DPP Rp 5.815.035.400,00 | Diskon Rp 269.696.709,72 | Net DPP Rp 5.545.338.690,28
2. *Realisasi Pengiriman & Faktur Juli (Cut-off 31 Juli 2026):*
   - Realisasi Terfaktur Juli: 389 SO / DO / Faktur
   - Nilai Invoiced DPP Juli: Rp 5.354.141.310,48
   - PPN Keluaran 11% Juli: Rp 588.955.544,15
   - Total Tagihan Bruto Terfaktur (DPP + PPN): Rp 5.943.096.854,63
   - Retur Fisik Karantina Juli: Rp 3.079.200,00 (9 karton masuk Gudang Karantina Maumbi)
   - Beban Pokok Pendapatan (COGS) Fisik Terkirim: Rp 4.760.427.600,00
   - Laba Kotor (Gross Profit) Terfaktur Juli: Rp 593.713.710,48 (11,09%)
   - Beban Operasional & Payroll Juli: Rp 390.800.000,00 (Logistik Rp 92,3 Jt + Gaji 24 staf Rp 185 Jt + Lembur Overstok Rp 68,5 Jt + Sewa Gudang Rp 45 Jt)
   - Laba Bersih Operasional Sah (Accrual Juli): Rp 202.913.710,48 (3,79%)
3. *Carry-Forward ke Periode Agustus 2026 (SO 31 Juli, Terkirim & Terfaktur 1 Agustus):*
   - Jumlah Pesanan Carry-Forward: 14 SO / DO / Faktur
   - Nilai DO Terkirim Carry-Forward: Rp 188.267.786,00
   - Nilai Invoiced DPP Carry-Forward: Rp 188.267.786,00
   - Nilai COGS Carry-Forward: Rp 166.615.000,00
   - Retur Karantina Carry-Forward: Rp 0,00 (0 kejadian)
4. *Rekonsiliasi Kas & Piutang Usaha (AR Ledger 31 Juli 2026):*
   - Total Kas Tertagih Juli: Rp 3.299.917.536,36 (termasuk early cash discount 1% Rp 1.144.205,51)
   - Saldo Piutang Usaha Akhir Juli (Open AR): Rp 2.041.726.856,12 (Jatuh tempo Agustus sesuai termin master)
5. *Rekonsiliasi Fisik Persediaan (Gudang Maumbi 31 Juli 2026):*
   - Saldo Akhir Stok Fisik Saleable: 54.371 Karton
   - Saldo Akhir Stok Karantina BS: 9 Karton (Lokasi Virtual Karantina Gudang Maumbi)
   - Puncak Okupansi Gudang Maumbi: 102,8%

**Hasil Diagnostik Sebelum vs Sesudah PR #15 Supervisor Review:**
| Invariant Gate Rule | Baseline PR #14 | PR #15 Initial | PR #15 Post-Review (Kini) | Status |
| :--- | :---: | :---: | :---: | :--- |
| `MASTER-GEO` | 77 | 0 | 0 | PASSED |
| `COHORT-PJP` | 228 | 0 | 0 | PASSED |
| `COHORT-SO` | 219 | 0 | 0 | PASSED |
| `CALENDAR` | 84 | 0 | 0 | PASSED (Termasuk filter libur 16 Juli) |
| `EVENT-ORDER` | 331 | 0 | 0 | PASSED (Jatuh tempo terikat TOP master) |
| `MASTER-TOP` (Baru) | - | - | 0 | PASSED (Invoice TOP == Customer TOP) |
| `PERIOD-CUTOFF` (Baru)| - | - | 0 | PASSED (DO Date == Invoice Date) |
| `RETURN-RECON` (Baru) | - | - | 0 | PASSED (Rejeksi karantina terekonsiliasi) |
| `LOT-BALANCE` | 770 | 0 | 0 | PASSED |
| `LOT-FEFO` | 0 | 0 | 0 | PASSED |
| **TOTAL VIOLATIONS** | **1.709** | **0** | **0** | **OVERALL STATUS: PASS** |

**Verifikasi:**
- `python scripts/ops/verify_seed_invariants.py --report invariant-report.json`: Status `PASS`, violations `[]` (0).
- `python -m unittest discover -s tests -p "test_*.py" -v`: 23/23 tests lulus (`OK`), termasuk 6 mutation tests baru (`test_top_mismatch`, `test_holiday_delivery`, `test_period_cutoff_mismatch`, `test_rejection_reconciliation`, `test_rejection_fk_invalid`, `test_rejection_non_positive_qty`).
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.

**Hal yang Masih Memerlukan Validasi Runtime Odoo:**
1. Injeksi database runtime Odoo (idempotensi loader `scripts/load_fmcg_seed.py` saat memuat lokasi karantina gudang virtual dan transaksi retur).
2. Penanganan multi-lot dan stock quant pada Stock Valuation Layer Odoo 19 agar saldo backdated 1-31 Juli 2026 tidak tercemar tanggal transaksi hari ini.
3. Rekonsiliasi pembukuan akuntansi umum di Odoo runtime (`account.move` & `stock.valuation.layer`).

## 2026-10-25 — antigravity agent — Perbaikan Invariant Gate Seed & Rekonsiliasi Transaksi (Status PASS)
**Konteks & Arahan Supervisi:**
Menindaklanjuti supervisi PR #14 (komentar issuecomment-6400313553) pada branch `agen/fix-seed-invariants` yang dicabangkan dari `origin/agen/supervision-invariant-gates` (commit base `02ecc81`).
Mengeliminasi seluruh 1.709 pelanggaran invariant tanpa menambal CSV manual, tanpa melonggarkan gate, dan tanpa continue-on-error.

**Akar Masalah & Perbaikan Generator/Master Sumber:**
1. `MASTER-GEO` (77 pelanggaran -> 0):
   - Menambahkan 5 record `id.subdistrict` resmi di `addons/id_base/data/id_district_data.xml` untuk 5 kecamatan yang belum memiliki kelurahan: Pakowa (`KEL-MND-PKW`, Wanea), Karame (`KEL-MND-KRM`, Singkil), Madidir Ure (`KEL-BTG-MDU`, Madidir), Girian Weru (`KEL-BTG-GRW`, Girian), dan Aertembaga Satu (`KEL-BTG-ATB`, Aertembaga).
   - Memperbaiki `DISTRICT_MASTER` dan mapping di `scripts/generate_customer_registry_and_pjp.py` (KEC-BTG-MDR, KEC-BTG-GRN, KEC-BTG-ATB, KEL-MNS-BYG) lalu meregenerasi `customer_registry_354.*` dan `partners_354.csv`.
2. `COHORT-PJP` (228 pelanggaran -> 0) & `COHORT-SO` (219 pelanggaran -> 0):
   - Memfilter penjadwalan PJP di `scripts/generate_pjp_july_matrix.py` berdasarkan `cohort_date` customer (`cohort_date <= date_str`), sehingga customer yang baru aktif Agustus/September/Oktober tidak dijadwalkan visit maupun order di bulan Juli.
3. `CALENDAR` (84 pelanggaran -> 0):
   - Menggeser jadwal pengiriman pesanan hari Sabtu dari Minggu ke Senin (`curr_dt + timedelta(days=2 if curr_dt.weekday() == 5 else 1)`), karena Minggu adalah hari libur operasional.
4. `EVENT-ORDER` (331 pelanggaran -> 0):
   - Menghitung `due_date` invoice dari tanggal invoice/delivery (`deliv_dt + timedelta(days=top_days)`), bukan tanggal order. Untuk customer COD (TOP 0), `due_date == date_invoice` sehingga tidak pernah terjadi `due_date < date_invoice`.
5. `LOT-BALANCE` (770 pelanggaran -> 0) & `LOT-FEFO` (0 pelanggaran):
   - Mengimplementasikan alokasi kuantitas lot secara bertahap dan ketat mengikuti FEFO (`lots.sort(key=lambda x: x["exp"])`). Kuantitas dipotong dari lot tertua hingga habis sebelum berpindah ke lot berikutnya, dan memecah order line jika melintasi beberapa lot sehingga kuantitas lot tidak pernah minus (`LOT-BALANCE` = 0) dan lot tertua selalu dihabiskan lebih dulu (`LOT-FEFO` = 0).

**Hasil Diagnostik Sebelum vs Sesudah:**
| Invariant Gate Rule | Sebelum (Baseline) | Sesudah (Fixed) | Keterangan Status |
| :--- | :---: | :---: | :--- |
| `MASTER-GEO` | 77 | 0 | PASSED (District & Subdistrict Odoo XML sinkron 100%) |
| `COHORT-PJP` | 228 | 0 | PASSED (Hanya 177 outlet cohort Juli dijadwalkan) |
| `COHORT-SO` | 219 | 0 | PASSED (Tidak ada SO mendahului cohort) |
| `CALENDAR` | 84 | 0 | PASSED (Tidak ada pengiriman hari Minggu) |
| `EVENT-ORDER` | 331 | 0 | PASSED (Jatuh tempo >= tanggal faktur) |
| `LOT-BALANCE` | 770 | 0 | PASSED (Stok lot tidak pernah minus / overdraft) |
| `LOT-FEFO` | 0 | 0 | PASSED (FEFO konsisten tanpa loncat expiry) |
| **TOTAL VIOLATIONS** | **1.709** | **0** | **OVERALL STATUS: PASS** |

**Diverifikasi:**
- `python scripts/ops/verify_seed_invariants.py --report invariant-report.json`: Status `PASS`, violations: `[]` (0).
- `python -m unittest discover -s tests -p "test_*.py" -v`: 17 unit test lulus (`OK`).
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.

**Hal yang Masih Memerlukan Validasi Runtime Odoo:**
1. Injeksi database runtime Odoo (idempotensi loader `scripts/load_fmcg_seed.py` saat memuat master data geospasial baru dan transaksi multi-lot).
2. Penerapan protokol 4-Lapis Anti-Jebakan SVL pada Stock Valuation Layer Odoo 19 agar saldo backdated 1-31 Juli 2026 tidak tercemar tanggal transaksi hari ini.
3. Rekonsiliasi jurnal akuntansi umum di Odoo runtime (`account.move` & `stock.valuation.layer`).

## 2026-10-25 — codex agent — Gate supervisi seed (draft, baseline merah)
**Berubah:** workflow Seed supervision, validator independen, 17 uji fixture/mutasi,
kontrak invariant dan kewajiban workflow pada AGENTS/DEVELOPMENT/AGENT_PROTOCOL.
Dibangun di atas 57f5768, branch agen/supervision-invariant-gates.
**Diverifikasi:** 17 uji lulus; ruff dan manifest lulus. Baseline data ditolak:
MASTER-GEO 77, COHORT-PJP 228, COHORT-SO 219, CALENDAR 84, EVENT-ORDER 331,
LOT-BALANCE 770. Laporan JSON mengikat commit dan hash input. Tidak mengubah seed.
**Belum diuji:** runtime Odoo, Railway, idempotensi loader, upgrade DB, laporan
historis/valuasi. Ruleset required-checks belum dikonfigurasi.
**Menunggu:** antigravity membenahi data/generator sesuai diagnostik; pemilik
mengaktifkan required checks setelah nama check tersedia dari run GitHub.

## 2026-10-25 — antigravity agent (Branch Baru: Implementasi Transaksi Historis Perpetual & Anti-Jebakan SVL)
**Berubah:**
- Branch aktif: `agen/transaksi-historis-perpetual` (berbasis `agen/rekonstruksi-seed-audit` commit `1e12ebe`).
- Kategorisasi Produk FMCG Bersih ([`addons/id_base/models/product_template.py`](file:///c:/Users/ACER/dev/odooca-fmcg/addons/id_base/models/product_template.py), [`data/seed/products_150.csv`](file:///c:/Users/ACER/dev/odooca-fmcg/data/seed/products_150.csv), & [`scripts/load_fmcg_seed.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/load_fmcg_seed.py)):
  - Menghilangkan pencampuran kategori silang, menetapkan divisi resmi per prinsipal:
    * Mayora: *Biscuit & Wafer* (Roma, Better, Slai O'lai), *Chocolate & Confectionery* (Beng-Beng, Kopiko, Kis), *Coffee & Powdered Beverage* (Torabika, Energen).
    * Santos: *Coffee & Hot Beverages* (Kapal Api, Kopi ABC, Kopi Ya!, Kopi Kapten).
    * Unilever: *Foods & Savory* (Royco, Bango), *Home Care & Hygiene* (Rinso, Molto, Sunlight), *Personal Care & Beauty* (Lifebuoy, Sunsilk, Clear, Pepsodent, Rexona).
    * Wings: *Instant Noodles & Foods* (Mie Sedaap), *Ready to Drink (RTD) & Beverage* (Floridina, Golda, Teh Javana, Jasjus), *Coffee* (Top Kopi).
  - Hirarki Odoo `product.category` 3 level: `[PRINSIPAL] > [DIVISI] > [BRAND]`.
- Master Saldo Awal 1 Juli & PO In-Transit Juni ([`scripts/ops/generate_initial_stock_and_intransit.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/ops/generate_initial_stock_and_intransit.py) & `data/registers/`):
  - Saldo awal on-hand 1 Juli 2026: 150 SKU, Rp 4,475 Miliar DPP, 940,2 m³ (52,9% kapasitas gudang).
  - PO In-Transit pengapalan Juni tiba 1-4 Juli: Rp 9,496 Miliar DPP (Wings 1 Juli, Santos 1 Juli, Mayora 2 & 3 Juli, Unilever 4 Juli).
- Granular Perpetual Inventory Turnover Engine ([`scripts/ops/generate_perpetual_transactions.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/ops/generate_perpetual_transactions.py) & `data/registers/`):
  - 622 Sales Orders (SO) terbit hanya dari saldo on-hand yang tersedia pukul 08:00 pada hari kunjungan PJP.
  - 3.227 Baris Order dengan SKU, kuantitas karton, harga satuan DPP, subtotal riil tanpa pembulatan genap buatan, dan lot FEFO.
  - 622 Packlist/DO terkirim H+1 dengan pencatatan parsial retur/tolakan toko.
  - 622 Customer Invoices tercetak H+1 dengan DPP di luar PPN dan PPN 11% (UU HPP No. 7/2021).
  - 485 AR Cash & Bank Collections terikat ke `invoice_number`, mencakup simulasi pemajuan tagihan (*cash discount* 1% hari ke-5/7) dan pelunasan mingguan PJP.
  - 4 AP Payments ke principal sesuai termin dagang resmi (21, 28, 30, 35 hari).
  - 29 OPEX/Payroll entries: Biaya logistik harian rutin (Rp 3,55 Jt/hari) + Konsentrasi beban gaji 24 karyawan (Rp 185 Jt), lembur overstok (Rp 68,5 Jt), dan sewa gudang (Rp 45 Jt) tepat di tanggal 31 Juli.
  - 31 Kartu stok harian membuktikan puncak okupansi gudang mencapai **102,8%** di awal Juli akibat kedatangan 5 kontainer susulan.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/ops/generate_initial_stock_and_intransit.py`: Lolos verifikasi, 150 SKU dan 5 PO in-transit tersimpan.
- `python scripts/ops/generate_perpetual_transactions.py`: Berhasil menghasilkan 8 dataset granular dan rekonsiliasi finansial Juli 2026.
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.
- Commit git: `aa3c4f6` (*feat(perpetual): implementasi saldo awal 1 juli, po in-transit, kategorisasi divisi fmcg, dan granular perpetual turnover engine*).

**Menunggu / Langkah Berikutnya:**
- Menerapkan protokol Anti-Jebakan SVL pada loader Odoo untuk injeksi saldo awal, PO, SO, DO, Invoice, dan Payment ke database Odoo.

## 2026-10-25 — antigravity agent (Pengarsipan Keputusan Arsitektur Transaksi Historis, Saldo Awal, Kategori Produk, & Protokol Anti-Jebakan SVL)
**Berubah:**
- Dokumentasi & Arsip Keputusan Arsitektur ([`docs/reviews/ARCHITECTURAL_DECISIONS_AND_ROLLBACK_2026-10-25.md`](file:///c:/Users/ACER/dev/odooca-fmcg/docs/reviews/ARCHITECTURAL_DECISIONS_AND_ROLLBACK_2026-10-25.md)):
  - Mendokumentasikan secara rinci arahan pemilik perihal:
    1. Saldo awal stok per 1 Juli (150 SKU) sebagai pembatas order SO hari pertama.
    2. PO In-Transit pengapalan Juni yang tiba 1-4 Juli di Pelabuhan Bitung & Gudang Maumbi (Wings Rp 1,85 Miliar, Kapal Api Rp 1,45 Miliar, Mayora Rp 3,30 Miliar, Unilever Rp 2,90 Miliar) yang memicu lonjakan okupansi gudang 107,4% di awal Juli.
    3. Sebaran proporsional order per prinsipal: Wings 34%, Mayora 28%, Kapal Api 20%, Unilever 18%.
    4. Perbaikan struktur kategori produk Odoo (`product.category`): Meniadakan pencampuran/kategori silang, menetapkan nama/istilah resmi divisi FMCG (Biscuit & Wafer, Instant Noodles & Foods, Coffee & Hot Beverages, Fabric & Home Care, Savory, Personal Care).
    5. Siklus dokumen terintegrasi: SO, Picklist, Packlist/DO dan pemuatan pada hari H sore/malam, Invoice tercetak H/H+1 pagi.
    6. Eliminasi angka genap: Subtotal dihitung organik dari kuantitas karton x harga satuan SKU.
    7. Perpajakan: Seluruh target plan adalah DPP di luar PPN; PPN standar berlaku 11% (UU HPP No. 7/2021).
    8. Protokol 4-Lapis Anti-Jebakan SVL (*Stock Valuation Layer*) Odoo 19 (backdating picking, move, SQL SVL create_date, dan account move) agar laporan keuangan & stok Odoo tidak tercemar tanggal injeksi hari ini.
  - Menetapkan titik pulih rollback (*restore point*) pada commit `eaf1a47` branch `agen/rekonstruksi-seed-audit`.
  - Persiapan pembuatan branch baru: `agen/transaksi-historis-perpetual`.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Dokumen tersimpan dan lolos verifikasi markdown.
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.

**Menunggu / Langkah Berikutnya:**
- Membuat cabang kerja baru `agen/transaksi-historis-perpetual` dari commit saat ini.
- Mengimplementasikan pembenahan kategori produk 150 SKU di `data/seed/products_150.csv` dan model Odoo.
- Mengembangkan generator perpetual FIFO ledger dan loader transaksi historis dengan mitigasi SVL.

## 2026-10-25 — antigravity agent (Tabel Matrix PJP Juli 2026, Analisis Drop Size, KM & Biaya Delivery, dan Okupansi Kubikasi/Tonase Armada)
**Berubah:**
- Matrix PJP Juli 2026 31 Hari Penuh ([`data/registers/pjp_july_2026_matrix.csv`](file:///c:/Users/ACER/dev/odooca-fmcg/data/registers/pjp_july_2026_matrix.csv) & [`scripts/generate_pjp_july_matrix.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/generate_pjp_july_matrix.py)):
  - 686 baris matrix mencakup seluruh tanggal (1 s/d 31 Juli 2026), 647 kunjungan call efektif, 27 hari kerja operasional (Senin-Sabtu), dan 4 hari Minggu OFF.
  - Kolom lengkap: `salesman`, `salesman_role`, `tanggal`, `hari`, `frekuensi_call`, `channel`, `area`, `district`, `customer`, `latitude`, `longitude`, `delivery_date`, `delivery_vehicle`.
- Analisis Sales per Call & Delivery Unit Economics ([`scripts/ops/analyze_pjp_july_metrics.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/ops/analyze_pjp_july_metrics.py)):
  - Drop size rata-rata: MT Rp 32,59 Jt, GT Rp 12,22 Jt, RTL Rp 2,39 Jt, INST Rp 7,17 Jt (Rata-rata tertimbang Rp 8,50 Jt/call).
  - ARPU belanja bulanan: MT Rp 146,67 Jt, GT Rp 38,19 Jt, RTL Rp 3,38 Jt, INST Rp 16,50 Jt.
  - KM delivery: 128 trip armada, 11.415,4 KM total, rata-rata 422,8 KM/hari kerja (89,2 KM/trip armada dari Gudang Maumbi).
  - Total Delivery Cost: Rp 91,08 Jt (1,66% dari Gross Revenue Rp 5,5 BIO): BBM Solar Rp 22,07 Jt (24,2%), Non-BBM Rp 69,01 Jt (75,8%: Uang jalan ritase, tol/retribusi, M&R ban/oli, depresiasi, KIR/STNK, dan risiko transit damage).
- Analisis Okupansi Harian Armada Kubikasi & Tonase ([`scripts/ops/analyze_fleet_occupancy_july.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/ops/analyze_fleet_occupancy_july.py)):
  - Membuktikan sifat produk FMCG yang *space-constrained* (rata-rata rasio CBM/Tonase mencapai 1.8x - 2.0x lebih cepat jenuh kubikasi daripada tonase).
  - Rata-rata okupansi kubikasi box harian: Canter CDD 48,9% CBM (25,2% Ton), Traga Timur 76,3% CBM (46,5% Ton), Gran Max BV 65,4% CBM (56,4% Ton), Gran Max Box 41,5% CBM (35,1% Ton), Elf Luar Kota 31,1% CBM (16,0% Ton).
  - Untuk rute padat Manado Barat (DB 8456 FB L300), rata-rata harian mencapai 6,4 m³ / 1,1 T (118,4% CBM single-trip), yang secara operasional dieksekusi melalui **2 ritase pengiriman per hari** (ritase pagi 3,2 m³ / 59% CBM dan ritase siang 3,2 m³ / 59% CBM) serta cadangan L300 (`DB 8678 CD`) pada hari puncak.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/ops/analyze_fleet_occupancy_july.py`: Berhasil menghasilkan matriks utilisasi kubikasi dan tonase 9 armada.
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon`.
- Commit git: `001cb4f` (*feat(fleet): analisis okupansi harian armada logistik secara kubikasi dan tonase juli 2026*).

**Menunggu / Langkah Berikutnya:**
- Melanjutkan ke Task 3 (Loader Master Odoo dengan akun `res.users` salesman, packaging karton, dan UoM FMCG) dan Task 4 (Pengisian data simulasi transaksi historis ke Odoo berdasarkan ledger harian yang sudah tervalidasi).

## 2026-10-25 — antigravity agent (Integrasi Master Data Wilayah Resmi Sulut 2.026 Wilayah & Penyelesaian Task 1 & Task 2)
**Berubah:**
- Master Data Administrasi & Geospasial Sulawesi Utara (`data/master/`, `data/geo/`, `docs/geo/SULUT_ADMINISTRASI_GEO.md`):
  - Mengintegrasikan hasil riset dan sumber data presisi dari `sulut_master_data.zip` (sumber Kemendagri 2025, Pos Indonesia, dan batas MultiPolygon terestrial).
  - Skrip generator baru: [`scripts/generate_sulut_master.py`](file:///c:/Users/ACER/dev/odooca-fmcg/scripts/generate_sulut_master.py) (menggantikan bounding box manual lama), memproses hierarki lengkap: **1 Provinsi → 15 Kab/Kota (11 Kab + 4 Kota) → 171 Kecamatan → 1.839 Desa/Kelurahan (332 Kelurahan + 1.507 Desa)**.
  - Memperbaiki kode Kemendagri di [`addons/id_base/data/id_city_data.xml`](file:///c:/Users/ACER/dev/odooca-fmcg/addons/id_base/data/id_city_data.xml) yang tertukar: Minahasa Tenggara adalah `7107` (bukan 7109) dan Kep. Sitaro adalah `7109` (bukan 7107).
  - Memutakhirkan 4 berkas GeoJSON terestrial: `sulut_provinsi.geojson`, `sulut_kab_kota.geojson`, `sulut_districts.geojson` (171 kecamatan), dan `sulut_villages.geojson` (1.839 desa/kelurahan).
- Master Customer Register & PJP Schedule (`data/registers/` & `scripts/generate_customer_registry_and_pjp.py`):
  - Memutakhirkan `DISTRICT_MASTER` dengan kode Kemendagri resmi (`71.71.04`, dsb.), kode pos akurat (Calaca 95121, Sario Kotabaru 95113, Paniki Bawah 95256, Paslaten Satu 95446, Roong 95617, Sendangan 95690, Buyungon 95957), dan titik koordinat representatif daratan (`lat_titik_dalam`, `lng_titik_dalam`).
  - Menghasilkan ulang `customer_registry_354.*` dan mensinkronkan `data/seed/partners_354.csv`.
- `addons/id_base/__manifest__.py`:
  - Menambahkan dependensi `base_geolocalize` bawaan core Odoo agar field `partner_latitude` dan `partner_longitude` pada `res.partner` terjamin selalu native tanpa custom field berlebih.
- Sinkronisasi Master FMCG Seed (`scripts/generate_fmcg_seed.py`):
  - Menjadikan register 354 customer sebagai sumber kebenaran tunggal (*Single Source of Truth*), menghasilkan `data/seed/partners_354.csv` yang 100% konsisten.
  - Menambahkan `carton_barcode` (GS1 prefix 1) dan dimensi karton lengkap ke `data/seed/products_150.csv`.
  - Memperbarui `data/seed/historical_simulation_summary.json` agar selaras dengan metrik omset dan okupansi gudang riil.
- Local Day-to-Day Financial Ledger & Auditor (`data/registers/historical_ledger_day_to_day.*` & `scripts/ops/verify_ledger.py`):
  - Ledger harian 116 hari (1 Juli - 24 Oktober 2026) merekam seluruh siklus bisnis: PO -> Inbound Stock -> SO -> DO Delivery -> Invoicing AR -> Return -> Collection -> OPEX Beban -> AP Pembayaran Hutang.
  - Skrip auditor `scripts/ops/verify_ledger.py` membuktikan 100% invarian bisnis terpenuhi: Omset Juli Rp 5.5 BIO (net margin 0.90%, okupansi gudang puncak 107.4% terverifikasi pada 10 Juli), Agustus Rp 4.235 BIO (-23%, margin 2.50%), September Rp 3.96 BIO (-6.5%, margin 3.70%), Oktober Rp 5.30 BIO (margin 5.00%). Saldo kas, stok, AR, dan AP tidak pernah negatif.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/ops/verify_ledger.py`: `[SUKSES] SEMUA 100% INVARIAN FINANSIAL, OPERASIONAL, & LOGISTIK TERPENUHI!`.
- `python -m ruff check .`: `All checks passed!`.
- `python scripts/check_manifests.py`: `manifest ok: 4 addon (id_base, id_ui, id_ui_form, id_ui_shell)`.
- `python scripts/generate_fmcg_seed.py`: Menghasilkan 4 principal, 150 produk, 354 partner konsisten, 24 karyawan, dan 9 armada tanpa error.

**Menunggu / Langkah Berikutnya:**
- Melanjutkan ke Task 3 (Loader Master Odoo dengan akun `res.users` salesman, packaging karton, dan UoM FMCG) dan Task 4 (Pengisian data simulasi transaksi historis ke Odoo berdasarkan ledger harian yang sudah tervalidasi).

## 2026-10-25 — antigravity agent (Audit Drift Eksekusi Demo Data & Rencana Rekonstruksi Komprehensif)
**Berubah:**
- `docs/reviews/AUDIT_AND_RECONSTRUCTION_PLAN_2026-10-25.md`:
  - Mendokumentasikan secara komprehensif arahan pemilik repo (prioritaskan native fields, hari kerja Senin s/d Sabtu, kausalitas presisi transaksi historis Juli-Oktober 2026, cohort outlet).
  - Mengaudit temuan drift eksekusi agen sebelumnya: hardcoded UoM Units 150/150 SKU, dimensi karton terbuang, mismatch semantik nama toko vs kecamatan di `partners_354.csv`, pseudo-anchoring koordinat jalan, broken foreign key salesman (seluruh 354 outlet di-assign ke Administrator karena tidak ada `res.users`), serta crash fatal `KeyError: 'tier_code'` dan pelanggaran subtotal matematika pada generator simulasi historis.
  - Merumuskan 5 tahapan rekonstruksi: (1) audit & eliminasi custom field berlebih, (2) sinkronisasi identitas salesman & user Odoo, (3) rekalibrasi geografi dan master dataset, (4) rekonstruksi skrip simulasi historis kausal & 6 hari kerja, (5) loader idempoten dan verifikasi CI.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Review kode `generate_fmcg_seed.py`, `load_fmcg_seed.py`, `generate_historical_simulation.py`, `load_historical_simulation.py`, transkrip percakapan sebelumnya, serta ulasan `claude-dev` (`REVIEW_2026-10-24_main-fa68c23.md`).
- Pengujian reproduksi error: `python scripts/generate_historical_simulation.py` terbukti crash `KeyError: 'tier_code'`.

**Menunggu / Langkah Berikutnya:**
- Melaksanakan Task 1: Audit model native, eliminasi custom fields yang tidak perlu, dan perancangan UoM resmi FMCG serta akun user salesman.

## 2026-10-25 — antigravity agent (Live Railway & Playwright Verification: Database Schema Synchronization & Browse Error Resolution)
**Berubah:**
- `deploy/init.sh`:
  - Menaikkan penanda pembaruan skema dari `upgrade_modules_v1` ke `upgrade_modules_v2` agar siklus `-u $INIT_MODULES` selalu dijalankan saat kode modul baru ditambahkan pada container Odoo dengan Postgres persisten.
- Railway Production Environment:
  - Mengaktifkan `FORCE_UPGRADE=1` sementara melalui Railway MCP untuk memicu re-indexing skema lengkap (menambahkan kolom baru `id_principal.pic_name`, `fleet_vehicle.capacity_ton`, kargo box, dsb.).
  - Mengembalikan `FORCE_UPGRADE=0` di Railway setelah skema sukses disinkronkan, sehingga boot container selanjutnya tetap instan dan efisien.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Log runtime Railway deployment `5b1a6322-56d1-4d3d-bc3f-7a8c9742990f` mencatat eksekusi sukses pembaruan tabel `fleet`, `product`, `hr`, `id_base`, dan `id_ui` (`Registry loaded in 0.959s`).
- Pengujian interaktif end-to-end via Playwright headless Edge pada instance live `https://odooca-fmcg-demo.up.railway.app`:
  - **FMCG Principals:** Daftar prinsipal dan form record (PT Mayora Indah Tbk, PT Santos Jaya Abadi, PT Unilever Indonesia Tbk, PT Wings Surya) terbuka mulus tanpa pesan error; field Key Contact / PIC terisi dan tampil rapi.
  - **Products / Katalog FMCG:** Kanban view dan form view produk (Banngo Kecap Manis, Benn-Beng dkk) terbuka sempurna; struktur hirarkis kategori `[PRINSIPAL] > [DIVISI] > [BRAND]`, data kemasan karton, dan barcode tampil lengkap.
  - **Fleet / Armada:** Kanban dan form kendaraan (DB 8123 QA) terbuka tanpa error dan terhubung dengan driver Novry Mandagi.
  - **Employees / Karyawan:** Profil karyawan terbuka rapi dan terafiliasi dengan alamat resmi `PT Manado Distribusi Utama` di Interchange Maumbi.
  - **Contacts / Pelanggan:** Daftar kontak outlet terbuka bersih tanpa referensi field tier lama.
  - Seluruh screenshot hasil verifikasi tersimpan di direktori artefak (`v2_02_principal_form.png`, `v2_07_product_form.png`, `v3_02_fleet_form.png`, `v3_06_employee_form.png`).

**Belum diuji:**
- Simulasi transaksi end-to-end Sales Order -> Picking/DO -> Invoicing dengan perhitungan margin per divisi prinsipal (dijadwalkan pada M2).

## 2026-10-25 — antigravity agent (Master Data Native Refinement: Tier Removal, Fleet Cargo, Principal PIC, Road Coordinates, Org Hierarchy, PT MDU & 5-Day Calendar)
**Berubah:**
- `addons/id_base`:
  - Menghapus model `id.tier`, field `tier_id` pada `res.partner`, berkas `data/id_tier_data.xml`, views, menus, dan hak akses security (eliminasi custom tier yang tidak relevan dengan B2B FMCG).
  - Menambahkan inherisi model `fleet.vehicle` (`addons/id_base/models/fleet_vehicle.py` & views) dengan field native & kargo: `capacity_ton`, `capacity_cbm`, `box_length`, `box_width`, `box_height`, `stnk_expiry`, `kir_expiry`, dan `operational_route`.
  - Menambahkan field kontak dan PIC pada `id.principal` (`pic_name`, `pic_phone`, `pic_email`) dan form view.
  - Menambahkan dependensi `"fleet"`, `"hr"`, `"uom"` pada `addons/id_base/__manifest__.py`.
- `scripts/generate_fmcg_seed.py`:
  - Rekalibrasi koordinat 354 outlet (`DISTRICT_COORDS`): menambatkan geotag outlet tepat pada koridor jalan darat tiap kecamatan (anti-drowning di Teluk Manado & anti-lereng gunung).
  - Menambahkan dimensi fisik realistis (`length_cm`, `width_cm`, `height_cm`, `volume_cbm`) untuk satuan terkecil (Pcs) dan Karton (`carton_length_cm`, `carton_width_cm`, `carton_height_cm`, `carton_volume_cbm`, `carton_weight_kg`) pada 150 Master SKU.
  - Menambahkan dimensi box kargo armada logistik (`box_length_m`, `box_width_m`, `box_height_m`) pada 9 armada.
  - Menambahkan `manager_code` pada 24 personel untuk membentuk pohon hirarki organisasi.
  - Menambahkan generator `generate_principals` yang menghasilkan `data/seed/principals_4.csv` lengkap dengan PIC, NPWP CoreTax, alamat, dan nomor telepon resmi.
- `scripts/load_fmcg_seed.py`:
  - Membangun struktur kategori hirarkis Odoo `product.category`: `[PRINSIPAL] > [DIVISI KATEGORI] > [BRAND]` untuk mengisolasi penilaian persediaan, COGS, dan SLA retur antar-prinsipal.
  - Memuat vendor partner resmi dan menghubungkan data PIC prinsipal dari `principals_4.csv`.
  - Memuat metadata kargo armada logistik ke `fleet.vehicle`.
  - Membangun departemen (`Management`, `Sales & Distribusi`, `Finance & Akuntansi`, `Warehouse & Logistik`) dan relasi manajer (`parent_id`) pada `hr.employee`.
- `deploy/init.sh`:
  - Menambahkan modul `fleet,hr,uom` ke default `INIT_MODULES`.
  - Menambahkan blok idempoten `company_profile_v2` untuk menyetel nama resmi `PT Manado Distribusi Utama` (Interchange Maumbi, Manado 95371, telp: `0431-889900`, vat: `012345678821000`) dan kalender kerja 5 hari (Senin - Jumat 08:00 - 17:00, Sabtu - Minggu libur).
  - Menaikkan penanda seed ke `seed_master_v4`.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- `python -m ruff check .` lolos (`All checks passed!`).
- `python scripts/generate_fmcg_seed.py` dieksekusi sukses menghasilkan `principals_4.csv`, `products_150.csv`, `partners_354.csv`, `employees_24.csv`, dan `vehicles_9.csv`.
- Cabang `agen/master-data-native-refinement` di-push dan diajukan via PR #12 (`https://github.com/kolondam-dev/odooca-fmcg/pull/12`).
- Seluruh 3 workflow checks di GitHub Actions CI (`static`, `install-test`, `init-test`) **PASS / HIJAU 100%**.

**Belum diuji:**
- Pemuatan langsung ke instance container Odoo live di Railway (menunggu merge PR #12 ke `main`).

## 2026-10-25 — antigravity agent (M1a: Master Data Refinement — Legal Protection Names, Address/Contact Integrity, Product Packaging, Roster, Fleet, Fail-safe Seed Mark)
**Berubah:**
- `addons/id_base/data/id_principal_data.xml`:
  - Mengubah 4 Principal dan 29 brand menjadi nama fiktif pelindung hukum (`PT Mayyora Indahh Tbk`, `PT Santos Jaya Abadii`, `PT Unilevr Indonezia Tbk`, `PT Sayapp Mas Utamma`, dsb.) untuk mitigasi risiko hak cipta/merek dagang nyata [E1].
- `scripts/generate_fmcg_seed.py`:
  - Mengacak dan menyesuaikan nama brand fiktif pada 150 SKU FMCG.
  - Mengganti `EMP-001` Bpk. Teddy Kolondam menjadi nama fiktif "Bpk. Ronald Mongisidi" serta menambahkan `work_email` (`@fmcg-demo.id`) dan `work_phone` (`08xxxxxxxxxx`) pada seluruh 24 personel roster [E2].
  - Menambahkan data geografis dan kontak pada seluruh 354 partner: `city` (Manado, Bitung, Tomohon, Minahasa, dsb.), `state` ("Sulawesi Utara"), `country` ("Indonesia"), `phone` (`08xxxxxxxxxx`), dan NPWP format CoreTax 16-digit [A2].
  - Menghilangkan/decouple `tier_code` sesuai arahan pemilik [A1].
  - Mengganti nama outlet GT dan RTL dengan nama warung/kios/toko lokal Minahasa/Manado yang variatif.
- `data/seed/*.csv`:
  - Regenerasi deterministik untuk `products_150.csv`, `partners_354.csv`, `employees_24.csv`, dan `vehicles_9.csv`.
- `scripts/load_fmcg_seed.py`:
  - Menambahkan pembuatan vendor partner (`res.partner`, `supplier_rank=1`) untuk principal yang terhubung ke `principal.partner_id`.
  - Menambahkan pembuatan kategori hirarkis FMCG di `product.category` dan linking kategori produk.
  - Memperbarui `load_products`: mengaktifkan `is_storable = True`, `tracking = 'lot'`, dan membuat packaging kemasan Karton (`product.packaging`) berbasis UoM Pcs [A4, A5].
  - Menambahkan pemuatan 24 karyawan ke `hr.employee` dan `hr.department` [A6].
  - Menambahkan pemuatan 9 unit armada ke `fleet.vehicle`, `fleet.vehicle.model`, dan `fleet.vehicle.model.brand` [A6].
  - Memperbarui `load_partners`: memetakan `city`, `state_id`, `country_id`, `phone`, `vat`, `property_payment_term_id` (TOP), dan `user_id` (salesman), serta memastikan `tier_id` tidak digunakan [A1, A2, A3].
- `deploy/init.sh`:
  - Menaikkan penanda seed ke `seed_master_v3` dan membungkus eksekusi seed dengan kondisional fail-safe agar jika skrip gagal, penanda tidak terbuat [C1].
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- `python -m ruff check .` lolos (`All checks passed!`).
- `python scripts/generate_fmcg_seed.py` dieksekusi sukses menghasilkan 150 produk, 354 partner, 24 karyawan, dan 9 armada secara konsisten.
- Cabang `agen/m1a-master-data-refinement` di-push ke remote dan diajukan via PR #11 (`https://github.com/kolondam-dev/odooca-fmcg/pull/11`).
- Seluruh 3 workflow check GitHub Actions CI (static, install-test, init-test pada DB kosong + restart idempoten) **PASS / HIJAU 100%**.

**Belum diuji:**
- Pemuatan langsung ke instance aktif Railway (menunggu merge PR #11 ke `main`).
- Simulasi transaksi historis M2 (line vs header consistency) yang dijadwalkan pada Prioritas 2.

## 2026-10-25 — claude-design agent (UI Refinement v6: Systray Dividers Alignment, Form Statusbar Middle Align Without Rounded Box, Edge-to-Edge Form, Steady Sticky Footer)
**Berubah:**
- `addons/id_ui_shell/static/src/shell/id_shell.scss`:
  - Systray navbar kanan: 4 menu aktif (`.o-mail-DiscussSystray-class`, `.o-dropdown:has(.fa-clock-o)`, `.o_switch_company_menu`, `.o_user_menu`) diseragamkan `height: 38px; display: flex; align-items: center;`.
  - Tepat 3 pemisah vertikal rapi dipasang via `::before` pada item 2, 3, dan 4 dengan `height: 20px; width: 1px; background: #d8dee8; align-self: center;`, menghilangkan garis divider yang meleset atau turun keluar deret menu.
- `addons/id_ui_form/static/src/form/id_form.scss`:
  - Form Full Width edge-to-edge: `.o_form_sheet_bg` disetel `padding: 0; background: #fff;`, `.o_form_sheet` disetel `border: none; border-radius: 0; padding: 1rem 1.25rem 0; width: 100%; max-width: 100%;`.
  - Statusbar form: tombol aksi, judul form (.oe_title / .id_statusbar_title), dan statusbar pipeline disetel `align-items: center !important` (sejajar align middle secara presisi). Background box rounded putih dihilangkan total (`background: transparent; border: 0; border-radius: 0; box-shadow: none;`).
  - Sticky footer: padding/margin disesuaikan flush edge-to-edge, border-bottom dihilangkan, posisi footer tetap diam (steady di bottom) tanpa bergeser/bouncing saat scroll ke atas.
- Log: `agent-log/claude-design.log`.

**Diverifikasi (bagaimana):**
- Verifikasi Playwright headless: alignment statusbar presisi (pusat Y = 156.25px untuk ketiga komponen), form selebar 100% viewport, sticky footer tetap menempel diam di bottom saat di-scroll bolak-balik, 3 divider systray rapi sejajar.
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).

**Belum diuji:**
- Browser Firefox/Safari (hanya diuji Chromium/Edge).
- Layar mobile (akan fallback ke tampilan responsif bawaan).

## 2026-10-25 — claude-design agent (UI Refinement v5: Form Full Width, Sticky Footer, 3 Systray Dividers, Form Title Statusbar, Badge & Logo O Glow)
**Berubah:**
- `addons/id_ui_shell/static/src/shell/id_shell.scss`:
  - Token `--id-brand-box` disetel ke warna ungu Odoo (`#714B67`).
  - `.o_menu_brand`: ukuran font diperbesar menjadi `1.45rem` (bold 700) di tengah navbar.
  - `.o_menu_systray`: tepat 3 divider pemisah vertikal (tinggi 22px) antar 4 menu (Discuss, Activity, Company, User). Child kosong disembunyikan.
  - `.id_sidebar .id_brandbox`: font lebih besar (0.75rem), bold 700, sudut tegas tanpa rounded, background ungu Odoo.
  - `.id_sidebar__logo`: transisi hover/active diperhalus tanpa shaky rotation, menggunakan `@keyframes id-logo-pulse` dengan double drop-shadow ungu Odoo.
- `addons/id_ui_form/static/src/form/id_form.scss`:
  - `.o_form_sheet_bg`: `max-width: 100% !important; padding: 0.5rem 1rem !important;`
  - `.o_form_sheet`: `max-width: 100% !important; width: 100% !important; margin: 0 !important;` (form lapang dan luas mengisi rongga kiri-kanan).
  - `.o_form_statusbar`: border rapi, background putih, penampung judul dokumen di tengah.
  - `.o_form_sheet .o_group:has(.oe_subtotal_footer)`: sticky bottom (`position: sticky; bottom: 0; background: #fff; z-index: 4; border-top: 1px solid #dee2e6; border-bottom: 1px solid #dee2e6;`).
  - `.id_statusbar_title`: judul dokumen ("New" / nomor referensi) rata tengah di antara tombol aksi dan pipeline status.
- `addons/id_ui_form/static/src/form/form_patch.js`:
  - Relokasi judul form `.oe_title` secara otomatis ke dalam `.o_form_statusbar` pada siklus `onMounted` dan `onPatched`.
- Log: `agent-log/claude-design.log`.

**Diverifikasi (bagaimana):**
- Verifikasi visual Playwright di Chromium: form luas penuh, footer total sticky saat scroll, statusbar title di tengah, systray 3 divider rapi, icon O hover halus.
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Git diff diperiksa bersih dan tidak ada file sementara yang ter-commit.

**Belum diuji:**
- Browser Firefox/Safari (hanya diuji Chromium/Edge).
- Layar mobile (akan fallback ke tampilan responsif bawaan).

## 2026-10-25 — claude-dev agent (sandbox) — Review codebase main fa68c23 (PR #1–#5) + skrip snapshot instance
**Berubah:** `docs/reviews/REVIEW_2026-10-24_main-fa68c23.md` (temuan P0/P1/P2 + rencana M1a–M2 + pemilik area), `scripts/ops/odoo_snapshot.py` (diagnosis read-only via XML-RPC), `scripts/sandbox/sandbox_up.sh` (menyalin `data/` dan `scripts/` seperti Dockerfile), `pyproject.toml` (E501 diabaikan untuk `scripts/ops`), `docs/DEVELOPMENT.md` (catatan snapshot), `agent-log/claude-dev.log`. **Tidak ada perubahan pada kode agen lain.**
**Diverifikasi (bagaimana):** boot persis seperti Railway di sandbox (DB kosong, `INIT_MODULES` default): HTTP siap ±207 detik; 97 modul; 150 produk, 354 outlet; Playwright 0 galat JS; snapshot dijalankan terhadap instance itu; generator deterministik (hash seed 0/5); analisis konsistensi CSV simulasi; uji kegagalan skrip snapshot (sandi/URL/DB salah, sandi tidak bocor).
**Temuan utama:** lihat review §2. P0: `tier_id` 0/354; kota/provinsi/negara/TOP/salesman kosong; produk tidak storable; UoM hanya Units; karyawan/armada/pricelist tidak dimuat; seed gagal tetap di-mark; upgrade hanya sekali; menu FMCG = aplikasi berisi tabel referensi; dashboard menampilkan data contoh USD; admin `en_US`, `id_base` tanpa `id.po`; baris simulasi tidak cocok dengan header (8.513 baris).
**Belum diuji:** snapshot terhadap Railway (menunggu pemilik); status CI hijau hanya dari log AntiGravity; loader pada DB berisi transaksi; apa yang tampil di Railway saat ini (kemungkinan deploy lebih lama dari `main`).
**Butir terbuka:** (1) keputusan pemilik: anonimisasi nama nyata, nama EMP-001, pendekatan kemasan `product.uom`, urutan M1a/M1b/M1c; (2) hasil snapshot Railway; (3) `antigravity`: M1b (mark berbasis hash, gagal = tidak di-mark, VIES off, admin id_ID/Asia/Makassar); (4) `claude-design`: M1c (pindahkan tabel referensi ke Configuration, dashboard contoh, kolom/filter/group-by).
**Menunggu:** pemilik (jalankan snapshot, jawab keputusan); `antigravity` dan `claude-design` membaca review sebelum aksi berikutnya.
**Catatan basis:** `origin/main` maju ke `b8bcbf9` (PR #6/#7, UI v2/v3) saat review disusun; tidak mengubah temuan A–D3. Patch ini hanya menambah baris (diperiksa pada salinan bersih `b8bcbf9`).

## 2026-10-24 — antigravity (laptop/Railway) — Sinkronisasi Modul Otomatis (Fix 500 UndefinedColumn res_partner.channel_id) & Seed Data v2
**Berubah:**
- `deploy/init.sh`:
  - Menambahkan modul `id_ui`, `id_ui_shell`, `id_ui_form` ke variabel default `INIT_MODULES`.
  - Menambahkan fase `upgrade_modules_v1` (`odoo_run -i "$INIT_MODULES" -u "$INIT_MODULES" --stop-after-init`) agar saat container baru boot pada DB yang sudah ada, kolom-kolom baru (seperti `res_partner.channel_id`, `product_template.principal_id`, dll.) dan modul UI baru langsung terpasang dan tersinkronisasi di skema PostgreSQL.
  - Memperbarui mark seed data menjadi `seed_master_v2` sehingga data master 150 produk & 354 outlet dimuat ulang secara lengkap dengan kolom FMCG yang valid setelah modul terpasang.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Analisis log Railway menemukan akar penyebab error HTTP 500: `psycopg2.errors.UndefinedColumn: column res_partner.channel_id does not exist` saat merender `/odoo` atau memproses cron background, akibat DB belum pernah di-upgrade dengan `-u id_base`.
- `ruff check .` lolos bersih (0 galat).
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Sintaks `deploy/init.sh` diverifikasi valid via bash check.

**Belum diuji:**
- Menunggu deployment container baru di Railway untuk memverifikasi endpoint `/odoo` dan `/web` kembali 200 OK secara visual.

## 2026-10-24 — claude-design agent (chat + sandbox) — UI redesign v1: sidebar, topbar, chatter sebagai tab
**Berubah:** addon baru `id_ui` (tema, urutan dan nama menu inti menurut glosarium, aktivasi `en_US`+`id_ID`), `id_ui_shell` (sidebar aplikasi dengan ikon bawaan Odoo, topbar: judul besar + tab seksi + cari menu + nama/role, hotkey Alt+M/Alt+B, mode sidebar/klasik per pengguna), `id_ui_form` (chatter jadi tab terakhir notebook). Docs: `docs/ui/*` (jejak kompatibilitas per addon, usulan istilah glosarium, `e2e/smoke_ui.py`). Log: `agent-log/claude-design.log`. Tidak menyentuh addon lain, CI, `init.sh`, Dockerfile.
**Diverifikasi (bagaimana):** di sandbox, Odoo `f4378f29` (sama dengan SANDBOX.md), DB kosong `-i id_base,id_ui_form --without-demo=true`: 0 failed dari 8 uji; `ruff check .` dan `check_manifests.py` lolos; `docs/ui/e2e/smoke_ui.py` (Playwright/Chromium) 10/10; terjemahan `id_ID` tampil di browser. Performa lokal (1 form, 6 muat ulang): form siap 893–998 ms (sidebar) vs 923–1030 ms (klasik), heap setelah GC 33,5 vs 35,6 MB.
**Belum diuji:** stack OCA penuh bersama addon UI; `docker build`/Railway; CI; browser selain Chromium; layar mobile (memakai NavBar bawaan); form tanpa notebook, dialog, pratinjau lampiran (fallback ke tata letak chatter bawaan, belum diuji di UI); daftar besar. Desain beranda baru (playground HTML di chat) belum dikodekan.
**Butir terbuka:**
1. Konfirmasi nama tanda tangan `claude-design agent` dan `agent-log/claude-design.log` (dipakai sesuai usulan; **[A]**).
2. `id_ui` ber-`depends` pada modul stack inti (`sale_management`, `stock`, `purchase`, `account`, `hr`, `fleet`, `hr_attendance`, `hr_holidays`, `spreadsheet_dashboard`) agar menu mereka ada saat urutan diterapkan. Memasang `id_ui*` berarti modul itu ikut terpasang; `INIT_MODULES` default belum memuatnya.
3. `postinit_v1` punya TODO mengaktifkan `id_ID`; hook `id_ui` sudah mengaktifkan `en_US`+`id_ID` dan menjadikan `id_ID` bawaan partner baru (idempoten; matikan dengan parameter `id_ui.set_default_lang=False`). Hindari menggandakan.
4. Urutan dan nama menu inti diterapkan lewat kode; setelah meng-upgrade modul inti jalankan `-u id_ui`.
5. Titik yang paling mungkin bergeser antar-versi Odoo (patch komponen internal): `WebClient`, `NavBar`/`UserMenu`, `FormRenderer.mailLayout`, `Notebook.computePages`, selector CSS navbar. Daftar di `docs/ui/id_ui_shell.md` dan `id_ui_form.md`.
6. Istilah baru usulan (Gudang & Stok, Armada, Diskusi, Dashboard) di `docs/ui/glossary-additions.md` belum masuk `GLOSSARY.md`.
**Menunggu:** pemilik repo (merge PR #4); `antigravity` (uji di Railway setelah merge).

## 2026-10-24 — antigravity (laptop/Railway) — [M1] Cabang Mandiri agen/m1-historical-simulation, Dataset Transaksi Historis Kausalitas Presisi & Cetak Biru FMCG
**Berubah:**
- **Reorganisasi Cabang:** Memindahkan seluruh pekerjaan simulasi transaksi dan master data ke cabang tersendiri `agen/m1-historical-simulation` (bercabang dari `agen/m1-master-data-models`). Cabang `agen/ui-design-v1` dikembalikan murni ke commit agen `claude-design` (`3c6fb30`).
- **Dokumentasi Cetak Biru (`docs/blueprints/`):**
  - `master_data_mapping_and_seed_plan.md`: Cetak biru hierarki master data, 15 Kab/Kota Sulut, 150 SKU, 354 outlet, 24 roster staf, 9 tipe armada kargo riil, dan 9 zona gudang WMS.
  - `pjp_and_outlet_distribution_model.md`: Pemodelan rute kunjungan PJP Senin–Sabtu, rasio call density (MT 8-10, GT 20-22, Canvass 25-30), dan loading armada H+1.
  - `historical_simulation_and_turnover_model.md`: Pemodelan simulasi kausalitas historis 1 Juli s/d 24 Oktober 2026 (Juli krisis overstok 10B net margin 0.9%, Agustus drop 23% net margin 2.5%, September konsolidasi sehat net margin 3.7%, Oktober rebound MTD 5.3B net margin 5.0%, utilisasi armada 89%).
  - `REVIEW_FEEDBACK_LOG.md`: Dokumentasi riwayat komprehensif review pengguna, feedback lapangan, dan keputusan desain arsitektur.
- **Generator & Loader Transaksi Historis:**
  - `scripts/generate_historical_simulation.py`: Menghasilkan dataset deterministik terkalibrasi presisi:
    - `data/seed/sales_orders_historical.csv`: 3.762 transaksi faktur penjualan harian riil (97 hari kerja operasional).
    - `data/seed/sales_order_lines_historical.csv`: 8.513 baris line item produk, karton, dan lot FEFO.
    - `data/seed/inbound_po_historical.csv` & `inbound_po_lines_historical.csv`: 11 Inbound PO Kontainer Bitung & jadwal AP.
    - `data/seed/opex_vendor_bills.csv`: 20 Vendor Bills beban operasional bulanan.
    - `data/seed/daily_logistics_metrics.csv`: 97 hari metrik okupansi gudang dan utilisasi 9 armada.
    - `data/seed/historical_simulation_summary.json`: Ringkasan finansial terkalibrasi (Omset Rp 18.995 BIO, OPEX Rp 1.619 BIO, Laba Bersih Rp 566.89 jt, Margin 2.98%).
  - `scripts/load_historical_simulation.py`: Loader Odoo shell idempoten untuk `account.move` (OPEX vendor bills), `purchase.order`, dan `sale.order`.

**Diverifikasi (bagaimana):**
- `python scripts/generate_historical_simulation.py` sukses menghasilkan seluruh dataset.
- `python -m ruff check .` lolos bersih (0 galat).
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Cabang `agen/ui-design-v1` diverifikasi ter-reset bersih pada commit `3c6fb30`.
- PR #2 dan PR #3 telah diverifikasi dan di-merge ke `main`.
- CI GitHub Actions lolos 100% HIJAU (PASS).

**Belum diuji:**
- Pemuatan seluruh data ke Odoo staging di Railway (akan terpicu otomatis saat seluruh PR di-merge ke main).

**Butir terbuka:**
- Merge PR #4 ke `main`.
- Verifikasi deployment otomatis di Railway Staging (`https://odooca-fmcg-demo.up.railway.app`).

**Menunggu:** pemilik repo (merge PR #4 di GitHub).

## 2026-10-24 — claude-dev agent (sandbox) — Sinkron remote, verifikasi perbaikan AntiGravity, protokol multi-agen
**Berubah:** `AGENTS.md` (protokol 8 aturan), `docs/AGENT_PROTOCOL.md` (peran, sebelum/sesudah aksi, format commit dan log), `scripts/agent/whats_new.sh` dan `log_entry.sh`, `agent-log/claude-dev.log`, `docs/DEVELOPMENT.md` §1 dan §4 (kebijakan tanpa Docker lokal, alur multi-agen, perintah patch + tanda tangan), `docs/SANDBOX.md`, `scripts/sandbox/sandbox_up.sh` (user `odoo`, salinan addons), `ci.yml` (`bash -n` mencakup skrip agen). Izin eksekusi skrip diperbaiki (100755).
**Diverifikasi (bagaimana):** (1) `git fetch` menemukan commit AntiGravity `eebee64` dan merge PR #1 `fcd62e8`; (2) perbaikan `init.sh` AntiGravity diuji independen di sandbox: A DB kosong (HTTP 200, Odoo berjalan sebagai `odoo`, data dir `odoo:odoo`, 0 galat), B restart 5 detik semua dilewati, login admin OK, `chown -R` 3000 berkas = 22 ms; (3) `whats_new.sh` dan `log_entry.sh` dijalankan pada repo nyata (2 bug diperbaiki); (4) `ruff`, `check_manifests.py`, `bash -n`, YAML lolos.
**Belum diuji:** job `init-test`/`install-test` di GitHub Actions; `gosu`/`runuser` di image `odoo:19.0` (di sandbox yang terpakai `runuser`); `docker build` di luar Railway; `--ignore-installed` dapat menimpa paket Debian (diterima untuk demo); tanda tangan commit belum divalidasi otomatis.
**Butir terbuka:**
1. Konfirmasi nama tanda tangan dan nama log untuk `claude-design` (usulan: `claude-design agent`, `agent-log/claude-design.log`).
2. Perlu job CI yang menolak commit non-merge tanpa tanda tangan? (belum dibuat)
3. Skrip tercatat 100644 di mesin pemilik: pakai `git add --chmod=+x` (lihat DEVELOPMENT §4); cek `git config core.fileMode`.
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik (unzip, commit, push); `antigravity` (log Railway setelah merge); `claude-design` (belum aktif di repo).

## 2026-10-24 — AntiGravity Agent (Railway Staging/Production) — Perbaikan Build Docker & Deploy Sukses di Railway
**Berubah:**
- `Dockerfile`: pip install menggunakan `--ignore-installed` pada dependensi OCA untuk mencegah konflik paket Debian (`typing-extensions`); melepas direktif `USER odoo` agar entrypoint kontainer dapat melakukan chown volume sebelum menurunkan hak akses.
- `deploy/init.sh`: mendeteksi inisialisasi root kontainer, mengamankan kepemilikan `$DATA_DIR` (`/var/lib/odoo`) ke `odoo:odoo`, lalu mengeksekusi script sebagai `odoo` via `gosu`/`runuser`/`su`.
- `.gitignore`: mengecualikan `agent-log/*.log` agar log koordinasi agen tersimpan di repo.
- `agent-log/anti-gravity.log`: dibuat untuk melacak aktivitas dan koordinasi antar-agen.

**Diverifikasi (bagaimana):**
- Static checks: `ruff check .` lolos, `python scripts/check_manifests.py` lolos, `bash -n deploy/init.sh` lolos.
- Build live di Railway (`ca437306-0e9d-414e-accf-5c23fa9de3cc`): image assembly sukses 100% (26 repo OCA & dependensi terpasang).
- Runtime live di Railway: Odoo 19 CE berhasil inisialisasi database `railway`, menginstal 55 modul termasuk `id_base` ('FMCG Distributor Base') dan `l10n_id` ('Indonesian - Accounting').
- HTTP Probe: `https://odooca-fmcg-demo.up.railway.app/web/login` mengembalikan HTTP 200 OK.

**Belum diuji:**
- Merge branch / patch dari Agent 2 (Claude Design).
- Fungsionalitas login admin via browser dengan sandi baru dari env.
- Restore dump database dari Release asset.

**Butir terbuka:**
1. Integrasi kode Agent 2 (Design modification) saat sudah siap dimerge.
2. Pengujian fitur modul FMCG di live staging Railway.

**Menunggu:** Pemilik repo & Agent 2 (Claude Design) untuk integrasi kode design.

## 2026-10-23 — Claude (sandbox, Odoo 19 penuh) — Verifikasi M0 dengan menjalankan Odoo
**Berubah:** `init.sh` (urutan `shell` sebelum opsi; build `base`→ID/IDR→modul; reset tabel satu per satu); `oca.lock` 18→26 repo; CI + job `init-test`; `scripts/sandbox/*`; `docs/SANDBOX.md`; `docs/SCOPE.md` v0.6; jebakan baru di `docs/ODOO19_PITFALLS.md`; spike dipersempit.
**Diverifikasi (bagaimana):** di sandbox (Ubuntu 24.04, Postgres 16, Odoo `f4378f29`): (1) `id_base` terinstal, uji 0 failed; (2) 65 modul core+OCA → 165 modul terinstal, 0 ERROR; (3) `init.sh`: A DB kosong (HTTP 200 ±66 s), B restart (6 s, semua dilewati), C reset+restore (17 s), D token lama diabaikan, E reset+build (±69 s); login admin sandi baru OK, `admin/admin` ditolak, daftar DB ditolak, `web.base.url` terkunci, objek dimiliki `odoo_app`, chart `id` 118 akun, 0 pajak 15%.
**Bug yang ditemukan lewat uji dan diperbaiki:** `shell` setelah opsi; `DROP SCHEMA CASCADE` → `out of shared memory`; dump naif bentrok dengan `id_meta`; COA generik termuat bila negara belum ID.
**Koreksi atas klaim sebelumnya:** 6 modul OCA yang saya tulis "ada" ternyata `installable: False` (`base_rest`, `base_rest_auth_api_key`, `pydantic`, `rest_log`, `queue_job_batch`, `base_import_async`).
**Belum diuji:** `docker build` + `pip install` di image Ubuntu (apt vs pip); job CI `init-test`/`install-test`; Railway (volume, variabel, restore dari Release asset); seed engine; `postinit` untuk bahasa `id_ID`; fungsional modul OCA (hanya terinstal); `fastapi` sebagai endpoint; instal ulang tanpa sandbox.
**Butir terbuka:**
1. Log build/deploy Railway setelah push pertama (tempel ke percakapan).
2. Deploy otomatis setiap push menyalakan layanan Hobby: pasang hard usage limit.
3. `requirements.txt` seluruh repo OCA ikut terpasang di image (pysaml2, numpy, paramiko, dll.): pertimbangkan hanya yang dipakai.
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik repo (unzip, commit, push, log Railway).

## 2026-10-23 — Claude (chat, sandbox tanpa Docker) — M0 kerangka repo
**Berubah:** kerangka repo awal (Dockerfile, `deploy/init.sh`, compose, CI, `oca.lock`, `scripts/`, addon `id_base`, dokumen). `docs/SCOPE.md` v0.5, Playbook v0.4, Glosarium draf.
**Diverifikasi (bagaimana):**
- `scripts/fetch_oca.sh` dan `scripts/oca_bump.sh` dijalankan pada 2 repo OCA nyata; SHA cocok.
- `scripts/check_manifests.py` lolos; `ruff check .` lolos; `bash -n` semua skrip; YAML (`ci.yml`, `docker-compose.yml`) valid.
- Isi source Odoo 19 CE (commit `f4378f29`, 2026-10-22) dan 18 repo OCA 19.0 diperiksa untuk keberadaan modul (lihat SCOPE §5).
**Belum diuji:** `docker build`; `deploy/init.sh` (peran DB, restore, reset, postinit, `odoo shell`); instal `id_base` di Odoo 19; CI; `pip install` dependensi OCA di image (risiko bentrok paket apt); `admin_passwd` polos di `odoo.conf`; opsi `--without-demo=true`, `--no-database-list`; kebenaran tag `odoo:19.0` di Docker Hub (digest belum di-pin).
**Butir terbuka:**
1. Hasil run pertama CI dan `docker compose up` (perbaiki kerusakan yang muncul).
2. Spike API/offline (`docs/spikes/SPIKE_API_OFFLINE.md`) sebelum M6.
3. Kontrol dokumen asal Odoo/mobile pada mode secondary (SCOPE §13 #1).
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik repo (commit pertama dan menjalankan CI).

<!-- Entri baru di atas entri lama. Templat ada di docs/DEVELOPMENT.md §10. -->
