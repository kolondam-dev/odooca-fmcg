# id_ui_form: chatter sebagai tab, judul di statusbar, form lebar penuh

Hanya aktif di tata letak sidebar (per pengguna) dan layar bukan kecil. Form memakai lebar penuh;
chatter menjadi tab terakhir ("Messages & Activities") di notebook terluar; judul form (`.oe_title`)
pindah ke statusbar; footer total menempel di bawah (sticky).

## Cara kerja dan jejak kompatibilitas
- `patch(FormRenderer.prototype)`: `mailLayout()` mengembalikan `"NONE"` (nilai yang sudah dikenal
  kompiler form mail) sehingga chatter bawaan tidak dirender, lalu menyediakan props Chatter.
- `patch(Notebook.prototype).computePages()`: menambah satu halaman ke notebook terluar,
  yang merender `Chatter` bawaan mail dengan props yang sama seperti kompiler form.
- **Judul murni di tengah statusbar (tanpa memindahkan DOM).** Judul yang hanya ditampilkan (nomor/nama
  dokumen: S00001, nomor draft faktur) ditampilkan ulang oleh elemen milik kita sendiri
  (`.id_header_title`) yang disisipkan di statusbar, tepat di tengah antara tombol aksi dan pipeline
  status (`flex: 1 1 0`, selisih tengah terukur 0px). Label kecil di atas judul (mis. "Customer Invoice")
  menjadi caption. Node OWL tidak pernah dipindah; blok asli `.o_form_sheet > .oe_title` disembunyikan
  lewat CSS `:has()` hanya bila judulnya sudah tampil di header.
- **Aturan "judul murni" (`readTitleSpec`).** Blok judul diangkat hanya bila tidak memuat field untuk
  diisi pengguna: tidak ada kontrol di luar `<h1>` dan tidak ada kontrol wajib isi. Satu input nomor
  non-wajib di `<h1>` (nomor draft faktur) tetap dianggap judul; klik judul membuka input aslinya untuk
  diedit (kelas `id_title_editing`). Blok yang berisi field (kendaraan, produk, kontak, principal)
  tetap di sheet tanpa header. Field form tidak pernah berubah tempat.
- Batasan lain: elemen dibatasi ke akar renderer (`useRef("compiled_view_root")`), idempoten (kunci teks
  di `data-id-key`), dibuang bila tata letak klasik, layar kecil, atau form di dialog (syarat JS sama
  dengan syarat CSS). Uji: pager, ketik, form baru, batalkan, ganti tata letak, layar kecil, faktur,
  kendaraan (smoke_ui).
- CSS (`id_form.scss`): lebar penuh, statusbar rata tengah, footer sticky untuk grup yang memuat
  `.oe_subtotal_footer` (selector `:has()`; hanya mengenai form dengan footer total, teruji pada order penjualan;
  form lain dengan `.oe_subtotal_footer` ikut terkena, belum diuji satu per satu). `!important` dipakai hanya pada empat properti yang melawan utilitas Bootstrap/Odoo
  (padding-block statusbar, gap tombol statusbar, margin-top footer, padding panel kontrol); alasan
  tertulis di komentar SCSS.
- Tidak mengubah addon mail, tidak ada DB, model, atau data. Hapus addon = kembali ke bawaan.
- Fallback ke tata letak bawaan: form tanpa `<notebook>`, form di dialog, pratinjau lampiran
  (mis. tagihan vendor), atau notebook yang tidak pernah dirender.
- Titik yang paling mungkin bergeser antar-versi: signature `Notebook.computePages`, nama nilai
  `mailLayout`, `props.archInfo.xmlDoc`, ref `compiled_view_root`, struktur `.o_form_sheet > .oe_title`
  dan `.o_form_statusbar`, serta kelas `.oe_subtotal_footer`.

## Uji
`docs/ui/e2e/smoke_ui.py` (Playwright): sidebar, tab chatter, tanpa chatter samping, tanpa scroll halaman,
judul murni tepat di tengah (SO, faktur), blok berisi field tidak diangkat (kendaraan), layar kecil,
footer sticky, divider systray (normal dan debug), pager, ganti tata letak, hotkey.
