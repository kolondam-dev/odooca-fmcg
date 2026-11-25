# Rencana implementasi riwayat absensi PWA di Odoo

**Status:** rancangan untuk review · **Basis discovery:** `main` `f0b3632` · **Penanggung jawab:** ChatGPT-ABSENSI

[F] Temuan dari kode atau riwayat Git. [A] Usulan implementasi atau kebijakan yang perlu dikonfirmasi. [BU] Verifikasi runtime atau keputusan operasional masih terbuka.

## 1. Hasil yang dituju

HR membuka menu **Absensi** untuk melihat overview periode, rekap per karyawan, dan detail karyawan per tanggal. Target jam berasal dari jadwal kerja dan hari libur yang berlaku pada tanggal tersebut. Realisasi masuk dan pulang berasal dari absensi PWA yang diterima Odoo. Cuti, sakit, dan izin berasal dari Time Off. Koreksi jam dan pengajuan yang membutuhkan persetujuan memiliki jejak keputusan. Cakupan laporan awal adalah simulasi dan operasional HR.

## 2. Kondisi sekarang dan gap

| Area | Temuan [F] | Gap menuju penerimaan |
|---|---|---|
| Masuk/pulang PWA | `pwa/src/App.tsx` memakai `morningService.openDay()` dan `clockOut()` di `pwa/src/domain/morning.ts`. Catatan sesi dan referensi bukti disimpan lokal per pengguna, perusahaan, dan hari WITA. | Sesi lokal belum menghasilkan `hr.attendance`. Sinkronisasi perlu menjaga kesiapan kerja Sales/Delivery dan memisahkan status sesi lokal dari status posting HR. |
| API dan bukti | `id_mobile_api` memiliki kantor, assignment, bukti foto/GPS, dan log command idempoten. `SUPPORTED_COMMANDS` pada `models/mobile_command.py` belum menangani `hris.attendance.capture` atau `hris.leave.request` walau namanya ada di kontrak PWA. | Tambah handler, pengaitan karyawan, validasi bukti untuk konteks kantor, dan receipt yang dapat dicocokkan dengan record Odoo. Audit cakupan actor dan bukti yang sekarang terkait workday operasional. |
| HR native | `id_ui` memasang dependensi `hr_attendance` dan `hr_holidays` serta menata menu Absensi dan Cuti. | Belum ada penanda sumber PWA, laporan terpadu, cakupan historis, dan konfigurasi kalender khusus kebutuhan ini. |
| Time Off dan approval | Formulir PWA mendukung rentang tanggal dan alasan cuti tahunan. `id_approval` memiliki kategori `hr_leave_2line` dan callback target. | Belum ada adaptor `hr.leave`, mapping jenis cuti/sakit/izin, serta aturan transisi yang menyelaraskan approval dan Time Off. |
| Riwayat live | [BU] Tinjauan berbasis kode dan Git. Populasi data absensi, kalender, identitas karyawan, dan kemampuan pemulihan IndexedDB belum diverifikasi. | Inventarisasi read-only dengan akun berizin dan tetapkan tanggal awal cakupan per kelompok. |

Riwayat perubahan yang menjadi acuan:

