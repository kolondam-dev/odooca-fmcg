# Inventaris 62 layar sumber Android

**Sumber visual** `odoo-fmcg-standalone-prototype-preview-fitfix.zip`, SHA-256
`5bc9fdafb957f3797dc80da006b88fde4de602b57b3b5a3a3cc34d8e2073bb5d`.
Path per baris relatif terhadap `standalone/`. Dibaca 20 November 2026.
62 PNG 780×1688 diperiksa melalui enam lembar kontak, dan 62 HTML dirujuk berdasarkan indeks serta dicek keberadaannya. Arsip juga berisi 62 `.dc.html`.
`data/routes.json` adalah rute simulasi yang diinferensikan. Referensi visual dipakai untuk pembandingan, sedangkan kebijakan produk, acceptance, dan backend mengikuti sumber repo terkini.
Tidak ada aset tangkapan layar yang disalin ke repo atau Figma.

Pemetaan komponen per baris mengacu ID `DS-Cxx` dalam [Design System](DESIGN_SYSTEM.md), dan memakai source PWA/Compose pada parent Design `0f2739c`. Kolom gap menyebut pekerjaan atau dependensi, bukan bukti eksekusi. Lihat [gap study](DES02_SCREEN_COMPONENT_GAPS.md) untuk padanan Compose per keluarga dan node draft.

