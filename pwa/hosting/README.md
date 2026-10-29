# Hosting PWA dan Railway

PWA terkompilasi adalah aset statis; tidak memerlukan proses Odoo kedua, database
baru, volume, atau worker bisnis. Paket ini memakai HTTP server kecil Node.js 24
(tanpa dependency runtime npm) untuk menyajikan aset. Server bukan API bisnis.

## Topologi yang disarankan

Tambahkan **satu service `field-pwa` dalam project Railway yang sama** dengan Odoo
serta Postgres. Lifecycle/build frontend terpisah dari Odoo. Perangkat mengunduh
shell dari `/field/`, lalu menjalankan UI, draft dan outbox di browser.

Saat API siap, gunakan origin PWA yang sama untuk `/api/v1/*`, diteruskan oleh
gateway ke Odoo melalui private network. Saat ini server sengaja mengembalikan
503 untuk `/api/*`; proxy/auth belum diimplementasi. Jangan mengaktifkan HTTP
adapter melalui URL lintas origin tanpa desain cookie, CSRF, CORS dan session.

Alternatif tanpa service tambahan: reverse proxy yang sudah ada menyajikan
`/field/` dari static build dan meneruskan route Odoo. Ini menghemat satu runtime,
tetapi membutuhkan perubahan deploy/gateway existing milik agent deploy. Paket
ini tidak mengubah deploy Odoo. Hosting statis eksternal juga memungkinkan, dengan
keputusan origin API/auth yang sama. Biaya aktual mengikuti pemakaian provider.

## Konfigurasi Railway (disiapkan, belum dideploy)

1. Service baru dari repository yang sama. **Root Directory `/pwa`**, configuration
   file **`/pwa/railway.toml`** secara eksplisit (path config relatif root repo,
   bukan Root Directory). Docker build context
   wajib folder `pwa`, bukan root repo (root mempunyai Dockerfile Odoo).
2. Dockerfile `Dockerfile` dalam root service. `PORT` dibaca saat runtime; default
   8080. Healthcheck `/healthz`. Public domain melalui HTTPS Railway.
3. Default build argument `PWA_BUILD_MODE=live`: shell terkunci, tanpa fixture.
   Untuk preview simulasi, set variable/build argument `PWA_BUILD_MODE=demo` secara
   eksplisit, lalu buka `https://<domain>/field/`. Banner simulasi tetap tampil.
   Jangan menganggap nama service/environment production membuka fitur live.
4. Tidak perlu database/volume atau kredensial Odoo. Jangan salin secret ke build
   argument atau variable Vite. Build arg PWA_BUILD_MODE hanya memilih mode publik.
5. Ikuti kebijakan repo: auto-deploy dimatikan, deploy manual oleh pemilik/agent
   deploy setelah review. Tidak ada service Railway yang dibuat oleh perubahan ini.

Konfigurasi root/config path perlu diperiksa di dashboard saat setup pertama.
Rujukan resmi: https://docs.railway.com/guides/monorepo,
https://docs.railway.com/guides/react,
https://docs.railway.com/builds/dockerfiles dan
https://docs.railway.com/builds/build-configuration.

## Verifikasi lokal dan CI

```bash
cd pwa
npm run build
npm start
# http://localhost:8080/field/ (locked live)
# terminal lain:
npm run test:hosting

# Preview simulasi lokal:
npm run build:demo
PWA_DIST=dist/demo PORT=8080 npm start

# Container dari ROOT repo:
docker build -t fmcg-pwa ./pwa
docker run --rm -p 8080:8080 fmcg-pwa
# Simulasi eksplisit:
docker build --build-arg PWA_BUILD_MODE=demo -t fmcg-pwa-demo ./pwa
```

HTML, manifest dan service worker memakai `no-store`; aset hashed di `/field/assets/`
memakai cache immutable. SW hanya scope `/field/`. API tidak pernah mendapat HTML
fallback. GET/HEAD saja, file tersembunyi/traversal/missing assets ditolak. Browser
suite menjalankan server hosting yang sama, bukan server Vite preview. Container
build dan smoke health/static/API masuk gate CI terpisah `pwa-container`.

Healthcheck hanya membuktikan proses server hidup; bukan backend, login atau
kesiapan operasional. Image tag Node mengikuti patch upstream dan belum dikunci
ke digest. HTTPS diterminasi Railway; server lokal HTTP hanya untuk pengembangan.
