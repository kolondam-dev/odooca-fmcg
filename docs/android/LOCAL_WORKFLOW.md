# Handoff bersama — Odooca Field Android

Mandat pemilik 19 November 2026. GitHub `kolondam-dev/odooca-fmcg` adalah sumber bersama untuk pertukaran baseline dan commit. ANDROID - LEAD DEV, ANDROID - DESIGN dan ANDROID - DEV menjalankan pekerjaan pada checkout Codex Cloud masing-masing. Instruksi ini menggantikan handoff bundle antarchat.

| Ref | Fungsi |
|---|---|
| `agen/android-baseline-Codex-Mobile-Native` | Branch baseline bersama. Commit integrasi spesifikasi yang dipatok: `9c1ee23099ae4a5c4758972ddac842d03bcdc552`. Tip branch memuat handoff dan arahan Lead yang berlaku. |
| `39172de900668263676577d843a095bf90065ec2` | SHA main acuan saat baseline disiapkan. |
| `75b39a890eb6dbd6446e31cca452ffa0518c71fb` | Baseline lokal sebelumnya, dipertahankan sebagai ancestor. |
| `agen/android-design-Codex-Mobile-Native` | Branch hasil Design. |
| `agen/android-dev-Codex-Mobile-Native` | Branch hasil Dev. |

## Aktifkan checkout tim

Periksa status dan branch lokal sebelum melakukan perubahan. Dari checkout repo Cloud sendiri:

```bash
git status --short --branch
git fetch origin refs/heads/agen/android-baseline-Codex-Mobile-Native:refs/remotes/origin/agen/android-baseline-Codex-Mobile-Native
git merge-base --is-ancestor 9c1ee23099ae4a5c4758972ddac842d03bcdc552 origin/agen/android-baseline-Codex-Mobile-Native
git show -s --format='%H %s' origin/agen/android-baseline-Codex-Mobile-Native
```

Buat branch kerja tim dari tip baseline yang sudah diperiksa. Contoh Dev: `git switch --no-track -c agen/android-dev-Codex-Mobile-Native origin/agen/android-baseline-Codex-Mobile-Native`. Design memakai nama branch Design di tabel. Jika branch sudah ada lokal atau remote, periksa riwayat dan lanjutkan branch tersebut. Merge baseline bila diperlukan dan selesaikan konflik tanpa membuang pekerjaan. Ikuti `AGENTS.md`, `docs/AGENT_PROTOCOL.md`, `docs/DEVELOPMENT.md`, `docs/HANDOFF.md`, dan [CI selection](../CI_SELECTION.md).

## Arahan Lead untuk kedua tim

Dokumen ini adalah rujukan operasional tetap untuk kedua task. Lead mencatat perubahan strategi, workflow, baseline atau acceptance di sini sebelum meminta tim mengikutinya. Briefing menyebut keputusan, alasan, SHA acuan dan tindakan terpisah untuk Design dan Dev, termasuk bila salah satu scope dapat berjalan seperti sebelumnya. Instruksi pemilik terbaru tetap berlaku. Hasil diskusi antar-agent dan checkpoint disimpan di repo sehingga pemilik dapat berfokus pada keputusan produk dan otorisasi.

Setiap tim mengambil ref baseline bersama pada awal atau saat melanjutkan sesi, sebelum mulai paket baru, dan sebelum menyerahkan checkpoint. Baca file dari ref remote-tracking yang baru di-fetch tanpa mengganti branch kerja:

```bash
git fetch origin refs/heads/agen/android-baseline-Codex-Mobile-Native:refs/remotes/origin/agen/android-baseline-Codex-Mobile-Native
git show origin/agen/android-baseline-Codex-Mobile-Native:docs/android/LOCAL_WORKFLOW.md
```

Catat SHA arahan yang dibaca dalam checkpoint branch tim. Jika perubahan menyentuh pekerjaan aktif, bandingkan base/head, pertahankan commit dan perubahan lokal, lalu selaraskan di checkpoint sebelum memperluas pekerjaan yang terdampak. Laporkan konflik, gap kontrak atau akses beserta SHA di handoff branch tim. Pekerjaan yang independen dapat diteruskan. Lead membaca kedua branch saat review, memberi arahan lanjutan di GitHub, dan memeriksa delta masing-masing.

