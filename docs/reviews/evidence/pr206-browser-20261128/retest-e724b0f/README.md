# PR #206 — retest pemulihan 1/2 pada `e724b0f`, 28 November 2026 WITA

**Verdict: PASS untuk skenario yang sebelumnya FAIL.** Retest ini hanya menjalankan ulang pemulihan progres dari konteks browser baru; penolakan **Akhiri trip** tetap memakai bukti PASS sebelumnya. Tidak ada merge atau deploy pilot.

## SHA dan environment yang benar-benar dijalankan

| Item | Nilai |
| --- | --- |
| Kode PR / PWA / Odoo | `e724b0f1a44c852dac1548643f06b2478b2d88c1` |
| Deployment PWA | `e8df512e-5c93-4924-9c1c-1fb370ee10aa` (`SUCCESS`) |
| Deployment Odoo | `6ec7cfe3-6a10-4b77-8884-45f7c5f33b66` (`SUCCESS`) |
| Gateway | `5793ab9e-a918-40ef-a757-f66b2e956674` (refresh setelah Odoo redeploy; bukan perubahan kode) |
| Fork | `pr206-ui`, environment `617b914f-186b-4d6d-ad34-731a4d29a3a6`, sumber `pilot` |
| Database Odoo | `pr110_rehearsal_20261127` pada `postgres.railway.internal`, `FMCG_STAGING_DISPOSABLE=YES` |
| Driver / assignment / trip | `driver-01` (user 40), assignment 486, `TRIP-ACC-20261128-01` |
| DO | `WH/OUT/06409` → outlet 8; `WH/OUT/06410` → outlet 9 |

Runtime Odoo melaporkan environment ID fork, `PILOT_GIT_SHA=e724b0f…`, dan DB `pr110_rehearsal_20261127` sebelum pengujian. Kedua variabel layanan juga bernilai SHA yang sama. Commit dokumentasi ini berada **di atas** `e724b0f`; isi kode aplikasi tidak berubah.

## Hasil

POD pertama yang sudah tersimpan (dibuat `2026-11-28 02:19:57 UTC`, masih hari kerja WITA yang sama) tidak dikirim ulang. Konteks browser baru memakai penyimpanan lokal kosong, login ulang sebagai driver, lalu sinkronisasi.

- Snapshot HTTP 200 mengembalikan `accepted_delivery_pods: {"WH/OUT/06409": "3038c01a-433c-4c8f-9a5d-95c63abc61be"}` — receipt yang sama dengan POD tersimpan.
- PWA menampilkan **`1/2 toko selesai`**, DO pertama **`Selesai`**, DO kedua **`Berikutnya`**, dan trip **`Belum ditutup`**.
- Tidak ada request `delivery.pod.submit` maupun closing dari uji ini (`commandRequests: []`).
- Audit Odoo: tepat satu command hari itu, `delivery.pod.submit` accepted untuk `WH/OUT/06409`; nol command closing; kedua picking tetap `assigned`.

Bukti: [daftar trip 1/2](03-new-context-progress-1-of-2-list.png), [detail DO pertama selesai dan DO kedua berikutnya](03-new-context-progress-1-of-2.png), [log observasi](retest-observations.log), [skrip verifikasi](verify-restoration.cjs).

Catatan: status absensi pada PWA ini tersimpan lokal, sehingga perangkat baru mengulang alur absensi morning (hanya attendance, tanpa command POD/closing). Audit Odoo menunjukkan tidak ada command tambahan selain satu POD tersebut.

## Dampak test untuk re-review

Perbaikan `e724b0f` menambah regresi di dua level: unit PWA (`delivery-progress`, `authenticated-provider`) dan integrasi Odoo (`test_read_api`) yang menolak source dengan `version`, `outlet_id`, atau koordinat berbeda meski flag demo diabaikan. Bukti runtime ini melengkapi tes tersebut. **Tidak ada perubahan test tambahan yang diminta** dari retest ini; keputusan HOLD dicabut atau tidak tetap milik reviewer.

## Cleanup

Fork masih aktif atas permintaan pemilik, dengan TTL tercatat hingga 13:06 WITA 28 November 2026. Pilot tidak disentuh: empat layanan `SUCCESS`, dua volume `live`. Bukti pada commit tetap tersedia setelah fork berakhir.
