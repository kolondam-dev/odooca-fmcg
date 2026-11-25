# Register kontrak Android, Odoo dan database

Baseline sumber `origin/main 39172de`. Kebijakan terbaru dan gap approval dicatat di [BACKLOG_FE_BE](../ui/BACKLOG_FE_BE.md). Status di bawah berbasis source. Ketersediaan pada runtime dan database tertentu harus dibuktikan per SHA/target. Proposal kontrak dicatat bersama maintainer backend sebelum capability diaktifkan. Nama command baru tetap mengikuti keputusan kontrak bersama.

## Endpoint yang sudah ada

| Endpoint | Kontrak berjalan di source | Yang dibuktikan untuk Android |
|---|---|---|
| `POST /web/session/authenticate` | Android memakai RPC sesi Odoo melalui cookie jar. Bootstrap memberi CSRF untuk request yang memerlukannya. | Login disposable, expiry/revoke, identity mismatch, isolasi akun/tenant dan penyimpanan kredensial. Integrasi native auth final masih B01. |
| `GET /api/v1/me/bootstrap` | Identitas dan role berbasis sesi/assignment. Role driver masih ditentukan dari heuristik login/jabatan pada baseline. | ACL dan identity binding untuk dua akun, absence/capability, kesiapan role bertumpuk. |
| `GET /api/v1/sync/snapshot` | Katalog v2, scope/tanggal/versi, SKU/pack/stock/outlet, office opsional, `deliveries: []`. | Owner/company/day mismatch, perubahan assignment, PJP kosong sah, cache, recovery saat rollover. |
| `GET /api/v1/outlets/<outlet_id>/image` | Akses foto outlet scoped. | Audit cache per owner dan jalur offline/forbidden. |
| `POST /api/v1/evidence` dan `GET /api/v1/evidence/<client_uuid>/<variant>` | Multipart dengan sesi/CSRF, media privat, hash, watermark/source. | Binding owner, outlet, data capture, geofence, retake, ukuran/format, stale, ACL lintas akun dan idem. |
| `POST /api/v1/sync/commands` | Dispatcher dengan UUID/fingerprint, receipt dan allowlist enam tipe. | Verifikasi bentuk wire request/receipt terhadap Odoo disposable. Uji 401/403, payload berubah dengan UUID lama, repeat, capability dan dependency. |

Allowlist baseline: `sales.order.submit`, `sales.visit.check_in`, `sales.visit.check_out`, `delivery.pod.submit`, `delivery.trip.close`, `delivery.proof.submit`. Kesiapan handler diuji terpisah dari kesiapan read model, manifest, dan efek bisnis. Bandingkan `pwa/contracts/openapi.json` dengan controller dan test Odoo saat merancang integrasi.

## Blocker register dan ownership

