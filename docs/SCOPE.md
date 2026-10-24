# SCOPE.md — Odoo 19 CE untuk Distributor FMCG Manado (Demo/PoC)

Status: **DRAFT v0.6** · 2026-10-23 · Fase 0 (Discovery), metode `odoo-delivery-method`
Rujukan bisnis: *Business Meta & Playbook Distributor FMCG v0.3* (selanjutnya "Playbook").
Legenda: **[F]** fakta bersumber (bertanggal) · **[A]** asumsi (konfirmasi) · **[BU]** belum diuji/diverifikasi

---

## 0. Perubahan (v0.1 → v0.3)
- Cakupan diselaraskan dengan Playbook; v0.1 terlalu sempit (HRIS, payroll, Coretax, mobile, integrasi sebelumnya "di luar scope").
- **Channel** (segmen customer: MT/GT/Retail/Institusional) dipisahkan dari **model penjualan** (Taking Order/Canvassing/Direct Selling). v0.1 mencampurnya.
- Dimensi analitik naik dari 3 ke 8 sesuai Playbook §3.4.
- Mode operasional Odoo ditentukan: **secondary lebih dulu, lalu primary** (Playbook §5.2).
- **v0.3:** asesmen PWA vs kustomisasi Odoo (§4A) → arsitektur **hybrid**. Absensi demo = foto + geotag (face recognition ditunda). Payroll demo = struktur generik + PPh 21/BPJS berparameter fiktif.
- **v0.3 (koreksi dari source Odoo 19 CE):** CE sudah punya modul Coretax (`l10n_id_efaktur_coretax`) dan pajak PPN 12% efektif 11% di `l10n_id` → `id_coretax_prep` **memperluas** modul itu, `id_tax` tidak diperlukan; COA CE hanya 118 akun (chart `id`) → perlu `id_coa`.
- **v0.4:** keputusan pemilik dimasukkan: aplikasi mobile **selalu sinkron ke Odoo**, sinkron ke legacy DMS via **ekspor manual** (§4A.4); **satu aplikasi dengan tab dinamis menurut app role** (§4A.5); PWA Preact + Vite, native Android setelah proyek disetujui; tanpa gudang transit; UI Indonesia penuh + English (§4C); asesmen hosting Railway Free (§4B, **ada risiko**). Playbook diperbarui ke v0.4.
- **v0.5:** keputusan hosting dan app role ditutup (§4B, §4A.5); repo dibangun sebagai kerangka M0 (lihat `docs/DEVELOPMENT.md` di repo). Dump DB **tidak** disimpan di git karena repo publik; dibagikan sebagai Release asset (§4B).
- **v0.6:** klaim diganti hasil uji nyata di sandbox (Odoo 19 `f4378f29`, Postgres 16, 2026-10-23): 65 modul core+OCA diinstal (165 modul, 0 ERROR); **6 modul OCA ternyata `installable: False`** sehingga klaim "ada" di v0.2–v0.5 keliru/menyesatkan; 8 repo OCA tambahan diperlukan (`oca.lock` 18 → 26); COA Indonesia hanya termuat bila negara = ID sebelum akuntansi diinstal; `init.sh` diuji 5 skenario dan 2 bug ditemukan serta diperbaiki.

## 1. Tujuan & narasi demo
Calon klien melihat satu distributor FMCG multi-prinsipal di **Manado (Sulut)**, coverage ±100–150 km, dengan data **fiktif**:
1. **Data masuk ke Odoo (mode secondary):** master, SO, stok, invoice, update AR diimpor dari DMS sumber (disimulasikan) via CSV/XLSX dan API.
2. **Aplikasi lapangan (PWA):** sales ordering, delivery, dan HRIS (absensi, cuti, payslip) berjalan di atas data itu.
3. **Odoo sebagai DMS yang fungsional:** SO dan invoice manual di antarmuka Odoo, order-to-cash penuh, akuntansi dasar + COA lengkap, modul persiapan Coretax.
4. **Monitoring ter-dashboard:** sales, fulfillment, logistik, AR/collection, produktivitas sales, produktivitas logistik.
5. **Peralihan ke mode primary** ditunjukkan setelah mode secondary.

