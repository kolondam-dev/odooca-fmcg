# PWA — alur Sales dan Delivery

Implementasi `agen/pwa-sales-delivery-workflow`, basis merge PR64 (`6901d9e`).
Permintaan pemilik: daftar outlet datar, pencarian layar penuh, kunjungan dengan
Check-in → Open session → Close session, mini POS dan penerimaan DO yang ringkas.

## Sales

- [F] Header dan navigasi tetap; toolbar daftar outlet tetap, daftar mempunyai scroll sendiri.
  Pencarian nama/alamat membuka drawer penuh, filter langsung, Escape/tombol tutup,
  perangkap fokus dan pemulihan fokus. Pemilihan outlet membuka halaman toko.
- [F] Halaman toko menampilkan gambar native Odoo melalui endpoint privat, metrik tiga
  kolom, TOP, limit jika positif, dan PIC. Tidak ada kartu sesi kerja pada Sales/Delivery.
- [F] Check-in menjadi tab awal. Maps, foto dan validasi kunjungan yang sudah ada tetap
  menentukan kelayakan Open session. Preview peta tidak menggantikan validasi.
- [F] Open session membuka mini POS penuh dengan pencarian dan principal dalam satu
  toolbar. Principal lain terkunci selama keranjang berisi item untuk menjaga aturan
  satu principal per order. Kosongkan keranjang untuk beralih principal.
- [F] Preview order menampilkan item/jumlah/nilai sebelum Kirim order. Enter dari layar
  edit hanya membuka preview. Antrean, approval diskon dan dependensi kunjungan tetap
  memakai workflow yang sudah ada. Sesudah pengajuan, tab penutupan menampilkan foto,
  catatan dan akhiri kunjungan; penutupan tanpa order tetap mengikuti aturan sebelumnya.

## Ringkasan toko dari Odoo

| Tampilan | Sumber dan batas |
| --- | --- |
| Ikon/foto | `res.partner.image_128`, hanya outlet assignment aktif dan company yang sesuai |
| Omset terbesar | `amount_untaxed` SO terkonfirmasi (`sale/done`) terbesar, partner tepat dan company/currency assignment; sebelum pajak, bukan omzet invoice |
| Kunjungan sebelumnya | `null` / “—”; transaksi kunjungan resmi belum terintegrasi, tidak ditaksir dari SO terbaru |
| Top order SKU | Produk dengan total `price_subtotal` SO terkonfirmasi tertinggi pada scope sama |
| TOP / limit / PIC | `property_payment_term_id`, `credit_limit` positif, `pic_name`; visibilitas field native tetap berlaku |

[F] Riwayat SO memakai ACL/record rules native tanpa sudo; akun yang tidak mempunyai
hak baca riwayat mendapat metrik kosong. Tidak menambah grup sales secara otomatis.
Foto memakai cookie sesi, `no-store, private`, `Vary: Cookie`, `nosniff`; endpoint menolak
anonim, lintas origin, query override dan outlet di luar assignment. SVG tidak dilayani.
Gagal memuat foto memakai ikon toko biasa. Addon menjadi `19.0.1.3.0` dan memerlukan upgrade
terarah sebelum data baru tersedia pada server.

## Delivery

[F] Check-in berisi maps dan foto awal; Open session baru aktif setelah sesi tervalidasi.
Drawer penuh menampilkan item DO, qty diterima, penerima, alasan dan preview penerimaan.
Tombol kembali menutup halaman DO untuk memilih DO lain. Status tampilan hanya tiga:
DITERIMA SEMUA, DITERIMA PARSIAL, DITOLAK SEMUA. Batal/pending tetap jenis permintaan
internal untuk mempertahankan approval yang ada.

| Alasan DO | Workflow internal bila seluruh DO tidak diterima |
| --- | --- |
| TOKO TUTUP | Cancel Delivery / Toko Tutup |
| TOKO TIDAK PUNYA UANG | Cancel Delivery / Tidak bisa bayar |
| TOKO TIDAK DAPAT DIAKSES | Cancel Delivery / Toko tidak dapat diakses |
| TOKO TIDAK ORDER | Cancel Delivery / Kesalahan Order |
| ORDER MELEBIHI KEMAMPUAN TOKO | Rejected |
| SKU TIDAK SESUAI ORDER | Rejected |
| REQUEST PENDING KIRIM | Pending Requested, wajib estimasi tanggal |

[F] Pada penerimaan parsial, alasan DO selain pending menjadi konteks tambahan;
alasan per item terdampak tetap wajib. Pilihan item: ITEM RUSAK, ITEM EXPIRED,
SALAH SKU, QTY TERLALU BANYAK. Catatan item disimpan terpisah dari alasan DO
(`item_note`, `item_reason`); field legacy `reason` tetap dikirim sesuai validator.

[F] Wizard Terima semua mengisi jumlah dikirim; Terima setengah memakai pembulatan ke
bawah pada satuan integer manifest; Tolak semua mengisi nol. Qty manual dibatasi jumlah
dikirim dan status diterima diturunkan dari jumlah aktual. Wizard tidak mengarang alasan.
Pending mempertahankan tangga approval <3 hari SPV, >=3 hari SPV+BM; cancel tetap SPV.
Tidak otomatis menyelesaikan picking, pembayaran atau settlement Odoo.

[F] Preview menampilkan ringkasan penerimaan, catatan penutupan, biaya DO, biaya toko,
foto penutupan, Simpan draft POD dan Ajukan POD untuk review. Draft item sebelum foto
tersimpan per trip/DO/tanggal/versi sumber, dipulihkan dengan identitas SKU, dan ditolak
bila sumber berubah atau qty tidak cocok. Draft POD lengkap dan bukti final tetap memakai
validasi media, manifest, parent koreksi dan transaksi atomik yang sudah ada.

## Biaya

[F] Biaya DO dan biaya toko membuat `field_expense.request` kategori `delivery_fee`.
Scope DO mengikat trip/tanggal/DO; scope toko mengikat trip/tanggal/outlet (satu pengajuan
per scope, juga bila ada beberapa DO untuk toko yang sama). Form sementara dan marker
pengajuan dipisah; marker/outbox ditulis atomik dengan CAS agar dua layar tidak menggandakan
pengajuan. Tombol terkunci setelah pengajuan, termasuk setelah reload. Koreksi/approval
biaya tetap melalui alur biaya yang ada, bukan pengeluaran/posting otomatis.

## Verifikasi dan batas penerimaan

[F] Tes mencakup scroll daftar 120 outlet, pencarian/dismiss/fokus, Sales sampai foto
penutupan, wizard parsial Delivery, alasan item, biaya berbeda scope dan restore offline.
Regresi lama disesuaikan dengan perpindahan layar tanpa menghapus invariant bisnis.

[BU] Acceptance kamera/GPS perangkat nyata, upgrade database staging existing, tampilan
foto/master riil serta pengiriman transaksi resmi tetap terpisah. Login/identitas/snapshot
berasal dari server; transaksi aplikasi penuh masih dalam jalur demo lokal. Build produksi
terkunci dan staging baca saja tidak dibuka oleh perubahan ini. Tidak melakukan deployment.
