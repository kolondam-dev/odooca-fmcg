# Gap analysis kesiapan API dan PWA mobile

Tanggal: 26 Oktober 2026 · Status: sebelum implementasi mobile.
Baseline deploy/source utama: `origin/main` **69a7ef6**.
Calon dependency data: `origin/agen/fix-seed-invariants` **c435447** (PR #15).
Plan mobile lokal: v0.3, `docs/blueprints/mobile_api_and_pwa_plan.md`.

[F] = source/API/hasil pemeriksaan sesi ini; [A] = rekomendasi/inferensi;
[BU] = belum dibuktikan pada runtime yang dimaksud. Snapshot ini bukan persetujuan
merge PR seed, sertifikasi production, atau implementasi fitur mobile.

## 1. Keputusan kesiapan

**Siap untuk menyusun kontrak dan spike disposable (MOB-00). Belum siap untuk
implementasi fitur lapangan lengkap yang menganggap data dan domain sudah final.**
Fondasi Odoo/UI ada; artefak seed terbaru lolos validator dan unit tests, tetapi
API/app role/PWA belum ada. PJP dan ledger file bukan model operasional online.
Identitas petugas, kalender, geofence dan bukti runtime loader masih membutuhkan
penutupan sebelum dipakai sebagai sumber kebenaran mobile.

| Lapisan | Status berdasarkan bukti |
|---|---|
| Odoo core + custom master/UI main | Ada; CI main sukses pada pemeriksaan sebelumnya; manifest empat addon PASS pada sesi ini |
| Artefak kanonikal branch seed | Dua validator PASS dan 98 unit tests PASS pada c435447 |
| Loader kanonikal pada Odoo aktual | Source adapter dan runner ada; tidak ditemukan bukti eksekusi runner pada CI yang diperiksa |
| Domain mobile | id_app/id_api/id_distribusi/id_hris_ext/id_field_expense belum ada di kedua tree |
| Client PWA | Belum ada package/app shell/outbox/media/tracking runtime |
| Produksi saat ini | Tidak diakses; snapshot DB/image/version/module aktual belum diperoleh |

## 2. Branch, CI dan workflow yang dibaca

### Snapshot integrasi

- [F] PR #15: `agen/fix-seed-invariants` -> `agen/supervision-invariant-gates`, open.
- [F] PR #14: `agen/supervision-invariant-gates` -> `agen/transaksi-historis-perpetual`, open.
- [F] Belum ada jalur merge selesai dari dependency tersebut ke main. CI hijau
  pada c435447 tidak membuat source/data branch itu otomatis tersedia di main.
- [F] Check c435447: static/install-test/init-test/invariant-tests/seed-invariants
  success (beberapa job muncul ganda karena event workflow berbeda).
- [F] CI install-test branch seed masih memasang `id_base`; main sudah mempunyai
  instalasi UI dan browser smoke lebih luas. Selisih UI antar-tip terjadi karena
  sejarah branch berbeda; jangan disebut penghapusan sengaja tanpa melihat merge diff.
- [A] Integrasikan lewat PR dan resolusi konflik selektif; pertahankan koreksi UI,
  browser CI dan log main. Jangan menyalin seluruh tree seed menimpa main.

Rujukan CI:
- https://github.com/kolondam-dev/odooca-fmcg/actions/runs/40339973361 (CI c435447).
- https://github.com/kolondam-dev/odooca-fmcg/actions/runs/40339973539 (Seed supervision c435447).
- https://github.com/kolondam-dev/odooca-fmcg/pull/15
- https://github.com/kolondam-dev/odooca-fmcg/pull/14

### Pembagian peran dan aturan commit

[F] Dibaca: AGENTS.md, AGENT_PROTOCOL.md, DEVELOPMENT.md, HANDOFF main dan entri
branch seed, log claude-dev/claude-design/anti-gravity/codex, serta tambahan log
branch seed terhadap main. Log adalah riwayat klaim; source, CI dan uji ulang
menentukan status terkini. Catatan historis yang telah dikoreksi tidak menjadi baseline baru.

| Agent | Workflow yang tercatat | Titik koordinasi mobile |
|---|---|---|
| claude-dev | Kode/review dan Odoo penuh di sandbox; patch zip, hasil verifikasi dan handoff | Kontrak/domain Odoo, instalasi dan pengujian actual ORM |
| antigravity | Laptop pemilik/Railway; master/seed/loader, commit/push dan deploy sesuai mandat | Dependency data, identity mapping, loader aktual, snapshot staging |
| claude-design | id_ui/id_ui_shell/id_ui_form, tampilan dan browser smoke | Token warna, aset menu, konsistensi UI, koordinasi perubahan shared |
| codex | Gate/QA existing dan sesi mobile ini; agent-log/codex.log | Plan, kontrak mobile, readiness dan penerimaan; jangan mencampur klaim lint dengan runtime |

Aturan yang diikuti:
1. Fetch dan whats_new sebelum aksi; baca HANDOFF terbaru dan log pemilik area.
2. Kerja di `agen/<topik>`, dari ujung branch relevan; main untuk hasil layak deploy.
3. Author commit pemilik: `kolondam-dev <franky@kolondam.dev>` (diobservasi dari git).
4. Identitas agent pada baris terakhir: `task managed by codex agent at <ISO8601 +07:00>`.
   Ini penanda workflow, bukan tanda tangan kriptografis Git.
5. Log append-only + HANDOFF entri sendiri di atas; keduanya satu commit dengan perubahan.
6. Modul baru id_*, LGPL-3, versi 19.0; source English, i18n Indonesia; tests sesuai perubahan.
7. PR/merge oleh pemilik sesuai protokol; tidak mengubah production untuk membuktikan readiness.

[F] Main belum menerima argumen codex di dua skrip agent; branch seed sudah.
Untuk scan lintas branch dipakai --since eksplisit pada skrip yang sesuai; log
lokal mempertahankan format codex tanpa mengaku sebagai agent lain. Dukungan
skrip dan log kedua sejarah harus disatukan saat integrasi, tanpa menghapus entri.
Ada variasi historis signature antigravity/antigravity-agent dan UTC/WIB pada log;
pencarian signature tunggal dapat melewatkan commit. Acuan SHA eksplisit diperlukan.

## 3. Modul dan gap terhadap plan mobile

| ID / prioritas | Kebutuhan | Yang tersedia | Gap dan kriteria penutupan |
|---|---|---|---|
| G01 P1 | Baseline source bersama | Main 69a7ef6; seed c435447 di PR bertingkat | Dependency disatukan tanpa regresi UI/CI; tentukan SHA calon implementasi dan snapshot referensi |
| G02 P1 | Identitas employee -> user -> scope | 24 employee, manager_code; loader memasukkan role CSV sebagai job_title | User minimal/mobile-role/employee stable key belum dibuat oleh loader; fixture user nyata, binding, ACL, scope tanpa fallback admin |
| G03 P1 | App role, device binding, work session | Baru plan; label User/Admin pada UI placeholder | id_app, registration/revoke, stacked role, sesi pagi, snapshot ack dan race tests |
| G04 P1 | API/sync | OCA pin dan spike tertulis | Auth, OpenAPI, command receipt/idempotensi, snapshot, media, heartbeat belum ada; buktikan MOB-00/02 |
| G05 P1 | PJP operasional | CSV 354 jadwal dan matrix Juli | Tidak ada model id_distribusi/PJP/visit/grant; import/model/service harus dibuat, tidak membaca CSV Juli sebagai tugas hari ini |
| G06 P1 | Kalender kerja dan jam sesi | HR init Senin-Jumat; generator lapangan Senin-Sabtu | Selaraskan shift/calendar per role (bukan memaksa semua staf sama), timezone dan site luar kota; Sabtu tidak otomatis dianggap absen |
| G07 P1 | Geofence 5–15m | Koordinat simulasi; native geolocation dependency hanya eksplisit di seed | Survey/fixture kontrol, kantor/gudang, radius/polygon, revision dan quality; jangan memakai titik simulasi sebagai bukti presisi toko |
| G08 P1 | Harga/UoM/HPP | cost_price/list_price, inner_qty/carton_qty; loader memakai uom_unit | Kontrak pcs/karton/pack, pembulatan dan readback actual; metode HPP/cost revision; jangan membandingkan harga per karton dengan HPP per unit |
| G09 P1 | Kredit/diskon/approval | credit_mode field dan OCA repos tersedia | Field bukan mesin enforcement; pricing/discount/credit/id_approval, extra call, limit supervisor/BM/Owner, audit dan invalidation belum ada |
| G10 P1 | Stok/lot/AR resmi | Artefak perpetual + adapter | Truthiness model kosong masih dipakai adapter/runner; bukti load/rerun/stock/GL/cutoff pada Odoo aktual belum tersedia; transaksi CSV bukan saldo DB current |
| G11 P1 | Trip/DO dan assignment | fleet, 9 kendaraan, delivery_vehicle pada CSV | Trip/crew/driver user, manifest, lokasi van dan scope DO belum menjadi domain mobile; driver fleet dicari lewat nama partner |
| G12 P1 | Biaya DO/trip/petty cash | Fleet fields, OPEX payroll CSV, account core melalui dependency | Tidak ada request/approval/advance/realisasi/struk/odometer/settlement; OPEX agregat bukan transaksi petty cash |
| G13 P1 | Absensi dan personal HRIS | hr_attendance/hr_holidays ikut dependency id_ui | Custom foto/geofence/device/session, rule shift, saldo dan publikasi slip sendiri belum ada; payroll OCA dipin bukan berarti aktif |
| G14 P1 | Bukti foto/map dan tracking | Belum ada evidence/track store | Camera/media ownership, geotag+map persisted, 5/15m sampling/gap, ACL/retensi/provider belum dibuat |
| G15 P1 | Offline dan notifikasi | Baru rancangan | Durable outbox, polling/reconnect, retry/race, isolate user, queue heartbeat/status/backend notification belum ada |
| G16 P2 | Visual PWA | Web navy/blue tokens, Odoo menu icons; UI desktop ada | Phosphor subset, font mobile, semantic palette, component tokens, contrast/perf/device acceptance belum diimplementasikan |
| G17 P2 | Bukti deployment dan docs | Handoff deployment lama, marks init, README status lama | Snapshot instance calon mobile diperlukan; dukungan codex/workflow dan status docs diselaraskan setelah dependency diterima |

Prioritas P1 di sini berarti penghalang penerimaan fitur terkait, bukan semua harus
selesai sebelum membuat komponen visual atau spike terisolasi. G01/G02/G06/G07/G08/G10
adalah pekerjaan fondasi bersama yang jangan disamarkan dengan mock frontend.

## 4. Inventaris data yang benar-benar diperiksa

| Dataset | Main | Seed c435447 | Makna kesiapan |
|---|---:|---:|---|
| Outlet master | 354 | 354 | Ada; bukan 354 titik geofence yang sudah disurvey |
| Pasangan lat/lon unik | 145 | 269 | Titik berbagi bukan otomatis error, tetapi tidak membuktikan ketepatan 5–15m |
| Produk | 150 | 150 | Seed menambah carton_barcode; harga/UoM actual perlu readback |
| Employee | 24 | 24 | role adalah job/business label CSV; tidak ada kolom app_role atau user_id |
| Armada | 9 | 9 | Driver/nama/rute bukan assignment petugas mobile yang terotorisasi |
| Jadwal PJP registry | Tidak ada | 354 | File referensi |
| Matrix Juli | Tidak ada | 502 baris | 419 kunjungan CUST-, 55 baris admin/staging, 28 Minggu OFF |
| SO / lines | Dataset historis lama | 1.324 / 2.738 kanonikal | Tidak menyamakan dataset main lama dengan register kanonikal |
| DO / invoice | Register kanonikal tidak ada | 1.324 / 1.324 | History Juli + carry-forward; bukan daftar kerja hari ini |
| AR / AP payment | Register kanonikal tidak ada | 967 / 4 | Validator artefak PASS, saldo ORM belum dibuktikan |
| Retur / OPEX payroll | Register kanonikal tidak ada | 9 / 30 | Tidak mencakup approval biaya/BBM dan settlement lapangan |
| Saldo awal SKU | Register kanonikal tidak ada | 150 | Snapshot 1 Juli, bukan stok pagi tanggal operasi mobile |

[F] 55 kunjungan efektif jatuh Sabtu pada matrix seed, sedangkan init resource.calendar
masih menghapus Sabtu/Minggu. [F] `deploy/init.sh` hanya memanggil master seed otomatis;
loader kanonikal belum menjadi tahap boot dengan bukti penerimaan. Memasukkan
register ke image tidak sama dengan memuatnya ke DB.

### Gap source yang spesifik dan dapat ditindaklanjuti

- `scripts/load_fmcg_seed.py:get_salesman_user`: login kode tidak ditemukan masih
  kembali ke admin. Ini berbeda dari fail-fast yang ditambahkan pada adapter transaksi.
  Outlet assignment tidak boleh dipakai scope mobile sebelum diperbaiki/diverifikasi.
- `load_employees`: mencari employee dengan name dan mengisi job_title/manager;
  tidak mengisi stable code/user_id/mobile roles. Rename/duplicate name dan integrasi
  user perlu key stabil dan migration/readback, tanpa mengandalkan nama orang.
- `load_products`: uom_id tetap Units; carton_qty/packaging tidak otomatis menyelesaikan
  seluruh semantik base_uom/purchase_uom. Exception packaging masih warning; readback
  harus memastikan SKU yang diperlukan mobile benar-benar mempunyai konversi sah.
  Guard `if Packaging` juga memakai model recordset kosong, demikian pula
  `if PaymentTerm` / `if not PaymentTerm` pada loader; ini dapat melewati pembuatan
  packaging/termin meskipun model terpasang, terlepas dari keberadaan data di tabel.
- Fleet loader mencari driver pada res.partner berdasarkan nama, bukan pemetaan
  employee-user eksplisit. Keberadaan driver_id actual tidak diasumsikan dari CSV.
- `company_profile_v2` masih kalender lima hari dan mark versi tetap. Koreksi harus
  patch/migration idempoten ber-mark baru setelah disepakati, bukan SQL server langsung.
- Module fastapi/payroll/credit-control di oca.lock adalah source yang dapat diambil,
  bukan bukti modul tersebut aktif pada instance yang akan dipakai mobile.

## 5. Kualitas bukti runtime loader: penghalang yang masih ada

[F] c435447 memperbaiki pemeriksaan ID payment sumber dan lifecycle Odoo 19.
26 test adapter termasuk negative regression ada dan bagian dari 98 tests PASS.
Ini kemajuan yang terverifikasi pada mock, bukan bukti loader berhasil pada Odoo aktual.

**P1 source tambahan pada adapter:** `scripts/load_canonical_perpetual.py` juga
memakai truthiness model, bukan hanya runner: `if StockLot` (sekitar 354/531),
`if AccountMove` (627/734/996 dan tempat lain), `if not StockLocation` (793),
dan `if StockPicking` (831). Karena objek tersebut adalah `env[model].sudo()`
tanpa ID, cabang lot/invoice/discount dapat terlewat atau karantina dianggap tidak
tersedia walau model terpasang. Guard `if StockMoveLine` juga memengaruhi mapping
field/pembuatan move line. Semua guard ketersediaan model perlu dibedakan dari
guard keberadaan record. MockModel biasa tidak otomatis meniru semantik recordset
kosong ini; 98 tests PASS tidak membuktikan cabang actual ORM akan dijalankan.
Temuan ini berbasis kontrol alur source + semantik ORM resmi, belum reproduksi DB
Odoo aktual. Jangan menutupnya hanya dengan mengganti mock agar tetap truthy.

Runner `scripts/ops/verify_disposable_slice.py` masih memerlukan koreksi sebelum
dapat dijadikan gate runtime:

1. **Guard readback dapat melewati pemeriksaan.** Pada baris 90/100/117, runner
   memakai `if StockPicking`, `if AccountPayment`, `if AccountMove` setelah variabel
   berisi model recordset tanpa ID. Source ORM Odoo 19 `__bool__` bergantung pada
   `_ids`; recordset model kosong bernilai false. Periksa ketersediaan model secara
   eksplisit, kemudian search/assert data, bukan truthiness model kosong.
2. **Slice tidak memuat kasus karantina yang disebut docstring.** Run memakai
   `limit_orders=1`, memilih SO-202607-0001. Register menunjukkan satu AR berdiskon
   PAY-AR-00098 untuk SO ini, tetapi nol rejection. SO-202607-0063 yang disebut
   untuk rejection tidak dipilih. Pilih source IDs representatif secara eksplisit.
3. **Rerun belum membuktikan tidak ada drift saldo.** Runner memeriksa beberapa
   counter created=0, bukan identitas/jumlah/saldo snapshot aktual lengkap sebelum
   dan sesudah. Dibutuhkan perbandingan quant/lot, invoice/residual, payment,
   journal/GL dan quarantine/source location termasuk subset yang memang dipilih.
4. **Tidak ada langkah eksekusi runner pada workflow yang diperiksa.** CI seed
   menjalankan tests dan validator; install-test hanya id_base. Tambahkan runtime
   disposable fixture/DB, actual schema/image/module snapshot dan artifact readback.

Ini temuan source; runtime runner belum dijalankan pada sesi ini karena executable
Odoo/Docker tidak tersedia di environment audit. Jangan menafsirkan sebagai hasil
eksekusi kegagalan runtime yang sudah direproduksi. Source rujukan semantics:
https://github.com/odoo/odoo/blob/19.0/odoo/orm/models.py (`__bool__`, sekitar 6494
saat diperiksa); ulangi terhadap image/commit aktual calon deploy.

