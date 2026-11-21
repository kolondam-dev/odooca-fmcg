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

### Review Lead — DES-00/DES-01 D01-r1

**Diterima sebagai checkpoint dokumentasi** pada Design HEAD `37d97ebbff83fdc1a8dcc9edd98bbd9943482b45`, parent arahan `92da15d` dan main acuan `39172de`. [Checkpoint D01-r1](https://github.com/kolondam-dev/odooca-fmcg/blob/37d97ebbff83fdc1a8dcc9edd98bbd9943482b45/docs/android/DES01_D01_CHECKPOINT.md) siap menjadi referensi untuk perencanaan UI dan tes. Lead menjalankan ulang gate statis pada SHA penuh, memeriksa 22 ID unik dan trace/link, serta menghitung ulang pasangan kontras. **Dampak test: CUKUP** untuk perubahan dokumentasi ini. Penerimaan visual, perangkat dan runtime Odoo tetap di milestone masing-masing.

- **Design:** lanjutkan bagian DES-02 yang bisa diverifikasi, termasuk varian komponen, fokus, status receipt dan target uji 48 dp. Pertahankan status 0/62 frame diperiksa sampai file sumber/library dan area review Figma ditetapkan. Navy, label dan format jam rencana tetap untuk review pemilik. Waktu kejadian tetap `HH.mm.ss` WITA.
- **Dev:** lanjutkan DEV-01A/01B tanpa menunggu Figma. Pakai D01-r1 untuk memetakan tes, dengan scope smoke tetap berjalan pada layar yang tersedia. Implementasi visual D01 memakai frame/versi yang diterima. Saat mengerjakan D01-05c/d, gunakan counterexample receipt 2xx dengan UUID cocok dan status yang tidak dikenal. Source saat ini memetakan status di luar `accepted`/`needs_approval` ke `REJECTED`. UI hanya boleh menampilkan penolakan resmi untuk receipt `rejected` yang valid. Arahkan status tak dikenal ke state kendala protokol/review, dan uji pembedaan dengan receipt bisnis valid, 403 tanpa receipt, dan respons yang gagal diparse. Scope tes repository/API dan Compose masuk slice D01 terkait, terpisah dari smoke emulator.
- **Dependensi:** jalur resmi PJP opsi C, carry-over, absensi dan AR tetap bergantung pada B03/B04/B07. Persetujuan checkpoint ini memberi jalur lanjut desain dan perencanaan tes. Perubahan kode, freeze desain dan integrasi membutuhkan bukti sesuai gate masing-masing.

### Review Lead — DEV-01

**HOLD untuk acceptance runtime** pada Dev HEAD `dcad2156ee918a264aa93c71f63835306c25069a`. [Diff checkpoint](https://github.com/kolondam-dev/odooca-fmcg/compare/92da15d...dcad2156ee918a264aa93c71f63835306c25069a). Lead menjalankan gate statis pada SHA tersebut, Bash syntax dan uji host laporan instrumentation untuk hasil absen, lulus dan duplikat. Hasil gate: Ruff, 14 manifest, 29 tes kontrak CI dan token lulus. Planner memilih full regression, 11 suite, karena workflow dan tes control plane berubah. Build APK dan tes Kotlin yang dilaporkan Dev merujuk sumber `9d51fb8`. Gate Gradle penuh serta bukti API 24/35 belum tersedia.

**Dampak test: TAMBAH.** Gate lama membuktikan build, lint, domain dan data. Kelas baru perlu bukti yang membedakan APK terpasang dari aplikasi benar-benar mencapai Login setelah cold start dan mampu menjalankan flow awal. Pertahankan emulator opt-in dan required context yang ada. Jalankan smoke API 24/35 dahulu pada SHA kandidat, lalu UI instrumentation bila smoke lulus di keduanya. Lampirkan hasil KVM, image revision, SHA, hash APK, boot/install, Login dan laporan UI. Android required gate dan full regression harus dibuktikan sesuai planner pada kandidat integrasi terkini.

- **Dev:** pertahankan scope DEV-01 dan commit yang ada. Belum ada run GitHub untuk checkpoint saat ditinjau. Dispatch oleh Lead lewat GH CLI menerima `Forbidden` saat akses endpoint workflow; akses melalui Cloud Desktop juga belum tersedia. Bukti lokal tidak menutup acceptance emulator. DEV-02A dan perluasan visual D01 tetap di luar checkpoint.
- **Design:** lanjutkan DES-02 dan pekerjaan yang independen dari emulator. Ref Design kini `6abeef3a7c3a8ecb232854efbd4e6e948308b78d` dengan parent dan tree identik dengan checkpoint `37d97eb`; perubahan metadata tidak mengubah verdict DES-00/DES-01. File/library Figma dan penerimaan visual tetap terbuka.

### Arahan Lead — toolchain main setelah PR #173

Main acuan untuk **kandidat integrasi DEV-01 berikutnya** adalah `127287a`, yang memuat [PR #173](https://github.com/kolondam-dev/odooca-fmcg/pull/173): AGP 9.5.1, Gradle 9.9.1, Kotlin 2.4.21 dan compileSdk 37. `targetSdk` tetap 35. Pemasangan SDK di workflow memakai paket `platforms;android-37.0`. API emulator 24/35 tetap menjadi matriks acceptance runtime.

- **Dev:** pertahankan checkpoint `dcad2156ee918a264aa93c71f63835306c25069a` sebagai bukti historis. Sinkronkan kandidat DEV-01 terhadap main ini dan selaraskan workflow, SDK install dan pin wrapper dalam skrip serta tes dengan toolchain yang sudah di-merge. Pertahankan emulator opt-in, required gate, dan acceptance per API. Catat SHA kandidat dan hasil pemeriksaan; DEV-02A masih di luar scope. Gate lokal menggunakan SHA main baru. Acceptance runtime tetap HOLD dan full regression berjalan pada SHA integrasi.
- **Design:** checkpoint draft DES-02-r0 pada `0f2739c7904fc4674b0e66ec83f78aefba2f60b0` sudah terlihat. Lanjut review visual dan dokumentasikan keputusan Figma. Upgrade toolchain tidak menghentikan alur ini. Approval visual dan inventaris frame sumber tetap mengikuti review pemilik.
- **Akses Actions:** pada pemeriksaan Lead, whitelist `api.github.com` belum efektif pada instance yang sedang berjalan dan koneksi HTTPS ditolak proxy dengan 403. Lead memverifikasi jaringan dan akses Actions setelah pengaturan instance aktif.

### Review Lead — DEV-01 pada toolchain PR #173

**HOLD untuk runtime** pada kandidat `7bcd5aab839092b96de862be1b2b045fb0ceab2f`, `refs/heads/agen/android-dev-Codex-Mobile-Native`. Parent kandidat adalah checkpoint Dev `dcad215` dan main `69c6e053a02870fa28ee4d8e45bfebbda125e588`. [Definisi workflow pada SHA kandidat](https://github.com/kolondam-dev/odooca-fmcg/blob/7bcd5aab839092b96de862be1b2b045fb0ceab2f/.github/workflows/android.yml). Lead menjalankan gate statis pada SHA penuh: Ruff, 14 manifest, 30 tes kontrak CI, Bash syntax dan token lulus; semua job Android yang dimiliki main identik pada kandidat. Job tambahan hanya smoke opt-in API 24/35. Planner memilih full regression (11 suite).

**Dampak test: TAMBAH.** Instalasi yang berhasil dapat terjadi tanpa tampilnya Login. Matriks harus membuktikan boot, instalasi, cold start dan Login pada kedua API serta menyimpan bukti SHA, hash APK dan image. Instrumentation menyusul setelah dua smoke lulus. Gate statis dan build lokal belum membuktikan runtime atau lint/Robolectric yang tertahan mirror Maven.

Untuk Lead yang memiliki akses Actions, verifikasi identitas berizin `Actions: write`, status workflow aktif, dan ref Dev menunjuk SHA di atas sebelum dispatch. `main` memiliki `android.yml` tetapi belum memuat input emulator, jadi gunakan **ref workflow branch Dev** dan pin checkout ke SHA kandidat. Jalankan Android dengan `force_all=true`, `emulator_smoke=true`, `emulator_ui=false`. Setelah kedua API lulus, ulangi dengan `emulator_ui=true`. Verifikasi `android-gate` pada run Android dan jalankan `full-regression.yml` dengan input `ref` SHA yang sama, `purpose=audit`. Full Regression Gate tidak memanggil suite Android, sehingga bukti Android harus diverifikasi tersendiri. Catat run ID, SHA checkout dan hasil per job; status penerimaan hanya berubah setelah bukti sah. Sesi Lead ini masih menerima 403 dari proxy pada `api.github.com`; akses metadata Lead lain belum membuktikan izin dispatch. Belum ada dispatch yang terverifikasi dari sesi ini.

- **Dev:** checkpoint sudah diterima untuk penjadwalan pengujian. Pertahankan SHA dan scope DEV-01 selama penerimaan. DEV-02A dan perluasan visual D01 menunggu checkpoint berikutnya.
- **Design:** lanjutkan DES-02 dan review desain secara paralel. Referensi Penpot dan dua foto check-in tetap di jalur desain; pekerjaan kontrak bukti dan implementasi visual berada di luar DEV-01.

### Arahan Lead — integrasi DEV-01A/01B

- **Lead:** Integrasikan checkpoint Dev `7bcd5aab839092b96de862be1b2b045fb0ceab2f` dengan main `69c6e053a02870fa28ee4d8e45bfebbda125e588` pada `agen/android-integration-dev-01-Codex-Mobile-Native`. [Draft PR #177](https://github.com/kolondam-dev/odooca-fmcg/pull/177) memakai SHA integrasi `27d74284c86d536836be369cd383417c094bb3fb`. Gate statis Lead lulus dan planner memilih 11 suite. PR memicu CI wajib. Lead memeriksa hasil pada SHA PR. Smoke dan instrumentation API 24/35 tetap bukti acceptance terpisah. **Dampak test TAMBAH** sesuai review DEV-01. Runtime tetap HOLD.
- **Dev:** Handoff diterima dan Lead mengambil alih integrasi. Pertahankan checkpoint; tindak lanjut implementasi menunggu temuan yang spesifik dari CI atau pengujian runtime. DEV-02A dan implementasi visual D01 berada di luar PR ini.
- **Design:** Lanjutkan review DES-02-r1 pada checkpoint `46788ad0b0fdded5f8c0c1107e7058ac6ffcf1d0` dan catat versi/node serta hasil review visual. Dua foto check-in tetap memerlukan review binding B02/B09 dengan Lead dan maintainer. Pekerjaan DES-02 berjalan paralel; checkpoint desain belum masuk PR DEV-01.

### Tindak lanjut CI — PR #177

- **Dev:** Tindak lanjuti kegagalan [domain-tests](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/44857861509/job/136704210173) pada kandidat Lead `27d7428`. Gradle melaporkan `:core:domain:test FROM-CACHE`, lalu validator gagal karena `contract-samples/check_in.json` hilang. Task saat ini memasok lokasi lewat `contract.out` tanpa mendeklarasikan direktori sampel sebagai output. Buktikan reproduksi cache hit pada checkout bersih dan bahwa tiga sampel dipulihkan serta validator OpenAPI lulus setelah perbaikan. Pertahankan assertion, gate dan scope. Serahkan SHA perbaikan di branch Dev dengan bukti cold run dan cache hit.
- **Design:** Lanjutkan DES-02-r1 sesuai arahan di atas. Temuan Gradle tidak mengubah checkpoint desain.
- **Lead:** PR tetap draft. Data tests lulus, build dilewati, dan android-gate gagal karena domain-tests. Lead mengintegrasikan SHA perbaikan dan memeriksa ulang CI. Bukti emulator tetap HOLD.

### Review Lead — perbaikan cache domain PR #177

- **Lead:** Perbaikan Dev `f23ea50204d13f018bc40872c01ce3b4d5bf288e` terintegrasi pada `a74613c5d3295a5fc706c57de393328fe4e7f2e9`. Gate statis lulus dan planner memilih 11 suite. **Dampak test CUKUP** untuk delta cache: bukti Dev mencakup reproduksi sampel hilang, cold run dan pemulihan ketiga sampel identik dari cache lintas checkout. [CI PR #177](https://github.com/kolondam-dev/odooca-fmcg/pull/177/checks) memverifikasi SHA integrasi. Runtime API 24/35 tetap HOLD.
- **Hasil CI Android:** [Run 44873451351](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/44873451351) lulus untuk domain dan validator OpenAPI, data, lint/build serta required android-gate. Pemeriksaan lintas suite PR dan bukti emulator masih terbuka.
- **Dev:** Tindak lanjut cache selesai. Lanjutkan hanya jika ada temuan baru.
- **Design:** Lanjutkan review DES-02-r1 dan catat hasil di branch Design.

### Tindak lanjut Lead — smoke API 24/35 pada PR #177

- **Lead:** Dispatch GitHub berhasil pada `a74613c5d3295a5fc706c57de393328fe4e7f2e9`. [Run 44881381326](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/44881381326) membuktikan akses KVM dan instalasi SDK pada kedua runner. Kedua job berhenti sebelum boot: `sdkmanager` memasang platform-tools 37.0.3 sedangkan skrip mensyaratkan 37.0.1. Artefak diagnostik tersedia untuk API 24 dan 35. Runtime HOLD; instrumentation menyusul setelah kedua smoke lulus.
- **Dev:** Selaraskan provisioning dan pin toolchain. Periksa juga revisi emulator dan image kedua API yang belum dicapai pemeriksaan. Pertahankan validasi revisi dan bukti per tahap, lalu serahkan SHA dan hasil verifikasi.
- **Design:** Lanjutkan DES-02-r1 secara paralel.

## Penugasan yang dilanjutkan

| Tim | Dependensi dan ruang lingkup | Acceptance checkpoint |
|---|---|---|
| **Design · DES-00/DES-01** | [Job Design](DESIGN_SPEC.md), [Design System](DESIGN_SYSTEM.md), [SSOT](ARCHITECTURE.md), [register backend](BACKEND_REGISTER.md), dan [keputusan PJP/approval terbaru](../ui/BACKLOG_FE_BE.md). Pertahankan audit token dan draf D01-r0. Gunakan 48 dp sebagai target uji sementara. File sumber/library Figma dan akses review diperlukan untuk mencocokkan frame aktual. | Matriks D01-01–05 mencantumkan state, role, route, Rxx/Bxx/DS-Cxx dan acceptance. Mapping token ke Compose dapat direview. Laporkan URL/node/versi dan jumlah frame yang benar-benar diperiksa. PJP opsi C memerlukan status carry-over yang eksplisit. |
| **Dev · DEV-01A, lalu siapkan DEV-01B** | [Job Dev](DEV_SPEC.md), [Android README](../../android/README.md), [SSOT](ARCHITECTURE.md) dan gate lokal. Pertahankan audit pada N1. Toolchain JDK 17, SDK, image emulator dan akselerasi runner diperlukan untuk bukti runtime. | Kandidat smoke untuk API 24 dan 35 mencatat image/ABI, SHA, checksum APK, hasil boot dalam timeout, install, dan Login setelah cold start. Pisahkan bukti boot/install dan UI. DEV-01B menyiapkan Login, navigasi, dan izin. Hasil yang belum dijalankan ditandai [BU]. |

## Serahkan pekerjaan ke Lead melalui GitHub

Kerjakan dan uji di Cloud. Buat commit atomik hanya pada branch tim. Catat base/head, paket, hasil gate, dampak test, bukti, dan blocker dalam entri handoff. Dev memakai `ANDROID_GATE_BASE=39172de900668263676577d843a095bf90065ec2 bash android/tools/integration_gate.sh` untuk baseline ini atau SHA acuan baru yang dikunci Lead.

Push branch tim dengan ref eksplisit, misalnya `git push -u origin HEAD:refs/heads/agen/android-dev-Codex-Mobile-Native` dari branch Dev setelah pemeriksaan diff dan secret. Design memakai ref Design. Checkpoint siap ditinjau ketika SHA dan catatan handoff sudah tersedia pada branch remote. Lead membaca branch dan diff langsung di GitHub. Jika diperlukan PR review terpisah, koordinasikan base dan head dengan Lead sesuai protokol supervisor. Lead menyiapkan kandidat integrasi ke main dari commit yang diterima, setelah menyegarkan main dan memeriksa CI.

Handoff ini memberi jalur kerja dan review. Merge ke main, deployment, serta operasi database persisten memerlukan mandat terpisah.
