# Deployment demo — 30 Oktober 2026

Scope mengikuti DEMO_ENVIRONMENT_SCOPE_DECISION.md. PR45 merged7d667915. Tidak ada reset/provisioning/upgrade database pada sesi ini.

## Deployment yang dijalankan

- field-pwa: pinned49739350127b9514af8fb3cd096ac2bc3b1adbc5, PWA_BUILD_MODE=staging, deployment84abcb97-814d-4073-8a23-be2ca0890e11 SUCCESS; build-info publik mode staging.
- demo-gateway: service df1e5bd0-3103-47aa-b56f-bf5d3706bd3d, domain demo-gateway-production-abd1.up.railway.app, image resmi nginx:1.28-alpine; deployment8f42f93b-0a29-45eb-886a-d05f70380716 SUCCESS. Healthcheck saja belum membuktikan backend siap.
- Odoo: log runtime database railway, endpoint mobile langsung404. Ini belum merupakan audit schema/module/database menyeluruh; jangan mengasumsikan fmcg_base dari brief lama.

## Koreksi jalur deployment gateway

Percobaan source repo dengan Root Directory /pwa memakai default pwa/railway.toml yang memilih static Dockerfile. Akibatnya healthz200 berasal dari static PWA, bukan proxy. Variabel RAILWAY_DOCKERFILE_PATH tidak mengubah hasil probe tersebut. Plugin update-service menolak railwayConfigFile dengan pesan Config as Code deprecated, use Infrastructure as Code.

Jalur yang dipakai: image resmi nginx:1.28-alpine dan Start Command yang merekonstruksi tiga file gateway yang sudah diaudit pada4973935. Perintah dibuat dari source, tanpa credential atau unduhan kode saat startup:

```bash
cd pwa
node scripts/railway-gateway-command.mjs
```

Salin hasil lengkap sebagai Start Command pada service gateway, lalu connect image resmi. Generator memakai base64 hanya untuk mempertahankan byte dan kutip file saat melewati konfigurasi shell; bukan enkripsi/secret. Untuk reproduksi hasil deployment sesi ini, jalankan generator pada source4973935 dengan generator dari PR ini. Source gateway tidak berubah dalam PR ini.

Variabel gateway: PORT=8080, STAGING_HOST=demo-gateway-production-abd1.up.railway.app, ODOO_UPSTREAM referensi private-domain service odooca-fmcg port8069, FIELD_UPSTREAM referensi private-domain field-pwa port8080. Tidak membuka TCP proxy database. Domain existing Odoo/PWA belum dicabut.

## Pekerjaan backend yang belum dapat dieksekusi melalui plugin

Plugin tidak menyediakan shell container, backup DB/filestore atau introspeksi ORM. OAuth juga hanya mengembalikan nama variabel, bukan nilai database/credential. Tidak mengganti credential agar dapat melewati batas akses ini.

Operator dengan CLI Railway aktif perlu:
1. Baca runtime target aktual dan modul terpasang; buat backup database+filestore yang dapat dipulihkan sebelum perubahan data.
2. Adaptasi provisioning exact-target demo sesuai keputusan pemilik, review dan uji idempotensi/preservasi data non-fixture. Guard staging existing tetap utuh.
3. Install/upgrade id_mobile_api secara terarah tanpa reset atau re-run seluruh seed. Jangan menyalakan FORCE_UPGRADE umum tanpa audit efeknya.
4. Buat company/dua akun/assignment TEST melalui jalur yang telah direview; verifikasi bootstrap/snapshot dan isolasi foto.
5. Catat hasil login+GPS/foto aktual dengan owner. Endpoint404 dan akun belum tersedia berarti acceptance belum siap walau build/deploy SUCCESS.

Tidak ada klaim deployment end-to-end selesai.
