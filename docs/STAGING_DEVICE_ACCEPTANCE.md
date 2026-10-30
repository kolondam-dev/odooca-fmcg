# Catatan sesi acceptance perangkat staging

Status awal seluruh baris: BELUM DIUJI. Isi hasil aktual, bukan menyalin hasil CI.

- Tanggal/jam WITA:
- Penguji:
- Perangkat/OS/browser/versi:
- SHA addon/PWA/gateway dan deployment IDs:
- URL HTTPS gateway:
- Environment/database (tanpa secret):
- User/company/warehouse/assignment/hari snapshot:
- Office ID/status sumber dan outlet ID:
- Mode: strict server / simulator demo (pilih satu, jangan digabung):
- Keterbatasan sesi: owner remote; GPS lapangan kantor/outlet belum diterima.

| Skenario | Hasil yang diharapkan | Hasil aktual / bukti |
|---|---|---|
| HTTPS/login akun1 | Satu origin, cookie aman, identitas benar | BELUM DIUJI |
| Daily sync | Assignment/company/warehouse/hari sesuai server | BELUM DIUJI |
| Master kantor | Titik/radius/status sama dengan admin; TEST tidak menjadi verified | BELUM DIUJI |
| Preview outlet | Titik/radius sama dengan assignment; jarak & posisi perangkat terlihat | BELUM DIUJI |
| Tile opt-in | Tidak request sebelum pilihan; attribution terlihat; peta jalan nyata tampil | BELUM DIUJI |
| Izin lokasi ditolak | Pesan jelas, tanpa titik pengganti di staging | BELUM DIUJI |
| Jaringan/tile gagal | Diagram/status tersedia, tidak dianggap check-in berhasil | BELUM DIUJI |
| Ganti target/sesi | Posisi/respons lama tidak mengisi target/user baru | BELUM DIUJI |
| GPS di luar radius/akurasi buruk | Upload strict ditolak; preview tetap tersedia | BELUM DIUJI |
| GPS di dalam radius | Upload strict berhasil hanya bila kondisi nyata terpenuhi; remote: tandai tidak diuji | BELUM DIUJI |
| Foto/watermark | Source privat; device/server time terpisah; receipt/hash cocok | BELUM DIUJI |
| Retry upload UUID sama | Receipt sama; user+UUID, bukan dedup seluruh gambar | BELUM DIUJI |
| Login akun2/akses foto akun1 | Ditolak; tidak bocor source/derivative | BELUM DIUJI |
| Clear/offline/rollover WITA | Data/tab/session scope dihapus/diminta sync ulang sesuai kondisi | BELUM DIUJI |

Simpan ID evidence/screenshot yang disetujui untuk review tanpa cookie, password, token atau foto sensitif. Hasil geofence dari simulator/DevTools tidak membuktikan kehadiran lapangan. Keputusan akhir: PASS fungsi remote / HOLD / FAIL; acceptance GPS lapangan diberi status terpisah.
