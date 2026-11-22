# Odooca Field (Android native)

Aplikasi lapangan Android native untuk Odooca FMCG. Terhubung langsung ke backend Odoo dan DB aktif.
Tidak ada jalur data pengganti: data, validasi, dan receipt selalu berasal dari server. Bila server atau
endpoint belum tersedia, aplikasi menampilkan status nyata (offline, ditolak, belum tersambung), bukan data lain.

Acuan arsitektur: `docs/blueprints/native_android_architecture_blueprint.md`.

## Struktur

| Modul | Isi | Verifikasi |
|---|---|---|
| `core/domain` | Kotlin murni: geofence, jendela waktu bukti, kualifikasi GPS, lifecycle command, perencana outbox, pembuat command check-in/out dan metadata evidence | Dikompilasi `-Werror`, **72 tes lolos**, payload **divalidasi terhadap skema OpenAPI** |
| `core/designsystem` | Tema Compose; `Tokens.kt` dihasilkan dari `pwa/design/tokens.json` | Generator zero-diff dan kompilasi Gradle lulus di CI |
| `core/data` | Klien Odoo (OkHttp), sesi terenkripsi Keystore, Room, repositori, WorkManager | KSP, kompilasi Gradle, dan tes Room/sesi (Robolectric) lulus di CI |
| `app` | Aktivitas, navigasi, layar Login, Beranda (outlet dari server), Kalibrasi GPS | Lint dan `assembleDebug` lulus di CI |

## Menjalankan

```
# alamat backend wajib diisi (tanpa garis miring di akhir)
./gradlew :app:assembleDebug -Podooca.baseUrl=https://<host-odoo> -Podooca.database=<nama-db>
./gradlew :core:domain:test
./gradlew :core:data:testDebugUnitTest
```

Gunakan JDK 17. Toolchain dipatok bersama: Gradle wrapper 9.9.1 (beserta checksum
distribusinya), AGP 9.5.1, Kotlin 2.4.21, KSP 2.3.14, dan `compileSdk = 37`.
Naikkan atau turunkan nilai itu sebagai satu kesatuan karena AGP mensyaratkan
Gradle minimum, sedangkan AndroidX/OkHttp mensyaratkan `compileSdk` minimum.
Jangan memakai instalasi Gradle global. Di Windows gunakan `gradlew.bat` dengan
argumen yang sama. Komponen SDK yang dipasang CI adalah
`platforms;android-37.0` dan `build-tools;36.0.0`; sejak API 37 paket platform
memakai versi minor sehingga `platforms;android-37` tidak tersedia.

## CI dan artifact

Workflow `.github/workflows/android.yml` menjalankan guard token desain dan
jalur data, 72 tes domain, validasi payload terhadap OpenAPI, tes Room/sesi
data-layer, lint, serta `assembleDebug`. APK debug, SHA-256, manifest ZIP, dan
laporan lint disimpan sebagai artifact `odooca-field-debug-<sha>`; laporan tes
data-layer disimpan sebagai `android-data-reports-<sha>`. Keduanya berlaku 14
hari. Emulator dan uji perangkat fisik belum menjadi bagian bootstrap N1 ini.

`minSdk = 24` adalah titik awal. Nilai final ditetapkan dari uji Redmi 4X dan POCO M3.

## Alur yang sudah ada

1. Login sesi Odoo (`/web/session/authenticate`), lalu `GET /api/v1/me/bootstrap`.
2. `GET /api/v1/sync/snapshot` disimpan ke Room; Beranda menampilkan outlet dari server.
3. Antrean pengiriman (`POST /api/v1/sync/commands`): UUID stabil, dependensi, backoff, 401 menghentikan antrean, receipt divalidasi.
4. Kalibrasi GPS perangkat memakai penilai domain (ambang berstatus hipotesis).
5. Check-in: `VisitRepository.queueCheckIn` memvalidasi (geofence, kesegaran fix dan foto, hash), lalu mengantre
   unggahan evidence (`POST /api/v1/evidence`, multipart) dan command check-in yang bergantung padanya dalam satu transaksi.
   `packageHash` memakai SHA-256 foto asli (server menerima `original_sha256`), sehingga check-in bisa disusun offline.

## Register hutang konektivitas

Backend dikerjakan paralel. Butir berikut dicatat sebagai hutang sambungan, bukan penghalang.

