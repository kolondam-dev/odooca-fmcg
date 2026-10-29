# Pemindaian repo dan kesiapan agent mobile — 26 Oktober 2026

Basis: `main` commit `69a7ef6b853283a70d7ee11770995d347a7d237b`.
Legenda: [F] teramati pada source/API GitHub; [A] usulan; [BU] belum diuji.
Scan mencakup arsitektur, model, aset UI, konfigurasi deploy, CI, dokumen kerja,
serta perbedaan branch aktif. Ini bukan audit runtime menyeluruh atau audit keamanan formal.

## Kesimpulan

[F] Repo merupakan fondasi Odoo 19 CE + OCA 19.0 untuk demo distributor FMCG
Manado. Empat addon custom tersedia: `id_base`, `id_ui`, `id_ui_shell`,
`id_ui_form`. Aplikasi lapangan PWA, `id_api`, `id_app`, `id_distribusi`, dan
`id_hris_ext` belum ada pada tree main. Tidak ditemukan package.json, entry
Preact/Vite, IndexedDB outbox atau service worker aplikasi lapangan.

[F] Mobile yang dimaksud dokumen adalah aplikasi lapangan terpisah dari backend
Odoo. Backend responsif tetap perlu dijaga, tetapi bukan pengganti PWA offline.

## Peta implementasi

| Area | Bukti source | Kesiapan mobile |
|---|---|---|
| Master | id_base: principal, channel, wilayah, outlet, SKU, fleet | Dasar ada; API dan pembatasan data per petugas belum ada |
| Backend desktop | id_ui, id_ui_shell, id_ui_form | Ada; shell kembali ke navbar bawaan saat ui.isSmall |
| App role | SCOPE 4A.5; UserMenu.idRoleLabel masih placeholder | Baru rancangan |
| REST API | SPIKE_API_OFFLINE.md | Belum ada endpoint custom |
| Sales lapangan | SCOPE C; Playbook 5.3 | Belum ada UI/alur runtime |
| Delivery | SCOPE D | Belum ada UI/alur runtime |
| HRIS lapangan | SCOPE F | Belum ada ekstensi foto/geofence custom |
| Sinkronisasi | SCOPE 4A.3; spike E2–E4 | Baru rancangan |
| CI | ci.yml: static, install-test, init-test, Chromium smoke | Backend diuji; alur PWA belum tersedia untuk diuji |

## Keputusan existing yang harus dipertahankan

- [F] Satu PWA Preact + Vite, tab dinamis dari server; default Indonesia, English tersedia.
- [F] Role bertumpuk: HRIS untuk semua role; Sales untuk salesman; Delivery untuk logistic.
  Canvasser dapat memakai Sales dan Delivery sekaligus.
- [F] Mobile menulis ke Odoo pada mode primary maupun secondary. Ekspor ke legacy DMS manual.
- [F] Harga, diskon, kredit dan approval diputuskan server; harga offline bersifat sementara.
- [F] Token dipetakan ke pengguna/karyawan, tanpa akun sudo bersama untuk seluruh petugas.
- [F] Demo absensi memakai foto + geotag; face recognition dan native Android fase berikutnya.
- [F] Spike harus memutuskan FastAPI OCA vs controller Odoo; prototype spike dibuang.
- [F] Kontrak seed di branch aktif menetapkan satu SO hanya satu principal berdasarkan master SKU.
  Ini requirement terdokumentasi di branch, belum constraint sale.order yang ditemukan di main.

## Temuan dan risiko

| Prioritas | Temuan | Dampak / tindakan |
|---|---|---|
| P1 fondasi | Auth, role, bootstrap dan record scope belum diimplementasikan | Tetapkan izin per operasi, outlet milik salesman, DO milik penugasan, HRIS milik diri sendiri; tab tersembunyi bukan otorisasi |
| P1 fondasi | Idempotensi baru disebut client_uuid | Tetapkan scope user/operasi, unique constraint, payload hash, atomic commit dan replay respons; UUID sama dengan payload berbeda harus konflik |
| P1 fondasi | Pull write_date belum punya kontrak pagination/deletion | Tentukan cursor stabil, batas snapshot, tie-break ID, archive/tombstone dan resync |
| P1 fondasi | Antrean offline belum punya lifecycle | Tentukan queued/sending/accepted/needs_approval/rejected, retry jaringan, resume setelah crash, dependency foto dan dokumen |
| P1 privasi | Isolasi cache per identitas belum ditentukan | Jangan tampilkan data user sebelumnya saat logout/switch account; tentukan penanganan draft belum sinkron |
| P1 integrasi | Pricing, credit, approval, distribusi belum menjadi addon custom | Mulai dari spike terbatas; jangan klaim order produksi selesai sebelum backend tersedia |
| P2 kandidat bug | form_patch.js syncTitle memeriksa mode sidebar/dialog, tetapi tidak ui.isSmall | Pada layar kecil judul berpotensi tetap dipindah ke statusbar saat shell sudah kembali ke navbar native; perlu reproduksi breakpoint [BU] |
| P2 QA | smoke_ui.py memakai 1440x860 | Test systray 390px hanya fixture CSS/helper, bukan bukti seluruh Odoo mobile atau PWA |
| P2 bukti lapangan | Geofence, akurasi GPS, clock klien, foto belum punya kebijakan runtime | Tetapkan radius, akurasi, izin ditolak, waktu server vs klien, batas MIME/ukuran dan retensi; lokasi browser bukan bukti anti-fraud mutlak |
| P2 dokumentasi | README dan header ci.yml masih menyebut CI belum dijalankan | Bertentangan dengan run GitHub sukses; roadmap juga belum mencerminkan semua perubahan terbaru |
| P2 koordinasi | Skrip main belum menerima codex | whats_new.sh codex ditolak; scan memakai --since root eksplisit. Dukungan codex ada di branch seed tetapi belum di main |

