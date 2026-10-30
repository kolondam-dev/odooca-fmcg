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
- **Aturan fail-closed judul murni (`readTitleSpec`).** Judul readonly boleh berupa teks biasa.
  Satu-satunya kontrol editable yang dipromosikan adalah tepat satu `input` teks/pencarian non-wajib
  di dalam `<h1>` (nomor draft faktur). Multiple controls, `select`, `textarea`, `contenteditable`,
  input required/native `aria-required`, modifier wajib Odoo, input disabled/readonly, tipe input lain,
  atau input di luar `<h1>` membuat fungsi mengembalikan `null`; hidden input diabaikan dan tidak pernah dipilih sebagai editor; blok asli tetap terlihat.
  Tombol native pada header mendukung Tab, Enter, Space, nama aksesibel dan focus-visible; aktivasi
  membuka serta memfokuskan input OWL asli. Escape/blur menutup editor tanpa memindahkan node OWL.
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
`docs/ui/e2e/test_form_scss_compile.py` mengompilasi SCSS produksi `id_form.scss` menggunakan libsass yang dipasang CI (`libsass==0.23.0`); kegagalan kompilasi membuat regression test gagal. `docs/ui/e2e/smoke_ui.py` (Playwright) juga menggulir SO fixture dengan 18 baris transaksi dan memeriksa scroll owner, posisi footer di scrollport, keterjangkauan baris terakhir, serta overflow horizontal. Cakupan invoice lintas-scroll dan validasi model/resolved view masih perlu diuji pada runtime Odoo 19 CE. Smoke mencakup sidebar, tab chatter, tanpa chatter samping, tanpa scroll halaman,
judul murni tepat di tengah (SO, faktur), keyboard edit nomor draft (Enter/Space/blur/Escape),
blok berisi field tidak diangkat (kendaraan), layar kecil,
footer sticky, divider systray (normal dan debug), pager, ganti tata letak, hotkey.


### Regresi guard judul
`python -m unittest discover -s docs/ui/e2e -p 'test_*.py' -v` menjalankan fungsi `readTitleSpec` yang diekstrak dari source produksi di Chromium terhadap fixture readonly, nomor draft invoice, multiple input, contenteditable, required/aria-required/Odoo modifier, select, textarea, input luar h1, tipe input tak didukung, serta hidden input sebelum nomor draft untuk memastikan fokus selalu ke input yang tervalidasi.


## Keputusan bisnis: ringkasan diskon native Odoo (2026-10-29)

**Keputusan pemilik: pilih opsi B.** Untuk tahap demo, UI menggunakan ringkasan diskon native yang memang tersedia dari model/view Odoo yang terpasang. Tidak menambahkan dua diskon dokumen baru, field visual palsu, formula baru, atau perilaku diskon/promo khusus hanya demi memenuhi layout.

**Alasan dan batas cakupan:** aturan diskon dan promosi end-to-end — termasuk akuisisi/penambahan modul, pengelolaan aturan, dashboard, konfigurasi, dan workflow approval — cukup kompleks dan berada di luar scope demo saat ini. Mengimplementasikan semua itu sekarang akan memperluas scope UI secara tidak proporsional dan berisiko mengarang aturan bisnis yang belum disetujui.

**Aturan tampilan untuk PR #36:**
- Pertahankan dan tata letak ulang ringkasan diskon/totals native yang sudah ada pada resolved view/model; audit runtime tetap diperlukan untuk memastikan field yang benar-benar tersedia.
- Jika sumber native menyediakan total diskon yang valid, tampilkan nilai tersebut dengan label yang jelas. Jangan menjumlahkan ulang atau menafsirkan ulang diskon baris, early-payment discount, pajak, atau promo.
- Jika Odoo tidak menyediakan satu agregat native yang jelas pada form/model terkait, tampilkan ringkasan native yang tersedia atau jangan tampilkan angka agregat tambahan. Jangan menciptakan formula pengganti.
- Fokus penerimaan UI adalah hierarki visual, responsivitas, scroll/sticky, aksesibilitas, dan keterjangkauan baris transaksi. Semantik diskon/promo bukan blocker untuk UI ini.
- Kebutuhan mesin aturan diskon/promo, konfigurasi, dashboard, dan approval workflow dicatat sebagai pekerjaan bisnis terpisah di luar demo; keputusan ini bukan persetujuan untuk implementasi fitur tersebut dalam PR #36.

