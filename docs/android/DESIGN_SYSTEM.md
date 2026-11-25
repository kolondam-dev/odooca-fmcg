# Design system Odooca Field Android

Spesifikasi untuk Codex-Android-Design dan Codex-Android-Dev. Status: baseline engineering untuk review pemilik. Nilai bertanda usulan harus melalui review visual dan uji perangkat sebelum menjadi standar. Pendamping [SSOT](ARCHITECTURE.md), [spesifikasi Design](DESIGN_SPEC.md), dan [spesifikasi Dev](DEV_SPEC.md).

## 1. Sumber, hierarki, dan kepemilikan token

| Tingkat | Contoh dan aturan | Sumber perubahan |
|---|---|---|
| Primitif bersama | `color.base.ink`, `color.brand.nav`, `spacing.4`, skala tipografi. Nilai aktual dibaca dari `pwa/design/tokens.json`. | Perubahan bersama direview maintainer PWA dan Android. |
| Semantik Android | `color/text/default`, `color/surface/canvas`, `color/status/pending/fg`, `size/target/min`. Alias berarti tujuan penggunaan dan pasangan foreground/background. | Design mendefinisikan peran, Dev memastikan mapping Material dan Compose, Lead menyelesaikan perubahan lintas platform. |
| Komponen | `button/primary/container`, `evidence/status/error`. Alias semantik hanya ditambahkan jika pola membutuhkan kontrak stabil. | Design dan Dev menyetujui nama, varian, nilai fallback, dan pemakaian. |

Repositori menyimpan nilai bersama dan mapping versi. Figma menyimpan representasi Library, state, dan prototype. Generator saat ini menghasilkan `Tokens.kt` dari sumber bersama. Perubahan pada primitives atau generator harus membawa diff sumber dan hasil regenerasi yang deterministik. Untuk alias Android yang belum tercakup generator, gunakan definisi terpusat di design system. Feature tidak mendefinisikan salinan token atau mengganti file hasil generate secara manual.

### Color dan state

| Peran semantik | Dasar aktual | Penggunaan |
|---|---|---|
| Text/default dan secondary | `base.ink #0B1F4D`, `base.mute #52647A` | Teks utama dan keterangan pada surface terang. |
| Canvas, surface, divider | `base.bg #F7F9FC`, `base.surface #FFFFFF`, `base.line #E6ECF3`, `base.border #C5D2E0` | Latar, kartu, pembatas, dan outline. Cek field boundary dengan kontras aktual. |
| Primary dan navigation | `brand.primary #1B5E8C`, `brand.nav #001A57`, `brand.navFg #DCE6F5` | Primary action dan navigasi. Putih pada primary mengikuti tema Compose saat ini. |
| Accepted | `status.ok #11663F` / `okBg #E7F6ED` | Receipt resmi yang diterima. Beri teks status dan referensi jika ada. |
| Hold atau approval | `status.warn #7A4B00` / `warnBg #FDF0D5` | Perlu tindakan atau keputusan. Status approval ditulis lengkap. |
| Rejected atau error | `status.bad #B42318` / `badBg #FDE8E6` | Bedakan pesan gagal kirim dan penolakan resmi. Tampilkan alasan yang aman. |
| Info dan neutral | `status.info #17537E` / `infoBg #E5F0F8`, `neutral #3F5068` / `neutralBg #EAEFF5` | Sinkronisasi, draft atau antrean. Status offline persisten dengan keterangan asal data. |

Baseline pertama mengikuti tema terang yang ada. Dark mode, dynamic color dan varian high-contrast menjadi keputusan terpisah. Ukur pasangan aktual termasuk ikon, focus, scrim, dan status pada foto. Usulan acceptance WCAG AA: 4.5:1 untuk teks biasa, 3:1 untuk teks besar dan batas/ikon yang diperlukan untuk memahami kontrol. Warna dilengkapi teks, ikon, atau bentuk.

### Tipografi, ukuran, dan responsivitas

- Inter adalah sumber desain. Verifikasi font Android yang benar-benar termuat di APK, lisensi, fallback sistem, dan keterbacaan angka. Gunakan `sp` untuk teks dan `dp` untuk layout. Role inti dari sumber: caption 13/18, label 13/18, body 15/22, input 16/24, title 18/24, heading 20/28, display 26/34. Angka adalah size/line-height sumber.
- Spacing bersama 4/8/12/16/20/24. Radius bersama 8/10/14/20. Target sentuh Android **usulan minimum 48 dp** untuk aksi interaktif; token sumber 44 dipertahankan untuk platform asal. Area sentuh dapat melebihi visual control selama hitbox tidak bertumpuk.
- Desain dan uji lebar compact sekitar 320 dan 360 dp, referensi 390 dp, serta expanded mulai 600 dp sebagai target awal pengujian adaptif. Gunakan window/insets runtime, posisi keyboard, cutout dan gesture bar. Pada font 200%, status, nilai uang dan tombol utama tetap terbaca dan dapat dijangkau dengan scroll. Orientasi, split-screen dan landscape masuk matriks, dengan prioritas layar lapangan.
- Tetapkan pola elevation untuk pemisahan surface, sheet dan dialog, serta ikon keluarga yang sama dengan aset yang sudah disetujui. Ikon status punya label, ikon dekoratif dikecualikan dari TalkBack. Motion pendek dan dapat dikurangi. Haptics hanya untuk aksi yang punya makna dan dihormati pengaturan sistem.

## 2. Katalog komponen dan kontrak Compose

Nama Compose di bawah ini adalah nama rancangan, cek komponen existing sebelum menambah API. Varian diturunkan dari state yang benar-benar dipakai. Tes preview dan semantics menutupi tiap varian rilis.

