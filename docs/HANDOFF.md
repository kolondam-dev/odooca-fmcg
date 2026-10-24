# HANDOFF

## 2026-10-24 — antigravity (laptop/Railway) — [M1] Implementasi Model Master Data FMCG, Geografi Kecamatan & Tipe Armada di id_base
**Berubah:**
- `addons/id_base`:
  - Model hierarki: `id.principal`, `id.brand`, `id.sub.brand`.
  - Model dimensi geografi & armada: `id.channel`, `id.tier`, `id.coverage.area`, `id.district` (Kecamatan), `id.subdistrict` (Kelurahan & Kode Pos Sulut), `id.fleet.type` (9 tipe armada operasional dengan dimensi kargo dan tonase riil pabrikan).
  - Ekstensi `res.partner`: `channel_id`, `tier_id`, `coverage_area_id`, `district_id`, `subdistrict_id`, `principal_ids`, `credit_mode`, `pic_name`, `pic_phone`, `delivery_notes`.
  - Ekstensi `product.template`: `principal_id`, `fmcg_category` (Food, RTD, Home Care, Personal Care, Dairy, dll), `brand_id`, `sub_brand_id`, `inner_qty` (fraction dinamis), `carton_qty`.
  - Akses keamanan (`security/ir.model.access.csv`) untuk seluruh model baru.
  - Tampilan views & menu `views/principal_views.xml`, `views/fmcg_dimension_views.xml`, `views/res_partner_views.xml`, `views/product_template_views.xml`, `views/menu_views.xml`.
  - Master seed bawaan (`data/`): 4 channel, 4 tier, 4 coverage area, 4 principal nasional (Mayora, Unilever, Kapal Api, Wings) beserta brand unggulan, 9 tipe armada operasional standar FMCG dengan kubikasi box riil, serta 18 kecamatan kunci se-Sulut (Manado, Bitung Maesa, Tomohon, Tondano, Kawangkoan, Minut, Minsel) dan kelurahan dengan kode pos resmi.
  - Manifest `__manifest__.py` diperbarui ke versi `19.0.1.0.0`, depends `["base", "contacts", "product"]`.
- Blueprint & Pemetaan Master Data (`master_data_mapping_and_seed_plan.md`):
  - Penyelarasan target omset Rp 5-6 BIO IDR per bulan dengan universe 620 outlet (coverage 65% = 403 outlet aktif, gap 35% untuk narasi improvement demo).
  - Pemetaan berbasis Kecamatan (Manado Urban, Maesa Urban Bitung, Tomohon/Tondano/Kawangkoan Hinterland, Minut/Minsel Luar Kota).
  - Penugasan Direct Selling (Horeka/RS) langsung ke Branch Manager & Sales Supervisor.
  - Arsitektur Multi-UoM dinamis (Satuan Terbesar, INNER/FRACTION dinamis, Satuan Terkecil/Base UoM untuk retur eceran) dan kode SKU sama persis dengan faktur principal Coretax.
  - 9 Lokasi gudang fisik murni WMS (GD Utama, Eaches, Return Staging, Bad Stock, Promo/Sample, Premium, Cold Storage, Dock, In-Transit).
  - Multi-diskon line item (slot principal > 1) dan traceable footer cashback/promo budget.
  - Data armada dengan dimensi p×l×t kargo, kubikasi/tonase riil pabrikan, serta kelengkapan STNK dan KIR.
- Pemodelan Sebaran Outlet & Rute Kunjungan PJP (`pjp_and_outlet_distribution_model.md`):
  - Penataan 403 outlet aktif dalam 18 kecamatan kunci se-Sulut (Universe 620 outlet, Coverage 65%).
  - Segregasi channel ketat (MT 8-10 call, GT 20-22 call, Canvass 25-30 call, Direct Selling Horeka).
  - Sinkronisasi rute harian Senin-Sabtu dengan jadwal loading gudang dan penugasan armada pengiriman H+1.


**Diverifikasi (bagaimana):**
- `python -m ruff check addons/id_base` lolos (0 lint error).
- `python scripts/check_manifests.py` lolos (`manifest ok: 1 addon (id_base)`).
- `scripts/agent/whats_new.sh antigravity` dijalankan sebelum aksi.
- `scripts/agent/log_entry.sh antigravity` dicatat ke `agent-log/anti-gravity.log`.

**Belum diuji:**
- Upgrade modul `id_base` di server Railway (akan otomatis ter-deploy setelah merge PR).
- Pemodelan cluster geografis dan simulasi sebaran 400 outlet PJP.

