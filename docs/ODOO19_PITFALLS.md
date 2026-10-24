# Jebakan Odoo 19 yang sudah terbukti
- `account.account.code` disimpan per company (`code_store` jsonb); field company-dependent & nama terjemahan = jsonb → query SQL harus `->>`.
- Grup: `group_ids` (bukan `groups_id`) di v19; operator domain `<>` sudah deprecated (gunakan `!=`).
- `tracking=` pada `fields.Selection` tanpa mail.thread → warning; hapus.
- `stock.scrap` memakai lokasi inventory-usage → akun beban lain; pastikan akun terpetakan.
- Cron `_quant_tasks` menghapus quant nol → jangan jadikan id quant kunci verifikasi.
- Odoo menolak `db_user=postgres`; env `PG*` menimpa `odoo.conf`.
- Menyalin DB via template tidak menyalin filestore → salin folder `filestore/<db>` juga.
- Restore dump: butuh `--no-owner --no-acl`, set peran & `ALTER ... OWNER`; skema `public` perlu izin.
- Aset web (attachment) dibuat ulang otomatis; hapus sebelum dump agar kecil.
- `web.base.url` + `web.base.url.freeze` agar link tidak berubah.
- Waktu simulasi: gunakan freezegun; zona bisnis ≠ UTC.
- Set iteration order tergantung hash → urutkan; `PYTHONHASHSEED=0`.
- Hak akses admin tidak otomatis mencakup semua aplikasi → beri grup bisnis eksplisit di postinit.
- Python 3.12 venv di sandbox; Postgres lokal (port non-standar, socket dir milik user postgres).
- Verifikasi tarif/pajak di sumber resmi dan beri tanggal; jangan menulis angka dari ingatan.

## Temuan M0 (terbukti di sandbox, 2026-10-23)
- **COA Indonesia hanya termuat bila negara perusahaan = ID *sebelum* modul akuntansi terinstal.** Kalau tidak, COA generik (US, pajak 15%) termuat lebih dulu. Urutan benar: `-i base` → set `country_id=ID`, `IDR` aktif dan jadi mata uang → `-i account,l10n_id,...`. Hasil: chart `id`, 118 akun, 3 pajak "12% (Non-Luxury Good)" bernilai 11%, 0 pajak generik.
- **`DROP SCHEMA public CASCADE` dalam satu transaksi → `ERROR: out of shared memory`** (kuota lock Postgres habis pada ribuan objek Odoo). Hapus tabel satu per satu lalu skema.
- **Subperintah Odoo (`shell`) harus ditulis sebelum opsi**: `odoo shell -d db ...`, bukan `odoo -d db ... shell`.
- **Dump seed wajib `--exclude-schema=id_meta`**: dump naif memuat `CREATE SCHEMA id_meta` dan isi `marks`, restore ke DB yang sudah punya `id_meta` akan bentrok.
- **`admin_passwd` hanya lewat berkas konfigurasi** (FileOnlyOption), bukan CLI.
- **Modul OCA 19.0 `installable: False`** (modul ada di repo tetapi tidak bisa dipasang): `base_rest`, `base_rest_auth_api_key`, `base_rest_pydantic`, `pydantic`, `extendable`, `rest_log`, `queue_job_batch`, `queue_job_cron*`, `queue_job_subscribe`, `base_import_async`. Selalu periksa `installable`, bukan hanya keberadaan folder.
- Dependensi OCA bersilang antar repo: `account_financial_report` butuh `date_range` (server-ux); `fastapi` butuh `endpoint_route_handler` (web-api); `sale_exception` butuh `base_exception` (server-tools); `auth_api_key` ada di server-auth. Hitung closure dependensi, jangan menebak.