**Terkonfirmasi (pemilik, 2026-10-23):** Odoo = *stack main DMS*. Distributor yang sudah punya DMS (**legacy DMS**) mengirim data ke Odoo (mode secondary); aplikasi mobile terintegrasi ke Odoo. Pada demo, legacy DMS diemulasi `id_demo_seed` lewat berkas/API. Aplikasi mobile **selalu** menulis ke Odoo; sinkron ke legacy DMS lewat ekspor manual (§4A.4).

## 2. Cakupan demo (in scope)
| # | Komponen | Isi demo | Rujukan Playbook |
|---|---|---|---|
| A | **Integrasi data (secondary)** | Konfigurasi mode & sumber per jenis data (SO, stok, invoice, AR), template XLSX/CSV bernomor versi + panduan, validasi pra-posting, dedup via kunci unik, log batch/baris, kirim ulang, rekonsiliasi stok & AR, sinkronisasi master incremental, **ekspor manual ke legacy DMS** (template bernomor versi), penanda `origin_system` | §5.2 |
| B | **Odoo DMS (order-to-cash penuh)** | Master (principal, produk, outlet, area, tier), harga bertingkat, diskon berlapis, kebijakan kredit 4 mode, approval, SO manual (layar keyboard-first), picking → DO → invoice → pembayaran → closing harian, FEFO/lot/ED, Stock on Delivery, Money in Transit | §2.6, §3.1–3.2, §3.6 |
| C | **PWA Sales Ordering** | PJP harian, check-in tervalidasi geotag, order, foto bertimestamp, penagihan | §2.6, §5 |
| D | **PWA Delivery** | Daftar DO per kendaraan, serah terima + foto, terima uang (cash/transfer), validasi pengiriman | §2.6, §5 |
| E | **WMS dasar + fulfillment** | Lokasi/zona dasar, putaway rule dasar, batch picking, FEFO, near-expiry, fill rate, backorder | §2.9, §6 |
| F | **HRIS (PWA + Odoo)** | Absensi (geotag + foto), pengajuan & approval cuti, payslip digital; payroll dasar di Odoo (struktur gaji, slip, jurnal setelah approval owner) | §5.1 |
| G | **Dashboard monitoring** | 6 area: sales, fulfillment, logistik, AR/collection, produktivitas sales, produktivitas logistik | §8 |
| H | **Akuntansi** | COA lengkap, laporan umum (GL, TB, neraca, L/R, aging AR/AP, kas), jurnal bank/kas, akun perantara uang di jalan | §3.3–3.4, §4.4 |
| I | **Modul persiapan Coretax** | Validasi data partner/faktur, penyusunan data faktur keluaran, ekspor XML, antrean & pelacakan status manual | §3.5 |

C, D, dan F adalah **satu aplikasi PWA** dengan tab dinamis menurut *app role* (§4A.5): HRIS untuk semua role, Sales Ordering untuk salesman, Logistic Delivery untuk logistic.

## 3. Di luar scope demo (fase berikutnya, jadwal terpisah)
Face recognition sungguhan (demo = foto + geotag), optimasi rute otomatis, WMS 3D/slotting lanjutan, listener desktop (hanya spesifikasi/stub), host-to-host Coretax/PJAP, e-Bupot, BPJS/PPh 21 sebagai kepatuhan penuh (demo memakai parameter fiktif bertanda), aplikasi native, konsinyasi, multi-company.

## 4. Arsitektur demo (hybrid, hasil asesmen §4A) **[A]**
```
 DMS sumber (simulasi: seed engine)
   │ CSV/XLSX + API  (queue_job, validasi, log)
   ▼
 ┌────────────── Odoo 19 CE (Railway) ──────────────┐
 │ id_integration · id_pricing/discount/credit/approval │
 │ id_distribusi · id_hris_ext · id_coretax_prep        │
 │ id_dashboard · id_api (REST)                         │
 └───────────────┬──────────────────────────────────┘
                 │ REST (token) – offline queue
         PWA (service terpisah): Sales · Delivery · HRIS
 Postgres (Railway)
 Ekspor manual XLSX/CSV ──► legacy DMS (sinkron manual oleh operator)
```
- Railway: layanan **odoo** dan **postgres**; **pwa** (statis) di Railway atau host statis lain (§4B). Dump-restore, penanda init, patch idempoten (skill `odoo-deploy-and-handoff`).
- PWA: offline-first (IndexedDB + antrean keluar/outbox, idempotency key, server menghitung ulang harga/diskon/kredit saat sinkron) **[A]**; stack ringan (mis. Vite + Preact) **[A]**; satu aplikasi, tab dinamis menurut app role (§4A.5).
- Lisensi: **LGPL-3** untuk addon `id_*` (selaras Odoo Community & OCA).

