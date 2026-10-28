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
| Evidence | Foto <=1 MB dengan watermark waktu/koordinat, hash binding, pinpoint grid simulasi <=128 KB; paket per owner offline, map_pending resmi tetap; tidak mengklaim kamera asli/geofence sah |
| API draft | Zod DTO + OpenAPI generated, HTTP adapter tanpa fallback; belum diaktifkan sebagai aplikasi live |
| Offline shell | Manifest, icon SVG/PNG, asset precache hanya /field; tidak cache API; app update menunggu lifecycle service worker biasa tanpa memaksa reload input |

Ini menutup fondasi dan beberapa alur client PWA-01–04, **bukan seluruh roadmap**.
English/i18n penuh, tracking perjalanan, geofence workflow lengkap, sesi pagi resmi (simulasi tersedia),
settlement final, pembatalan transaksi belum terkonfirmasi dan integrasi media, server notification/approval, snapshot peta resmi, recovery
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
- Map snapshot resmi, media upload/hash server, verifikasi konten struk/OCR dan duplikasi
  server. Pemeriksaan lokal mencakup hash paket baru serta referensi foto/struk,
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
Foto check-in/check-out beserta pinpoint simulasi kini tersedia; peta resmi dan tracking latar belakang 5/15 menit belum tersedia.

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

## Pusat diagnosis sinkronisasi

Menu Lainnya → Aktivitas perangkat ini menyediakan filter Semua, Menunggu,
Perlu review, Approval dan Diterima. Buka Detail sinkronisasi untuk UUID lengkap,
waktu WITA, percobaan, jadwal retry, referensi receipt dan konteks/dependency
kunjungan. Filter/accordion hanya membaca data; tidak mengubah antrean, draft,
receipt atau UUID, dan tidak menjalankan submit. Tombol Sinkronkan existing
memakai engine yang sama; terminal rejection/auth_required tetap terkunci.

Diagnosis memisahkan offline/backoff/pengiriman belum terkonfirmasi, dependency,
source/graph visit invalid, auth, receipt approval, penolakan bisnis dan penolakan
transport. Receipt wajib cocok UUID/status. State historis accepted tetap terlihat
jika datanya kemudian rusak, tetapi ditandai Integritas perlu review; receipt lama
tidak menjadi izin mengirim ulang. Diterima simulator bukan approval/pencairan atau
posting Odoo. Validasi finansial/media/otorisasi resmi tetap dependency backend.

Snapshot ledger+morning+outbox dibaca atomik per refresh existing, tanpa request
jaringan/polling tambahan. Validator graf bersama hanya dievaluasi sekali untuk
satu proyeksi snapshot; sync tetap membuat validator baru di setiap boundary.
Detail membatasi field yang ditampilkan, tidak menampilkan payload mentah/blob
foto/token, tanpa fitur ekspor/hapus/edit/paksa kirim. Pesan receipt/error existing
masih ditampilkan sebagai teks. Owner terisolasi dan async result lama dibuang
saat komponen/persona berganti. Diagnosis berlaku pada snapshot terakhir yang
berhasil dibaca; tidak mengklaim status backend terkini atau fitur pemulihan admin.

## Paket bukti foto dan pinpoint simulasi

Komponen bukti bersama (realisasi struk/odometer, form pengajuan, absensi/POD lokal)
membuat foto JPEG ber-watermark waktu pencatatan perangkat WITA, koordinat dan
akurasi. Waktu pilih file dicatat terpisah; waktu shutter/kamera asli tidak terbukti.
Pinpoint PNG berupa grid lokal, skala meter, arah utara dan lingkar akurasi;
**SIMULASI TANPA BASEMAP**, bukan peta jalan atau snapshot peta resmi. Tidak ada
permintaan tile/API/provider, tracking atau pengiriman koordinat ke pihak ketiga.
Status `map_pending`/`local_map_pending` tetap berlaku; gate absensi/POD resmi
belum dibuka. Foto check-in/check-out sales menggunakan paket yang sama pada iterasi lanjutan di bawah.

