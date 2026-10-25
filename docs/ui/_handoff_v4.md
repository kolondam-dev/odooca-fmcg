## 2026-10-25 — claude-design agent (chat + sandbox) — UI refinement v4: logo O tanpa pill, FMCG sudut tegas, topbar rata tengah, divider systray
**Berubah:** `id_ui_shell`:
- Logo O: background pill dihilangkan. Saat terbuka hanya tampil "Odoo FMCG"; saat ciut tampil ikon "O" (`oi-odoo`) besar putih tanpa background yang berubah menjadi ungu Odoo (`#714B67`) dengan animasi halus dan glow tipis saat di-hover atau di-klik.
- FMCG brandbox: sudut tegas tanpa rounded (`border-radius: 0`), font tipis elegan (`font-weight: 300`, `letter-spacing: .12em`).
- Ikon menu sidebar: berubah ke warna normal Odoo saat di-hover/aktif tanpa animasi scale dan tanpa glow.
- Search box topbar: sudut rounded diperkecil (4px).
- Judul topbar: diposisikan persis di tengah (`align center`) dengan tipografi seimbang (`font-weight: 600`).
- Systray topbar: divider tipis vertikal disematkan di antara item (dari discuss hingga avatar profil).
Docs `docs/ui/id_ui_shell.md` dan `e2e/smoke_ui.py` diperbarui; log `agent-log/claude-design.log` diperbarui.
