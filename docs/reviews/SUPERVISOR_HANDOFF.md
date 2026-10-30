# Estafet supervisor — odooca-fmcg

Snapshot verifikasi: 30 Oktober 2026, sekitar 12:00 WIB (Asia/Jakarta). Repository: https://github.com/kolondam-dev/odooca-fmcg. Main saat pemeriksaan: `7d667915e7b9d839084b974e03b91e5ec4ee025b`.

Dokumen ini memindahkan konteks dan metode kerja, bukan memberikan verdict permanen atau otorisasi baru. SHA, CI, akses dan deployment wajib dibaca ulang sebelum bertindak. [F] fakta terverifikasi pada snapshot; [BU] belum dibuktikan; [A] asumsi yang perlu dikonfirmasi.

## Daftar isi

1. Mandat dan tiga langkah pertama
2. Aktor dan tanggung jawab
3. Domain dan kontrak bisnis
4. PR aktif dan temuan terbuka
5. Riwayat integrasi penting
6. Environment dan runtime
7. Otorisasi pemilik dan batas akses
8. Metode review dan teknik pembuktian
9. Merge, deployment dan komunikasi
10. Sumber dan prompt pengganti

## 1. Mandat dan tiga langkah pertama

Ambil peran supervisor/reviewer yang memeriksa source, CI dan runtime; jangan hanya menerima laporan implementer. Pengguna menghendaki verdict konkret yang dapat langsung dieksekusi, tanpa dugaan dan tanpa siklus “agent menunggu supervisor, supervisor menunggu agent”. Jelaskan siapa memegang aksi dan bukti keluaran yang diperlukan.

Langkah awal agent pengganti:

1. Baca `AGENTS.md`, `docs/AGENT_PROTOCOL.md`, `docs/DEVELOPMENT.md`, entri terbaru `docs/HANDOFF.md`, kontrak domain dan komentar review terakhir. Jalankan `bash scripts/agent/whats_new.sh codex --since <checkpoint-yang-diverifikasi>`; pilih checkout/worktree terisolasi.
2. Refresh metadata PR36/39/46/47, main, checks dan Railway jika tugas menyentuh runtime. Jangan menganggap status snapshot ini masih berlaku. Baca diff baru sejak review yang relevan.
3. Prioritaskan re-review fix PR39 ketika ada HEAD baru; review independen PR46 dan PR47 sebelum mengklaim kesiapan provisioning/acceptance. PR36 tetap perlu investigasi kegagalan install/browser terbaru. Jangan merge PR lain karena ada izin merge pada PR terdahulu.

Skill portable tersedia di `.agents/skills/supervise-pr-evidence/SKILL.md`; baca referensinya sesuai domain. Agent di luar ChatGPT dapat memakai file repository ini sebagai instruksi review tanpa akses direktori skill personal pemilik.

## 2. Aktor dan tanggung jawab

| Aktor | Domain/peran aktual | Aksi dan bukti yang diharapkan |
|---|---|---|
| Franky / `kolondam-dev` | Pemilik proyek, keputusan bisnis, penerimaan demo, otorisasi merge/deploy | Menentukan scope; pengujian perangkat; keputusan aturan bisnis. Jangan meminta ulang otorisasi yang jelas sudah diberikan. |
| Codex supervisor (peran yang diwariskan) | Review lintas domain, audit source/CI/runtime, verdict, merge berotorisasi | Reproduksi counterexample, acceptance jelas, komentar PR, preflight exact HEAD. Pernah mengimplementasikan dokumentasi/deploy PR45–46; ungkapkan peran tersebut saat mengklaim independensi. |
| Antigravity | Seed kanonikal, loader historis perpetual, accounting guards, full runtime; operator Railway jika akses CLI tersedia | PR14/15/37/39 dan bukti Odoo/PostgreSQL. Nama agent tidak membuktikan akses CLI masih aktif. |
| Codex-pwa / `agent-codex-pwa` | PWA, API Odoo mobile, sesi, evidence, maps, provisioning | PR33/34/38/40–44/47. Dapat menjadi operator jika punya akses CLI/shell; tidak harus Antigravity. |
| Claude-design | UI native Odoo dan browser smoke | PR32/35/36, title/form/footer/sticky/overflow. Dashboard native berikutnya, belum otomatis selesai dari roadmap. |
| Claude-dev | Fondasi addon, seed, scripts dan dokumentasi sesuai protokol lama | Peran historis; lihat signature/log aktual. Protokol awal memakai patch dari sandbox. |
| GitHub Actions | Eksekusi otomatis CI | Bukti event/SHA/job/log, bukan pengambil keputusan acceptance. |
| Pemegang CLI/shell aktif | Operator backup, introspeksi DB/modul, install terarah dan provisioning | Eksekusi hanya scope yang sudah disetujui; kembalikan target, command yang aman, hasil, SHA/image dan gap. |

