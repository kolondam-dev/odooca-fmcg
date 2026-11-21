# DES-02-r0 · Gap study layar dan komponen Odooca Field Android

**Basis audit** [D01-r1](DES01_D01_CHECKPOINT.md) pada Design `6abeef3`, main acuan `39172de` dan [arahan Lead](https://github.com/kolondam-dev/odooca-fmcg/blob/8836d05/docs/android/LOCAL_WORKFLOW.md) pada `8836d05`. Bukti kode merujuk tree Design `6abeef3`. Hasil adalah kandidat desain editable. Design QA dan kesiapan produksi mengikuti acceptance masing-masing.

## 1. Cakupan sumber 62 layar

**62/62 PNG referensi di arsip pemilik telah diperiksa secara visual melalui enam lembar kontak.** Seluruh ID memiliki padanan HTML. [Inventaris layar sumber](SCREEN_SOURCE_INVENTORY.md) mencatat path dalam ZIP, judul, padanan PWA, pemetaan Android dan gap per layar. Arsip adalah sumber pembandingan visual. Perilaku simulator merupakan hipotesis dan keputusan produk terkini mengatur versi Android.

Koreksi atas rekonsiliasi PWA: layar **33** adalah Datepicker janji bayar, **47** adalah beranda HRIS, dan **48** adalah Ajukan cuti. Layar **24** menampilkan PJP kosong dengan Extra call; NOO dan carry-over merupakan perluasan berdasarkan keputusan yang lebih baru. Layar **28** menampilkan slot “Foto lokasi toko” dan “Foto toko”. Pemilik menetapkan keduanya wajib untuk check-in toko.

## 2. Gap per workflow

Temuan Android membedakan UI native, potongan UI, dan fondasi domain/data. Komponen PWA menjadi pembanding implementasi. Kehadiran komponen PWA tidak membuktikan kesiapan Android atau backend. Capability merujuk [register](BACKEND_REGISTER.md).

| Referensi dan layar/state yang terdokumentasi | Bukti PWA | Bukti Compose dan gap | Tindakan desain / capability |
|---|---|---|---|
| Login, Login_gagal, Sesi berakhir, Profil dan Lainnya · K23/K29 | `Login`, `ProfileScreen`, `MorePage`, `AppHeader`, `BottomNav`, `Field`, `BottomSheet`. | `LoginScreen`, `AppNav`, `ScreenHeader`, Material 3 field. Session data layer ada. UI status expiry, konfirmasi ganti akun pending dan navigasi role penuh perlu kontrak visual. | DS-C01–C04/C06. B01 menjaga akses dan isolasi owner. |
| Beranda Sales/Delivery/Canvasser, Sinkron jalan/gagal, Status_offline · K2/K24/K25/K33 | `Home`, `MorningSession`, `SyncProgressCard`, `Progress`, `Callout`. | `HomeScreen` dan `SnapshotRepository` menyediakan tampilan dasar dan cache. Progres tahapan, state scope/expiry, pemulihan offline dan provenance butuh desain. | DS-C04/C11 untuk load/error, plus pola progres. B03/B04 untuk readiness resmi. |
| Outlet, Outlet_kosong, Kunjungan_hub, Navigasi, Extra_call, Selesai_kunjungan · K15/K27/K28 | `OutletDirectory`, `OutletCard`, `VisitPanel`, `NavigationScreen`, `ExtraCallScreen`, `CloseVisitScreen`, `Tracker`. | Home punya tampilan outlet. `VisitRepository` dan validasi domain ada. Hub/route, jejak progress, filter, dan PJP kosong/carry-over perlu UI. | DS-C05/C07/C11, tracker dan kartu ringkasan. B03 untuk izin carry-over, Extra call dan NOO. B07 untuk piutang yang terverifikasi. |
| Status_gps/izin, Check-in, Kamera viewfinder/pratinjau/kedaluwarsa/luar · K16/K22/K23/K26/K31 | `LocationNotice`, `CheckinMap`, `Evidence`, `CameraViewfinder`, `OfficialEvidence`. | `CalibrationScreen` dan pengumpul fix ada. Komposisi Settings, state izin/kamera, retake dan bukti resmi belum tersedia sebagai UI Native di tree audit. | DS-C06/C07/C08. App Settings mengikuti state izin. Bukti resmi dan keputusan policy mengikuti B02 dan target B09. |
| Absen informasi/dalam/luar/selfie/pulang · 04–08, K22 | `AttendanceScreen`, `CameraViewfinder`, `Callout`, `Chip`. | Kalibrasi dapat digunakan untuk pola feedback. UI absen dan ringkasan hari resmi belum ditemukan. | DS-C07/C08, tracker dan ringkasan. B04 untuk absensi resmi. |
| Antrean, Riwayat aktivitas/pengajuan, Hasil kirim · K13/K29/K33 | `QueueScreen`, `ActivityScreen`, `RequestsScreen`, `OrderResult`. | Outbox dan badge dasar ada. UI detail receipt, perbedaan kegagalan transport/protokol dan keputusan bisnis belum ada. | DS-C09, dengan tiga jalur kendala terpisah untuk status tak dikenal, 403 tanpa receipt, dan respons tak terbaca. B01/B09. |
| POS, Katalog, Diskon_baris/footer, Ringkasan, Koreksi_so, Display_stok · K13/K14 | `OrderScreen`, `DiscountSheets`, `OrderCorrections`, `DisplayStockScreen`, `Stepper`, `Field`. | Skala nominal/teks tersedia dari tema. Kontrol multi-satuan, baris SKU, tampilkan estimasi dan status pricing masih memerlukan UI. | DS-C10, baris SKU dan ringkasan uang. B05/B07 menahan angka resmi, approval lanjutan dan pricing v2. |
| Delivery DO/detail/hub, POD semua/sebagian/tolak/TTD, Closing_trip · 49–51, 53–56, K17/K19 | `DeliveryWorkspace`, `DeliveryTaskEditor`, `DeliveryApproval`, `TripClosing`, `Segmented`, `RadioRow`. | UI native manifest/POD dan editor serah terima belum ditemukan. Domain/presenter tidak boleh mengisi manifest fiktif di produksi. | DS-C05/C08/C09, baris manifest dan pemilih outcome. B06 untuk manifest, TTD dan efek resmi; B07 untuk ringkasan kas. |
| Penagihan_toko, Penagihan_bukti, Tidak_tertagih · 30–33, 52, K20 | `PenagihanScreen`, `CollectionWorkspace`, `Checkbox`, `Field`, `RadioRow`. | Belum ada UI Compose untuk memilih faktur, mengalokasikan nilai dan mencatat sisa. | DS-C05/C08/C10, baris alokasi faktur dan ringkasan uang. B07 untuk saldo, ledger dan settlement. |
| Uang_lapangan, Ajukan_uang, Realisasi, Biaya_toko, Setor_uang · 57–58, K16/K18 | `ExpenseWorkspace`, `AjukanUangScreen`, `BiayaTokoScreen`, `SetorUangScreen`. | Belum ditemukan UI native untuk saldo, formulir dan approval uang lapangan. | DS-C03/C08/C09/C10, ringkasan uang dan baris pengajuan. B07. |
| HRIS dan Ajukan cuti · 47–48, K21 | `AjukanCutiScreen`, `App`, `Field`. Layar 48 memuat saldo, jenis, tanggal, alasan dan slot lampiran. | Tidak ditemukan layar Compose HRIS di tree audit. | DS-C03/C09/C11 dan reuse status pengajuan. Data personel dan capability B08. |
| Pilot dan adaptasi · D06 | Galeri dev [PWA](../../pwa/src/ui/Gallery.tsx), unit dan browser test yang disitir K30/K33. | Tema dan font Android ada. Screenshot, ukuran sentuh aktual, font scale, IME, talkback dan kebijakan fokus memerlukan uji runtime. | DS-C01–C11. Cocokkan 320/360/390/600 dp, font scale 100/130/200%, perangkat, focus order dan insets. |

## 3. Matriks prioritas komponen

| ID | PWA | Android saat audit | Usulan yang dibangun untuk review |
|---|---|---|---|
| DS-C01 | AppHeader, BottomNav, ScreenHeader | ScreenHeader dan AppNav dasar | FieldTopBar root/back dan item navigasi default/aktif. |
| DS-C02 | Button, IconButton | PrimaryButton | Primary, secondary, tertiary, destructive, fokus, pressed, busy dan disabled. |
| DS-C03 | Field, Select, Textarea | OutlinedTextField di Login | Default, fokus, error, password dan read-only. |
| DS-C04 | Chip, Callout, StatusDot | StatusBadge | StatusChip dan InlineNotice untuk informasi, offline, sesi, dan error. |
| DS-C05 | ListRow, OutletCard, Card | Kartu outlet dalam Home | Kartu terjadwal, carry-over, selesai dan terbatas. Baris domain memakai struktur yang sama. |
| DS-C06 | BottomSheet, SheetHeader | Material 3 tersedia; pola khusus belum ditemukan | ConfirmationSheet izin, konfirmasi akun, dan kendala. |
| DS-C07 | LocationNoticeSheet dan CheckinMap | CalibrationScreen dan data fix | LocationPanel mencari, izin, akurasi rendah, luar radius dan siap. |
| DS-C08 | CameraViewfinder, Evidence, OfficialEvidence | Fondasi evidence, UI capture belum ditemukan | EvidenceCapture siap, preview, izin, antre, gagal dan kedaluwarsa. |
| DS-C09 | QueueScreen, OrderResult, RequestsScreen | OutboxRepository dan badge dasar | QueueRow/ReceiptPanel dengan status lokal, protokol, pembatasan akses, dan keputusan bisnis resmi. |
| DS-C10 | Stepper, Segmented, Stat | Belum ditemukan komponen reusable setara | QuantityStepper dan ringkasan transaksi untuk kebutuhan Sales, POD dan AR. |
| DS-C11 | Callout, Progress, fallback per layar | Refresh dan error di Home | ScreenState loading, empty, error dan capability unavailable. |

### Kontrak visual dan teknis

- Dua tier variable Figma merepresentasikan `pwa/design/tokens.json`: primitives, lalu alias Android. Inter mengikuti skala sumber. Gunakan navy untuk shell sebagai usulan review dan target sentuh **48 dp** sebagai target uji sementara. Token bersama **44** dipertahankan. Pastikan fokus yang terlihat, target tidak tumpang tindih, teks panjang dapat membungkus, dan Back mengembalikan fokus.
- Receipt `accepted`, `needs_approval`, dan `rejected` memerlukan hasil yang sah. HTTP 2xx ber-UUID cocok dengan status asing memakai **Hasil perlu ditinjau**, HTTP 403 tanpa receipt memakai **Akses ditolak**, dan respons gagal parse memakai **Respons tidak dapat dibaca**. Hanya receipt `rejected` yang sah memakai **Ditolak server**. Saat audit, fallback parser Compose masih mengembalikan `REJECTED` untuk status selain `accepted`/`needs_approval`. Lead menugaskan koreksi dan acceptance repository/API serta Compose pada slice Dev D01-05.
- Waktu kejadian `HH.mm.ss` WITA. Asal waktu lokal, antre dan server diberi konteks berbeda. Keputusan pemilik 20 November 2026 menetapkan jam rencana `HH.mm` sesuai presisi jadwal. Contoh yang tidak memiliki jam sah tetap menampilkan asal atau ketidaktersediaan data. Semua contoh desain memakai data sintetis.
- Gap pola lain yang menunggu review workflow dan data: editor multi-satuan SKU/POD per baris, signature/retensi, rincian alokasi dan sisa faktur, budget/approval per principal, form nominal dan tanggal dengan error, serta bukti foto aktual. Representasi draft untuk pola yang punya source dapat dipakai untuk review. Aktivasi produksi mengikuti B03–B08 dan uji B09.

## 4. Draft Figma dan bukti review

**Versi desain DES-02-r0.** File dibuat pada akun Figma yang terhubung. Paket Starter membatasi file menjadi tiga halaman, sehingga Product Map dan review D01 berada dalam satu halaman. Versi ini dicatat melalui nama frame dan SHA checkpoint repo. Riwayat versi bernama Figma belum dicatat.

| Keluaran | Node | Isi |
|---|---|---|
| Foundations | [8:105](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=8-105) | 41 primitive, 36 alias Android, 9 text styles Inter dan contoh pasangan kontras. |
| Komponen | [2:180](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=2-180) | 13 set inti dan 8 set pola lintas workflow. |
| Review D01 | [4:2](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=4-2) | Lima contoh D01 dengan 28 instance editable. |
| Product Map | [4:137](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=4-137) | Enam kelompok workflow dari DES-02-r0. Pembaruan angka 62/62 dan keputusan pemilik tertahan oleh kuota Figma MCP Starter. |

| Set inti | Node | Varian |
|---|---|---:|
| DS-C01 · FieldTopBar | [3:2](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-2) | 2 |
| DS-C01 · FieldNavigation | [3:9](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-9) | 2 |
| DS-C02 · FieldButton | [3:14](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-14) | 8 |
| DS-C03 · FieldInput | [3:31](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-31) | 5 |
| DS-C04 · StatusChip | [3:54](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-54) | 5 |
| DS-C04 · InlineNotice | [3:65](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-65) | 4 |
| DS-C05 · OutletCard | [3:78](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-78) | 4 |
| DS-C06 · ConfirmationSheet | [3:99](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-99) | 3 |
| DS-C07 · LocationPanel | [3:115](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-115) | 5 |
| DS-C08 · EvidenceCapture | [3:141](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-141) | 6 |
| DS-C09 · QueueRow & ReceiptPanel | [3:172](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-172) | 11 |
| DS-C10 · QuantityStepper | [3:228](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-228) | 4 |
| DS-C11 · ScreenState | [3:253](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=3-253) | 4 |

| Pola lintas workflow | Node | Varian | Pijakan |
|---|---|---:|---|
| Pola · Tracker | [5:2](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-2) | 3 | Tracker/VisitPanel |
| Pola · SyncProgress | [5:39](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-39) | 4 | SyncProgressCard |
| Pola · CatalogItem | [5:60](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-60) | 3 | OrderScreen/DisplayStockScreen |
| Pola · MoneySummary | [5:76](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-76) | 3 | CustomerSummary/OrderResult/TripClosing |
| Pola · SegmentedChoice | [5:89](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-89) | 2 | Segmented/DeliveryTaskEditor/PenagihanScreen |
| Pola · ManifestRow | [5:108](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-108) | 3 | DeliveryWorkspace |
| Pola · InvoiceAllocationRow | [5:124](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-124) | 3 | PenagihanScreen/CollectionWorkspace |
| Pola · ActivityRow | [5:140](https://www.figma.com/design/16gvzHRHxERodxxVsQJe8y?node-id=5-140) | 3 | ActivityScreens/ProfileScreen |

Node pengguna dapat dikomentari di draft bila akses file memberi izin. Library bersama belum dipublikasikan. Draft ini memuat komponen dan contoh komposisi. Prototipe D01 yang menghubungkan alur, perbandingan detail frame asli, serta review visual dan aksesibilitas perangkat tetap menunggu acceptance.

**Bukti Figma.** Pembacaan balik menemukan 21 set, 87 varian, 36 alias dan 232 layer teks pada varian menggunakan text style Inter. Review board memuat 28 instance dengan layer editable. Tombol primary dan fokus berukuran 56, tombol sekunder 48 dalam desain. Label PJP carry-over dan status receipt dibaca balik dari instance. Pemeriksaan Figma belum membuktikan ukuran sentuh Compose, fokus runtime, TalkBack, keyboard, font scale, atau kontras terhadap foto.

## 5. Keputusan produk · 20 November 2026

| Keputusan | Dampak desain | Acceptance dan dependensi |
|---|---|---|
| Jam rencana `HH.mm` | Jadwal pada kartu outlet, Beranda dan rute mengikuti presisi menit. Waktu kejadian tetap `HH.mm.ss` WITA. | Fixture jadwal `08.30`, kejadian `08.30.16 WITA` dan jadwal hilang. Gunakan sumber masing-masing. |
| NOO menunggu persetujuan mengizinkan survei/foto saja | Bedakan aksi **Survei outlet** dan **Ambil foto** dari **Mulai kunjungan** dan **Buat order**. Saat status Menunggu persetujuan, kunjungan resmi dan order tetap terkunci. | B03 menetapkan scope, capability survei, keterikatan foto ke pengajuan dan keputusan Branch Manager. Uji pending + capability aktif/mati, ditolak, disetujui, dan scope owner salah. Status disetujui tetap mengikuti hak akses kunjungan/order. Aktivasi resmi belum tersedia. |
| Kedua foto check-in toko wajib | Layar 28 dan D01-04 menampilkan slot **Foto lokasi toko** dan **Foto toko**. Status 0/2 atau 1/2 menahan check-in. Draf parsial dapat dipulihkan. Status 2/2 berarti kedua bukti lokal siap untuk alur lanjut. | Uji tiap slot hilang, foto tidak valid, retake, 2/2 valid, offline dan receipt. Bentuk wire, tujuan audit per slot, binding gambar dan acceptance resmi menunggu Lead/B02/B09. Source saat ini memakai satu `EvidenceRef` dan satu file per intent. |

## 6. Penpot · verifikasi awal rebuild

Pemilik memilih Penpot untuk pembangunan ulang design system. File aktif **Odooca-FMCG Field Apps**, ID `42288968-6e5e-808d-8008-f9456c20a1f7`, page `42288968-6e5e-808d-8008-f9456c20a1f8`. Figma DES-02-r0 tetap menjadi referensi checkpoint historis.

- Koneksi baca/tulis MCP terverifikasi pada file ini. Set `Odooca/Primitives` berisi 41 token dari sumber repo dan `Odooca/Android` berisi 36 alias aktif. Alias primary resolve ke `#1B5E8C`.
- Komponen lokal **DS-C08 · Bukti check-in** node `d1ec018c-c393-80c4-8008-f947b7864ffe` memiliki varian 0/2, 1/2 dan 2/2. Instance uji `d1ec018c-c393-80c4-8008-f947b81c1341` terverifikasi sebagai komponen, dengan dua slot terikat ke token tinggi 48 dan font Inter. Kesiapan desain 2/2 belum berarti check-in resmi.
- Build lengkap komponen lain lintas workflow, pemetaan node desain baru, review visual dan publikasi library belum selesai.

## 7. Penpot · DES-02-r1, komponen dari gap study

Pemilik mengotorisasi penambahan gap yang diaudit pada halaman [02 · Components](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0). Parent Design `71dff8c`; arahan bersama `f9dae3b`. Struktur lama menjadi acuan. Kelompok baru disusun vertikal setelah `ProgressSteps`, sejajar x=40 dan dengan jarak 100 px.

| Kelompok | Komponen | Jumlah varian |
|---|---|---:|
| D01 | [RecoverySheet](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ae853f5c4a), [SyncRecovery](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9aeba44bad3), [BottomNavSales](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9aed2757c55), [BottomNavDelivery](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9aeee96be49), [OutletAvailability](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9aea8caeaba), [CameraEvidence](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ae97cab3f4), [CheckInEvidence](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ade56a3f5a), [QueueRow](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ae2e594c17), [ReceiptPanel](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ae54f1011f), [ActivityRow](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9ae65f407b9) | 48 |
| Penagihan dan Sales | [PaymentMethod](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9af63401880), [InvoiceAllocationRow](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9af7c41cfc8), [UncollectedReason](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9af931b0948), [PromiseDate](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9afaeb4813f), [DiscountEditor](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9afcb25fbb2), [OrderSummary](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9afdec7f7c1) | 15 |
| Delivery | [ManifestRow](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9afee03e90b), [DeliveryProgressSteps](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b01223250f), [PODOutcome](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b03dc0a2bc), [RecipientSignature](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b058d86f02) | 13 |
| Kas dan HRIS | [FieldCashRequest](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b07084b0c7), [LeaveRequest](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b089fb812c), [CashTripSummary](https://design.penpot.app/#/view?file-id=42288968-6e5e-808d-8008-f9456c20a1f7&page-id=d1ec018c-c393-80c4-8008-f94a84b178e0&shape-id=6ecae0c7-19b7-807a-8008-f9b09ffa746a) | 7 |

- `Button` yang sudah ada menerima enam varian baru: `Focused` pada empat tipe ukuran Md, dan `Busy` pada Primary ukuran Md dan Lg. Sampel sinkron terakhir memakai `08.02.15 WITA`.
- `CheckInEvidence` memakai dua instance `PhotoSlot`, dengan state kosong, satu slot siap dari masing-masing sisi, keduanya siap, dan retake per slot. `ReceiptPanel` memisahkan status resmi dari hasil protokol, pemblokiran akses dan respons yang tidak terbaca.
- Pembacaan balik Penpot memverifikasi 23 keluarga baru, 83 varian baru, enam varian tombol, tanpa error varian dan tanpa board varian keluar dari kontainer masing-masing. Contoh layout dan data tetap berada dalam lingkup design system. Binding dua bukti, acceptance runtime dan prototipe alur penuh tetap mengikuti milestone dan kontrak.

## 8. Review Penpot menjelang alih kerja · 21 November 2026

Pembacaan melalui MCP menemukan 54 root di `02 · Components`, 22 gaya tipografi, 5 set token aktif dan 5 template di `03 · Patterns`: Tab root, Detail sticky action, Bottom sheet, Loading, dan Offline. `01 · Foundations` memuat contoh warna, tipografi, spasi/radius/elevation, perangkat, dan ikon. `05 · Motion & Haptics` memuat aturan serta contoh interaksi. `04 · Screens` masih kosong saat dibaca. Template dan library dapat menjadi titik mulai penyusunan layar setelah giliran Claude selesai.

| Area | Library Claude Design | Komponen r1 | Arah integrasi yang diusulkan |
|---|---|---|---|
| Tanggal | `Calendar` punya angka hari per layer dalam komponen flex. | `PromiseDate` menyimpan state Empty/Selected; kisi contoh memakai teks per pekan. | Gunakan Calendar untuk tampilan tanggal dan pertahankan konteks janji bayar, pemilihan, serta aksi konfirmasi. |
| Sheet dan kamera | `BottomSheet` memakai slot satu/dua aksi. `CameraControls` punya Ready, Out of area, Review. | `RecoverySheet` memuat lima sebab pemulihan. `CameraEvidence` memuat Capture/Outside/Preview/Expired. `CheckInEvidence` merangkai dua PhotoSlot. | Instance pola dasar Claude untuk presentasi. Pertahankan aturan pemulihan, metadata bukti, kedaluwarsa, dan dua foto wajib pada pola domain. |
| Antrean dan hasil | `ListItem` memiliki pilihan trailing; `SuccessHero` memiliki tone Success/Pending/Failed. | `QueueRow` memiliki 7 state. `ReceiptPanel` membedakan keputusan bisnis resmi dari kendala respons/protokol. | Gunakan ListItem untuk ringkasan antrean. Hero mengikuti state yang sudah diverifikasi; detail hasil tetap mendapat provenance, referensi, dan waktu server bila ada. |
| Progres | `ChecklistStep` berisi Done/Current/Locked. `ProgressSteps` adalah tracker horizontal empat tahap Sales. | `DeliveryProgressSteps` adalah daftar vertikal lima tahap dengan detail per langkah. | Evaluasi satu blok langkah reusable dan komposisi Sales/Delivery. Pertahankan urutan domain dan uji tangkapan layar lebar kecil. |
| Harga dan stok | `ProductCard` punya 2/3 baris UOM. Contoh header menyatukan SKU dan stok, misalnya `MYR-RMA-01 · 84 krt`. `KeyValueRow` menyediakan varian emphasis. | Ringkasan order dan faktur punya baris label/nominal buatan lokal. | Gunakan ProductCard untuk konteks SKU, stok badge untuk kuantitas, dan KeyValueRow untuk ringkasan uang. |
| Fondasi | Banyak komponen inti memakai token `color.*`/`spacing.*` dan Inter Tight. Komponen baru seperti Calendar/SuccessHero juga memakai Inter. | Banyak komponen domain memakai `android.*` dan Inter. | Setelah handoff, petakan alias peran dan tipografi yang duplikat sebelum migrasi instances. Tetapkan contoh pemakaian untuk mencegah perubahan global tanpa uji. |

### StockQuantityBadge · kontrak desain

Horizontal, dalam urutan **ikon karton + qty terbesar** | **ikon inner + qty inner** | **@ + qty eaches**. Pilihan inner yang disiapkan: Pack, Lusin, Lainnya, dan Tanpa inner untuk SKU tanpa tier tengah. Kuantitas adalah teks editable. `0` adalah angka yang sah. Varian tanpa inner hanya untuk SKU yang tidak memiliki tier itu. Stok yang tidak diketahui memakai label terpisah. Deskripsi Android kelak menyebut satuan lengkap sesuai `productUnitLabels`; perhitungan jumlah mengikuti `productPackaging` dan stok terverifikasi. Representasi sumber PWA `stockText()` memecah stok karton ke unit dasar dan label singkat. Pemilihan ikon tidak mengubah konversi.

Penerapan yang disarankan: baris metadata `ProductCard`, kolom **stok sistem** dan **stok display** dengan judul yang jelas, serta ringkasan **dipesan/diterima/selisih** pada baris POD. Simbol `@` dipakai untuk satuan eceran. Nilai Rupiah, status transaksi, dan count notifikasi mempertahankan pola masing-masing.

Status saat checkpoint review: [BU] pembuatan node badge menunggu tab Penpot aktif. MCP berhasil membaca library dan struktur terbaru, lalu tab editor tersuspensi sebelum penulisan dapat diverifikasi.
