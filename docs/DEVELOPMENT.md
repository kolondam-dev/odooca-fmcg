# DEVELOPMENT

## 1. Peran per lingkungan
| Lingkungan | Peran | Catatan |
|---|---|---|
| Sandbox agen | Menulis kode, **menjalankan Odoo 19 penuh** (Postgres lokal, tanpa Docker), memodifikasi, memeriksa, memverifikasi | Lihat `docs/SANDBOX.md`. Tidak ada Docker: `docker build`/CI/Railway tidak bisa diuji di sini |
| Laptop / Claude Code | Edit, `docker compose`, uji instal | Tempat commit/PR (penulis commit = pemilik) |
| GitHub Actions | Lint, build image, uji instal `id_*` pada DB kosong | Tanpa secret; PR fork aman |
| Railway (Hobby) | Menjalankan hasil build | Data tidak diedit. Dinyalakan hanya saat demo/uji; pasang hard usage limit; **matikan deploy otomatis dari git** |

## 2. Aturan wajib
1. Addon custom berawalan `id_`, `license: LGPL-3`, versi `19.0.x.y.z`.
2. String sumber di kode English; terjemahan Indonesia di `i18n/id.po`; istilah FMCG mengikuti `GLOSSARY.md`.
3. Tarif/pajak = konfigurasi bertanggal dengan sumber, bukan konstanta kode.
4. Server menghitung ulang harga/diskon/kredit; klien (PWA) tipis.
5. Perubahan setelah live = patch idempoten bermark baru (`patch_<nama>`); perubahan data = seed ulang + dump baru + referensi baru.
6. Tanpa rahasia di repo. Dump/filestore tidak masuk git.
7. Setiap sesi kerja menulis entri `HANDOFF.md`.
8. **Verifikasi dengan menjalankan Odoo di sandbox sebelum menyerahkan patch.** "Modul ada di repo" tidak cukup: periksa `installable` dan instal sungguhan. Klaim yang belum dijalankan ditandai [BU].
9. Penyerahan kerja dari sandbox = **patch zip** + perintah `unzip`, `git commit` (pesan deskriptif), `git push` (§4). Penulis commit = pemilik repo.

## 3. Peta repo (ubah apa → jalankan apa)
| Ubah | Jalankan |
|---|---|
| `addons/id_*` | `ruff check .`, `python scripts/check_manifests.py`, instal di DB kosong (`-i <modul> --test-tags /<modul>`) |
| `oca.lock` | `scripts/oca_bump.sh` (tinjau diff), `docker build .`, CI |
| `deploy/init.sh` | `bash -n`, `docker compose up` di DB kosong **dan** di DB terisi (uji idempoten + `RESET_DB`) |
| `Dockerfile`, `docker-compose.yml` | `docker build .`, `docker compose up --build` |
| `docs/` | Perbarui `HANDOFF.md`; ubah Playbook = catat di changelog Playbook |

## 4. Alur kerja dan sinkron
1. **Awal sesi (agen):** `git clone`/`git pull` repo publik, bandingkan dengan salinan sandbox (`git diff`), selaraskan dengan commit agen lain. Baca `docs/HANDOFF.md`.
2. **Kerja:** ubah di sandbox, jalankan Odoo (`docs/SANDBOX.md`), verifikasi.
3. **Serah terima:** patch zip berisi berkas yang berubah, relatif terhadap akar repo, dengan perintah berikut (Downloads sejajar dengan folder `dev`, repo di `dev/odooca-fmcg`):
```bash
cd dev/odooca-fmcg          # sesuaikan dari lokasi Anda; akar repo
unzip -o ../../Downloads/<nama-patch>.zip
git status && git diff --stat
git add -A
git commit -m "<pesan deskriptif>"
git push                    # commit pertama: git branch -M main && git push -u origin main
```
4. **Deploy:** Railway berjalan otomatis setelah push (keputusan pemilik). Pemilik menempelkan log build/deploy ke percakapan; agen memperbaiki lewat patch berikutnya. Catatan biaya Hobby: setiap push menyalakan layanan; pasang hard usage limit.
5. Perubahan oleh agen lain sudah ada di repo: agen selalu mulai dari `git pull`, bukan dari salinan sandbox lama.