Input JPEG/PNG/WebP maksimal 12 MB/40 MP, diperkecil maksimal sisi 1600 px sebelum
watermark (kanvas watermark minimal lebar 640 px, foto tidak diperbesar). Output
JPEG <=1 MB, pinpoint PNG <=128 KB. Pemilihan foto maksimal 5 menit sebelum save;
fix GPS maksimal 60 detik, future tolerance 1 detik, accuracy >0 dan <=10 km.
Ini validasi input bukti, bukan geofence atau jaminan lokasi sah.

Satu record evidence berisi foto + snapshot + metadata + SHA-256 keduanya dan
binding owner/key/koordinat/waktu. PackageHash opsional ditambahkan pada ref di
OpenAPI draft 0.5; payload lama tetap valid. Paket baru immutable melalui store API,
perubahan membuat ID bukti baru. Save gagal tidak meninggalkan record parsial;
restore, submit realisasi dan send/retry memeriksa ulang hash/ref/owner/binding.
Saat sync, kegagalan paket menahan command tanpa receipt bisnis palsu; anotasi
lokal `evidenceHold` menempatkannya pada Perlu review di diagnosis. Anotasi berasal
dari pemeriksaan sync terakhir, bukan pemeriksaan hash baru saat membuka diagnosis.

Validasi waktu paket historis mengikuti capturedAt, bukan hari sync; bukti sah
bisa direplay esok hari. Ref legacy tanpa hash hanya memakai pemeriksaan metadata/
keberadaan Blob lama dan diberi label belum memiliki paket baru. Tidak ada migrasi
otomatis atau rekonstruksi paket hilang. Foto yang dipulihkan tidak menjadi sumber
foto baru; pilih file lagi untuk mengganti bukti. Hash lokal mendeteksi perubahan
biasa, tidak mencegah pemalsuan seluruh DB/rehash, titip akun, mock GPS atau kamera
palsu. Server-authoritative media, maps berlisensi, signing/ACL, retention/GC,
malware/OCR dan dedup konten lintas perangkat tetap dependency backend/native.


## Foto check-in/check-out kunjungan sales

Kunjungan baru wajib paket foto berbeda untuk setiap aksi. Pilih outlet PJP dari
sesi pagi, ambil lokasi outlet, simpan foto check-in beserta GPS, lalu mulai
kunjungan. Sebelum menutup, simpan foto check-out baru dan isi hasil/catatan.
Foto dan lokasi asal paket harus masih segar (maksimal 60 detik) pada waktu aksi;
jarak+accuracy harus <= radius outlet. Foto check-in tidak boleh mendahului sesi,
foto check-out tidak boleh mendahului check-in. Tidak ada toleransi radius tambahan.

Ref harus memiliki packageHash, owner cocok, foto/map/hash valid. Ref disalin ke
command dan ledger secara atomik melalui CAS; satu ID foto hanya untuk satu aksi
di ledger owner. Pergantian draft tidak mengubah ref pada transaksi yang sudah
antre. Slot draft dipisah owner/sesi/outlet/fase/visit ID; reload offline memulihkan
paket yang belum dikirim. Tombol aksi baru aktif setelah slot berhasil tersimpan;
foto kedaluwarsa harus diganti. Riwayat foto tersimpan dibuka read-only.

Restore memeriksa semantik dan hash seluruh sumber visit yang dibaca. Sebelum
sync, media pada graf kunjungan terkait diperiksa termasuk parent ber-receipt
accepted. Parent rusak menahan child tanpa membuat receipt palsu: parent bisa
Perlu review sementara child tetap Menunggu dependency. Pengecekan graf/sesi
sebelum provider tetap dilakukan setelah await hash. Foto historis dinilai pada
waktu aksi, sehingga replay sah esok hari tetap berjalan.

OpenAPI draft 0.6 menambah pasangan evidence_version=1 + evidence pada check-in/
check-out. Keduanya opsional hanya untuk membaca/replay riwayat tanpa foto dari
versi lama. Commit kunjungan baru tetap wajib foto di service dan validator atomik;
jalur legacy DTO bukan izin membuat aksi baru tanpa bukti. Tidak ada auto-migrasi
atau pengisian bukti lama secara sintetis. Tes lama memakai fixture foto eksplisit
untuk mempertahankan regresi geo/sesi pada jalur baru; replay legacy dites terpisah.

