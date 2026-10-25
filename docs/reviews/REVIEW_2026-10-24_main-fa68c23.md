# Review codebase `main` @ fa68c23 (PR #1–#5)

Penulis: claude-dev agent · 2026-10-24 · Basis: `origin/main` fa68c23 · Diuji di sandbox (Odoo 19 `f4378f29`, Postgres 16) dengan **boot persis seperti Railway** (`INIT_MODULES=id_base,id_ui,id_ui_shell,id_ui_form,l10n_id`, DB kosong): 97 modul, 150 produk, 354 outlet, 0 galat JS (Playwright). Skrip: `scripts/ops/odoo_snapshot.py`.
**Catatan basis:** setelah review ditulis, `origin/main` maju ke `b8bcbf9` (PR #6 dan #7: UI v2/v3, hanya `id_ui_shell`, `docs/ui`, `agent-log/claude-design.log`). Kedua PR **tidak mengubah** temuan A–C maupun D1–D3; `claude-design` mencatat sendiri bahwa halaman Dashboards kini punya dua panel kiri (terkait D2).
Legenda: **P0** salah/menyesatkan sekarang · **P1** kurang dari yang dijanjikan · **P2** kualitas. Bukti = angka dari snapshot atau berkas yang disebut.

## 1. Yang sudah baik (pertahankan)
- Arsitektur data benar: outlet = `res.partner`, SKU = `product.template` (diperluas), tabel referensi `id.*` terpisah; ACL rapi (baca untuk user, tulis hanya `group_system`).
- Generator **deterministik** (identik lintas `PYTHONHASHSEED` 0/5; hasil sama dengan berkas commit kecuali akhir baris CR).
- Total **di level header** simulasi tepat sasaran: Juli 5.500, Agustus 4.235, September 3.960, Oktober 5.300 juta (kolom `final_billed_amount`).
- CI hijau di ketiga PR **menurut log AntiGravity**, termasuk `init-test` (build + restart idempoten) pada GitHub Actions; saya belum melihat run-nya sendiri **[BU]**. Disiplin log/HANDOFF/tanda tangan commit dipatuhi.
- Tidak ada rahasia di HEAD maupun riwayat. Kode BPS 15 kab/kota sesuai pengetahuan saya (7171–7174, 7101–7111; belum dicek ke sumber resmi **[BU]**). Sidebar `id_ui_shell`: 0 galat JS.

## 2. Temuan

### A. Pemuat seed master (`scripts/load_fmcg_seed.py`)
| # | Sev | Temuan | Bukti |
|---|---|---|---|
| A1 | P0 | `tier_id` kosong di **semua** outlet. XML memakai `TIER-GOLD`, CSV memakai `GOLD`; pemetaan tak cocok dan kegagalannya diam. | tier 0/354 |
| A2 | P0 | Alamat tak lengkap: kota, provinsi, negara kosong; kode pos tampil di kolom State. | city/state/country 0/354 |
| A3 | P0 | `payment_term_days` (TOP) dan `salesman_code` ada di CSV tetapi tidak dibaca. | `property_payment_term_id` 0, `user_id` 0 |
| A4 | P0 | Produk **tidak storable**: `type=consu`, `is_storable` tidak diset; tanpa tracking lot/expiry. Inventory tidak melacak stok; FEFO mustahil. | `is_storable` 0/150 |
| A5 | P0 | UoM tunggal "Units". `base_uom` (Pcs/Sachet/Botol) dan `purchase_uom` (Karton) diabaikan; `inner_qty`/`carton_qty` hanya angka. Odoo 19 punya model kemasan `product.uom` (0 baris). Penjualan per karton tidak mungkin. | uom: Units 150; `product.uom` 0 |
| A6 | P1 | Tidak dimuat sama sekali: karyawan (24), armada (9), gudang/lokasi, daftar harga, sub-brand, partner vendor untuk principal, `categ_id` produk. | hr.employee 1, fleet.vehicle 0, pricelist 0, sub_brand 0, categ_id 0/150 |
| A7 | P1 | `volume_cbm` 0,0001–0,0015 m³ terpangkas presisi field → 0. | volume 0/150 |
| A8 | P0 | Filter `if k in Model._fields` membuang field **diam-diam** (mis. geotag bila `base_geolocalize` tak terpasang). Kegagalan tertelan, bukan terlihat. | kode loader |

### B. Simulasi historis
| # | Sev | Temuan | Bukti |
|---|---|---|---|
| B1 | P0 | **Data tidak konsisten di level baris:** semua 8.513 baris melanggar `subtotal = qty × harga` (rasio median 32,5×); jumlah baris ≠ header di 3.762/3.762 SO (Juli: baris 5.279 vs gross 5.834 juta). | analisis CSV |
| B2 | P0 | Loader (`load_historical_simulation.py`): hanya **500 SO pertama**; `except: pass`; kuantitas karton diperlakukan sebagai Unit dan nilai baris = qty×harga (total qty×harga **seluruh** baris Juli hanya ±168 juta, bukan 5.834 juta; sebelum pembatasan 500 SO); tanpa pengiriman/faktur/pembayaran; lot hanya di teks deskripsi; tidak dipanggil `init.sh`. | kode + analisis |
| B3 | P1 | Belum ada audit, `id_verify`, snapshot, waktu simulasi (freezegun) seperti skill `odoo-seed-and-verify`; invarian `SCOPE §10` tak terukur. | tidak ada berkas |
| B4 | P2 | Dokumen tak konsisten: 354 vs 403 outlet (PJP); "8 pilar" berisi 9 butir. | blueprint |

### C. `deploy/init.sh`
| # | Sev | Temuan |
|---|---|---|
| C1 | P0 | `\|\| log "warning"` lalu `set_mark seed_master_v2`: **seed gagal tetap ditandai sukses** dan tidak pernah diulang. |
| C2 | P0 | Upgrade modul memakai mark sekali pakai (`upgrade_modules_v1`). Perubahan model berikutnya menghasilkan lagi HTTP 500 `UndefinedColumn`. Usulan: mark berbasis **hash isi** `addons/` dan `data/seed/` yang dihitung saat build image (`upgrade_<hash>`, `seed_<hash>`); gagal = tidak di-mark. |
| C3 | P1 | Seed berjalan **sinkron di entrypoint** (bukan latar belakang): HTTP baru siap ±207 detik pada DB kosong (sandbox 1 CPU). Risiko health check/restart. Jangka menengah: restore dump Release asset. |
| C4 | P2 | `base_vat` memanggil IAP VIES untuk tiap partner ber-NPWP → galat log dan latensi (VIES tidak berlaku untuk NPWP). |

### D. UI, menu, bahasa
| # | Sev | Temuan |
|---|---|---|
| D1 | P0 | "FMCG Distribution" adalah **aplikasi tingkat atas** (`application: True`) berisi 9 tabel referensi. Seharusnya berada di **Configuration** aplikasi standar (xmlid terverifikasi: `contacts.res_partner_menu_config`, `sale.menu_sale_config`, `stock.menu_stock_config_settings`, `fleet.fleet_configuration`). |
| D2 | P0 | Kartu **Dashboards** menampilkan data contoh bawaan (`$491.617`, 456 order, dolar) padahal DB punya 0 order: menyesatkan untuk demo. |
| D3 | P0 | **Bahasa:** hook hanya mengatur bahasa bawaan untuk partner/user **baru** (`ir.default`); `admin` tetap `en_US`, `tz` kosong, perusahaan "My Company". `id_base` tanpa `id.po`: dengan `id_ID` aktif, menu inti Indonesia tetapi tab/label FMCG tetap English (terbukti di tangkapan layar). |
| D4 | P1 | Daftar Contacts tanpa kolom/filter/group-by FMCG (channel, tier, kecamatan, mode kredit). |
| D5 | P1 | Belum terinstal vs rencana: `product_expiry`, `stock_picking_batch`, `mis_builder`, `account_financial_report`, `queue_job`, `fastapi`, `sale_financial_risk`, `account_credit_control`. |
| D6 | P2 | Banyak modul bawaan ikut terpasang tanpa relevansi demo (Gmail/Outlook, SMS, snailmail, passkey, `partner_autocomplete`, `hr_skills`). |

### E. Data dan kepatuhan
- **E1 (P1)** Data berlabel "fiktif" memuat nama perusahaan/merek nyata (principal Mayora/Unilever/Wings/Santos; outlet Indomaret, Alfamidi, Sheraton, RSUP Kandou) dengan limit kredit dan omset rekaan di **repo publik**. Rekomendasi: anonimisasi, atau disclaimer jelas dan tidak menampilkan entitas nyata sebagai penunggak.
- **E2 (P1)** `EMP-001` bernama "Bpk. Teddy Kolondam" tampak nama pemilik repo. Konfirmasi atau ganti fiktif.
- **E3 (P2)** Wilayah: 18 kecamatan dan 14 kelurahan termuat (blueprint menyebut cakupan penuh). Perlu sumber resmi (Playbook §10 #15); kode pos belum diverifikasi **[BU]**.

## 3. Langkah berikutnya (usulan; urutan = prioritas)
**M1a — Perbaikan master data** (pemilik area: `claude-dev`; uji di sandbox sebelum patch):
1. Perbaiki A1–A5, A8: loader **gagal keras** pada kode tak dikenal (tanpa filter diam-diam), pemetaan tier, kota/provinsi/negara, TOP (`account.payment.term`), salesman (user/karyawan), `is_storable` + tracking lot + `product_expiry`, kemasan `uom.uom` + `product.uom`.
2. Muat karyawan, armada (`fleet.vehicle`), gudang+lokasi, daftar harga, partner vendor principal, kategori produk (A6, A7).
3. Tes: `id_base` menguji hasil seed (jumlah, field wajib, nol tier kosong) di CI.
**M1b — Init yang tahan perubahan** (pemilik: `antigravity`): C1–C4 (mark berbasis hash, gagal = tidak di-mark, VIES nonaktif); admin `lang=id_ID`, `tz=Asia/Makassar`, nama perusahaan (D3).
**M1c — Menu dan bahasa** (pemilik: `claude-design` + `claude-dev`): D1 pindahkan tabel referensi ke Configuration, hapus tile aplikasi; D2 sembunyikan dashboard contoh sampai ada data; D3 `id.po` untuk `id_base`; D4 kolom/filter/group-by.
**M2 — Simulasi dan verifikasi** (pemilik: `claude-dev`, skill `odoo-seed-and-verify`): perbaiki B1 di generator (baris dan header harus saling cocok), planner + eksekutor ORM penuh (pengiriman, faktur, pembayaran, lot/expiry) dengan waktu simulasi, `audit.py`, `id_verify`, snapshot referensi.
**Keputusan pemilik yang dibutuhkan:** (a) anonimisasi nama nyata (E1); (b) E2; (c) pendekatan kemasan: `product.uom` Odoo 19 (disarankan) vs bidang kustom; (d) urutan M1a/M1b/M1c.

## 4. Cara memverifikasi perbaikan
`python3 scripts/ops/odoo_snapshot.py --url <URL> --db <DB> --user admin` (prompt sandi). Kriteria selesai M1a: tier/city/state/country/TOP/salesman terisi 354/354; `is_storable` 150/150; karyawan 24; kendaraan 9; gudang bernama; `product.uom` terisi; log `[seed_loader]` tanpa peringatan.