## 4A. Asesmen: PWA sendiri vs kustomisasi Odoo (diverifikasi 2026-10-23)

### 4A.1 Fakta dari source Odoo 19 CE **[F]** (`odoo/odoo` cabang 19.0, commit `f4378f29`, 22 Okt 2026)
- Web client Odoo dapat dipasang sebagai PWA (webmanifest `display: standalone`, scope `/odoo`). Service worker hanya menyimpan halaman awal dan halaman offline sebagai cadangan saat fetch gagal. **Tidak ada penyimpanan data lokal maupun antrean tulis offline.**
- `hr_attendance` CE menyimpan latitude/longitude masuk dan keluar; **tidak ada field foto**. Dependensi: `hr`, `barcodes`, `base_geolocalize`.
- **Tidak ada di CE:** `stock_barcode`, `hr_payroll`, `approvals`, `documents`, `spreadsheet_edition`, `web_studio`, `account_reports`.
- **Ada di CE (LGPL-3):** `stock_picking_batch`, `product_expiry`, `fleet`, `hr_holidays`, `spreadsheet_dashboard`, `l10n_id`, `l10n_id_efaktur_coretax`.

### 4A.2 Penilaian opsi (penilaian saya **[A]**, perlu spike untuk dikunci)
| Kriteria | 1. Odoo-native (web client/PWA terpasang + view OWL kustom) | 2. PWA sendiri penuh | 3. **Hybrid** |
|---|---|---|---|
| Offline di lapangan (Playbook §9) | Rendah: perlu membangun lapisan offline di dalam OWL, praktis aplikasi baru | Tinggi | Tinggi (lapangan) |
| Kecepatan input order | Sedang | Tinggi | Tinggi (lapangan); layar keyboard-first di Odoo (admin) |
| Geotag + foto bertimestamp | Sedang (JS kustom) | Tinggi | Tinggi |
| Permukaan akses | Lebar: pengguna lapangan = user backend | Sempit (hanya endpoint) | Sempit untuk lapangan; backend hanya staf |
| Usaha bangun | Sedang, melonjak bila offline wajib | Tinggi (ulang approval, admin HR, dashboard) | Sedang |
| Risiko saat upgrade Odoo | Sedang (internal OWL berubah antar versi) | Rendah (kontrak API) | Rendah–sedang |
| Reuse back-office Odoo | Penuh | Rendah | Penuh |

### 4A.3 Rekomendasi: **hybrid**
| Peran | Dikerjakan di |
|---|---|
| Salesman (TO, canvasser) | **PWA** (offline) |
| Driver, helper | **PWA** (offline, foto serah terima, terima uang) |
| Karyawan (absen foto+geotag, cuti, payslip) | **PWA**, tab di shell yang sama |
| Sales admin, supervisor/approver, finance, owner | **Odoo web** (layar order keyboard-first, inbox approval, laporan) |
| Kepala/admin gudang | **Odoo web** (batch picking FEFO, tablet) |
| HR admin, payroll | **Odoo web** |
| Dashboard monitoring, Coretax | **Odoo web** |

Alasan utama: kebutuhan offline tidak dilayani Odoo CE (§4A.1), sedangkan semua logika bisnis (harga, diskon, kredit, approval, stok, akuntansi) tetap satu sumber di Odoo.

**Kontrak PWA ↔ Odoo (`id_api`):** versi `/api/v1`, token per pengguna yang dipetakan ke user/karyawan (bukan satu akun sudo bersama), idempotency key dari klien, `pull` master incremental berdasar `write_date`, `push` outbox. Harga offline hanya sementara: saat sinkron server menghitung ulang dan membalas status *diterima / butuh approval / ditolak*. **OCA `fastapi` terinstal di Odoo 19 [F, uji]** (satu-satunya modul `rest-framework` yang installable; tanpa otentikasi bawaan, jadi token per pengguna dibuat sendiri). Fungsionalnya belum diuji; spike M0 memutuskan `fastapi` vs controller sendiri.

