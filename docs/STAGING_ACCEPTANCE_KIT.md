# Paket kesiapan staging GPS/foto dan preview check-in

Status: implementasi/paket persiapan; belum create environment, provision akun server, deploy, atau acceptance perangkat. Pekerjaan ini tidak mencatat check-in/absensi/POD resmi. Backend evidence tetap strict. Baseline PR43 yang sudah diterima dipertahankan.

## Lingkungan yang dipilih

[F] Pembacaan Railway menemukan proyek `pleasant-caring` (`569df00d-48e8-411a-93a5-df39ba97f16b`), hanya environment `production`, dengan Odoo/Postgres/field-pwa. Pemeriksaan platform bukan audit versi addon/data yang berjalan. Ada perubahan deployment production oleh proses lain selama sesi; agen ini tidak melakukan deploy.

[A] Siapkan environment `staging-remote` di proyek yang sama; akun/proyek Railway baru tidak diperlukan. Gunakan database dan volume baru, bukan sekadar mengganti nama environment atau menyalin koneksi production. Empat layanan:

| Layanan | Sumber/config | Data dan akses |
|---|---|---|
| Postgres | image Postgres yang telah disetujui operator | Volume baru; DB `fmcg_staging_remote`; koneksi private |
| Odoo | root Dockerfile; addon id_mobile_api 19.0.1.2.0 | Volume baru `/var/lib/odoo`; `INIT_MODULES=id_base,l10n_id,id_mobile_api`; proxy_mode=True |
| field-pwa | `pwa/Dockerfile`, explicit build arg `PWA_BUILD_MODE=staging` | Private port8080; verifikasi build-info mode staging; default live build tidak cukup |
| gateway | context `pwa`, Dockerfile `hosting/Dockerfile.railway-gateway` | Satu domain HTTPS publik, private upstream Odoo/PWA |

Gunakan reference variable database milik environment staging saja. Buat ODOO_DB_USER/ODOO_DB_PASSWORD, ADMIN_PASSWD dan ADMIN_LOGIN_PASSWORD khusus staging; jangan menyalin kredensial production. Inisialisasi mengikuti deploy/init.sh, bukan SQL langsung. `PGDATABASE=fmcg_staging_remote`; tidak ada SEED_URL atau RESET_DB production. Review dan batasi biaya/resource; resource tambahan bisa menambah penggunaan. Auto-deploy dinonaktifkan untuk pengujian terkontrol; pin SHA yang sudah disetujui.

Gateway memerlukan PORT, STAGING_HOST (hostname domain HTTPS tanpa scheme/port/path), ODOO_UPSTREAM dan FIELD_UPSTREAM (private DNS host:port, misalnya odooca-fmcg.railway.internal:8069 dan field-pwa.railway.internal:8080). Konfirmasi DNS sesuai service name pada environment baru, bukan mengasumsikan contoh benar. STAGING_HOST menjadi authority konstan; forwarded-host/proto tidak dipercaya dari klien. Railway edge HTTPS → private HTTP → gateway → Odoo proxy_mode. Unknown Host ditutup kecuali healthz; API bisnis tetap404. Origin publik harus sama untuk login, PWA dan upload. Set BASE_URL Odoo ke `https://<STAGING_HOST>` dan pastikan konfigurasi aktif benar. Healthz200 bukan bukti backend/login sudah siap.

Jangan berikan domain publik langsung ke Odoo/PWA staging jika gateway dimaksudkan sebagai satu-satunya pintu masuk. Simpan ID resource, domain dan SHA hasil deployment pada catatan sesi, tanpa secret. Pastikan volume, database, domain dan reference variable terpisah dari production sebelum menjalankan skrip provisioning.

## Master kantor dari server

Admin: Settings → Mobile Office Locations; isi company, nama, latitude/longitude, radius5–500m, status dan catatan sumber koordinat. Tetapkan Office Location pada Mobile Read Assignment hari itu. Default unverified; status verified adalah pernyataan admin, bukan hasil survei otomatis. Tidak ada koordinat kantor nyata yang diasumsikan dari nama cabang atau titik demo. Catatan sumber tidak dikirim ke PWA.

Snapshot optional `office` memuat id/nama/koordinat/radius/status dan ikut hash versi snapshot. Pengguna mobile hanya read; mutasi admin-only dan company isolation. Office inactive/invalid atau lintas company menyebabkan gagal baca; tidak ada fallback titik demo. Tanpa office, daftar outlet tetap tersedia dan UI menyatakan master kantor belum ditetapkan.