Foto berasal dari paket generik PR #26; hubungan visit/outlet/session/phase dicatat
pada ledger/command dan slot draft, bukan tanda tangan server di dalam foto.
Peta tetap grid pinpoint simulasi tanpa basemap. Tidak membuktikan kamera asli,
anti-mock GPS atau anti-titip; koordinasi manipulasi seluruh DB tetap di luar
integritas client. Otorisasi, binding perangkat, media/maps resmi, recovery visit
tertahan dan retention/GC masih dependency backend/native. Live tetap terkunci.


### POD simulator (main setelah PR #27)

Delivery memuat manifest contoh per petugas/hari dan menyimpannya offline.
Buka DO, isi penerima, kuantitas diterima per item, hasil penuh/sebagian/ditolak
serta alasan selisih. Foto/pinpoint simulasi wajib, GPS di geofence dan <=60 detik
saat pengajuan. Tombol **Simpan draft POD** menyimpan form+referensi foto;
pengisian form belum autosave. Setelah diajukan, data/foto menjadi read-only;
status receipt terbaru ada di Lainnya. Pengajuan normal selalu membutuhkan review.

Command baru `delivery.pod.submit` mempunyai DTO strict dan snapshot sumber
owner/DO/trip/outlet/versi/hari/item. `delivery.proof.submit` lama tidak ditafsirkan
ulang. CAS ledger+queue serta reservasi DO/foto atomik mencegah pengajuan ganda
antar tab dalam IndexedDB owner yang sama. Restore dan sebelum submit memvalidasi
manifest tersimpan, command, geofence saat kejadian, foto dan hash. Replay besok
memakai waktu kejadian, bukan izin membuat POD hari lama. Data rusak ditahan untuk
review, tanpa hapus/paksa-kirim/recovery otomatis.

Fixture satu item/DO bukan manifest stok/lot nyata. Tidak menyelesaikan picking,
retur, collection, closing trip atau approval resmi. Koreksi POD hanya dibuka untuk penolakan bisnis dengan receipt UUID cocok;
lihat alur koreksi di bawah. Manifest immutable contoh belum
memiliki refresh/reassignment/revocation server. Hash/local storage bukan batas
keamanan; media/maps resmi, auth/session/device/ACL dan dedup server tetap wajib
sebelum live. Live tetap terkunci.


### Koreksi POD simulator (lanjutan PR #28)

Tombol **Koreksi POD ditolak** hanya muncul untuk penolakan bisnis dengan receipt
yang cocok. Perbaiki data, isi alasan koreksi dan ambil foto baru di geofence.
Simpan draft secara eksplisit; draft koreksi terpisah per parent dan pulih offline.
Pengajuan memakai UUID baru dan `supersedes_uuid`/`correction_reason`, tidak
menimpa parent atau receipt. Histori data tetap read-only; receipt child normal
masih needs_approval. Kegagalan transport, receipt salah UUID, queued, accepted
dan needs_approval tidak membuka koreksi.

CAS pointer command dan snapshot parent/receipt dicek di transaksi IndexedDB
yang sama. Satu parent hanya boleh memiliki satu successor; foto tidak boleh
dipakai ulang, manifest harus identik. Restore dan sync memvalidasi seluruh
lineage serta media ancestor, memeriksa ulang perubahan setelah await.
Koreksi pada hari manifest saja; antrean koreksi sah tetap dapat replay hari
berikutnya, tetapi koreksi baru lintas hari/reassignment menunggu policy backend.
Receipt/media hilang atau rusak tetap perlu review tanpa hapus/rekonstruksi
otomatis. Maps/auth/device/server authority, collection, closing, retur dan posting
Odoo tetap belum terintegrasi; build live terkunci.


### Collection simulator (setelah PR #28/#29 merged)

Menu Delivery memuat bagian **Penerimaan uang · simulasi** hanya bagi persona
dengan capability contoh `collection.capture` (Driver/Canvasser), terpisah dari
role delivery. Penugasan tagihan contoh mengikat DO/trip/outlet/owner/hari/versi,
saldo Rupiah dan waktu snapshot. Ini bukan invoice/saldo piutang resmi.

