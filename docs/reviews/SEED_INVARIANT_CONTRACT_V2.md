# Kontrak invariant seed v2 (periode Agustus 2026 dan seterusnya)

**Status:** diajukan claude-dev, 2026-11-05. Memperluas, tidak menggantikan, `SEED_INVARIANT_CONTRACT.md` (v1). v1 tetap berlaku penuh untuk Juli 2026 dan tidak diubah.
**Dasar:** analisis dan keputusan di `docs/blueprints/SEED_AGUSTUS_NOVEMBER_ANALISIS_DAN_PLAN.md` (Bab 9A). Instruksi pemilik 2026-11-05: K1 seed s/d Kamis 5 Nov, mesin harian hanya 6 Nov+; K2 Juli beku, kalibrasi biaya, retur dan diskon; K3 opsi A (tambah ke database live) dengan micro-slicing presisi; K4 campuran principal organik; dokumen live PWA = fakta; pemicu via shell oleh antigravity.
**Penandaan:** [F] fakta bersumber · [A] asumsi · [BU] belum diuji (AGENTS.md butir 6).

## 1. Aturan yang tidak berubah dari v1

Tidak ada allowlist atau pengecualian baseline. Tidak boleh melebarkan toleransi (uang: Rp0,01, `Decimal`), menghapus tes, memakai `continue-on-error`, atau menyembunyikan check. CI hijau dasar bukan penerimaan seed. Perubahan kontrak/validator wajib dijelaskan di PR dan HANDOFF dengan referensi instruksi pemilik. Parameter bisnis (saldo awal kas, pita naratif, lead time, sumber pajak) **ditetapkan pemilik**, bukan worker, dan tidak boleh dilebarkan untuk meloloskan pack.

## 2. Pack periode

Satu pack per bulan di `data/registers/periods/<YYYY-MM>/`, memakai skema berkas yang sama dengan register Juli (`perpetual_*.csv`, header PO, ledger stok) ditambah `MANIFEST.json` (SHA-256 LF-kanonikal tiap berkas, SHA commit generator, hash 15 register Juli, versi konfigurasi anchor/biaya/diskon, sumber pajak bertanggal). Register Juli tidak diubah dan tidak diregenerasi.

| Aturan | Isi |
|---|---|
| Jendela | `pack_start`..`pack_end` (hari kalender). SO dan event stok di dalam jendela; DO, faktur dan retur boleh sampai hari kerja resmi berikutnya (carry-forward) |
| Carry-forward | SO hari terakhir pack, DO/faktur hari kerja berikutnya. Dokumen tetap milik pack asal (preseden Juli: 48 DO/faktur 1 Agustus). Event stok penyelesaiannya (DO dispatch) **masuk ledger pack berikutnya** [F: ledger Juli tidak memuat event setelah 31 Juli] |
| Penomoran | `SO/DO/INV-YYYYMM-NNNN`, `REJ-YYYYMM-NNN`, `PO-YYYY-MM-NN`; `PAY-AR-NNNNN`, `PAY-AP-NN`, `EVT-NNNNNN` berurutan global. Setiap deret berlanjut dari nomor terakhir yang sudah ada |
| PO | PO yang dipesan di dalam pack wajib membawa `rop_trigger_date` dan `rop_cover_days`. PO dipesan sebelum pack = in-transit pada pembukaan |
| Faktur | kolom PPN bernama `ppn_amount` (nama lama `ppn_11_amount` masih diterima karena register Juli) |
| Pembayaran | satu pelunasan penuh per faktur; pembayaran parsial AR/AP memerlukan perluasan skema dan tes (sama dengan v1) |

## 3. Gate v2

Implementasi: `scripts/ops/seed_v2_gates.py` (murni, tanpa Odoo). Tes: `tests/test_seed_v2_gates.py` (fixture bersih lulus; setiap mutasi ditolak; baseline Juli nyata lulus). Gate inti selalu berjalan; gate berbasis konfigurasi hanya berjalan bila inputnya ada, dan **penerimaan wajib memakai `strict=True`** agar gate yang terlewat menjadi pelanggaran.

