# Login, beranda dan absensi PWA

Basis pengerjaan: `main` 628f603 (termasuk PR #53/#56). Branch:
`agen/pwa-login-attendance-ux`. Instruksi pemilik: perbaikan UX/UI terlebih dahulu;
pengujian integrasi backend secara intensif menyusul.

## Perilaku yang diubah

- Build demo yang memuat aplikasi penuh sekarang wajib membaca sesi Odoo nyata
  melalui bootstrap dan snapshot yang sudah memiliki ACL/assignment. Tidak ada
  pemilihan persona pada aplikasi, maupun fallback identitas/katalog saat API gagal.
  Cookie sesi yang masih valid langsung membuka beranda.
- Login mandiri menggunakan form native `/web/login`: token CSRF dibaca dari form
  server, kredensial dikirim same-origin lewat POST, lalu sesi native dan akses
  mobile diperiksa. Kata sandi tidak disimpan di browser atau log. MFA/SSO tetap
  menggunakan halaman login native yang ditautkan. Gagal login menampilkan pesan
  umum dan bantuan admin/line manager.
- Nama perusahaan untuk watermark ditambahkan secara aditif pada bootstrap dari
  company assignment; `id_mobile_api` menjadi versi 19.0.1.2.2. Backend lama yang
  belum diperbarui hanya dapat menampilkan identitas perusahaan berupa ID.
- Logo header memenuhi tinggi navbar, status koneksi berada di header, dan tanggal
  Indonesia menyertakan tahun serta jam:menit:detik WITA yang berjalan.
- Sesi kerja berada setelah sapaan dan sebelum quick action. Quick action selain
  absensi terkunci sebelum check-in hari WITA yang sama dan setelah clock out.
  Tombol sesi kerja juga tidak lagi dapat membuat absensi tanpa melalui form.
- Setelah check-in, kartu absensi terbagi menjadi waktu clock in dan tombol clock
  out. Clock out meminta bukti baru, disimpan per user/company/hari, menonaktifkan
  kesiapan sesi, dan tetap terlihat setelah reload.
- Navbar berisi empat kolom tanpa gap/padding luar dan membentang selebar viewport.
  Pada akun Sales+Delivery, Delivery tetap tersedia lewat quick action dan berada
  di bawah indikator tab kerja Sales sehingga jumlah tab tetap empat.
- Form yang sebelumnya memakai sheet kini memenuhi tinggi layar; header beranda,
  navbar dan toast disembunyikan. Footer Kembali / Check in (atau Check out) tetap
  terlihat, konten form dapat digulir, dan fokus kembali ke pemicu saat ditutup.

## Lokasi dan foto

Master kantor berasal dari snapshot, bukan koordinat kantor hardcoded. Form mencoba
perkiraan lokasi perangkat saat dibuka; tombol Ambil Lokasi Presisi meminta fix
baru. Geofence dan posisi perangkat tetap terlihat. Tile jalan OpenStreetMap tetap
opt-in dengan atribusi dan fallback diagram saat jaringan gagal. Form absensi tidak
mengganti lokasi GPS yang gagal dengan titik kantor.

Alamat lengkap saat ini diisi pengguna secara eksplisit. Belum ada reverse geocoder;
alamat kantor tidak dinyatakan sebagai alamat aktual pengguna. Watermark memuat nama
perusahaan, nama karyawan, waktu perangkat WITA, alamat yang dinyatakan pengguna,
koordinat dan akurasi. Foto dipaketkan bersama hash dan pinpoint lokal; mengubah
alamat/lokasi membatalkan referensi foto sebelumnya. Fix lebih dari 60 detik meminta
pengambilan ulang. Foto ditampilkan langsung setelah pemrosesan tanpa tombol simpan
bukti tambahan. Tombol Check in/Check out menunggu paket foto lengkap.

## Batas integrasi yang tetap berlaku

Autentikasi, identitas, company, penugasan dan snapshot dibaca dari Odoo nyata.
**Pencatatan absensi/clock out dan transaksi pada aplikasi penuh masih mekanisme
lokal demo**, belum posting HR atau transaksi resmi Odoo. Label bukti lokal tetap
ada; tidak ada klaim server telah memverifikasi kehadiran. Referensi foto absensi
kini ikut tersimpan pada record sesi lokal dan dicek terhadap paket lokal sebelum
sesi dibuka/ditutup. Mode respons transaksi lokal tetap berada di Lainnya; ini tidak
memilih atau mengganti identitas pengguna.

Build production tetap terkunci dan build staging baca saja tetap terpisah. Tidak
ada perubahan pada gate evidence resmi, CSRF server, ACL, validasi GPS resmi, maupun
aturan revisi/approval SO lewat hari. Data antrean/draft akun lama tidak dihapus saat
sesi berakhir atau akun berganti. Untuk membuka aplikasi penuh dari kondisi awal,
perangkat harus dapat memverifikasi sesi dengan backend; ini bukan login offline.

## Verifikasi

Tes browser menyediakan respons HTTP sesi/assignment dalam fixture pengujian saja;
tidak ada flag bypass login yang dikirim dalam build aplikasi. Akun uji pada fixture
bukan akun yang dibuat di server. Cakupan meliputi login gagal/berhasil, CSRF native,
layout ponsel/tablet, lebar empat kolom, posisi sesi kerja, izin GPS ditolak, foto dan
clock out, pemulihan fokus, sesi kedaluwarsa, serta regresi alur bisnis sebelumnya.

Hasil eksekusi akhir dicatat pada entri HANDOFF dan log agen. Uji login terhadap
instance Odoo yang dideploy, acceptance perangkat/kamera nyata, dan upgrade addon
server belum dilakukan dalam pekerjaan UX ini. Tidak ada merge atau deployment.
