# Aktivasi mobile pada database demo existing

Mengimplementasikan keputusan scope PR45. Guard disposable PR44 tetap utuh; jangan mengganti nama database atau menyetel flag staging untuk memaksa skrip lama berjalan.

## Pemeriksaan sesi dan batas akses

Pada pembacaan aktual, gateway/field-pwa mode staging tersedia; GET bootstrap mobile404 dan /web/login200. Railway OAuth connector dapat membaca konfigurasi/nama variabel, tetapi nilainya disamarkan dan tidak menyediakan shell/SSH. Percobaan memasang/memeriksa CLI melalui npm keluar1, tanpa binary yang dapat dipakai; tidak ada login CLI yang berhasil. Karena itu belum ada backup, instal addon, provisioning atau acceptance E2E yang dilakukan agen pada server.

Scope target tetap project569df00d-48e8-411a-93a5-df39ba97f16b, environment47b72704-4054-4941-b978-d42c1befca55, service Odoo56186eb1-eec2-4604-92d3-f449504cba4a. Nama DB tidak diasumsikan dari nama service atau environment, termasuk fmcg_base: konfirmasi lewat preflight read-only. Otorisasi owner sudah berlaku; blocker adalah akses eksekusi, bukan persetujuan ulang.

## Urutan operator setelah akses shell tersedia

1. Pilih project pleasant-caring, environment production dan service odooca-fmcg secara eksplisit. Periksa SSH context/identity dan SHA image. Jalankan sebagai OS user odoo, dengan PGUSER/PGPASSWORD dioverride ke Odoo role; jangan cetak printenv atau password. Jangan memakai init.sh shell karena entrypoint tersebut juga mengubah role/kepemilikan DB sebelum masuk shell.
2. Jalankan `mobile_demo_preflight.py` melalui Odoo shell pada DB runtime. Catat DB, deployment SHA, module state/version, jumlah data dan filestore. Skrip hanya baca. Belum ada perintah instal/provision yang boleh didasarkan pada tebakan DB.
3. Dalam maintenance window yang sudah disetujui, hentikan aktivitas penulisan aplikasi secara terkontrol. Ambil pg_dump custom-format dan arsip filestore DB yang sama; simpan di lokasi privat di luar git dan di luar direktori filestore yang sedang diarsipkan. Periksa `pg_restore --list`, daftar archive, ukuran/hash dan satu pasangan DB/filestore yang konsisten. Simpan salinan pemulihan di luar layanan; hash lokal tidak membuktikan backup konsisten, offsite atau siap restore. Jangan menyalin file backup CI sebagai backup server.
4. Setelah target/backup terkonfirmasi, jalankan instal/upgrade native yang ditargetkan hanya `id_mobile_api` pada DB tersebut dengan `--no-http --stop-after-init`. Jangan memakai FORCE_UPGRADE global, RESET_DB, init ulang atau seed ulang. Rekam log dan ulangi baseline setelah aktivasi addon; instal dependency native dapat memerlukan perubahan schema, jadi preservasi tahap instal harus diperiksa terpisah. Restart Odoo terkontrol dan verifikasi anonymous bootstrap menjadi401, bukan404.
5. Sesudah review/test PR ini dan image memuat kode, jalankan `provision_mobile_demo.py`. Isi database hasil preflight, opt-in `PRESERVE_EXISTING_DEMO`, dua password dummy berbeda minimal12 karakter dan path manifest backup di environment proses operator. Jangan mengubah variabel database layanan untuk meloloskan guard.
6. Verifikasi dua akun/assignment TEST, login native melalui gateway, bootstrap, daily sync, preview maps, upload strict bila posisi memenuhi geofence, serta penolakan foto akun lain. Baru bagikan login/password dummy sesi ke owner. Belum PASS perangkat sebelum owner mencoba.

Perintah pada shell service, dengan variable yang sudah diperiksa (bukan default tebakan):

```bash
env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
  odoo shell -c /tmp/odoo.conf -d "$PGDATABASE" --no-http \
  < /opt/scripts/ops/mobile_demo_preflight.py

# Hanya setelah backup dan target dinyatakan sesuai; bukan menjalankan ulang init/seed.
env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
  odoo -c /tmp/odoo.conf -d "$PGDATABASE" -i id_mobile_api --no-http --stop-after-init

env PGUSER="$ODOO_DB_USER" PGPASSWORD="$ODOO_DB_PASSWORD" \
  odoo shell -c /tmp/odoo.conf -d "$FMCG_DEMO_DATABASE" --no-http \
  < /opt/scripts/ops/provision_mobile_demo.py
```

