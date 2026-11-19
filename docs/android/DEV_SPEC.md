# Spesifikasi Codex-Android-Dev

Acuan: [SSOT](ARCHITECTURE.md) dan [spec desain](DESIGN_SPEC.md). Tim dev memiliki implementasi Compose, data/domain Android, dan bukti tes. Lead mengoordinasikan perubahan kontrak Odoo/OpenAPI, DS bersama, dan workflow CI dengan maintainer terkait.

## Paket dan acceptance

| Paket | Pekerjaan | Acceptance dan bukti |
|---|---|---|
| DEV-01 / N2a | Uji runner dengan akselerasi emulator. Patok system image/API/ABI dan versi toolchain. Siapkan smoke API 24/35 untuk install, cold start, Login, navigasi layar awal dan izin yang relevan. | Kedua API boot dan menjalankan APK. Upload log boot/instrumentation dan screenshot tersanitasi pada SHA yang diuji. Mulai job opsional sampai waktu dan stabilitas terbukti, lalu ajukan perubahan gate melalui PR. |
| DEV-02 / N2b | Siapkan Odoo disposable, akun/assignment TEST, clock WITA dan konfigurasi URL/DB saat build. Buktikan sesi Odoo sementara, bootstrap, snapshot, expiry dan switch-account. Review auth/registrasi/qualification bersama backend. | Akun valid, 401/403, scope mismatch dan pemulihan diuji; laporan menunjukkan SHA Android/Odoo, seed, target dan cleanup. Catat OS/perangkat Redmi 4X/POCO M3 dan hasil GPS secara terpisah. |
| DEV-03 / N3 | Perkuat Room, media privat dan restart worker. Trace dependency dan receipt per owner. Uji retry, backoff, upgrade dan penyimpanan ketika proses berhenti. | Command dengan UUID tetap, 401 pertama menghentikan request berikutnya, login B tidak membuka item A, dan hanya receipt cocok memajukan status. Buktikan process death/reboot, retry tanpa duplikasi dan migration dengan data pending. |
| DEV-04 / N4 | Implementasikan D01 pada Compose. Gunakan CameraX setelah kompatibilitas diverifikasi, buat evidence dan command secara atomik, tampilkan status per receipt. | Permission revoke, retake, storage penuh, fix stale, mismatch evidence dan dependency hold tercakup. Evidence/check-in/out diuji pada backend disposable dengan bukti server. Absensi dan PJP kosong mengikuti capability B03/B04. |
| DEV-05 / N5+ | Buktikan SO resmi, lalu order v2, Delivery, kas dan HRIS sesuai register blocker. | Setiap operasi punya schema/golden payload, tes ACL dan effect server, serta layar unavailable bila capability belum tersedia. |

## Detail implementasi

- Gunakan `core/designsystem` untuk token/komponen dan fungsi Compose yang dapat diuji. Hubungkan ID D01 ke route dan tes. Android menangani state loading, empty, offline, expiry, retry, blocked, rejected, needs approval dan accepted.
- Validasi identitas dan business date snapshot terhadap bootstrap; pertahankan kompatibilitas data Room dan antrean yang sudah tersimpan. Pastikan WorkManager dan repository tetap memakai lease owner/generation yang sama. Uji counterexample PR #159 saat jalur sesi berubah.
- Kunci payload terhadap controller/tes Odoo dan versi shared schema. Akun, company, scope outlet, saldo, harga, approval dan status stok berasal dari keputusan server. Evidence punya checksum, provenance dan binding. State GPS display tidak mengesahkan aktivitas resmi.
- Untuk job emulator, periksa akselerasi sebelum menetapkan runner. Rekam emulator version, image, API, ABI, timeout, log alat, dan hasil per API. Gunakan target HTTP lokal terkontrol hanya untuk test yang berwenang dan pisahkan konfigurasi build resmi. Environment Android yang menulis transaksi memakai database disposable serta kredensial terisolasi.
- Pada PR, jalankan gate lokal, sertakan hasil planner, suite CI untuk exact SHA, daftar perubahan schema/token, dan evidence level yang relevan. Pertahankan guard OpenAPI, integritas sesi, dan required check. Tes yang gagal harus mempertahankan oracle yang mencerminkan invariant.

Integrasi dimulai setelah lead mengonfirmasi scope potongan dan base SHA. Dependensi eksternal yang belum siap dilaporkan dengan ID B, pemilik, acceptance, dan state UI yang ditahan.
