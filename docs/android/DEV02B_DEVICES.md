# DEV-02B · Sesi provisional dan matriks perangkat

Acuan `bb84709` dan arahan Lead `072e989`. Jalur sesi provisional memakai cookie Odoo dan scope dari bootstrap. Pengujian fisik memakai fixture disposable yang disetujui Lead dan APK yang sama untuk kedua model.

## Bukti fixture dan adapter

Jalankan dari commit bersih dengan image Docker Odoo repo dan PostgreSQL 16 yang tersedia.

```bash
bash android/tools/verify_dev02b_session.sh
```

Probe host memvalidasi TLS terhadap CA fixture B09, autentikasi dua akun, bootstrap dan isolasi snapshot, penolakan kredensial salah, pencabutan satu sesi melalui endpoint Odoo, HTTP 401 untuk cookie lama, sesi akun lain yang masih valid dan login ulang akun asal. Probe hanya membuka rute destroy pada gateway loopback disposable untuk run ini. Simulasi pencabutan memberikan sinyal 401 tanpa menunggu TTL alami.

Tes Robolectric memeriksa adapter Android dengan server loopback sintetis. Sesi disusun ulang dari storage, identitas/cookie/CSRF dan akses pemilik dibersihkan saat bootstrap mendapat 401, serta logout tetap bersih setelah adapter dibuat ulang dan tidak menghapus antrean. Tes lama tetap memeriksa batas batch 401, isolasi owner, dan UUID antrean. Build APK, hasil host HTTPS, hasil Robolectric dan hasil fisik dicatat terpisah.

## Inventaris perangkat fisik

| Perangkat | OS dan build/MIUI | Android API | ABI/RAM | GNSS dan mode izin |
| --- | --- | --- | --- | --- |
| Redmi 4X | [BU] Unit produksi belum terhubung | [BU] | [BU] | [BU] |
| POCO M3 M2010J19CG | Android 10, MIUI V12.0.7.0.QJFIDXM berdasarkan handoff Lead | 29 | [BU] | [BU] |

Jalankan pada perangkat yang ditetapkan operator. Catat SHA, varian APK, SHA-256, waktu WITA, kondisi jaringan, versi OS/MIUI, build incremental, API, ABI, dan RAM. Potong laporan bila ada serial, lokasi persis, identitas akun, cookie, token, atau kredensial.

```bash
git rev-parse HEAD
sha256sum "$APK"
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk
adb shell getprop ro.build.version.incremental
adb shell getprop ro.miui.ui.version.name
adb shell getprop ro.product.cpu.abilist
adb shell 'head -n 1 /proc/meminfo'
adb shell pm has-feature android.hardware.location.gps
```

## Matriks acceptance fisik

| Kasus | Prosedur dan bukti | Redmi 4X | POCO M3 |
| --- | --- | --- | --- |
| Install dan cold start bersih | Instal APK, paksa berhenti, jalankan dari launcher. Catat hasil install, layar Login yang benar-benar tampil, dan durasi start jika tersedia. | [BU] Ditunda sebelum full deploy | APK awal lulus, Login tampil dalam 4339 ms. APK fixture [BU]. |
| Cold start dengan sesi | Login akun TEST, seed snapshot, paksa berhenti lalu buka ulang. Catat hasil saat online dan offline, serta pemisahan cache dari hasil refresh. | [BU] | [BU] |
| Izin ditolak atau dicabut | Tolak prompt, ulangi setelah mencabut izin lewat Settings. Catat state denied dan cara pulih setelah izin diberikan. | [BU] | [BU] |
| Precise dan approximate | Beri izin presisi dan ukur state. Bila perangkat menawarkan approximate, ulangi pada mode itu dan catat dampaknya. Tandai tidak didukung jika opsi OS memang absen. | [BU] | [BU] |
| Outdoor | Ukur di ruang terbuka. Catat waktu ke fix, jumlah sampel, akurasi median/p90, umur fix dan state diagnostik. | [BU] | [BU] |
| Indoor / low accuracy | Ulangi pengukuran di dalam ruangan. Catat unavailable atau low accuracy bila terjadi dan verifikasi state diagnostik. | [BU] | [BU] |
| Stale | Ambil fix, hentikan pembaruan atau tunggu di luar jendela validasi, lalu ulangi aksi lokasi. Catat umur dan hasil aktual. Batas stale evidence saat ini lebih dari 60 detik. | [BU] | [BU] |
| Lock/unlock | Kunci layar ketika Home dan saat pengukuran. Buka lagi, catat recovery atau kebutuhan pengukuran ulang, permission, sesi dan keadaan Home. | [BU] | [BU] |
| Expiry dan login ulang | Lead/operator mencabut sesi TEST pada server fixture. Setelah refresh terlindungi, verifikasi 401 kembali ke Login, lalu login akun semula dan cocokkan scope/outbox. | [BU] | [BU] |
| Logout | Logout dari Home, kembali ke aplikasi setelah cold start, cek Login dan Back. Login akun TEST lain untuk memastikan antrean sebelumnya tidak berpindah pemilik. | [BU] | [BU] |

