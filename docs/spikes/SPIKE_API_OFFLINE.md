# Spike M0 — API untuk PWA dan sinkron offline
**Time-box:** 2 hari kerja. **Keluaran:** keputusan tertulis + prototipe terbuang (jangan dipakai sebagai kode produksi).

## Pertanyaan
1. **Terjawab sebagian (2026-10-23):** `fastapi` v19.0.1.1.1 terinstal bersih di Odoo 19; `base_rest`, `base_rest_auth_api_key`, `pydantic`, `rest_log` **tidak installable**; tidak ada modul otentikasi `fastapi_auth_*`. Yang tersisa: apakah `fastapi` stabil dan nyaman dipakai untuk endpoint kita (router, dependensi, pydantic bawaan fastapi), atau controller HTTP sendiri di `id_api` lebih sederhana?
2. Bagaimana memetakan token/API key ke user atau karyawan tertentu (bukan satu akun sudo bersama), dan menegakkan izin per app role di server?
3. Idempotency: bagaimana klien mengirim `client_uuid` dan server menolak duplikat saat sinkron ulang?
4. Pull master incremental berdasar `write_date`: bagaimana menangani rekaman yang dihapus/dinonaktifkan?
5. Apakah antrean outbox (IndexedDB) + service worker Preact/Vite cukup untuk: buat order offline → sinkron → status *diterima / butuh approval / ditolak*?
6. Foto bertimestamp dan geotag dari browser: berapa ukuran unggahan, kompresi di klien, dan fallback saat izin lokasi ditolak?

## Eksperimen
- E1: dengan `fastapi` yang sudah terinstal, buat endpoint `GET /api/v1/ping` dan `POST /api/v1/echo`; otentikasi token per pengguna buatan sendiri (`auth_api_key` ada di server-auth sebagai pembanding).
- E2: endpoint `POST /api/v1/orders` dengan `client_uuid` (buat 1 SO draf; kirim dua kali, hasilnya satu).
- E3: PWA minimal (Preact + Vite): login, tab dinamis dari `GET /api/v1/me/bootstrap`, outbox offline untuk E2, sinkron saat online.
- E4: ukur: ukuran bundle, waktu sinkron 50 order, perilaku saat koneksi putus di tengah unggah.

## Kriteria keputusan
Pilih OCA `fastapi` bila: terinstal bersih di CI, auth per pengguna jelas, dan skema (pydantic/OpenAPI) bisa dipakai klien native nanti. Bila tidak, controller sendiri dengan OpenAPI yang ditulis tangan.

## Catatan
Keterbatasan PWA (geolokasi hanya saat aplikasi aktif, deteksi mock-location, push) dicatat; evaluasi aplikasi native Android setelah proyek disetujui.
