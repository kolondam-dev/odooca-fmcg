# id_ui_shell: shell sidebar, topbar, panel seksi, navigasi keyboard

Berdampingan dengan tata letak klasik; dipilih per pengguna lewat menu pengguna
("Layout: switch to ..."). Bawaan pengguna baru: parameter sistem `id_ui_shell.default_mode`
(`sidebar` atau `classic`, bawaan `sidebar`).

## Susunan layar (tata letak sidebar)
- **Sidebar** (kiri): hanya daftar aplikasi. Item aktif persegi dan selebar sidebar sehingga menyambung
  ke panel/isi. Scrollbar selalu tersembunyi (tetap bisa di-scroll). Judul = saat terbuka tampil "Odoo FMCG"
  (wordmark resmi Odoo + kotak "FMCG" sudut tegas tanpa rounded, font tipis elegan). Saat ciut = ikon "O"
  (`oi-odoo`) besar tanpa background pill (putih saat diam, ungu Odoo `#714B67` dengan animasi & glow tipis saat hover/click).
- **Ikon aplikasi**: ikon bawaan Odoo tanpa latar. Diam = duo-tone (biru transparan + putih); hover/fokus/terpilih =
  berubah ke warna normal bawaan Odoo secara bersih tanpa animasi pembesaran dan tanpa glow.
- **Topbar**: pencarian menu di kiri dengan sudut rounded diperkecil (4px); judul halaman aktif persis di tengah
  (align center) dengan tipografi seimbang; area kanan (systray) dilengkapi divider tipis vertikal antar-ikon (dari discuss hingga profil user). Polos: tanpa garis bawah, tanpa tab seksi.
- **Panel seksi** (kiri isi): seksi > sub-seksi > sub dari menu aplikasi aktif, bisa diciutkan
  (tombol atau `Alt+P`), lebar 208px, font kecil. Menu aktif cukup tebal tanpa latar. Sub-seksi
  tertutup kecuali dilalui menu aktif. Menu aktif dikenali dari
  `action.currentController`. Aplikasi tanpa submenu tidak menampilkan panel.

## Alur Tab
Halaman selesai dirender -> fokus di pencarian menu. `Tab` -> sidebar (satu perhentian, aplikasi aktif).
Di sidebar: panah atas/bawah pindah aplikasi, `Home`/`End`, `Enter` buka, panah kanan masuk ke panel.
Di panel: panah atas/bawah, panah kanan/kiri buka/tutup grup (kiri pada item = kembali ke sidebar).
`Tab` dari sidebar atau panel -> isi: field pertama di form, atau kolom cari bila ada. `Shift+Tab`
dari sidebar -> pencarian. `Esc` -> isi. `Alt+M` fokus sidebar, `Alt+B` ciutkan sidebar,
`Alt+P` ciutkan panel, `Ctrl+K` palette. Tab di dalam isi belum diatur (menyusul).

## Jejak ke sistem lain (untuk koordinasi antar-agent)
- DB: satu kolom `id_ui_shell` pada `res_users_settings`. Tidak ada tabel, model, atau data lain.
- Titik sentuh Odoo: `patch(WebClient, {components})` + `t-inherit` pada `web.WebClient` (sisip
  `<IdSidebar/>` dan `<IdSectionPanel/>` setelah `<NavBar/>`), `patch(NavBar, {components})` + `t-inherit`
  `web.NavBar`/`web.UserMenu`, registry `services` (`id_shell`) dan `user_menuitems`, service `menu`,
  `action`, `command`, `ui`, hook `useHotkey`, event bus `MENUS:APP-CHANGED` dan
  `ACTION_MANAGER:UI-UPDATED`.
- NavBar bawaan tidak diubah di JS; disesuaikan lewat CSS (`.o_main_navbar`, `.o_navbar_apps_menu`,
  `.o_menu_sections`, `.o_menu_brand`). Selector ini paling mungkin bergeser antar-versi Odoo.
- Pengelola fokus mencari elemen lewat selector (`.o_action_manager`, `.o_form_sheet`,
  `.o_searchview_input`); ikut diperiksa saat upgrade Odoo.
- Semua CSS di bawah `body.id-shell-sidebar`; klasik tidak tersentuh. Layar kecil (`ui.isSmall`)
  memakai NavBar bawaan. Role pengguna placeholder (`UserMenu.idRoleLabel`) sampai `id_app` ada.
- Tidak membaca atau menulis field bisnis, tidak menyentuh addon `id_*` lain.

## Belum dikerjakan
Pola mobile (bottom nav), Tab di dalam isi, panel khusus aplikasi Dashboards (saat ini dobel dengan
panel milik halaman dashboard), form profile, layout daftar, beranda.