**Butir terbuka:**
- Sesi pemodelan mendalam PJP & outlet distribution (target giliran berikutnya).
- Pembuatan file seed CSV/XML untuk 400 outlet dan 150 SKU produk.

**Menunggu:** pemilik repo (review PR lokal; instruksi untuk push saat sudah siap).


## 2026-10-24 — claude-dev agent (sandbox) — Sinkron remote, verifikasi perbaikan AntiGravity, protokol multi-agen
**Berubah:** `AGENTS.md` (protokol 8 aturan), `docs/AGENT_PROTOCOL.md` (peran, sebelum/sesudah aksi, format commit dan log), `scripts/agent/whats_new.sh` dan `log_entry.sh`, `agent-log/claude-dev.log`, `docs/DEVELOPMENT.md` §1 dan §4 (kebijakan tanpa Docker lokal, alur multi-agen, perintah patch + tanda tangan), `docs/SANDBOX.md`, `scripts/sandbox/sandbox_up.sh` (user `odoo`, salinan addons), `ci.yml` (`bash -n` mencakup skrip agen). Izin eksekusi skrip diperbaiki (100755).
**Diverifikasi (bagaimana):** (1) `git fetch` menemukan commit AntiGravity `eebee64` dan merge PR #1 `fcd62e8`; (2) perbaikan `init.sh` AntiGravity diuji independen di sandbox: A DB kosong (HTTP 200, Odoo berjalan sebagai `odoo`, data dir `odoo:odoo`, 0 galat), B restart 5 detik semua dilewati, login admin OK, `chown -R` 3000 berkas = 22 ms; (3) `whats_new.sh` dan `log_entry.sh` dijalankan pada repo nyata (2 bug diperbaiki); (4) `ruff`, `check_manifests.py`, `bash -n`, YAML lolos.
**Belum diuji:** job `init-test`/`install-test` di GitHub Actions; `gosu`/`runuser` di image `odoo:19.0` (di sandbox yang terpakai `runuser`); `docker build` di luar Railway; `--ignore-installed` dapat menimpa paket Debian (diterima untuk demo); tanda tangan commit belum divalidasi otomatis.
**Butir terbuka:**
1. Konfirmasi nama tanda tangan dan nama log untuk `claude-design` (usulan: `claude-design agent`, `agent-log/claude-design.log`).
2. Perlu job CI yang menolak commit non-merge tanpa tanda tangan? (belum dibuat)
3. Skrip tercatat 100644 di mesin pemilik: pakai `git add --chmod=+x` (lihat DEVELOPMENT §4); cek `git config core.fileMode`.
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik (unzip, commit, push); `antigravity` (log Railway setelah merge); `claude-design` (belum aktif di repo).

## 2026-10-24 — AntiGravity Agent (Railway Staging/Production) — Perbaikan Build Docker & Deploy Sukses di Railway
**Berubah:**
- `Dockerfile`: pip install menggunakan `--ignore-installed` pada dependensi OCA untuk mencegah konflik paket Debian (`typing-extensions`); melepas direktif `USER odoo` agar entrypoint kontainer dapat melakukan chown volume sebelum menurunkan hak akses.
- `deploy/init.sh`: mendeteksi inisialisasi root kontainer, mengamankan kepemilikan `$DATA_DIR` (`/var/lib/odoo`) ke `odoo:odoo`, lalu mengeksekusi script sebagai `odoo` via `gosu`/`runuser`/`su`.
- `.gitignore`: mengecualikan `agent-log/*.log` agar log koordinasi agen tersimpan di repo.
- `agent-log/anti-gravity.log`: dibuat untuk melacak aktivitas dan koordinasi antar-agen.

**Diverifikasi (bagaimana):**
- Static checks: `ruff check .` lolos, `python scripts/check_manifests.py` lolos, `bash -n deploy/init.sh` lolos.
- Build live di Railway (`ca437306-0e9d-414e-accf-5c23fa9de3cc`): image assembly sukses 100% (26 repo OCA & dependensi terpasang).
- Runtime live di Railway: Odoo 19 CE berhasil inisialisasi database `railway`, menginstal 55 modul termasuk `id_base` ('FMCG Distributor Base') dan `l10n_id` ('Indonesian - Accounting').
- HTTP Probe: `https://odooca-fmcg-demo.up.railway.app/web/login` mengembalikan HTTP 200 OK.

**Belum diuji:**
- Merge branch / patch dari Agent 2 (Claude Design).
- Fungsionalitas login admin via browser dengan sandi baru dari env.
- Restore dump database dari Release asset.

**Butir terbuka:**
1. Integrasi kode Agent 2 (Design modification) saat sudah siap dimerge.
2. Pengujian fitur modul FMCG di live staging Railway.

