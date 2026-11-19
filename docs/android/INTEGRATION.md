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
