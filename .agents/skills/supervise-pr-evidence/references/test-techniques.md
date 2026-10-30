# Teknik pengujian supervisi

## Isi

1. CI/source
2. Oracle stok dan akuntansi
3. Transaksi dan replay
4. PWA sesi/media
5. UI/browser
6. Deployment

## 1. CI/source

Catat SHA/event/run/job/conclusion/jumlah tes/artifact. Hijau pada SHA lama bukan hijau pada fix baru. Cocokkan tree HEAD dan synthetic merge dengan git rev-parse REF^{tree}. Baca tes yang benar-benar berjalan; bedakan install bersih dari upgrade DB lama. Parse JS untuk page.evaluate dengan node --check, YAML/TOML/manifests dengan parser aslinya, SCSS dengan compiler produksi.

## 2. Oracle stok dan akuntansi

- Turunkan expected dari CSV/kontrak independen, bukan summary loader atau DB actual yang sedang diuji. Gunakan Decimal dan konversi UoM per produk. Mutasikan satu input oracle untuk membuktikan responsnya.
- Bandingkan multiset company/location/SKU/lot; total dapat menyembunyikan swap. Audit reserved per SKU dan unexpected keys/records.
- Resolusi company/gudang harus memakai identitas persisten yang disepakati. Reject missing/ambiguous/conflicting config/XMLID; jangan mengganti dengan env.company, ID2, nama mirip atau warehouse “not other”.
- Audit native stock.move -> singular account_move_id sesuai ORM aktual; jangan mengasumsikan SVL. Periksa posted, STJ, company, product, date, source/destination, debit HPP/kredit stok, nominal independen dan coverage transaksi sumber.
- Dukung beberapa move dalam satu header jurnal jika native demikian. Konsumsi AML unik berdasarkan kandidat yang benar atau rekonsiliasi kelompok; buktikan anti-reuse dan hindari assertion vacuous terhadap empty recordset.
- Mutasi bernilai tinggi: swap+qty/-qty antarsku, substitusi lot, reserved swap, journal unlink/rebind, company/product/date salah, debit-credit terbalik, source supplier, balanced value tampering, cross-cutoff invoice. Jalankan setelah posting agar auditor independen yang diuji, bukan hanya hook loader.
- Definisikan business timezone/UTC boundary dan audit kedua fase. Re-audit AML Juli setelah carry-forward Agustus; tanggal invoice saja tidak mewakili timestamp stock movement.

## 3. Transaksi dan replay

Injeksi exception dan no-op write; wajibkan readback field kritis sebelum validate/post. Ukur bahwa boundary berikutnya belum dipanggil. Pada stock move, relokasi dapat menghapus move lines: align sebelum alokasi lot/quantity. Uji rollback record baru dan mutasi in-place record lama. Untuk PostgreSQL, tangkap snapshot, injeksi pada loader boundary, buktikan rollback/no commit, invalidate cache dan baca ulang. Savepoint helper saja bukan bukti loader memanggil rollback. Snapshot mencakup lot/lokasi/UoM/company, journal binding, waktu penuh, residual/reconciled, payments dan GL. Audit Run1 benar sebelum membuktikan Run2 identik; jangan menulis ulang tanggal picking done.

## 4. PWA sesi/media

- Race dua bootstrap: respons sukses/error lama tidak boleh menimpa identity/CSRF/snapshot generasi baru. Abort saja tidak cukup.
- Uji clear/logout/role/company/day, offline/hidden/reload/WITA midnight. Periksa storage/cache sesuai kontrak volatile/offline yang berlaku.
- Cocokkan media terhadap owner/company/warehouse/assignment/day/trip/source/purpose. UUID DO saja pernah meloloskan POD kemarin untuk closing hari baru. Pisahkan replay historis sah dari bukti transaksi baru.
- Uji CAS, offline draft, root SO day, approval setelah midnight, rasio SKU144/12 vs24/6 dan UoM historis legacy corrections.
- Audit native cookie/CSRF/ACL/record rules, dua-akun IDOR dan private attachments. Client scope/radius bukan otorisasi server. Hash source/derivative dan waktu device/server harus dibedakan; watermark bukan bukti anti-mock GPS atau shutter asli.
- Peta hanya preview kecuali backend mencatat transaksi. Uji label TEST/simulasi, tile opt-in/attribution, denied GPS tanpa fallback dan late callback ke target lama.

## 5. UI/browser

- SCSS min(100%,32rem) pernah gagal pada libsass produksi. Validasi compiler nyata.
- Audit model/resolved view sebelum mengarang field. Native SO note/tax_totals; invoice narration/tax_totals. Dua diskon memerlukan keputusan bisnis, bukan asumsi field.
- Fixture fokus harus terhubung document.body; assert isConnected/activeElement dan cleanup finally. Hidden input tidak boleh mengalahkan visible text input. Guard title fail-closed terhadap multiple controls/contenteditable/required/select/textarea; focus failure memulihkan title asli.
- Ukur normal-flow dengan sticky dinonaktifkan sementara lalu restore style. Identifikasi scroll owner, containing block, scrollport/clamp interval dan efek trial/actionability. Last row harus terlihat utuh dalam viewport dan action tidak tertutup; “di bawah footer” saja tidak cukup.
- Zoom harus mengubah metrik aktual. Cover SO/invoice berisi baris desktop/mobile. Telusuri overflow melalui clientWidth/scrollWidth, bounding boxes dan ancestor computed styles; jangan menaikkan toleransi demi PASS.

## 6. Deployment

Periksa effective config/build logs: config repo dapat memilih Dockerfile lain, static healthz200 dapat menyamar sebagai gateway sehat. Uji /web/login menuju Odoo, /field/build-info.json mode benar dan API respons kontrak (bukan404/SPA HTML). Odoo19 ProxyFix bergantung forwarded-host; trusted gateway menetapkan authority/proto dan membuang header klien alternatif. Uji spoof dan cookie Secure. Pisahkan Werkzeug/HTTP fixture dari Odoo+Railway/perangkat nyata. OAuth plugin tidak otomatis menyediakan CLI credential, browser session, variable values atau shell. Production demo tetap memerlukan preservasi data dan pemulihan; scope itu bukan izin reset/bypass geofence.