## 6. Paket penutupan gap sebelum fitur bergantung padanya

| Urutan | Pekerjaan | Bukti selesai | Pemilik koordinasi yang disarankan |
|---|---|---|---|
| A | Bekukan SHA calon integrasi dan koreksi runner/runtime slice | Actual Odoo Run1/Run2, source IDs termasuk discount/rejection/AP, saldo dan GL terikat hash | Worker seed + QA |
| B | Pemetaan employee/user/role/supervisor/driver dan kalender | Tidak ada fallback admin, role bertumpuk, Sabtu/shift/Asia-Makassar benar, ACL tests | Backend/master + mobile |
| C | Fixture master mobile yang relevan | Outlet/control geofence disahkan, kantor/gudang/SPBU/site, UoM/HPP/pricelist, tugas hari operasi | Backend/data + operasi |
| D | Kontrak auth/session/snapshot/command/media | OpenAPI dan spike disposable; account/device scope, retry/race tests | Mobile + backend |
| E | PJP/trip/approval/expense/HR domain sesuai paket | Field/state/policy wajib aktif, limit kosong menahan aksi, audit dan domain integration tests | Domain backend |
| F | PWA shell/visual/offline dan alur pertama | UI token, outbox dan satu SO draft sesudah sync; tidak mengklaim Sales produksi selesai | Mobile + desain |

