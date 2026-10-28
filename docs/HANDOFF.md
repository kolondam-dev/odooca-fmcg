# HANDOFF

## 2026-10-28 — agent-codex-pwa — Follow-up HOLD PR33 c48bf5a
**Review:** https://github.com/kolondam-dev/odooca-fmcg/pull/33#issuecomment-6472436334; basis c48bf5a pada branch agen/pwa-sales-delivery-rules. CI lama 40705244566 sudah FAILURE (7 failed, 5 flaky, 52 passed), bukan pending; CI Odoo lama 40705244625 SUCCESS. Log browser resmi dibaca: kegagalan menunggu readiness/klik absensi ada di ensureDaily, termasuk pemulihan setelah persona berganti.
**P1 offline:** DeliveryWorkspace memvalidasi manifest daily sync (owner/hari/keunikan) sebelum materialisasi cache secara lokal tanpa pemeriksaan online/provider. Cache yang sudah ada tetap diparse/dibandingkan; cache berbeda/rusak tidak ditimpa. Regresi phone/tablet membuktikan daily sync online → offline sebelum first-open list → mulai sesi/simpan draft; juga reload offline sebelum first-open. Kontrol negatif tanpa daily sync, owner/hari manifest berbeda dan cache berbeda mempertahankan data sumber.
**P1 gate:** ensureDaily membedakan ready/attendance-only; setelah klik absensi wajib menunggu tombol sync enabled (completion IndexedDB), lalu klik dan tunggu ready. switchPersona menunggu data-owner tujuan serta restore aria-busy=false; seluruh pergantian persona tes memakai helper ini. Gate completion write absensi dan success restore sengaja ditahan/dilepas lewat handshake test, tanpa sleep/kenaikan timeout/pengurangan worker/skip.
**P2 audit:** riwayat POD menampilkan nama, received dan unit dari source command historis per SKU; tidak ada literal karton pada gabungan angka. Regresi root rejected → correction → riwayat multi-SKU pcs serta fixture legacy karton lulus.
**Diverifikasi lokal:** 239 unit +1 hosting PASS; 84 browser phone/tablet PASS, seluruh 64 lama +20 regresi, satu run final tanpa retry dan worker default. Browser resmi Chrome for Testing Headless Shell145.0.7632.6 (versi Playwright1.58.2), bukan Chromium153 pengganti. Full Chrome resmi gagal launch karena socket singleton dibatasi lingkungan; verifikasi resmi memakai headless shell yang sesuai runner. Format/typecheck/contracts/demo+live/budget (demo67,1 KiB gzip/font47,1 KiB), Ruff/4 manifest dan diff check PASS.
**Batas/menunggu:** CI remote pada SHA perbaikan diperiksa setelah publikasi dan URL/hasil dicatat pada PR. Docker/Odoo lokal tidak diulang; tidak ada perubahan backend/addon/seed/hosting/workflow/ruleset/Railway. Tetap simulator/live terkunci, HOLD menunggu review ulang; tidak merge/deploy.


## 2026-10-28 — agent-codex-pwa — Implementasi rules Sales Order dan Delivery
**Basis:** main 2feadf3; branch agen/pwa-sales-delivery-rules, sesuai mandat pemilik. Aturan §17 ditulis sebelum implementasi; protocol/development/handoff dan log codex dibaca.
**Berubah:** list Sales/Delivery wajib daily sync; driver memakai sesi pagi dan manifest tersimpan bersama snapshot. SO demo mendukung karton144/pack12/pcs1, qty/SKU, estimasi harga dan diskon order dengan alasan. Pengajuan diskon Normal menunggu approval; kontrol simulator di Lainnya membuat keputusan approved/rejected beralasan dengan CAS satu kali dan command immutable. Delivery manifest v2 multi-SKU pcs, lima status sesuai label pemilik, alasan non-partial disalin ke semua baris dan partial wajib per item terdampak. Foto toko → set pinpoint → mulai sesi → penerimaan → foto closing berbeda → enqueue+closed atomik → summary/list updated → DO berikutnya; satu sesi delivery aktif per owner/DB, restore offline dan validasi media opening/closing/ancestor. Sesi Sales existing diperluas urutan foto/pinpoint dan status closed pada list.
**Diverifikasi:** 239 unit +1 hosting PASS; 64 browser phone/tablet PASS dalam satu run final penuh (Chromium lokal153; CI tetap browser resmi Playwright). Termasuk draft partial offline, alasan wajib, iterasi DO kedua, approval accepted/rejected, legacy, corrupt media, race dua koneksi sesi/keputusan dan historical replay. Typecheck/format/contracts/demo+live/build budget, Ruff/4 manifest, git diff --check PASS; screenshot ponsel SO/POD ditinjau. Docker/Odoo runtime lokal tidak dijalankan karena addon/hosting tidak berubah. CI setelah publikasi PR.
**Batas:** diskon demo persen integer pada total order, approve seluruh nilai diminta atau reject; limit/tier/per-line/promo belum ditetapkan. Cancel/pending hanya hasil simulator, bukan pembatalan picking/approval server. Same-day aksi/koreksi; sesi tertinggal lintas hari/rusak ditahan untuk review, belum recovery. Pinpoint tetap grid simulasi tanpa basemap; timestamp aksi set pin berbeda dari sampel GPS. Snapshot/receipt/hash client bukan authority backend. OpenAPI0.11 additive; riwayat lama dipertahankan, tanpa migrasi/destructive rewrite. Backend/addon/seed/loader/workflow/ruleset/Railway tidak disentuh; live terkunci.
**Menunggu:** review PR dan CI remote; tidak merge/deploy.


## 2026-10-28 — agent-codex-pwa — Rules SO, penerimaan dan sesi lapangan
**Berubah:** SCOPE §14 merujuk blueprint mobile §17: lima status delivery, alasan per baris dengan input massal non-partial, tier SKU demo 144 pcs/karton dan 12 pcs/pack, simulasi approval diskon, daily sync sebelum list dan siklus sesi foto opening/pinpoint–intra–foto closing–update list pada Sales/Delivery.
**Diverifikasi:** dokumentasi dan konsistensi requirement diperiksa; git diff --check.
**Belum diuji:** tidak ada perubahan runtime; seluruh requirement baru masih pekerjaan implementasi.
**Butir terbuka:** authority/transisi cancel-pending dan parameter approval diskon; backend tetap dependency, live terkunci.
**Menunggu:** implementasi sesuai urutan §17.5; tidak deploy.



