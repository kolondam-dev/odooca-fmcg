# Tahap3 — PWA baca resmi pada staging

[F] Branch ini menyediakan build `staging` yang terpisah dari `demo` dan `live`.
`npm run build` tetap menghasilkan live terkunci; staging harus dipilih eksplisit
melalui `npm run build:staging` atau Docker build arg `PWA_BUILD_MODE=staging`.
Tidak ada deployment, perubahan data server, atau aktivasi transaksi oleh PR ini.

## Alur yang diimplementasikan

1. Buka `/field/` pada origin staging yang sama dengan Odoo. UI membaca
   GET `/api/v1/me/bootstrap`;401 menampilkan tautan native
   `/web/login?redirect=%2Ffield%2F`. Password tidak diminta/disimpan oleh PWA.
2. Login/ganti akun pada halaman Odoo, lalu kembali ke `/field/`. UI menunjukkan
   identitas dari server, company ID dan hari bisnis WITA. Ini bukan absensi.
3. Pilih **Daily sync**. Bootstrap baru wajib selesai sebelum snapshot dibaca.
   Adapter memvalidasi catalog v2 dan scope company/user/hari. Daftar baru hanya
   tampil setelah seluruh pembacaan berhasil; daftar lama dibersihkan di awal.
4. UI menampilkan outlet terjadwal dan katalog dengan kode SKU, rasio karton/pack,
   harga referensi per karton serta stok tersedia pada warehouse assignment.
   Ketentuan harga/stok tahap2 tetap berlaku; bukan otoritas transaksi.
5. Respons 401/403/409/422, respons rusak, kegagalan jaringan, offline, pergantian WITA,
   tab disembunyikan atau **Bersihkan tampilan** menghapus identitas/daftar dari
   memori. Respons lama tidak dapat mengisi kembali tampilan. Setelah reconnect,
   sesi dan snapshot harus dibaca ulang. Tidak ada restore offline tahap baca.

Staging tidak mengimpor FieldStore/outbox maupun mock provider. Identity/token/
snapshot tidak ditulis ke IndexedDB, localStorage, sessionStorage atau cache SW.
Cookie session tetap dikelola Odoo/browser. Worker `/field/` sebelumnya dilepas;
worker staging tidak menyediakan offline fetch. Gunakan origin staging khusus,
terpisah dari demo/production; PWA demo mempunyai penyimpanan dan lifecycle sendiri.

Tidak ada form SO/revisi, absensi, approval, evidence, collection atau closing.
Adapter read-only menolak submit405 sebelum fetch. Daftar Delivery belum ada
karena backend tahap2 mengembalikan `deliveries=[]`; tidak membuat manifest palsu.

## Gateway satu origin

Gunakan `staging-locations.conf` sebagai **template include untuk server HTTPS
staging yang sudah dikonfigurasi**, bukan konfigurasi Railway siap deploy.
Pemilik/agent deploy mengganti hostname upstream dan memverifikasi TLS/network.

- `/field/` menuju static server build staging.
- Dua route baca `/api/v1/me/bootstrap` dan `/api/v1/sync/snapshot` menuju Odoo.
- Route `/api/` lain ditolak404, method non-GET pada route baca ditolak gateway.
- `/web/login`, session dan asset Odoo tetap menuju Odoo pada origin yang sama.
- Host dan X-Forwarded-Host ditetapkan dari `$http_host`; X-Forwarded-Proto
  dari `$scheme` dan X-Forwarded-For dari `$remote_addr`, termasuk pada route
  API dan fallback Odoo. Header Forwarded/X-Forwarded-Port/Prefix kiriman klien
  dibuang, bukan dipercaya. Cookie diteruskan; tidak ada CORS wildcard, credential di
  build, auth bypass, login API baru, API proxy dalam static server, atau rewrite
  ke HTML untuk API. Cookie session Odoo harus Path=/, HttpOnly dan Secure HTTPS.
- Odoo perlu `proxy_mode=True`, host/database filtering benar dan hanya menerima
  forwarded headers dari gateway terpercaya. Template mengasumsikan TLS
  diterminasi pada gateway; jika ada terminator lain, konfigurasi trusted proxy
  harus disesuaikan agar host/proto publik tetap benar. Jangan expose backend
  untuk menghindari batas gateway. Ini tidak memperluas ACL native Odoo.

Provisioning user/group/assignment per WITA tetap mengikuti
`addons/id_mobile_api/README.md` di root repo. Tidak membuat assignment dari seed
atau menyatakan full dataset siap. Standalone `npm start` tetap503 untuk `/api/`
dan404 untuk halaman login Odoo; gateway diperlukan untuk koneksi resmi.

## Bukti pengujian dan acceptance operasional

Unit menguji lifecycle/generation, deadline WITA, penghapusan state dan larangan
submit. Browser ponsel/tablet memakai **fixture transport HTTP**, menguji login
handoff, daily sync, rasio SKU, rollback error/scope, offline/reload dan tengah
malam. Fixture tidak membuktikan login Odoo asli atau penerimaan data staging.
HttpCase Odoo tahap2 tetap menguji autentikasi/ACL nyata pada CI Odoo.

`bash pwa/hosting/test-gateway.sh` dari root repo menjalankan Nginx+build staging
bersama fixture backend disposable Python/Werkzeug dalam Docker CI. Fixture
mereplikasi gate Odoo19: ProxyFix x_for=1/x_proto=1/x_host=1 hanya bila
X-Forwarded-Host tersedia. Tiga probe unit membuktikan perilaku header hilang,
header attacker, dan authority gateway yang sah. Smoke menguji HTTP serta
HTTPS dengan sertifikat CA disposable yang diverifikasi curl (--cacert, bukan
-k), port publik nondefault, kedua route API dan fallback /web, spoofed
forwarded headers, origin valid/invalid, secure cookie dan method boundary.
Key/cert dibuang saat cleanup; bukan artifact atau credential deployment.
Ini membuktikan TLS/proxy transport; bukan bukti ACL atau deployment Odoo nyata.
Fixture hanya dipakai tes; tidak ikut runtime image PWA.

[BU] Acceptance end-to-end **pada staging nyata** harus dilakukan setelah deploy
terpisah yang diotorisasi: login user assignment hari ini, cocokkan company,
warehouse, kode/rasio/harga/stok serta outlet terhadap Odoo, uji logout/session
expiry, user tanpa role/assignment, company berbeda dan rollover WITA. Pastikan
Network hanya GET dua route baca dan tidak ada command/write. Ulangi di ponsel
serta tablet. Verifikasi TLS, cookie Secure/HttpOnly, no-store dan tidak adanya
CORS wildcard; simpan bukti teredaksi tanpa token/cookie/credential.

Belum ada klaim E2E staging nyata, deployment, atau kesiapan live. SO/approval dan
Delivery/POD tetap tahap berikutnya setelah acceptance read staging selesai.
