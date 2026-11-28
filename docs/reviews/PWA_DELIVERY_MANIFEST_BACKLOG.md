# Backlog — Manifest Delivery Order Asli di PWA Driver

Status: **IMPLEMENTED — exact-SHA CI dan acceptance disposable masih wajib**

## 2026-11-27 — Acceptance runtime disposable PR #206 (berjalan)

- [F] Fork Railway `pr206-acceptance` (`76986ccf-843e-4084-b67a-c357717c3c5e`) terpisah copy-on-write dari pilot. Fork sumber tidak memiliki DO `WH/OUT/06409`/`06410`; dua stock picking native berstatus `assigned` dibuat lewat Odoo ORM hanya pada fork, assignment driver hari WITA dibuat, dengan outlet 8/9 dan kuantitas 60+160 / 90+320.
- [F] Runtime SHA `b2a9076a27fd3ace8da38f1396b4562114a1249e`: driver login dari PWA, snapshot API 200 tepat dua DO dan browser menampilkan keduanya terpasang ke outlet tepat. Foto/GPS browser menggunakan fixture sintetis pada salinan disposable, bukan bukti kunjungan lapangan.
- [F] POD penuh dari layar PWA menghasilkan HTTP 422 `Bukti POD ... tidak ditemukan`: command diteruskan tetapi foto resmi tidak diunggah ke `/api/v1/evidence`. Fix menambah upload opening/POD dan penerjemahan hash foto server sebelum command, tanpa mengubah outbox lokal. **Bukti runtime fix, CI SHA baru, POD kedua, closing, resync dan cleanup belum lulus.**
- [BU] Verdict tetap **HOLD — CI head sebelumnya PASS, runtime acceptance pending**. Fork wajib dilepas setelah bukti atau saat pengujian dihentikan; jangan merge/deploy ke pilot.

### Bukti lanjutan — 27 November, fork yang sama

- [F] Build transaksi `b2efacd0dd3c088ea95f3d6a064099815fc61133` (Odoo `50df91de`, PWA `89056648`): browser driver mengunggah bukti pembukaan dan POD lewat `/api/v1/evidence` HTTP 201, lalu POD penuh DO `WH/OUT/06409` (outlet `8`, `60+160`) HTTP 200, UUID `411fc337-0f43-4aee-8335-c25d368bc245`.
- [F] Closing **prematur** dengan satu UUID melalui endpoint resmi, dipanggil dari sesi browser terautentikasi yang sama, HTTP 422 (`Trip ... belum lengkap`). Ini **bukan** bukti layar closing PWA sendiri menampilkan 422: guard lokal mencegah pengajuan sebelum kedua POD tersedia.
- [F] POD parsial DO `WH/OUT/06410` (outlet `9`, `90+110` diterima dari `90+320`; alasan item `QTY TERLALU BANYAK` untuk 210 unit) HTTP 200, UUID `f0dc6ee1-233f-4427-9d66-0f4be4976dbe`. Closing final HTTP 200 UUID `69d542b7-71b9-4284-bb8a-83b4d8113f31` dengan **kedua UUID** POD. Audit DB read-only: tepat dua POD accepted dan satu closing accepted; native pickings tetap `assigned` (bukan posting stok).
- [F] Deploy SHA `7d5fa2e1087fc1026efa847fbcb7f6c4450935c2` ke **fork saja**: PWA `a059afbb`, Odoo `0fba677e`, gateway restart `5983c383`, semuanya SUCCESS. Dua sesi browser baru terpisah, masing-masing refresh, snapshot HTTP 200 tepat dua pasangan `(06409,8)` dan `(06410,9)`, UI tepat satu task/DO; audit DB sesudahnya tetap 2 POD + 1 closing tanpa duplikasi. Foto dan koordinat adalah fixture sintetis disposable, bukan bukti lapangan.
- [F] **Batas penting:** sesi baru menampilkan `0/2 toko selesai` dan `Belum ditutup` meskipun command sudah accepted di Odoo; progres lokal tidak dipulihkan dari server. Jadi bukti resync hanya menutup pasangan DO–outlet/no-duplicate, **bukan** persistensi status completed UI. Transaksi HTTP 200 di atas terjadi pada ancestor `b2efacd`, bukan exact SHA `7d5fa2e` atau hasil merge PR #208.
- [BU] Dampak test **TAMBAH** untuk persistensi progres lintas browser: level browser terautentikasi + audit command Odoo, counterexample dua POD+closing accepted tetapi sesi baru 0/2, acceptance UI merekonsiliasi status authoritative tanpa submit ulang. Trigger `pwa/**` → `pwa` dalam `.ci/test-impact.yml`; test upload ordering/hash fail-closed yang sudah ditambah menutup risiko transport, bukan risiko rekonsiliasi. **HOLD** sampai kriteria UI 422/persistensi bila diwajibkan, CI SHA akhir, dan bukti cleanup terverifikasi; merge/pilot deployment tetap tanpa otorisasi.
- [F] Cleanup `release-fork` sukses untuk `pr206-acceptance` (`76986ccf-843e-4084-b67a-c357717c3c5e`): `fork-list` kosong dan `describe-environment` mengembalikan *Environment not found*. Sebelum release fork memiliki empat layanan + volume Postgres/filestore; setelah release pilot (`fe7ccc17-6418-4e03-a295-5bd17acb7555`) masih mempunyai empat layanan `SUCCESS` dan dua volume. Tidak ada merge PR atau deploy pilot.

