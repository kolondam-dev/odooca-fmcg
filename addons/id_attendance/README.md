# Pilot absensi PWA

Pasang `id_attendance` di DB staging dan siapkan pengguna mobile yang sudah
bisa login ke PWA operasional. Beri grup **FMCG Mobile Evidence Capture**.
Pada karyawan dengan user dan perusahaan yang cocok, HR Manager memilih
**PWA Attendance Office**. Gunakan kantor aktif dengan koordinat terverifikasi.
Karyawan tanpa konfigurasi ini tetap mengikuti alur PWA sebelumnya.

Pada aplikasi PWA yang terhubung ke Odoo, gunakan mode operasi LIVE. Capture
foto, lokasi dan waktu, lalu simpan absen. Bukti dan receipt command disimpan
di server. Daftar Attendance native menunjukkan sumber masuk/pulang **PWA**.
Bila konfirmasi terputus, buka kembali dialog absensi di hari WITA yang sama
dan kirim ulang event yang tersimpan. Request yang berhasil dapat diulang
dengan UUID dan isi yang sama.

Pilot menyaratkan foto dan fix terbaru, unggah di hari WITA yang sama,
serta posting dalam lima menit setelah bukti diterima. Antrian retry bertahan
di perangkat, namun unggah bukti lama memerlukan pengambilan ulang. Pengguna
yang perlu absen penuh tanpa jaringan memerlukan kebijakan dan alur rekonsiliasi
lebih lanjut. Gunakan perangkat uji dengan izin kamera dan GPS yang sesuai.

Periksa catatan Attendance terbuka sebelum onboarding. Sesi yang belum
memiliki absen pulang resmi dapat memerlukan tindakan HR sebelum check-in baru.
Odoo dapat memiliki checkout otomatis atau manual. Untuk pelaporan PWA,
identifikasi pasangan resmi dari tautan bukti masuk dan pulang. Koreksi
ber-approval dan perhitungan rekap merupakan milestone berikutnya.

Saat Odoo memastikan bukti belum diposting dan sudah kedaluwarsa, PWA
membuka pengambilan foto dan lokasi baru. Respons yang hilang atau status
server yang belum pasti tetap memakai UUID lama. Draft hari sebelumnya
dilepas saat PWA memuat hari WITA yang baru. Riwayat resmi tetap di Odoo.

## Kalender dan rekap absensi

Buka **Karyawan → Rekap Absensi PWA** sebagai HR Manager.

1. Di **Jadwal Kerja**, siapkan kalender native Odoo dengan zona dan jam yang
   sesuai. Contoh WITA: Senin–Jumat 08.00–12.00 dan 13.00–17.00.
   Istirahat dikeluarkan dari jam target. Untuk mutasi atau perubahan historis,
   buat kalender baru jika interval berubah, lalu buat versi HR baru dengan
   tanggal efektif, kalender, departemen, dan lokasi kerja. Rekap memakai versi
   aktif tanggal itu. Mengedit kalender lama akan mengubah hasil regenerasi.
2. Di form karyawan, isi **Mulai Cakupan Rekap PWA** sejak hari pertama data absensi
   dapat diandalkan. Tanpa tanggal ini, rekap tidak menetapkan alpa untuk catatan
   yang hilang. Data perangkat lama tidak diimpor otomatis.
3. Di **Hari Libur Absensi**, daftarkan rentang hari inklusif beserta jenis dan
   sumber keputusan. Kosongkan kalender/lokasi untuk libur se-perusahaan.
   Jika keduanya dipilih, keduanya harus cocok dengan versi karyawan pada tanggal
   tersebut. HR menetapkan apakah cuti bersama berlaku dengan memasukkan entri
   pada cakupan yang disetujui. Tanggal resmi dan sumber diisi HR. Entri ini
   berlaku untuk rekap absensi. Hari libur native Odoo juga dihormati, termasuk
   libur parsial. Libur bertumpuk mengurangi jam target satu kali.
4. Pada jenis Time Off Odoo, admin Time Off dapat memilih kategori rekap cuti,
   sakit, atau izin. Pengajuan disetujui mengurangi jadwal wajib hadir hanya
   pada irisan jadwal. Pengajuan menunggu tampil di menit pending. Jika ada
   tumpang tindih antar-izin sah, satu menit dialokasikan sekali, dengan urutan
   sakit, izin, lalu cuti. Jam hadir yang beririsan dengan izin ditampilkan
   sebagai overlap dan tidak dihitung ulang sebagai realisasi wajib hadir.
5. Di **Rekap Periode**, pilih perusahaan, tanggal, karyawan bila perlu, dan
   toleransi dalam menit (default 0). Nilai terlambat/pulang awal sampai ambang
   toleransi tampil nol. Jika melewati ambang, rekap menunjukkan selisih aktual.
   Rentang maksimum 92 hari dan 20.000 kandidat baris per laporan.
6. Ringkasan menampilkan pembilang dan penyebut kehadiran, jam target/tercatat,
   alpa, dan catatan tidak lengkap. Buka detail untuk rekap per karyawan,
   filter departemen/lokasi/status, dan tampilan pivot atau grafik. Timestamp
   masuk/pulang mengikuti zona tampilan akun Odoo. Tanggal bisnis tetap WITA.

**Aturan pembacaan.** Target memiliki dua ukuran: menit terjadwal setelah istirahat
dan libur, serta menit wajib hadir setelah Time Off sah. Alpa hanya berlaku
sesudah hari WITA berakhir, dalam cakupan PWA, dengan sisa jadwal wajib hadir,
tanpa check-in maupun pengajuan pending yang beririsan. Hari tanpa jadwal tetap
tidak masuk penyebut. Hari dengan check-in PWA dihitung hadir pada tingkat
kehadiran, termasuk jika check-out hilang. Catatan demikian ditandai tidak
lengkap dan tidak menyumbang durasi. Checkout otomatis/kiosk tidak menggantikan
bukti check-out PWA. Durasi aktual adalah rentang masuk–pulang di hari bisnis,
termasuk istirahat. Menit dalam jadwal wajib hadir mengecualikan istirahat,
libur, dan Time Off.

Laporan adalah hasil sementara per pengguna. Buat ulang laporan setelah koreksi
data atau perubahan konfigurasi. Fitur ini menggunakan Time Off native yang
sudah tersedia. Pengajuan PWA dan approval khusus mengikuti tahap 3.