### 3.1 Dapat dieksekusi sekarang

| ID | Invariant | Parameter / sumber |
|---|---|---|
| INPUT-SCHEMA | tabel wajib ada dan tidak kosong; kolom wajib ada; angka valid | skema pack |
| CALENDAR-OFFICIAL | tanggal SO, DO, faktur, retur, PO (pesan dan terima), pembayaran AP, OPEX dan event stok adalah hari kerja resmi menurut `fmcg_calendar.py` (satu-satunya sumber); tahun di luar 2026 ditolak karena kalender belum memuatnya. Tanggal pembayaran AR **sengaja tidak diuji** (transfer bank dapat jatuh pada hari non-kerja; 25 kasus di Juli) | `fmcg_calendar.py` |
| PERIOD-WINDOW | dokumen dan event berada di jendela pack; carry-forward hanya sampai hari kerja berikutnya | `pack_start`, `pack_end` |
| NUMBERING | format valid, unik, tidak bertabrakan dengan nomor yang ada, berurutan tanpa celah dari nomor terakhir, monoton terhadap tanggal, bulan nomor SO/PO sama dengan bulan tanggalnya | nomor yang ada |
| STOCK-NONNEG | replay ledger berurutan: fisik, reservasi dan karantina tidak negatif, reservasi ≤ fisik, event id unik, tanggal tidak mundur, karton bilangan bulat | saldo pembukaan |
| PERIOD-CONTINUITY | pembukaan yang dideklarasikan = penutupan pack sebelumnya (stok per SKU/lot, piutang terbuka, piutang carry-forward, hutang terbuka, PO in-transit, DO tertunda). `replay_closing` menghitung penutupan | `previous_closing` |
| PO-CAUSALITY | PO dalam pack punya pemicu ROP (tanggal kerja, tidak setelah pesan) dan cover positif; terima ≥ pesan + lead time minimum principal | `min_lead_days` |
| AR-TERMS | jatuh tempo = tanggal faktur + TOP; pembayaran mengenal faktur, tidak mendahului, tidak ganda | skema |
| AP-TERMS | jatuh tempo = terima + TOP; pembayaran mengenal PO dan tidak mendahului penerimaan | skema |
| TAX-SOURCE | konfigurasi pajak wajib punya tarif, sumber resmi, tanggal sumber dan tanggal berlaku; PPN = DPP × tarif (pembulatan sen), total = DPP + PPN; faktur tidak mendahului tanggal berlaku. Tarif tidak dikunci dalam kode | `config.tax` (K8) |
| CASH-NONNEG | saldo kas penutupan harian tidak negatif dari saldo awal yang disahkan. Kas masuk AR berbasis total termasuk PPN, AP berbasis DPP (PPN masukan belum dimodelkan, gap G-07) | `config.opening_cash` (K5) |
| NARRATIVE-ANCHORS | omzet net DPP, diskon %, tolakan %, outlet aktif per bulan berada dalam pita terversi | `bands` (K2/K5) |

### 3.2 Belum dapat dieksekusi (dinyatakan terbuka, bukan lulus)

