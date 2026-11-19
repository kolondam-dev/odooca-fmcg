# Operasi integrasi Android

Lead Android menjaga ref basis, workspace tim, urutan integrasi, dan proposal PR. Codex-Android-Design menyerahkan sumber visual dan traceability. Codex-Android-Dev menyerahkan kode serta bukti pengujian. Pemilik menerima pilihan produk dan mengotorisasi publikasi/merge sesuai lingkup yang diberikan. Reviewer independen memeriksa SHA dan dampak tes sebelum merge.

## Batas akses dan serah terima

Untuk subproyek Android, **Lead adalah satu-satunya jalur GitHub**. Lead melakukan fetch/pull, pemeriksaan remote/CI, push kandidat, PR dan merge sesuai mandat pemilik. Codex-Android-Design dan Codex-Android-Dev mengerjakan serta menguji commit di Cloud lokal dan menyerahkannya ke Lead. Tim tidak menjalankan operasi GitHub, meminta kredensial, atau menjalankan skrip yang melakukan fetch remote. Koneksi Figma untuk Design tetap mengikuti otorisasi desain.

Cloud dengan repository yang sama dapat menyediakan checkout terpisah per chat. Validasi melalui path worktree, ref dan objek commit. Ikuti [panduan kerja lokal](LOCAL_WORKFLOW.md) untuk branch yang langsung terlihat dan untuk pemindahan bundle antarsesi.

## Branch dan commit

- `main` adalah basis remote yang layak integrasi. Ref kerja lead: `agen/android-integration-Codex-Mobile-Native`. Ref tim: `agen/android-design-Codex-Mobile-Native` dan `agen/android-dev-Codex-Mobile-Native`. Gunakan worktree terpisah di Cloud, satu pemilik per branch.
- Lead menjalankan `bash scripts/agent/whats_new.sh codex` dan menyegarkan `origin/main`. Lead memeriksa perubahan upstream, mencatat SHA main dan SHA baseline tim, lalu menyerahkan snapshot dan petunjuk sinkronisasi ke tim. Tim memeriksa riwayat serta HANDOFF secara lokal. Pada kandidat yang sudah dipublikasikan, Lead menyinkronkan main dengan merge biasa agar riwayat review tetap utuh.
- Tim membuat commit atomik per ID paket dalam bahasa Indonesia. Tambahkan jejak HANDOFF dan log sesuai aturan repo. Gunakan signature workstream `Task managed by Agent Codex-Mobile Native at <ISO8601 +07:00>` sebagai atribusi native, dan baris terakhir yang dikenali protokol `task managed by codex agent at <ISO8601 +07:00>` sampai aturan bersama menyelaraskan dua format. Gunakan identitas Git yang disetujui pemilik.
- Untuk setiap milestone, buat branch kandidat yang berangkat dari `origin/main` terbaru. Integrasikan hanya commit yang masuk scope dan sudah ditinjau, termasuk versi desain yang disetujui. Tinjau konflik shared contract/DS bersama pemilik area dan pertahankan riwayat HANDOFF/log. Catat commit asal dan SHA kandidat. Branch tim dapat terus mengerjakan slice berikutnya di worktree masing-masing.

## Mirror lokal dan jalur integrasi Lead

`/workspace/odooca-fmcg` membuka `main` lokal sebagai mirror GitHub. Worktree tim dan integrasi berbagi objek Git dengan repo itu di instance Cloud yang sama. Lead menjaga mirror bersih dan menggesernya hanya dengan fast-forward. Jika main lokal berisi commit tambahan, berubah di working tree, atau history GitHub ditulis ulang, hentikan sinkronisasi mirror dan periksa selisihnya sebelum memperbarui ref. Jangan reset pekerjaan pihak lain.

Pada awal checkpoint, setelah menerima handoff, dan sebelum merakit kandidat:

```bash
git -C /workspace/odooca-fmcg fetch origin refs/heads/main:refs/remotes/origin/main
git -C /workspace/odooca-fmcg status --short --branch
# Setelah memeriksa branch main dan worktree bersih:
git -C /workspace/odooca-fmcg merge --ff-only origin/main
git -C /workspace/odooca-fmcg rev-parse origin/main
```

1. Catat SHA main yang baru. Untuk team worktree, periksa status, HEAD dan delta sejak baseline. Jika perubahan upstream menyentuh scope aktif, sepakati checkpoint dan sinkronkan branch tim saat bersih. Pertahankan draf dan commit tim. Untuk sesi terpisah, kirim baseline yang dipatok dan terima hasil melalui bundle lokal sesuai [panduan tim](LOCAL_WORKFLOW.md).
2. Review handoff dan daftar commit yang diterima. Dari `origin/main` yang baru diverifikasi, buat worktree kandidat pada `agen/android-integration-<slice>-Codex-Mobile-Native`. Integrasikan hanya commit slice yang disetujui dan dependency yang belum ada di main. Catat SHA asal dan ulangi pemeriksaan diff. Konflik kontrak atau desain dibahas dengan pemilik area.
3. Periksa main sekali lagi sebelum membentuk commit integrasi. Jika bergerak, ambil basis baru dan rakit ulang sebelum commit atau sinkronkan kandidat yang sudah terlanjur memiliki commit. Jika kandidat sudah dipublikasikan, merge main baru ke kandidat dan pertahankan riwayat PR.

## Gate lokal dan publikasi

Pada kandidat yang sudah di-commit, Lead menjalankan:

