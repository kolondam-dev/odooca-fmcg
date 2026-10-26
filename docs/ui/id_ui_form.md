# id_ui_form: chatter sebagai tab, judul di statusbar, form lebar penuh

Hanya aktif di tata letak sidebar (per pengguna) dan layar bukan kecil. Form memakai lebar penuh;
chatter menjadi tab terakhir ("Messages & Activities") di notebook terluar; judul form (`.oe_title`)
pindah ke statusbar; footer total menempel di bawah (sticky).

## Cara kerja dan jejak kompatibilitas
- `patch(FormRenderer.prototype)`: `mailLayout()` mengembalikan `"NONE"` (nilai yang sudah dikenal
  kompiler form mail) sehingga chatter bawaan tidak dirender, lalu menyediakan props Chatter.
- `patch(Notebook.prototype).computePages()`: menambah satu halaman ke notebook terluar,
  yang merender `Chatter` bawaan mail dengan props yang sama seperti kompiler form.
- **Judul di statusbar (memindahkan DOM milik OWL).** `syncTitle()` memindahkan `.o_form_sheet > .oe_title`
  ke dalam `.o_form_statusbar`. Batasan yang dijaga: (1) dibatasi ke akar renderer ini lewat
  `useRef("compiled_view_root")`, bukan `document`; (2) idempoten, tidak menyentuh DOM bila judul sudah
  di statusbar; (3) bila tata letak berganti ke klasik atau form di dialog, judul dikembalikan ke posisi
  semula dan kelas `id_statusbar_title` dilepas; (4) titik sisip dicari sebagai anak langsung statusbar
  (tidak melempar `NotFoundError` bila pipeline status bersarang). Uji: pager, ketik, form baru,
  batalkan, ganti tata letak (smoke_ui).
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
judul tepat satu di statusbar, footer sticky, divider systray (normal dan debug), pager, ganti tata letak
dan pemulihan judul, hotkey.