**Keterbatasan PWA yang jujur [A, pengetahuan umum, belum diuji di sini]:** geolokasi hanya saat aplikasi aktif, deteksi mock-location dan push notification lebih lemah dibanding aplikasi native. Untuk demo cukup. Untuk produksi dengan kontrol fraud ketat (Playbook §2.11), evaluasi aplikasi native belakangan. Server mencatat waktu terima, waktu klien, dan akurasi GPS, lalu menandai anomali.

### 4A.4 Keputusan: aplikasi mobile selalu sinkron ke Odoo; legacy DMS via ekspor manual (2026-10-23)
- Semua data aplikasi mobile (HRIS, Sales Ordering, Delivery) ditulis ke Odoo sebagai stack utama, pada mode primary **maupun** secondary.
- Pada distributor dengan legacy DMS, arah Odoo → legacy dilakukan **manual lewat ekspor data** (template ekspor bernomor versi di `id_integration`) disertai laporan selisih.
- Risiko dua sumber kebenaran dikendalikan lewat: penanda `origin_system` (legacy | odoo | mobile) pada SO, invoice, pembayaran, dan transfer; kunci unik lintas sistem agar impor ulang dari legacy tidak menggandakan data; laporan rekonsiliasi; dan kontrol menurut asal dokumen (asal legacy = informatif, asal Odoo/mobile = kontrol penuh). **[A]**
- Playbook §5.2 dan §5.3 sudah diperbarui (v0.4).

### 4A.5 Satu aplikasi, tab dinamis menurut app role
- **App role** = field tambahan pada karyawan, terpisah dari jabatan dan divisi (model `id_app.role`, many2many ke `hr.employee` **[A]**).
- Tab: **HRIS untuk semua role**; Sales Ordering untuk role salesman; Logistic Delivery untuk role logistic. Daftar tab per role adalah konfigurasi di Odoo, bukan kode klien.
- `GET /api/v1/me/bootstrap` mengembalikan role, tab, izin, dan versi master. **Server menegakkan izin**, bukan hanya UI.
- **Kasus canvassing:** canvasser menjual dan mengantar sendiri, sehingga butuh dua tab. Karena itu role sebaiknya dapat bertumpuk (many2many). **Diputuskan (2026-10-23): role bertumpuk**, satu karyawan boleh punya beberapa app role.
- Kontrak API bertipe (OpenAPI) dengan logika bisnis di server → aplikasi native Android nanti memakai API yang sama; PWA ditulis tipis.

## 4B. Hosting dan anggaran Railway **[F, diverifikasi 2026-10-23; sumber: docs.railway.com Pricing/Plans dan ringkasan pihak ketiga Agu 2026]**
- **Free:** $0/bulan dengan kredit pemakaian **$1/bulan** (tidak digulirkan). Batas per layanan yang saya temukan: 1 replika, ±0,5 GB RAM, 1 vCPU, 1 GB penyimpanan sementara, 0,5 GB volume. Tabel docs untuk Trial menampilkan angka lain (1 GB RAM, 2 vCPU) **[BU]**.
- **Hobby:** $5/bulan, sudah termasuk $5 pemakaian; batas per layanan jauh lebih longgar (docs: hingga 48 GB RAM, 48 vCPU, volume 5 GB).
- Tarif pemakaian: RAM $10/GB/bulan · CPU $20/vCPU/bulan · volume $0,15/GB/bulan · egress $0,05/GB; **ditagih per menit**. Hard usage limit (minimum $10) tersedia di paket berlangganan.
- **Penilaian saya [A]:** (1) Odoo 19 + Postgres tidak muat nyaman di ±0,5 GB RAM; (2) kredit $1 ≈ 70 GB-jam RAM (hitungan kasar dari tarif, belum termasuk CPU), jadi hanya puluhan jam per bulan untuk Odoo + Postgres; (3) volume 0,5 GB sempit untuk 6 bulan data. **Free tier tidak cocok untuk demo yang berjalan terus-menerus.**
- **Opsi:** (i) **Hobby $5/bulan** dan layanan dinyalakan hanya saat demo/uji (ditagih per menit) + hard limit; (ii) pengembangan harian dan CI di luar Railway (docker compose lokal + GitHub Actions), Railway hanya untuk deploy demo; (iii) PWA statis di host statis lain supaya tidak memakai kredit; (iv) bila tetap Free: dataset kecil (±2 bulan, ±100 outlet) dengan jendela jalan terbatas.
- Host alternatif belum saya verifikasi.
- **Diputuskan (2026-10-23): Railway Hobby $5/bulan**, layanan dinyalakan hanya saat demo/uji, hard usage limit dipasang, deploy otomatis dari git dimatikan agar push tidak menyalakan layanan. Volume Hobby 5 GB mencukupi dump terkompresi; dump dibagikan sebagai **GitHub Release asset** (repo publik, batas ukuran file git) dan diunduh `init.sh` dengan verifikasi sha256. **[A]**