- [#21](https://github.com/kolondam-dev/odooca-fmcg/pull/21) `b19240a` dan [#64](https://github.com/kolondam-dev/odooca-fmcg/pull/64) `6901d9e`: sesi lokal dan identitas Odoo.
- [#42](https://github.com/kolondam-dev/odooca-fmcg/pull/42) `fca1e0f`, [#70](https://github.com/kolondam-dev/odooca-fmcg/pull/70) `2c18174`, dan [#82](https://github.com/kolondam-dev/odooca-fmcg/pull/82) `a125b47`: bukti privat, operational readiness, dan pola integrasi live.
- [#76](https://github.com/kolondam-dev/odooca-fmcg/pull/76) `69149f6`: rollover WITA dan preservasi sesi tanpa mengarang jam pulang.
- [#130](https://github.com/kolondam-dev/odooca-fmcg/pull/130) `99ad910`, [#132](https://github.com/kolondam-dev/odooca-fmcg/pull/132) `6fe9f2c`, [#143](https://github.com/kolondam-dev/odooca-fmcg/pull/143) `14caec6`, dan [#160](https://github.com/kolondam-dev/odooca-fmcg/pull/160) `9502838`: formulir cuti, layar absen, status GPS, dan waktu kejadian.

## 3. Desain implementasi [A]

### 3.1 Sumber data dan posting PWA

- Tambah addon `id_attendance` versi `19.0.x`, LGPL-3. Pakai `hr.attendance`, `hr.leave` dan `resource.calendar` sebagai sumber. Tambah adaptor approval di addon ini saat milestone terkait. Definisikan dependensi manifest sesuai fitur yang dipakai pada tiap milestone. String kode English dan terjemahan Indonesia di `i18n/id.po`.
- Resolusi karyawan dari user Odoo aktif dan perusahaan sesi. Tolak pemetaan kosong atau ambigu dengan pesan operasional. Jangan terima pilihan employee/company dari payload sebagai otoritas. Uji akun HRIS yang tidak punya assignment penjualan.
- Kirim check-in/check-out melalui outbox dengan UUID stabil per event. Simpan waktu kejadian UTC dan waktu penerimaan server. Gunakan hari WITA untuk sesi pilot. Scope bukti ke actor, perusahaan, event, dan kantor yang sesuai. Terapkan kebijakan umur bukti dan offline di server. Simpan tautan ke bukti privat dan receipt.
- Receipt server membedakan menunggu sync, tercatat, dan perlu ditinjau. Check-out merujuk sesi yang sah. Replay identik mengembalikan receipt yang sama. Event ganda atau turutan salah pada dua perangkat tidak boleh membuat dua catatan aktif. Uji transaksi konkurensi, retry ketika respons hilang, rollover, dan pulang tanpa masuk.
- Tandai sumber PWA pada catatan yang diposting. Laporan mengambil catatan PWA dan koreksi yang terkait dengannya. Kiosk, input manual lepas, dan DEMO tetap dapat dikenali sebagai sumber terpisah. Data lokal lama hanya layak dipulihkan bila asal, waktu, kepemilikan, dan duplikasi bisa diperiksa. Jika tidak, tampilkan cakupan historis sebagai belum tersedia.

### 3.2 Kalender kerja dan hari libur

- **Absensi → Konfigurasi → Kalender Kerja & Hari Libur.** Gunakan interval kalender native Odoo untuk hari kerja, jam dan istirahat. Penugasan jadwal karyawan efektif per tanggal. Simpan versi atau riwayat penugasan agar perubahan jadwal dan mutasi tidak menggeser rekap periode lama. Tentukan representasi final setelah uji model native.
- Pilot memakai zona `Asia/Makassar` dan baseline 08.00–17.00. HR bisa mengatur Minggu, Sabtu, jadwal cabang, dan interval istirahat. Tanggal aktif kerja mengikuti masa penugasan karyawan. Konversi UTC ke zona kalender pada batas hari.
- Sediakan entri libur nasional, cuti bersama, libur daerah, dan libur internal. Simpan tanggal, label, kategori, perusahaan, cakupan cabang/lokasi, dan nomor atau tautan sumber. HR memasukkan data tahunan dari dokumen pemerintah Indonesia dan keputusan daerah/perusahaan yang berlaku. HR menetapkan penerapan cuti bersama. Verifikasi dokumen dan cakupan tahun sebelum memuat data pilot.
- Kurangi interval kerja dengan gabungan libur yang berlaku. Libur nasional dan lokal di tanggal sama dihitung sekali. Clock-in pada hari libur tetap dapat ditelusuri sebagai hadir pada hari libur dengan target nol. Informasi hari libur di detail menyebut sumber dan cakupannya.

### 3.3 Time Off, approval, dan koreksi

- Mapping jenis `hr.leave.type` ke cuti, sakit, dan izin melalui konfigurasi perusahaan. Ambil durasi dari irisan Time Off yang tervalidasi dan jadwal hari itu. Pengajuan pending terlihat terpisah. Simpan status ditolak dan dibatalkan untuk penelusuran.
- Alur cuti/izin yang dikonfigurasi memakai `hr_leave_2line` dengan Atasan Langsung lalu Branch Manager. Tetapkan satu jalur otorisasi untuk tiap jenis dan kebijakan Time Off. Adaptor mengikat request ke dokumen dan versi tanggal/jenis yang disetujui. Callback idempoten. Cegah jalur paralel yang bisa memvalidasi jenis terkelola sebelum persetujuan sah. Uji pengajuan ulang, perubahan sesudah approval, pembatalan, dan hak approver lintas perusahaan.
- Koreksi absen mencatat waktu lama/baru, alasan, referensi catatan PWA, pemohon, approver dan waktu keputusan. Terapkan perubahan setelah approval yang disyaratkan. Penutupan sesi lewat dugaan jam kerja menghasilkan angka yang tidak bisa diaudit, sehingga kasus tanpa jam pulang tetap terbuka sampai ditangani.

### 3.4 Mesin rekap dan tampilan

| Ukuran | Definisi usulan |
|---|---|
| Terjadwal | Jumlah menit interval kerja efektif setelah istirahat dan libur. |
| Durasi masuk–pulang | Jumlah interval catatan PWA yang lengkap. Interval tumpang tindih diperiksa agar menit tidak dihitung dua kali. |
| Jam tercatat dalam jadwal | Irisan interval absensi lengkap dengan interval kerja. Jam di luar jadwal ditampilkan terpisah. |
| Terlambat / pulang awal | Menit yang hilang pada batas awal/akhir jadwal yang wajib hadir setelah penyesuaian Time Off sah dan toleransi. |
| Cuti / sakit / izin | Menit izin sah dalam jadwal. Anomali jam hadir yang beririsan dengan izin ditandai dan tidak menggandakan menit pada agregat. |
| Alpa / belum lengkap | Alpa hanya pada hari kerja yang telah ditutup dalam cakupan data aktif dan tanpa bukti hadir atau alasan sah. Pending dan pasangan absen tidak lengkap terlihat tersendiri. Hari dengan izin parsial tetap punya sisa jadwal yang harus dievaluasi. |
| Tingkat kehadiran | Hari-karyawan hadir dibagi hari-karyawan yang wajib hadir. Hari tanpa kewajiban hadir dikeluarkan dari penyebut. Tampilkan pembilang, penyebut, dan kebijakan untuk hari parsial pada UI. |

Buat perhitungan per karyawan dan tanggal. Mulai dengan query periodik terbatasi dan agregasi server yang konsisten. Jika uji volume perlu materialisasi, pastikan koreksi absen, perubahan kalender, dan keputusan Time Off menghitung ulang tanggal terdampak. Bandingkan total overview dengan agregasi baris detail.

- **Overview** menampilkan hari terjadwal, hadir, menit dan kejadian terlambat, jam target dan realisasi, alpa, cuti, sakit, izin, pending dan data tidak lengkap.
- **Rekap karyawan** menyajikan ukuran yang sama, dengan filter periode, perusahaan, cabang/departemen, dan status. Mulai dengan list, pivot, dan graph Odoo.
- **Detail harian** menyajikan jadwal efektif, alasan libur, jam masuk/pulang, sumber, receipt, status validasi, pengajuan dan koreksi. HR memberi akses terpisah untuk foto, GPS, dan dokumen kesehatan. Agregat, klik ke detail, dan ekspor yang tersedia mengikuti record rule yang sama.
- **Contoh oracle:** masuk 08.17 dan pulang 16.40 dengan jadwal 08.00–17.00 dan istirahat 12.00–13.00 menghasilkan target 480 menit, realisasi dalam jadwal 443 menit, terlambat 17 menit, dan pulang awal 20 menit, dengan toleransi nol dan tanpa izin.

## 4. Milestone, slice, dan batas PR

Dokumen ini menjadi commit perencanaan pada `agen/absensi` dan dapat ikut PR 1. Rencana anggaran **tiga PR implementasi berurutan**, masing-masing dengan satu hasil yang bisa diuji. Slice di bawah adalah unit kerja dan verifikasi di dalam PR. Targetkan beberapa commit logis per PR dan rapikan commit percobaan lokal sebelum review. Buat cabang tahap berikutnya dari `origin/main` setelah tahap sebelumnya merge. Jika ada hambatan lintas tim, selesaikan desain dan fixture lokal sambil menunggu basis berikutnya.

| PR dan branch | Slice dalam PR | Exit criteria |
|---|---|---|
| **1. Posting absensi PWA** · `agen/absensi` | 1A addon, source marker, akses, pemetaan actor dan bukti. 1B handler masuk/pulang, receipt, idempotensi dan konkurensi. 1C outbox PWA, status sinkronisasi, kompatibilitas API lama, dan list native HR. | Satu pasangan masuk/pulang PWA tercatat pada karyawan yang tepat dan bisa ditelusuri di Odoo. Replays, dua perangkat, kegagalan bukti, serta beda perusahaan diuji. Pilot bisa diaktifkan terpisah dari demo dan pengguna lain. |
| **2. Kalender dan rekap dasar** · `agen/absensi-kalender-rekap` | 2A penugasan kalender efektif, jadwal, cakupan libur dan konfigurasi HR. 2B mesin periode dan status cakupan, memakai Time Off native yang sudah sah. 2C overview, list/pivot rekap dan drill-down. | Oracle 08.00–17.00 cocok, perubahan jadwal berlaku dari tanggal efektif, libur cabang dan libur bertumpuk benar. Selisih nol antara total agregat dan detail pada fixture, termasuk hari sebelum cakupan serta jam pulang kosong. |
| **3. Time Off PWA dan approval** · `agen/absensi-approval` | 3A bridge `hris.leave.request` dan mapping kategori. 3B approval/callback Time Off serta koreksi absensi. 3C detail status, rekalkulasi, dan acceptance pilot. | Dari pengajuan sampai persetujuan final, rekap berubah tepat sekali. Penolakan, pengajuan ulang, izin parsial, koreksi, dan ACL diuji. HR menyetujui sampel rekap dan prosedur penanganan pengecualian. |

Satu PR aktif untuk implementasi absensi. Perbaikan review masuk PR terkait. Pecah PR hanya jika ada unit yang perlu merge atau rollback mandiri dan memiliki kontrak serta bukti acceptance sendiri. Setiap PR berisi perubahan kode, migrasi bila perlu, penerjemahan, dan bukti uji untuk jalur yang disentuh.

## 5. Keputusan, blocker, dan pemilik

| Status | Butir | Dampak dan penyelesaian |
|---|---|---|
| [BU] Prasyarat pilot 1 | User pilot, pemetaan employee/company, assignment, kantor, grup, dan jenis bukti. | HR/admin Odoo memastikan fixture staging dan sampel perangkat. Dev bisa membangun dan menguji mekanisme dengan fixture disposable. |
| [BU] Kebijakan sebelum posting live | Batas waktu offline, keterlambatan upload dan clock skew, aturan geofence, kasus kerja di luar kantor, serta hak akses dan retensi foto/GPS. | HR dan pemilik menyepakati konfigurasi pilot. Dev memverifikasi penerapan di server dan status penanganan pengecualian. |
| [A] Kebijakan sebelum penerimaan PR 2 | Toleransi terlambat, jam istirahat, pola Sabtu/Minggu, batas penutupan alpa, hari parsial, cakupan cabang dan penerapan cuti bersama. | HR memberikan jadwal dan sumber kalender, menetapkan parameter simulasi, lalu menyetujui hasil contoh. |
| [BU] Histori existing | Cakupan per kelompok dan asal data lama. | HR/admin memeriksa read-only. Tetapkan tanggal awal yang bisa dibuktikan. Jika data lama lolos verifikasi, desain backfill idempoten dengan rekonsiliasi terpisah. |
| [BU] Prasyarat PR 3 | Kategori Time Off, atasan/approver cadangan, kebijakan sakit, dokumen pendukung, koreksi terlambat, dan cara menangani pengajuan lama. | HR dan pemilik memutuskan kebijakan. Dev memverifikasi benturan antara approval custom dan native pada DB staging. |
| [BU] Bukti rilis | Instal/upgrade Odoo, uji browser, perangkat nyata, volume rekap, dan penerimaan HR. | Jalankan gate pada SHA kandidat dan catat hasil. Aktivasi menunggu bukti tersebut dan keputusan pemilik. |

## 6. Verifikasi, rilis, dan rollback

- Ikuti [AGENT_PROTOCOL](../AGENT_PROTOCOL.md), [DEVELOPMENT](../DEVELOPMENT.md), dan [CI_SELECTION](../CI_SELECTION.md). Sinkronkan basis, tambah entri log dan HANDOFF, gunakan branch `agen/*` dan signature di baris terakhir. Untuk identitas baru gunakan `Task managed by ChatGPT-ABSENSI at <ISO8601 +07:00>`. Helper yang hanya mengenal alias lama dapat memakai `codex --since <ref>` untuk discovery.
- Jalankan `ruff check .`, `python scripts/check_manifests.py`, `git diff --check` dan impact planner sebelum review. PR 1 memerlukan Odoo install/upgrade, mobile provisioning dan PWA quality/browser/container sesuai planner. PR 2 memerlukan ORM/install/upgrade, uji UI/drill-down dan oracle agregasi. PR 3 memerlukan Odoo approval/Time Off, upgrade dan jalur browser PWA. Validasi pemetaan addon dan suite di `.ci/test-impact.yml`. Jika map perlu diubah, sertakan counterexample planner dan jalankan full regression sebagaimana aturan.
- Uji modul di DB kosong dan jalur persisted upgrade di DB disposable. Uji retry dan konkurensi pada integrasi ORM. Uji matriks pengguna HR, manajer, PWA, dan perusahaan kedua melalui UI serta RPC. Gunakan tes phone/tablet untuk outbox, online/offline dan respons gagal. Tambah uji baru pada invariant yang tidak tercakup oleh fixture existing. Catat hasil, oracle, trigger, waktu dan pemilik kegagalan per PR.
- Rilis berurutan di staging: pasang atau upgrade addon, konfigurasi cohort, aktifkan posting terbatas, rekonsiliasi receipt Odoo dengan perangkat, lalu aktifkan kalender/rekap dan pengajuan approval sesuai milestone. Pantau retry, reject, sesi tanpa pulang, selisih rekap dan antrian approval.
- Jika pilot dihentikan, nonaktifkan penerimaan command HRIS untuk cohort. Pertahankan catatan yang sudah diposting, receipt dan riwayat approval untuk rekonsiliasi. Perbaikan data memakai migrasi idempoten atau proses koreksi yang disetujui. Setelah pemulihan, replay outbox dengan UUID yang sama dan cek hasil rekonsiliasi sebelum melanjutkan.
