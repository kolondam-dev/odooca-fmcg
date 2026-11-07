# src/ui: design system

Token dan atom dari mockup mobile (62 layar). Sumber token: `pwa/design/tokens.json` (Tokens Studio / Figma) dan `src/ui/tokens.css`; ubah keduanya bersamaan.

- `tokens.css`: variabel `--c-*`, `--r-*`, `--sp-*`, ukuran. `style.css` memakainya; `--blue`, `--muted`, `--border`, `--surface` kini alias token. `--navy` (#001a57) sengaja belum disamakan dengan `--c-nav` (#0b1f4d); putuskan di Fase 1.
- `ui.css`: gaya atom, kelas berawalan `ui-`, dimuat setelah `style.css` (menimpa aturan global `button`, `label`, `input`).
- Atom: Button, IconButton, Chip, Field, Select, Segmented, Checkbox, RadioRow, Stepper, Progress, StatusDot. Impor dari `src/ui`.
- Galeri: jalankan `npm run dev`, buka `/field/#ui` (hanya mode pengembangan).
- Aturan: token bukan nilai mentah; target sentuh ≥44 px; teks ≥12 px; atom tidak tahu alur (aksi lewat props).
- Uji: `tests/ui-atoms.test.ts`.
