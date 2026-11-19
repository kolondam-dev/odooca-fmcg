# Spesifikasi Codex-Android-Design

Acuan: [SSOT](ARCHITECTURE.md). Tim desain memiliki inventaris layar, state model UX, token/komponen dan referensi prototipe. Tim memegang keputusan visual setelah review pemilik. Perubahan urutan bisnis, otorisasi, status resmi dan data yang diperlukan diproses bersama lead serta backend.

## Paket pertama D01 — dari Login sampai receipt kunjungan

| ID | Layar/kelompok | State yang wajib dirancang | Requirement |
|---|---|---|---|
| D01-01 | Login dan pemulihan sesi | Awal, proses, kredensial salah, offline, expiry, ganti akun dengan antrean pending. | R01/R02 |
| D01-02 | Beranda dan sinkron | Memuat, snapshot siap, retry, hari WITA berubah, scope salah, PJP kosong sah, kemampuan Extra call/NOO tersedia atau ditahan. | R01/R03 |
| D01-03 | Outlet dan hub kunjungan | Terjadwal, selesai, kosong, tanpa data AR, kemampuan kunjungan/order terkunci dengan sebab. | R03/R06 |
| D01-04 | Lokasi dan kamera | Izin kontekstual, ditolak/dicabut, provider mati, fix usang, akurasi rendah, di luar radius, foto/retake, storage penuh. | R04/R07 |
| D01-05 | Antrean dan hasil | Draft lokal, menunggu evidence/jaringan, mengirim, perlu login, diterima, butuh approval, ditolak; tampilkan aksi pemulihan yang sah. | R02/R05/R06 |

Keluaran pertama: flow diagram, prototype clickable, frame dan varian untuk tabel di atas, serta matriks ID → route → role → state → capability/dependency → frame → acceptance. Gunakan fixture fiktif untuk prototype. Status resmi dari receipt ditampilkan dengan teks dan semantik yang jelas. Review pada perangkat kecil, font besar, keyboard terbuka, TalkBack, tombol sistem Back dan target sentuh. Waktu kejadian `HH.mm.ss` WITA. Simpan draft saat navigasi kembali sesuai workflow.

## Library desain dan review pemilik

- Figma: buat halaman Product Map, Foundations, Components, Workflows, dan Review. Gunakan variables semantik untuk surface/text/action/status, component variants dan auto layout. Dokumentasikan Android insets, typography, density, spacing, dan fallback aset. Token bersama yang berubah diajukan ke maintainer PWA dan ditelusuri hingga regenerasi `Tokens.kt`.
- Setiap handoff mencatat URL/node, versi desain, ID alur, perubahan dari versi yang direview, state, serta contoh atau screenshot Compose yang diharapkan. Capture feedback pemilik melalui komentar pada frame. Catat resolusi dan keputusan yang diterima di repo, bersama tautan atau ekspor review yang diizinkan. Perubahan setelah persetujuan memerlukan delta review.
- Gunakan plugin Figma setelah koneksi dan akses file tersedia, untuk komponen editable, iterasi prototipe, dan feedback. Penpoint dapat dipakai untuk pencatatan review setelah konektor/akses terverifikasi. Git menyimpan keputusan, traceability dan aset ekspor yang disetujui. Figma menyimpan desain visual dan komentar.
- Handoff diterima ketika state matrix lengkap, token dapat dipetakan ke Compose, blocker bertaut ke B01–B09, dan keputusan pemilik tertelusur. Status yang belum disetujui diberi tanda review pending.

Setelah D01, perluas ke order, manifest/POD/closing, penagihan/kas, lalu HRIS dan activity mengikuti capability yang tersedia.
