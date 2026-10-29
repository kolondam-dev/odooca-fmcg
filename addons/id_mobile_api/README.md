# FMCG Mobile Read API — tahap2 baca

Addon ini menambahkan GET `/api/v1/me/bootstrap` dan GET `/api/v1/sync/snapshot`
berbentuk JSON langsung sesuai kontrak PWA catalog v2. Login memakai sesi cookie
Odoo yang sudah ada melalui `/web/login`; tidak ada login/password API baru,
API key bersama, auth bypass, simulator fallback, atau endpoint command/write.
PWA live dan paket hosting masih terkunci; pemasangan addon ini tidak melakukan
deployment atau mengaktifkan UI live/proxy hosting.

## Provisioning eksplisit

1. Instal `id_mobile_api` pada database staging (dependency `id_base`, `sale_stock`).
2. Admin memberi group **FMCG Mobile Sales Read** kepada internal user yang disetujui.
   Group hanya mengimplikasikan `base.group_user`; tidak memberi write Sales/Stock.
3. Settings → Mobile Read Assignments: tetapkan satu penugasan aktif per
   user/company/hari WITA, dengan warehouse, pricelist IDR, daftar SKU dan outlet
   terjadwal. Penugasan ini adalah read scope admin, belum impor otomatis PJP CSV.
4. Company endpoint adalah company default akun (`res.users.company_id`) dan
   wajib masih menjadi company yang diizinkan user. Tidak ada selector scope HTTP.
   Multi-company switching lewat cookie/query bukan fitur kontrak tahap ini.
5. Pricelist harus shared atau milik company itu; warehouse harus milik company
   itu. SKU/outlet harus dapat dibaca oleh user melalui ACL/record rules normal.
   SKU memakai base UoM `uom.product_uom_unit`, inner_qty/carton_qty integer positif
   dengan pembagian utuh, default_code unik, dan principal yang valid.
   Outlet harus aktif, company compatible dan mempunyai koordinat sah; radius
   assignment5–15m. Tidak ada `demo_unrestricted` pada respons resmi.

Tanpa role/penugasan yang cocok endpoint403, tanpa session401. Konfigurasi yang
belum lengkap/rasio/harga invalid422. Rollover WITA saat membaca409 agar bootstrap
diulang. Query parameter dan cross-origin/cross-site read ditolak400. Method selain
GET tidak didaftarkan (405). Raw ORM/RPC tetap tunduk pada native Odoo ACL; mobile
user hanya dapat membaca penugasannya, tidak dapat membuat/mengubah/menghapusnya.
Admin sistem mengelola scope melalui ACL khusus; tidak ada auto assignment/seed.

## Data yang dikembalikan

Bootstrap hanya identity sendiri, company, role `sales`, businessDate WITA dan
CSRF token Odoo bagi session tersebut. Token tidak mengaktifkan endpoint write.
Snapshot mengirim scope company/user/warehouse/hari, katalog SKU dan daftar outlet
terjadwal. ID adalah native variant/principal/partner ID dalam string; kode SKU
berasal dari default_code, bukan nama sebagai foreign key. `deliveries=[]` secara
eksplisit karena mapping assignment delivery/picking belum menjadi scope tahap ini.
Tidak mengklaim manifest pengiriman/HRIS/approval/accounting sudah terintegrasi.

Harga berasal dari pricelist yang ditetapkan, untuk referensi pembelian1karton
pada tanggal bisnis WITA, dikonversi dari base pcs lalu dikeluarkan pajak termasuk
harga melalui `account.tax.compute_all`. Tidak hardcode tarif. Hasilnya IDR/carton
sebelum permintaan diskon dan tanpa fiscal-position/outlet-specific pricing.
Server transaksi tahap berikutnya tetap wajib menghitung ulang seluruh harga,
quantity-break, fiscal position, pajak, diskon dan stok; snapshot hanya estimasi.

Stok tersedia = max(0, quantity - reserved_quantity) / carton_qty pada **lokasi
stok utama yang tepat** (`warehouse.lot_stock_id`), company dan SKU assignment;
tidak menjumlahkan warehouse/company lain, consignment, transit, quarantine atau
child bins. Ini proyeksi terbatas, bukan seluruh physical/reserved ledger warehouse.
ACL/record rules stock.quant tetap berlaku; tidak menggunakan sudo. Tidak ada
reservasi atau validasi ketersediaan untuk transaksi baru pada endpoint ini.

Version menggunakan hash konten scope/catalog/outlet; updatedAt timestamp UTC.
Versi berubah bila isi yang dikembalikan berubah, bukan setiap detik. Kedua route
memakai cursor readonly, no-store/private, Vary Cookie, tanpa CORS wildcard.
Tidak mengembalikan standard_price, margin, saldo AR, invoice/payment, payroll,
nomor telepon, VAT, lot/owner/quant individual, atau dokumen user/company lain.

## Pengujian dan acceptance

`tests/test_read_api.py` menggunakan ORM/HttpCase Odoo nyata (bukan stub):
- session/public/portal/internal tanpa role, missing assignment, tampered scope;
- isolation company, warehouse dan consignment; packaging/price/stok/outlets;
- ACL own assignment read-only, tidak menambah business write permission;
- product record rule tidak dibypass; konfigurasi invalid ditahan; rollover;
- cache/header/origin/method boundary dan tidak menambah transaksi saat read.

CI install-test memasang addon pada DB kosong dan menjalankan `/id_mobile_api`.
PWA tetap menjalankan test/bootstrap generation guard dan schema contract gate.
Sandbox sesi ini tidak dapat memasang/menjalankan PostgreSQL (setgroups/setuid
container dibatasi); runtime acceptance dinyatakan hanya setelah CI nyata lulus.
Full dataset/cut-off seed tetap acceptance antigravity terpisah, tidak dimuat oleh
API. Source/model/ACL yang diverifikasi harus diuji kembali di staging sebelum live.