Akun GitHub bersama bukan identitas agent. Signature commit/log adalah atribusi kerja, bukan bukti kriptografis. Baca `agent-log/anti-gravity.log`, `agent-log/agent-codex-pwa.log`, `agent-log/claude-design.log`, `agent-log/claude-dev.log`, dan `agent-log/codex.log` sesuai domain; log historis supervisor lain mungkin juga ada.

## 3. Domain dan kontrak bisnis

| Domain | Yang sudah dimiliki | Acceptance yang harus dijaga |
|---|---|---|
| Odoo19 CE + OCA19 | Addon `id_base`, `id_ui`, `id_ui_shell`, `id_ui_form`, `id_mobile_api` pada main snapshot | Instal bersih, schema/modul runtime aktual, model/view sesuai versi; install baru tidak membuktikan upgrade DB lama. |
| Seed / perpetual accounting | CSV kanonikal, loader, guards COGS, slice dan full-runner yang sedang direview | Oracle independen, identitas persisten, lokasi/UoM/lot, jurnal native, rollback dan replay. |
| UI native | Title/form work; footer PR36 masih terbuka | Keyboard/fokus, fail-closed controls, libsass, sticky/overflow, SO+invoice desktop/mobile dengan baris transaksi. |
| PWA simulator | Order/correction, delivery, daily sync, offline drafts dan session rules | Simulator tidak sama dengan backend transaksi resmi. Live bisnis tetap terkunci pada scope terakhir. |
| Mobile read/API | Bootstrap/snapshot Odoo auth+ACL, scope user/company/warehouse/hari, rasio SKU | Sesi generasi terbaru, native CSRF/record rules, authorized subset dan fail-closed empty/mismatch. |
| GPS/foto | Evidence mandiri, private source+watermark, hash/scope/freshness dan strict geofence | Bukan check-in/POD backend. Periksa owner/company/assignment/day/purpose sebelum binding bisnis kelak. |
| Maps | Demo dan preview staging dengan office server optional | Label TEST/unverified/verified, GPS real tanpa fallback pada staging, tile opt-in/attribution/error, callback lama dibatalkan. Preview bukan bukti kehadiran. |
| Operasional demo | Production environment diperbolehkan untuk demo, gateway/PWA telah diaktifkan | Data existing tetap utuh; addon/API/akun/backup/acceptance belum otomatis selesai. |

### Aturan bisnis yang sudah diputuskan

- Business timezone: **Asia/Makassar / WITA / UTC+8**. Timestamp koordinasi/commit: **Asia/Jakarta / WIB / UTC+7**. Jangan menukar keduanya.
- Freeze **15 CSV `data/registers/` sejak checkpoint `fae5835`**, bukan sejak root branch. Periksa diff byte dan fingerprints; jangan regenerate untuk meloloskan tes.
- SO single-prinsipal. Koreksi dan keputusan approval baru wajib pada **hari root SO di WITA**; draft lewat hari read-only, history/pending dipertahankan, tanpa auto-decision. Salesman wajib follow-up manual ke manager. Replay historis sah tetap diperbolehkan.
- Pending Requested: 0–2 hari SPV; **mulai tepat3hari SPV lalu Branch Manager**. Cancel delivery memakai lima subreason kontrak dan approval SPV; baca rules repo untuk enum tepatnya.
- Closing trip harus memakai POD yang source lengkapnya cocok hari/trip/manifest; lookup hanya DO ID pernah meloloskan POD kemarin. Office geofence memiliki toleransi25m pada aturan simulator terkait; jangan memindahkan kelonggaran demo ke server evidence strict.
- Rasio carton/pack/pcs **per SKU**, bukan144/12 global. Cakup rasio24/6 dan riwayat legacy.
- Footer: keputusan bisnis terbaru adalah **ringkasan diskon native (opsiB)**, bukan mengarang dua field diskon generik. Audit model/resolved view sebelum implementasi. Layout dan sticky tetap acceptance tersendiri.

