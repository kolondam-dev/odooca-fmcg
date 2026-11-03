# Tahap 3B — subledger historis, cohort pengiriman, margin order

Basis main `69149f6` sesudah PR75. Implementasi read-only; tidak menyentuh workflow PWA, posting, seed/register, server atau deployment. Versi tiga addon dashboard menjadi 19.0.1.4.0. Owner metrik: Finance (AR/margin) dan Warehouse/Logistics (service pengiriman). Threshold tindakan otomatis tidak ditambahkan.

## Piutang historis

Grain adalah AML receivable terposting, termasuk termin, jurnal manual, credit note dan penerimaan belum dialokasikan; currency company, bukan mata uang transaksi. Untuk tanggal akuntansi D: balance − partial.debit amount + partial.credit amount, hanya partial.max_date ≤ D. Jurnal sesudah D tidak masuk. Kredit negatif disajikan terpisah dari debit aging. Null maturity dikelompokkan not due dan count kualitasnya terlihat. Snapshot tanpa data = nol; peran invoice-only = unavailable tanpa payload ledger.

Filter company/area/salesperson berlaku native ORM/ACL, tanpa sudo. Area dan fallback PIC mengikuti master saat query, bukan atribusi historis immutable. Current invoice KPI tidak diganti atau diberi tanggal historis palsu. Periode target finance berbeda dari tanggal snapshot. Mata uang campuran ditolak.

Migrasi memakai pos jurnal yang sama pada dua cutoff: bucket awal → bucket akhir, opening/closing signed serta jumlah pos; new dan settled dipisahkan. Jumlah opening/closing cell harus merekonsiliasi total snapshot. Movement bukan klaim cash collection (dapat mencakup credit, write-off, FX).

Batas rekonstruksi: memakai *current posted documents dan current reconciliation links*, bukan audit sistem "apa yang diketahui saat itu". Unreconcile/deletion/backdating/reclassification dapat mengubah hasil historis. Tidak membuat snapshot immutable atau promise-to-pay fiktif. Source drill-down memperlihatkan jurnal saat ini, bukan residual historis tersimpan. Maksimum 50k AML/200k partial, ditolak eksplisit bila terlampaui.

## Cohort pengiriman

Anchor = current scheduled timestamp pada root outgoing customer DO non-draft; kalender hari WITA. Pilihan tanggal default bulan berjalan sampai hari ini. Fleet filter memakai root DO, kategori stok tidak memotong DO. Backorder chain ditelusuri dan denominator tetap satu root. Demand = jumlah planned quantity pada chain dalam UoM produk; done actual quantity dibanding per produk, bukan jumlah DO berstatus done. Ini rekonstruksi demand terkini, bukan frozen original demand; perubahan/pembatalan administratif setelah kejadian memerlukan audit event terpisah.

OTIF = root yang seluruh demand-nya selesai on/before jadwal, chain tertutup tanpa cancellation / root yang scheduled timestamp-nya telah berlalu. H+1/H+2 = chain penuh tanpa cancellation selesai sampai akhir hari jadwal+1/+2 / cohort yang hari batasnya sudah berlalu penuh. Bukan H+1 sejak SO diterima atau kalender hari kerja. Pending/cancel tetap denominator, unknown demand tidak menjadi sukses. Closed partial adalah kegagalan; backlog berarti chain masih terbuka. Cancel rate = root dengan setidaknya satu child/root cancel / seluruh root. Tolakan = distinct root per alasan DO; multi-reason tidak dijumlahkan menjadi cancelled total.

Completion offset median/p90 memakai jam relatif ke scheduled timestamp (negatif berarti lebih awal), hanya chain penuh tertutup; backlog count dan p90 age tetap terlihat agar kasus belum selesai tidak hilang. Native picking/move sumber dapat dibuka; 50k chain cap, bukan silent partial aggregate. Event first-attempt, POD reasons per line, approved reschedule dan promised-date history belum memiliki bridge pada panel ini; tidak disamakan dengan empat alasan legacy DO.

## Margin order yang dapat ditelusuri

Cohort confirmed SO tanggal order mengikuti filter Sales/WITA. Native posted invoice income AML (company balance signed) versus **singular stock.move.account_move_id** posted expense_direct_cost; tanpa standard_price/SVL/pro-rata fallback. Hanya order stock dengan quantity ordered=delivered=posted-invoiced, baris positif tanpa downpayment/service/refund/return dan tanpa shared valuation journal lintas order yang masuk total. Currency sudah company currency pada ledger, bukan konversi ulang SO. Margin ini gross margin sumber terpilih, belum cost-to-serve/net margin; biaya DO/outlet/trip/maintenance tetap tahap4.

Coverage wajib: covered/all orders, alasan unavailable per order, source invoice dan journal IDs. Hilang COGS tidak menjadi cost0/margin100%. Peran Sales tanpa accounting tidak menerima biaya atau source IDs. Maksimum 5k SO; tabel100 baris pertama dilabeli, total dihitung seluruh cohort eligible. Partial order, layanan, return/refund dan generic native invoice-only COGS tanpa delivery link belum dialokasikan: sengaja unavailable sampai bridge lebih luas dapat direkonsiliasi. Tidak mengubah cost/posting hook canonical.

## Verifikasi dan batas penerimaan

Regresi native ditambahkan: installment, unallocated credit, current full reconciliation dengan cutoff terdahulu, migration reconciliation; root/backorder, cancel, backlog, mature denominator dan OTIF; invoice+posted delivery cost versus missing link, no-cost role. Tes JS: date payload/stale response dan drill-down server scope. Screenshot native mencakup panel baru pada1440/1024/768. Fixture/test state eksplisit merupakan pengujian read-model, bukan acceptance end-to-end posting gudang.

[F] Lokal: Ruff/manifests/compile/XML/Node/diff dijalankan. [BU] Odoo lokal tidak tersedia: setup Postgres gagal pada sandbox setgroups/seteuid. Native Odoo, upgrade database persisten dan visual nyata harus dibuktikan CI HEAD final. Tidak menyatakan hasil CI atau deployment sebelum bukti tersedia.

Sisa roadmap tetap dipertahankan: promise-to-pay, immutable snapshots/audit, collection settlement, weighted/outlet-eligible distribution, first-attempt/POD bridge, generic partial/refund cost attribution, stock valuation/slow stock/retur/expiry enrichment, asset capacity/occupancy/mileage/cost allocation, warehouse detail dan Three.js. Panel3B ini bukan klaim seluruh program enhancement selesai.
