# GLOSSARY.md — Istilah Antarmuka (DRAFT v0.1, untuk ditinjau)

Prinsip: antarmuka **Indonesia penuh** dengan **English** tersedia. Istilah umum FMCG **dipertahankan apa adanya**; terjemahan tidak dipaksakan bila membingungkan tim lapangan. Semua baris di bawah adalah **usulan** dan perlu dikonfirmasi dengan distributor pilot.

Kolom "Perlakuan": **Tetap** = tampil sama di Indonesia dan English · **Id** = diterjemahkan · **Dwi** = tampil Indonesia, istilah asli di kurung/tooltip.

## A. Dipertahankan (Tetap)
| Istilah | Catatan |
|---|---|
| Principal | Pemilik brand yang menunjuk distributor |
| Outlet | Titik jual pelanggan |
| SKU | Unit stok terkecil yang dijual |
| UoM | Satuan ukur; boleh ditampilkan "Satuan (UoM)" |
| Brand, Sub-brand | Hierarki produk |
| PJP | Personal Journey Plan; tampilkan kepanjangan di tooltip |
| Taking Order (TO) | Model penjualan |
| Canvassing | Model penjualan (stok di kendaraan) |
| Direct Selling | Model penjualan |
| Modern Trade (MT), General Trade (GT) | Channel |
| Sales Order (SO) | Dokumen pesanan |
| Delivery Order (DO) | Dokumen pengiriman |
| Picking list, Batch picking | Gudang |
| FEFO | First Expired First Out |
| Lot/Batch, ED (Expired Date), Near-expiry, Bad stock | Gudang |
| Stock on Delivery | Barang dalam pengiriman |
| Money in Transit | Uang di jalan |
| TOP | Term of Payment |
| Aging, DSO, Fill rate, Backorder | KPI dan laporan |
| Footer discount | Diskon per dokumen |
| Double invoice, Pemajuan tagihan | Proses approval (Playbook §3.2) |
| Geotag, Check-in | Lokasi |
| App role | Peran aplikasi mobile |
| PKP, NPWP, NIK, NITKU, KIR, SIM | Singkatan resmi |
| Coretax, e-Faktur, e-Bupot, PPN, PPh 21, BPJS | Istilah pajak/lembaga |

## B. Dwibahasa (Dwi), usulan
| Tampil | Istilah asli | Catatan |
|---|---|---|
| Faktur | Invoice | Tim lapangan memakai "faktur"; istilah teknis integrasi tetap `invoice` |
| Pelanggan | Customer | Usulan; "Outlet" dipakai untuk titik jual |
| Piutang | AR (Accounts Receivable) | Laporan memakai "Piutang (AR)" |
| Daftar Harga | Pricelist | Perlu ditinjau: lapangan mungkin lebih lazim "Pricelist" |
| Gudang | Warehouse | |
| Slip Gaji | Payslip | |
| Absensi | Attendance | |
| Cuti | Time Off | |

## C. Diterjemahkan (Id), istilah umum antarmuka
Simpan, Batal, Hapus, Ubah, Cari, Filter, Kirim, Setujui, Tolak, Konfirmasi, Validasi, Draf, Selesai, Tanggal, Jumlah, Harga, Total, Catatan, Status, Pengguna.

## D. Aturan pemakaian
1. String sumber di kode Odoo/OCA ditulis **English**; terjemahan Indonesia di `i18n/id.po`.
2. Istilah di bagian A **tidak diterjemahkan** di `id.po` (disalin apa adanya).
3. Istilah baru: tambahkan ke glosarium lebih dulu, baru ke `id.po` dan berkas i18n PWA.
4. Perubahan istilah mengikuti peninjauan dengan distributor pilot (Playbook §11 langkah 1).