Isi pembayar, tunai atau bukti transfer, nominal Rupiah bulat tanpa separator,
nomor tanda terima dan catatan; transfer wajib referensi. Nominal positif maksimal
saldo contoh, foto watermark/pinpoint wajib dengan GPS di geofence dan TTL60s
saat pengajuan. **Simpan draft collection** menyimpan form+referensi foto secara
eksplisit; belum autosave. Form hanya dapat disimpan jika field wajib lengkap.
Reload offline memulihkan draft; setelah antre, data/bukti read-only dan receipt
normal needs_approval. Status terbaru di Lainnya. Saldo contoh tidak dikurangi
dan tidak ada klaim pembayaran posted, uang sudah diterima kasir atau AR lunas.

Satu tagihan satu pencatatan (boleh nominal sebagian). CAS source+ledger+queue
serta dedup tagihan/nomor tanda terima/ref transfer/foto atomik lintas tab dan
koneksi dalam satu owner/IndexedDB. Normalisasi referensi mengabaikan case,
spasi dan separator umum secara konservatif. Klaim tidak dilepas setelah
transport maupun penolakan bisnis; cancel/cicilan lanjutan belum tersedia.
Koreksi setelah penolakan bisnis memakai alur di bawah.
Draft/queue/Blob tetap utuh saat integritas gagal. Restore dan pre-sync membaca
snapshot ledger+source+outbox konsisten lalu memeriksa ulang sesudah hashing.
Pengajuan baru harus hari penugasan, replay antrean sah boleh hari berikutnya.
Tagihan yang pernah dicatat dengan source berbeda terkunci untuk review.

Kontrak `collection.receipt.submit` draft0.9 belum endpoint Odoo. Penugasan
collection tidak mengambil izin dari receipt POD. Authority capability/session/
device/idempotency/saldo dan dedup lintas user/perangkat tetap harus di server;
hash client bukan anti-mock GPS/anti-titip atau bukti dua foto berbeda. Peta masih
pinpoint simulasi, belum peta resmi. Bank verification, multi-invoice allocation,
closing/settlement kasir, collection koreksi dan posting account.payment belum
diimplementasikan. Live tetap terkunci, backend/Railway tidak diubah.


### Koreksi collection ditolak
Receipt rejected cocok UUID membuka **Koreksi collection ditolak**. UUID baru,
alasan dan foto baru wajib; source tagihan identik. Draft manual per parent
pulih offline. Parent/receipt tetap utuh di Lainnya, hasil/bukti readonly.
CAS pointer dan snapshot receipt atomik mencegah fork antar tab; hanya ujung
lineage rejected dapat dikoreksi. Queued/approval/accepted/transport error tidak
membuka edit. Restore dan sync memvalidasi seluruh ancestor dan media, lalu
recheck setelah hashing. Referensi/tanda terima boleh sama dalam lineage, tetapi
semua klaim ancestor tetap reserved terhadap tagihan lain. Foto tidak boleh
dipakai ulang. Same-day capture/historical replay tetap berlaku. Tidak ada
auto-recovery/cancel, bank verification, AR/payment posting; live terkunci.

## Rules SO dan Delivery — iterasi 2026-10-28

Acuan requirement: blueprint mobile §17 dan SCOPE §14. List Sales maupun Delivery
terkunci sebelum absensi simulasi + daily sync berhasil. Driver kini menggunakan
sesi pagi juga; daily sync menyimpan manifest bersama snapshot. Paket legacy
Canvasser tanpa manifest harus sync ulang; draft/outbox lama tidak dihapus.

SO demo: pilih SKU, qty dan satuan karton (144 pcs), pack (12 pcs) atau pcs.
Harga yang ditampilkan adalah harga karton; estimasi dinormalisasi ke pcs lalu
Rupiah dibulatkan pada total. Diskon demo adalah persentase integer 1–100% untuk
seluruh order, dengan alasan; tidak ada limit approver atau promo resmi yang
dianggap sudah disepakati. Normal menghasilkan needs_approval. Di **Lainnya →
Simulator approval diskon**, isi alasan lalu setujui/tolak pengajuan pending.
Persetujuan demo menerima seluruh persen diminta; penolakan bukan penerimaan SO
pada harga tanpa diskon. Command tetap immutable, receipt/keputusan lokal berubah
secara CAS sekali saja dan menampilkan persen/total yang disetujui. Ini bukan
hak approval sales atau approval/posting Odoo. Simulasi tier approval berjenjang,
diskon per baris/berlapis/promo dan harga aktual tetap pekerjaan lanjutan.