**Pemisahan gate:** keputusan ini menyelesaikan blocker keputusan bisnis mengenai diskon. Gate teknis yang independen — CI aktual pada SHA terbaru, audit resolved view/runtime, dan bukti browser scroll/footer — tetap wajib diselesaikan sebelum PR dapat dipertimbangkan untuk merge. PR tetap draft/HOLD sampai gate teknis tersebut ditutup.

Task Managed by agent claude-design-takeoverby-codex at 2026-10-29T14:31:00+07:00

## Enhancement footer transaksi — spesifikasi penerimaan

Target layout desktop pada sidebar layout adalah tiga kolom bila ruang dan struktur view memungkinkan:

1. **Notes** — catatan transaksi.
2. **Ringkasan diskon native** — hanya diskon/agregat yang memang disediakan model dan resolved view Odoo.
3. **Ringkasan nilai** — subtotal, DPP, tax, dan grand total yang memang tersedia pada dokumen.

Kolom harus collapse menjadi layout bertumpuk pada viewport sempit; tidak boleh menyebabkan horizontal overflow atau menutupi baris transaksi. Grand total menjadi fokus visual utama; DPP/subtotal menjadi tingkat kedua. Warna mengikuti token UI konsisten, bukan warna status hardcoded pada nilai bisnis.

**Perilaku scroll wajib diverifikasi:** footer tidak boleh ikut bergeser secara mengganggu saat scroll baris/form. Pastikan tidak ada nested scroll yang bersaing, konten terakhir tidak tertutup, footer tidak menutupi tombol/statusbar, serta keyboard dan zoom tetap bekerja. Uji quotation/SO dan invoice/customer bill yang sesuai.

**Integritas nilai dan batas scope:** pilihan bisnis adalah opsi B, yaitu memakai ringkasan diskon native Odoo. Jangan membuat field diskon dokumen baru, menghitung ulang diskon/promo, atau mengasumsikan aturan agregasi yang tidak diberikan oleh model. Jika tidak ada agregat native yang jelas, jangan tampilkan angka agregat buatan. Implementasi rule engine diskon/promo, modul tambahan, management, dashboard, konfigurasi, dan approval workflow berada di luar tahap demo. Karena keputusan ini sudah dibuat, semantik diskon/promo tidak lagi menjadi blocker UI pada PR #36.

**Status teknis:** audit registry/model dan resolved XML pada runtime Odoo 19 CE tetap dibutuhkan untuk mengonfirmasi field native yang tersedia. Sticky saat ini memakai selector .o_form_sheet .o_group:has(.oe_subtotal_footer); pengujian harus membuktikan scroll dan keterjangkauan baris terakhir pada SO dan invoice. Keputusan bisnis tidak menggantikan gate CI/runtime/browser.

### Catatan audit implementasi lanjutan (2026-10-29)

Audit branch menemukan addon kustom id_base, id_ui, id_ui_shell, dan id_ui_form; tidak ditemukan addon kustom id_discount atau field eksplisit footer_discount_1/2. Source penuh addon Odoo/OCA eksternal tidak disimpan dalam direktori addons/ repo ini, sehingga inspeksi registry/model dan resolved form architecture pada runtime Odoo 19 CE tetap diperlukan untuk menentukan ringkasan native yang benar-benar tersedia. Jangan memindahkan elemen atau menambahkan field hanya lewat CSS tanpa mengetahui parent XML dan sumber nilainya.

### Implementasi awal footer — 2026-10-29

Pada branch agen/ui-footer-transaction-layout-v1, SCSS memberi panel ringkasan .oe_subtotal_footer latar netral, border halus, lebar maksimum responsif, alignment ke kanan dan angka tabular. Strip sticky diberi isolasi stacking dan bayangan yang lebih jelas; breakpoint mobile mengurangi padding dan mengizinkan panel memakai lebar penuh. Ini hanya enhancement visual pada markup yang sudah ada: tidak memindahkan field, tidak mengubah perhitungan, dan tidak menambahkan diskon.

**Belum selesai / belum terverifikasi:** stabilitas sticky saat scroll nyata; overflow, zoom, keyboard, serta form selain SO. Runtime Odoo tidak tersedia dalam sesi implementasi ini, sehingga struktur resolved view/model dan field native pada invoice harus dikonfirmasi oleh CI/browser smoke. Layout tiga kolom tetap tujuan presentasi bila struktur view mendukung, tetapi kolom diskon menggunakan ringkasan native dan bukan dua field diskon baru.


