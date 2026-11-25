# DEV-02A · Harness Odoo B09

Jalankan dari commit kandidat. Docker perlu memiliki image yang dibangun dari Dockerfile repo dan image PostgreSQL 16. Runner memilih image lokal melalui ID dan mencatat ID serta versi yang benar-benar dipakai. Pakai ID dari laporan untuk mengulang dengan image yang sama bila masih tersedia.

```sh
docker build -t odooca-fmcg-odoo:latest .
docker pull postgres:16
bash android/tools/verify_dev02a.sh
```

Setel `DEV02A_ODOO_IMAGE` dan `DEV02A_POSTGRES_IMAGE` bila memakai image lokal lain. Harness memasang `id_mobile_api` dan `id_approval` dari arsip commit pada database kosong tanpa data demo. PostgreSQL dan Odoo berada di jaringan Docker internal tanpa port publik. Odoo menerima HTTP melalui loopback di kontainernya. Akun TEST A dan TEST B memiliki assignment, outlet dan produk berbeda dalam satu company IDR dan berbagi kantor berkoordinat sintetis. Skenario memakai HTTP Odoo melalui `HttpCase`.

| Skenario | Bukti penerimaan |
| --- | --- |
| 401 | Snapshot tanpa sesi terautentikasi mengembalikan 401 dan `not_authenticated`. |
| Login dan scope | Kedua akun login lewat JSON-RPC. Bootstrap mengembalikan identitas dan CSRF. Snapshot memuat company, warehouse, hari, produk, outlet dan kantor sesuai assignment. |
| 403 | TEST B mendapat 403 saat membaca gambar outlet TEST A setelah snapshot sendiri berhasil. |
| Command | `sales.order.submit` dikirim dengan versi snapshot dan CSRF. Receipt 200 mencocokkan UUID, status serta referensi ke ledger Odoo dan tepat satu sales order. |
| Rollover WITA | Clock tes berpindah dari malam 16 November menuju 17 November. Snapshot berganti hari dan versi. Versi kemarin menghasilkan 409 tanpa menyimpan command. |
| Scope dicabut | Assignment hari berjalan dinonaktifkan. Sesi yang sama mendapat 403 dari snapshot dan command, tanpa command baru di ledger. |
| Cleanup | Runner menghapus container, volume database dan network fixture. Pemeriksaan akhir memastikan nol resource dengan label run. |

Laporan hanya mencatat rute, status HTTP, metadata versi, identitas TEST, payload sintetis dan kolom receipt yang dipilih. Simpan stdout untuk checkpoint. Batas startup PostgreSQL 90 detik, eksekusi Odoo 15 menit. Untuk latihan jalur gagal, ulangi dengan `DEV02A_ODOO_IMAGE=postgres:16`. Harapkan exit nonzero, `result=failed` dan `cleanup=passed`. Pengaturan ini membuat DB fixture sebelum gagal memulai Odoo.

Tes HTTP B09 dipilih lewat tag opt-in `dev02a`. Saat rollover, Odoo bisa mencatat percobaan tulis pada cursor read-only sebelum otomatis mengulang request dengan cursor read/write. Suite wajib dan pemeriksaan log CI tetap berlaku. Path tes memicu `odoo_install`, `mobile`, dan `upgrade`. Path runner memicu `android`. Jalankan harness manual untuk bukti B09 dan cleanup. Dev memelihara fixture dan laporan. Lead/maintainer backend meninjau perubahan perilaku Odoo. Untuk acceptance lewat APK, Lead perlu menyepakati target disposable HTTPS yang dapat dijangkau runner Android, lalu mengulang alur dengan APK pada SHA yang sama.