Prioritas: **tinggi untuk menutup acceptance driver PWA**

Acceptance gudang/DO/closing API: **PASS** — lihat
`WAREHOUSE_TRIP_DO_ACCEPTANCE_REPORT.txt`.

## 1. Batas hasil yang sudah diterima

- [F] Picklist dan Packlist mencatat lot FEFO serta paket untuk kedua DO.
- [F] `WH/OUT/06409` mencatat 220 unit keluar dan diterima penuh.
- [F] `WH/OUT/06410` mencatat 410 unit keluar; 200 diterima dan 210 kembali
  melalui retur `WH/IN/00042`. Lot, stock move, dan quant akhir cocok.
- [F] API menolak closing dengan HTTP 422 saat POD DO kedua belum diterima.
- [F] Setelah kedua POD diterima, API mengembalikan HTTP 200 dan mencatat dua
  DO terverifikasi pada trip yang sama.

Acceptance tersebut menutup konsistensi gudang, laporan, POD API, dan closing
trip API. Acceptance tersebut **belum** membuktikan bahwa operator driver dapat
mengerjakan dua DO asli dari antarmuka PWA.

## 2. Masalah terbuka dan counterexample

- [F] `addons/id_mobile_api/models/mobile_workday.py` mengembalikan
  `"deliveries": []` secara eksplisit pada snapshot.
- [F] `pwa/src/data/mock.ts` membuat `DEMO-DO-OUTLET-*` saat snapshot tidak
  memiliki delivery.
- [F] `deliveryTasks()` kemudian membuat tiga baris produk contoh dan, untuk DO
  non-sintetis, mengikat outlet berdasarkan posisi array, bukan `outlet_id`
  eksplisit.
- [F] Pada provider terautentikasi, hanya command sales yang diteruskan ke
  backend; delivery POD dan closing masih melalui simulator lokal.

Counterexample yang menahan acceptance driver PWA:

1. Odoo memiliki DO asli `WH/OUT/06409` dan `WH/OUT/06410` pada trip aktif.
2. `/api/v1/sync/snapshot` mengembalikan `deliveries: []`.
3. PWA menampilkan `DEMO-DO-OUTLET-8` dan `DEMO-DO-OUTLET-9`, bukan kedua nomor
   DO Odoo tersebut, serta menampilkan baris contoh yang tidak berasal dari
   stock move DO.
4. Karena identitas dan baris sumber berbeda, keberhasilan HTTP yang memakai ID
   DO asli tidak membuktikan alur operator melalui PWA.

## 3. Scope implementasi yang diperlukan

### Backend `id_mobile_api`

Snapshot harus memuat manifest DO asli yang aman dan terbatas pada assignment:

- outgoing picking pada company dan warehouse assignment;
- driver/user yang ditugaskan;
- tanggal operasional WITA assignment;
- partner termasuk dalam `outlet_ids` assignment;
- status operasional yang diizinkan (`assigned` dan, bila diperlukan untuk
  readback, `done`);
- satu identitas trip authoritative yang sama dengan aturan POD/closing server;
- `id` = nama DO native Odoo, bukan ID sintetis;
- `outlet_id`, alamat, trip, kendaraan, versi manifest, dan baris produk asli;
- kuantitas baris dalam base unit integer yang diterima kontrak PWA;
- tanpa lot, harga pokok, margin, nomor telepon, VAT, quant individual, atau data
  DO di luar assignment.

[A] Kontrak `deliveries` sebaiknya dinaikkan dari ringkasan UI menjadi delivery
task lengkap atau diberi endpoint task detail tersendiri. Pilihan desain harus
menjamin PWA tidak perlu mengarang baris produk.

### PWA

- Gunakan `outlet_id` eksplisit; jangan mengikat DO ke outlet berdasarkan indeks.
- Gunakan nomor DO, trip, kendaraan, dan baris asli dari server.
- Jangan membuat fallback `DEMO-DO-OUTLET-*` dalam mode authenticated/official.
  Fallback demo hanya boleh hidup pada mode demo yang eksplisit.
- Teruskan `delivery.pod.submit` dan `delivery.trip.close` ke API pada provider
  authenticated, dengan mekanisme outbox/idempotensi yang sudah berlaku.
- Tampilkan error scope/version dari server dan paksa resync bila assignment atau
  manifest berubah.
- Pertahankan simulasi lokal hanya untuk mode demo; label dan data demo tidak
  boleh muncul pada sesi driver resmi.

## 4. Kriteria penerimaan

Semua butir berikut wajib lulus pada satu salinan disposable dan exact runtime
SHA yang dicatat:

