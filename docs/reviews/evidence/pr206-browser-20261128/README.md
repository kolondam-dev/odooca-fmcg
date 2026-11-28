# PR #206 — browser acceptance PWA → Odoo, 28 November 2026 WITA

**Verdict: skenario 1 PASS; skenario 2 FAIL.** Bukti ini untuk re-review, bukan izin merge atau deploy. Foto dan koordinat browser adalah sintetis pada salinan database disposable, bukan bukti kunjungan lapangan. Tidak ada dump DB, filestore, password, cookie, atau token dalam direktori ini.

## Scope dan identitas runtime

- PR HEAD saat acceptance **sama** dengan kandidat `5c0922456e604e9679d3c3811c93ae7577d172d8`; tidak ada pergantian SHA. PWA deployment `20aff65d-8784-4ab2-938b-81c946785d92`, Odoo `a2435f2c-5182-40db-a264-daf1fcb57074`, gateway `5696f230-2446-4db6-b29e-5242922c6e93`. Konfigurasi deploy PWA/Odoo memuat SHA kandidat; Odoo runtime memverifikasi SHA dan ID environment yang sama. Ini identitas deploy acceptance, **bukan SHA commit yang menambahkan bukti ini**.
- Railway project `d61f96d8-a1f4-462d-81da-31d5acb0a554`; fork copy-on-write **`pr206-ui`**, environment `617b914f-186b-4d6d-ad34-731a4d29a3a6`, sumber `pilot` (`fe7ccc17-6418-4e03-a295-5bd17acb7555`). Sebelum transaksi, runtime Odoo melaporkan DB `pr110_rehearsal_20261127`, host `postgres.railway.internal`, environment ID fork, dan nol picking/command target. Gateway fork `/field/` dan `/web/login` HTTP 200. Tidak ada transaksi di pilot.
- Driver uji `driver-01` (user 40), assignment Odoo 486 tanggal `2026-11-28` WITA; trip `TRIP-ACC-20261128-01`. Kedua DO native/picking `assigned`: `WH/OUT/06409` → outlet 8 (60 + 160 unit) dan `WH/OUT/06410` → outlet 9 (90 + 320 unit). Disiapkan lewat Odoo ORM **hanya pada fork**.

## Bukti per skenario

| Skenario | Verdict | Observasi |
| --- | --- | --- |
| POD DO pertama lalu klik **Akhiri trip** | **PASS** | Kedua DO muncul, dua evidence upload HTTP 201, POD `WH/OUT/06409` diterima HTTP 200, `POD-3038c01a`, UUID `3038c01a-433c-4c8f-9a5d-95c63abc61be`. UI: `Trip belum lengkap. DO WH/OUT/06410 masih menunggu POD.` Tidak ada request closing, trip `Belum ditutup`. |
| Konteks browser baru, login dan sinkronisasi | **FAIL pada pemulihan receipt** | Snapshot HTTP 200 memuat pasangan `WH/OUT/06409`–8 dan `WH/OUT/06410`–9, tetapi `accepted_delivery_pods: {}`. Expected: DO pertama selesai, DO kedua menunggu, **1/2**, trip terbuka. Actual: DO pertama `Berikutnya`, kedua `Belum`, **0/2**, trip masih terbuka. Screenshot sukses 1/2 tidak ada karena tidak pernah terjadi. Tidak ada POD kedua atau closing final. |

Artefak: [dua DO di trip](01-two-native-do.png), [penolakan UI](02-premature-closing-ui.png), [progres 0/2 pada konteks browser baru](failure-new-context-0-of-2.png), [pasangan DO di konteks baru](failure-new-context.png), [observasi browser dan HTTP](browser-observations.log), [sinkronisasi ulang read-only](read-only-progress-observations.log). Log dipilih dari output lokal dan **bukan** HAR lengkap; tidak berisi kredensial.

## Audit Odoo read-only dan diagnosis

ORM pada fork, user driver dan bahasa `id_ID`, menghasilkan:

```text
assignment=486 business_date=2026-11-28 user_id=40 lang=id_ID
command id=1 type=delivery.pod.submit status=accepted
client_uuid=3038c01a-433c-4c8f-9a5d-95c63abc61be
source.id=WH/OUT/06409 create_date=2026-11-28 02:19:57.408143 UTC
driver commands that day=1; accepted PODs=1; closing commands=0
pickings: WH/OUT/06409 assigned outlet=8; WH/OUT/06410 assigned outlet=9
source == driver-language manifest: False
only differing key: source.site.demo_unrestricted=True (absent in manifest)
source without that key == driver-language manifest: True
_accepted_delivery_pods(...) == {}
```

`pwa/src/data/mock.ts` menambahkan `site.demo_unrestricted` ke manifest lokal authenticated-demo. `addons/id_mobile_api/models/mobile_workday.py` mencocokkan `source == task` untuk mengembalikan POD accepted pada snapshot. Karena perbandingan seluruh dict gagal, receipt accepted tidak masuk `accepted_delivery_pods`. Pemeriksaan shell Odoo dengan bahasa bawaan `en_US` juga mendapati unit terjemahan `Unit` versus `Units` dan hash `version` berbeda; **setelah konteks disamakan ke bahasa driver `id_ID`**, hanya flag demo tadi yang berbeda. Jangan menyimpulkan flag bisa dihapus dari kontrak tanpa review keamanan/produk.

**Dampak test: TAMBAH.** Risiko: receipt POD yang sah tersimpan di server tetapi tidak memulihkan status setelah sesi baru. Counterexample: manifest dari authenticated-demo PWA dengan flag lokasi lokal, satu POD accepted, kedua belum POD, lalu login/snapshot baru mengembalikan 0/2. Acceptance: regresi lintas adapter PWA–snapshot Odoo–browser baru menghasilkan 1/2 tanpa melonggarkan validasi source yang tidak berkaitan; trip tetap terbuka, tidak ada closing prematur. Level: integrasi Odoo/PWA + browser runtime disposable; path trigger `pwa/**` dan `addons/id_mobile_api/**` mengikuti `.ci/test-impact.yml`. Tes gudang, laporan, dan CI tidak diulang dalam acceptance ini.

**Cleanup:** atas permintaan pemilik, fork belum dilepas supaya bisa ditinjau ulang; pemeriksaan akhir menunjukkan pilot empat layanan `SUCCESS` dan dua volume `live`. **Perhatian:** TTL fork saat dibuat berakhir `2026-11-28T06:06:12.861Z` (**13:06:12 WITA**). Tanpa perpanjangan/penghapusan TTL, fork dapat terhapus otomatis sebelum approval dan merge. Bukti pada commit tetap tersedia walaupun fork berakhir.
