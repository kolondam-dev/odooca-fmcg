# Spesifikasi Codex-Android-Dev

Acuan: [SSOT](ARCHITECTURE.md), [Design](DESIGN_SPEC.md), [Design System](DESIGN_SYSTEM.md), [register backend](BACKEND_REGISTER.md), dan [operasi integrasi](INTEGRATION.md). Tim Dev bertanggung jawab atas kode Android, instrumentation dan evidence. Lead mengoordinasikan kontrak Odoo, sumber token, dan CI bersama maintainer terkait.

## 1. Peta implementasi dan boundaries

| Area | Baseline | Perluasan |
|---|---|---|
| `app` | `MainActivity`, `AppNav`, layar Login, Home dan Calibration, collector lokasi/integritas. | Route dan state holder per workflow. UI render immutable state dan kirim intent. State lifecycle-aware dan pekerjaan sync durable. |
| `core/designsystem` | `Theme.kt`, `Tokens.kt` hasil generator, Material 3 light. | Alias semantik dan komponen DS-C01–C11 sesuai kebutuhan feature. Preview varian, semantics, screenshot dan mapping Figma. |
| `core/domain` | GPS qualification, evidence/geofence, state command dan planner antrean. | Pure rules untuk validasi format dan eligibility lokal; model bisnis resmi tetap di backend. Domain bebas framework, repository, transport dan Compose. |
| `core/data` | OkHttp, session gate, Room DAO, snapshot/visit/outbox repository dan WorkManager. | DTO/version mapping, kebijakan cache, Room migration, media lifecycle, jalur diagnostics, retry/reconciliation, tests repository. |
| Odoo/PWA/shared | `id_mobile_api`, schema OpenAPI draft dan sumber token PWA. | Perubahan kontrak/versioning lewat review dua pihak. Utamakan penambahan kompatibel, document schema delta dan uji backend. |

Gunakan ViewModel atau state holder yang mudah diuji, coroutine cancellation, navigasi dengan identifier minimum dan data scoped setiap resume. Hindari payload sensitif di route, saved instance state dan diagnostics. Pertahankan target SDK/Gradle yang dipatok sampai ada perubahan kompatibilitas dengan bukti.

## 2. Semantik data dan pemulihan

1. **Sesi.** Tautkan request ke account/company/generation. 401 menghentikan batch dan mengunci pengiriman hingga autentikasi kembali. 403 ditangani sesuai kode backend, termasuk scope dicabut. Pergantian akun tidak mengirim, menampilkan atau menghapus data akun asal. Gunakan counterexample integrasi PR #159 pada perubahan sesi dan worker.
2. **Snapshot.** Simpan secara atomik setelah validasi owner/company/gudang, versi, hari WITA dan scope dari bootstrap. Malformed atau mismatch mempertahankan snapshot lama hanya sesuai kebijakan cache dan ditandai statusnya. PJP kosong sah berbeda dari jaringan gagal dan data belum tersedia. Untuk opsi C, carry-over hanya diterima berdasarkan keputusan Supervisor yang dinyatakan dalam kontrak server. Desain kebijakan stale/rollover bersama backend sebelum aktivitas hari kerja resmi.
3. **Outbox.** Simpan command dan dependency evidence dalam transaksi Room. UUID dibuat per intent dan disimpan; retry mengirim payload yang ekuivalen. Audit concurrency worker/manual sync, process death di tengah request, duplicate tap, timeout dengan hasil server ambigu dan replay receipt. Jika perlu mengubah isi intent setelah penolakan, buat intent baru sesuai aturan koreksi.
4. **Failure mapping.** Network, timeout dan 5xx masuk retry dengan backoff/batas observabilitas. 429 menghormati jadwal retry server bila tersedia. 401 membuka pemulihan sesi akun asal. Konflik fingerprint, scope dan penolakan bisnis dipetakan dari respons aktual, disertai petunjuk atau status hold. Hanya receipt dengan identitas dan UUID yang cocok menutup command lokal. `needs_approval` tetap status resmi tersendiri.
5. **Evidence.** Simpan file di area privat dan metadata capture, fix, binding, hash serta owner. Upload mendahului command yang membutuhkannya. Audit storage limit dan cleanup setelah crash, logout, retensi serta status receipt. Pertahankan evidence pending dan lineage koreksi sesuai kebijakan. Verifikasi format/ukuran dari endpoint dan backend target sebelum mengunci kompresi.
6. **Migrasi dan privacy.** Uji upgrade Room dengan draf, evidence, outbox dan receipt existing. Retensi/cleanup diajukan sebagai keputusan. Artifak dan log hanya mencatat status, versi, error aman serta ID yang diizinkan. Token, koordinat presisi, foto, pelanggan dan payroll dikeluarkan dari bukti publik.

## 3. Paket implementasi yang dapat direview