**Menunggu:** Pemilik repo & Agent 2 (Claude Design) untuk integrasi kode design.

## 2026-10-23 — Claude (sandbox, Odoo 19 penuh) — Verifikasi M0 dengan menjalankan Odoo
**Berubah:** `init.sh` (urutan `shell` sebelum opsi; build `base`→ID/IDR→modul; reset tabel satu per satu); `oca.lock` 18→26 repo; CI + job `init-test`; `scripts/sandbox/*`; `docs/SANDBOX.md`; `docs/SCOPE.md` v0.6; jebakan baru di `docs/ODOO19_PITFALLS.md`; spike dipersempit.
**Diverifikasi (bagaimana):** di sandbox (Ubuntu 24.04, Postgres 16, Odoo `f4378f29`): (1) `id_base` terinstal, uji 0 failed; (2) 65 modul core+OCA → 165 modul terinstal, 0 ERROR; (3) `init.sh`: A DB kosong (HTTP 200 ±66 s), B restart (6 s, semua dilewati), C reset+restore (17 s), D token lama diabaikan, E reset+build (±69 s); login admin sandi baru OK, `admin/admin` ditolak, daftar DB ditolak, `web.base.url` terkunci, objek dimiliki `odoo_app`, chart `id` 118 akun, 0 pajak 15%.
**Bug yang ditemukan lewat uji dan diperbaiki:** `shell` setelah opsi; `DROP SCHEMA CASCADE` → `out of shared memory`; dump naif bentrok dengan `id_meta`; COA generik termuat bila negara belum ID.
**Koreksi atas klaim sebelumnya:** 6 modul OCA yang saya tulis "ada" ternyata `installable: False` (`base_rest`, `base_rest_auth_api_key`, `pydantic`, `rest_log`, `queue_job_batch`, `base_import_async`).
**Belum diuji:** `docker build` + `pip install` di image Ubuntu (apt vs pip); job CI `init-test`/`install-test`; Railway (volume, variabel, restore dari Release asset); seed engine; `postinit` untuk bahasa `id_ID`; fungsional modul OCA (hanya terinstal); `fastapi` sebagai endpoint; instal ulang tanpa sandbox.
**Butir terbuka:**
1. Log build/deploy Railway setelah push pertama (tempel ke percakapan).
2. Deploy otomatis setiap push menyalakan layanan Hobby: pasang hard usage limit.
3. `requirements.txt` seluruh repo OCA ikut terpasang di image (pysaml2, numpy, paramiko, dll.): pertimbangkan hanya yang dipakai.
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik repo (unzip, commit, push, log Railway).

## 2026-10-23 — Claude (chat, sandbox tanpa Docker) — M0 kerangka repo
**Berubah:** kerangka repo awal (Dockerfile, `deploy/init.sh`, compose, CI, `oca.lock`, `scripts/`, addon `id_base`, dokumen). `docs/SCOPE.md` v0.5, Playbook v0.4, Glosarium draf.
**Diverifikasi (bagaimana):**
- `scripts/fetch_oca.sh` dan `scripts/oca_bump.sh` dijalankan pada 2 repo OCA nyata; SHA cocok.
- `scripts/check_manifests.py` lolos; `ruff check .` lolos; `bash -n` semua skrip; YAML (`ci.yml`, `docker-compose.yml`) valid.
- Isi source Odoo 19 CE (commit `f4378f29`, 2026-10-22) dan 18 repo OCA 19.0 diperiksa untuk keberadaan modul (lihat SCOPE §5).
**Belum diuji:** `docker build`; `deploy/init.sh` (peran DB, restore, reset, postinit, `odoo shell`); instal `id_base` di Odoo 19; CI; `pip install` dependensi OCA di image (risiko bentrok paket apt); `admin_passwd` polos di `odoo.conf`; opsi `--without-demo=true`, `--no-database-list`; kebenaran tag `odoo:19.0` di Docker Hub (digest belum di-pin).
**Butir terbuka:**
1. Hasil run pertama CI dan `docker compose up` (perbaiki kerusakan yang muncul).
2. Spike API/offline (`docs/spikes/SPIKE_API_OFFLINE.md`) sebelum M6.
3. Kontrol dokumen asal Odoo/mobile pada mode secondary (SCOPE §13 #1).
4. Pemegang hak cipta pada header lisensi.
**Menunggu:** pemilik repo (commit pertama dan menjalankan CI).

<!-- Entri baru di atas entri lama. Templat ada di docs/DEVELOPMENT.md §10. -->
