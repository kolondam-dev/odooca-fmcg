# Odoo FMCG Mobile — frontend-first

Implementasi awal client PWA untuk repo Odoo FMCG. Tidak mengubah backend, loader,
seed atau deployment Odoo. Paket hosting PWA terisolasi tersedia; belum dideploy. Seluruh fixture independen dari data/seed dan hanya masuk
build demo. Rujukan utama: [plan mobile](../docs/blueprints/mobile_api_and_pwa_plan.md).

## Menjalankan

Node.js 24 dan npm dengan package-lock committed:

```bash
cd pwa
npm ci
npm run dev
```

Buka `http://127.0.0.1:5173/field/`. Dev server adalah simulasi eksplisit.
Service worker/offline reload diuji pada build preview, bukan dev server:

```bash
npm run build:demo
npm run build
npm run preview -- --outDir dist/demo
```

Preview demo: `http://127.0.0.1:4173/field/`.
`npm run build` menghasilkan **dist/live**, yang saat ini terkunci sampai backend
resmi diterima. Tidak ada query parameter atau API-error fallback yang mengaktifkan
simulator pada live. Belum ada publikasi web, integrasi auth nyata atau deploy.

## Yang tersedia dan batasnya

| Area | Implementasi saat ini |
|---|---|
| Shell/UI | Preact + TypeScript + Vite, bottom nav responsif, Phosphor duotone SVG subset, Inter WOFF2 lokal, navy/blue tokens, reduced motion, haptic opsional |
| Persona | Sales, driver, canvasser dengan role bertumpuk; selector hanya demo, bukan login/auth/device binding |
| Sales | Outlet contoh, pemilihan principal, draft quantity yang dipulihkan, estimasi total, validasi satu principal, request extra call |
| Delivery | Manifest contoh, form POD dan capture bukti; official submit ditahan karena API evidence/map belum tersedia |
| Personal HRIS | Form absensi/cuti, akun sendiri per persona, slip ditandai belum terintegrasi; tidak meng-cache slip personal |
| Biaya | Request simulasi BBM/makan/nginap/darurat: schema ketat nominal/KM, referensi trip/DO, H-1 menurut tanggal bisnis bootstrap, narasi tier Supervisor/BM; tidak mencairkan uang atau menghitung limit resmi |
| Outbox | IndexedDB per identity, command UUID tetap, single-engine flush lock, retry/backoff, otomatis saat online/resume, 15s timer saat aktif, terminal 4xx/401 tertahan |
| Evidence | Foto terkompresi <=1 MB, koordinat/accuracy dan waktu lokal, Blob tersimpan per user, status map_pending; tidak mengklaim kamera asli/geofence sah |
| API draft | Zod DTO + OpenAPI generated, HTTP adapter tanpa fallback; belum diaktifkan sebagai aplikasi live |
| Offline shell | Manifest, icon SVG/PNG, asset precache hanya /field; tidak cache API; app update menunggu lifecycle service worker biasa tanpa memaksa reload input |

Ini menutup fondasi dan beberapa alur client PWA-01–04, **bukan seluruh roadmap**.
English/i18n penuh, tracking perjalanan, geofence workflow lengkap, sesi pagi resmi (simulasi tersedia),
settlement final, pembatalan transaksi belum terkonfirmasi dan integrasi media, server notification/approval, snapshot peta, recovery
session/device, backend receipt/record aktual dan E2E production masih pekerjaan
berikutnya. Jangan menilai status accepted simulator sebagai bukti Odoo menerima SO.

## Struktur

- `src/components`: icon wrapper dan evidence capture.
- `src/domain`: kontrak, validasi client, state outbox, format/geofence preview.
- `src/storage`: partition IndexedDB untuk draft/outbox/media/receipt simulator.
- `src/data`: HTTP provider dan lazy mock adapter yang dipisah saat build.
- `src/App.tsx`: shell, layar dan form client awal.
- `contracts/openapi.json`: kontrak client draft hasil Zod, bukan endpoint yang sudah ada.
- `scripts`: export/check kontrak dan budget/build boundary.
- `tests`: unit/contract/storage tests dan browser phone/tablet.

DTO bukan salinan model ORM. Contoh HTTP adapter saat ini mengirim satu command
ke `/api/v1/sync/commands` dan menerima satu receipt. Batch/dependency, identity
mapping, secure cookie/CSRF flow dan schema final harus direview bersama backend;
frontend tidak memaksakan protokol yang belum disepakati.

