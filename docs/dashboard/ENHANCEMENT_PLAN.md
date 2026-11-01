# Dashboard: rencana peningkatan dan kontrak keputusan

Status: rencana disetujui pemilik; implementasi bertahap. Basis audit kode main `13b2ee0` (2026-11-01). [F] = terverifikasi pada sumber/tes; [A] = rancangan; [BU] = belum diverifikasi runtime.

## Tujuan dan urutan delivery

Dashboard membantu pengguna mengetahui keadaan bisnis, penyimpangan yang perlu ditangani, penyebab, dan dokumen yang dapat ditindaklanjuti. Pengalaman tetap menyatu dengan navigasi, form, list, hak akses, dan bahasa visual Odoo. Tambahan utilisasi aset dan visualisasi 3D memperluas rencana awal, tidak menggantikan analisis keuangan, penjualan, collection, dan kualitas data.

| Tahap | Hasil yang dapat direview | Gate penerimaan |
| --- | --- | --- |
| 1 — fondasi, PR ini | Rekonsiliasi overdue, penjumlahan target pada periode identik, filter tolakan armada, company rules/role ACL, respons RPC terbaru, drill-down terikat scope; capture visual Odoo asli di CI | Regresi fungsi produksi, tes ORM/SQL/ACL native, upgrade DB persisten, screenshot desktop/tablet dan temuan visual; tidak menyamakan screenshot CI dengan acceptance live |
| 2 — presentasi keputusan | Susunan konteks → KPI → exception → diagnosis → dokumen; komponen Odoo konsisten, filter global beserta scope yang jelas, kosong/error/loading/aksesibilitas | Review screenshot populated/empty/error pada peran relevan; keyboard, viewport dan drill-down; tidak ada dekorasi tanpa fungsi informasi |
| 3 — kedalaman bisnis | Margin, target tersegmentasi, kualitas PJP/EC, distribusi assortment, collection/aging migration, backlog/OTIF/retur/expiry | Definisi KPI dan rekonsiliasi ke dokumen sumber, owner metrik, threshold dan aksi disepakati |
| 4 — utilisasi aset dan biaya | Volume/berat gudang dan armada, trip/period/mileage, biaya pengiriman dan maintenance yang terpisah | Coverage master dan event cukup; ukuran fisik/UoM konsisten; denominator kapasitas efektif; tidak mengubah unknown menjadi 0 |
| 5 — warehouse detail | Occupancy per zona/bin/rack/pallet, throughput, dwell time, picking/putaway, expiry dan capacity constraints | Master kapasitas/lokasi dan alur stok dapat diaudit; drill-down sampai quant/lot/movement |
| 6 — advanced spatial dashboard | Three.js terpisah: tata letak aktual, stok, aktivitas dan posisi armada yang memiliki sumber | Layout berdimensi dan koordinat resmi tersedia, freshness jelas, fallback 2D/tabel, performa terukur; tidak membuat posisi semu |

Merge dan deployment merupakan langkah terpisah. PR tahap 1 tidak mengaktifkan fitur 3D, tidak menulis master/server nyata, dan tidak membuktikan acceptance perangkat/staging.

## Kontrak KPI dan kualitas data

Setiap KPI wajib mencantumkan definisi, satuan/currency, grain, periode atau waktu snapshot, filter yang berlaku, numerator/denominator, sumber dokumen, owner, freshness dan drill-down. Kosong berbeda dari nol; rasio tanpa denominator ditampilkan `—`. Penjumlahan lintas currency memerlukan konversi eksplisit, bukan label Rp pada angka campuran. Tanggal operasional WITA dan tanggal SQL/server tidak boleh disamakan secara diam-diam.

