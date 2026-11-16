# Harness UI live lokal untuk Odoo dan PWA

Harness ini menjalankan Chromium/Playwright **secara lokal atau on-demand oleh
agen**, bukan sebagai GitHub Actions workflow. Tujuannya adalah menyediakan
browser session dan bukti UI yang dapat dipakai ulang untuk Odoo backend/web,
dashboard, dan PWA pada environment yang secara eksplisit dipilih operator.

## Batas keamanan

- Gunakan akun TEST dengan hak minimum/read-only untuk production demo.
- Harness bawaan hanya melakukan login, navigasi GET/read, assertion, dan
  screenshot. Skenario yang menulis data wajib memanggil `requireWriteOptIn()`
  dan hanya berjalan bila `LIVE_UI_ALLOW_WRITE=YES` diberikan secara eksplisit.
- File `pwa/.env.live-ui.local`, cookie storage state, screenshot, HTML report,
  dan trace diabaikan Git. Jangan unggah artifact mentah karena screenshot,
  cookie, request, atau data bisnis dapat bersifat sensitif.
- `LIVE_UI_TRACE` default `NO`; aktifkan hanya untuk diagnosis lokal dan hapus
  trace setelah selesai. Jangan mencetak password/token pada log atau source.
- Harness tidak memberikan akses dengan sendirinya. Setiap mesin/agen tetap
  memerlukan URL dan kredensial yang disediakan melalui environment lokal.
- Bukti browser tidak mengotorisasi merge, deployment, atau mutasi data.

## Instalasi satu kali

Node 24 dibutuhkan sesuai `pwa/package.json`.

```bash
cd pwa
npm ci
npm run live:ui:install
cp .env.live-ui.example .env.live-ui.local
```

Di PowerShell, salin konfigurasi dengan:

```powershell
Copy-Item .env.live-ui.example .env.live-ui.local
```

Isi `.env.live-ui.local` tanpa menempelkan nilainya ke chat, commit, atau log:

```dotenv
LIVE_UI_ODOO_URL=https://<gateway-atau-odoo>
LIVE_UI_PWA_URL=https://<gateway>/field/
ODOO_DEMO_LOGIN=<akun-test-read-only>
ODOO_DEMO_PASSWORD=<password-lokal>
LIVE_UI_ALLOW_WRITE=NO
```

Gunakan URL gateway yang sama untuk Odoo dan PWA bila session cookie memang
dirancang satu origin. `ODOO_DEMO_DB` bersifat opsional. Chromium bawaan
Playwright dipakai secara default; `LIVE_UI_CHROMIUM_EXECUTABLE` dapat menunjuk
Chrome/Chromium yang sudah terpasang.

## Menjalankan

```bash
cd pwa
npm run live:ui
npm run live:ui -- --project=live-desktop
npm run live:ui -- --project=live-phone
npm run live:ui -- --headed
npm run live:ui:report
```

Probe publik tanpa password tersedia untuk mengecek HTTP/login page:

```dotenv
LIVE_UI_PUBLIC_ONLY=YES
```

Hasil lokal berada di `pwa/test-results/live-ui/` dan
`pwa/playwright-report/live-ui/`. Default satu worker, tanpa retry, tanpa video,
dan tanpa trace agar beban serta paparan data production tetap minimum.

## Bukti route dashboard atau halaman tertentu

Salin `live-ui.routes.example.json` ke lokasi ignored lalu isi URL relatif dan
teks oracle yang nyata:

```bash
mkdir -p tests/live-local
cp live-ui.routes.example.json tests/live-local/routes.json
```

```dotenv
LIVE_UI_ROUTE_FILE=tests/live-local/routes.json
```

Setiap route menghasilkan screenshot untuk desktop dan phone. Direct route
serta `expectText` harus ditentukan dari deployment yang diuji; screenshot saja
tidak membuktikan angka, ACL, drilldown, atau invariant bisnis.

## Skenario khusus agen

Simpan spec sementara di `pwa/tests/live-local/*.spec.ts`; direktori ini ignored
dan otomatis ditemukan oleh `playwright.live.config.ts`. Import helper dari
`../live/helpers`. Contoh read-only:

```ts
import { expect, test } from "@playwright/test";
import { targetUrl } from "../live/helpers";

test("D1 ke D7 mempertahankan filter", async ({ page }) => {
  await page.goto(targetUrl("odoo", "/odoo/<route-D1>"));
  await expect(page.getByText("Sales Performance")).toBeVisible();
  // Tambahkan interaksi dan oracle spesifik deployment yang sedang direview.
});
```

Untuk skenario tulis, tambahkan `requireWriteOptIn()` di awal test dan catat
otorisasi, target, record fixture, serta cleanup. Flag bukan pengganti akun yang
dibatasi atau persetujuan mutasi production.

## Serah-terima bukti

Catat environment, deployment/SHA, browser, viewport, waktu WITA, akun/company
tanpa password, langkah, oracle, dan batas pengujian. Bagikan screenshot yang
sudah diperiksa/redaksi; jangan bagikan `.auth/state.json`, trace mentah, HTML
report mentah, atau `.env.live-ui.local`. Untuk acceptance perangkat/GPS/foto,
ikuti `docs/STAGING_DEVICE_ACCEPTANCE.md`; emulasi browser bukan bukti kehadiran
lapangan.