## 4C. Bahasa antarmuka dan istilah
- Bahasa default antarmuka **Indonesia** (`id_ID`), **English** tersedia.
- Odoo/OCA: string sumber di kode ditulis English (konvensi), terjemahan Indonesia di `i18n/id.po` tiap addon; PWA memakai berkas i18n `id`/`en` (default `id`).
- Istilah umum FMCG **dipertahankan** (tidak dipaksakan terjemahan): aturan dan daftar draf ada di `GLOSSARY.md`. Prinsip: bila padanan Indonesia tidak lazim di industri atau bisa membingungkan, pakai istilah aslinya; bila keduanya lazim, tampilkan istilah yang dipakai tim lapangan.
- Kualitas terjemahan Indonesia bawaan Odoo core belum diperiksa **[BU]**.

## 5. Peta modul
### 5.1 Core CE (verifikasi satu per satu di CE 19 saat provisioning **[BU]**)
**Terverifikasi ada di source CE 19 [F]:** `sale_management`, `sale_stock`, `purchase`, `stock`, `stock_account`, `stock_delivery`, `stock_picking_batch`, `product_expiry`, `account`, `analytic` (bagian `account`), `fleet`, `hr`, `hr_attendance`, `hr_holidays`, `hr_expense`, `l10n_id`, `l10n_id_efaktur_coretax`, `base_geolocalize`, `barcodes`, `board`, `spreadsheet_dashboard`. **Terinstal bersih di Odoo 19 [F, sandbox 2026-10-23]**; uji fungsional belum.

### 5.2 OCA 19.0 — modul **terinstal** di Odoo 19 pada 2026-10-23 **[F]** (terinstal ≠ fungsional; uji fungsional wajib)
| Kebutuhan | Modul | Repo |
|---|---|---|
| API untuk PWA | `fastapi` v19.0.1.1.1 (+ `endpoint_route_handler`). **Tidak installable di 19.0:** `base_rest`, `base_rest_auth_api_key`, `pydantic`, `rest_log` | rest-framework, web-api |
| Antrean async | `queue_job`. **Tidak installable:** `queue_job_batch`, `base_import_async` | queue |
| Limit & risiko kredit, penagihan | `sale_financial_risk`, `account_financial_risk`, `account_credit_control` | credit-control |
| FEFO/lot | `sale_order_lot_selection`, `stock_restrict_lot`, `stock_move_line_expiration_date_required`, `stock_no_negative`, `stock_picking_return_lot` | sale-workflow, stock-logistics-workflow |
| Batch picking & jendela kirim | `stock_picking_batch_extended`, `stock_picking_batch_group_by_date`, `stock_partner_delivery_window`, `stock_picking_backorder_policy` | stock-logistics-workflow |
| Approval order | `sale_order_approval_block`, `sale_exception` | sale-workflow |
| Satuan sekunder (karton/pcs) | `sale_order_secondary_unit`, `stock_secondary_unit` | sale-workflow, stock-logistics-warehouse |
| Laporan keuangan | `account_financial_report`, `partner_statement`, `account_tax_balance`, `mis_builder`, `mis_builder_budget`, `mis_builder_cash_flow` | account-financial-reporting, mis-builder |
| Dashboard/KPI/SQL view | `bi_sql_editor`, `kpi`, `report_xlsx` | reporting-engine |
| Impor mutasi bank (konfirmasi transfer) | `account_statement_import_sheet_file_xlsx`, `account_reconcile_oca` | bank-statement-import, account-reconcile |
| HR | `hr_employee_document`, `hr_employee_relative`, `hr_holidays_public`, `hr_attendance_reason` | hr, hr-holidays, hr-attendance |
| Payroll (mesin) | `payroll` (v19.0.1.0.2; depends `hr_holidays`, `mail`) | payroll |
| Kendaraan | `fleet_vehicle_inspection`, `fleet_vehicle_usage`, `fleet_vehicle_log_fuel` | fleet |
| Barcode | `product_multi_barcode` | stock-logistics-barcode |

