# Keputusan owner — acceptance GPS/foto jarak jauh

Tanggal: 2026-10-30 (WIB). Basis: main fca1e0ff20ea9bcd3fd466d0d85bac46efe72cdf, PR #42.
Status: keputusan kebutuhan dan rencana pelaksanaan; belum deployment/provisioning atau acceptance.

## Mandat owner [F]
- Asumsikan staging belum tersedia; evaluasi penggunaan server demo awal atau instance tambahan pada Railway yang sama.
- Agen boleh memilih akun uji dan menetapkan password dummy. Owner mengizinkan kredensial akun demo transparan karena lingkungan disposable; tidak berlaku untuk akun admin, Railway, database atau lingkungan lain.
- Agen boleh memilih customer sesuai hari assignment.
- Owner menjadi penguji jarak jauh dari kantor/outlet; perlu pengecualian lokasi.
- Untuk sesi ini, akurasi lokasi boleh dikesampingkan dengan placeholder. Semua fungsi dan visibilitas maps harus tetap tersedia.
- Keputusan ini harus terlihat oleh reviewer.

## Inventaris dan rekomendasi [F/A]
Pemeriksaan Railway read-only menemukan proyek pleasant-caring, hanya environment production; layanan field-pwa, odooca-fmcg dan Postgres. Odoo dan Postgres memiliki volume masing-masing. Status deployment SUCCESS bukan bukti versi addon, konfigurasi gateway, login, maps atau acceptance perangkat sudah benar.

[A] Rekomendasi: environment baru staging-remote pada proyek Railway yang sama, dengan Odoo, gateway/PWA, database dan filestore terisolasi serta origin HTTPS sendiri. Tidak perlu akun/proyek Railway baru. Environment terpisah tetap menjalankan resource yang dapat menambah biaya; jangan menghubungkan ulang ke database/volume production. Verifikasi pemisahan nyata, bukan sekadar nama environment. Baseline production tetap dipertahankan.

Server demo awal secara teknis dapat dipakai jika dialihfungsikan secara eksplisit, tetapi akan mencampurkan fixture remote dan demo yang ada. Karena itu bukan pilihan utama. Provisioning/deploy belum dilakukan oleh perubahan dokumentasi ini.

## Batas pengecualian lokasi [F/A]
[F] Owner mengizinkan placeholder/pengecualian akurasi untuk sesi uji remote.
[A] Implementasikan sebagai mode remote-test yang eksplisit dan terbatas pada environment disposable, akun/assignment uji dan sesi bertanggal; default mati. Tidak mengubah validasi operasional PR #42 secara global dan tidak menyamarkan placeholder sebagai GPS nyata.

- Pisahkan koordinat/accuracy perangkat yang benar-benar tersedia dari titik/accuracy simulasi; nilai tidak tersedia ditulis tidak tersedia, bukan angka presisi palsu.
- Tampilkan banner REMOTE TEST / LOKASI SIMULASI pada layar, maps, receipt dan watermark foto uji.
- Catat sumber lokasi, alasan pengecualian, aktor, waktu server, assignment dan konfigurasi sesi. Override harus diperiksa server; jangan menerima flag client sebagai otorisasi.
- Di maps tampilkan titik master customer dan titik uji/perangkat dengan label berbeda, radius dan jarak bila dapat dihitung. Placeholder accuracy tidak dihitung sebagai kelulusan geofence.
- Tetap uji session, assignment/day/snapshot, upload, CSRF, owner/company, private photo, source/derivative hash, watermark waktu terpisah dan replay user+UUID.
- Sediakan mode strict untuk regresi penolakan outside/uncertain/stale. GPS lapangan nyata tetap acceptance terpisah.
- Lokasi/accuracy simulasi tidak membuktikan keberadaan petugas di outlet, keaslian shutter atau akurasi GPS.

## Akun, customer dan hari uji [A]
Setelah lingkungan terisolasi tersedia, inventaris akun/master melalui Odoo lalu pilih akun internal non-admin dengan assignment aktif dan capability capture. Siapkan akun kedua untuk uji akses lintas pengguna. Password dummy unik per sesi boleh dibagikan kepada owner; jangan gunakan ulang password admin atau kredensial infrastruktur. Dokumen/log git ini tidak memuat password. Belum ada akun yang direset atau dibuat.

Pilih customer dari assignment pada hari bisnis server (WITA), catat ID user/company/warehouse/assignment/outlet dan snapshot. Jangan menetapkan outlet/tanggal statis sebelum membaca data. Untuk remote test, gunakan fixture khusus tanpa menggeser koordinat master kanonikal. Jangan memberi akun uji write Sales/Stock hanya demi capture.

## Maps dan kriteria selesai [F/BU]
[F] Layar OfficialEvidence/ReadApp pada PR #42 belum menyediakan basemap resmi; requirement maps owner adalah tambahan implementasi, bukan kemampuan yang telah diterima.
[BU] Provider/lisensi/attribution, akses tiles dari perangkat, kebijakan privasi dan kredensial provider bila diperlukan harus ditetapkan saat implementasi. Maps tidak boleh membuat foto privat/receipt dipublikasikan.

Sesi dinyatakan lulus fungsi remote setelah:
1. Login dan daily sync nyata dari perangkat owner menampilkan assignment hari itu.
2. Maps terlihat dengan attribution, master/radius dan posisi uji berlabel; kegagalan tile/izin GPS terlihat jelas tanpa titik palsu diam-diam.
3. Foto sumber dan derivative privat dapat dilihat pemilik; watermark membedakan waktu perangkat/server dan status remote test.
4. Retry UUID sama mengembalikan bukti yang sama; UUID lain bukan deduplikasi semua foto identik.
5. User lain ditolak; CSRF/scope/day tetap diberlakukan; tidak ada check-in/POD/SO/closing yang tersirat.
6. Hasil strict dan remote dicatat terpisah; bukti hasil uji menyebut perangkat/browser/build/server dan batas yang belum diuji.

## Urutan pelaksanaan dan status
- Selesai: dokumentasi keputusan owner dan inventaris Railway read-only.
- Berikutnya: implementasi mode remote-test berlabel dan maps melalui PR, regresi strict vs remote, kemudian provisioning environment terisolasi dan akun/master melalui alur aplikasi/fixture terkontrol.
- Setelah deployment yang ditentukan secara eksplisit: berikan URL HTTPS dan akun dummy kepada owner, jalankan sesi uji perangkat.
- Belum dilakukan: create environment, deploy/redeploy, reset database, perubahan akun/password/master, maps, bypass geofence, atau acceptance perangkat. Live tetap terkunci.
