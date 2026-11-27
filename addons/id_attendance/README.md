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