Delivery baru memakai manifest v2 multi-SKU dalam satuan dasar pcs. Pilih DO dari
list, simpan foto toko, **Set pinpoint delivery**, lalu **Mulai sesi delivery**.
Opening tersimpan offline dan satu owner hanya dapat mempunyai satu sesi delivery
aktif dalam IndexedDB yang sama. Proses intra sesi mencatat penerima, hasil dan
qty per SKU. Fully Received, Rejected, Cancel Delivery, Pending Requested wajib
alasan sekali yang disalin ke seluruh baris. Received Partial wajib alasan pada
setiap baris yang diterima sebagian/ditolak. Cancel/pending tidak berarti Odoo
membatalkan picking atau menyetujui penundaan. Foto closing serah-terima
barang/faktur/uang wajib berbeda ID dari opening. **Ajukan POD untuk review**
menyimpan closing dan antrean atomik; summary berubah menjadi Session closed.
Pilih DO berikutnya untuk mengulang. Simpan draft secara eksplisit sebelum pindah
layar; input yang belum disimpan dapat hilang. Foto kedaluwarsa harus diganti.

Sales memakai sesi kunjungan existing: foto toko → set lokasi/pinpoint → mulai →
order → foto closing serah-terima/ttd nota manual atau faktur/uang → tutup. List
menampilkan sesi yang closed, terpisah dari status sync/approval. Closing lokal
bukan bukti transaksi sudah diterima server. Geofence tetap berdasarkan koordinat
penugasan; set pinpoint tidak menggeser radius/koordinat toko untuk meluluskan GPS.
Waktu aksi set pinpoint dicatat terpisah dari timestamp sampel GPS.

Kontrak draft0.11 additive: pricing_version/discount_request dan UoM pada VisitOrder;
workflow_version=2 pada manifest; status, alasan baris dan paket session opening
pada POD. V2 wajib sesi, status, alasan dan media; riwayat POD/order lama tetap
terbaca tanpa migrasi atau rewrite. Closing/koreksi baru tetap same-day; replay
antrean yang sah dapat lintas hari. Sesi aktif yang tertinggal lintas hari atau
rusak ditahan untuk review, belum ada recovery/pembatalan otomatis. Bukti opening,
closing dan seluruh ancestor koreksi diperiksa sebelum sync. Live tetap terkunci;
media/maps/auth/device/authority server dan posting stok/retur/AR belum tersedia.


### Follow-up review PR33 (c48bf5a)

Delivery pertama kali dapat dibuka offline dari manifest yang sudah diterima daily
sync, meskipun cache list belum pernah dibuat. Materialisasi lokal memvalidasi
owner/hari/keunikan; cache berbeda/rusak ditahan, tidak ditimpa. Pembukaan list
ini tidak meminta ulang manifest ke provider. Collection mempunyai cache sumber
terpisah; status belum tersedianya tagihan offline bukan kegagalan list POD.

Riwayat koreksi menampilkan setiap nama SKU, received dan unit source command
historisnya (pcs pada manifest baru; karton tetap karton pada legacy).
Helper browser menunggu completion absensi/tombol sync enabled serta owner dan
restore persona tujuan. Regresi browser menahan completion IndexedDB dan restore
secara deterministik; tanpa sleep, timeout lebih panjang, pengurangan worker atau
skip. 239 unit +1 hosting +84 browser resmi145.0.7632.6 lokal lulus (64 lama+20
regresi); hasil remote pada SHA perbaikan dicatat di PR setelah publikasi.


## Revisi SO, pending/cancel dan closing kantor — mandat 2026-10-28