| ID | Prioritas / pemilik area | Gap dan acceptance | Perilaku client sementara |
|---|---|---|---|
| B01 | P0 N2b · Mobile API + identitas | Native auth, expiry/revoke, multirole dan capability otoritatif. Sepakati owner/company per device/sesi, format error dan perpindahan akun. Tes expiry, revoke, 403, akun ganda dan scope berubah. | Adapter sesi Odoo untuk harness. Fitur yang membutuhkan role/capability khusus tetap ditahan. |
| B02 | P0 aktivasi resmi · Mobile API + device | Register perangkat, submit kalibrasi/integrity, qualification/requalification, retensi dan admin recovery. Uji Redmi 4X/POCO M3, pola unavailable/suspicious, korelasi dengan policy version. | Kalibrasi lokal diagnostik. Aktivasi resmi mengikuti keputusan server. |
| B03 | P0 N4 · Penugasan/AR | Penanda PJP kosong sah, jadwal/AR, jam rencana/format, carry-over opsi C dengan izin Supervisor dan audit, Extra call tanpa sesi PJP dengan approval Supervisor, dan NOO dengan approval Branch Manager. Buktikan user/company/day pada penugasan kosong/biasa, cache scope dan feed AR. | Beranda dan data yang diizinkan tetap tersedia untuk PJP kosong sah ketika marker disediakan. Sesi PJP terkunci pada default kosong. Scope carry-over memerlukan keputusan server. |
| B04 | P0 N4 · HRIS/absensi + Mobile API | Command absensi resmi, evidence kantor, receipt pembuka/penutup hari, kalender/hari Minggu, penolakan dan koreksi. | UI memakai state capability dan menandai bukti lokal. |
| B05 | P1 N5 Sales · Pricing/Sales | Order v2, diskon/program/budget, kredit/AR, revisi dan lineage, foto SKU/version, riwayat dan display stock. PR #170 mencatat Tier 0, persen diskon kumulatif termasuk program resmi, rantai berjenjang dan batas per principal; masih perlu permintaan approval otomatis, konfigurasi tier serta snapshot dari server. Aktifkan flag setelah kontrak dan tes pricing resmi serta reconciliation. | Jalur SO yang didukung saja, preview diberi status estimasi. |
| B06 | P1 N5 Delivery · Logistics | Manifest scoped DO/trip/item/assignment, tanda tangan bila disetujui, kebijakan partial/reject/pending, efek picking/return, settlement dan closing. Tes lintas driver/DO, bukti ulang dan saldo item. | Render manifest unavailable sesuai API. Handler POD tidak membuka aksi tanpa DO resmi yang sah. |
| B07 | P1 N5 Finance · AR/Cash/Accounting | Settlement multi-invoice, allocation dan saldo aktual, alasan/janji bayar, biaya/realisasi, setoran, biaya toko, efek payment/ledger. Tes concurrent allocation, split, 403, replay dan rekonsiliasi. | Flag server menentukan fitur kas. Data AR kosong dan nol dibedakan. |
| B08 | P2 N6 · HRIS/Payroll | Cuti/slip dan riwayat personal, ACL, publikasi dan retensi. Tes akses silang, version dan recovery. | Tampilkan capability unavailable atau akses ditolak. |
| B09 | P0 N2b · Lead + infra/backend | Target Odoo disposable dengan Android runner, fixture reproducible, HTTPS sesuai target, serta cleanup. Cek satu route login→snapshot dan satu command pada data disposable. | Selesaikan domain/UIs dan emulator smoke; acceptance resmi menunggu bukti target. |

P0 menghalangi penerimaan scope terkait, P1 diperlukan untuk ekspansi workflow inti dan P2 untuk tahap sesudahnya. Pemilik area di atas adalah jalur koordinasi, bukan nama orang yang sudah terkonfirmasi. Saat dependency diterima, catat issue/PR, PIC, versi schema, SHA Android dan Odoo yang kompatibel, run/fixture yang membuktikan, serta perubahan capability. Flag baseline OFF: `order_pricing_v2`, `collection_v2`, `field_expense_v2`, `cash_deposit_v1`, `outlet_expense_v1`.

## Matriks database dan fixture

| Target | Data dan operasi yang diizinkan | Bukti dan cleanup |
|---|---|---|
| Android JVM/Room | DB in-memory, HTTP lokal, owner A/B, cookie/CSRF dan request log sintetis. | Putus sesi, race, UUID/receipt dan migration. |
| Android emulator API 24/35 | DB aplikasi test dan fixture lokal terisolasi, endpoint runtime test bila tersedia. | Boot, install, wipe per job, log/screenshot tanpa data pribadi. |
| Odoo+Postgres disposable | Namespace/DB unik per run, addon revision jelas, dua akun internal terpisah, company kedua, kantor/outlet dan SKU/multi-UoM, route PJP dan kandidat kosong, hari WITA eksplisit, DO hanya saat model siap, saldo fixture. | Fixture yang sama dapat diulang, idempotensi dan scope dibuktikan, DB dan filestore disposable ditutup dan dibersihkan setelah run. |
| Railway demo persisten | Uji sesuai mandat pemilik dengan account/assignment TEST dan target terverifikasi. | Scope dan deployment SHA dikunci. Operasi write, reset, provisioning serta perubahan data mengikuti otorisasi pemilik secara terpisah. |
| Perangkat fisik | Build terikat SHA, data test, model/OS/API dan kondisi lingkungan dicatat. | Simpan hasil izin, kamera/GPS, kecepatan dan pemulihan. Bersihkan data pilot sesuai kebijakan yang disetujui. |
