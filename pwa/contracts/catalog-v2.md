# Katalog snapshot v2 — tahap pertama integrasi PWA

Status: kontrak client draft0.13, bukan endpoint Odoo yang sudah diimplementasikan.
Basis repository: main b957e02. Model/master berasal dari integrasi seed PR37;
penerimaan runtime full dataset/cut-off tetap pekerjaan terpisah.

## Envelope dan scope

`Snapshot.catalog_version=2` memerlukan `scope` berisi company_id, user_id,
warehouse_id dan business_date (WITA), versi snapshot tidak kosong dan updatedAt
ISO datetime. Scope company/user/hari harus cocok dengan bootstrap. Scope warehouse
harus dipilih dan diotorisasi server; client tidak membuktikan ACL warehouse.
HTTP adapter wajib bootstrap dahulu, mengosongkan sesi lama saat bootstrap ulang,
dan menolak respons yang datang dari bootstrap lama. Setiap bootstrap menaikkan
generation sebelum request dimulai; hanya generation terbaru boleh mengadopsi
identity/CSRF. Pemanggil usang ditolak409 baik respons sukses maupun error, tanpa
mengubah state terbaru. Jika bootstrap terbaru gagal, sukses lama tidak boleh
memulihkan sesi yang sudah dikosongkan. Snapshot HTTP tanpa v2 ditolak.
Daily bundle v2 lokal juga diikat kembali ke owner/hari pada restore.

Endpoint berikut masih draft: GET /api/v1/me/bootstrap dan GET /api/v1/sync/snapshot.
Live tetap terkunci; hosting tetap503 untuk /api/. Tidak menambahkan controller,
auth, ACL, loader, scheduler, mapping assignment/PJP, atau menyalakan submit live.
Tahap backend berikutnya harus menyepakati dan menguji hal-hal itu di staging.

## Mapping katalog

`mapCatalogProducts` menerima read-model yang telah disanitasi/diotorisasi backend,
bukan raw ORM JSON/RPC. `CatalogRowSchema` strict: field tidak dikenal ditolak.

| Read-model sumber | Kandidat sumber Odoo | Product client |
|---|---|---|
| product_id | product.product.id (variant, bukan template) | id berupa string stabil |
| default_code | product.product.default_code | sku_code |
| principal_id | product.template.principal_id.id | principal berupa ID string |
| name / brand_name | nama produk/brand yang boleh dilihat user | name / brand |
| carton_qty | product.template.carton_qty | packaging.carton |
| inner_qty | product.template.inner_qty | packaging.pack |
| price_per_carton | hasil kalkulasi harga yang diotorisasi server | price, price_basis=carton |
| stock_cartons | hasil proyeksi stok scope warehouse dari server | stock, stock_basis=carton |

Jangan menyalin list_price, standard_price atau qty_available secara buta:
konversi basis UoM/pricelist/tax/company/warehouse harus diputuskan backend.
Client saat ini mengestimasi IDR sebelum pajak dan sebelum diskon yang diminta;
backend harus memasok harga pada basis tersebut, memvalidasi currency IDR dan
menghitung ulang harga/pajak/discount/stock saat transaksi diterima. Tidak ada
klaim harga final, reservasi, uang diterima, margin atau akses standard_price.
`stock_cartons` boleh pecahan dan bukan batas otorisasi order offline.

Identitas variant/kode harus unik dalam satu katalog. Principal kosong/0 ditolak.
Nama/kode tampilan tidak digunakan sebagai relasi ORM atau identitas assignment.
Mapping yang memerlukan user/company/warehouse/PJP/outlet tetap harus dijaga server.

## Kemasan dan estimasi

packaging={carton:<pcs per karton>,pack:<pcs per pack>,pcs:1}; integer positif,
carton>=pack dan carton%pack=0. Jika inner_qty=1, pack ekuivalen1pcs.
Kemasan nonintegral/rasio tidak valid ditolak; model selain basis pcs perlu kontrak
lain, bukan pembulatan diam-diam. JSON Schema menampilkan batas scalar; constraint
pembagian dan uniqueness field juga dicatat sebagai x-invariant/x-unique dan wajib
dijalankan backend. Zod menegakkan keduanya pada client.

Estimasi baris = price_per_carton * qty * pcs_per_selected_unit / pcs_per_carton.
Jumlah gross dibulatkan sekali ke rupiah lalu diskon permintaan dibulatkan sekali,
sama dengan policy demo sebelumnya. Jumlah di luar batas integer aman ditolak.
Label order/koreksi memakai rasio produk; harga dan stok diberi label karton.

## Kompatibilitas dan demo

Snapshot lama tanpa catalog_version tetap dapat dibaca untuk sejarah. Rasio
implisit144/12/1 hanya berlaku pada snapshot lama di build demo. Tidak ada default
rasio untuk katalog v2 atau HTTP/live. Tidak menulis ulang snapshot, draft, command,
UUID, receipt, harga atau evidence historis untuk menyesuaikan katalog terbaru.
Replay valid tetap memakai source/snapshot asal; deadline SO root WITA tetap berlaku.

Tiga SKU demo sebelumnya tetap144/12. SKU tambahan khusus demo memakai24/6 untuk
uji campuran rasio dan koreksi offline, tanpa memasukkan file master seed ke bundle.
`mapCatalogProducts` adalah adapter murni yang diuji; belum dipasang pada endpoint
backend. Tahap selanjutnya adalah endpoint baca berotorisasi dan acceptance mapping
bootstrap/PJP/outlet/katalog/manifest sebelum integrasi SO/delivery write.