### 5.3 Temuan penting dari verifikasi **[F, 2026-10-23]**
- `OCA/l10n-indonesia` 19.0: **kosong** (tanpa modul) → lokalisasi di luar `l10n_id` core = custom.
- `OCA/server-ux` 19.0: **tidak ada `base_tier_validation`** → matriks approval nominal × peran = custom `id_approval`.
- `OCA/sale-workflow` 19.0: **tidak ada triple discount** → diskon berlapis 1–5 kolom + footer + rules = custom `id_discount`.
- `OCA/payroll` 19.0: hanya mesin `payroll`, **tanpa posting jurnal & tanpa aturan Indonesia** → `id_payroll` (struktur gaji, PPh 21/BPJS berparameter, jurnal setelah approval owner).
- `OCA/wms` 19.0: **kosong**. `OCA/hr-attendance` 19.0: tanpa geotag/foto → keduanya custom di atas core.
- **`l10n_id_efaktur_coretax` ada di CE 19** (LGPL-3): menghasilkan XML faktur keluaran/retur, dokumen e-Faktur, kode produk & UoM, NITKU (`l10n_id_tku`), NIK, PKP, kode transaksi 07/08. Saya **tidak menemukan** pelacakan status Coretax (approved/ditolak), antrean kirim ulang, atau pemeriksaan kesiapan data → itu celah `id_coretax_prep`.
- **`l10n_id` CE:** file CSV memuat 114 akun; setelah dimuat DB berisi **118 akun** dan 18 pajak, termasuk 3 "12% (Non-Luxury Good)" bernilai 11% **[F, uji]**. Chart `id` **hanya** termuat bila negara perusahaan = ID *sebelum* modul akuntansi terinstal; kalau tidak, COA generik (US, pajak 15%) termuat. `init.sh` menjalankan urutan `base` → set ID/IDR → instal modul.
- **Dashboard:** `spreadsheet_dashboard` ada, `spreadsheet_edition` tidak → cara menyusun dashboard baru di CE **[BU]**; rencana: `id_dashboard` (view OWL/SQL + `bi_sql_editor`).
- Barcode: `stock_barcode` (Enterprise) tidak ada → pemindaian di WMS dasar memakai pemindai mode keyboard.
- **Modul OCA 19.0 yang ada di repo tetapi `installable: False` [F, uji]:** `base_rest`, `base_rest_auth_api_key`, `base_rest_pydantic`, `pydantic`, `extendable`, `rest_log`, `queue_job_batch`, `queue_job_cron*`, `queue_job_subscribe`, `base_import_async`. Di `rest-framework` hanya `fastapi` yang bisa dipasang, dan tidak ada modul otentikasinya (`fastapi_auth_*` tidak ada) → otentikasi token per pengguna dibuat sendiri di `id_api`.
- **Dependensi lintas repo [F, uji]:** `account_financial_report` butuh `date_range` (server-ux); `fastapi` butuh `endpoint_route_handler` (web-api); `sale_exception` butuh `base_exception` (server-tools); `auth_api_key` di server-auth. Closure 116 modul memerlukan **8 repo tambahan**: calendar, connector, product-attribute, server-auth, server-backend, server-tools, server-ux, web-api (kini di `oca.lock`, total 26).
- **Perbaikan setelah menjalankan `init.sh` [F, uji]:** (1) subperintah `shell` harus sebelum opsi; (2) `RESET_DB` memakai `DROP SCHEMA ... CASCADE` satu transaksi → `out of shared memory`, kini tabel dihapus satu per satu; (3) dump seed wajib `--exclude-schema=id_meta`. Detail: `docs/ODOO19_PITFALLS.md`, `docs/SANDBOX.md`.