## Gate CI

```bash
npm run format:check
npm run typecheck
npm run contracts:check
npm test
npm run test:hosting
npm run build:demo
npm run build
npm run check:build
npx playwright install --with-deps chromium
npm run test:e2e
```

Workflow `.github/workflows/pwa.yml`:

- `pwa-quality`: reproducible npm ci, formatting, typecheck, schema drift, unit tests,
  demo/live builds, total JS gzip <=200 KiB, font <=100 KiB, scope dan fixture leakage.
- `pwa-browser`: phone/tablet, actual preview, offline reload dan reconnect, persona
  isolation, expense pending approval, missing evidence, live fail-closed, screenshot/trace.
- `pwa-container`: build image live/demo terisolasi dan smoke health/static/API.
- `pwa-gate`: always-run aggregator; gagal jika quality/browser/container gagal, dibatalkan atau skipped.

Tidak memakai path filter agar check wajib tidak menggantung pada PR non-PWA.
Workflow tidak merge/deploy, tidak memakai secret, dan tidak mengubah workflow Odoo.
Untuk enforcement merge, tambahkan `pwa-gate` ke required checks ruleset yang
berlaku setelah nama check muncul. Workflow hijau saja tidak membuktikan ruleset
sudah diperbarui. Perubahan ruleset tidak dilakukan dalam pekerjaan ini.

Browser fixture dipisah per context dan akun; tidak memakai password, akun Railway
atau data production. Cross-tab/server concurrency dan ACL harus diuji pada backend
aktual nanti. Browser cache/local data bisa dihapus OS/user; jangan simpan pending
berhari-hari atau menyebut browser storage sebagai backup server.

## Aset dan lisensi

Kode project mengikuti LGPL-3.0-only. Phosphor SVG: MIT; Inter: SIL OFL.
Salinan license tersedia pada `public/licenses`. Hanya glyph/ikon yang diperlukan
yang dikirim, tanpa CDN, font icon penuh, map SDK atau dependensi React untuk ikon.
Aset PNG merupakan rasterisasi icon.svg repo, bukan foto/gambar generatif.

## Hosting dan status biaya

Lihat [paket hosting Railway](hosting/README.md). Default container menyajikan
build live terkunci; simulasi harus dipilih eksplisit. Tidak membuat service,
mengubah routing Odoo, atau menyalakan aplikasi operasional.

Schema `ExpenseRequest` diekspor ke OpenAPI sebagai draft kontrak khusus biaya.
Validasi H-1 menggunakan tanggal bisnis bootstrap (termasuk batas bulan/tahun),
bukan jam browser. Tanggal bootstrap dapat kedaluwarsa saat aplikasi dibiarkan
terbuka: server wajib memeriksa ulang tanggal, cutoff, referensi/akses trip-DO,
limit rupiah, bukti odometer dan seluruh approval. Referensi pada simulasi masih
input manual; schema dan UI bukan bukti bahwa trip/DO benar-benar ada. Permintaan
tetap menunggu review simulator, bukan approved/disbursed. Foto masih lokal dan
map_pending; realisasi/settlement serta limit resmi belum diimplementasi.

## Sesi kerja pagi (simulasi)

Sales dan Canvasser harus menyelesaikan dua langkah pada kartu Sesi kerja pagi:
**Simulasikan absensi diterima** → **Sync pagi & buka sesi demo**. Kedua langkah
memerlukan koneksi dan respons simulator Normal. Driver tetap memakai alur Delivery.
Kontrol ini sengaja terpisah dari form foto absensi: tidak menjadikan foto lokal
map_pending sebagai absensi sah.

PJP, stok/harga, reference absensi, session UUID dan tanggal bisnis disimpan dalam
satu record IndexedDB per perusahaan/persona. Ready hanya muncul setelah write
berhasil. Paket harus lengkap dan bertanggal hari WITA yang sama. Order/extra call
baru ditahan bila sesi belum siap atau sudah berganti hari. Daftar outlet masih
bisa dilihat sebagai preview. Setelah sesi siap, paket yang sama dipulihkan saat
reload offline; peralihan persona tidak memakai sesi persona lain. Outbox yang
sudah dibuat hari sebelumnya tetap dikirim dengan UUID dan konteks asal.