Rules terbaru ada di plan §18 dan SCOPE §15, menggantikan batas demo sebelumnya.
Di Lainnya → Koreksi Sales Order, buka pengajuan dengan penolakan bisnis/receipt
UUID cocok lalu pilih Koreksi SO ditolak. Edit SKU/satuan/qty/diskon/catatan dan
alasan koreksi; simpan draft eksplisit untuk reload offline. Revisi memakai UUID
baru dan parent/root tetap immutable; satu successor per parent, termasuk dua tab.
Outlet/principal tetap sama; harga/estimasi memakai daily snapshot saat revisi.
Koreksi administratif boleh setelah sesi toko closed atau lintas hari dengan
daily sync hari berjalan, tanpa membuka ulang sesi lama. Draft per parent dapat
dibaca setelah daily sync baru; estimasi dihitung ulang sebelum pengajuan.
Semua revisi memerlukan approval ulang, termasuk saat diskon0%. Kontrol Simulator
approval diskon di Lainnya juga menangani revisi tanpa diskon. Queued/accepted/
needs_approval atau penolakan transport tidak membuka koreksi. Root/cycle/sumber/
receipt/bukti rusak ditahan tanpa penghapusan atau receipt palsu.

Pada Pending Requested isi tanggal kirim ulang (hari kalender, boleh hari yang
sama; tidak boleh sebelum hari pengiriman). Selisih0/1/2 hari membutuhkan SPV;
selisih>=3 hari membutuhkan SPV lalu Branch Manager. Batas tepat3 hari masuk tier
BM secara konservatif sesuai keputusan implementasi yang disampaikan ke pemilik.
Cancel Delivery wajib SPV dan subreason Toko Tutup / Kesalahan Order / Tidak bisa
bayar / Toko tidak dapat diakses / Waktu pengiriman tidak cukup. Alasan umum tetap
direkam pada seluruh item. Simulator approval pending/cancel di Lainnya meminta
alasan keputusan dan menolak BM yang mendahului SPV, keputusan ganda atau snapshot
receipt berubah. Keputusan/history per UUID tersimpan; jadwal/picking resmi belum
diubah atau diterbitkan ulang otomatis sampai backend siap.

Closing trip dari Delivery → Closing trip · tiba di kantor. Semua DO harus
mempunyai hasil POD dan tidak ada sesi delivery aktif; pending review boleh
tercatat tanpa dianggap disetujui. Satu closing lokal per trip/hari, source/POD
terikat dan dicek ulang, replay historis didukung. Setelah closing, pengajuan/
koreksi POD baru pada trip itu ditahan untuk review (belum ada reopen otomatis).
Fixture kantor SIM-OFFICE-MANADO memakai titik1.465/124.833 dan radius30m sebagai
contoh, bukan koordinat/radius kantor nyata. Aturan strict: jarak+akurasi <=radius
kantor+25m. Pada demo baru, lokasi di luar kantor tetap diterima dan diberi label
tanpa validasi. Closing bukan settlement kasir, uang/cek belum dianggap diserahkan,
AR/payment/GL tidak berubah. Cashier handoff di luar scope. Backlog saja: upload
resi uang/cek ke kasir, faktur ke admin, retur ke SPV gudang.

Fixture UI baru memakai site.demo_unrestricted, dibawa dalam sumber/kontrak. Demo
menerima koordinat dan gambar tanpa geofence/akurasi atau pemeriksaan keaslian/
EXIF/kamera. GPS dapat dipakai, atau Gunakan lokasi demo pada foto; capture sesi
memakai titik contoh bila GPS tidak tersedia/ditolak. Seluruhnya berlabel simulasi.
Watermark waktu pencatatan WITA dan koordinat serta pinpoint grid tetap dihasilkan.
Format/ukuran gambar untuk rendering, hash/keberadaan file, owner, urutan aksi dan
binding referensi tidak dihapus: ini integritas penyimpanan, bukan validasi foto
sebagai bukti sah. Foto yang sama boleh diunggah ulang menjadi paket/ID baru.
Bukti baru menyimpan kebijakan demo dalam metadata hash; antrean/snapshot strict
lama tidak ditulis ulang atau dimigrasi. Gate strict tetap diuji di unit; live
tetap terkunci dan tidak menggunakan kebijakan permissive.

OpenAPI draft0.12 menambah sales.order.revise, delivery.trip.close dan DTO request
pending/cancel. Bukan endpoint Odoo yang sudah tersedia. Integrasi backend menunggu
kesiapan seeding sesuai mandat; tidak menyentuh addon/seed/deployment/ruleset.