| Kelompok | Definisi/sumber dan batas saat ini | Pengembangan berikutnya |
| --- | --- | --- |
| Penjualan | [F] dashboard Sales menggunakan SO confirmed; jangan disamakan dengan invoice/omset akuntansi | Pisahkan ordered, delivered, invoiced DPP, return/credit note, gross margin; target per salesperson/area/channel/principal dan periode pembanding sepadan |
| Realisasi finance | [F] tahap 1 memakai signed untaxed posted invoice/refund dalam periode target, company currency | Rekonsiliasi GL dan kebijakan tanggal invoice vs accounting date; tampilkan bridge SO → pengiriman → faktur |
| Target | [F] target company dijumlahkan hanya pada rentang tanggal identik yang dipilih; duplikat aktif exact company/periode ditolak | Target segmentasi, validasi overlap/currency, coverage company tanpa target; target tidak boleh terhitung ganda |
| Piutang | [F] residual invoice terbuka, bucket berdasarkan CURRENT_DATE DB; tabel pelanggan dihitung dari invoice terfilter yang sama | Full AR subledger: credit/unallocated payment, installment maturity, historical as-of dan rekonsiliasi saldo ledger; label sekarang tidak mengklaim keseluruhan ledger |
| Collection | [F] inbound payment paid/in_process; judul pembayaran tercatat | Pisahkan uang diterima, posting, settlement/reconciliation bank, alokasi invoice, aging migration dan promise-to-pay kept/broken |
| PJP dan EC | [F] evidence dan order membutuhkan pengujian hubungan kausal | EC hanya order sah sesudah kunjungan pada assignment/outlet/hari yang sesuai; no-order reason, produktivitas rute, validitas evidence; jangan menghitung order sebelum visit |
| Penetrasi assortment | [F] universe yang hanya berasal dari grup terjual akan menutupi grup nol | Universe SKU/principal yang eligible per outlet, active selling outlet, numeric/weighted distribution, repeat/drop/lost outlet |
| Stok | [F] qty × standard price merupakan estimasi biaya stok, bukan valuasi akuntansi final | Rekonsiliasi stock valuation, available/reserved/blocked, stock cover/turn, slow/dead stock, expiry at risk dan lot tanpa tanggal sebagai exception |
| Pengiriman | [F] fulfillment count existing bukan OTIF | Backlog cohort, first attempt, H+1/H+2, OTIF, partial/reject reason terpisah line/DO, failed attempt dan reschedule |
| Biaya | [F] model trip saat ini BBM + helper; bukan seluruh biaya operasional | Biaya order/pengiriman murni, biaya outlet, maintenance armada dan alokasinya terpisah; hindari double counting |

H+1/H+2 harus menyatakan anchor (order accepted/cutoff atau promised date), kalender kerja, timezone, cohort denominator dan perlakuan pending/cancel. OTIF menggabungkan on-time dan in-full pada DO/cohort yang sama, bukan perkalian dua agregat. Tampilkan median dan p90 lead time serta backlog yang belum selesai agar kasus lama tidak hilang dari statistik.

Exception memerlukan nilai dampak, umur, alasan, PIC, tenggat, status dan tautan dokumen. Kandidat: overdue bernilai besar, promise gagal, order tertahan limit/approval, backlog terlambat, tolakan berulang, expiry dekat, data dimensi kosong. Prioritas berdasarkan risiko bisnis, bukan warna dekoratif.

## Kontrak utilisasi aset

[F] Field yang sudah tersedia: `product.template.carton_qty`, `carton_length_cm`, `carton_width_cm`, `carton_height_cm`, computed `carton_volume_cbm`, `carton_weight_kg`; `fleet.vehicle.capacity_cbm`, `capacity_ton`, `box_length`, `box_width`, `box_height`; kapasitas default tipe di `id.fleet.type`. Sumber: `addons/id_base/models/product_template.py`, `fleet_vehicle.py`, `fmcg_dimension.py`. Field tersebut belum membuktikan kelengkapan/akurasi data produksi.

[A] Volume SKU dalam satuan stok = qty dasar / carton_qty × carton_volume_cbm; berat = qty dasar / carton_qty × carton_weight_kg. Konversi UoM terlebih dahulu, perlakukan kemasan parsial sesuai kebijakan yang eksplisit. Kubikasi karton bukan geometri aktual tumpukan. Tampilkan coverage qty/SKU dengan dimensi/berat valid dan nilai unknown secara terpisah.

[A] Gudang: bedakan kapasitas geometris gedung, kapasitas usable storage, kapasitas slot/pallet dan beban lantai/rack. Occupancy volume = volume tersimpan valid / usable capacity pada lokasi/snapshot yang sama; pallet occupancy = occupied eligible slots / available eligible slots. Receiving, quarantine, aisle dan staging tidak otomatis masuk denominator penyimpanan. [BU] Model khusus kapasitas warehouse/bin/rack/pallet, layout koordinat dan aturan stacking belum ditemukan di addon kustom; inventarisasi native `stock.location` dan master existing wajib sebelum membuat model tambahan.

