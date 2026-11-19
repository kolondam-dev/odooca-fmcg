# Spesifikasi Codex-Android-Design

Tim Design memiliki inventaris layar, design system, prototype, dan handoff visual. Prinsip dan requirement berlaku dari [arsitektur](ARCHITECTURE.md). Kontrak token, komponen, aksesibilitas dan library ada di [DESIGN_SYSTEM](DESIGN_SYSTEM.md). Tim Design memutuskan proposal visual bersama pemilik. Perubahan aturan bisnis, otorisasi, status resmi dan data diputuskan bersama lead dan maintainer backend.

## Paket kerja dan deliverable

| Paket | Pekerjaan | Keluaran dan gerbang |
|---|---|---|
| DES-00 Inventaris | Cocokkan prototype 62 layar dan DS dengan K1–K33, PWA terbaru, source Android, dan capability Odoo. Simpan perbedaan sebagai keputusan atau gap. | Daftar frame aktual, ID, peran, rute masuk/keluar, state, source, requirement, capability, blocker, milestone, acceptance dan status review. Jumlah 62 merujuk inventaris sumber; varian Android bisa bertambah. |
| DES-01 Foundations | Tetapkan token dan alias, grid responsif, tipografi, iconography, konten WITA, warna status dan aksesibilitas. | Library Figma dan mapping Compose direview. Cek kontras, inset, ukuran sentuh dan font scale. |
| DES-02 Komponen inti | Rancang DS-C01–C09, prototype komponen dan varian status. Mulai shell, tombol, input, banner, list dan receipt. | Auto Layout, variables, properties, contoh penggunaan, semua state relevan. Dev menyepakati kontrak Compose. |
| D01 Alur kunjungan | Rancang alur pertama dan cabang pemulihan pada tabel berikut. | Flow diagram, prototype clickable, panel review, referensi node dan versi, checklist acceptance dari pengguna. |
| D02 Kehadiran dan hari kerja | Absen masuk/pulang, status GPS/kamera, menunggu bukti, sinkron harian, pergantian tanggal, hari nonkerja, tanpa PJP. | Urutan membuka sesi sesuai R03 dan server. Bedakan absensi lokal dan resmi. Capability B03/B04 mengikat aksi. |
| D03 Sales | Katalog/search/empty, pemilihan outlet, satuan/qty, stok, harga estimasi, diskon, review SO, approval, receipt, koreksi, display stok, NOO/Extra call. | Flow terpisah per capability legacy/v2. Review penagihan sebagai prasyarat order hanya bila aturan dan feed server mendukung. |
| D04 Delivery | Manifest/DO, navigasi, detail item, partial/reject/pending, POD, tanda tangan bila didukung, closing trip. | Counterexample bukti salah DO dan manifest kosong, peran driver/Canvasser, pending approval dan receipt resmi. |
| D05 Cash dan HRIS | Penagihan/allocations/sisa/janji bayar, expense/setoran, cuti/slip, activity dan diagnostics. | Tampilkan data privat sesuai role, state akses ditolak dan capability unavailable. Review angka dan istilah dengan pemilik domain. |
| D06 Adaptasi dan pilot | Review device minimum, font scale, TalkBack, keyboard, safe area, orientasi yang didukung, jaringan lambat dan outdoor. | Checklist aksesibilitas, perbandingan Figma vs screenshot Compose per perangkat, catatan dissent dan release sign-off visual. |

## D01 dari Login sampai receipt kunjungan

| ID | Alur | State wajib dan kriteria penerimaan | Trace |
|---|---|---|---|
| D01-01 | Launch → Login → sesi | Belum login, validasi, loading, salah login, offline, sesi kedaluwarsa, ganti akun dengan draft pending. Pengguna paham antrean hanya dipulihkan lewat akun asal. | R01/R02, B01, DS-C02/C03/C04 |
| D01-02 | Beranda → sinkronisasi | Memuat, snapshot siap, gagal/ulang, hari WITA berubah, scope salah, offline dengan cache yang masih sah, PJP kosong sah. Beranda tetap terbuka ketika penanda PJP kosong sah tersedia. Opsi C: tanpa sesi PJP secara default; carry-over yang disetujui Supervisor harus tampak sebagai carry-over. Extra call/NOO mengikuti capability dan status approval. | R01/R03, B03/B04, DS-C01/C04/C11 |
| D01-03 | Outlet → detail → hub | List terjadwal, selesai, kosong, AR tidak tersedia, outlet tak lagi berwenang. Aksi kunjungan/order menunjukkan sebab ketika ditahan. Jarak estimasi memberi label sesuai sumber. | R03/R06, B03/B07, DS-C05 |
| D01-04 | Check-in → lokasi/foto → simpan | Izin ditolak/dicabut, provider mati, fix stale, low accuracy, di luar radius, retake, penyimpanan penuh, kamera gagal. Satu paket bukti diikat ke konteks yang benar. Back menjaga draf sesuai workflow. | R04/R07, B02, DS-C06/C07/C08 |
| D01-05 | Check-out / antrean → receipt | Draft, blocked dependency, queued, sending, perlu login, diterima, perlu approval, ditolak, gagal sementara dan respons ambigu. Tampilkan asal status, referensi resmi dan aksi pemulihan. Waktu kejadian berdetik di WITA. | R02/R05/R06/R07, DS-C04/C09 |

Jalur prototype wajib: happy path dengan receipt, offline → reconnect, pergantian akun saat pending, izin ditolak, GPS kurang akurat, snapshot kedaluwarsa, dan penolakan bisnis. Alur D01 dapat didesain sebelum seluruh kontrak tersedia dengan menandai fixture dan kemampuan yang masih ditahan. Koordinasikan D01-04 dengan dukungan perangkat nyata.

## Format inventaris dan serah terima

Satu baris per state yang punya perilaku berbeda. Kolom wajib: ID frame Figma, ID Android, rute, role, trigger masuk, aksi utama/sekunder, berikutnya dan Back, data/asal, fallback, capability/Bxx, analytics yang diizinkan bila dibutuhkan, Rxx, test ID, versi dan keputusan review. Gunakan data fiktif. Foto asli, lokasi presisi dan data pelanggan/pengguna tetap di luar prototype publik.

Review setiap paket dimulai dari flow dan terminologi, dilanjutkan komponen serta layout, lalu prototype dan edge case. Pemilik dapat memberi komentar langsung pada frame setelah file dan izin tersedia. Lead mencatat persetujuan, item ditunda, dan perubahan setelah persetujuan. Dev menerapkan berdasarkan versi/node yang disetujui. Apabila file berubah, periksa delta di area terdampak sebelum integrasi ulang.

Kondisi selesai: tersedia prototype, frame/node permanen, varian dan token terpetakan, state matrix lengkap, aksesibilitas dicek, setiap blocker tertaut, dan hasil review tercatat. Setelah implementasi, Design meninjau screenshot runtime aktual pada perangkat/ukuran yang disepakati.