### Guard accounting yang tidak boleh mundur

Seed SO/invoice memiliki batch persisten `fmcg_seed_batch` (`CANONICAL_JULY_2026_PERPETUAL`); identitas seed company diikat config/XMLID. Periksa native `stock.move.account_move_id` singular, posted/STJ/company/product/date/value, anti-AML reuse, UoM normalization dan dispatched-return=billed. Retur terikat melalui `origin_returned_move_id`, bukan substring note/origin. Jangan memakai `move_reverse_cancel` untuk menyembunyikan COGS invoice. Invoice non-seed, vendor bill/refund dan mixed recordset tetap native sesuai kontrak.

### Rekonsiliasi dataset yang benar

14 kunjungan outlet31Juli → **48 SO/DO/invoice single-prinsipal Agustus**, bukan14invoice. Carry-forward1038karton/56282unit, DPP187858691,40. Total1324SO;1276DO Juli +48DO Agustus;5PO receipts;9retur →1338pickings. Invoice1276Juli+48Agustus=1324;967AR+4AP=971payments;30OPEX. Angka lama1281DO adalah1276outgoing+5receipt pada checkpoint Juli, bukan totalDO seluruh periode.

Cut-off Juli31Juli23:59:59WITA =31Juli15:59:59UTC; awalAgustus1Agustus00:00WITA =31Juli16:00UTC. Jangan mengasumsikan SVL pada Odoo19; ikuti stock.move/account_move_id/AML aktual.

## 4. PR aktif — snapshot, bukan izin merge