### Koreksi kompatibilitas libsass — 2026-10-29
Smoke UI pada PR #36 mengungkap bahwa `max-width: min(100%, 32rem)` gagal dikompilasi oleh libsass CI (`Incompatible units: 'rem' and '%'`). Deklarasi diganti menjadi `width: 32rem; max-width: 100%;`, yang kompatibel pada uji kompilasi pembanding. Ini menghilangkan fungsi CSS `min()` yang tidak didukung pada jalur kompilasi ini; lebar tetap dibatasi kontainer. Tetap wajib memeriksa computed layout pada Odoo 19 CE. CI untuk commit koreksi belum diverifikasi. PR #36 tetap HOLD sampai smoke UI lulus; layout tiga kolom dan stabilitas sticky masih terbuka.


### Follow-up regression coverage — 2026-10-29

The CI fixture now creates a populated draft invoice from a confirmed 18-line order and prints runtime evidence for the installed modules, registry fields, XMLIDs, and resolved Sales Order/invoice form architecture. Playwright uses one geometry audit for `order_line` and `invoice_line_ids`: it calculates the sticky threshold from the natural footer position and scrollport geometry, checks multiple samples after engagement, requires exactly one sticky footer group, and tests the last row's visibility/uncovered area plus trial-click actionability. A hidden-row negative control rejects a row entirely above the scrollport. Overflow is measured at page, form, scroll owner, and footer levels. Invoice checks run at desktop, mobile viewport, and browser zoom.

**Not yet verified:** these checks and runtime audit require a fresh successful GitHub Actions run; the latest SHA currently has no run/check evidence exposed by the connector. The fixture changes the CI install set to include `sale_management`, `account`, `fleet`, and `l10n_id` because the smoke uses Sales, invoice, and vehicle forms. The owner has selected option B: use only the native Odoo discount summary available from the resolved model/view. Discount/promotion semantics are no longer a UI blocker; CI, runtime model/view audit, and browser scroll/footer evidence remain technical gates. No merge/deploy.

### Koreksi sticky/overflow hasil audit runtime — 2026-10-30

Audit CI pada HEAD `2c694f8` menunjukkan tiga akar masalah, bukan toleransi tes:

1. Seluruh aturan footer berada di bawah `body.id-shell-sidebar`. Kelas itu dilepas `id_sidebar.js` saat `ui.isSmall`, sehingga di viewport mobile tidak ada grup sticky (`stickyGroupCount=0`). Aturan footer dipindah keluar scope sidebar agar berlaku juga di mobile dan tata letak klasik.
2. Sticky sempat memakai `top: calc(100vh - 300px)`. Containing block grup total hanya menyisakan sekitar 16px ruang, sehingga kotak tidak pernah benar-benar pinned; audit lama lalu mengambil sampel di luar fase sticky. Footer kembali memakai `position: sticky; bottom: 0`, dan interval pinned diturunkan dari geometri normal-flow (sticky dimatikan sementara), batas containing block, serta `bottom` inset.
3. Pada invoice, grup total adalah kolom `colspan=4` di samping narration; margin inline negatif menambah overflow. Tab `.oe_invoice_lines_tab` kini menjadi elemen sticky (setara group catatan pada SO), kolom narration+total ditumpuk penuh, dan margin negatif dihapus.

Audit Playwright sekarang:

- Mengumpulkan seluruh ancestor sticky dari `.oe_subtotal_footer` dan menolak lebih dari satu (nested sticky).
- Menerima baris list desktop maupun kartu kanban mobile (minimal 10 item) dan menguji trial click tanpa force.
- Mengukur pinned bottom terhadap scrollport bottom pada interval `[pinStart, pinEnd]`, visibility di awal, release setelah interval, serta keterjangkauan item terakhir.
- Mengemulasikan zoom browser 125% lewat CDP `Emulation.setDeviceMetricsOverride` (1152x688 CSS px, DPR 1.25) dan membuktikan metrik browser berubah; bukan sekadar menekan Ctrl+Equal.

Regression: `test_smoke_javascript.py` mengekstrak blok JavaScript produksi dan menjalankan `node --check`; `test_footer_audit_fixture.py` menjalankan fungsi audit produksi pada fixture bottom-sticky terkontrol (pinned lalu released) dan menolak nested sticky; `test_form_scss_compile.py` menjaga kontrak bottom-sticky dan tab invoice.

**Belum terverifikasi:** hasil ini masih memerlukan run CI/browser aktual pada SHA final. Tidak merge/deploy.