## 2026-10-28 — codex agent — Koreksi collection ditolak simulator
**Basis:** main f99e117 (PR #30 merged), branch agen/mobile-collection-corrections; whats_new/protocol/development/handoff dibaca dan plan sebelum kode.
**Berubah:** hanya receipt bisnis rejected cocok UUID membuka koreksi. UUID/alasan/foto baru, source identik, parent immutable. CAS pointer schema-canonical+snapshot receipt atomik, satu successor; nominal bukan saldo tambahan. Referensi/tanda terima dapat dipertahankan dalam lineage; semua klaim ancestor tetap reserved lintas tagihan, foto wajib berbeda. Restore/pre-sync memvalidasi root/parent/time/source/dedup/media semua ancestor dan recheck setelah await. Draft manual per parent pulih offline, hasil/bukti readonly, parent di Lainnya. Kontrak0.10 pasangan optional fields (legacy valid) dan fixture live gate additive; workflow tidak berubah.
**Diverifikasi lokal:** 227 unit +1 hosting +58 browser PASS; race dua koneksi, receipt berubah saat commit/hash, multilevel/root media rusak, persisted cycle/missing parent/dropped ref, transport/approval/accepted lock, reserve ancestor serta draft koreksi offline+UUID/parent utuh. Typecheck/format/contracts/demo+live/budget (demo62,9 KiB gzip/font47,1 KiB), Ruff/4 manifest PASS. Screenshot ponsel ditinjau. CI setelah push.
**Batas:** same-day correction/historical replay, local source/hash bukan auth/server authority. Cancel/cicilan lanjutan/closing/kasir/bank/payment/AR/GL belum terintegrasi. Backend/addon/seed/loader/workflow/ruleset/Railway tidak disentuh; runtime Odoo lokal tidak dijalankan karena addon tidak berubah. Tidak merge/deploy, live terkunci.
**Menunggu:** CI dan review pemilik.

## 2026-10-27 — codex agent — Penerimaan uang delivery/collection simulator
**Basis:** main08b0050, PR #28/#29 sudah merged; branch agen/mobile-collection. Protocol/development/handoff dan whats_new dibaca, plan terintegrasi sebelum kode.
**Berubah:** capability fixture collection.capture terpisah, tagihan contoh bertimestamp mengikat DO/trip/outlet/owner/hari/versi/saldo. Cash/transfer, pembayar/nominal/nomor tanda terima/ref transfer/catatan, foto watermark+pinpoint/geofence wajib. Rupiah integer string+BigInt, >0 <=saldo. Draft manual pulih offline, hasil/bukti readonly. Receipt normal needs_approval, saldo tidak dikurangi dan bukan AR lunas/payment posted. Source+ledger+queue CAS atomik; dedup tagihan/nomor bukti/ref transfer/foto lintas tab/koneksi. Snapshot read-only source+ledger+outbox konsisten, restore/pre-sync recheck setelah hash. Source berbeda/queue/media rusak tertahan tanpa hapus/force. Kontrak0.9 conditional ref transfer dan gate fixture live additive; workflow tidak diubah.
**Diverifikasi lokal:** 208 unit +1 hosting +56 browser PASS; race dua koneksi tagihan/ref transfer, source berubah saat media read, corrupt source/ledger/queue/foto, nominal/geo/owner/day/capability, next-day replay, transfer wajib ref/overamount/dedup dan draft offline/readonly. Typecheck/format/contracts/demo+live/budget (demo62,4 KiB gzip/font47,1 KiB), Ruff/4 manifest PASS. Screenshot ponsel ditinjau; 6 browser collection diulang setelah guard snapshot berbeda diperketat. CI sesudah publish.
**Batas:** satu pencatatan per tagihan (boleh sebagian); reserve tetap pada rejected/transport, cicilan lanjutan/koreksi/cancel belum tersedia. Capture pada hari penugasan, replay historis sah boleh besok. Capability/source/local hash bukan security authority, dedup hanya satu owner/DB; peta tetap simulasi. Bank verification/multi-invoice/closing/settlement kasir/account.payment/GL belum terintegrasi. Tidak menyentuh addon/backend/seed/loader/workflow/ruleset/Railway; runtime Odoo lokal tidak dijalankan karena addon tidak berubah. Live terkunci, tidak merge/deploy.
**Berikutnya:** koreksi collection berbasis receipt penolakan dan lineage, lalu closing/settlement dengan authority backend.
**Menunggu:** CI dan review pemilik pada PR baru.

## 2026-10-27 — codex agent — Koreksi POD ditolak simulator
**Basis:** 4459bcb PR #28 direview layak merge tetapi belum merged; branch agen/mobile-pod-corrections, PR bertumpuk base agen/mobile-delivery-pod. Review issuecomment-6444798338 dibaca; seed agent terbaru 812ae66 tidak disentuh.
**Berubah:** UUID baru/supersedes_uuid/alasan, source manifest identik, foto baru. Hanya receipt bisnis rejected cocok UUID membuka koreksi; transport/queued/needs_approval/accepted tetap terkunci. CAS pointer+snapshot receipt parent dalam transaksi sama, satu successor; parent/receipt/media immutable. Graph root/lineage/time/owner/DO/source/photo diperiksa pada commit/restore/pre-sync, termasuk media ancestor dan perubahan setelah await. JSON canonical schema untuk CAS pointer POD lama (urutan properti tidak bermakna); guard domain lain tetap. Draft koreksi terpisah per parent, pulih offline, histori readonly dan receipt normal needs_approval. Kontrak0.8 mencerminkan pasangan field.
**Diverifikasi lokal:** 175 unit +1 hosting +50 browser PASS; race dua koneksi, receipt snapshot berubah saat commit/await media, multi-level correction dan root rusak, persisted cycle/missing parent/source/dropped ref, offline draft+UUID baru+parent utuh. Typecheck/format/contracts/demo+live/budget (demo60,0 KiB gzip/font47,1 KiB), Ruff/4 manifest PASS. Screenshot ponsel ditinjau; 6 browser POD diulang sesudah perubahan presentasi. CI setelah push.
**Batas:** koreksi baru hanya hari manifest, replay antrean sah boleh besok. Tidak mengedit accepted/approval atau recovery data rusak. Maps tetap simulasi, bukan authority auth/session/device/media/approval/backend. Collection/closing/retur/lot/posting Odoo belum diintegrasikan; runtime Odoo lokal tidak dijalankan karena tidak ada addon/backend berubah. Backend/seed/loader/workflow/ruleset/Railway tidak disentuh, live terkunci, tidak merge/deploy.
**Menunggu:** CI dan review pemilik; PR #28 harus merged sebelum PR lanjutan di-retarget ke main/merge.

## 2026-10-27 — codex agent — Koreksi fixture typecheck PR #28
**Temuan:** CI 4910b03 gagal typecheck karena fixture receipt status melebar menjadi string. Klaim typecheck lokal PASS pada entri POD sebelumnya keliru; exit typecheck terlewat dalam command sequence.
**Perbaikan:** literal status needs_approval dibuat const pada fixture tes; tidak mengubah runtime/gate/workflow. Typecheck/format/unit/contracts diperiksa ulang secara eksplisit; CI commit baru diperiksa setelah push.
**Batas:** seluruh batas simulasi/live lock tetap berlaku, belum merge/deploy.

## 2026-10-27 — codex agent — POD terikat DO/trip simulator
**Basis:** main 6aa9cc3 (PR #27 merged); branch agen/mobile-delivery-pod. Plan diperbarui sebelum kode.
**Berubah:** manifest cache per owner/hari, DTO command baru delivery.pod.submit, penerima/hasil/kuantitas per item/alasan dan foto wajib dengan geofence 5–15m/TTL60s. Draft offline disimpan eksplisit, antrean+ledger CAS atomik; dedup DO/foto lintas tab. Restore dan pre-sync memvalidasi source/envelope/event time/media/hash, termasuk recheck sumber setelah await media. Replay next-day sah; kerusakan ditahan dan data dipertahankan. Bukti/data hasil read-only, receipt normal needs_approval, bukan picking done. OpenAPI draft0.7 dan fixture live gate additive, tidak mengubah workflow.
**Diverifikasi lokal:** 154 unit +1 hosting +48 browser ponsel/tablet PASS; dua koneksi DB, source berubah saat await, media/manifest/ledger rusak, draft offline dan readonly. Screenshot ponsel ditinjau; format/typecheck/contracts/demo+live/budget (demo JS58,9 KiB gzip; font47,1 KiB), Ruff/4 manifest PASS. CI setelah push.
**Batas:** fixture satu item/DO, bukan stock/lot, retur, collection, closing atau approval backend. Draft manual; koreksi POD/reassignment/revocation/recovery belum tersedia. Maps tetap pinpoint simulasi; auth/session/device/media/security dan dedup server dependency. Backend/addon/seed/loader/workflow/ruleset/Railway tidak disentuh; tidak merge/deploy, live terkunci.
**Berikutnya:** koreksi POD berbasis receipt penolakan dan lineage immutable, kemudian collection/closing sesuai authority backend terpisah.
**Menunggu:** CI dan review pemilik.

## 2026-10-27 — codex agent — Foto wajib pada aksi kunjungan sales
**Basis:** main d1cd6e8 (PR #26 merged); branch agen/mobile-visit-evidence. Plan terintegrasi sebelum implementasi.
**Berubah:** check-in/check-out baru wajib paket foto v1 berbeda per aksi; owner/ref/hash/foto/map cocok, geofence sumber PJP tetap konservatif, capturedAt sesudah pembukaan sesi/check-in dan foto/GPS asli paket TTL60s pada waktu aksi. Ref disalin atomik ke ledger+command dengan CAS dan keunikan ID foto per aksi ledger owner; draft berubah tidak mengubah transaksi tersimpan. DTO version/ref berpasangan; legacy photo-less hanya replay, commit baru tanpa foto ditolak di service dan validator atomik.
**Offline/UI:** slot tuple owner/session/outlet/phase/visit menyimpan draft foto dan pulih offline; siap hanya setelah durable. Scope/generation guard mencegah callback lama mengisi scope baru. Tombol aksi menahan foto stale, bukti historis read-only. Kontrol bukti disembunyikan selama aksi sibuk. Kontrak OpenAPI draft0.6 mencerminkan dependentRequired untuk pasangan version/ref (DTO dan branch Command); schema command tetap1 dan schema IndexedDB tetap1.
**Restore/sync:** validasi semantik+media termasuk parent accepted yang medianya rusak; hash sebelum provider diikuti recheck graf. Photo proof historis dinilai terhadap occurred_at, bukan hari sync. Parent media rusak bisa Perlu review sementara child Menunggu dependency; tidak ada receipt palsu/deletion/forced replay. Jalur legacy diuji terpisah tanpa mengubah UUID yang sudah diterima simulator.
**Diverifikasi lokal:** 134 unit + 1 hosting + 44 browser phone/tablet PASS; wajib photo/commit guard, ref reuse, owner/site/time/session/hash/missing source, media parent accepted, source berubah selama await, replay next-day/legacy, draft reload offline, read-only history, corrupt media restore dan hold setelah reconnect. Fixture helper test memberi paket foto eksplisit pada regresi geo/sesi lama, bukan bypass service. Screenshot foto kunjungan ponsel ditinjau. Format/typecheck/contracts/demo+live/budget (demo JS56,5KiB gzip/font47,1KiB), Ruff/4 manifest PASS; CI setelah push.
**Batas:** foto berasal dari paket generik PR #26; assignment visit/session/outlet/phase ada pada slot/ledger/command, bukan signature server di foto. Pinpoint tetap simulasi tanpa basemap; bukan anti-mock GPS/kamera asli/titip akun atau authority backend. Tidak ada retention/GC/recovery baru. Tidak menyentuh addon/backend/seed/loader/workflow/ruleset/Railway; tidak merge/deploy, live terkunci.
**Berikutnya:** delivery/POD dengan bukti terikat DO/trip; maps/media/session/device server tetap dependency terpisah.
**Menunggu:** CI dan review pemilik atas PR baru.

## 2026-10-27 — codex agent — Regresi kuota paket bukti PR #26
**Basis:** PR #26 HEAD 1e0edf3; branch tetap agen/mobile-evidence-packages.
**Tambahan:** injeksi QuotaExceededError pada IDBObjectStore.put membuktikan transaksi media rollback utuh: tidak ada record foto/map parsial. Tidak mengubah implementasi produksi.
**Diverifikasi:** seluruh 123 unit PASS (sebelumnya 122); format/typecheck dicek. Hasil 1 hosting + 40 browser/build/Ruff pada source produksi identik tetap berlaku; CI commit baru diperiksa setelah push.
**Menunggu:** CI/review PR; live tetap terkunci, tidak merge/deploy.

## 2026-10-27 — codex agent — Paket bukti watermark/hash/pinpoint simulasi
**Basis:** main d4cf21b (PR #25 merged); branch agen/mobile-evidence-packages. Rencana masuk plan sebelum implementasi.
**Berubah:** komponen evidence bersama menghasilkan JPEG watermark waktu pencatatan WITA/koordinat/akurasi + PNG pinpoint SIMULASI TANPA BASEMAP (grid/skala/utara/akurasi). Tidak ada tile/provider/network baru. Waktu pilih file dipisah dari waktu pencatatan; waktu shutter/kamera asli tidak dibuktikan. Output foto <=1 MB, map <=128 KB; input <=12 MB/40 MP, sisi foto <=1600 px. Fix TTL60s/future1s/accuracy>0<=10km, pilih foto <=5menit sebelum save.
**Integritas:** satu record atomik foto+map+metadata/hashes/binding owner-key-time-location; immutable via store API. Shared assertLocalEvidence untuk restore/submit realisasi; sebelum provider hash paket baru dicek, lalu graf visit dicek ulang. Paket hilang/berubah ditahan tanpa receipt bisnis baru. evidenceHold lokal menampilkan Perlu review berdasarkan pemeriksaan sync terakhir. Generation guard/object URL cleanup berlaku saat ganti file/ref/owner/unmount. getEvidence memberi pembacaan keyed untuk sync. Tidak ada auto-rekonstruksi/GC.
**Kontrak:** OpenAPI draft 0.5 dengan packageHash opsional pada evidence ref; schema command tetap v1, legacy tanpa hash tetap path metadata/Blob lama dan diberi label belum memiliki paket baru. Map_status/evidence_status tetap pending; absensi/POD resmi tetap terkunci, foto visit belum ditambahkan pada iterasi ini.
**Diverifikasi:** 122 unit + 1 hosting + 40 browser phone/tablet PASS; perubahan byte foto/map/metadata/hash/source, missing/downgrade package, immutable write, historical replay, legacy, corrupt persisted foto restore/submit, offline reload map+foto, screenshot watermark/pinpoint ponsel ditinjau. Format/typecheck/contracts/demo+live/budget (demo JS54,6 KiB gzip/font47,1 KiB), Ruff/4 manifest PASS. CI diperiksa setelah push.
**Batas:** grid pinpoint lokal bukan peta jalan/snapshot peta resmi; hash client tidak mencegah pemalsuan seluruh DB/rehash/mock GPS/kamera palsu/titip akun. Server media/signing/ACL/maps berlisensi/OCR/retention/GC/dedup lintas perangkat tetap dependency. Tidak menyentuh backend/addon/seed/loader/workflow/ruleset/Railway, tidak merge/deploy; live terkunci.
**Berikutnya:** integrasi paket bukti ke visit/delivery secara bertahap; adapter media/maps server dengan authority terpisah dari representasi client.
**Menunggu:** CI dan review pemilik pada PR baru.

## 2026-10-27 — codex agent — Pusat diagnosis sinkronisasi simulator
**Basis:** main 302587e (PR #24 merged); branch agen/mobile-sync-diagnostics. Plan terintegrasi sebelum implementasi, tetap area PWA.
**Berubah:** menu Lainnya kini menampilkan filter Semua/Menunggu/Perlu review/Approval/Diterima dan detail UUID, waktu WITA, percobaan, jadwal retry, referensi receipt, konteks sesi dan dependency. Bedakan offline/backoff/sending/auth, integritas visit, dependency, approval, penolakan bisnis vs transport. Receipt wajib cocok UUID/status. State accepted historis yang grafnya rusak tetap tersimpan tetapi ditandai perlu review.
**Integritas/performa:** proyeksi read-only satu snapshot ledger/morning/outbox, field terbatas tanpa payload mentah/foto/token atau ekspor. Refactor createVisitSyncValidator membagi validator; graf sekali per proyeksi snapshot, sedangkan validateVisitSync di engine selalu instance baru per boundary. Tidak mengubah retry, state, receipt, UUID, source atau API wire. UI aman pada DTO invalid, async hasil lama dibuang saat unmount/owner berganti. Tidak ada polling/request baru.
**Diverifikasi lokal:** 111 unit + 1 hosting + 38 browser phone/tablet PASS; diagnosis parent accepted tapi rusak, receipt mismatch, DTO/time/state/retry invalid, offline/backoff/auth/approval/rejected, legacy/next-day, isolasi owner, no raw payload, snapshot IndexedDB identik sesudah filter/detail/persona. Screenshot ponsel ditinjau, tanpa overflow; format/typecheck/contracts/demo+live/budget (demo JS 52,5 KiB gzip; font 47,1 KiB), Ruff/4 manifest PASS. CI diperiksa setelah push.
**Batas:** status pada snapshot lokal terakhir, bukan backend authority; validasi finansial/media/approval/otorisasi resmi belum tersedia. Tidak ada edit/hapus/paksa kirim/approve/auto-recovery/login; tombol Sinkronkan existing tetap memakai engine lama. Backend/addon/seed/loader/workflow/ruleset/Railway tidak disentuh; live terkunci, belum merge/deploy.
**Berikutnya:** evidence foto timestamp/GPS + pinpoint map; delivery/POD/HRIS bertahap, server session/device/media/policy/idempotency tetap dependency terpisah.
**Menunggu:** CI dan review pemilik atas PR baru sebelum merge/deploy manual.

## 2026-10-27 — codex agent — Tutup blocker sync PR #24
**Basis:** PR #24 HEAD 1eea9f0; review issuecomment-6434268284 dibaca. Branch agen/mobile-sales-visits tetap.
**Koreksi klaim sebelumnya:** restore memang menolak graf rusak, tetapi outbox hanya mengecek dependency dan tetap submit; 3 regresi reproduksi check-in/order/check-out gagal pada outbox lama. Kini shared visitLedger memvalidasi semantik sebelum sync, termasuk source, envelope/owner/key, relasi/konteks/geo/time/produk. Snapshot read-only ledger+morning+outbox konsisten; pemeriksaan diulang sesudah sending tepat sebelum provider. Parent invalid menahan descendants walau receipt accepted lama ada. Invalid visit graph konservatif menahan visit owner; draft/command tetap utuh, pesan review, tanpa receipt bisnis baru.
**Historical replay:** check-in baru menyimpan morning_source penuh atomik. morningReady tanggal historis + event-time GPS mendukung antrean sah hari sebelumnya setelah paket pagi diganti. Legacy record tanpa source hanya memakai fallback paket tersimpan yang cocok session/date/version/site/openedAt; source hilang/tidak cocok ditahan tanpa auto-rekonstruksi. Command legacy unbound tetap berjalan; order yang dirujuk visit tidak boleh membuang konteks untuk bypass.
**Diverifikasi lokal:** 102 unit + 1 hosting; 36 browser phone/tablet termasuk corrupt IndexedDB → reload → reconnect → retry. Mutasi check-in/order/check-out/parent accepted/session/outlet/geo/source/owner/time/envelope, missing source/ledger, dropped context, boundary before provider, next-day valid replay dan legacy compatibility. Format/typecheck/contracts/demo+live/budget/Ruff/4 manifest. CI diperiksa sesudah push.
**Batas:** snapshot sumber/validasi client hanya integritas simulator, bukan keamanan/anti-mock GPS/otorisasi backend. Tidak mengubah wire DTO atau versi IndexedDB. Tidak menyentuh addon/backend/seed/loader/workflow/ruleset/Railway; live tetap terkunci, tidak merge/deploy.
**Menunggu:** CI commit perbaikan dan review ulang supervisor sebelum merge pemilik.

## 2026-10-27 — codex agent — Kunjungan outlet dan dependency sync simulator
**Basis:** main 955071a; branch agen/mobile-sales-visits, terisolasi dari pekerjaan seed.
**Berubah:** pilih PJP → GPS/check-in → order → check-out hasil/catatan; konteks visit/session/date/version/outlet/geofence. GPS TTL 60 detik, future tolerance 1 detik, radius 5–15 m tanpa ekspansi (distance+accuracy <= radius). Order dan check-out mengambil GPS baru; stale/uncertain/outside/denied menahan aksi.
**Offline/integritas:** ledger+outbox+sumber sesi ditulis atomik CAS; restore owner/time/ref/source memeriksa konteks. Sync bergantung receipt check-in accepted lalu semua receipt bisnis order sebelum check-out; urutan UUID tidak menentukan urutan submit. Transport error tidak menjadi receipt bisnis. Satu aktif/hari dan satu visit per outlet/hari simulasi; histori lama tidak menjadi izin hari berikutnya.
**Kontrak/CI:** OpenAPI draft 0.4 menambahkan strict visit DTO/VisitOrder; legacy order generic tetap kompatibel. CI existing otomatis memuat tes baru; live fixture gate ditambah. README/plan terintegrasi.
**Diverifikasi:** 81 unit + 1 hosting; 34 browser phone/tablet; format/typecheck/contracts/demo+live/budget (demo JS 49,7 KiB gzip; font 47,1 KiB), Ruff/4 manifest. CI diperiksa setelah push.
**Batas:** hanya simulator; bukan ACL/auth/geofence authoritative atau anti-mock GPS. Belum pinpoint map/foto visit/tracking background/extra-call approved visit/recovery admin. Queue tertahan butuh review, tidak auto-cancel. Server session/device/media/policy/idempotency tetap dependency.
**Tidak disentuh:** addon/backend/seed/loader, workflow/ruleset, Railway/domain/deployment. Live tetap terkunci; tidak merge/deploy.
**Menunggu:** review PR, hasil CI, merge pemilik dan deploy manual commit diterima.

## 2026-10-27 — codex agent — Follow-up PR #22 dan koreksi realisasi simulator
**Basis:** main 5088144; branch agen/mobile-expense-revisions; detail review issuecomment-6433199416 dibaca.
**Tiga perbaikan:** ID komponen stabil (draft legacy tanpa ID dipulihkan dengan default baru), preview/file/location direconcile saat ref/owner berganti atau file gagal, async generation guard; dedup merchant/receipt/date lintas advance satu owner/DB dipindah ke transaksi outbox; sumber request dibandingkan ulang atomik setelah rangkaian await. Receipt transport tidak melepaskan klaim struk.
**Dev berikutnya:** receipt penolakan bisnis cocok UUID membuka koreksi; UUID baru + supersedes_uuid/alasan, parent lama immutable, status belum terkonfirmasi/transport tidak membuka edit. Restore memvalidasi lineage/source/owner/urutan waktu/parent rejected/missing ref/cycle; CAS predecessor mencegah koreksi atas penolakan yang berubah dan dua successor aktif.
**Kontrak/docs:** OpenAPI draft 0.3, revision fields opsional demi kompatibilitas payload lama; pasangan diwajibkan pada jalur koreksi. Tidak ada DB migration atau endpoint backend baru. README/plan memperbarui batas lama, bukan hanya menambah klaim baru.
**Diverifikasi lokal:** 71 unit, 1 hosting, 30 browser phone/tablet PASS; barrier dua koneksi untuk dedup lintas advance/koreksi, source-change-during-submit (payload/status), transport/wrong receipt lock, lineage corruption, remove-line/replace-invalid/missingblob, browser rejected→correction→needsapproval dengan parent tetap utuh. Format/typecheck/contracts/demo+live builds/budget/Ruff/4 manifest PASS; demo JS ~45 KiB gzip, font 47,1 KiB. CI diperiksa setelah push.
**Batas:** dedup hanya cooperative writer satu owner dan IndexedDB yang sama; lintas akun/perangkat/server tetap authority backend. Foto local_map_pending; revision state bukan security boundary. Settlement final, cancel pending, cash/GL/auth/media/geofence/tracking tetap dependency/roadmap.
**Tidak disentuh:** backend/addon/seed/loader, workflow/ruleset, Railway/domain/deployment. Live terkunci.
**Menunggu:** review PR dan CI; merge pemilik lalu deploy manual commit yang diterima.

## 2026-10-27 — codex agent — Realisasi biaya dan estimasi settlement simulator
**Basis:** main b19240a (PR #21 merged); branch agen/mobile-expense-settlement.
**Berubah:** layar Lainnya → Realisasi & saldo uang lapangan; receipt request dipisah dari approval/pencairan fiktif. Policy fixture contoh, komponen/struk, foto lokal, odometer/liter-harga BBM, draft offline, preview refund/variance dan tier total exposure. Pratinjau foto dipulihkan per owner setelah reload.
**Integritas client:** restore advance/submit memakai validator source fingerprint/owner/amount/approval/timestamp/link outbox; create-if-absent advance dan transaksi outbox+link dengan compare-and-set. Dua koneksi diuji agar satu advance tidak punya dua command realisasi; rollback/quota tidak membuat orphan. Request material berubah menahan advance lama.
**Kontrak/CI:** CommandSchema discriminated union dengan payload realization strict, OpenAPI draft 0.2; tidak menambah endpoint backend. Gate build menolak fixture/kontrol pencairan pada live. Seluruh workflow CI existing dipertahankan; tes baru ditemukan otomatis.
**Diverifikasi lokal:** 60 unit, 1 hosting, 24 browser phone/tablet PASS; format/typecheck/contracts/demo+live build/budget (demo JS ~43,8 KiB gzip, font 47,1 KiB), Ruff/4 manifest PASS. Screenshot realisasi/pratinjau bukti ditinjau; foto tes memakai icon app. CI diperiksa setelah push.
**Batas:** estimasi settlement, bukan uang dikembalikan/top-up disetujui/dibayar/GL. Foto local_map_pending; submit hanya simulator dan receipt membutuhkan review. Limit Rp250.000 adalah fixture contoh, bukan policy perusahaan. Koreksi setelah antre/reject, final settlement, policy bertanggal/agregat, media hash/map/OCR/dedup server, multi-pengisian/multi-hari tetap dependency. Referensi foto terpisah tidak membuktikan konten foto berbeda; local state bukan security boundary.
**Tidak disentuh:** addon/backend/seed/loader, workflow/ruleset, Railway/domain/deployment. Live terkunci.
**Menunggu:** review PR dan CI, merge pemilik serta deploy manual commit yang diterima. Panduan dan batas lengkap di pwa/README.md.

## 2026-10-27 — codex agent — Tutup celah restore sesi PR #21
**Basis:** PR #21 HEAD 8693b13; review issuecomment-6432082496, tetap branch agen/mobile-session-brand.
**Koreksi:** klaim paket invalid tidak membuka sesi pada entri sebelumnya belum berlaku untuk restore. Celah direproduksi: 17 dari 19 kasus mutasi persisted state baru gagal pada implementasi lama.
**Berubah:** validator semantik shared untuk sync/open, restore dan morningReady. Memeriksa owner/businessDate, hari/urutan timestamp absensi–sesi–snapshot, masa depan, versi nonblank, products/outlets nonempty dan konsistensi attendance-only vs sesi lengkap. Restore invalid mengembalikan undefined tanpa menghapus pending outbox atau draft bisnis.
**Diverifikasi lokal:** 48 unit, 1 hosting dan 20 browser phone/tablet PASS; regresi corrupt IndexedDB bundle lalu reload offline menahan order/extra-call dan mempertahankan seluruh draft/outbox. Paket valid lintas tanggal UTC dalam satu hari WITA tetap diterima. Format/typecheck/contracts, demo/live builds/budget, Ruff/4 manifest PASS. CI diperiksa setelah push.
**Batas:** tetap simulator client; bukan auth/device/server security. Branding dan live lock dipertahankan.
**Tidak disentuh:** backend/seed/loader/Railway, workflow atau ruleset. Tidak merge/deploy.
**Menunggu:** reviewer memeriksa ulang commit perbaikan pada PR #21 setelah CI.

## 2026-10-27 — codex agent — Sesi pagi simulator dan branding Odoo FMCG Mobile
**Basis:** main efd0373 (PR #20 merged), branch agen/mobile-session-brand. Deployment field-pwa dilaporkan pemilik SUCCESS/live terkunci; tidak diubah pada pekerjaan ini.
**Berubah:** kartu sesi pagi Sales/Canvasser (absensi diterima simulator → sync online), paket snapshot PJP/stok/harga dan sesi atomik per company/persona; order/extra-call baru memerlukan sesi hari WITA yang sama. Reload offline memulihkan paket; error, tanggal/snapshot invalid atau quota gagal tidak membuka sesi.
**Branding:** nama Odoo FMCG Mobile pada title/manifest/boot/header; wordmark Odoo + badge FMCG, Mobile di bawah, navy kontras. Glyph oi-odoo resmi diekstrak menjadi SVG; icon PNG 192/512, apple-touch 180, favicon 32; atribusi/license lokal. Tidak menyentuh addon desain web; log claude-design dibaca untuk konsistensi.
**Diverifikasi lokal:** 27 unit, 1 hosting, 18 browser phone/tablet; format/typecheck/OpenAPI drift, demo/live build/budget (demo JS ~38,2 KiB gzip; font 47,1 KiB), Ruff/4 manifest. Preview logo/icon dan screenshot home ditinjau. CI diperiksa setelah push.
**Batas:** sesi ini simulator client, bukan server auth/security/device binding. Kontrol absensi demo terpisah dari bukti foto map_pending; tidak mengklaim absensi sah. Tanggal perangkat/storage dapat diubah. Backend tetap wajib menerbitkan sesi/tanggal/ACL/approval/evidence; driver tidak digate oleh sesi Sales. Realisasi/settlement belum dikerjakan.
**Tidak disentuh:** backend/seed/loader, workflow Odoo, Railway/service/domain/mode deployment. Build live tetap terkunci; tombol sesi simulator tidak dikirim ke bundle live.
**Menunggu:** review PR/CI, merge pemilik dan deploy manual commit yang disetujui agar branding muncul di domain aktif.

## 2026-10-27 — codex agent — Biaya client dan hosting PWA terisolasi
**Basis:** main f636129 (PR #19 diterima sebagai fondasi simulasi); branch agen/mobile-expense-hosting.
**Berubah:** validasi request biaya (H-1 menurut businessDate bootstrap, referensi trip/DO, rupiah bulat, KM BBM dan satu charging scope), schema ExpenseRequest OpenAPI; server hosting Node24, Dockerfile multi-stage live-locked default/demo eksplisit, railway.toml + runbook.
**CI:** browser memakai server hosting yang sama; test:hosting dan pwa-container additive, aggregator pwa-gate memerlukan quality/browser/container. Tidak mengubah ruleset atau workflow Odoo.
**Diverifikasi:** 19 unit + 1 hosting test + 14 browser phone/tablet PASS, format/typecheck/contracts/build budget, Ruff/4 manifest PASS. CI diperiksa setelah push.
**CI awal:** quality/browser PASS; image live berhasil dibangun. Smoke health request terkena connection reset saat startup; retry diperluas untuk reset selain refused. Run baru diperiksa setelah fix. Docker lokal tidak tersedia. Railway belum dibuat/dideploy, API route mengembalikan 503 eksplisit.
**Batas:** businessDate bootstrap bisa stale; server wajib validasi ulang tanggal/cutoff, referensi/ACL, limit, bukti dan approval. Input referensi manual simulasi belum membuktikan DO/trip ada. Absensi/POD, auth/device, peta, realisasi/settlement dan posting backend tetap dependency; live terkunci.
**Menunggu:** review pemilik; setup service/deploy oleh pemilik/agent deploy setelah review. Backend/seed/loader dan service Odoo tidak disentuh.

## 2026-10-27 — codex agent — Frontend PWA awal dan CI additive
**Basis:** origin/main 69a7ef6 + plan lokal, branch agen/mobile-pwa-foundation.
**Berubah:** folder pwa (Preact/TS/Vite, Phosphor, Inter, navy/blue, bottom nav, role fixture, form lapangan/personal HRIS/petty cash, local evidence, draft/outbox, provider contract); .github/workflows/pwa.yml; plan §16.
**Diverifikasi lokal:** format/typecheck/contract drift, 14 unit/contract/storage tests, 12 browser tests phone/tablet; demo/live builds dan budget PASS (demo JS ~36 KiB gzip, font 47,1 KiB). Visual screenshot ditinjau; SVG sizing dan offline cache Vary diperbaiki, ditangkap gate browser.
**CI baru:** pwa-quality, pwa-browser, pwa-gate aggregator. Tidak mengubah workflow Odoo, ruleset atau deployment. Hasil GitHub CI ditinjau setelah push.
**Batas:** build live terkunci, fixture hanya demo; accepted bukan SO Odoo. Capture foto/lokasi lokal masih map_pending sehingga absensi/POD tidak dinyatakan sah. I18n English penuh, tracking, realisasi/settlement rinci dan integrasi API/domain masih mengikuti roadmap; README mencatat status per paket.
**Tidak disentuh:** addon backend/seed/loader, server production dan branch agent lain.
**Menunggu:** review PR dan CI; backend menjadi dependency/handoff sesuai mandat mobile-only.

## 2026-10-26 — codex agent — Plan v0.4: frontend-first, mandat mobile-only
**Arahan pemilik:** tidak mengambil pekerjaan agent lain; siapkan mobile/PWA meski backend belum siap.
**Berubah:** plan mobile §1.1/1.2 dan §7.1/7.2: UI/alur client dengan provider interface dan mock terisolasi, kontrak bertahap, HTTP adapter saat API siap. PWA-01–06 menjadi urutan kerja aktif; MOB existing tetap peta dependency sistem.
**Batas:** harga/kredit/HPP/approval/auth/posting tetap keputusan backend. Mock berlabel Simulation, tidak fallback diam-diam di produksi. Agent mobile tidak mengoreksi seed/loader atau membangun id_api/id_app tanpa mandat baru.
**Dokumentasi:** plan satu sumber teknis di blueprints; audit gap snapshot terpisah; integrasi SCOPE/DEVELOPMENT berupa tautan/ringkasan saat koordinasi, bukan duplikasi seluruh desain.
**Diverifikasi:** contoh JSON, sequence paket dan whitespace; perubahan docs-only, belum ada implementasi/runtime test baru.
**Menunggu:** eksekusi PWA sesuai urutan frontend-first; tidak ada push, merge atau deploy.

## 2026-10-26 — codex agent — Gap analysis pra-implementasi mobile dan visual plan v0.3
**Basis:** origin/main 69a7ef6; dependency seed PR #15 head c435447; branch lokal agen/mobile-reconnaissance.
**Berubah:** `docs/reviews/MOBILE_READINESS_GAP_2026-10-26.md` (G01–G17, inventaris data, workflow/commit, acceptance gates); plan mobile v0.3 (Phosphor duotone, Inter Variable, palette navy/blue, readiness dependency).
**Diverifikasi:** handoff/log empat agent dan delta branch seed dibaca; PR/checks diperiksa lewat GitHub; dua validator serta 98 tests PASS pada worktree c435447 (26,752s), manifest empat addon PASS; struktur dokumen dan rasio kontras diperiksa.
**Temuan P1:** truthiness model recordset kosong dipakai adapter/runner sehingga lot/invoice/discount/readback dapat terlewat; guard bukan bukti model tidak terpasang. Runner limit_orders=1 tidak memilih SO rejection yang disebut. Bukti actual runtime Odoo dan snapshot Run1/Run2 lengkap tetap diperlukan.
**Gap lain:** fallback admin pada master salesman, employee stable code/user/app role belum dipetakan, kalender HR 5 hari vs PJP 6 hari, UoM Units/packaging, geo simulasi bukan presisi geofence, domain approval/expense/trip/API/PWA belum ada.
**Belum diuji:** DB/image aktual, staging/production, perangkat mobile, Phosphor/font build dan screenshot UI. Tidak mengubah kode/data worker atau menjalankan loader production.
**Menunggu:** worker seed/backend menutup gap dependency dan runtime; koordinasi agent desain untuk token visual; pemilik menentukan integrasi PR. Rekomendasi handoff belum dikirim sebagai pesan ke agent lain.

## 2026-10-26 — codex agent — Mobile plan v0.2: kontrol operasional dan biaya lapangan
**Mandat:** 11 tambahan requirement pemilik dimasukkan ke `docs/blueprints/mobile_api_and_pwa_plan.md` (§9–14, traceability R01–R11).
**Berubah:** binding akun/perangkat dan sesi kerja; petty cash/BBM H-1/insidentil/biaya DO-trip/settlement; extra call dan approval diskon sampai Owner untuk below-cost; seluruh foto berpeta; geofence 5–15m; tracking 5/15 menit; polling/outbox/notifikasi; bottom nav, liquid motion/haptic dengan budget low-end.
**Diverifikasi:** main tetap 69a7ef6 setelah fetch; sumber W3C/Chrome/MDN untuk batas PWA; contoh JSON, struktur heading/tabel, coverage R01–R11 dan whitespace diperiksa. Manifest validator dijalankan; tidak ada kode runtime baru.
**Belum diuji:** seluruh kontrol dan angka baseline masih rancangan; tidak menjanjikan background tracking/polling selalu hidup atau anti-spoof mutlak di PWA/native.
**Butir terbuka:** limit rupiah, cutoff H-1, metode HPP, provider map, kebijakan luar kota/retensi dan hasil spike akun/perangkat. MOB-01 mencakup absensi minimum agar sesi pagi tidak menunggu MOB-05.
**Menunggu:** paket MOB-00 setelah finalisasi rancangan; tidak ada push, merge atau deploy.

## 2026-10-26 — codex agent — Rancangan dua jalur API backend dan PWA
**Mandat:** pemilik menegaskan hybrid: Odoo web penuh untuk back-office, PWA sendiri untuk lapangan/personal HRIS.
**Berubah:** `docs/blueprints/mobile_api_and_pwa_plan.md` v0.1 menjadi rancangan bersama API/PWA; mencakup modul, endpoint usulan, auth/role/scope, sync/idempotensi, offline UX, Sales/Delivery/HRIS, media, roadmap MOB-00–06 dan gate penerimaan.
**Diverifikasi:** konsistensi terhadap SCOPE/Playbook/spike existing, source main 69a7ef6 dan scan repo sebelumnya; JSON contoh dan whitespace diperiksa.
**Belum diuji:** semua endpoint/model/policy/performance baru masih rancangan; runtime Odoo/mobile belum dijalankan. Ruff tidak tersedia pada runtime sesi lanjutan; tidak mengklaim lint ulang PASS.
**Butir terbuka:** MOB-00 menutup transport API, akun/session minimal dan transaksi; budget offline/media/performance perlu bukti perangkat pilot. Personal HRIS slip/bukti potong menunggu modul domain tersedia.
**Menunggu:** review rancangan oleh pemilik; tidak ada perubahan kode aplikasi, dataset, push atau deploy.

## 2026-10-26 — codex agent — Deep scan kesiapan mobile
**Basis:** main 69a7ef6; branch lokal agen/mobile-reconnaissance.
**Berubah:** laporan `docs/reviews/MOBILE_SCAN_2026-10-26.md`, log codex; tanpa perubahan kode aplikasi/dataset.
**Diverifikasi:** manifest dan Ruff PASS; CI main static/install-test/init-test success melalui GitHub API; PR #14/#15 masih open.
**Belum diuji:** runtime Odoo lokal, device mobile, spike API, kandidat masalah judul form saat ui.isSmall.
**Butir terbuka:** API/auth/role belum ada; kontrak idempotensi, incremental sync, privasi cache dan scope ownership perlu dikunci sebelum implementasi mobile.
**Menunggu:** mandat implementasi berikutnya dari pemilik; scan ini tidak push, merge atau deploy.

## 2026-10-26 — codex agent — UI v7 siap review tanpa SQL wilayah
**Basis:** main f130693 + perubahan UI/dokumentasi claude-design 388eff6.
**Scope:** 20 SQL data/raw tidak dibawa; file asli tetap di agen/ui-cleanup-v7.
**Perbaikan:** divider memakai computed visibility observer scoped ke systray,
tanpa display override, cleanup saat unmount; pager smoke wajib dua record,
memastikan judul berubah lalu pulih. Empat regression tests Chromium memakai
SCSS/helper asli (hidden, responsive, dynamic item, observer cleanup).
**CI:** install-test memasang id_ui_form beserta dependency, menjalankan tests
id_base/id_ui/id_ui_shell, fixture dua quotation, Odoo server dan browser smoke.
Tidak memakai Railway/production atau data seed transaksi.
**Verifikasi lokal:** Ruff dan manifest/syntax checks; browser lokal belum tersedia,
penerimaan runtime menunggu hasil CI branch ini. Tidak ada klaim merge main.

## 2026-10-25 — claude-design agent (chat + sandbox) — UI cleanup v7: handoff dirapikan, judul statusbar dikokohkan, divider generik, !important dikurangi
**Berubah:** (1) Entri HANDOFF v2/v3/v4 dilipat ke berkas ini dan `docs/ui/_handoff_v2/_v3/_v4.md` dihapus; mulai sekarang entri ditulis langsung di `HANDOFF.md`, tanpa berkas sementara. (2) `id_ui_form`: `syncTitle` idempoten, dibatasi ke akar renderer (`useRef("compiled_view_root")`), dikembalikan ke sheet bila tata letak klasik atau form di dialog, titik sisip aman. (3) `id_ui_shell`: divider systray generik (item tampil - 1; item kosong dan pembungkus tombol menu mobile tidak dihitung) sehingga benar juga di mode debug (5 item). (4) `!important` turun dari 27 ke 3 (shell) dan dari 60 ke 4 (form), semuanya melawan utilitas Bootstrap/Odoo dan diberi komentar alasan. (5) `smoke_ui.py` 25 -> 32 cek (judul tunggal di statusbar, footer sticky, divider normal/debug, pager, ganti tata letak dan pemulihan judul). (6) `docs/ui/id_ui_form.md` dan `id_ui_shell.md` diperbarui (pemindahan DOM, kebijakan `!important`).
**Diverifikasi (bagaimana):** sandbox, Odoo `f4378f29`, DB kosong: 0 failed dari 7 uji; smoke 32/32; snapshot gaya terhitung + posisi elemen kunci di 4 halaman (form, form debug, daftar, dashboard) sebelum vs sesudah identik untuk halaman normal (selisih hanya mode debug: ikon debug kini sejajar, divider konsisten); smoke baru GAGAL terhadap SCSS lama (debug: 5 item, 3 divider), jadi cek itu memang menangkap bug; pemindahan DOM judul 1 kali saat mount dan tetap 1 setelah 9 re-render tab; `ruff` dan `check_manifests.py` lolos.
**Belum diuji:** stack OCA penuh, `docker build`/Railway, CI, browser selain Chromium, mobile; footer sticky pada form selain order penjualan.
**Butir terbuka:** (1) dua sesi memakai tanda tangan `claude-design agent` sehingga acuan `whats_new.sh` ambigu; usul untuk pemilik/`claude-dev`: bedakan per sesi (mis. akhiran sesi) di `AGENT_PROTOCOL.md` dan wajibkan `log_entry.sh` agar tanda tangan commit sama dengan entri log (log v4 memakai UTC dan tanda tangan v4-v6 berbeda dengan stempel entri log). (2) M1c dari review `claude-dev` (menu referensi ke Configuration, dashboard contoh, kolom/filter/group-by) belum dikerjakan. (3) Panel ganda di aplikasi Dashboards masih terbuka. (4) Koreksi dari saya: entri v2 menyebut fase `-u` berjalan setiap boot; yang benar berbasis penanda (`upgrade_modules_vN`). Aturan kapan perlu `-u` ada di `docs/ui/id_ui.md`. (5) Menu `FMCG Distribution` (id_base, sequence 25) belum punya terjemahan `id_ID` sehingga tampil Inggris di sidebar Indonesia; terjemahan sebaiknya di `id_base/i18n` atau lewat glosarium (istilah baru). (6) CI `install-test` masih hanya memasang `id_base`; permintaan menambah `-i id_ui_form` dan `--test-tags /id_ui,/id_ui_shell` belum terpenuhi (diuji manual bersama id_base terbaru: 0 failed dari 8, log bersih).
**Menunggu:** pemilik (terapkan patch, commit, push); `claude-dev` (putuskan aturan penamaan sesi di protokol).

## 2026-10-25 — antigravity agent (Live Railway & Playwright Verification: Database Schema Synchronization & Browse Error Resolution)
**Berubah:**
- `deploy/init.sh`:
  - Menaikkan penanda pembaruan skema dari `upgrade_modules_v1` ke `upgrade_modules_v2` agar siklus `-u $INIT_MODULES` selalu dijalankan saat kode modul baru ditambahkan pada container Odoo dengan Postgres persisten.
- Railway Production Environment:
  - Mengaktifkan `FORCE_UPGRADE=1` sementara melalui Railway MCP untuk memicu re-indexing skema lengkap (menambahkan kolom baru `id_principal.pic_name`, `fleet_vehicle.capacity_ton`, kargo box, dsb.).
  - Mengembalikan `FORCE_UPGRADE=0` di Railway setelah skema sukses disinkronkan, sehingga boot container selanjutnya tetap instan dan efisien.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Log runtime Railway deployment `5b1a6322-56d1-4d3d-bc3f-7a8c9742990f` mencatat eksekusi sukses pembaruan tabel `fleet`, `product`, `hr`, `id_base`, dan `id_ui` (`Registry loaded in 0.959s`).
- Pengujian interaktif end-to-end via Playwright headless Edge pada instance live `https://odooca-fmcg-demo.up.railway.app`:
  - **FMCG Principals:** Daftar prinsipal dan form record (PT Mayora Indah Tbk, PT Santos Jaya Abadi, PT Unilever Indonesia Tbk, PT Wings Surya) terbuka mulus tanpa pesan error; field Key Contact / PIC terisi dan tampil rapi.
  - **Products / Katalog FMCG:** Kanban view dan form view produk (Banngo Kecap Manis, Benn-Beng dkk) terbuka sempurna; struktur hirarkis kategori `[PRINSIPAL] > [DIVISI] > [BRAND]`, data kemasan karton, dan barcode tampil lengkap.
  - **Fleet / Armada:** Kanban dan form kendaraan (DB 8123 QA) terbuka tanpa error dan terhubung dengan driver Novry Mandagi.
  - **Employees / Karyawan:** Profil karyawan terbuka rapi dan terafiliasi dengan alamat resmi `PT Manado Distribusi Utama` di Interchange Maumbi.
  - **Contacts / Pelanggan:** Daftar kontak outlet terbuka bersih tanpa referensi field tier lama.
  - Seluruh screenshot hasil verifikasi tersimpan di direktori artefak (`v2_02_principal_form.png`, `v2_07_product_form.png`, `v3_02_fleet_form.png`, `v3_06_employee_form.png`).

**Belum diuji:**
- Simulasi transaksi end-to-end Sales Order -> Picking/DO -> Invoicing dengan perhitungan margin per divisi prinsipal (dijadwalkan pada M2).

## 2026-10-25 — antigravity agent (Master Data Native Refinement: Tier Removal, Fleet Cargo, Principal PIC, Road Coordinates, Org Hierarchy, PT MDU & 5-Day Calendar)
**Berubah:**
- `addons/id_base`:
  - Menghapus model `id.tier`, field `tier_id` pada `res.partner`, berkas `data/id_tier_data.xml`, views, menus, dan hak akses security (eliminasi custom tier yang tidak relevan dengan B2B FMCG).
  - Menambahkan inherisi model `fleet.vehicle` (`addons/id_base/models/fleet_vehicle.py` & views) dengan field native & kargo: `capacity_ton`, `capacity_cbm`, `box_length`, `box_width`, `box_height`, `stnk_expiry`, `kir_expiry`, dan `operational_route`.
  - Menambahkan field kontak dan PIC pada `id.principal` (`pic_name`, `pic_phone`, `pic_email`) dan form view.
  - Menambahkan dependensi `"fleet"`, `"hr"`, `"uom"` pada `addons/id_base/__manifest__.py`.
- `scripts/generate_fmcg_seed.py`:
  - Rekalibrasi koordinat 354 outlet (`DISTRICT_COORDS`): menambatkan geotag outlet tepat pada koridor jalan darat tiap kecamatan (anti-drowning di Teluk Manado & anti-lereng gunung).
  - Menambahkan dimensi fisik realistis (`length_cm`, `width_cm`, `height_cm`, `volume_cbm`) untuk satuan terkecil (Pcs) dan Karton (`carton_length_cm`, `carton_width_cm`, `carton_height_cm`, `carton_volume_cbm`, `carton_weight_kg`) pada 150 Master SKU.
  - Menambahkan dimensi box kargo armada logistik (`box_length_m`, `box_width_m`, `box_height_m`) pada 9 armada.
  - Menambahkan `manager_code` pada 24 personel untuk membentuk pohon hirarki organisasi.
  - Menambahkan generator `generate_principals` yang menghasilkan `data/seed/principals_4.csv` lengkap dengan PIC, NPWP CoreTax, alamat, dan nomor telepon resmi.
- `scripts/load_fmcg_seed.py`:
  - Membangun struktur kategori hirarkis Odoo `product.category`: `[PRINSIPAL] > [DIVISI KATEGORI] > [BRAND]` untuk mengisolasi penilaian persediaan, COGS, dan SLA retur antar-prinsipal.
  - Memuat vendor partner resmi dan menghubungkan data PIC prinsipal dari `principals_4.csv`.
  - Memuat metadata kargo armada logistik ke `fleet.vehicle`.
  - Membangun departemen (`Management`, `Sales & Distribusi`, `Finance & Akuntansi`, `Warehouse & Logistik`) dan relasi manajer (`parent_id`) pada `hr.employee`.
- `deploy/init.sh`:
  - Menambahkan modul `fleet,hr,uom` ke default `INIT_MODULES`.
  - Menambahkan blok idempoten `company_profile_v2` untuk menyetel nama resmi `PT Manado Distribusi Utama` (Interchange Maumbi, Manado 95371, telp: `0431-889900`, vat: `012345678821000`) dan kalender kerja 5 hari (Senin - Jumat 08:00 - 17:00, Sabtu - Minggu libur).
  - Menaikkan penanda seed ke `seed_master_v4`.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- `python -m ruff check .` lolos (`All checks passed!`).
- `python scripts/generate_fmcg_seed.py` dieksekusi sukses menghasilkan `principals_4.csv`, `products_150.csv`, `partners_354.csv`, `employees_24.csv`, dan `vehicles_9.csv`.
- Cabang `agen/master-data-native-refinement` di-push dan diajukan via PR #12 (`https://github.com/kolondam-dev/odooca-fmcg/pull/12`).
- Seluruh 3 workflow checks di GitHub Actions CI (`static`, `install-test`, `init-test`) **PASS / HIJAU 100%**.

**Belum diuji:**
- Pemuatan langsung ke instance container Odoo live di Railway (menunggu merge PR #12 ke `main`).

## 2026-10-25 — antigravity agent (M1a: Master Data Refinement — Legal Protection Names, Address/Contact Integrity, Product Packaging, Roster, Fleet, Fail-safe Seed Mark)
**Berubah:**
- `addons/id_base/data/id_principal_data.xml`:
  - Mengubah 4 Principal dan 29 brand menjadi nama fiktif pelindung hukum (`PT Mayyora Indahh Tbk`, `PT Santos Jaya Abadii`, `PT Unilevr Indonezia Tbk`, `PT Sayapp Mas Utamma`, dsb.) untuk mitigasi risiko hak cipta/merek dagang nyata [E1].
- `scripts/generate_fmcg_seed.py`:
  - Mengacak dan menyesuaikan nama brand fiktif pada 150 SKU FMCG.
  - Mengganti `EMP-001` Bpk. Teddy Kolondam menjadi nama fiktif "Bpk. Ronald Mongisidi" serta menambahkan `work_email` (`@fmcg-demo.id`) dan `work_phone` (`08xxxxxxxxxx`) pada seluruh 24 personel roster [E2].
  - Menambahkan data geografis dan kontak pada seluruh 354 partner: `city` (Manado, Bitung, Tomohon, Minahasa, dsb.), `state` ("Sulawesi Utara"), `country` ("Indonesia"), `phone` (`08xxxxxxxxxx`), dan NPWP format CoreTax 16-digit [A2].
  - Menghilangkan/decouple `tier_code` sesuai arahan pemilik [A1].
  - Mengganti nama outlet GT dan RTL dengan nama warung/kios/toko lokal Minahasa/Manado yang variatif.
- `data/seed/*.csv`:
  - Regenerasi deterministik untuk `products_150.csv`, `partners_354.csv`, `employees_24.csv`, dan `vehicles_9.csv`.
- `scripts/load_fmcg_seed.py`:
  - Menambahkan pembuatan vendor partner (`res.partner`, `supplier_rank=1`) untuk principal yang terhubung ke `principal.partner_id`.
  - Menambahkan pembuatan kategori hirarkis FMCG di `product.category` dan linking kategori produk.
  - Memperbarui `load_products`: mengaktifkan `is_storable = True`, `tracking = 'lot'`, dan membuat packaging kemasan Karton (`product.packaging`) berbasis UoM Pcs [A4, A5].
  - Menambahkan pemuatan 24 karyawan ke `hr.employee` dan `hr.department` [A6].
  - Menambahkan pemuatan 9 unit armada ke `fleet.vehicle`, `fleet.vehicle.model`, dan `fleet.vehicle.model.brand` [A6].
  - Memperbarui `load_partners`: memetakan `city`, `state_id`, `country_id`, `phone`, `vat`, `property_payment_term_id` (TOP), dan `user_id` (salesman), serta memastikan `tier_id` tidak digunakan [A1, A2, A3].
- `deploy/init.sh`:
  - Menaikkan penanda seed ke `seed_master_v3` dan membungkus eksekusi seed dengan kondisional fail-safe agar jika skrip gagal, penanda tidak terbuat [C1].
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- `python -m ruff check .` lolos (`All checks passed!`).
- `python scripts/generate_fmcg_seed.py` dieksekusi sukses menghasilkan 150 produk, 354 partner, 24 karyawan, dan 9 armada secara konsisten.
- Cabang `agen/m1a-master-data-refinement` di-push ke remote dan diajukan via PR #11 (`https://github.com/kolondam-dev/odooca-fmcg/pull/11`).
- Seluruh 3 workflow check GitHub Actions CI (static, install-test, init-test pada DB kosong + restart idempoten) **PASS / HIJAU 100%**.

**Belum diuji:**
- Pemuatan langsung ke instance aktif Railway (menunggu merge PR #11 ke `main`).
- Simulasi transaksi historis M2 (line vs header consistency) yang dijadwalkan pada Prioritas 2.

## 2026-10-25 — claude-design agent (UI Refinement v6: Systray Dividers Alignment, Form Statusbar Middle Align Without Rounded Box, Edge-to-Edge Form, Steady Sticky Footer)
**Berubah:**
- `addons/id_ui_shell/static/src/shell/id_shell.scss`:
  - Systray navbar kanan: 4 menu aktif (`.o-mail-DiscussSystray-class`, `.o-dropdown:has(.fa-clock-o)`, `.o_switch_company_menu`, `.o_user_menu`) diseragamkan `height: 38px; display: flex; align-items: center;`.
  - Tepat 3 pemisah vertikal rapi dipasang via `::before` pada item 2, 3, dan 4 dengan `height: 20px; width: 1px; background: #d8dee8; align-self: center;`, menghilangkan garis divider yang meleset atau turun keluar deret menu.
- `addons/id_ui_form/static/src/form/id_form.scss`:
  - Form Full Width edge-to-edge: `.o_form_sheet_bg` disetel `padding: 0; background: #fff;`, `.o_form_sheet` disetel `border: none; border-radius: 0; padding: 1rem 1.25rem 0; width: 100%; max-width: 100%;`.
  - Statusbar form: tombol aksi, judul form (.oe_title / .id_statusbar_title), dan statusbar pipeline disetel `align-items: center !important` (sejajar align middle secara presisi). Background box rounded putih dihilangkan total (`background: transparent; border: 0; border-radius: 0; box-shadow: none;`).
  - Sticky footer: padding/margin disesuaikan flush edge-to-edge, border-bottom dihilangkan, posisi footer tetap diam (steady di bottom) tanpa bergeser/bouncing saat scroll ke atas.
- Log: `agent-log/claude-design.log`.

**Diverifikasi (bagaimana):**
- Verifikasi Playwright headless: alignment statusbar presisi (pusat Y = 156.25px untuk ketiga komponen), form selebar 100% viewport, sticky footer tetap menempel diam di bottom saat di-scroll bolak-balik, 3 divider systray rapi sejajar.
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).

**Belum diuji:**
- Browser Firefox/Safari (hanya diuji Chromium/Edge).
- Layar mobile (akan fallback ke tampilan responsif bawaan).

## 2026-10-25 — claude-design agent (UI Refinement v5: Form Full Width, Sticky Footer, 3 Systray Dividers, Form Title Statusbar, Badge & Logo O Glow)
**Berubah:**
- `addons/id_ui_shell/static/src/shell/id_shell.scss`:
  - Token `--id-brand-box` disetel ke warna ungu Odoo (`#714B67`).
  - `.o_menu_brand`: ukuran font diperbesar menjadi `1.45rem` (bold 700) di tengah navbar.
  - `.o_menu_systray`: tepat 3 divider pemisah vertikal (tinggi 22px) antar 4 menu (Discuss, Activity, Company, User). Child kosong disembunyikan.
  - `.id_sidebar .id_brandbox`: font lebih besar (0.75rem), bold 700, sudut tegas tanpa rounded, background ungu Odoo.
  - `.id_sidebar__logo`: transisi hover/active diperhalus tanpa shaky rotation, menggunakan `@keyframes id-logo-pulse` dengan double drop-shadow ungu Odoo.
- `addons/id_ui_form/static/src/form/id_form.scss`:
  - `.o_form_sheet_bg`: `max-width: 100% !important; padding: 0.5rem 1rem !important;`
  - `.o_form_sheet`: `max-width: 100% !important; width: 100% !important; margin: 0 !important;` (form lapang dan luas mengisi rongga kiri-kanan).
  - `.o_form_statusbar`: border rapi, background putih, penampung judul dokumen di tengah.
  - `.o_form_sheet .o_group:has(.oe_subtotal_footer)`: sticky bottom (`position: sticky; bottom: 0; background: #fff; z-index: 4; border-top: 1px solid #dee2e6; border-bottom: 1px solid #dee2e6;`).
  - `.id_statusbar_title`: judul dokumen ("New" / nomor referensi) rata tengah di antara tombol aksi dan pipeline status.
- `addons/id_ui_form/static/src/form/form_patch.js`:
  - Relokasi judul form `.oe_title` secara otomatis ke dalam `.o_form_statusbar` pada siklus `onMounted` dan `onPatched`.
- Log: `agent-log/claude-design.log`.

**Diverifikasi (bagaimana):**
- Verifikasi visual Playwright di Chromium: form luas penuh, footer total sticky saat scroll, statusbar title di tengah, systray 3 divider rapi, icon O hover halus.
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Git diff diperiksa bersih dan tidak ada file sementara yang ter-commit.

**Belum diuji:**
- Browser Firefox/Safari (hanya diuji Chromium/Edge).
- Layar mobile (akan fallback ke tampilan responsif bawaan).

## 2026-10-25 — claude-design agent (chat + sandbox) — UI refinement v4: logo O tanpa pill, FMCG sudut tegas, topbar rata tengah, divider systray
**Berubah:** `id_ui_shell`:
- Logo O: background pill dihilangkan. Saat terbuka hanya tampil "Odoo FMCG"; saat ciut tampil ikon "O" (`oi-odoo`) besar putih tanpa background yang berubah menjadi ungu Odoo (`#714B67`) dengan animasi halus dan glow tipis saat di-hover atau di-klik.
- FMCG brandbox: sudut tegas tanpa rounded (`border-radius: 0`), font tipis elegan (`font-weight: 300`, `letter-spacing: .12em`).
- Ikon menu sidebar: berubah ke warna normal Odoo saat di-hover/aktif tanpa animasi scale dan tanpa glow.
- Search box topbar: sudut rounded diperkecil (4px).
- Judul topbar: diposisikan persis di tengah (`align center`) dengan tipografi seimbang (`font-weight: 600`).
- Systray topbar: divider tipis vertikal disematkan di antara item (dari discuss hingga avatar profil).
Docs `docs/ui/id_ui_shell.md` dan `e2e/smoke_ui.py` diperbarui; log `agent-log/claude-design.log` diperbarui.

## 2026-10-25 — claude-design agent (chat + sandbox) — UI refinement v3: ikon duo-tone, wordmark Odoo FMCG, panel seksi tenang
**Berubah:** `id_ui_shell`: scrollbar sidebar/panel selalu tersembunyi (lebar menu tidak menyusut saat hover, latar item terpilih penuh); ikon aplikasi tanpa latar, duo-tone saat diam (filter SVG `feColorMatrix` inline, tanpa aset tambahan) dan warna asli Odoo saat hover/fokus/terpilih (crossfade halus, glow putih tipis); judul sidebar = wordmark resmi Odoo (`/web/static/img/odoo_logo.svg`, dirujuk bukan disalin) + kotak "FMCG"; panel seksi: menu aktif cukup tebal tanpa latar, font lebih kecil, lebar 208px; topbar: pencarian di kiri, judul di kanan. Docs `docs/ui/id_ui_shell.md` dan `e2e/smoke_ui.py` diperbarui; `id.po/pot` diperbarui.
**Diverifikasi (bagaimana):** sandbox, Odoo `f4378f29`, DB kosong: 0 failed dari 7 uji; `ruff` dan `check_manifests.py` lolos; smoke Playwright 24/24 (duo-tone, lebar menu saat hover, urutan cari/judul, menu panel aktif tebal tanpa latar, serta cek v2). Selama uji ditemukan: pipeline aset menulis ulang `url(#id)` di SCSS menjadi alamat absolut, jadi filter dipasang inline di template.
**Belum diuji:** stack OCA penuh, `docker build`/Railway, CI, browser selain Chromium, mobile.
**Butir terbuka:** wordmark Odoo berwarna bawaan (ungu/abu) di atas navy kurang kontras; varian putih `odoo_logo_dark.svg` tersedia bila disetujui. Arti "ketika sidebar dibuka" untuk ikon berwarna masih diasumsikan = hover/fokus/terpilih (**[A]**).
**Menunggu:** pemilik (unzip, commit, push); tidak ada permintaan baru ke agen lain.

## 2026-10-24 — claude-design agent (chat + sandbox) — UI refinement v2: panel seksi, topbar polos, alur Tab
**Berubah:** `id_ui_shell`: seksi aplikasi pindah dari tab navbar ke panel seksi di kiri isi (`IdSectionPanel`; seksi > sub-seksi > sub, bisa diciutkan, `Alt+P`); sidebar hanya aplikasi, item aktif persegi selebar sidebar, scrollbar disamarkan; topbar tanpa garis bawah dan pencarian menu 34px rata tengah; logo `oi-odoo` dengan glow dan gerak tipis saat hover; alur Tab: halaman dirender -> pencarian menu -> sidebar -> isi (field pertama form atau kolom cari); pengelola fokus ada di service `id_shell`. `id_ui`: hanya warna navbar klasik. Docs `docs/ui/id_ui_shell.md` dan `e2e/smoke_ui.py` diperbarui.
**Diverifikasi (bagaimana):** sandbox, Odoo `f4378f29`, DB kosong: 0 failed dari 7 uji; `ruff` dan `check_manifests.py` lolos; smoke Playwright 19/19 (fokus awal, alur Tab, panel, posisi/tinggi pencarian, tanpa garis navbar, item aktif persegi, chatter tab, hotkey); terjemahan `id.po` diperbarui.
**Belum diuji:** sama seperti v1 (stack OCA penuh, `docker build`/Railway, CI, browser selain Chromium, mobile). Tab di dalam isi belum diatur.
**Butir terbuka:** halaman Dashboards kini punya dua panel kiri (panel seksi + panel milik halaman dashboard); belum diputuskan apakah panel seksi disembunyikan untuk aplikasi itu. Titik rawan antar-versi Odoo bertambah: event `ACTION_MANAGER:UI-UPDATED`, `action.currentController`, selector fokus (`.o_form_sheet`, `.o_searchview_input`). Daftar di `docs/ui/id_ui_shell.md`.
**Menunggu:** pemilik (unzip, commit, push); tidak ada permintaan baru ke agen lain.

## 2026-10-25 — claude-dev agent (sandbox) — Review codebase main fa68c23 (PR #1–#5) + skrip snapshot instance
**Berubah:** `docs/reviews/REVIEW_2026-10-24_main-fa68c23.md` (temuan P0/P1/P2 + rencana M1a–M2 + pemilik area), `scripts/ops/odoo_snapshot.py` (diagnosis read-only via XML-RPC), `scripts/sandbox/sandbox_up.sh` (menyalin `data/` dan `scripts/` seperti Dockerfile), `pyproject.toml` (E501 diabaikan untuk `scripts/ops`), `docs/DEVELOPMENT.md` (catatan snapshot), `agent-log/claude-dev.log`. **Tidak ada perubahan pada kode agen lain.**
**Diverifikasi (bagaimana):** boot persis seperti Railway di sandbox (DB kosong, `INIT_MODULES` default): HTTP siap ±207 detik; 97 modul; 150 produk, 354 outlet; Playwright 0 galat JS; snapshot dijalankan terhadap instance itu; generator deterministik (hash seed 0/5); analisis konsistensi CSV simulasi; uji kegagalan skrip snapshot (sandi/URL/DB salah, sandi tidak bocor).
**Temuan utama:** lihat review §2. P0: `tier_id` 0/354; kota/provinsi/negara/TOP/salesman kosong; produk tidak storable; UoM hanya Units; karyawan/armada/pricelist tidak dimuat; seed gagal tetap di-mark; upgrade hanya sekali; menu FMCG = aplikasi berisi tabel referensi; dashboard menampilkan data contoh USD; admin `en_US`, `id_base` tanpa `id.po`; baris simulasi tidak cocok dengan header (8.513 baris).
**Belum diuji:** snapshot terhadap Railway (menunggu pemilik); status CI hijau hanya dari log AntiGravity; loader pada DB berisi transaksi; apa yang tampil di Railway saat ini (kemungkinan deploy lebih lama dari `main`).
**Butir terbuka:** (1) keputusan pemilik: anonimisasi nama nyata, nama EMP-001, pendekatan kemasan `product.uom`, urutan M1a/M1b/M1c; (2) hasil snapshot Railway; (3) `antigravity`: M1b (mark berbasis hash, gagal = tidak di-mark, VIES off, admin id_ID/Asia/Makassar); (4) `claude-design`: M1c (pindahkan tabel referensi ke Configuration, dashboard contoh, kolom/filter/group-by).
**Menunggu:** pemilik (jalankan snapshot, jawab keputusan); `antigravity` dan `claude-design` membaca review sebelum aksi berikutnya.
**Catatan basis:** `origin/main` maju ke `b8bcbf9` (PR #6/#7, UI v2/v3) saat review disusun; tidak mengubah temuan A–D3. Patch ini hanya menambah baris (diperiksa pada salinan bersih `b8bcbf9`).

## 2026-10-24 — antigravity (laptop/Railway) — Sinkronisasi Modul Otomatis (Fix 500 UndefinedColumn res_partner.channel_id) & Seed Data v2
**Berubah:**
- `deploy/init.sh`:
  - Menambahkan modul `id_ui`, `id_ui_shell`, `id_ui_form` ke variabel default `INIT_MODULES`.
  - Menambahkan fase `upgrade_modules_v1` (`odoo_run -i "$INIT_MODULES" -u "$INIT_MODULES" --stop-after-init`) agar saat container baru boot pada DB yang sudah ada, kolom-kolom baru (seperti `res_partner.channel_id`, `product_template.principal_id`, dll.) dan modul UI baru langsung terpasang dan tersinkronisasi di skema PostgreSQL.
  - Memperbarui mark seed data menjadi `seed_master_v2` sehingga data master 150 produk & 354 outlet dimuat ulang secara lengkap dengan kolom FMCG yang valid setelah modul terpasang.
- Log: `agent-log/anti-gravity.log`.

**Diverifikasi (bagaimana):**
- Analisis log Railway menemukan akar penyebab error HTTP 500: `psycopg2.errors.UndefinedColumn: column res_partner.channel_id does not exist` saat merender `/odoo` atau memproses cron background, akibat DB belum pernah di-upgrade dengan `-u id_base`.
- `ruff check .` lolos bersih (0 galat).
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Sintaks `deploy/init.sh` diverifikasi valid via bash check.

**Belum diuji:**
- Menunggu deployment container baru di Railway untuk memverifikasi endpoint `/odoo` dan `/web` kembali 200 OK secara visual.

## 2026-10-24 — claude-design agent (chat + sandbox) — UI redesign v1: sidebar, topbar, chatter sebagai tab
**Berubah:** addon baru `id_ui` (tema, urutan dan nama menu inti menurut glosarium, aktivasi `en_US`+`id_ID`), `id_ui_shell` (sidebar aplikasi dengan ikon bawaan Odoo, topbar: judul besar + tab seksi + cari menu + nama/role, hotkey Alt+M/Alt+B, mode sidebar/klasik per pengguna), `id_ui_form` (chatter jadi tab terakhir notebook). Docs: `docs/ui/*` (jejak kompatibilitas per addon, usulan istilah glosarium, `e2e/smoke_ui.py`). Log: `agent-log/claude-design.log`. Tidak menyentuh addon lain, CI, `init.sh`, Dockerfile.
**Diverifikasi (bagaimana):** di sandbox, Odoo `f4378f29` (sama dengan SANDBOX.md), DB kosong `-i id_base,id_ui_form --without-demo=true`: 0 failed dari 8 uji; `ruff check .` dan `check_manifests.py` lolos; `docs/ui/e2e/smoke_ui.py` (Playwright/Chromium) 10/10; terjemahan `id_ID` tampil di browser. Performa lokal (1 form, 6 muat ulang): form siap 893–998 ms (sidebar) vs 923–1030 ms (klasik), heap setelah GC 33,5 vs 35,6 MB.
**Belum diuji:** stack OCA penuh bersama addon UI; `docker build`/Railway; CI; browser selain Chromium; layar mobile (memakai NavBar bawaan); form tanpa notebook, dialog, pratinjau lampiran (fallback ke tata letak chatter bawaan, belum diuji di UI); daftar besar. Desain beranda baru (playground HTML di chat) belum dikodekan.
**Butir terbuka:**
1. Konfirmasi nama tanda tangan `claude-design agent` dan `agent-log/claude-design.log` (dipakai sesuai usulan; **[A]**).
2. `id_ui` ber-`depends` pada modul stack inti (`sale_management`, `stock`, `purchase`, `account`, `hr`, `fleet`, `hr_attendance`, `hr_holidays`, `spreadsheet_dashboard`) agar menu mereka ada saat urutan diterapkan. Memasang `id_ui*` berarti modul itu ikut terpasang; `INIT_MODULES` default belum memuatnya.
3. `postinit_v1` punya TODO mengaktifkan `id_ID`; hook `id_ui` sudah mengaktifkan `en_US`+`id_ID` dan menjadikan `id_ID` bawaan partner baru (idempoten; matikan dengan parameter `id_ui.set_default_lang=False`). Hindari menggandakan.
4. Urutan dan nama menu inti diterapkan lewat kode; setelah meng-upgrade modul inti jalankan `-u id_ui`.
5. Titik yang paling mungkin bergeser antar-versi Odoo (patch komponen internal): `WebClient`, `NavBar`/`UserMenu`, `FormRenderer.mailLayout`, `Notebook.computePages`, selector CSS navbar. Daftar di `docs/ui/id_ui_shell.md` dan `id_ui_form.md`.
6. Istilah baru usulan (Gudang & Stok, Armada, Diskusi, Dashboard) di `docs/ui/glossary-additions.md` belum masuk `GLOSSARY.md`.
**Menunggu:** pemilik repo (merge PR #4); `antigravity` (uji di Railway setelah merge).

## 2026-10-24 — antigravity (laptop/Railway) — [M1] Cabang Mandiri agen/m1-historical-simulation, Dataset Transaksi Historis Kausalitas Presisi & Cetak Biru FMCG
**Berubah:**
- **Reorganisasi Cabang:** Memindahkan seluruh pekerjaan simulasi transaksi dan master data ke cabang tersendiri `agen/m1-historical-simulation` (bercabang dari `agen/m1-master-data-models`). Cabang `agen/ui-design-v1` dikembalikan murni ke commit agen `claude-design` (`3c6fb30`).
- **Dokumentasi Cetak Biru (`docs/blueprints/`):**
  - `master_data_mapping_and_seed_plan.md`: Cetak biru hierarki master data, 15 Kab/Kota Sulut, 150 SKU, 354 outlet, 24 roster staf, 9 tipe armada kargo riil, dan 9 zona gudang WMS.
  - `pjp_and_outlet_distribution_model.md`: Pemodelan rute kunjungan PJP Senin–Sabtu, rasio call density (MT 8-10, GT 20-22, Canvass 25-30), dan loading armada H+1.
  - `historical_simulation_and_turnover_model.md`: Pemodelan simulasi kausalitas historis 1 Juli s/d 24 Oktober 2026 (Juli krisis overstok 10B net margin 0.9%, Agustus drop 23% net margin 2.5%, September konsolidasi sehat net margin 3.7%, Oktober rebound MTD 5.3B net margin 5.0%, utilisasi armada 89%).
  - `REVIEW_FEEDBACK_LOG.md`: Dokumentasi riwayat komprehensif review pengguna, feedback lapangan, dan keputusan desain arsitektur.
- **Generator & Loader Transaksi Historis:**
  - `scripts/generate_historical_simulation.py`: Menghasilkan dataset deterministik terkalibrasi presisi:
    - `data/seed/sales_orders_historical.csv`: 3.762 transaksi faktur penjualan harian riil (97 hari kerja operasional).
    - `data/seed/sales_order_lines_historical.csv`: 8.513 baris line item produk, karton, dan lot FEFO.
    - `data/seed/inbound_po_historical.csv` & `inbound_po_lines_historical.csv`: 11 Inbound PO Kontainer Bitung & jadwal AP.
    - `data/seed/opex_vendor_bills.csv`: 20 Vendor Bills beban operasional bulanan.
    - `data/seed/daily_logistics_metrics.csv`: 97 hari metrik okupansi gudang dan utilisasi 9 armada.
    - `data/seed/historical_simulation_summary.json`: Ringkasan finansial terkalibrasi (Omset Rp 18.995 BIO, OPEX Rp 1.619 BIO, Laba Bersih Rp 566.89 jt, Margin 2.98%).
  - `scripts/load_historical_simulation.py`: Loader Odoo shell idempoten untuk `account.move` (OPEX vendor bills), `purchase.order`, dan `sale.order`.

**Diverifikasi (bagaimana):**
- `python scripts/generate_historical_simulation.py` sukses menghasilkan seluruh dataset.
- `python -m ruff check .` lolos bersih (0 galat).
- `python scripts/check_manifests.py` lolos (`manifest ok: 4 addon`).
- Cabang `agen/ui-design-v1` diverifikasi ter-reset bersih pada commit `3c6fb30`.
- PR #2 dan PR #3 telah diverifikasi dan di-merge ke `main`.
- CI GitHub Actions lolos 100% HIJAU (PASS).

**Belum diuji:**
- Pemuatan seluruh data ke Odoo staging di Railway (akan terpicu otomatis saat seluruh PR di-merge ke main).

**Butir terbuka:**
- Merge PR #4 ke `main`.
- Verifikasi deployment otomatis di Railway Staging (`https://odooca-fmcg-demo.up.railway.app`).

**Menunggu:** pemilik repo (merge PR #4 di GitHub).

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