Catat [BU] jika kondisi yang diperlukan tidak muncul. Keputusan `minSdk` menunggu API aktual serta hasil install dan flow pada perangkat tertua yang disetujui Lead. Nilai build saat ini 24. Dukungan approximate bergantung pada OS dan perlu dikonfirmasi di perangkat.

## Dependensi Lead

- **B01** memerlukan keputusan native auth, TTL/revoke, identitas owner/company, perilaku perpindahan akun dan sumber capability. Logout adapter saat ini membersihkan sesi lokal. Probe server destroy hanya membuktikan penolakan sesi yang dicabut.
- **B02** memerlukan registrasi dan pemulihan perangkat, kebijakan penerimaan kalibrasi, sinyal integritas, serta qualification/requalification. Pengukuran di atas mencatat diagnostik lokal sambil menunggu keputusan itu.
- Lead perlu menetapkan operator, unit fisik, dan target HTTPS fixture yang bisa dijangkau perangkat. Mount gateway loopback CI berlaku untuk runner emulator. Untuk uji fisik yang memakai lokasi nyata, kumpulkan metrik kualitas dan state tanpa membagikan koordinat.

## Hasil checkpoint Cloud

Probe host lulus pada `f0c2172` dengan fixture `b09-dev02b-session-v1`, Odoo `19.0.20261112`, PostgreSQL `16.16`, `id_mobile_api` `19.0.1.4.0`, `id_base` `19.0.1.3.5` dan `id_approval` `19.0.1.0.0`.

| Kasus host HTTPS | Hasil |
| --- | --- |
| Tanpa sesi dan password salah | Bootstrap/snapshot tanpa sesi mengembalikan 401. Password salah ditolak. |
| Dua akun TEST | Login, bootstrap, dan snapshot lulus. Identitas dan outlet sesuai assignment masing-masing. |
| Pencabutan server | Cookie lama mendapat 401 pada bootstrap dan snapshot. Akun kedua tetap mendapat 200. |
| Login ulang | Akun asal kembali ke scope yang sama. |
| Cleanup | Gateway berhenti. Tersisa nol container, volume dan network fixture. |

Gate pada sumber yang sama lulus dengan 40 tes kontrak CI, 72 tes domain, 5 tes data/Robolectric, lint, build debug, dan validasi OpenAPI. SHA-256 APK debug lokal `320e008987a9817fd235fae776e53a4ff1f297b12b938d257c2e6e0d4d21f534`. Build ini memakai endpoint `https://ci.invalid` dan dicatat sebagai bukti build. Tes adapter memakai cipher sintetis dan belum membuktikan Keystore perangkat.

Bukti POCO M3 awal dicatat pada [handoff Lead f840da4](https://github.com/kolondam-dev/odooca-fmcg/blob/f840da4/docs/android/LOCAL_WORKFLOW.md). Bukti fisik fixture tetap [BU]. Gunakan [paket POCO M3](DEV02B_POCO_PACKAGE.md) saat transport disetujui. Cloud tidak menampilkan perangkat USB. ADB lokal berhenti saat akan membuat direktori `.android` di home yang hanya-baca. KVM juga tidak tersedia. Matriks menunggu unit Redmi 4X dan POCO M3, operator, build OS aktual, dan akses ke target fixture. TTL alami sesi masih [BU].

## Re-review checkpoint POCO M3

[Supervisor](https://github.com/kolondam-dev/odooca-fmcg/pull/207#pullrequestreview-6091929853) menerima bukti APK `5ab7088` pada POCO M3 Android 10/API 29: install/cold start, HTTPS/401, login/snapshot, Keystore dan isolasi outbox, pemulihan izin lokasi, GPS indoor/outdoor serta kelanjutan pengukuran setelah unlock. Laju sampling selama layar terkunci tidak diukur. **Dampak test CUKUP** untuk checkpoint ini.

Redmi 4X [BU] sampai validasi sebelum full deploy. `minSdk=24` sementara. Stale fix fisik [BU] di DEV-04A; expiry alami perangkat dan idle TTL server [BU] di B01. Cookie sekitar tujuh hari tidak membuktikan idle TTL.

Sinkronisasi main `8e83a301` mempertahankan tree Android, workflow Android, Mobile API dan OpenAPI dari APK yang diuji. Bukti perangkat tetap merujuk ke SHA APK `5ab7088`; CI dijalankan ulang pada kandidat integrasi.