## Keadaan branch dan CI

- [F] Main dilindungi; status check `static`, `install-test`, `init-test` sukses
  untuk 69a7ef6. Run CI: https://github.com/kolondam-dev/odooca-fmcg/actions/runs/40266940153.
- [F] PR #14: agen/supervision-invariant-gates -> agen/transaksi-historis-perpetual.
- [F] PR #15: agen/fix-seed-invariants -> agen/supervision-invariant-gates;
  head cc2276c. Keduanya masih open saat scan, bukan PR langsung ke main.
- [F] Run terbaru pada cc2276c sukses. Ini tidak membuktikan runtime loader Odoo;
  kontrak branch sendiri membedakan validasi artefak dan bukti runtime.
- [A] Basis mobile gunakan main terbaru, ambil dependency yang sudah direview secara selektif.
  Jangan mengganti main dengan branch seed secara utuh: branch mempunyai snapshot UI berbeda
  dan belum memuat seluruh koreksi UI terbaru main. Selisih antar-tip bukan otomatis rollback PR.

## Pembagian scope agent mobile yang disarankan

| Pemilik | Scope |
|---|---|
| Agent mobile (sesi ini) | PWA shell, routing/tab berbasis bootstrap, IndexedDB/outbox, sinkronisasi, foto/geolokasi, i18n, performa dan pengujian mobile |
| Kolaborasi mobile + backend | id_api/id_app, auth, OpenAPI, idempotensi, pagination, status bisnis dan upload attachment |
| Backend/domain | Pricing, discount, credit, approval, posting stok/akuntansi, PJP dan penugasan |
| Agent desain existing | Arah visual dan komponen; koordinasi sebelum mengubah id_ui_shell/id_ui_form |
| Deploy/owner | Hosting, secret, Railway dan penerimaan merge |

Ini usulan pembagian tanggung jawab, bukan perubahan mandat agent lain.

## Urutan kerja konkret

1. Tutup spike API/offline existing: keputusan auth/transport, model role dan
   spesifikasi bootstrap/order minimum. Ukur bundle dan sinkron 50 order pada perangkat target.
2. Buktikan vertical slice disposable: login salesman -> bootstrap HRIS+Sales ->
   master terbatas -> draft order offline -> reconnect -> satu SO draft.
   Dua pengiriman identik dan dua request bersamaan wajib menghasilkan satu dokumen.
3. Tambahkan UI status diterima/perlu approval/ditolak, perubahan harga saat sync,
   pemulihan setelah browser ditutup, dan penanganan token dicabut.
4. Implementasikan Sales/PJP/check-in; lanjut Delivery/POD/collection sesuai kesiapan
   domain backend; HRIS foto/geotag/cuti/payslip sesuai M7.
5. QA layar 360/390px dan tablet, portrait/landscape, touch, keyboard virtual,
   offline/putus tengah unggah, GPS/kamera ditolak, user switching, Android Chrome
   dan iOS Safari [A: target browser perlu diselaraskan perangkat pengguna].

## Bukti verifikasi sesi

- Clone dan fetch remote; inventaris tree main dan branch; baca AGENTS, protokol,
  DEVELOPMENT, HANDOFF, SCOPE, Playbook, spike, dokumen UI, kode model/patch dan CI.
- Manifest validator: PASS, empat addon.
- Ruff 0.6.9: PASS pada main.
- Status CI dibaca melalui GitHub plugin; tidak disimpulkan dari log agent.
- [BU] Odoo runtime lokal, device/browser mobile, runtime FastAPI dan perilaku
  resize judul belum dijalankan. Tidak mengakses atau mengubah production.
- Tidak ada perubahan kode aplikasi, dataset, remote branch, PR atau deploy dalam scan ini.

Rujukan utama: docs/SCOPE.md 4A, 4C, 12; docs/spikes/SPIKE_API_OFFLINE.md;
docs/PLAYBOOK_DISTRIBUTOR_FMCG.md 5.3; docs/ui/id_ui_shell.md;
addons/id_ui_form/static/src/form/form_patch.js; .github/workflows/ci.yml.