### 5.4 Addon custom (prefix `id_`)
| Addon | Isi |
|---|---|
| `id_base` | Master tambahan: principal, area/wilayah (provinsi→desa), channel, tier, geotag, PIC (NPWP/NIK/PKP/NITKU memakai field `l10n_id` CE) |
| `id_coa` | Perluasan COA (118 akun chart `id` → lengkap untuk distributor): Money in Transit, Stock on Delivery, biaya §3.3, diskon & klaim principal, selisih van |
| `id_pricing` | Harga = principal × channel × area × tier × kuantitas/promo |
| `id_discount` | Line 1–5 kolom berantai, footer 1–2, config + rules, sumber dana, data klaim ke principal |
| `id_credit` | 4 mode kredit, eksposur (AR + SO pending + stock on delivery) per komponen, titik cek configurable |
| `id_approval` | Matriks nominal × peran, eskalasi SLA, delegasi, audit trail; 6 proses Playbook §3.2 |
| `id_distribusi` | PJP/rute kunjungan, canvassing (lokasi van, muat–jual–setor), Stock on Delivery, Money in Transit, closing harian |
| `id_integration` | Modul integrasi data (Playbook §5.2): impor, validasi, log, rekonsiliasi; **ekspor manual ke legacy DMS**; penanda `origin_system` dan kunci unik |
| `id_api` | Endpoint REST untuk PWA (auth token, idempotency key) |
| `id_app` | App role (`id_app.role`), konfigurasi tab per role, endpoint bootstrap, penegakan izin per role |
| `id_hris_ext` | Absensi geotag+foto, cuti & approval, SIM/dokumen kedaluwarsa + notifikasi |
| `id_payroll` | Lihat 5.3 |
| `id_coretax_prep` | Lihat §7 |
| `id_dashboard` | 6 dashboard monitoring |
| `id_demo_seed` | Mesin event deterministik + snapshot (skill `odoo-seed-and-verify`) |

## 6. Dimensi analitik (8, wajib terisi 100% pada baris bisnis) — Playbook §3.4
Produk (principal/brand/kategori) · Customer · Channel (MT/GT/Retail/Institusional) · Area · Departemen · Cost center · Salesman/tim · Kendaraan & gudang. Model penjualan (TO/Canvassing/Direct) disimpan sebagai atribut order, bukan dimensi. **[A]**

## 7. Modul persiapan Coretax (spesifikasi awal)
**Dasar:** `id_coretax_prep` **memperluas** `l10n_id_efaktur_coretax` CE (lihat §5.3), tidak membangun ulang. Di bawah ini yang ditambahkan.
Fakta **[F]**: Coretax memakai impor **XML** (menggantikan CSV e-Faktur desktop); DJP menyediakan template XML dan converter Excel→XML; validasi mencakup NPWP, kode objek pajak, tarif, dan penambahan **NITKU**. Template Excel faktur keluaran **v1.6** dengan converter **v1.5** (DDTCNews, 24 Sep 2025). Impor faktur keluaran dilaporkan beberapa kali bermasalah dan DJP meminta percobaan berkala.
**[BU]:** kapasitas unggah per file/menit saling bertentangan antar sumber (1.000 vs 15.000 faktur/unggahan; PJAP 21→50/menit) dan berubah cepat; versi template terbaru; kode transaksi/keterangan tambahan. Verifikasi ke pajak.go.id sebelum membekukan skema XML.
Fitur modul:
1. Kelengkapan data partner (NPWP/NIK, nama, alamat, NITKU) dengan tampilan "siap faktur".
2. Penyusunan data faktur keluaran dari invoice + PPN 12% DPP nilai lain 11/12 (efektif 11% non-mewah, lihat §8).
3. Ekspor XML per batch + log versi template.
4. Pelacakan status manual (dalam proses / approved / ditolak) dengan alasan penolakan dan antrean kirim ulang.
5. Mode secondary: opsi aktif/nonaktif; bila nonaktif, status diterima dari sistem sumber.
H2H/PJAP = fase berikutnya.

## 8. Pajak & sumber **[F, 2026-10-23]**
- PPN tarif UU 12% sejak 1 Jan 2025; BKP/JKP **non-mewah** memakai DPP nilai lain 11/12 sehingga efektif **11%** (PMK 131/2024; DDTCNews 17 Agu 2025: tidak berubah untuk 2026).
- DJP dilaporkan meninjau/merevisi sejumlah PMK DPP nilai lain **[BU]**; tanggal artikel tidak terbaca → cek JDIH/DJP sebelum `id_tax` dibekukan.
- **[BU]** bebas PPN barang strategis/pokok, perlakuan rokok & cukai, minyak goreng bersubsidi → kategori ini ditandai "contoh" pada demo.
- Pajak memakai konfigurasi `l10n_id` CE (12% dengan nilai 11% untuk non-mewah). Tarif/DPP kategori khusus = konfigurasi bertanggal, bukan konstanta kode.