| ID | Komponen dan varian yang wajib | Kontrak penggunaan |
|---|---|---|
| DS-C01 | `FieldTopBar`, `FieldNavigation`: root/back, top/bottom, role, selected, badge | Role dari server, rute tetap, selected terucap. Saat capability dicabut, keluar dari rute dengan alasan. |
| DS-C02 | `FieldButton`: primary/secondary/tertiary/destructive, enabled/pressed/focused/busy/disabled | Satu aksi utama per region; busy menahan tap ulang; aksi disabled punya alasan terbaca bila penyebab relevan. |
| DS-C03 | `FieldInput`: teks, angka, PIN/password, mata uang, multiline, valid/error/read-only | Label permanen, pesan kesalahan berdekatan, IME/focus sesuai aksi. Password tidak masuk log. |
| DS-C04 | `StatusChip`, `InlineNotice`, `ConnectivityBanner`: status lokal dan server | Status memakai label lengkap. Network, sesi dan keputusan transaksi punya state terpisah. |
| DS-C05 | `ListRow`, `OutletCard`, `SummaryRow`: skeleton, data, empty, incomplete, restricted | Nilai yang belum tersedia memakai label yang sesuai. Nilai nol berasal dari data valid. |
| DS-C06 | `Sheet`, `ConfirmationDialog`: info, pilih opsi, destructive, blocked | Back menutup lapisan teratas dan mengembalikan focus. Konfirmasi hanya untuk konsekuensi penting. Form kompleks memakai screen. |
| DS-C07 | `LocationPanel`: unknown, permission denied, acquiring, low accuracy, outside, valid for display | Menampilkan akurasi dan instruksi pemulihan. Peta memberi konteks dan hanya receipt server mengesahkan aktivitas resmi. |
| DS-C08 | `EvidenceCapture`: ready, permission denied, preview, retake, queued, failed, expired | Satu paket bukti terikat konteks. Preview privat, tanpa data sensitif pada screenshot review. Retake menghormati status command. |
| DS-C09 | `QueueRow`, `ReceiptPanel`: local, blocked, sending, auth, approval, accepted, rejected | UI memakai state domain; tampilkan aksi retry hanya saat sah, tampilkan referensi server bila tersedia. |
| DS-C10 | `QuantityStepper`, `MoneySummary`, `FilterBar`: default, batas, invalid, read-only | Pertahankan unit karton/pack/pcs dan angka Rupiah. Label estimasi sampai server memberi angka resmi. |
| DS-C11 | `EmptyState`, `ErrorState`, `LoadingState` | Fallback dapat dinavigasi tanpa kehilangan draft. Error hanya menyarankan tindakan yang nyata. |

### Bahasa dan status operasional

| Sumber state | Label pengguna | Aksi yang disediakan |
|---|---|---|
| Draft tersimpan | Draf tersimpan di perangkat | Lanjutkan atau buang draf dengan aturan yang berlaku. |
| Antrean dan dependency | Menunggu jaringan / Menunggu bukti | Detail penyebab. Retry tersedia ketika syarat terpenuhi. |
| Sending | Sedang mengirim | Cegah pengiriman ulang dari aksi yang sama. |
| AUTH_REQUIRED | Masuk kembali untuk mengirim | Login akun asal. Antrean akun lain tetap terisolasi. |
| Receipt needs_approval | Menunggu persetujuan | Tampilkan referensi, konteks dan histori yang diizinkan. |
| Receipt accepted/rejected | Diterima server / Ditolak server | Tampilkan referensi atau alasan, dan koreksi/resubmit bila capability tersedia. |

Waktu aksi `HH.mm.ss` WITA. Jam rencana masih menunggu keputusan akhir pemilik. Lokalisasi Indonesia mencakup unit, Rp, pesan izin, singkatan FMCG, plural dan deskripsi aksesibilitas. Error server mentah dipetakan ke pesan yang aman. Hindari ikon atau toast sebagai satu-satunya pemberitahuan penting.

## 3. Figma, handoff, dan versioning library

| Halaman | Keluaran |
|---|---|
| 00 Product Map | Pemetaan ID Android ke frame sumber dan rute, aktor, alur, milestone serta blocker. |
| 01 Foundations | Collections untuk primitives, semantic dan kebutuhan Android, pasangan kontras dan skala adaptif. |
| 02 Components | Komponen editable, Auto Layout, variables/bindings, varian prioritas, fokus dan dokumentasi properties. |
| 03 Patterns | Form, navigasi, aksesibilitas, izin perangkat, kamera, state offline dan receipt. |
| 04 Workflows | Prototype per alur dan fixture desain yang jelas, termasuk jalur gagal. |
| 05 Review & Decisions | Versi kandidat, komentar pemilik, keputusan, link issue dan resolusi. |
| 99 Deprecated | Komponen lama dengan pengganti dan catatan migrasi. |

Plugin Figma telah terhubung. Baseline file, library bersama dan izin publikasi masih menunggu tautan/akses. Setelah file ditetapkan, inventarisasi existing styles/variables/components, lalu bangun library secara bertahap. Gunakan Penpoint sebagai jalur review tambahan bila workspace dan integrasinya dipastikan. Umpan balik pemilik selalu dapat ditelusuri ke node/versi dan catatan keputusan repo.

Handoff setiap komponen memuat ID, node, versi, pemilik, token, semua state terkait, perilaku resize/focus, referensi Compose, dan bukti. Gunakan perubahan major untuk kontrak komponen yang memerlukan migrasi, minor untuk penambahan kompatibel, dan patch untuk koreksi tanpa perubahan kontrak. Gerbang publikasi library memerlukan review pemilik dan lead, contoh penggunaan, pemeriksaan kontras, serta rencana migrasi feature yang terdampak.
