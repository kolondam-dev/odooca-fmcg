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

## Kapan perlu `-u` (mengikuti `deploy/init.sh`)
Fase upgrade di `init.sh` berjalan **sekali per penanda** (`upgrade_modules_vN`), bukan setiap boot;
paksa dengan `FORCE_UPGRADE=1` atau naikkan penanda. Hasil uji (Odoo `f4378f29`):
- **Tanpa `-u`:** perubahan JS, template OWL (`.xml` statis), dan SCSS langsung terpakai setelah restart
  (bundle aset dibangun ulang otomatis; diuji dengan mengubah ukuran font sidebar).
- **Perlu `-u`:** perubahan `i18n/*.po`, kode Python, data XML, dan manifest. Termasuk urutan dan nama menu inti
  (`<function>` `_id_ui_apply_navigation`) serta bahasa bawaan (`post_init_hook` hanya saat instal pertama).
- Setelah meng-upgrade modul inti (sale, stock, ...) urutan/nama menu bisa tertimpa; jalankan `-u id_ui`
  (di `init.sh`: `FORCE_UPGRADE=1` atau penanda baru).

## Uji
`odoo-bin -d <db> -u id_ui --test-enable --test-tags /id_ui --stop-after-init`

### CI UI v7
`install-test` memasang `id_ui_form` dan dependency UI, menguji addon Python,
membuat dua quotation pada DB disposable, lalu menjalankan regression systray
dan smoke browser. Pager wajib berpindah ke record berbeda dan kembali; satu
record saja menggagalkan smoke. `UI_TEST_LOGIN`/`UI_TEST_PASSWORD` hanya akun uji.
Bukti log tersedia pada artifact `ui-smoke-diagnostics`. Berkas SQL wilayah pada
branch asli claude-design tidak termasuk PR UI ini.
