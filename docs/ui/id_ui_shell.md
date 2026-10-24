# id_ui_shell: shell sidebar dan navigasi keyboard

Langkah 2 UI/view (redesign). Berdampingan dengan tata letak klasik; dipilih per pengguna lewat
menu pengguna ("Tata letak: ganti ke ..."). Bawaan pengguna baru: parameter sistem
`id_ui_shell.default_mode` (`sidebar` atau `classic`, bawaan `sidebar`).

## Jejak ke sistem lain (untuk koordinasi antar-agent)
- DB: satu kolom `id_ui_shell` pada `res_users_settings`. Tidak ada tabel, model, atau data lain.
- Titik sentuh Odoo yang dipakai: `patch(WebClient, {components})` + `t-inherit` pada
  `web.WebClient` (sisip `<IdSidebar/>` sebelum `<NavBar/>`), registry `services`
  (`id_shell`), registry `user_menuitems`, service `menu`, `command`, `ui`, dan hook `useHotkey`.
- NavBar bawaan tidak diubah di JS; di mode sidebar ia disesuaikan lewat CSS pada selector
  `.o_main_navbar`, `.o_navbar_apps_menu`, `.o_menu_brand`, `.o_menu_sections`. Selector ini
  yang paling mungkin bergeser antar-versi Odoo.
- Semua CSS ada di bawah `body.id-shell-sidebar`; mode klasik tidak tersentuh. Layar kecil
  (`ui.isSmall`) otomatis memakai NavBar bawaan.
- Ikon aplikasi memakai ikon bawaan Odoo (`webIconData` atau `webIcon`), bukan set ikon sendiri.
- Tidak membaca atau menulis field bisnis, tidak menyentuh addon `id_*` lain.

## Keyboard
`Alt+M` fokus ke menu, panah atas/bawah pindah item, panah kanan/kiri buka/tutup grup,
`Home`/`End`, `Enter` buka, `Esc` kembali ke isi, `Alt+B` ciutkan/bentang, `Ctrl+K` palette
bawaan Odoo (tidak dibuat ulang).

## Topbar (v0.2)
Judul besar = aplikasi aktif, seksi aplikasi sebagai tab horizontal (NavBar bawaan, termasuk
overflow "+" dan hotkey Alt+1..9), pencarian menu global (membuka command palette bawaan,
awalan `/`), systray, nama dan role pengguna di samping avatar. Sidebar hanya berisi aplikasi
(ikon bawaan Odoo). Role saat ini placeholder (`UserMenu.idRoleLabel`) sampai `id_app` ada.

## Belum dikerjakan
Aplikasi mobile (bottom nav), highlight item aktif berdasarkan URL, string JS lewat `_t`,
form profile (tab dan visible/hidden by default), layout form tanpa scroll.
