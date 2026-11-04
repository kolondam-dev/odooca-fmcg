# Tahap 5 — Detail gudang

Cakupan: detail penyimpanan fisik terkini, arus pergerakan aktual, pencatatan waktu operasi oleh server, serta kontrol persediaan terhadap buku besar. PR ini dibangun di atas penyelesaian backlog3B; bukan deployment atau implementasi Three.js tahap6.

## Sumber dan keputusan

| Keputusan | Sumber resmi / definisi | Batas dan tindak lanjut |
| --- | --- | --- |
| Zona/rack/bin/posisi pallet | Perluasan `stock.location` native; hierarki dan keanggotaan warehouse tetap native | Tidak membuat ledger persediaan bin paralel. Isi kapasitas usable beserta sumber ukur, bukan volume gedung bruto. |
| Okupansi pallet | Hierarki fisik `stock.package.parent_package_id`; pallet terluar yang diklasifikasikan eksplisit dan berada pada satu lokasi | `outermost_package_id` tujuan perpindahan tidak dipakai. Pallet tanpa klasifikasi atau tersebar di beberapa lokasi membuat rasio slot tidak lengkap. |
| Batas kapasitas | Usable m³/slot eksplisit pada lokasi; batas berat storage category native dikonversi ke kg; satu aturan kapasitas jenis pallet yang tidak ambigu | Aturan alternatif jenis pallet tidak dijumlahkan. Volume ekuivalen karton bukan bukti susunan aktual atau keselamatan beban. Baris induk mencakup anak, sehingga tidak boleh dijumlahkan lagi. |
| Kesiapan layout | Kerangka koordinat lokal terverifikasi, dimensi meter, sumber dan company; anak terverifikasi harus berada dalam envelope induk terverifikasi | Menyiapkan data spasial aktual tanpa membuat posisi gudang/rack/bin/armada fiktif. Beberapa kerangka koordinat terverifikasi pada satu gudang ditandai sebagai konflik. |
| Kesehatan stok | Quant native per SKU/gudang: fisik, reservasi, tersedia; expiry lot dan tanggal wajib yang kosong | `quant.in_date` adalah proksi umur posisi, bukan waktu penerimaan lot pertama. Median/p90 tidak dibobot kuantitas. Posisi negatif tetap menjadi exception. |
| Slow / inactive | Umur posisi positif tertua dan outbound pelanggan done terakhir yang teramati; kebijakan warehouse default90/180 hari | Inactive berarti tidak ada outbound dalam jendela pengamatan, bukan tidak pernah terjual. Horizon ditampilkan. Tidak mengarang denominator stock cover. |
| Throughput | `stock.move.line` done berkuantitas positif, tanggal WITA, periode terpilih; received/shipped/putaway/picking/other | Setiap baris dihitung sekali. Bukan jumlah order, produktivitas per jam kerja atau penjumlahan satuan SKU berbeda. Grafik harian dan drill-down sumber tersedia. |
| Picking/putaway/receiving dwell | Action pencatatan pada operasi native ready; server merekam mulai/akhir/pelaku/company. Penyelesaian membutuhkan operasi done | Waktu berlalu termasuk menunggu dan jeda klik. Operasi historis tidak diberi waktu mulai fiktif. Receiving bertahap membutuhkan rantai penerimaan/putaway aktif selesai dan mencapai storage. Median/p90 hanya event selesai dalam periode; running terkini dan cancelled periode dipisahkan. |
| Kontrol valuasi | Native Odoo19 `product.total_value`; pemetaan company `_get_accounts_by_product` dan saldo posted `stock_accounting_value` | Snapshot terkini company-wide, hanya peran akuntansi. Filter warehouse/kategori/periode tidak berlaku. Pemetaan kosong unavailable. Selisih perlu rekonsiliasi, bukan otomatis kerugian atau jurnal koreksi. Estimasi standard-cost lama tetap mempunyai scope terpisah. |

## Cakupan, kendali dan operasi

Pemilih gudang hanya memengaruhi bagian detail baru ini. Kategori berlaku pada kesehatan SKU/pergerakan, tidak pada okupansi lokasi atau waktu operasi. Armada tidak berlaku. Input tanggal cohort existing menentukan periode pergerakan dan waktu operasi selesai; stok/kapasitas/layout tetap terkini. ACL, company rule dan akses sumber native tetap dipakai, tanpa sudo read atau pemaparan payload evidence privat.

Stock manager memelihara atribut fisik lokasi, klasifikasi pallet dan kebijakan pengamatan. Operator membuat/memulai pencatatannya; hanya pekerja yang memulai atau stock manager yang menyelesaikan/membatalkan. Fakta event, identitas setelah mulai, dan record selesai/batal tidak dapat ditulis ulang/dihapus melalui RPC maupun context defaults. Duplikasi jenis/operasi dilindungi konflik tulis pada baris picking native. Koreksi membutuhkan tindak lanjut terdokumentasi, bukan perubahan diam-diam durasi lama.

Batas query:1.000 lokasi,50.000 quant/pergerakan/waktu operasi,10.000 produk valuasi. Bila terlampaui, pengguna diminta mempersempit cakupan; tidak ada agregasi parsial diam-diam. UI menampilkan200 lokasi/SKU pertama beserta total dan keterangan batas. Tidak ada cache yang melewati company/role. Read-model tidak memposting stok/akuntansi atau mengubah master produksi.

## Bukti penerimaan

Regresi native ditambahkan untuk hierarki package/slot/dimensi kosong, geometri anak dan kebijakan invalid; pemalsuan context/duplikasi/idempotensi/pembatasan pekerja pada waktu operasi; umur stok dan klasifikasi pergerakan; serta kontrol akun valuasi posted yang dipetakan native. Regresi JS menguji source domain dan klik usang. Fixture/screenshot Odoo native mencakup desktop/tablet/portrait dan dibatasi pada `ci_db` disposable, tanpa perubahan server live.

Ruff, manifest, XML/compile, Node dan whitespace lokal adalah pemeriksaan implementasi, bukan verdict native PASS. Bukti instalasi/upgrade/visual dan verdict reviewer harus merujuk HEAD final. Three.js tahap6 tetap terpisah; data layout aktual wajib diterima sebelum scene diaktifkan.


Receiving-dwell coverage (PR84 repair): every actually received positive quantity branch must reach first storage arrival in the same warehouse, with exact native-UoM quantity coverage at each intermediate split. Missing/cancelled/short/overallocated/shared-origin paths fail closed. A pending downstream backorder with zero recorded done quantity still blocks the received branch. Separate incoming receipt backorders have their own clock and unreceived quantities are not fabricated. Later customer shipment after first storage arrival does not reopen receiving. Completion selection must be an actual first-storage picking in the covered chain. Native regressions cover these rules; no legacy duration is backfilled.