| ID dan judul | PNG / HTML | Alur Android | Padanan PWA | Komponen DS | Gap atau adaptasi |
|---|---|---|---|---|---|
| 01 · Login | `references/01-Main.png` / `screens/01-Main.html` | D01-01 | Login | DS-C02/DS-C03 | LoginScreen ada; pertahankan brand dan field. |
| 02 · Login · gagal dan SSO | `references/02-Login_gagal.png` / `screens/02-Login_gagal.html` | D01-01 | Login | DS-C02/DS-C03/DS-C04 | Tampilkan galat. SSO hanya bila B01 tersedia. |
| 03 · Beranda · belum absen | `references/03-Beranda_belum_absen.png` / `screens/03-Beranda_belum_absen.html` | D02 | Home, MorningSession | DS-C01/DS-C04/DS-C11 | State sebelum absen dan tracker; B04. |
| 04 · Absen · di dalam geofence | `references/04-Absen_dalam.png` / `screens/04-Absen_dalam.html` | D02 | AttendanceScreen | DS-C02/DS-C07 | Peta, jarak dan status dalam radius; B02/B04. |
| 05 · Absen · di luar geofence | `references/05-Absen_luar.png` / `screens/05-Absen_luar.html` | D02 | AttendanceScreen | DS-C02/DS-C04/DS-C07 | Selfie terkunci di luar radius; aksi ukur ulang. |
| 06 · Absen · selfie terambil | `references/06-Absen_selfie.png` / `screens/06-Absen_selfie.html` | D02 | AttendanceScreen, Evidence | DS-C07/DS-C08 | Preview lokal, waktu dan retake; receipt absen terpisah. |
| 07 · Info ⓘ · aturan geofence | `references/07-Absen_info.png` / `screens/07-Absen_info.html` | D02 | AttendanceScreen | DS-C06/DS-C07 | Lembar aturan geofence dan pemulihan fokus. |
| 08 · Absen pulang | `references/08-Absen_pulang.png` / `screens/08-Absen_pulang.html` | D02 | AttendanceScreen, MorningSession | DS-C04/DS-C07/DS-C08 | Ringkasan pulang dan pending; waktu kejadian berdetik, B04. |
| 09 · Kamera · viewfinder | `references/09-Kamera_viewfinder.png` / `screens/09-Kamera_viewfinder.html` | D01-04 | CameraViewfinder | DS-C02/DS-C08 | Buat shell kamera gelap dengan shutter dan tombol ganti kamera. |
| 10 · Kamera · luar geofence | `references/10-Kamera_luar.png` / `screens/10-Kamera_luar.html` | D01-04 | CameraViewfinder | DS-C04/DS-C07/DS-C08 | Shutter terkunci di luar geofence; nilai resmi dari policy. |
| 11 · Kamera · pratinjau dan watermark | `references/11-Kamera_pratinjau.png` / `screens/11-Kamera_pratinjau.html` | D01-04 | CameraViewfinder, Evidence | DS-C02/DS-C08 | Preview, metadata waktu/bukti, retake dan gunakan foto. |
| 12 · Kamera · foto kedaluwarsa | `references/12-Kamera_kedaluwarsa.png` / `screens/12-Kamera_kedaluwarsa.html` | D01-04 | CameraViewfinder | DS-C04/DS-C08 | Foto kedaluwarsa; ambil ulang, tanpa menyalin policy dari mockup. |
| 13 · Status · akurasi GPS buruk | `references/13-Status_gps.png` / `screens/13-Status_gps.html` | D01-04 | LocationNotice, AttendanceScreen | DS-C04/DS-C06/DS-C07 | Lembar akurasi dan ukur ulang; threshold server masih B02. |
| 14 · Status · izin lokasi ditolak | `references/14-Status_izin.png` / `screens/14-Status_izin.html` | D01-04 | LocationNotice, VisitPanel | DS-C04/DS-C06/DS-C07 | Pengaturan izin Android dan pemulihan fokus. |
| 15 · Status · offline | `references/15-Status_offline.png` / `screens/15-Status_offline.html` | D01-02/05 | App, OutletDirectory | DS-C01/DS-C04/DS-C05/DS-C09 | Banner persisten. Bedakan offline dari status penerimaan. |
| 16 · Status · sesi berakhir (401) | `references/16-Status_401.png` / `screens/16-Status_401.html` | D01-01 | App, Login | DS-C03/DS-C04/DS-C06 | Reauth akun asal; data pemilik di bawah overlay sumber dikosongkan. |
| 17 · Sinkron harian · berjalan | `references/17-Sinkron_jalan.png` / `screens/17-Sinkron_jalan.html` | D01-02 | SyncProgressCard | DS-C04/DS-C11 | Progres berdasarkan tahap snapshot yang dapat dibuktikan. |
| 18 · Sinkron harian · gagal | `references/18-Sinkron_gagal.png` / `screens/18-Sinkron_gagal.html` | D01-02 | SyncProgressCard | DS-C02/DS-C04/DS-C11 | Retry dan lanjut offline hanya jika cache sah. |
| 19 · Sinkron harian · gagal (AR belum selesai) | `references/19-Sinkron_gagal_ar.png` / `screens/19-Sinkron_gagal_ar.html` | D01-02 | SyncProgressCard | DS-C02/DS-C04/DS-C11 | AR gagal/kurang; pisahkan AR tidak tersedia, tanpa mengarang tahap. |
| 20 · Beranda · wajib sync harian | `references/20-Beranda_wajib_sync.png` / `screens/20-Beranda_wajib_sync.html` | D01-02/D02 | Home, MorningSession | DS-C01/DS-C04/DS-C11 | Absen, sinkron, kunjungan tetap capability-gated. |
| 21 · Beranda · sesi aktif (Sales) | `references/21-Beranda_sesi.png` / `screens/21-Beranda_sesi.html` | D01-02/03 | Home, OutletDirectory | DS-C01/DS-C05/DS-C11 | Beranda Sales sesuai scope, jam rencana HH.mm. |
| 22 · Beranda · Delivery | `references/22-Beranda_delivery.png` / `screens/22-Beranda_delivery.html` | D04 | Home, DeliveryWorkspace | DS-C01/DS-C05/DS-C11 | Beranda Delivery dan DO berikutnya; B06. |
| 23 · Beranda · Sales dan Delivery | `references/23-Beranda_canvasser.png` / `screens/23-Beranda_canvasser.html` | D01-02/D04 | Home, DeliveryWorkspace | DS-C01/DS-C05/DS-C11 | Canvasser role gabungan berdasarkan bootstrap; B01/B06. |
| 24 · Daftar outlet · kosong | `references/24-Outlet_kosong.png` / `screens/24-Outlet_kosong.html` | D01-02/03 | OutletDirectory | DS-C01/DS-C04/DS-C11 | Pisahkan kosong sah, belum sinkron dan carry-over; tambah jalur NOO sesuai B03. |
| 25 · Daftar outlet | `references/25-Outlet.png` / `screens/25-Outlet.html` | D01-03 | OutletDirectory, OutletCard | DS-C01/DS-C05/DS-C10 | Cari/filter, jadwal, jarak, dan kartu status. |
| 26 · Extra call | `references/26-Extra_call.png` / `screens/26-Extra_call.html` | D01-02/D03 | ExtraCallScreen | DS-C03/DS-C04/DS-C05 | Pengajuan luar PJP, menunggu Supervisor; B03. |
| 27 · Navigasi ke outlet | `references/27-Navigasi.png` / `screens/27-Navigasi.html` | D01-03 | NavigationScreen, CheckinMap | DS-C02/DS-C05/DS-C07 | Skema jarak dan tautan navigasi, tanpa otorisasi check-in. |
| 28 · Check-in toko (Sales dan Delivery) | `references/28-Checkin.png` / `screens/28-Checkin.html` | D01-04 | VisitPanel, VisitPhotoField | DS-C07/DS-C08 | Peta dan slot bukti; hubungan dua slot pada mockup perlu review B02. |
| 29 · Kunjungan · hub | `references/29-Kunjungan_hub.png` / `screens/29-Kunjungan_hub.html` | D01-03 | VisitPanel, CustomerSummary | DS-C04/DS-C05/DS-C10 | Tracker dan hub. AR/faktur dan urutan aksi mengikuti B03/B07. |
| 30 · Penagihan (Transfer) | `references/30-Penagihan_transfer.png` / `screens/30-Penagihan_transfer.html` | D05 | PenagihanScreen, CollectionWorkspace | DS-C03/DS-C05/DS-C10 | Alokasi dan metode transfer; angka resmi dari B07. |
| 31 · Penagihan · bukti transfer | `references/31-Penagihan_bukti.png` / `screens/31-Penagihan_bukti.html` | D05 | PenagihanScreen | DS-C03/DS-C08/DS-C10 | Bukti transfer dan nilai; jangan anggap bukti sebagai konfirmasi pembayaran. |
| 32 · Alasan tidak tertagih | `references/32-Tidak_tertagih.png` / `screens/32-Tidak_tertagih.html` | D05 | PenagihanScreen | DS-C03/DS-C06/DS-C10 | Pilihan alasan sisa dan input janji bayar; keyboard/fokus. |
| 33 · Datepicker · janji bayar | `references/33-Datepicker.png` / `screens/33-Datepicker.html` | D05 | PenagihanScreen | DS-C03/DS-C06 | DatePicker janji bayar; gunakan kontrol tanggal native yang aksesibel. |
| 34 · Foto display dan stok toko | `references/34-Display_stok.png` / `screens/34-Display_stok.html` | D03 | DisplayStockScreen, DisplayPhoto | DS-C05/DS-C08/DS-C10 | Bukti foto dan stok per satuan; command stok B05. |
| 35 · Order · POS | `references/35-Order_pos.png` / `screens/35-Order_pos.html` | D03 | OrderScreen | DS-C02/DS-C05/DS-C10 | SKU, principal, multi-satuan dan sticky total; B05. |
| 36 · Order · stok tidak cukup | `references/36-Order_stok.png` / `screens/36-Order_stok.html` | D03 | OrderScreen | DS-C04/DS-C05/DS-C10 | Peringatan stok dan estimasi; hasil resmi dari server. |
| 37 · Katalog SKU | `references/37-Katalog_sku.png` / `screens/37-Katalog_sku.html` | D03 | OrderScreen | DS-C05/DS-C06/DS-C10 | Lembar detail SKU dan fallback gambar; B05. |
| 38 · Diskon · baris (line) | `references/38-Diskon_baris.png` / `screens/38-Diskon_baris.html` | D03 | DiscountSheets | DS-C03/DS-C06/DS-C10 | Editor diskon baris dan alur approval; B05. |
| 39 · Diskon · footer order | `references/39-Diskon_footer.png` / `screens/39-Diskon_footer.html` | D03 | DiscountSheets | DS-C03/DS-C06/DS-C10 | Editor diskon footer dan budget; B05. |
| 40 · Ringkasan order | `references/40-Ringkasan.png` / `screens/40-Ringkasan.html` | D03 | OrderScreen, OrderResult | DS-C05/DS-C06/DS-C10 | Ringkasan, catatan dan sumber nominal; B05/B07. |
| 41 · Hasil kirim order | `references/41-Hasil_kirim.png` / `screens/41-Hasil_kirim.html` | D03/D01-05 | OrderResult | DS-C04/DS-C09 | Pisahkan draf, pengiriman, approval dan keputusan resmi. |
| 42 · Selesai kunjungan | `references/42-Selesai_kunjungan.png` / `screens/42-Selesai_kunjungan.html` | D01-05 | CloseVisitScreen | DS-C03/DS-C08/DS-C09 | Ringkasan akhir dan bukti penutup; berlaku sesuai kontrak kunjungan. |
| 43 · Riwayat pengajuan | `references/43-Riwayat_pengajuan.png` / `screens/43-Riwayat_pengajuan.html` | D03/D05 | ActivityScreens | DS-C04/DS-C05/DS-C09 | Riwayat approval, filter dan tindak lanjut sesuai akses. |
| 44 · Koreksi order ditolak | `references/44-Koreksi_so.png` / `screens/44-Koreksi_so.html` | D03 | OrderCorrections | DS-C03/DS-C04/DS-C09 | Alasan penolakan sah dan koreksi bersyarat B05. |
| 45 · Uang lapangan | `references/45-Uang_lapangan.png` / `screens/45-Uang_lapangan.html` | D05 | ExpenseWorkspace | DS-C04/DS-C05/DS-C10 | Saldo dan riwayat realisasi; B07. |
| 46 · Ajukan uang lapangan | `references/46-Ajukan_uang.png` / `screens/46-Ajukan_uang.html` | D05 | AjukanUangScreen | DS-C03/DS-C08/DS-C10 | Kategori, nominal, catatan dan bukti opsional; B07. |
| 47 · HRIS | `references/47-HRIS.png` / `screens/47-HRIS.html` | D05 | App, AjukanCutiScreen | DS-C01/DS-C04/DS-C05 | Beranda HRIS, saldo, riwayat dan fitur terbatas; B08. |
| 48 · Ajukan cuti | `references/48-Ajukan_cuti.png` / `screens/48-Ajukan_cuti.html` | D05 | AjukanCutiScreen | DS-C03/DS-C08/DS-C11 | Tanggal mulai/akhir, durasi, alasan, lampiran sesuai B08. |
| 49 · Delivery · daftar DO | `references/49-Delivery_do.png` / `screens/49-Delivery_do.html` | D04 | DeliveryWorkspace | DS-C01/DS-C04/DS-C05 | Daftar DO dan progres; manifest scoped B06. |
| 50 · Delivery · detail DO | `references/50-Delivery_detail.png` / `screens/50-Delivery_detail.html` | D04 | DeliveryWorkspace | DS-C02/DS-C05/DS-C07 | Daftar toko DO serta tindakan navigasi/AR; B06/B07. |
| 51 · Delivery · hub toko | `references/51-Delivery_hub.png` / `screens/51-Delivery_hub.html` | D04 | DeliveryWorkspace | DS-C05/DS-C08/DS-C10 | Hub toko DO dan tracker serah terima; B06/B07. |
| 52 · Penagihan toko (Delivery) | `references/52-Penagihan_toko.png` / `screens/52-Penagihan_toko.html` | D04/D05 | PenagihanScreen, DeliveryWorkspace | DS-C05/DS-C08/DS-C10 | Alokasi tagihan titipan; B06/B07. |
| 53 · Serah terima · terima semua | `references/53-Pod_semua.png` / `screens/53-Pod_semua.html` | D04 | DeliveryTaskEditor | DS-C08/DS-C09/DS-C10 | Outcome semua dan foto wajib menurut kontrak; B06. |
| 54 · Serah terima · sebagian | `references/54-Pod_sebagian.png` / `screens/54-Pod_sebagian.html` | D04 | DeliveryTaskEditor | DS-C03/DS-C08/DS-C10 | Kuantitas parsial, sebab dan foto; desain rinci menunggu B06. |
| 55 · Serah terima · tolak | `references/55-Pod_tolak.png` / `screens/55-Pod_tolak.html` | D04 | DeliveryTaskEditor | DS-C03/DS-C06/DS-C10 | Alasan tolak, tanggal pengiriman ulang dan approval; B06. |
| 56 · Tanda tangan penerima | `references/56-Pod_ttd.png` / `screens/56-Pod_ttd.html` | D04 | DeliveryTaskEditor | DS-C03/DS-C08 | SignaturePad perlu kontrak tanda tangan dan retensi B06. |
| 57 · Biaya operasional toko | `references/57-Biaya_toko.png` / `screens/57-Biaya_toko.html` | D05 | BiayaTokoScreen | DS-C03/DS-C08/DS-C10 | Baris biaya/nota dan ringkasan; capability B07. |
| 58 · Setor uang ke kasir | `references/58-Setor_uang.png` / `screens/58-Setor_uang.html` | D05 | SetorUangScreen | DS-C03/DS-C08/DS-C10 | Setoran, selisih dan bukti; nominal resmi B07. |
| 59 · Closing trip | `references/59-Closing_trip.png` / `screens/59-Closing_trip.html` | D04 | TripClosing | DS-C04/DS-C07/DS-C08/DS-C10 | Ringkasan trip dan bukti penutup; B06/B07. |
| 60 · Lainnya | `references/60-Lainnya.png` / `screens/60-Lainnya.html` | D01/D05 | MorePage, ProfileScreen | DS-C01/DS-C05/DS-C06 | Akses aktivitas, status integrasi dan ganti akun. |
| 61 · Antrean sinkronisasi | `references/61-Antrean.png` / `screens/61-Antrean.html` | D01-05 | ActivityScreens | DS-C04/DS-C09 | Antrean offline, retry dan state protokol yang tidak memalsukan receipt. |
| 62 · Riwayat aktivitas | `references/62-Riwayat_aktivitas.png` / `screens/62-Riwayat_aktivitas.html` | D01-05 | ActivityScreens | DS-C04/DS-C05/DS-C09 | Riwayat, filter dan provenance; waktu berdetik WITA. |