Ini client simulator, bukan kontrol keamanan: jam lokal/storage dapat dimanipulasi,
provider demo bukan validator otorisasi, dan tidak ada identitas perangkat atau
server session. Backend nantinya wajib menerbitkan sesi, menentukan tanggal bisnis,
memverifikasi absensi/geofence/ACL dan snapshot authoritative. Command sales demo
menambahkan work_session_id, morning_business_date, snapshot_version sebagai draft
konteks client; tidak ada endpoint atau addon Odoo baru.

## Branding

Nama aplikasi **Odoo FMCG Mobile**, termasuk title browser, manifest dan layar live.
Logo horizontal mengikuti referensi pemilik: Odoo + badge FMCG, Mobile pada baris
kedua, latar navy kontras. Icon memakai glyph oi-odoo besar, label ODOO FMCG lalu
Mobile. SVG menggunakan outline (termasuk teks), bukan font eksternal. PNG 192/512,
apple-touch 180 dan favicon 32 tersedia. Sumber/atribusi: branding/UPSTREAM.md.
Ikon browser 16/32 px mengutamakan bentuk O; tulisan paling jelas pada icon instalasi.

Branding ini baru tersedia setelah merge dan deploy manual commit baru. Deployment
Railway yang dilaporkan pemilik tetap live terkunci pada baseline PR #20; pekerjaan
ini tidak mengubah service, mode build, domain atau kebijakan auto-deploy.

### Koreksi restore paket (review PR #21)

Sync, restore IndexedDB, dan guard readiness memakai validator semantik yang sama:
owner/tanggal bisnis, tanggal dan urutan absensi–pembukaan sesi, timestamp bukan
masa depan, versi snapshot nonblank, updatedAt valid/hari WITA yang sama/tidak
melewati pembukaan sesi, serta products/outlets nonempty. State absensi saja
(sessionId/openedAt/snapshot semuanya null) tetap valid sebagai tahap antara,
bukan sesi ready. Kombinasi sesi parsial ditolak.

Restore invalid menghasilkan sesi belum siap tanpa menghapus record, outbox atau
draft bisnis. Pengguna harus mengulang alur sesi pagi; command pending tetap
tersimpan dengan konteks asal. Regresi diuji melalui mutasi record IndexedDB
nyata pada unit dan corrupt bundle → browser reload offline → order/extra-call
terkunci, dengan isi draft/outbox sebelum-sesudah tetap sama.

## Realisasi dan estimasi settlement (simulasi)

Akses dari **Lainnya → Realisasi & saldo uang lapangan**. Buat pengajuan biaya
melalui form yang sudah ada, tunggu receipt Menunggu approval, lalu pilih pengajuan.
Tombol laboratorium **Simulasikan approval & pencairan** tersedia hanya pada demo,
online dan respons Normal. Penerimaan request tetap tidak berarti uang cair.
Policy fixture `SIM-EXPENSE-POLICY-1` menggunakan limit contoh Rp250.000; angka ini
bukan limit perusahaan, bukan rekomendasi policy dan tidak dikirim pada build live.
BBM insidentil selalu menampilkan Supervisor + Branch Manager. Routing preview
variance memakai max(advance, total realisasi), bukan hanya selisih kecil.

Form mendukung hingga 10 komponen non-BBM (uraian, rupiah bulat, penjual, nomor
struk, tanggal dan bukti per komponen), atau satu pengisian BBM per pengajuan.
BBM mencatat liter (maksimal tiga desimal), harga/liter, KM sebelum/sesudah,
foto struk serta dua foto odometer dengan referensi terpisah. Total BBM dihitung
melalui mililiter integer lalu dibulatkan ke rupiah; KM nondecreasing terhadap
pengajuan dan sebelum isi. Bukti harus berupa Blob lokal milik akun dengan
metadata yang cocok. Draft dan pratinjau bukti dipulihkan offline.

Estimasi menampilkan total, perlu pengembalian, dan perlu tambahan/variance. Tidak
menganggap refund diterima, top-up disetujui/dibayar, settlement selesai atau GL
terposting. Foto masih `local_map_pending`: **submit hanya ke simulator**, receipt
realisasi tetap membutuhkan review dan bukan penerimaan bukti resmi.