| Kebutuhan klien | Kondisi sekarang |
|---|---|
| Auth native (token, refresh, revoke) | Sementara memakai sesi Odoo; ganti saat endpoint tersedia |
| Registrasi perangkat | Belum ada endpoint |
| Kirim laporan kalibrasi GPS | Belum ada endpoint; laporan baru tampil di layar |
| Capability granular di bootstrap | Server baru mengirim dua capability |
| Verifikasi integritas aplikasi | Belum diintegrasikan; status `INTEGRITY_UNAVAILABLE` dilaporkan apa adanya |

## Verifikasi kontrak

`tools/validate_contract.py` memvalidasi payload yang dihasilkan tes domain terhadap `pwa/contracts/openapi.json`,
termasuk empat kontrol negatif schema (UUID rusak, radius di luar batas, `client_uuid` hilang, dan outlet
non-angka). Guard terpisah memastikan klien native tidak pernah mengirim field `mode`.

## Asumsi yang harus dibuktikan pada uji pertama ke backend nyata

- Server menghitung `original_sha256` dari byte foto yang diunggah apa adanya.
- Login sesi Odoo lewat `/web/session/authenticate` diterima dan `bootstrap` mengembalikan `csrfToken`.

## Pekerjaan klien berikutnya

Kamera (CameraX) dan layar check-in/check-out, order, display, delivery, penagihan, absensi, dan parsing snapshot
lengkap, mengikuti urutan dependency di blueprint.

## DEV-01A/01B — emulator opsional

Lead dapat menjalankan workflow **Android native** dari branch Dev yang memuat
definisi workflow. Set input `ref` ke SHA kandidat, `force_all=true`,
`emulator_smoke=true` dan `emulator_ui=false` untuk DEV-01A. Ulangi dengan
`emulator_ui=true` untuk DEV-01B. Jika GitHub menolak input baru dari branch
fitur, jalankan perintah lokal pada runner Linux ber-KVM. Required `android-gate`
terpisah dari hasil kedua job opsional. Perubahan workflow memilih full
regression berdasarkan planner. Lead mengumpulkan full regression dan Android
pada SHA yang sama.

Untuk runner lokal, siapkan Temurin 17.0.17+10 dan SDK Linux x86_64 terisolasi
dengan Command-line Tools 19.0, platform `android-37.0` rev 2, Build Tools 36.0.0,
Platform Tools 37.0.3, emulator 37.3.10, dan kedua image Google APIs x86_64
(API 24 rev 27, API 35 rev 9). Workflow memasang Platform Tools, emulator, dan
image dari arsip Google yang dipatok dan diperiksa checksum-nya. SDK Manager
memasang platform SDK dan Build Tools. Skrip berhenti saat revisi terpasang
berbeda dari pin.
Dengan `ANDROID_HOME` dan `ANDROID_SDK_ROOT` mengarah ke SDK tersebut dan
`/dev/kvm` bisa dibaca/ditulis, jalankan setiap API secara berurutan:

```bash
bash android/tools/emulator_smoke.sh 24 /tmp/odooca-api24-smoke smoke
bash android/tools/emulator_smoke.sh 35 /tmp/odooca-api35-smoke smoke
bash android/tools/emulator_smoke.sh 24 /tmp/odooca-api24-ui ui
bash android/tools/emulator_smoke.sh 35 /tmp/odooca-api35-ui ui
```

Pakai direktori bukti baru setiap run. Skrip membuat AVD bersih dengan timeout boot
300 detik. Laporan TSV mencatat SDK/image, SHA, checksum dan hasil akselerasi,
build, boot, install, cold start, Login dan instrumentation secara terpisah.
Versi Gradle dicatat dari wrapper repo yang dipatok pada 9.9.1.
Screenshot Login diambil pada AVD bersih sebelum kredensial diisi. Mode UI
menambah ukuran/font perangkat dan laporan test ID, waktu, dan hasil yang
disanitasi. Dump UI, stack trace, payload HTTP, dan log emulator mentah tidak
masuk artefak. Kegagalan setup runner tampak pada job Actions dan metadata SHA/API.

Mode UI memasang build debug khusus dengan endpoint fixture HTTP di
`127.0.0.1`, memakai `adb reverse`. Varian itu hanya diaktifkan melalui
`-Podooca.uiFixture=true`, dan kebijakan HTTP lokal hanya masuk debug khusus.
Skenario memeriksa form kosong, tombol/label, resume dan rekreasi Activity,
login ditolak/diterima, Beranda kosong, navigasi Kalibrasi, dialog izin OS
ditolak, kembali, dan keluar. Bukti untuk izin diberikan, lokasi perkiraan,
variasi font/ukuran dan rotasi fisik masih perlu dikumpulkan. Penerimaan
transaksi Odoo disposable dan perangkat Redmi 4X/POCO M3 menjadi uji tersendiri.
