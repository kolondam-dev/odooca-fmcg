# Bukti lokasi dan foto resmi — tahap4 staging

Endpoint ini menyimpan bukti mandiri, belum membuat check-in, SO, POD, collection
atau closing. Default live tetap terkunci; simulator tidak diubah. Deployment dan
acceptance terhadap staging Odoo nyata tetap terpisah dari CI disposable.

## Hak akses dan scope

Admin harus memberi group **FMCG Mobile Evidence Capture** secara eksplisit.
Group ini mengimplikasikan mobile read/internal user, tanpa hak write Sales/Stock.
Bootstrap hanya menambahkan capability `evidence.capture` untuk group tersebut.
User read-only lama tetap tidak dapat mengunggah. Assignment hari WITA, company
default akun, SKU/outlet/warehouse dan ACL native tetap mengikuti tahap2.

POST `/api/v1/evidence` memakai sesi cookie Odoo, native multipart `csrf_token`,
`metadata` JSON dan tepat satu `photo`. Native CSRF yang salah dapat mengembalikan
HTTP400 sebelum controller; tidak ada csrf bypass. Origin/cross-site/query/scope
selector yang tidak sesuai ditolak. Gateway membatasi body6MiB; controller
membatasi foto5MiB dan metadata4KiB. Jangan expose Odoo langsung melewati gateway.

Metadata hanya UUID canonical, outlet ID, business_date, snapshot_version,
photo_selected_at, device_recorded_at, fix_sampled_at, latitude/longitude/accuracy.
Company, owner, koordinat master dan radius tidak diterima dari client. Server
membaca assignment/master, memerlukan snapshot v2 terkini, menghitung jarak
Haversine dan memerlukan `distance + accuracy <= radius`. Outside/uncertain
menghasilkan422 tanpa record. Radius assignment tetap5–15m; bukan radius kantor.
Perubahan master/snapshot mengharuskan daily sync ulang409.

Waktu GPS dibandingkan dengan clock server: umur maksimal60detik (toleransi future1detik). Foto dipilih maksimal
300detik sebelum penerimaan; pencatatan perangkat maksimal60detik sebelumnya
(toleransi clock future5detik untuk waktu pilih/pencatatan). Waktu pilih foto tidak boleh sesudah pencatatan.
Ini pemeriksaan konsistensi/freshness, bukan bukti waktu shutter atau anti-mock GPS.
Hari WITA diperiksa sebelum dan sesudah penyimpanan; rollover membatalkan record
beserta attachment dalam savepoint. Tidak menurunkan geofence resmi menjadi demo.

## Foto sumber, derivative dan receipt

Foto sumber adalah **byte file yang diterima dari browser**, bukan jaminan file
sensor kamera asli. Byte disimpan utuh pada binary attachment privat. Konten
harus JPEG/PNG yang bisa didekode, satu frame, maksimal12juta piksel; SVG/file
rusak/decompression bomb ditolak. Nama/MIME kiriman client bukan otoritas format.

Pillow server menghasilkan JPEG tersendiri, orientasi EXIF diterapkan pada
hasil saja, sisi maksimum1280px ditambah panel watermark. Panel memuat waktu
pencatatan perangkat dan waktu penerimaan server secara terpisah dalam WITA,
koordinat serta akurasi GPS, dan pernyataan keaslian GPS/shutter belum diverifikasi.
Timestamp tidak disebut sebagai waktu asli kamera. Tidak ada basemap resmi baru.

Receipt menyimpan owner/company/warehouse/assignment server, SHA256 sumber, derivative, dan binding metadata; posisi/radius
master yang dipakai ikut disimpan. Model immutable: user tidak dapat create/write/
unlink lewat ORM/RPC; controller memakai elevasi create yang terbatas sesudah
semua validasi scope/media. Record rules membatasi owner dan company yang sah;
admin dapat audit/retensi (unlink) tetapi tidak mengedit isi receipt. Tidak ada
attachment public/access_token atau URL foto publik. Hash bukan digital signature
atau pembuktian kondisi fisik; user yang mengontrol perangkat masih dapat
memanipulasi sumber input. Validasi server mencegah client mengubah aturan master.

GET `/api/v1/evidence/<uuid>/original|watermarked` memerlukan role, owner dan
company default yang sesuai; no-store/private/Vary Cookie/nosniff. UUID asing
menghasilkan404 setelah pemeriksaan role. Native attachment ACL tetap berlaku.

Idempotensi terikat user+UUID dan fingerprint metadata/file. Replay identik
mengembalikan receipt lama200, termasuk sesudah waktu/day deadline (bukan bukti
baru). Isi berbeda pada UUID sama409. Constraint unik mencegah duplikasi saat
race; loser409 dapat retry UUID/body yang sama pada request baru. Tidak mengganti
receipt atau membuat revisi diam-diam. Upload baru sukses201.

## PWA staging

Sesudah daily sync, capability evidence membuka form outlet/foto/GPS. Tidak ada
fallback koordinat atau gambar demo. File sumber diunggah tanpa kompresi PWA;
form mengirim CSRF native. PWA memeriksa receipt scope/UUID/hash sumber/waktu/
koordinat dan hash derivative privat sebelum menampilkan hasil. Retry memakai
UUID dan metadata yang sama selama form masih ada. Perubahan foto/GPS/outlet
memulai pengajuan baru; replay tidak mengubah bukti lama.

State hanya memori tab. Reload/offline/hidden/sesi berubah membersihkan UI;
request yang selesai terlambat tidak mengisi sesi baru. Abort/timeout tidak
menjamin pembatalan transaksi server: bukti bisa sudah tersimpan; UI tidak
mengklaim sukses sebelum receipt dan derivative tervalidasi. Belum ada draft
upload offline, daftar histori PWA atau alur rekonsiliasi transaksi. Bukti ini
belum dapat dipakai menutup kunjungan/DO melalui backend bisnis.

## Verifikasi

`test_evidence_api.py` memakai ORM/HttpCase asli pada CI Odoo: hash/dua file,
idempotensi, immutable ACL/IDOR, scope/master authoritative, geofence uncertainty,
clock/foto rusak, CSRF multipart, replay dan rollover rollback. Client unit dan
browser memakai transport fixture, bukan klaim autentikasi Odoo staging nyata.
Gateway HTTP/HTTPS smoke mengizinkan POST evidence secara eksplisit sambil tetap
memblokir business commands; header terpercaya dari PR41 dipertahankan.

Acceptance nyata setelah deploy memerlukan user capture terprovisi, titik master
terverifikasi dan GPS perangkat di lokasi outlet. Uji kamera/izin GPS, di dalam/
luar/ragu, jam perangkat, expired session, source vs derivative, private download,
retry, serta cleanup UI. Retensi kapasitas filestore dan penggunaan bukti pada
check-in/POD menjadi keputusan operasional/integrasi lanjutan.