| Paket | Scope dan counterexample | Exit dan dependency |
|---|---|---|
| DEV-01A Runner dan build | Buat spike GitHub Actions pakai API 24 dan 35. Cek akselerasi/ABI, pin image/SDK, boot dengan timeout, install dan cold start. | Dua API boot dan menjalankan APK, log runner/image dan failure artifact. Job opsional sampai runtime dan stabilitas disepakati. |
| DEV-01B Smoke UI | Compose instrumentation untuk Login, empty/error, navigasi awal dan izin. Tes launch vs resume, keyboard, rotasi/ukuran/font menurut DS. | Test IDs dan screenshot tersanitasi dengan SHA, API, ukuran dan font scale. Semantics tombol/label diuji. |
| DEV-02A Harness Odoo | Provision Odoo+Postgres disposable, addon/version, dua akun dan assignment, company, katalog, outlet, kantor, clock WITA yang deterministik. Jalankan jalur sukses, 401, 403, scope dicabut, rollover dan cleanup. | Bukti Android SHA, Odoo SHA, DB fixture/version, laporan request/receipt yang disanitasi, dan cleanup. B09. |
| DEV-02B Identity dan perangkat | Baca sistem OS/GPS pada Redmi 4X/POCO M3. Uji izin/expiry/logout, lock/unlock, GPS denied/stale/low accuracy, indoor/outdoor dan cold start. Susun adapter setelah native auth dan kebijakan registrasi disetujui. | Matriks fisik terisi, keputusan `minSdk` berdasar bukti. Login provisional dapat diuji pada harness. Aktivasi resmi menunggu B01/B02. |
| DEV-03A Outbox | Uji request sudah sampai server sebelum koneksi putus, beberapa item siap saat 401, worker overlap dan akun berganti. Perserialisasi work mengikuti owner/dependency dan aturan retry. | Domain, Room dan HTTP tests, ditambah reboot/process death pada emulator. Satu intent dan UUID menghasilkan satu efek server. |
| DEV-03B Storage | Uji atomic enqueue, media orphan, storage penuh, migrasi Room dengan antrean pending dan kebijakan retensi. | Upgrade dan recovery menyisakan draf serta receipt valid. Cleanup hanya untuk data yang memenuhi lifecycle. |
| DEV-04A Visit | Implementasi D01 dan komponen DS inti. CameraX setelah device check, izin, retake, fix/geofence, check-in/out, status antrean. | Receipt Odoo dari evidence dan kunjungan resmi sesuai scope; uji hash salah, evidence lintas outlet/akun, urutan dependency dan snapshot stale. |
| DEV-04B Hari kerja | Absensi, status server, sinkronisasi, PJP kosong dan Extra call/NOO sesuai capability. | Hari kerja dimulai sesuai receipt ketika kontrak aktif. Uji PJP kosong vs rusak, hari Minggu dan transisi hari. B03/B04. |
| DEV-05A Sales | SO dalam kontrak aktif, kemudian v2, diskon, approval, revisi, foto/katalog, display. | Uji konversi satuan, split per prinsipal, preview vs harga akhir, limit, koreksi dan replay. B05. |
| DEV-05B Delivery | Manifest DO/driver, detail, partial/reject, evidence POD dan closing. | Data manifest berasal dari server. Uji bukti salah DO, role, pending/replay, trip belum lengkap, serta efek fulfillment yang disepakati. B06. |
| DEV-05C Penagihan dan kas | AR jatuh tempo, alokasi receipt, alasan dan janji bayar, uang lapangan, biaya dan setoran. | ACL, transaksi atas saldo berubah, idempotensi dan rekonsiliasi payment/ledger. Capability bertahap. B07. |
| DEV-06 HRIS dan polish | Cuti/slip/history scoped, activity, penggunaan outdoor, aksesibilitas, performance device minimum. | Tes akses sendiri dan antar-akun, UX/performance matrix dan review Design. B08. |
| DEV-07 Rilis | Signing/distribusi, migration/rollback, monitoring, support dan pilot terbatas. | Artefak terlacak SHA, matriks target fisik, recovery scene, privasi dan kriteria penerimaan pilot. |

DEV-01A/01B dan desain D01 dapat berjalan paralel. DEV-03 dapat menambah tes data tanpa menunggu hasil desain. DEV-04A memakai versi frame yang diterima. Fitur resmi yang bergantung pada B01–B09 diangkat ke lead, disertai acceptance dan capability yang perlu dinyalakan.

## 4. Matriks verifikasi

| Level | Bukti wajib menurut scope | Batas bukti |
|---|---|---|
| Pure domain | Boundary kalender WITA, geofence/fix, eligibility dan reducer, lifecycle outbox dan OpenAPI samples. | Membuktikan logika dan payload. |
| JVM/Robolectric | Room DAO/migration, session lease, HTTP/CSRF/cookie, concurrency dan 401. | Membuktikan jalur repository dan interaksi JVM. |
| Instrumentation/emulator | Boot, lifecycle, Compose semantics, izin, process death, perubahan font/size dan screenshot. | Bukti OS virtual untuk API yang diuji. |
| Odoo disposable | Bootstrap, scope, device/evidence saat capability tersedia, command, receipt dan efek domain dengan record rules. | Bukti integrasi terhadap konfigurasi Odoo dan fixture yang tercatat. |
| Fisik | Redmi 4X/POCO M3, OS/RAM, kamera, GPS, thermal/memori, network berpindah serta latensi. | Bukti perangkat dan build yang dipakai. |
| Pilot | Acceptance pemilik, recovery real-world, rollback versi, telemetry yang disetujui. | Akun/perangkat/tenant dan scope dinyatakan. |

Terapkan data sintetis di harness. Catat nama suite, versi dependency, target, skenario, SHA, hasil, laporan, keterbatasan, dan dampak test untuk setiap PR. Untuk scope lokal gunakan `android/tools/integration_gate.sh`. Job Android yang ada menangani build/regresi. Device, Odoo dan pilot membutuhkan bukti tambahan pada potongan terkait.