1. Snapshot driver berisi **tepat dua** delivery: `WH/OUT/06409` dan
   `WH/OUT/06410`; tidak ada `DEMO-DO-*`.
2. Setiap task membawa `outlet_id` yang benar, trip yang sama, kendaraan yang
   benar, dan baris/kuantitas yang sama dengan stock move Odoo.
3. Operator membuka kedua DO dari PWA; layar detail menampilkan DO/outlet/SKU/
   kuantitas yang benar tanpa data contoh.
4. Operator mengirim POD penuh untuk DO A dari PWA; command tersimpan di Odoo
   dan terikat pada DO A/outlet A.
5. Operator mencoba closing dari PWA sebelum POD DO B; UI menampilkan penolakan
   HTTP 422 server dan trip belum ditandai selesai.
6. Operator mengirim POD parsial DO B dari PWA dengan alasan per item; command
   tersimpan di Odoo dan terikat pada DO B/outlet B.
7. Operator menutup trip dari PWA; server mengembalikan HTTP 200 dan referensi
   closing untuk trip yang sama serta kedua POD UUID.
8. Refresh/resync/new session tetap menampilkan hasil authoritative; tidak ada
   duplikasi POD, task silang outlet, atau fallback sintetis.
9. User/company/warehouse/outlet lain tidak dapat melihat atau memproses DO di
   luar assignment.
10. Cleanup salinan disposable terbukti dari sesi baru, tanpa residu pada DB
    sumber/demo.

## 5. Dampak test: TAMBAH

Alasan: kontrak read API, scope security, identitas DO/outlet, command forwarding,
dan alur browser driver berubah sekaligus. Test saat ini justru mengunci
`deliveries == []` dan fallback sintetis, sehingga tidak cukup untuk menutup
risiko.

Test minimum yang harus ditambah/diubah:

- **Odoo model/HttpCase** — `addons/id_mobile_api/tests/test_read_api.py`:
  manifest positif dua DO; company/warehouse/user/date/outlet/state isolation;
  line quantity dan native identifiers; digest berubah saat manifest berubah;
  data sensitif tidak bocor.
- **Odoo command integration** —
  `addons/id_mobile_api/tests/test_commands_api.py`: task dari snapshot dapat
  langsung menjadi source POD; premature closing 422; closing final 200; DO di
  luar snapshot ditolak.
- **PWA contract/provider tests** — hapus ekspektasi fallback authenticated,
  buktikan mapping `outlet_id` tidak bergantung urutan, baris tidak difabrikasi,
  dan POD/closing diteruskan ke provider HTTP.
- **PWA browser test** — dua DO asli dibuka, POD penuh + parsial dikirim, closing
  prematur ditolak, lalu closing final berhasil. Bukti harus mencakup request/
  response API dan tampilan nomor DO asli.
- **Runtime acceptance disposable** — ulangi acceptance driver PWA pada exact SHA;
  unit test/CI hijau saja tidak cukup.

Path implementasi memicu suite minimum menurut `.ci/test-impact.yml`:

- `addons/id_mobile_api/**` → `odoo_install`, `mobile`, `upgrade`;
- `pwa/**` → `pwa`.

Sebelum PR jalankan `python scripts/ci/plan.py --base origin/main --head HEAD`,
`ruff check .`, `python scripts/check_manifests.py`, test Odoo modul
`id_mobile_api`, serta `npm test`, `npm run typecheck`, `npm run build`, dan test
browser relevan di `pwa/`.

## 6. Di luar scope backlog ini

- Vendor offer, MOQ, dan whole-carton purchasing.
- Perubahan stock validation/return yang sudah lulus acceptance gudang.
- Pengubahan data langsung pada server atau demo production.
- Deploy, merge, atau persetujuan produksi; semuanya memerlukan otorisasi
  terpisah setelah exact-SHA CI dan acceptance PWA PASS.

## 7. Implementasi 2026-11-27

- [F] Snapshot menggunakan resolver DO native yang sama dengan POD dan closing,
  dengan batas company, warehouse, driver, outlet assignment, status, trip, dan
  tanggal WITA.
- [F] Kontrak `deliveries` sekarang membawa task lengkap: nama DO, `outlet_id`,
  trip, kendaraan, geofence, stock-move SKU/kuantitas, owner, hari, dan versi.
- [F] Sesi authenticated tidak lagi membuat `DEMO-DO-OUTLET-*`; manifest resmi
  kosong dipertahankan sebagai `[]`.
- [F] POD dan closing authenticated diteruskan melalui provider HTTP dan outbox;
  test transport membuktikan UUID tetap, tidak dikirim ulang setelah terminal,
  serta HTTP 422 menjadi item `rejected`.
- [F] Test backend menolak DO lintas company, warehouse, driver, outlet, dan hari
  WITA; test browser mengacak urutan outlet untuk membuktikan pairing eksplisit.
- [BU] Runtime Odoo, exact-SHA CI, acceptance PWA terhadap salinan disposable,
  bukti cleanup, dan keputusan reviewer belum selesai pada checkpoint ini.