| PR | HEAD pada pemeriksaan | CI/status | Langkah reviewer berikutnya |
|---|---|---|---|
| [36](https://github.com/kolondam-dev/odooca-fmcg/pull/36) | `2c694f8ba84b6709035ee8994c785cf592c8a5f5` | Draft, behind; install-test FAILURE, job lain terlihat hijau | Baca log failure terbaru. Jangan menganggap bug parser lama masih root cause tanpa meneliti HEAD ini. Audit footer/runtime tetap belum diterima. |
| [39](https://github.com/kolondam-dev/odooca-fmcg/pull/39) | `d816da8841c410daf0a07a860f0ef2e7f828792b` | Draft, behind; fullruntime +9jobPR hijau; **HOLD** | Selesaikan dua finding pada review Putaran5, sync main, ulang bukti. |
| [46](https://github.com/kolondam-dev/odooca-fmcg/pull/46) | `c863dc66f77e69019fed6d43e75bfe7ffb4f98d3` | Open non-draft, clean;9jobPR hijau | Generator gateway dan catatan deployment ditulis supervisor ini; perlu review independen. Belum merged pada snapshot. |
| [47](https://github.com/kolondam-dev/odooca-fmcg/pull/47) | `fd113dda0daf0a00012b0582770e17f401be0657` | Draft; static/pwa-quality hijau, job lain masih berjalan | Implementasi provisioning DB existing oleh codex-pwa baru tersedia. Belum direview supervisor; jangan menyatakan aman/lulus runtime server dari laporan saja. |

### PR39: verdict terakhir yang harus dipertahankan sampai ada fix

Sumber: [review Putaran5](https://github.com/kolondam-dev/odooca-fmcg/pull/39#issuecomment-6515188630). Fullruntime [40986984211](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/40986984211), job123840192739; CI40986984335, Seed40986984151, PWA40986984272. Seluruhnya d816da8.

Yang diterima: stok multiset, delapan probe PostgreSQL savepoint, baseline setelah rollback, candidate AML matching multi-move, cross-binding probe yang ditolak, carry-forward dan Run2 zero-drift. Bukti PostgreSQL berasal dari CI; reviewer tidak mengklaim mengulang fullruntime lokal. Enam tes lokal terpilih dan validator invariant/acceptance lulus.

Finding **P1**: kedua audit Juli/Agustus memilih done outbound berdasarkan destination customer tanpa memeriksa source internal/gudang kanonikal. Reproduksi fungsi produksi dengan fixture terisolasi: baseline internal→customer/postedSTJ/product/date/debit20credit20 PASS; ubah hanya source menjadi supplier → audit tetap PASS. Ini bukan klaim eksekusi PostgreSQL. Acceptance: reject source invalid (jangan sekadar skip), uji kedua fase, tambah post-posting PostgreSQL savepoint mutation, rollback dan baseline kembali lulus.

Finding **P2**: `resolve_canonical_company` mengembalikan `env.company` asing ketika canonical lookup kosong; resolver warehouse menerima loneAUX melalui “not other” bilaWH tidak ditemukan. Reproduksi lokal mengembalikan company999 dan stock location99. Acceptance: identitas persisten eksplisit, fail-closed missing/ambiguous/conflicting binding, tanpa ambient/name heuristic. Fixture harus menyiapkan binding, bukan mengandalkan fallback produksi. Tambah ORM disposable negative tests.

Main sudah maju ke7d667915; status behind perlu diselesaikan sesudah fix. BodyPR masih memuat baseline4addon/5tes lama; sinkronkan dengan hasil aktual. Upgrade baseline persisten (prioritas3) tetap PR terpisah dan belum dibuktikan.

### PR36: pelajaran lama, bukan diagnosis otomatis HEAD terbaru

Pernah ditemukan SCSS min(100%,32rem) tidak kompatibel libsass; fixture fokus detached; hidden input dipilih mendahului text input; assertion sticky salah; parse error JS page.evaluate; invoice scroll/overflow serta zoom yang tidak benar-benar mengubah metrik. Perbaikan beberapa poin sudah masuk. Gunakan histori untuk membangun regresi, lalu buktikan keadaan HEAD aktual.

### PR47: klaim implementer yang perlu diuji

Laporan/PR mengklaim jalur demo existing terpisah dari disposable guard: exact project/environment/service+DB, explicit opt-in, dua backup recent/hash-bound, ownership fixture, bounded locks20tabel, old-row fingerprints, zero new business records, rollback drift, cloneDB+backup+dua-run smoke. Hash bukan bukti restore/consistency/offsite; preservasi20tabel bukan seluruh M2M/sequence/filestore. Periksa source/test/log nyata. Instal addon juga memerlukan baseline/backup/preservasi tersendiri. Tidak ada otorisasi dari dokumen ini untuk menjalankan kandidat yang belum direview ke server.

## 5. Riwayat integrasi penting

| PR | Hubungan/hasil historis |
|---|---|
| 15 | Fix seed ke branch supervisi; **bukan langsung main**. Final audit diwarisi PR14/37. |
| 14 | HEAD3387ad8 merged ke `agen/transaksi-historis-perpetual` pada39c591671a84fc7e79b0f46bd1ebe63bca7245ae. |
| 37 | Integrasi perpetual/supervision ke main pada b957e02c4573c25be2de2c9853bb254049242431. Fullruntime/persistentupgrade saat itu belum dibuktikan. |
| 32/33/34/35 | Title, simulator sales/delivery/corrections dan UI baseline; sudah merged. PR34 memperbaiki POD lintas hari dan koreksi SO hari root WITA. |
| 38 | Catalog/snapshotv2, rasioSKU dan bootstrap generation guard; merge8d150838c12e7ef5269d889096eea6773706b131. |
| 40 | Native read API/ACL; merge d06fbc6f84db9552ce116aa451daf36c8f5b62c1. |
| 41 | Staging read UI/gateway trusted headers; mergeab2ccb5c9f2bb01c9654e28b5a60d6289c39516c. Fixture HTTPS tidak sama dengan acceptance staging nyata. |
| 42 | Standalone private GPS/photo evidence; mergefca1e0ff20ea9bcd3fd466d0d85bac46efe72cdf. Belum binding check-in/POD. |
| 43 | Demo maps check-in kantor/outlet; merge6cccbf291f2e3ec579308ba1dc1667a2fc89573e. |
| 44 | Office server/master/provisioning disposable/gateway kit; merge49739350127b9514af8fb3cd096ac2bc3b1adbc5. Bukan bukti environment/akun aktif. |
| 45 | Keputusan production sebagai demo terdokumentasi; merge7d667915e7b9d839084b974e03b91e5ec4ee025b. |

Verifikasi ulang ancestry dan merge targets bila digunakan untuk keputusan. Sumber utama tetap server GitHub/git, bukan tabel sejarah ini.

## 6. Environment dan runtime

| Lingkungan | Fungsi/batas |
|---|---|
| Workspace agent | Checkout/worktree lokal, unit/static/probe. Bisa sementara; tidak mewarisi credential agent lain. |
| GitHub Actions | Odoo19 bersih, Postgres16 disposable, browser, slice/fullruntime. DB `ci_db`, `fmcg_base` bootstrap CI, `fmcg_full_disposable`, `fmcg_staging_acceptance` bukan otomatis server demo. |
| Railway `production` | Demo existing yang diotorisasi pemilik; satu environment yang teramati. Tiga aplikasi+Postgres dipertahankan. |
| `staging-remote` | Rencana isolasi sebelumnya, tidak dibuat oleh supervisor. Tidak lagi prasyarat wajib scope demo setelah keputusan pemilik. |
| Browser/perangkat nyata | Acceptance login/camera/GPS/tile/cookie end-to-end; belum selesai. |

[F] Proyek Railway `pleasant-caring`: `569df00d-48e8-411a-93a5-df39ba97f16b`. Environment production: `47b72704-4054-4941-b978-d42c1befca55`. Region teramati `iad`.

| Service | ID | Fungsi/runtime pada snapshot |
|---|---|---|
| odooca-fmcg | 56186eb1-eec2-4604-92d3-f449504cba4a | Odoo, source main; latestSUCCESS bce4e482-a418-4e1e-b3d5-c043cf6ac919. Volume7708e3c6-396f-4696-9cfd-a9e41adbbd3b di /var/lib/odoo. |
| field-pwa | 1d4d5b2f-2171-446b-a549-91d9ec653553 | PWA pinned4973935, mode staging; deploy84abcb97-814d-4073-8a23-be2ca0890e11 SUCCESS. |
| demo-gateway | df1e5bd0-3103-47aa-b56f-bf5d3706bd3d | Nginx1.28-alpine; deploy8f42f93b-0a29-45eb-886a-d05f70380716 SUCCESS. Source image, bukan repo. |
| Postgres | 9081e8c1-66a8-460e-941a-ea2224ce4974 | Image ghcr.io/railwayapp-templates/postgres-ssl:18; volume39adaec2-0122-4eec-b195-3d2c3242c762 di /var/lib/postgresql/data. Jangan menyamakan versiDB server dengan Postgres16 CI. |

Volume teramati masing-masing500MB. Angka ini inventory, bukan ukuran data aktual atau estimasi biaya.

Domain teramati: `odooca-fmcg-demo.up.railway.app`, `field-pwa-production.up.railway.app`, `demo-gateway-production-abd1.up.railway.app`. Gateway merutekan /field ke PWA dan login/API ke Odoo agar cookie satu origin. Domain lama belum dicabut; tidak ada klaim gateway satu-satunya exposure.

Probe HTTPS terakhir oleh supervisor: /healthz200; /field/build-info.json200 mode staging; /web/login200; /api/v1/me/bootstrap404; /api/v1/sync/commands404. Endpoint bootstrap404 berarti API belum siap; bukan alasan menyatakan akun salah. Refresh sesudah upgrade/provisioning.

Log Odoo menyebut DB **railway**. [BU] Identitas/isi/schema/modul DB target belum diaudit penuh lewat shell; **jangan mengasumsikan fmcg_base** dari runbook CI. Addon code dalam image tidak otomatis terinstal di registry existing DB.

Gateway awal ter-build sebagai static PWA akibat default pwa/railway.toml. Pemilihan config file khusus ditolak plugin (Config as Code deprecated). Jalur runtime yang berhasil: image resmi Nginx + Start Command merekonstruksi tiga file audited4973935 dari base64; generator reproducible diPR46. Base64 menjaga byte/kutip, bukan enkripsi. Baca catatan PR46; jangan menempel raw credential ke command.

## 7. Otorisasi dan capability boundaries

Keputusan terbaru yang mengalahkan larangan historis untuk scope ini:

- Pemilik mengizinkan penggunaan **production existing sebagai demo**, konfigurasi/deploy/restart yang diperlukan, **tanpa reset/penghapusan/restore menimpa data existing**. Company/akun/assignment TEST terpisah. Tiga aplikasi+Postgres dipertahankan.
- Publikasi HANDOFF/log/dokumen demo sudah disetujui berulang; jangan meminta izin sama lagi. Ini tidak mengizinkan credential/dump/filestore/telemetri pribadi.
- Koordinat kantor sementara boleh TEST berlabel. Verified memerlukan sumber/radius yang dikonfirmasi. Permintaan owner untuk pengujian remote tidak otomatis berarti server bypass sudah diimplementasikan/diterima.
- Guard disposable lama tetap berlaku. Adaptasi existing demo harus jalur eksplisit yang direview, tidak rename database atau memaksa guard untuk lolos.
- Izin merge terdahulu berlaku pada PR yang disebut, bukan blanket merge semua PR berikutnya. Request review bukan izin merge. Deploy juga bukan izin menurunkan ruleset atau membuka DB publik.

Capability saat sesi supervisor:

| Jalur | Yang terbukti tersedia | Batas penting |
|---|---|---|
| GitHub plugin | Metadata/source/log/comment, branch/commit/PR/merge sesuai izin | Tetap exactHEAD dan ruleset; akun bersama tidak membuktikan pelaku agent. |
| Railway plugin OAuth | Inventory, config, services, variables writes, source/domain/deployment/logs | Values variable disembunyikan; tidak ada container shell/backup/ORM. Pembuatan environment tidak tersedia pada tool yang terpasang saat itu. |
| Railway CLI lokal supervisor | Instal dicoba | Gagal unduh binary/jaringan; tidak ada credential CLI terbukti. Jangan mewarisi otorisasi plugin sebagai token CLI. |
| Cloud browser | Fallback pernah diizinkan | Login Railway/GitHub/Google tidak selesai. Jangan menyimpan/menyalin session; jangan mengulang login untuk memecahkan kebutuhan shell. Penolakan otomatis harus dilaporkan dan tidak dibypass. |

Tidak harus Antigravity: codex-pwa atau operator lain boleh mengeksekusi bila benar-benar punya CLI/shell berotorisasi. Aksi terblock harus diberi prosedur, target dan acceptance; bukan permintaan izin ulang yang sudah ada.

## 8. Metode review

1. Kunci fullSHA/base/scope. Review delta sejak komentar terakhir sekaligus invariant global yang disentuh.
2. Verifikasi workflow event/SHA/run/job; baca log dan artifact. Bedakan duplikat push vs9jobPR unik. Synthetic merge boleh digunakan jika kesetaraan tree terbukti.
3. Bangun matriks klaim→invariant→source→tes→hasil→batas. Laporan implementer adalah input untuk diverifikasi.
4. Jalankan counterexample terkecil pada entrypoint produksi; baseline PASS→satu mutasi→expected reject. Nyatakan lokal/mock/AST vsPostgreSQL secara jujur.
5. Untuk database: oracle independen, multiset stock/lot/reserved, source/company, native HPP/AMLanti-reuse, cut-off, rollback loader boundary dan full replay. Total seimbang/zero-drift saja tidak cukup.
6. Untuk PWA: generation/race, WITA midnight/CAS, media source lengkap, perSKU UoM, ACL/CSRF/duaakun, private evidence. Demo/simulator bukan official write backend.
7. Untuk UI: native compiler/model/resolved view, attached focus fixture, actual scrollport/containingblock, sticky interval, last-row visibility, zoom metrics dan overflow diagnostics.
8. Tutup finding lama secara eksplisit. Bug dalam scope terkonfirmasi→HOLD; bukti penting taktersedia→HOLD/BLOCKED dengan alasan, bukan tuduhan. PASS scope terbatas boleh dengan gap di luar scope yang jelas.
9. Posting verdict konkret dan acceptance pada PR bila alur review telah diotorisasi. Jangan melonggarkan assertion demi hijau atau menambah temuan tanpa bukti.

Saat membantu implementasi sendiri (contohPR46), jangan menyebut review sendiri independen. Mintakan reviewer lain untuk area material.

## 9. Merge/deploy/komunikasi

[F] Ruleset `main-quality-gate` ID25827644 aktif, strict up-to-date=true; GitHubActions integration15368 required: static, install-test, init-test, pwa-gate, invariant-tests, seed-invariants. Deletion/nonfastforward protection dan thread resolution dipertahankan. Fullruntime PR39 merupakan acceptance domain tambahan walau bukan salah satu enam context tersebut.

Sebelum merge berizin: refresh expectedHEAD/base/draft/checks/behind/conflicts/threads. Jika HEAD berubah, audit delta; jangan bypass. Gunakan expected_head_sha, verifikasi merged/base/mergeSHA dari server. Resolusi log/HANDOFF mempertahankan kedua riwayat; jangan hapus tulisan agent lain.

Sebelum perubahan DB existing: target aktual, backup DB+filestore dan jalur pemulihan, baseline non-fixture, review code dan tes. Jangan menyalakan FORCE_UPGRADE umum/seed/reset untuk sekadar menghilangkan404. Provisioning dan addon install punya risiko/pembuktian yang berbeda.

Komunikasi: beri update singkat saat bekerja; final mandiri berbahasa Indonesia memuat verdict/SHA/bukti/link/tindakan. Hindari “sudah selesai” jika baru build hijau. Jika automatic review menolak, sebut aksi dan alasan penolakannya secara ringkas. Tidak ada pesan keluar ke orang lain tanpa izin eksplisit.

## 10. Sumber dan prompt agent pengganti

Sumber hidup yang wajib dibaca:

- AGENTS.md; docs/AGENT_PROTOCOL.md; docs/DEVELOPMENT.md; docs/HANDOFF.md.
- docs/reviews/SEED_INVARIANT_CONTRACT.md; docs/reviews/FULL_DATASET_RUNNER_AND_CUTOFF_PLAN.md padaPR39.
- docs/DEMO_ENVIRONMENT_SCOPE_DECISION.md pada mainPR45; docs/DEMO_DEPLOYMENT_20261030.md padaPR46 sampai merged.
- docs/STAGING_ACCEPTANCE_KIT.md; docs/STAGING_DEVICE_ACCEPTANCE.md; docs/REMOTE_ACCEPTANCE_DECISIONS.md; aturan/kontrak PWA dan docs/ui/id_ui_form.md pada ref terkait.
- Komentar review terakhir dan CI exactSHA; jangan mengandalkan link share ChatGPT yang belum dibaca atau ringkasan historis saja.

Prompt yang dapat dipakai pemilik:

> Anda menggantikan supervisor/reviewer pada kolondam-dev/odooca-fmcg. Gunakan skill supervise-pr-evidence bila tersedia, lalu baca dokumen SUPERVISOR_HANDOFF.md ini pada branch/ref yang saya berikan serta AGENTS/HANDOFF/kontrak terbaru. Refresh main/PR36/39/46/47 dan runtime hanya jika tugas membutuhkan. Laporkan apa yang berubah sejak snapshot, ambil alih antrean review, dan berikan verdict berbukti dengan reproduksi serta acceptance konkret. Jangan merge tanpa izin PR yang tepat atau men-deploy/memutasi data di luar scope pemilik. Production boleh untuk demo dengan data existing tetap utuh; tidak perlu meminta ulang persetujuan itu. Nyatakan capability blocker sebenarnya dan tentukan pelaksana berdasarkan akses, bukan nama agent. Bedakan CI, fullruntime disposable, upgrade/provisioning server dan acceptance perangkat. Jangan mengklaim review independen atas perubahan yang Anda tulis sendiri.
