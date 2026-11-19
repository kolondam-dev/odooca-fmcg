# Operasi integrasi Android

Lead Android menjaga ref basis, workspace tim, urutan integrasi, dan proposal PR. Codex-Android-Design menyerahkan sumber visual dan traceability. Codex-Android-Dev menyerahkan kode serta bukti pengujian. Pemilik menerima pilihan produk dan mengotorisasi publikasi/merge sesuai lingkup yang diberikan. Reviewer independen memeriksa SHA dan dampak tes sebelum merge.

## Branch dan commit

- `main` adalah basis remote yang layak integrasi. Ref kerja lead: `agen/android-integration-Codex-Mobile-Native`. Ref tim: `agen/android-design-Codex-Mobile-Native` dan `agen/android-dev-Codex-Mobile-Native`. Gunakan worktree terpisah di Cloud, satu pemilik per branch.
- Saat mulai atau menyambung sesi, jalankan `bash scripts/agent/whats_new.sh codex`, fetch `origin/main`, baca `AGENTS.md`, HANDOFF dan keputusan terbaru. Catat SHA basis. Pada branch yang sudah dipublikasikan, sinkronkan `origin/main` dengan merge biasa agar riwayat review tetap utuh. Ref lokal bebas mengikuti basis dengan fast-forward bila memungkinkan.
- Tim membuat commit atomik per ID paket dalam bahasa Indonesia. Tambahkan jejak HANDOFF dan log sesuai aturan repo. Gunakan signature workstream `Task managed by Agent Codex-Mobile Native at <ISO8601 +07:00>` sebagai atribusi native, dan baris terakhir yang dikenali protokol `task managed by codex agent at <ISO8601 +07:00>` sampai aturan bersama menyelaraskan dua format. Gunakan identitas Git yang disetujui pemilik.
- Untuk setiap milestone, buat branch kandidat yang berangkat dari `origin/main` terbaru. Integrasikan hanya commit yang masuk scope dan sudah ditinjau, termasuk versi desain yang disetujui. Tinjau konflik shared contract/DS bersama pemilik area dan pertahankan riwayat HANDOFF/log. Catat commit asal dan SHA kandidat. Branch tim dapat terus mengerjakan slice berikutnya di worktree masing-masing.

## Gate lokal dan Cloud

Pada branch kandidat dengan perubahan yang sudah di-commit:

```bash
git fetch origin main
bash android/tools/integration_gate.sh
# Jalankan juga Gradle bila JDK 17, SDK 35 dan build-tools tersedia
bash android/tools/integration_gate.sh --gradle
```

Gate memeriksa ancestor `origin/main`, working tree bersih, whitespace, Ruff, manifest, impact planner, tes selector/gate, dan kesesuaian token. Mode Gradle menambah domain, OpenAPI, data-layer, lint dan build debug. Gunakan branch yang di-commit agar planner melihat delta kandidat. Simpan output serta SHA basis/head di handoff. Gate tersedia di workstation dan Cloud dengan dependensi terkait, sementara GitHub menjalankan required checks existing. Untuk emulator gunakan bukti DEV-01 dan perangkat fisik sesuai milestone.

## Publikasi per milestone

1. Ajukan slice bila requirement dan acceptance sudah jelas. Lampirkan desain versi/node yang diterima, blocker dan status, daftar file, planner, serta evidence yang tepat. Push branch kandidat dan buka PR ke `main` dalam cakupan otorisasi pemilik.
2. Pastikan required checks hijau untuk HEAD terkini, basis masih up to date, dan thread review selesai. Jika main maju, sinkronkan dan ulangi bukti sesuai selector. Reviewer mencatat **Dampak test** dengan alasan dan counterexample yang relevan.
3. Merge melalui PR dengan otorisasi yang berlaku untuk PR tersebut. Lead memperbarui baseline tim dan memverifikasi SHA pascamerge. Deploy, pengujian terhadap Railway dan mutasi data mengikuti otorisasi tersendiri.

Urutan awal: dokumen/operasi → N2a smoke emulator dan D01 → N2b backend disposable/identity → N3 recovery → N4 visit → N5 commerce/logistics. Masing-masing slice dapat diterima dengan bukti sesuai scope.

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
