# FMCG Lapangan — frontend-first

Implementasi awal client PWA untuk repo Odoo FMCG. Tidak mengubah backend, loader,
seed atau deployment. Seluruh fixture independen dari data/seed dan hanya masuk
build demo. Rujukan utama: [plan mobile](../docs/blueprints/mobile_api_and_pwa_plan.md).

## Menjalankan

Node.js 24 dan npm dengan package-lock committed:

```bash
cd pwa
npm ci
npm run dev
```

Buka `http://127.0.0.1:5173/field/`. Dev server adalah simulasi eksplisit.
Service worker/offline reload diuji pada build preview, bukan dev server:

```bash
npm run build:demo
npm run build
npm run preview -- --outDir dist/demo
```

Preview demo: `http://127.0.0.1:4173/field/`.
`npm run build` menghasilkan **dist/live**, yang saat ini terkunci sampai backend
resmi diterima. Tidak ada query parameter atau API-error fallback yang mengaktifkan
simulator pada live. Belum ada publikasi web, integrasi auth nyata atau deploy.

## Yang tersedia dan batasnya

| Area | Implementasi saat ini |
|---|---|
| Shell/UI | Preact + TypeScript + Vite, bottom nav responsif, Phosphor duotone SVG subset, Inter WOFF2 lokal, navy/blue tokens, reduced motion, haptic opsional |
| Persona | Sales, driver, canvasser dengan role bertumpuk; selector hanya demo, bukan login/auth/device binding |
| Sales | Outlet contoh, pemilihan principal, draft quantity yang dipulihkan, estimasi total, validasi satu principal, request extra call |
| Delivery | Manifest contoh, form POD dan capture bukti; official submit ditahan karena API evidence/map belum tersedia |
| Personal HRIS | Form absensi/cuti, akun sendiri per persona, slip ditandai belum terintegrasi; tidak meng-cache slip personal |
| Biaya | Draft request kategori BBM/makan/nginap/darurat, per-trip/per-DO, odometer, narasi tier Supervisor/BM; tidak mencairkan uang atau menghitung limit resmi |
| Outbox | IndexedDB per identity, command UUID tetap, single-engine flush lock, retry/backoff, otomatis saat online/resume, 15s timer saat aktif, terminal 4xx/401 tertahan |
| Evidence | Foto terkompresi <=1 MB, koordinat/accuracy dan waktu lokal, Blob tersimpan per user, status map_pending; tidak mengklaim kamera asli/geofence sah |
| API draft | Zod DTO + OpenAPI generated, HTTP adapter tanpa fallback; belum diaktifkan sebagai aplikasi live |
| Offline shell | Manifest, icon SVG/PNG, asset precache hanya /field; tidak cache API; app update menunggu lifecycle service worker biasa tanpa memaksa reload input |

Ini menutup fondasi dan beberapa alur client PWA-01–04, **bukan seluruh roadmap**.
English/i18n penuh, tracking perjalanan, geofence workflow lengkap, sesi pagi nyata,
form realisasi/settlement rinci, server notification/approval, snapshot peta, recovery
session/device, backend receipt/record aktual dan E2E production masih pekerjaan
berikutnya. Jangan menilai status accepted simulator sebagai bukti Odoo menerima SO.

## Struktur

- `src/components`: icon wrapper dan evidence capture.
- `src/domain`: kontrak, validasi client, state outbox, format/geofence preview.
- `src/storage`: partition IndexedDB untuk draft/outbox/media/receipt simulator.
- `src/data`: HTTP provider dan lazy mock adapter yang dipisah saat build.
- `src/App.tsx`: shell, layar dan form client awal.
- `contracts/openapi.json`: kontrak client draft hasil Zod, bukan endpoint yang sudah ada.
- `scripts`: export/check kontrak dan budget/build boundary.
- `tests`: unit/contract/storage tests dan browser phone/tablet.

DTO bukan salinan model ORM. Contoh HTTP adapter saat ini mengirim satu command
ke `/api/v1/sync/commands` dan menerima satu receipt. Batch/dependency, identity
mapping, secure cookie/CSRF flow dan schema final harus direview bersama backend;
frontend tidak memaksakan protokol yang belum disepakati.

## Gate CI

```bash
npm run format:check
npm run typecheck
npm run contracts:check
npm test
npm run build:demo
npm run build
npm run check:build
npx playwright install --with-deps chromium
npm run test:e2e
```

Workflow `.github/workflows/pwa.yml`:

- `pwa-quality`: reproducible npm ci, formatting, typecheck, schema drift, unit tests,
  demo/live builds, total JS gzip <=200 KiB, font <=100 KiB, scope dan fixture leakage.
- `pwa-browser`: phone/tablet, actual preview, offline reload dan reconnect, persona
  isolation, expense pending approval, missing evidence, live fail-closed, screenshot/trace.
- `pwa-gate`: always-run aggregator; gagal jika quality/browser gagal, dibatalkan atau skipped.

Tidak memakai path filter agar check wajib tidak menggantung pada PR non-PWA.
Workflow tidak merge/deploy, tidak memakai secret, dan tidak mengubah workflow Odoo.
Untuk enforcement merge, tambahkan `pwa-gate` ke required checks ruleset yang
berlaku setelah nama check muncul. Workflow hijau saja tidak membuktikan ruleset
sudah diperbarui. Perubahan ruleset tidak dilakukan dalam pekerjaan ini.

Browser fixture dipisah per context dan akun; tidak memakai password, akun Railway
atau data production. Cross-tab/server concurrency dan ACL harus diuji pada backend
aktual nanti. Browser cache/local data bisa dihapus OS/user; jangan simpan pending
berhari-hari atau menyebut browser storage sebagai backup server.

## Aset dan lisensi

Kode project mengikuti LGPL-3.0-only. Phosphor SVG: MIT; Inter: SIL OFL.
Salinan license tersedia pada `public/licenses`. Hanya glyph/ikon yang diperlukan
yang dikirim, tanpa CDN, font icon penuh, map SDK atau dependensi React untuk ikon.
Aset PNG merupakan rasterisasi icon.svg repo, bukan foto/gambar generatif.
