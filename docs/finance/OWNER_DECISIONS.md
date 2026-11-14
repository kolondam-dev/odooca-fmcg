# Keputusan pemilik — finance, payroll dan lisensi

Tanggal: 13 November 2026 (WIB). Semua keputusan di bawah diambil pemilik repo
dalam sesi ini; dokumen ini mencatat keputusan, konsekuensi, dan hal yang masih
harus dibuktikan. Ini bukan klaim bahwa fitur sudah diterima.

| # | Topik | Keputusan | Konsekuensi |
|---|---|---|---|
| 1 | Model lisensi | **B — produk AGPL-compliant** | OCA AGPL-3 dipakai; modul finance yang menyentuh AGPL akan dilisensikan AGPL-3; monetisasi lewat implementasi, hosting, dan dukungan. Detail: [LICENSING.md](LICENSING.md) |
| 2 | `FIN55` pinjaman/sewa | **C — ada kewajiban, data belum lengkap** | Laporan dibangun *fail-closed*: kontrak tanpa parameter bertanggal tampil sebagai exception bernominal, bukan angka rekaan. Parameter (pokok, bunga, jadwal, akun, dokumen) harus disetujui Finance Controller |
| 3 | `FIN56` payroll | **A — payroll dihitung di Odoo** | Pencairan tetap transfer bank di luar Odoo dan dicatat sebagai pembayaran bank yang merujuk batch payroll |
| 4 | Cakupan payroll | **A — bertahap** | Alur karyawan → kontrak → slip → jurnal draft → persetujuan → pembayaran → bridge `FIN56` lebih dulu. PPh 21/BPJS menyusul setelah sumber resmi bertanggal + sign-off Tax PIC |
| 5 | Aktivasi DB demo | **A — bertahap setelah CI hijau** | `id_finance_reporting` + `id_finance_foundation` lebih dulu, `payroll` di PR terpisah. Setiap langkah memakai blok bertanda versi, idempoten; `RESET_DB` tidak dipakai |
| 6 | Cakupan blok aktivasi | **A — modul + admin demo sebagai Finance Reader** | Hanya `id_finance_reporting` + `id_finance_foundation` yang dipasang dan hanya `base.user_admin` yang diberi `group_finance_reader`; bahasa `id_ID`, user lain, chart, costing dan seed tidak diubah. Detail: [I2_ACTIVATION.md](I2_ACTIVATION.md) |

## Batas yang tetap berlaku

- `REPORT_CATALOG.csv` tidak diubah sampai ada bukti + sign-off; semua 58 ID
  tetap `BELUM_DITERIMA`.
- Tidak ada tarif pajak atau aturan BPJS yang ditulis tanpa sumber resmi
  bertanggal.
- Tidak ada klaim bahwa jurnal payroll otomatis dibuat oleh modul `payroll`:
  pada pin `58f8a39` modul itu tidak bergantung pada `account`.
- Asisten tidak melakukan merge, deploy, atau memberi verdict penerimaan.

## Pekerjaan yang dibuka oleh keputusan ini

| Keputusan | Pekerjaan berikutnya |
|---|---|
| 1 | `docs/finance/LICENSING.md`; PR lisensi terpisah untuk mengubah metadata modul turunan menjadi AGPL-3 (butuh persetujuan pemilik + perubahan `scripts/check_manifests.py`) |
| 2 | Model parameter kontrak `FIN55` + jadwal + tie-out GL, dengan exception bernominal |
| 3–4 | Instalasi `payroll` di profil CI terpisah, wizard post-payroll (draft → approve), bridge `FIN56`, lalu aturan statutori |
| 5 | Blok aktivasi bertanda versi di `deploy/init.sh` setelah CI hijau |
| 6 | Blok `activate_finance_reports_v1` + `demo_finance_reader_v1` di `deploy/init.sh`, bukti idempotensi di `init-test`, lalu deploy oleh pemilik/agen deploy |
