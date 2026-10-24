# id_ui — Tema, Navigasi, dan Bahasa

Dasar pekerjaan UI/view (agen `claude-design`). Lisensi LGPL-3. Diuji di Odoo 19 commit `f4378f29`.

## Isi
- **Tema**: token warna di `static/src/scss/primary_variables.scss` (navbar klasik `#001A57`,
  primer `#1B5E8C`; sidebar/topbar baru ada di `id_ui_shell`; usulan, ganti dengan warna merek distributor pilot) dan penyesuaian
  kerapatan daftar di `backend.scss`.
- **Navigasi**: urutan menu utama dan nama Indonesia menurut GLOSSARY.md, dikonfigurasi di
  `models/ir_ui_menu.py` (`ROOT_MENUS`, `SUBMENU_NAMES`). Menu dari modul yang tidak
  terpasang dilewati.
- **Dependensi**: modul stack inti (`sale_management`, `stock`, `purchase`, `account`, `hr`, `fleet`,
  `hr_attendance`, `hr_holidays`, `spreadsheet_dashboard`) agar menu mereka ada saat urutan diterapkan.
- **String**: sumber English, terjemahan `i18n/id.po`. Nama Indonesia menu inti (glosarium) ditulis lewat
  kode karena terjemahan modul inti tidak bisa ditimpa lewat `.po` addon lain.
- **Bahasa**: saat instal, mengaktifkan `en_US` dan `id_ID`, dan menjadikan `id_ID` bawaan
  partner baru (matikan dengan parameter sistem `id_ui.set_default_lang = False`).

## Catatan operasional
- Setelah meng-upgrade modul inti (sale, stock, account, ...), jalankan `-u id_ui` agar urutan
  dan nama menu diterapkan ulang.
- `en_US` wajib aktif: bila nonaktif, ORM Odoo menimpa nilai sumber English dengan teks
  Indonesia. Kode sudah menjaga ini, jangan menonaktifkan `en_US`.
- Peran per pengguna (menu tampil per app role) menunggu `id_app`.

## Uji
`odoo-bin -d <db> -u id_ui --test-enable --test-tags /id_ui --stop-after-init`