Command `field_expense.realization.submit` memakai payload strict yang menjadi
cabang khusus di CommandSchema/OpenAPI draft 0.3; tidak bisa memakai generic
payload fallback. Saat antre, payload dan referensi advance disimpan dalam satu
transaksi IndexedDB dengan compare-and-set. Dua koneksi/tab untuk advance sama
hanya bisa menghasilkan satu command. Retry mempertahankan UUID. Advance dibuat
create-if-absent agar kontrol demo tidak menimpa link realisasi yang sudah ada.
Restore dan submit memakai validator konteks yang sama (owner, request fingerprint,
amount, tier approval, timestamp dan link outbox). Perubahan material request
membutuhkan review ulang; data sumber/pending tidak dihapus otomatis.

Batas yang masih menunggu backend:

- Pengembalian uang, approval variance, pembayaran tambahan, final settlement dan
  posting. Pembatalan/koreksi transaksi queued/sending/auth_required/needs_approval
  dan penolakan transport tetap tertahan. Receipt penolakan bisnis yang valid dapat
  dikoreksi pada simulator dengan UUID baru dan link audit; versi lama tetap utuh.
- Secure identity/ACL, server-issued advance/revision dan policy bertanggal;
  fixture lokal bukan security boundary dan dapat dimanipulasi pengguna.
- Map snapshot, media upload/hash asli, verifikasi konten struk/OCR dan duplikasi
  server. Pemeriksaan lokal hanya referensi foto dan penjual/nomor/tanggal struk,
  bukan bukti foto berbeda atau anti-fraud global. Dedup struk lintas advance dalam
  satu owner/DB sekarang atomik; lintas akun, perangkat dan server tetap memerlukan
  unique constraint/validasi authority backend.
- Agregat limit per trip/periode, kapasitas BBM, multi-pengisian dan settlement
  multi-hari. Batas 10 komponen/Rp100 juta adalah batas input prototype, bukan limit
  approval bisnis.

Tidak mengubah backend/seed/deploy/Railway atau membuka build live. Fixture/test
foto memakai ikon aplikasi sebagai input tes, tanpa data operasional.

## Konsistensi bukti, race guards dan koreksi realisasi

Komponen biaya memiliki ID lokal stabil. Draft lama tanpa ID dimigrasikan saat
restore dan disimpan kembali; ID tidak masuk payload transaksi. EvidenceCapture
mengosongkan foto/preview/lokasi saat reference/owner berubah dari luar atau saat
file pengganti dipilih, lalu memuat Blob yang cocok. Lookup gagal tidak meninggalkan
foto lama; callback async lama diabaikan lewat generation guard dan Object URL
selalu dicabut. Pergantian file/lokasi dari dalam komponen tetap bisa diselesaikan
sebelum membuat evidence reference baru.

Saat submit, source request, advance CAS, predecessor (untuk koreksi), cek struk
owner yang sama dan insert outbox/link berada dalam satu transaksi read/write.
Cek struk memakai merchant/nomor yang trim + NFKC + uppercase serta tanggal.
Dua advance/tab pada owner dan database yang sama tidak bisa bersama-sama
menggunakan struk yang sama. Scan juga mencakup antrean legacy, tanpa migrasi DB.
Perubahan payload/status sumber selama await menolak commit tanpa orphan/link
baru. Penolakan HTTP/transport tetap menahan klaim struk; hanya receipt penolakan
bisnis yang valid dan cocok UUID yang melepaskannya. Ini local cooperative guard,
bukan security boundary, dedup lintas akun/perangkat, atau pengganti server unique.

Langkah dev berikutnya yang sudah tersedia adalah koreksi realisasi **ditolak
bisnis oleh simulator**. Form menampilkan pesan penolakan, alasan koreksi wajib,
serta riwayat. Payload baru memuat supersedes_uuid dan correction_reason; UUID lama,
receipt dan payload lama tidak diedit/dihapus. Kedua field opsional untuk kompatibilitas
payload lama, tetapi wajib berpasangan pada koreksi. State antre/sending/menunggu
approval/auth_required dan rejected tanpa receipt bisnis cocok tidak membuka edit.

