# id_ui_form: chatter sebagai tab di form

Hanya aktif di tata letak sidebar (per pengguna) dan layar bukan kecil. Form memakai lebar
penuh; chatter menjadi tab terakhir ("Pesan & Aktivitas") di notebook terluar.

## Cara kerja dan jejak kompatibilitas
- `patch(FormRenderer.prototype)`: `mailLayout()` mengembalikan `"NONE"` (nilai yang sudah dikenal
  kompiler form mail) sehingga chatter bawaan tidak dirender, lalu menyediakan props Chatter.
- `patch(Notebook.prototype).computePages()`: menambah satu halaman ke notebook terluar,
  yang merender `Chatter` bawaan mail dengan props yang sama seperti kompiler form.
- Tidak mengubah addon mail, tidak ada DB, model, atau data. Hapus addon = kembali ke bawaan.
- Fallback ke tata letak bawaan: form tanpa `<notebook>`, form di dialog, pratinjau lampiran
  (mis. tagihan vendor), atau notebook yang tidak pernah dirender.
- Titik yang paling mungkin bergeser antar-versi: signature `Notebook.computePages`,
  nama nilai `mailLayout`, dan `props.archInfo.xmlDoc`.

## Uji
`docs/ui/e2e/smoke_ui.py` (Playwright) memeriksa sidebar, tab chatter, tanpa chatter samping,
tanpa scroll halaman, dan hotkey.