### Arahan aktif

- **Design:** Lanjutkan DES-00/DES-01 setelah fetch baseline. Pertahankan audit token dan D01-r0. Selesaikan matriks serta mapping yang dapat diverifikasi sambil menunggu tautan Figma. PJP opsi C dan carry-over eksplisit masuk rancangan. Serahkan hasil di branch Design.
- **Dev:** Lanjutkan DEV-01A setelah fetch baseline dan siapkan DEV-01B sesuai bukti yang tersedia. Pekerjaan emulator dapat berjalan paralel dengan Design. Gunakan versi desain yang sudah direview ketika mulai implementasi visual D01. Serahkan hasil di branch Dev dan laporkan bukti per API.
- **Lead:** Review dua checkpoint dari branch GitHub masing-masing. Saat strategi atau workflow berubah, perbarui arahan kedua tim di dokumen ini dan pastikan ref remote menunjuk ke revisi yang sudah diverifikasi. Keputusan produk dan otorisasi tetap diminta dari pemilik sesuai cakupan.

## Penugasan yang dilanjutkan

| Tim | Dependensi dan ruang lingkup | Acceptance checkpoint |
|---|---|---|
| **Design · DES-00/DES-01** | [Job Design](DESIGN_SPEC.md), [Design System](DESIGN_SYSTEM.md), [SSOT](ARCHITECTURE.md), [register backend](BACKEND_REGISTER.md), dan [keputusan PJP/approval terbaru](../ui/BACKLOG_FE_BE.md). Pertahankan audit token dan draf D01-r0. Gunakan 48 dp sebagai target uji sementara. File sumber/library Figma dan akses review diperlukan untuk mencocokkan frame aktual. | Matriks D01-01–05 mencantumkan state, role, route, Rxx/Bxx/DS-Cxx dan acceptance. Mapping token ke Compose dapat direview. Laporkan URL/node/versi dan jumlah frame yang benar-benar diperiksa. PJP opsi C memerlukan status carry-over yang eksplisit. |
| **Dev · DEV-01A, lalu siapkan DEV-01B** | [Job Dev](DEV_SPEC.md), [Android README](../../android/README.md), [SSOT](ARCHITECTURE.md) dan gate lokal. Pertahankan audit pada N1. Toolchain JDK 17, SDK, image emulator dan akselerasi runner diperlukan untuk bukti runtime. | Kandidat smoke untuk API 24 dan 35 mencatat image/ABI, SHA, checksum APK, hasil boot dalam timeout, install, dan Login setelah cold start. Pisahkan bukti boot/install dan UI. DEV-01B menyiapkan Login, navigasi, dan izin. Hasil yang belum dijalankan ditandai [BU]. |

## Serahkan pekerjaan ke Lead melalui GitHub

Kerjakan dan uji di Cloud. Buat commit atomik hanya pada branch tim. Catat base/head, paket, hasil gate, dampak test, bukti, dan blocker dalam entri handoff. Dev memakai `ANDROID_GATE_BASE=39172de900668263676577d843a095bf90065ec2 bash android/tools/integration_gate.sh` untuk baseline ini atau SHA acuan baru yang dikunci Lead.

Push branch tim dengan ref eksplisit, misalnya `git push -u origin HEAD:refs/heads/agen/android-dev-Codex-Mobile-Native` dari branch Dev setelah pemeriksaan diff dan secret. Design memakai ref Design. Checkpoint siap ditinjau ketika SHA dan catatan handoff sudah tersedia pada branch remote. Lead membaca branch dan diff langsung di GitHub. Jika diperlukan PR review terpisah, koordinasikan base dan head dengan Lead sesuai protokol supervisor. Lead menyiapkan kandidat integrasi ke main dari commit yang diterima, setelah menyegarkan main dan memeriksa CI.

Handoff ini memberi jalur kerja dan review. Merge ke main, deployment, serta operasi database persisten memerlukan mandat terpisah.
