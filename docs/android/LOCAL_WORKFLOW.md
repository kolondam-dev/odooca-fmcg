# Panduan kerja lokal tim Android

Instruksi pemilik: seluruh lalu lintas GitHub untuk subproyek Android dikelola Lead. Design dan Dev memakai Git lokal di Cloud. Lead memberikan dua SHA pada setiap handoff: **main acuan** yang terakhir diverifikasi dari GitHub, dan **baseline kerja** yang sudah memuat spesifikasi. Hasil tim diserahkan ke Lead sebagai commit lokal atau bundle. Persetujuan publikasi tetap per milestone.

## Pemeriksaan awal tim

1. Periksa checkout yang benar dengan `git worktree list`, `git status --short --branch`, dan `git rev-parse HEAD`. Periksa objek baseline dengan `git cat-file -e '<SHA baseline>^{commit}'`.
2. Baca `AGENTS.md`, `docs/HANDOFF.md`, `docs/AGENT_PROTOCOL.md`, dan dokumen `docs/android/` pada baseline yang diserahkan. Pakai `git log`, `git show`, `git diff`, dan `git status` untuk pemeriksaan lokal. Skrip `whats_new.sh` melakukan fetch remote dan dijalankan oleh Lead.
3. Jika worktree dan baseline terlihat, gunakan worktree tim yang ditetapkan. Jika checkout menampilkan branch `work` atau SHA lama dan objek baseline belum ada, laporkan path, HEAD, status, dan hasil pemeriksaan objek. Lakukan audit baca-saja yang cocok dengan checkout tersebut sambil menunggu handoff. Dev dapat menginventarisasi JDK/SDK/adb/emulator/KVM dan membaca workflow N1. Design dapat mendata token atau memakai Figma yang sudah diotorisasi.

## Impor bila sesi memakai checkout terpisah

Lead menyiapkan bundle dan mencatat ref tim, SHA baseline, main acuan, prasyarat, serta checksum SHA-256. Pemindahan berkas memakai mekanisme file bersama yang telah dibuktikan atau lampiran yang diberikan pemilik. Nama direktori Cloud yang sama tidak menjamin berkas terlihat di chat lain.

Setelah bundle terlihat di sesi tujuan, jalankan dari repo lokal. Contoh Dev, dengan path absolut dari lokasi lampiran aktual:

```bash
git bundle verify "$BUNDLE"
git fetch "$BUNDLE" refs/heads/agen/android-dev-Codex-Mobile-Native:refs/heads/agen/android-dev-Codex-Mobile-Native
git rev-parse refs/heads/agen/android-dev-Codex-Mobile-Native
git worktree add /workspace/odooca-android-dev agen/android-dev-Codex-Mobile-Native
```

Cocokkan hasil `rev-parse` dengan SHA Lead sebelum membuat worktree. Untuk Design gunakan `agen/android-design-Codex-Mobile-Native` dan `/workspace/odooca-android-design`. `BUNDLE` menunjuk file lokal. Fetch ini membaca berkas lokal tanpa menyentuh `origin`. Perintah pembuatan worktree berlaku bila path belum digunakan. Bila branch tujuan sudah punya pekerjaan, impor ke ref handoff baru, laporkan delta ke Lead dan pertahankan worktree serta commit yang ada. Jika prasyarat bundle hilang, sampaikan SHA yang diminta verifier agar Lead menyiapkan bundle yang cocok.

## Kerja, verifikasi, dan serah terima

- Design mengerjakan DES-00/DES-01 dan D01 sesuai checkpoint. Dev mengerjakan DEV-01A lalu menyiapkan DEV-01B. Cakupan dan acceptance tetap mengikuti spec masing-masing.
- Commit lokal per slice. Catat main acuan, baseline paket, HEAD, file berubah, bukti, blocker, dan cakupan yang belum diverifikasi. Gate lokal menerima main acuan dari Lead: `ANDROID_GATE_BASE=<SHA-main-acuan> bash android/tools/integration_gate.sh`. Flag `--gradle` menambah tes Gradle bila toolchain tersedia. Bukti emulator/CI yang membutuhkan GitHub dijalankan oleh Lead pada kandidat yang disetujui.
- Jika Lead berbagi checkout, serahkan nama branch dan SHA. Jika checkout terpisah, buat bundle hasil dari branch lokal dengan prasyarat baseline tim yang telah disepakati:

  ```bash
  git bundle create "$HANDOFF_BUNDLE" refs/heads/agen/android-dev-Codex-Mobile-Native "^$TEAM_BASELINE"
  git bundle verify "$HANDOFF_BUNDLE"
  sha256sum "$HANDOFF_BUNDLE"
  ```

  Gunakan nama branch Design untuk hasil Design. `HANDOFF_BUNDLE` menunjuk nama file tujuan lokal. Lead mengimpor hasil ke ref review terpisah, memeriksa lineage dan full SHA, lalu mengintegrasikan commit yang diterima.
- Jika sesi tidak punya jalur file bersama, beri tahu pemilik dan Lead bahwa impor menunggu lampiran. Sementara itu, kirim laporan dan bukti yang dapat dibaca langsung di chat. Jalur GitHub tetap melalui Lead.
