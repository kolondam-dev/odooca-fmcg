# DEVELOPMENT

## 1. Peran per lingkungan
| Lingkungan | Agen/pelaku | Peran | Catatan |
|---|---|---|---|
| Sandbox agen | `claude-dev` | Menulis kode, **menjalankan Odoo 19 penuh** (Postgres lokal, tanpa Docker), memodifikasi, memeriksa, memverifikasi; menyerahkan patch zip | `docs/SANDBOX.md`. Tanpa Docker dan tanpa kredensial git/Railway |
| Laptop pemilik | pemilik, `antigravity` | Commit/PR/push, `railway up`, membaca log build/deploy | **Kebijakan: tidak ada Docker lokal** (hemat sumber daya laptop); build/staging/prod di Railway |
| Desain | `claude-design` | Desain antarmuka/PWA | Log sendiri di `agent-log/` |
| GitHub Actions | otomatis | Lint, build image, uji instal dan `init.sh` | Tanpa secret; satu-satunya tempat `docker build` otomatis |
| Railway (Hobby) | `antigravity` | Build dan menjalankan hasil build | Data tidak diedit. Pasang hard usage limit. Terverifikasi hidup (HTTP 200) 2026-10-24 |

Aturan koordinasi antar agen: `docs/AGENT_PROTOCOL.md`.

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

## 4. Alur kerja multi-agen dan sinkron
1. **Sebelum aksi:** `bash scripts/agent/whats_new.sh <agen>` (fetch, commit sejak commit terakhir agen, entri baru `agent-log/*.log`, cabang di depan `main`). Baca `docs/HANDOFF.md`.
2. **Kerja:** ubah di sandbox, jalankan Odoo (`docs/SANDBOX.md`), verifikasi.
3. **Sesudah aksi:** `bash scripts/agent/log_entry.sh <agen> INFO "<judul>" "<butir>"...` dan entri HANDOFF.
4. **Serah terima `claude-dev` (patch zip)**; Downloads sejajar dengan folder `dev`, repo di `dev/odooca-fmcg`:
```bash
cd dev/odooca-fmcg
git fetch origin && git checkout main && git pull --ff-only     # basis = main terbaru (atau cabang yang disebut agen)
unzip -o ../../Downloads/<nama-patch>.zip
git status && git diff --stat
git add -A
git add --chmod=+x deploy/*.sh scripts/*.sh scripts/*.py scripts/sandbox/*.sh scripts/agent/*.sh   # izin eksekusi hilang saat unzip
git commit -F - <<'EOF'
<tipe>(<lingkup>): <ringkasan>

<butir perubahan, hasil verifikasi, yang belum diuji>

task managed by claude-dev agent at <timestamp dari patch>
EOF
git push
```
5. **Deploy:** Railway membangun dari `main`; `antigravity` juga bisa `railway up` dari lokal. **Perbaikan yang belum di-merge ke `main` tidak ikut build otomatis.** Pemilik menempelkan log build/deploy bila ada masalah. Hobby: tiap push menyalakan layanan; pasang hard usage limit.
6. Perubahan agen lain sudah ada di repo: selalu mulai dari `whats_new.sh`, bukan dari salinan sandbox lama.

## 5. Uji statis lokal
```bash
pip install ruff pyyaml
ruff check . && python scripts/check_manifests.py
bash -n deploy/init.sh deploy/addons_path.sh scripts/*.sh scripts/sandbox/*.sh scripts/agent/*.sh
```
Diagnosis instance yang sedang berjalan (read-only, mis. Railway): `python3 scripts/ops/odoo_snapshot.py --url https://<host> --db <db> --user admin --out snapshot.md` (sandi diminta lewat prompt tersembunyi; tidak disimpan/dicetak). Memuat modul terinstal vs diharapkan, bahasa, menu, jumlah data, kelengkapan field outlet/produk, user, transaksi. Hanya baca; bisa dipakai di proyek lain (`--expect-modules`, `--extra-models`, `--menu-root`).
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

## 11. Gate supervisi seed
Kontrak dan checklist bukti: `docs/reviews/SEED_INVARIANT_CONTRACT.md`. Jalankan
validator independen sebelum mengajukan integrasi dataset; output merah adalah
pekerjaan terbuka. Validasi lokal tidak menggantikan rekonsiliasi runtime Odoo.