## Manifest dan guard provisioning existing

`FMCG_DEMO_DATABASE` harus sama dengan runtime PGDATABASE dan env.cr.dbname. Ketiga Railway runtime IDs harus sama persis dengan target di atas. `FMCG_DEMO_OPT_IN=PRESERVE_EXISTING_DEMO`; password diberikan lewat FMCG_DEMO_PASSWORD_1/2 dan tidak dicetak. `FMCG_DEMO_BACKUP_MANIFEST` menunjuk file JSON privat:

```json
{
  "database": "NAMA_DB_HASIL_PREFLIGHT",
  "target": {
    "RAILWAY_PROJECT_ID": "569df00d-48e8-411a-93a5-df39ba97f16b",
    "RAILWAY_ENVIRONMENT_ID": "47b72704-4054-4941-b978-d42c1befca55",
    "RAILWAY_SERVICE_ID": "56186eb1-eec2-4604-92d3-f449504cba4a"
  },
  "created_at": "ISO8601_UTC_SAAT_BACKUP",
  "database_dump": {"path": "/PRIVATE/ACTUAL/database.dump", "sha256": "SHA256_FILE_ASLI"},
  "filestore_archive": {"path": "/PRIVATE/ACTUAL/filestore.tar.gz", "sha256": "SHA256_FILE_ASLI"}
}
```

Guard memeriksa target/waktu maksimal24jam, dua file nyata berbeda, nonempty, path absolut/non-symlink dan hash persis. Ini bukti integritas file lokal dan identitas manifest; bukan validasi format dump, uji restore atau bukti tidak adanya penulisan saat backup. Operator tetap bertanggung jawab atas langkah3.

Provisioning membuat/memperbarui hanya fixture yang dimilikinya melalui helper PR44: company TEST, dua akun capture, produk/pricelist/outlet/kantor TEST dan assignment per hari WITA. Login existing yang bukan milik fixture ditolak. Tidak melonggarkan ACL, auth atau geofence dan tidak memberi hak write Sales/Stock/admin.

Sebelum write, guard mengunci tabel preservasi dalam SHARE mode dengan lock_timeout5detik: reads tetap tersedia, competing writers dapat tertahan selama transaksi operator. Baseline/hash row yang sudah ada pada20 tabel model business/master/attachment dibandingkan setelah provisioning; fixture milik skrip dan related partner/template miliknya dikecualikan secara eksplisit. Pengecualian native yang diaudit: res.company.create Odoo19 menautkan company baru ke operator dan SUPERUSER_ID. Hanya tambahan company TEST tersebut dan opsional grup UI multi-company yang diizinkan pada dua user teknis ini. Audit write_uid/write_date asli dipertahankan (tidak dikembalikan atau disamarkan); selain kedua kolom audit pada user teknis dan partner profil yang terikat padanya, seluruh kolom row tetap dibandingkan, dan perubahan audit hanya boleh oleh operator dengan waktu tidak mundur. Akses/company/group semua user existing lain harus identik. Partner customer lain tidak mendapat pengecualian audit. Recompute native diselesaikan dalam env operator sebelum snapshot dibaca sebagai akun capture. Ringkasan operator melaporkan tambahan membership aktual. Sumber: https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_company.py .

Jumlah/set transaksi SO/DO/move/quant/invoice/AML tidak boleh bertambah. Perubahan row non-fixture menyebabkan rollback seluruh provisioning. Lock dilepas saat entrypoint commit/rollback. Jika timeout, hentikan percobaan dan selesaikan aktivitas writer dahulu, jangan menghapus guard. Tidak ada reset/delete/restore ataupun raw SQL write data business.

Preservasi ini mencakup tabel yang disebut PROTECTED di existing_demo.py, bukan semua tabel/M2M/sequence database atau seluruh byte filestore. Tidak boleh dipakai sebagai pengganti backup dan pemeriksaan preservasi tahap instal addon. CI menyiapkan DB clone dengan contact/SO/file existing, dump+archive nyata, lalu menjalankan entrypoint operator dua kali dengan runtime Railway yang disimulasikan; ini bukan bukti server Railway telah dijalankan.

## Status hasil

Kode/preparasi dan CI adalah bukti terpisah dari deployment. Selama akses shell belum tersedia, jangan menyatakan akun sudah dibuat, backup sudah ada, module sudah aktif atau alur E2E telah lulus. Gunakan STAGING_DEVICE_ACCEPTANCE.md untuk hasil aktual setelah activation.