## 9. Skenario demo (kerangka `SCENARIO.md`)
Urutan (v0.4): **(1) Secondary:** impor master dan transaksi dari legacy DMS (simulasi) → validasi gagal sengaja (SKU tak dikenal) → perbaikan & proses ulang → rekonsiliasi stok/AR. **(2) Aplikasi mobile:** login salesman (tab HRIS + Sales) → absen foto+geotag → check-in outlet → order offline lalu sinkron → server hitung ulang → approval diskon; login logistic (tab HRIS + Delivery). **(3) Odoo manual:** SO & invoice manual, blokir kredit & override approval. **(4) Fulfillment & WMS dasar:** batch picking FEFO → DO → delivery + foto + terima uang → closing & rekonsiliasi Money in Transit. **(5) Ekspor manual ke legacy DMS** + laporan selisih. **(6) Akuntansi & Coretax:** laporan, siapkan XML faktur. **(7) HRIS:** cuti, payslip, jurnal gaji. **(8) Dashboard** enam area. **(9) Peralihan ke primary:** feed legacy dihentikan, kontrol penuh untuk semua dokumen.
Plot data: lonjakan musiman (Natal/Tahun Baru, Ramadan/Lebaran, Pengucapan Syukur **[A]**), near-expiry & promo cuci gudang, outlet melewati limit, selisih stok van, faktur tertolak/pending, backorder principal, pengiriman tertunda ke kabupaten.

## 10. Invarian audit
Valuasi persediaan = GL persediaan · stok per lot ≥ 0 & FEFO (override tercatat) · saldo AR per outlet = Σ faktur terbuka = GL piutang · PPN keluaran = faktur siap-Coretax · Money in Transit nol setelah closing · Stock on Delivery nol setelah validasi pengiriman · diskon terpetakan ke akun & klaim principal · 8 dimensi analitik terisi · Σ slip gaji = jurnal gaji · hasil impor idempoten (kirim ulang tidak menggandakan) · rekonsiliasi stok/AR Odoo vs sumber = selisih terjelaskan.

## 11. Volume demo **[A]**
6 bulan data (dapat dikecilkan menurut §4B) · 4 principal · ±150 SKU (UoM pcs/renceng/karton) · ±400 outlet (4 channel) · 12 salesman · 6 kendaraan/driver · 1 gudang pusat + lokasi van · ±30 karyawan fiktif · ±1.500 order/bulan (turunkan bila RAM Railway ketat).

## 12. Urutan bangun (milestone, tiap milestone punya DoD)
M0 kerangka repo + CI + image + spike API/offline-sync · M1 base+COA+master+wilayah+i18n (id/en) · M2 seed engine + snapshot · M3 `id_integration` (secondary) · M4 O2C inti (pricing, diskon, kredit, approval) · M5 gudang/FEFO/delivery/MIT · M6 `id_api` + `id_app` + PWA (shell, tab dinamis, Sales/Delivery) · M7 HRIS + payroll dasar + PWA HRIS · M8 dashboard · M9 Coretax prep · M10 mode primary + polish + deploy Railway.

## 13. Butir terbuka
**Terjawab:** hybrid · mobile selalu sinkron ke Odoo, legacy via ekspor manual · PWA Preact + Vite, native Android setelah proyek disetujui · satu aplikasi, tab dinamis menurut app role **bertumpuk** · tanpa gudang transit · UI Indonesia penuh + English, istilah FMCG dipertahankan · Railway **Hobby $5** start-stop · Playbook v0.4.

**Masih terbuka:**
1. **Kontrol dokumen asal Odoo/mobile pada mode secondary** (Playbook §10 #18): kredit dan approval penuh, atau sebagian? *(tidak menghalangi M0–M3)*
2. **Ekspor ke legacy DMS:** cukup template generik XLSX/CSV pada demo?
3. Tinjau `GLOSSARY.md` (istilah dipertahankan vs diterjemahkan).
4. Konfirmasi lisensi LGPL-3 untuk addon `id_*`, dan siapa pemegang hak cipta pada header (nama Anda/organisasi).
