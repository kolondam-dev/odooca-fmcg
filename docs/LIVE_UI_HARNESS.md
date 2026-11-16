# Harness UI live remote/lokal untuk Odoo dan PWA

Harness ini menjalankan Chromium/Playwright secara remote melalui manual GitHub
Actions atau secara lokal. Workflow `Remote Live UI Proof` hanya memiliki
`workflow_dispatch`: bukan required CI dan tidak berjalan pada push, PR, atau
schedule. Tujuannya menyediakan browser session dan bukti UI reusable untuk
Odoo backend/web, dashboard, dan PWA pada target yang dipilih operator.

## Batas keamanan

- Gunakan akun TEST dengan hak minimum/read-only untuk production demo.
- Harness bawaan hanya melakukan login, navigasi GET/read, assertion, dan
  screenshot. Skenario yang menulis data wajib memanggil `requireWriteOptIn()`
  dan hanya berjalan bila `LIVE_UI_ALLOW_WRITE=YES` diberikan secara eksplisit.
- File `pwa/.env.live-ui.local`, cookie storage state, screenshot, HTML report,
  dan trace lokal diabaikan Git. Workflow remote selalu menghapus auth state
  sebelum artifact diunggah dan tidak mengaktifkan trace.
- `LIVE_UI_TRACE` default `NO`; aktifkan hanya untuk diagnosis lokal dan hapus
  trace setelah selesai. Jangan mencetak password/token pada log atau source.
- Harness tidak memberikan izin GitHub dengan sendirinya. Agen memerlukan akses
  menjalankan Actions; kredensial target tetap hanya tersedia di Environment.
- Bukti browser tidak mengotorisasi merge, deployment, atau mutasi data.

## Runner remote lintas agen

### Konfigurasi repository satu kali

Buat GitHub Environment bernama `demo-ui`, lalu isi:

| Jenis           | Nama                 | Isi                                    |
| --------------- | -------------------- | -------------------------------------- |
| Variable        | `LIVE_UI_ODOO_URL`   | URL gateway/Odoo demo                  |
| Variable        | `LIVE_UI_PWA_URL`    | URL PWA, biasanya gateway `/field/`    |
| Secret          | `ODOO_DEMO_LOGIN`    | akun TEST demo                         |
| Secret          | `ODOO_DEMO_PASSWORD` | password akun TEST                     |
| Secret opsional | `ODOO_DEMO_DB`       | nama database bila login memerlukannya |

Aktifkan required reviewer pada Environment. Workflow dispatch sendiri harus
dijalankan dari `main`; input `source_ref` menentukan branch/tag/SHA test yang
di-checkout. Job `resolve` memublikasikan exact SHA sebelum job `demo-ui`
meminta approval. Karena source branch akan mengeksekusi Playwright dengan
secret Environment, reviewer wajib memeriksa ref/purpose dan hanya menyetujui
branch agen yang dipercaya.

Secret dapat diisi melalui GitHub UI (**Settings → Environments → demo-ui**) atau
CLI interaktif berikut. Jangan memberikan nilainya sebagai argumen command,
chat, atau log:

```bash
gh secret set ODOO_DEMO_LOGIN --env demo-ui
gh secret set ODOO_DEMO_PASSWORD --env demo-ui
# Opsional:
gh secret set ODOO_DEMO_DB --env demo-ui
```

Workflow memakai satu worker, tidak mengizinkan write opt-in, tidak mencetak
nilai URL/password, menghapus `.auth`, dan menyimpan screenshot/HTML report
selama tiga hari. Repo dan datanya merupakan showcase public sesuai keputusan
pemilik; tetap dilarang menaruh credential/cookie dalam source, log, atau
artifact.

### Menjalankan dari GitHub

UI: **Actions → Remote Live UI Proof → Run workflow**. Pilih workflow ref
`main`, lalu isi `source_ref`, suite, viewport, dan purpose.

CLI/API untuk agen yang memiliki izin Actions:

```bash
gh workflow run live-ui-proof.yml --ref main \
  -f source_ref=agen/d1-d7-proof \
  -f suite=odoo \
  -f project=desktop \
  -f purpose="D1 ke D7 production demo"
```

Suite tersedia: `smoke` (Odoo+PWA), `odoo`, `pwa`, `routes`, dan
`all-readonly`. `project` menerima `desktop`, `phone`, atau `all`. Exact source
SHA, target tanpa nilainya, suite, dan batas evidence dicatat pada run summary.

Untuk suite `routes`, commit profil JSON pada branch sumber di bawah
`pwa/tests/live-profiles/`, lalu isi input, misalnya:

```text
route_file=tests/live-profiles/d1-d7.json
```

Workflow menolak absolute path, traversal `..`, dan route file di luar folder
tersebut. Spec interaksi khusus dapat ditambahkan ke `pwa/tests/live/` pada
branch agen dan diberi tag suite yang sesuai, lalu dijalankan melalui
`source_ref` tanpa merge atau deployment. Perubahan workflow tetap hanya
berasal dari workflow ref `main`.

## Runner lokal opsional

### Instalasi satu kali

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

### Menjalankan

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

Untuk lokal, salin `live-ui.routes.example.json` ke lokasi ignored lalu isi URL
relatif dan teks oracle yang nyata:

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

Untuk eksekusi lokal, simpan spec sementara di
`pwa/tests/live-local/*.spec.ts`; direktori ini ignored dan otomatis ditemukan
oleh `playwright.live.config.ts`. Untuk remote, commit spec ke `pwa/tests/live/`
pada branch sumber. Import helper dari `../live/helpers`. Contoh read-only:

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
