# I0 — Costing efektif, ownership dan fondasi stok–HPP–GL

## Status dan kontrak

[F] Implementasi dibangun dari main `77a8ccc` (PR91). Paket ini tetap bagian
**I0, tahap 1 dari 9 (I0–I8)**. Bukan penerimaan I3, FIN02 penuh, atau FIN01–58.
Tidak mengganti chart, costing, company atau data demo; tidak mengaktifkan addon
pada demo. Company tambahan hanya fixture disposable yang di-rollback.

`id.finance.stock.bridge._snapshot(company_id, date_from, date_to)` adalah API
Python **private**, bukan endpoint RPC/menu/laporan pengguna akhir. Hasilnya
JSON-compatible. Guard accounting/company menggunakan guard OCA Trial Balance
yang sudah ada; tanpa sudo/SQL untuk mengambil data. ACL dan record rule sumber
tetap berlaku. Accounting role tidak otomatis memberi akses stok.

### Sumber dan granularitas

| Bagian | Sumber | Arti dan batas |
|---|---|---|
| Company/category/product | `cost_method`, `inventory_valuation`, `property_cost_method`, `property_valuation`, product effective fields | Konfigurasi efektif **sekarang**, bukan sejarah konfigurasi |
| Move | `stock.move.value`, `is_in/is_out`, singular `account_move_id` | Nilai aktual tersimpan, tidak dihitung dari harga standar/pro-rata |
| Physical | `stock.move.date`, line `quantity_product_uom`, owner/lot/location | Seleksi hari WITA UTC+08, interval awal inklusif/akhir eksklusif |
| GL | Jurnal terkait dan posted `account.move.line` pada akun stok terpetakan | Tanggal GL tidak digeser zona waktu; current mapping bukan mapping historis |
| Ownership | Quant internal per owner, lot dan lokasi | Snapshot fisik **saat ini**, bukan saldo as-of; owner eksplisit tidak otomatis disebut aset company |

Seleksi move = done company terpilih dengan tanggal fisik WITA **atau** tanggal
jurnal terkait dalam periode. Selisih tanggal tetap terlihat. Jurnal dapat
merangkum beberapa move; bridge membandingkan pada grain jurnal–produk–akun,
menjumlah seluruh sibling yang terlihat, tidak membandingkan setiap move dengan
seluruh jurnal. Nilai masuk bertanda positif, keluar negatif. Selisih dibulatkan
dengan currency company. Setiap model/query sumber dibatasi 20.000 record;
overflow menolak, bukan memotong diam-diam. Periode maksimal 367 hari.

GL stok tanpa direct link dipisahkan, **tidak langsung dianggap salah**: Odoo19
dapat mem-post melalui invoice/closing. Akun yang tidak ada dalam current mapping
belum tercakup. Produk atau sibling tersembunyi oleh record rule juga belum
terbukti lengkap. Karena itu output selalu berlabel `user_visible_sources_only`
dan **tidak mengeluarkan verdict rekonsiliasi penuh** walaupun selisih grup nol.
Current quant tidak dipakai untuk mengarang valuasi historis. `total_value` dengan
compute-sudo tidak dipakai. Harga standar hanya sumber native fixture, bukan
fallback dalam diagnostik.

## Fixture dan oracle independen

`scripts/ops/verify_finance_stock_bridge.py` hanya menerima DB bernama tepat
`finance_i0_reports_disposable`. Dua company IDR disposable, skala nominal 1×/7×.
Native stock moves memakai quotation line purchase sebagai sumber harga; bukan
klaim pengujian penuh alur PO/bill. Receipt dua kali 5 unit pada harga 10/20,
delivery 4 unit, customer return 1 unit merujuk delivery asli:

| Metode | Receipt 1 | Receipt 2 | Delivery | Return |
|---|---:|---:|---:|---:|
| Standard | 50 | 100 | 40 | 10 |
| AVCO | 50 | 100 | 60 | 15 |
| FIFO | 50 | 100 | 40 | 10 |

Angka oracle di atas ditulis terpisah dari perhitungan diagnostik. Standard
receipt berasal quotation; jumlah nilai receipt tidak diasumsikan sama dengan
on-hand × standard price. Selanjutnya transfer internal 1 unit (tanpa jurnal),
konsinyasi 2 unit per produk (owner eksplisit, tanpa nilai/jurnal company), dan
batch delivery 2 unit per produk (satu jurnal untuk tiga move), dengan nilai
standard 20, AVCO 30, FIFO 30 (melewati layer pertama), semuanya dikali skala.
Sisa company 15 unit, konsinyasi 6 unit, berbeda dari valuasi GL.

Gate native juga memeriksa:
- Semua grup GL aktual sama dengan signed move value pada fixture.
- Mutasi jurnal tetap balanced tetapi salah nominal ditolak; baseline pulih.
- Hilangnya direct link terlihat sebagai GL tanpa link.
- Batas UTC 15:59:59/16:00:00 memisahkan hari WITA; tanggal posting tetap Juli.
- Accountant+Stock User menjalankan tanpa sudo; Sales ditolak, foreign active
  company ditolak bahkan pada privileged caller.
- Seluruh fixture di-rollback dan universe company kembali persis.

## Bukti dan gate yang masih terbuka

[F] Tes oracle lokal dapat dijalankan dengan
`python -m unittest discover -s tests -p 'test_finance*.py'`.
[BU] Native CI exact SHA masih harus dijalankan; definisi workflow bukan bukti PASS.
Profil reports menambahkan `purchase_stock` hanya pada database disposable.
Artifact `finance-i0-candidate-evidence/stock-bridge.log` harus memuat JSON bukti
serta `FINANCE_STOCK_BRIDGE=PASS`.

Belum diterima: inventaris live terbaru costing/ownership company1, keputusan
mapping COA final, kronologi policy historis,
negative stock/revaluation/landed cost, consignment sale, invoice-linked COGS dan
closing, completeness terhadap record rule dan semua akun historis, laporan UI,
full stock–COGS–GL oracle I3. Tidak ada klaim hukum/pajak baru.
