# Dashboard FMCG — arsitektur dan acceptance plan

Status: desain/roadmap implementasi bertahap; bukan klaim dashboard sudah tersedia.

## Urutan implementasi
1. **Native Odoo dashboard enhancement** — kurasi menu/action, list, search filters, group-by, graph/pivot dan laporan Sales, Inventory, Purchase, Accounting, HR, Fleet. Tambahkan saved filters serta exception lists yang actionable; jangan menggandakan fungsi native yang sudah memadai.
2. **Custom `id_dashboard`** — bangun hanya kebutuhan lintas-modul atau workflow keputusan yang tidak layak dipenuhi native.
3. **`spreadsheet_dashboard`** — evaluasi terakhir, setelah instalasi bersih CE, dependensi, editing/sharing, ACL, refresh/filter/drill-down dan upgrade diuji. Jangan mengasumsikan fitur Enterprise atau `spreadsheet_edition`.

## Prinsip data
- Dashboard hanya menyajikan transaksi resmi Odoo sebagai angka operasional/finansial. Draft offline, simulator PWA, collection belum diverifikasi dan sesi delivery bukan posting/AR/kas/DO resmi.
- Setiap KPI mempunyai definisi, sumber model/field, formula, timezone/cut-off, domain, aturan agregasi, role, dan drill-down.
- Uang mengikuti company currency/tax config; kuantitas dinormalisasi ke UoM. Hindari agregasi one-to-many yang menggandakan nilai, N+1 query dan pelanggaran record rules.
- Data legacy dibedakan via `origin_system`; rekonsiliasi harus menjelaskan selisih.
- Owner-only margin/derived COGS dilindungi server-side, bukan hanya disembunyikan dengan CSS.

## Dashboard yang direncanakan

| Dashboard | KPI/pertanyaan awal | Sumber otoritatif yang dituju |
|---|---|---|
| Owner Control Tower | omzet/DPP, gross profit, margin, AR overdue, kas/AP jatuh tempo, risiko stok/expiry, approval dan rekonsiliasi exceptions | SO/invoice resmi, posted payment/reconciliation, stock valuation/moves, approval yang sudah diposting |
| Sales & Principal | omzet, margin, target, active outlet, coverage, tren order, diskon/sumber dana/approval | SO/invoice tervalidasi, master principal/channel/area, visit/PJP jika tersedia |
| Inventory & Warehouse | stock on hand, aging, lot/expiry, FEFO exceptions, picking backlog, replenishment risk | stock quant/moves, lot/expiry, receipts, picking states |
| Finance, AR & Collection | AR aging, due/overdue, collection tervalidasi, invoice pending/dispute, AP schedule, rekonsiliasi | posted invoice/payment dan reconciled receivable/payable lines |
| Logistics & Delivery | DO backlog, delivery/partial/rejected, vehicle utilization, cost/drop, Money in Transit/Stock on Delivery | validated picking/delivery, fleet/cost dan posted collection records |
| Sales Force & HR | PJP planned/completed, order/visit, productive outlets, attendance, productivity by role | approved visit/order/attendance records dengan ACL/privasi sesuai |

Sell-out, numeric distribution, vehicle cube utilization, fuel cost/km, target principal, Money in Transit dan Stock on Delivery hanya ditampilkan bila model/sumbernya benar-benar tersedia. Jika belum, tampilkan “belum tersedia”, bukan angka placeholder.

## Pola layout
- Filter konteks/periode yang relevan dan tombol reset.
- 4–6 KPI cards dengan nilai, pembanding periode dan tren hanya bila data mendukung.
- Tren dan breakdown/ranking.
- Daftar exception/action queue.
- Drill-down dari KPI ke record sumber.
- Dashboard operasional mendahulukan exception; dashboard eksekutif mendahulukan tren, margin dan risiko.

## Definition of Done
- Uji role/company/record rules termasuk user tanpa akses margin.
- Uji periode kosong, data kosong, filter gabungan, UoM, mata uang, query count/performance dan dataset besar.
- Tidak ada angka bisnis hardcoded atau fixture demo yang menyamar sebagai live metrics.
- Diuji pada Odoo 19 CE aktual; dependensi Enterprise tidak diasumsikan.
- Urutan tetap: native enhancement → custom dashboard → spreadsheet_dashboard.

## Riwayat keputusan dan alasan urutan

Keputusan ini dikonfirmasi pemilik pada percakapan 2026-10-29 setelah permintaan memeriksa backlog aktual dan mengeksplorasi dashboard default Odoo, dashboard FMCG berdasarkan business playbook/brainstorming, serta enhancement UI. Urutan eksplisit yang disetujui:

1. **Footer/form UI dan baseline audit** — masalah yang sudah terlihat di alur transaksi didahulukan; footer tiga kolom mengikuti `notes | footer discount 1 + 2 | subtotal/DPP/tax/grand total`. Diskon tidak boleh dibuat hanya sebagai tampilan tanpa field/model dan aturan kalkulasi sah.
2. **Native Odoo dashboard enhancement** — maksimalkan menu/action, list, search, graph, pivot dan report bawaan sebelum membuat permukaan baru.
3. **Custom dashboard FMCG** — tambahkan nilai lintas-modul yang tidak tersedia secara memadai di native; Owner Control Tower menjadi kandidat awal, setelah sumber KPI dan ACL terverifikasi.
4. **Spreadsheet dashboard** — prioritas terakhir, hanya setelah kompatibilitas Odoo 19 CE dan manfaat nyata dibuktikan.

Alasan: menghindari duplikasi fungsi native, mengurangi risiko menghitung KPI dari data tidak resmi, dan memastikan implementasi UI transaksi yang sudah menjadi keluhan ditangani sebelum dashboard baru. Pemilik juga mengubah keputusan ikon sidebar sebelumnya: ikon full-color baik pada kondisi default maupun selected; state selected dibedakan oleh background saja.