| ID | Alasan | Fase |
|---|---|---|
| SLICE-ATOMIC, SLICE-IDEMPOTENT, LIVE-AS-FACT, PACK-TO-DAILY-CONTINUITY | memerlukan mesin harian dan loader slice; spesifikasi ada di plan Bab 9A | F9 |
| Gate v1 per pack (MASTER-*, COHORT-*, SO-PRINCIPAL, PJP-SO, LINE/HEADER/PO/STOCK-MATH, TX-FK/COVERAGE, EVENT-ORDER, COLLECTION, LOT/FEFO/EXPIRY) | validator v1 terikat nama berkas Juli; harus diparameterkan per direktori pack tanpa mengubah perilaku untuk Juli | F2 |
| FLEET-CAPACITY | kapasitas armada per kendaraan belum ditetapkan pemilik | menunggu data |
| ROUND-NUMBER | heuristik angka bulat buatan perlu definisi dan ambang dari pemilik | menunggu keputusan |
| Bukti runtime Odoo | tetap seperti v1 (instal, replay 0 record, GL/stok/AR/AP/PPN, upgrade, imutabilitas bulan sebelumnya, snapshot) dan ditambah: backup DB+filestore sebelum tiap blok bulan, guard database demo, pembuktian pada database disposable berisi data pembanding | F5, F8, F9 |

## 4. Parameter yang menunggu pemilik

| Parameter | Status |
|---|---|
| `opening_cash` / fasilitas kredit modal kerja | K5 belum dijawab; tanpa nilai, CASH-NONNEG gagal pada strict. Bukti: register Juli tanpa saldo awal → kas minimum −Rp3.163.173.047,71 pada 31 Juli (gap G-06), tidak di-allowlist |
| `bands` NARRATIVE-ANCHORS | nilai ditetapkan pemilik; kurva sasaran di plan Bab 9A hanya arah [A]. Pita terversi dan di-hash di manifest, tidak dapat dilebarkan worker |
| `min_lead_days` per principal | Ditetapkan pemilik per F2: **Hari Kerja Operasional (working days: Senin s/d Sabtu, di luar hari libur nasional SKB 3 Menteri)**. Nilai acuan: Unilever 14, Wings 10, Mayora 12, Santos/ABC 10 hari kerja. Dihitung via `fmcg_calendar.count_working_days(order, arrival) >= min_lead`. |
| `config.tax` | tarif, sumber resmi bertanggal dan tanggal berlaku harus dicatat; acuan awal: PMK 131/2024 (pajak.go.id, dibaca 2026-11-04), perlu verifikasi ulang sebelum dikunci (K8) |

## 5. Bukti saat penyusunan

[F] Register Juli yang beku lulus seluruh gate v2 yang berlaku untuknya (tanpa CASH-NONNEG/NARRATIVE-ANCHORS/PERIOD-CONTINUITY yang butuh input): kalender resmi, jendela, penomoran, replay stok per event, TOP AR/AP, PPN 11%. `replay_closing` atas Juli menghasilkan 53.837 karton fisik, 1.038 reservasi, 9 karantina, 309 piutang terbuka, 48 piutang carry-forward, 48 DO tertunda dan satu hutang terbuka (`PO-2026-06-05`), sama dengan laporan rekonsiliasi kanonikal.
[F] Gate CALENDAR v1 memercayai kolom `is_working_day` kartu stok milik dataset sendiri dan hanya mengeraskan hari Minggu (gap G-17); CALENDAR-OFFICIAL v2 memakai kalender resmi sebagai sumber tunggal.
[F] Setiap pemeriksa v2, bila dimatikan, membuat sedikitnya 2 tes gagal (uji mutasi atas validator), sehingga tidak ada gate yang hanya dekoratif.
[BU] Perilaku pada pack nyata, runtime Odoo dan database live belum diuji; belum ada pack Agustus.

## 6. Alur penerimaan pack

1. Worker menghasilkan pack dari planner yang sama dengan mesin harian; manifest ditulis.
2. `python -m unittest discover -s tests -p 'test_*.py'` hijau; validator v1 per pack hijau (setelah F2); validator v2 `strict=True` hijau dengan semua input pemilik terisi dan laporan memuat `gates_skipped == []`.
3. CI exact-SHA; supervisor menilai laporan, diff dan bukti requirement.
4. Pemilik menyetujui; pemuatan ke database live per hari-slice, dengan backup sebelum tiap blok bulan, dijalankan antigravity.