A–C menghalangi penggunaan seed sebagai backend resmi untuk mobile. D/F dapat
dimulai terisolasi dengan fixture terkontrol tanpa menunggu seluruh history di-load.
Perangkat/native advance tidak boleh dijadikan alasan menunda kontrol akun/scope
dasar. Tidak ada pengurangan gate untuk membuat demo terlihat selesai.

## 7. Fixture tambahan yang belum tersedia

Minimal sebelum penerimaan: employee aktif/nonaktif, role salesman/logistic/gabungan,
supervisor/BM/Owner dengan limit, user tanpa scope dan device revoked; kantor/gudang
dan outlet dengan geofence teruji; satu trip multi-DO + site luar kota; request BBM
H-1, BBM insidentil, over-limit, split-request, realisasi kurang/lebih, struk duplikat;
order regular/extra call/discount/line below HPP; attendance uncertain/double event;
foto map_pending, GPS denied, tracking gap, token expired dan outbox lintas user.
Tanggal fixture mengikuti business_date pilot, tidak memalsukan histori Juli sebagai
kondisi operasional Oktober. Sample uang/dokumen/identitas tetap fiktif.

## 8. Arah visual yang diselaraskan

[F] Web menggunakan navy #001A57, primary #1B5E8C, accent #5BB3E6, text #0B1F4D,
dan brand purple #714B67. [R] Plan v0.3 menetapkan Phosphor duotone untuk micro
icons, penggunaan menu icons Odoo yang relevan, Inter Variable self-hosted dan
semantic color tokens untuk PWA. Phosphor resmi menyediakan duotone, bukan weight
tritone; tritone hanya komposisi terbatas/teruji bila perlu, bukan dependency baru.