Preview staging menawarkan kantor atau outlet assignment, real browser GPS tanpa fallback, peta jalan opt-in serta label status master. Hanya memori tab; pergantian target/snapshot/clear/sesi menyingkirkan hasil lokasi lama. GPS preview tidak dikirim sebagai transaksi. Preview maps bukan bukti kehadiran; server upload evidence tetap memvalidasi assignment/outlet dan geofence sendiri.

## Provisioning akun demo disposable

Skrip: `scripts/ops/provision_mobile_staging.py`, dijalankan melalui Odoo shell setelah addon terinstal. Hanya menerima env superuser, opt-in YES, DB tepat sama dan prefix fmcg_staging_. Dua password berbeda minimal12 karakter diberikan operator melalui environment, tidak tertanam di git atau dicetak oleh skrip. Owner mengizinkan password dummy dibagikan untuk sesi demo; ini tidak berlaku bagi admin/database/Railway.

```bash
# Di shell service Odoo staging; isi password dummy terpisah melalui secret/environment operator.
export FMCG_STAGING_DISPOSABLE=YES
export FMCG_STAGING_DATABASE=fmcg_staging_remote
# FMCG_STAGING_PASSWORD_1 dan FMCG_STAGING_PASSWORD_2 harus sudah tersedia.
odoo shell -c /tmp/odoo.conf -d fmcg_staging_remote --no-http < /opt/scripts/ops/provision_mobile_staging.py
```

Root Dockerfile menyalin scripts ke /opt/scripts, sehingga path di atas tersedia pada image SHA ini. Pastikan image yang berjalan memang memuat versi tersebut. Library provisioning berada pada addon terinstal. Sebelum eksekusi, pastikan role database/shell dan config menunjuk staging. Panggilan guard tidak menjadi pengganti review resource isolation.

Hasilnya dua akun `staging.capture.1` dan `staging.capture.2` dengan company fixture baru, SKU/pricelist/warehouse fixture, kantor berstatus TEST, outlet berbeda dan assignment hari WITA. Tidak menulis canonical company/customer/SKU; tidak memberi write Sales/Stock/admin. Tidak membuat order, invoice, payment atau inventory posting. Stock snapshot dapat nol. Provisioning ulang memperbarui fixture yang dimilikinya dan password dummy, tidak mengambil alih login existing milik pihak lain; assignment per hari dipertahankan sebagai record berbeda. Jalankan kembali pada hari uji jika WITA berubah. Seluruh perubahan atomik sebelum commit; ringkasan scope/ID tidak memuat password.

Koordinat fixture kantor/outlet adalah placeholder Manado berlabel TEST. Master customer operasional tidak dipindahkan agar cocok dengan lokasi owner. Untuk uji dari jauh, preview/penolakan geofence strict dapat diuji nyata, sedangkan keberhasilan upload lokasi memerlukan lokasi di dalam radius atau sesi simulator demo terpisah. Paket ini tidak menambahkan bypass remote pada server evidence. Keputusan owner mengizinkan pengecualian remote tetap berlaku sebagai requirement, tetapi penerapan bypass server berlabel belum bagian paket ini.

## Uji perangkat bersama owner

Gunakan template `docs/STAGING_DEVICE_ACCEPTANCE.md`. Setelah deployment, agen/operator memeriksa HTTPS, cookie Secure/HttpOnly/SameSite, login dua akun, bootstrap/snapshot, master kantor, attribution/tile nyata dan upload/read privat. Baru bagikan URL gateway, nama akun dan password dummy sesi kepada owner. Pengujian UI browser fixture/CI bukan pengganti sesi ini.

Owner cukup menyediakan perangkat/browser yang akan dipakai dan mengizinkan kamera/lokasi saat diminta. Karena owner jauh dari kantor/outlet, jangan menandai geofence lapangan PASS. Titik kantor nyata baru boleh diberi verified setelah koordinat/radius/sumber dikonfirmasi; kantor TEST cukup untuk uji konfigurasi dan preview. Jangan mengunggah foto pribadi sensitif ke lingkungan disposable.

## Urutan rilis

Review PR dan CI → tetapkan SHA → instruksi deployment staging → resource terisolasi + HTTPS → instal/upgrade addon + provisioning → smoke Odoo nyata → bagikan akses dummy → sesi owner → catat hasil/gap. Tidak merge/deploy otomatis dari paket ini. Cleanup dilakukan terpisah setelah bukti hasil disimpan dan penghapusan resource disepakati; tidak menyentuh production.