## 5. Uji statis lokal
```bash
pip install ruff pyyaml
ruff check . && python scripts/check_manifests.py
bash -n deploy/init.sh deploy/addons_path.sh scripts/*.sh scripts/sandbox/*.sh
```
Uji runtime di sandbox agen: `scripts/sandbox/sandbox_up.sh`, lalu `odoo ... -i <modul> --test-tags /<modul> --stop-after-init` dan `scripts/sandbox/test_init.sh` (lihat `docs/SANDBOX.md`).

## 6. Invarian data
Lihat `docs/SCOPE.md` §10. Menjadi uji audit dan snapshot di M2.

## 7. Variabel deploy dan urutan init
| Variabel | Wajib | Keterangan |
|---|---|---|
| `PGHOST` `PGPORT` `PGUSER` `PGPASSWORD` `PGDATABASE` | ya | Admin Postgres (Railway: referensi dari layanan Postgres) |
| `ODOO_DB_USER` `ODOO_DB_PASSWORD` | ya | Peran untuk Odoo; **bukan** `postgres` |
| `ADMIN_PASSWD` | ya | Master password Odoo (ditulis ke `/tmp/odoo.conf`) |
| `BASE_URL` | disarankan | `web.base.url` + `web.base.url.freeze` |
| `ADMIN_LOGIN_PASSWORD` | disarankan | Kata sandi login `admin` |
| `INIT_MODULES` | tidak | Default `id_base,l10n_id` (jalur tanpa dump) |
| `SEED_URL` `SEED_SHA256` `SEED_FILESTORE_URL` `SEED_FILESTORE_SHA256` | tidak | Dump dari Release asset |
| `RESET_DB` | tidak | Token **baru** untuk reset; hapus variabel setelah selesai |
| `ODOO_WORKERS` `ODOO_MAX_CRON` `PORT` | tidak | Default 0 / 1 / 8069 |

Urutan `deploy/init.sh` (diuji 5 skenario di sandbox, `docs/SANDBOX.md`): tunggu Postgres → peran & kepemilikan → skema `id_meta` → `/tmp/odoo.conf` → reset (token baru; tabel dihapus satu per satu) → restore dump **atau** build penuh (`base` → perusahaan ID/IDR → `INIT_MODULES`; mark `init.base`) → `postinit_v1` → jalankan Odoo. Semua langkah ber-mark; restart aman (±6 s).

**Railway Hobby:** nyalakan layanan hanya saat perlu; pasang hard usage limit; matikan auto-deploy dari git (push tidak boleh menyalakan layanan). Biaya dan batas: `docs/SCOPE.md` §4B.

## 8. Jebakan Odoo
`docs/ODOO19_PITFALLS.md` (terbukti dari proyek rujukan). Tambahan M0: `admin_passwd` hanya lewat berkas konfigurasi (FileOnlyOption); env `PG*` dibaca Odoo, jadi proses Odoo dijalankan dengan `env PGUSER=... PGPASSWORD=...` eksplisit.

## 9. Definition of done
**M0:** CI hijau (static + install-test); `docker compose up` menampilkan login Odoo; `id_base` terinstal; dokumen & HANDOFF terkini. **Keseluruhan (per skill deploy):** seed deterministik lulus audit; dump + sha256 + referensi konsisten; restore ke DB kosong → snapshot == referensi; Dockerfile menyalin seed; log bersih; tanpa rahasia di repo.

## 10. Templat HANDOFF
```
## YYYY-MM-DD — <agen/lingkungan> — <judul>
**Berubah:** ...
**Diverifikasi (bagaimana):** ...
**Belum diuji:** ...
**Butir terbuka:** 1. ...
**Menunggu:** <siapa>
```
