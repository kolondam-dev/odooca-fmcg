# Tahap 4 — utilisasi aset dan biaya tercatat

Basis main ca8b49c / PR80. Implementasi tidak membuat trip historis dari DO, tidak mengubah seed atau server dan tidak mengaktifkan Three.js. Warehouse detail/bin/rack/layout tetap tahap5–6. Backlog3B (audit AR immutable/promise-to-pay, partial/refund COGS, POD event bridge) tetap terpisah.

## Sumber dan scope

- Stock saat query: positive stock.quant di internal descendant warehouse.lot_stock_id; reserved tidak ditambah lagi, consigned tetap memakai ruang. Receiving/output di luar root stock tidak masuk. Quant negatif adalah exception, tidak mengurangi okupansi. Root gudang overlap ditolak.
- Kubikasi = qty dalam stock UoM produk / carton_qty × panjang×lebar×tinggi cm /1e6; berat = qty/carton_qty × carton_weight_kg. Memakai dimensi mentah, tidak menghilangkan kemasan kecil karena pembulatan volume master. Kemasan parsial dihitung ekuivalen proporsional, bukan bukti geometri stacking.
- Master stock.warehouse.usable_volume_cbm dan capacity_basis wajib merupakan kapasitas usable storage root yang sama; tidak otomatis panjang×lebar×tinggi gedung. Kosong/0=unknown, bukan gudang tanpa kapasitas. Existing warehouse/DO tidak diisi nilai perkiraan.
- Warehouse ratio unavailable bila volume/kapasitas/negative quant tidak lengkap; known volume/weight tetap lower bound dan exception count terlihat. Kapasitas harus finite nonnegative dan bernotasi sumber bila positif. Tidak ada klaim floor-load/rack capacity.

## Trip operasional baru

Model id.asset.trip mempunyai native list/form, company rule global; stock user read-only, stock manager/system mengelola. Draft menetapkan vehicle, DO yang siap dan odometer awal km. Record Departure memerlukan DO outgoing/customer/assigned yang cocok company+vehicle, actual picked quantity positif. DO tidak dapat masuk dua trip departed; guard write conflict PostgreSQL RR melindungi persaingan departure. Penguncian SQL adalah no-op audit field, tidak mengubah status/kuantitas DO.

Departure membekukan line move/product/picking/stock-UoM quantity, volume/weight (atau null), kapasitas cbm/kg dari vehicle dan actor/time. Perubahan master kemudian tidak menulis ulang histori. API create/write/context tidak boleh menyuntik fakta departure/closed; departed trip tidak dapat dihapus. Return/close mengharuskan setiap DO selesai/cancel, odometer akhir >=awal dan sumber biaya (termasuk biaya0). Closed record immutable; koreksi bukan pengeditan diam-diam. Tidak membuat clock-in atau validasi geofence/PWA baru.

Readings adalah input operator dalam km, bukan GPS mileage atau native odometer series yang diinferensikan. Kendaraan bersatuan mile harus dikonversi oleh operator ke km sebelum input. Jarak0 sah tetapi cost/km unavailable. Trip multi-stop dihitung departure load/capacity, bukan cbm-km atau average load per leg. Overload >100% terlihat, tidak dipotong menjadi100% dan tidak otomatis memblokir operasi.

## Agregasi dan biaya

Filter tanggal WMS/cohort memakai departure WITA (end inclusive); vehicle filter berlaku, kategori stock tidak. Fleet period utilization = summed eligible frozen volume / summed frozen capacity dan berat/kg secara independen; hanya trip dengan semua dimensi dan kapasitas valid yang masuk tiap denominator. Coverage eligible/all selalu terlihat. Tidak merata-ratakan persentase trip. Tabel100 row pertama dilabeli; total full selected cohort. Maksimum50k trip/stock positions per gudang, fail explicit bila terlampaui.

Biaya langsung = order processing+fuel+helper+other direct delivery expense yang dicatat pada trip baru dan referensi receipt/source. Maintenance tidak boleh diinput kembali sebagai other delivery cost. Maintenance memakai native fleet.vehicle.log.services state done, termasuk archived, pada tanggal biaya periode dan scope company/vehicle. Nilai ini biaya **tercatat**, bukan rekonsiliasi GL atau bank. Stock-role tanpa akses native service mendapat unavailable, bukan0. Tidak ada alokasi maintenance ganda ke masing-masing trip. Legacy id.delivery.trip.cost tetap di laporan lama, tidak dijumlahkan lagi ke trip baru; pembukuan yang sama tidak boleh dimasukkan sebagai dua sumber trip baru.

Cost/km memakai direct cost closed trip cohort + native completed maintenance periode / total recorded closed trip km. Hanya tersedia bila semua trip pada cohort ditutup dan sumber service readable; ini efisiensi sumber tercatat, bukan bukti semua perjalanan/biaya armada telah lengkap. Cost/delivered DPP memerlukan source sale_line, positive ordered qty dan company currency sama untuk seluruh done delivery move; foreign currency atau missing linkage unavailable, tanpa relabeling/fallback cost. DPP adalah physical gross delivery value saat closure (snapshot), bukan invoice revenue, net return, actual margin, GL matching atau alokasi invoice biaya. Calendar maintenance cost dan departure cohort adalah scope yang ditampilkan, bukan causal per-trip maintenance allocation.

## Audit data dan penerimaan

Panel baru di WMS memuat source quant drill-down, configuration capacity, trip list/form, snapshot ratios, source completeness, costs dan km. Belum ada klaim master runtime lengkap; kapasitas usable dan trip departure baru memang memerlukan input operator resmi. Tidak mengubah data instance yang ada.

Native regressions: physical unit math, snapshot master mutation, closure/missing SO linkage, duplicate departure/context spoof/readonly facts, capacity unknown/negative validation dan company/role. JS regressions: tiny-volume/currency precision, scoped/stale drilldown. CI fixture memakai usable capacity sintetis dalam ci_db, memeriksa warehouse volume/no-invented-trips sebelum membuat satu event keberangkatan QA baru, lalu menguji cost/km dan delivery DPP sebelum screenshot. Native read-model fixtures bukan acceptance operasi gudang end-to-end. Lokal Ruff/manifests/XML/compile/18Node/diff dijalankan; Odoo lokal tidak tersedia karena setup Postgres sandbox setgroups/seteuid. Native CI, upgrade/replay dan visual exact HEAD harus dibuktikan sebelum PASS.

Lanjutan kualitas operasional: immutable correction/reversal ledger untuk trip, kontrak fixed/per-leg load, actual service allocations/reconciled expense receipts dan benchmark skala representatif. Warehouse bin/rack/pallet, load-bearing, layout coordinates dan Three.js tetap mengikuti readiness gate roadmap.