Restore memvalidasi seluruh rantai revisi: source/advance/owner, urutan timestamp,
parent ditolak bisnis, missing reference dan siklus. Commit koreksi memeriksa ulang
predecessor atomik; status penolakan yang berubah selama submit membatalkan commit.
Dua koreksi serentak menghasilkan satu successor aktif. Retry tetap memakai UUID
koreksi yang sama, sedangkan koreksi berikutnya setelah penolakan baru membuat UUID
baru lagi. Settlement/uang/jurnal resmi masih menunggu backend dan live tetap terkunci.

## Kunjungan sales — simulasi lokal

Dari sesi pagi yang valid, pilih outlet PJP, ambil lokasi lalu mulai kunjungan.
Order memerlukan kunjungan aktif dan pengambilan lokasi baru ketika submit.
Check-out mengambil lokasi baru dan mencatat hasil; tanpa order, catatan minimal
5 karakter wajib. Satu outlet hanya satu kunjungan per hari WITA dalam simulator,
dan hanya satu kunjungan aktif pada hari yang sama. Kunjungan hari lama disimpan
sebagai histori, tidak otomatis ditutup atau menjadi izin transaksi hari baru.

Koordinat/radius 5–15 m berasal dari paket pagi fiktif. Fix maksimal 60 detik,
toleransi waktu masa depan 1 detik, dan jarak + akurasi harus <= radius. Di luar,
uncertain, stale, invalid atau izin GPS ditolak menahan transaksi; radius tidak
diperbesar. Browser tidak menjamin anti-mock GPS atau lokasi hardware terpercaya.
Belum ada peta pinpoint/foto kunjungan atau tracking latar belakang 5/15 menit.

Ledger dan command ditulis atomik dengan CAS, termasuk pemeriksaan ulang sesi
pagi dalam transaksi. Dua tab tidak dapat membuka kunjungan bersamaan atau
menutup kunjungan sambil melewatkan order yang baru tersimpan. Restore memeriksa
owner, konteks, timestamp dan referensi outbox tanpa menghapus data yang rusak.
Sinkronisasi mengurutkan check-in → order → check-out walaupun urutan UUID berbeda.
Order menunggu receipt check-in accepted; check-out menunggu receipt bisnis semua
order (accepted/needs_approval/rejected). Error transport bukan receipt bisnis.
Antrean tertahan tetap terlihat; tidak ada auto-cancel/recovery admin dalam scope ini.

OpenAPI draft 0.4 menambahkan DTO check-in/check-out strict dan VisitOrder. Legacy
sales.order.submit tetap kompatibel; jalur UI kunjungan menggunakan validasi payload
VisitOrder strict. Seluruh penerimaan, sesi, harga dan state di sini hanya simulator;
backend wajib mengecek ACL, device/session, idempotency, harga/approval, geofence,
waktu dan evidence sendiri. Tidak menambah endpoint Odoo atau deploy Railway.

### Koreksi review PR #24: validasi sebelum sync

Restore dan pengiriman kini berbagi validator semantik ledger yang sama. Sebelum
submit, outbox membaca satu snapshot IndexedDB (ledger, paket pagi dan seluruh
antrean owner), memeriksa envelope/owner/key, relasi visit/order/check-out, sumber
PJP/produk/sesi dan GPS pada waktu `occurred_at`. Pemeriksaan diulang sesudah
penandaan sending, tepat sebelum provider dipanggil. Receipt accepted lama tidak
mengesahkan parent atau konteks yang sudah rusak. Graf kunjungan invalid menahan
pengiriman visit milik owner tersebut secara konservatif; command/draft tetap
utuh, error meminta review, tanpa receipt bisnis palsu. Legacy command yang tidak
terikat visit tetap didukung, tetapi order yang dirujuk ledger tidak boleh
menghilangkan visit_context untuk melewati guard.

Kunjungan baru menyimpan salinan paket pagi historis pada ledger dalam transaksi
check-in. Replay tidak mewajibkan sesi hari ini: antrean sah dapat dikirim besok
meski paket pagi sudah diganti; GPS dinilai terhadap waktu aksi, bukan waktu sync.
Record lama tanpa salinan hanya memakai paket pagi tersimpan bila session/date/
version/site/openedAt masih cocok. Sumber hilang/tidak cocok ditahan untuk review,
tidak direkonstruksi atau dihapus otomatis. Penyimpanan sumber lokal ini tetap
bukan bukti otorisasi server atau perlindungan terhadap manipulasi seluruh DB.