```bash
bash android/tools/integration_gate.sh --refresh-main
# Jika toolchain Gradle tersedia:
bash android/tools/integration_gate.sh --refresh-main --gradle
```

Gate Lead menyegarkan `origin/main`, memeriksa ancestor dan working tree bersih, whitespace, Ruff, manifest, planner, tes kontrak CI, dan token. Gate membandingkan lagi SHA GitHub main pada akhir verifikasi. Mode Gradle menambah domain, OpenAPI, data layer, lint dan build debug. Tim bekerja dengan `ANDROID_GATE_BASE=<SHA main dari Lead> bash android/tools/integration_gate.sh` di lokal. Flag `--refresh-main` hanya untuk Lead.

1. Sebelum push, Lead memastikan kandidat masih mencakup tip main terbaru. Bila tip berubah setelah gate selesai, sinkronkan dan jalankan ulang pengujian sesuai dampak. Push ref kandidat melalui otorisasi pemilik, buka PR menuju main, dan catat base/head serta bukti.
2. Sebelum merge, verifikasi lagi base dan head PR, status up-to-date, required checks pada revisi yang tepat, dan thread review. Bila main bergerak sewaktu CI berjalan, sinkronkan kandidat dan ulangi bukti. Checks dan ruleset GitHub menjadi pengaman terakhir jika ada perubahan bersamaan setelah pemeriksaan Lead.
3. Setelah merge melalui PR, fetch dan fast-forward mirror lokal. Beri tim SHA main baru dan instruksi sinkronisasi. Deploy, Railway dan mutasi database tetap mengikuti otorisasi terpisah.

Urutan: dokumen/operasi → N2a smoke emulator dan D01 → N2b backend disposable/identity → N3 recovery → N4 visit → N5 commerce/logistics.

## Kepemilikan dan konflik

| Area | Penanggung jawab | Review minimum |
|---|---|---|
| SSOT, register blocker, gate, kandidat rilis | Lead | Pemilik untuk scope, reviewer independen untuk integrasi. |
| Figma, state matrix, token semantik dan prototype | Design | Pemilik untuk visual, Dev untuk feasibility dan pemetaan Compose. |
| Android, instrumentation dan evidence runtime | Dev | Lead untuk arsitektur, Design untuk kesesuaian visual, reviewer independen untuk kualitas. |
| API Odoo, shared schema/token, DB dan CI | Maintainer area bersama Lead | Review lintas tim; perubahan capability atau target persisten mengikuti mandat pemilik. |

Leader mengelola sinkronisasi dan staging commit. Sebelum fast-forward worktree tim, periksa status bersih dan ancestor. Jika branch tim memiliki commit berbeda atau perubahan lokal, hentikan fast-forward dan integrasikan melalui merge yang ditinjau bersama pemilik branch. Untuk perubahan yang bertumpuk di DS dan app, integrasikan primitives/kontrak yang dipakai kedua slice terlebih dahulu. Fitur memakai versi yang sama pada candidate. Handoff/agent-log dipertahankan append-only saat konflik.

## Gate desain ke implementasi

1. **Siap dirancang.** Paket memiliki Rxx, flow, aktor, source, capability dan Bxx. Perbedaan kebijakan dicatat sebagai DEC. Feature yang menunggu kontrak dapat menyiapkan prototype dengan fixture.
2. **Siap diimplementasikan.** Lead mencatat URL/node/version yang diterima, state matrix, token/component mapping, contoh ukuran/font dan delta keputusan. Dev mengikat rute dan test ID ke versi itu sebelum mengerjakannya.
3. **Siap diintegrasikan.** Cocokkan screenshot/semantics/actual flow dengan versi Figma yang disetujui. Jika desain atau kontrak bergerak, catat delta dan jalankan ulang suite yang terdampak. Bukti runtime mengikuti tabel DEV. Gate lokal dan CI tidak menggantikan pemeriksaan visual atau acceptance perangkat.
4. **Siap dipublikasikan.** Reviewer mencatat verdict dan dampak test pada SHA terkini. Branch memakai basis terbaru dan scope kandidat yang disetujui. Aturan required checks, review dan otorisasi tetap mengikuti repo.

## Urutan kandidat remote

| Slice | Isi | Bukti sebelum pengajuan |
|---|---|---|
| S0 | SSOT, design system, spec kedua tim dan operasi. | Konsistensi tautan/traceability, gate lokal, dan review scope. |
| S1 | DES-00/01/02 + D01 sesuai paket yang diterima, DEV-01A/01B terpisah bila independen. | Baseline node/versi untuk desain. Boot dan smoke API 24/35 untuk kandidat emulator. |
| S2 | DEV-02A/02B dan keputusan perangkat. | Fixture Odoo disposable, scope, expiry, bukti hardware terpisah, serta keputusan B01/B02. |
| S3 | DEV-03A/03B. | Bukti Room/HTTP, process death, migrasi dan retry. |
| S4 | DEV-04A lalu DEV-04B sesuai B03/B04. | Receipt server untuk kunjungan/evidence dan acceptance terpisah untuk absensi. |
| S5+ | Sales, Delivery, kas, HRIS dan pilot. | Per capability, QA fixture, efek server, bukti fisik dan sign-off release sesuai scope. |

Kandidat dapat berupa lebih dari satu PR bila dependency independen. Setiap PR mencatat base/head, daftar commit sumber, rancangan yang dipakai, blocker yang tersisa, hasil planner, proof link, temuan review serta otorisasi yang berlaku. SHA pascamerge menjadi titik integrasi berikutnya.