[A] Armada: occupancy volume dan berat terpisah per departure/trip; pembatas efektif adalah dimensi yang lebih dulu penuh. Jangan merata-ratakan persentase trip tanpa bobot. Agregat periode: total loaded cbm / total dispatched usable capacity; utilisasi perjalanan multi-stop juga dapat dibobot cbm-km/available cbm-km bila jarak per leg tersedia. Empty return, overload, unassigned vehicle dan capacity unknown menjadi exception.

[A] Distance dari odometer/trip reading yang berurutan atau sumber GPS tervalidasi; native fleet odometer/maintenance perlu dipetakan. Cost/km = biaya terkait / km sah; tampilkan juga biaya per DO, drop dan DPP delivered. Pisahkan biaya langsung trip/order, biaya outlet, maintenance actual dan allocation by km/time. Total kontrol = actual cost source; alokasi tidak menambah total baru. Pilih satuan km pada UI Indonesia; konversi mile bila diperlukan, jangan mencampur.

## Audit visual dan desain tahap berikutnya

[F] Cloud browser sesi audit gagal pada transport browser, sehingga belum ada klaim review live. CI tahap 1 menyiapkan fixture sintetis pada `ci_db`, membuka tiga action dashboard Odoo asli melalui Playwright, mempertahankan native navbar, menangkap screenshot 1440×900 dan 1024×768 serta tab analitis. Tidak ada mocked RPC atau perubahan data server. Artifact: `ui-smoke-diagnostics/dashboard-visual`.

[BU] Screenshot harus ditinjau setelah run selesai. Ukur kepadatan, hierarki informasi, overflow/scroll, konsistensi Odoo, keterbacaan tabel, filter-context, kontras dan affordance drill-down. Success script bukan verdict kualitas estetika. Hasil visual menjadi dasar tahap 2, bukan alasan mengganti semuanya dengan mockup terpisah.

[A] Dashboard utama: 4–6 KPI inti, masing-masing value, delta bermakna, periode dan status data. Satu area exception yang actionable. Bar untuk perbandingan, line untuk tren, stacked aging untuk komposisi; hindari gauge/donut dekoratif, animasi dan gradient berlebihan. Detail berbentuk tabel terurut dan native list/form. Filter persisten pada drill-down dan kembali; loading menahan klik data lama, response usang tidak mengganti pilihan terbaru. Tampilan kompak Odoo, jarak dan tipografi konsisten, satu pola scroll dan sticky header yang diuji.

[A] Three.js adalah advanced view opt-in, code-split/lazy-load; pilih objek → detail native, legend jelas, waktu update dan sumber posisi terlihat. Gunakan instancing/culling dan pembatasan refresh berdasarkan benchmark; sediakan 2D/tabel untuk perangkat lemah dan akses keyboard. Tanpa bin/layout resmi, tampilkan data unavailable, bukan animasi gudang fiktif.

## Kinerja dan acceptance lintas tahap

- [A] Benchmark cold/warm RPC p50/p95, SQL EXPLAIN pada dataset representatif, jumlah query, rows/payload dan memori; optimasi indeks/agregasi sebelum menambah cache.
- [A] Cache harus terikat company, role, filter, timezone dan freshness; jangan menyamarkan stale data. Hindari fetching semua invoice untuk tabel jika agregasi server dapat mempertahankan rekonsiliasi.
- [F] Tahap 1 membatasi direct read SQL view berdasarkan peran/company dan menolak mixed currency finance/WMS. Record rules tidak menggantikan pengujian role/ACL pada service dan underlying views.
- [A] Kasus wajib: populated, empty, invalid master, partial coverage, cross-company, wrong-role, late success/error RPC, filter drill-down, upgrade existing DB, readonly/source preservation.
- [BU] Periode WMS global, revisi margin/EC/penetrasi, full AR ledger, historical snapshot, cost-to-serve dan redesign menyeluruh tetap backlog. Jangan menyatakan seluruh program selesai hanya karena tahap fondasi lulus.
