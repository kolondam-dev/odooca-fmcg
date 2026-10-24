# deploy/seed

Berisi dump DB demo (`*.sql.gz`) dan filestore (`*.tgz`) **hanya di mesin build/deploy**. Berkas ini **tidak masuk git** (repo publik; batas ukuran file git).

Distribusi: GitHub **Release asset**. Railway mengunduhnya lewat `SEED_URL` + `SEED_SHA256` (dan `SEED_FILESTORE_URL` + `SEED_FILESTORE_SHA256`); `deploy/init.sh` memverifikasi sha256 sebelum restore.

## Membuat dump (terbukti di sandbox, restore 17 s)
```bash
pg_dump --no-owner --no-acl --exclude-schema=id_meta <db> | gzip > fmcg.sql.gz
sha256sum fmcg.sql.gz
```
- `--no-owner --no-acl`: `init.sh` memulihkan dengan `PGOPTIONS="-c role=<ODOO_DB_USER>"` sehingga objek dimiliki peran Odoo.
- **`--exclude-schema=id_meta` wajib**: skema penanda dibuat `init.sh`; di dump ia akan bentrok.
- Bersihkan attachment aset web sebelum dump agar kecil (dibuat ulang otomatis).
Restore dipicu pada DB tanpa mark `init.base` (DB kosong atau setelah `RESET_DB=<token baru>`).