[F] Kontras solid dihitung lokal: putih di #1B5E8C 6,94:1; #0B1F4D di putih
15,94:1; #52647A di putih 6,06:1. Accent #5BB3E6 di putih hanya 2,32:1 sehingga
tidak dipakai sendirian untuk teks kecil atau satu-satunya penanda penting.
Ini perhitungan token, bukan pengganti audit layar aktual, opacity dan state disabled.
Detail icon/font/palette/budget tercatat di plan, tidak mengubah tema web existing.

## 9. Bukti sesi ini dan batas laporan

- Fetch remote dan inspeksi PR/check-runs melalui GitHub plugin.
- Manifest main: PASS, empat addon. Kedua tree memiliki empat addon custom.
- Pada worktree audit detached c435447: verify_seed_invariants PASS,
  verify_seed_acceptance PASS, `unittest discover` **98 tests PASS / 26,752 detik**.
- Tests dan validator tidak mengubah dataset/worktree; source/data worker tidak diedit.
- JSON diagnostic berisi commit/hash input; scope eksplisit artefak, bukan runtime Odoo.
- Odoo actual, deployment DB, physical geofence, performance device dan mobile
  features belum diuji; tidak ada push/merge/deploy atau instruksi ke agent lain.
- Pembagian pemilik di laporan adalah rekomendasi handoff, bukan delegasi yang sudah dikirim.
