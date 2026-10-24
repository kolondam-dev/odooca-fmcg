# Odoo 19 CE untuk Distributor FMCG (Manado) — Demo/PoC

Demo Odoo 19 Community (+ OCA 19.0) untuk distributor FMCG multi-prinsipal di Manado, Sulawesi Utara. **Seluruh data fiktif.** Lisensi **LGPL-3**.

## Status jujur (M0, diverifikasi di sandbox 2026-10-23)
| Bagian | Status |
|---|---|
| Dokumen (SCOPE v0.6, Playbook v0.4, Glosarium, DEVELOPMENT, SANDBOX) | Ada, draf |
| `oca.lock` (26 repo OCA 19.0 di-pin ke SHA) | **Diuji**: diambil semua, dependensi pip terpasang, `pip check` bersih |
| Odoo 19 (commit `f4378f29`) + 65 modul core/OCA | **Diuji**: 165 modul terinstal, 0 ERROR; 6 modul OCA tidak installable (SCOPE §5.3) |
| `addons/id_base` | **Diuji**: terinstal, uji lolos (0 failed) |
| `deploy/init.sh` | **Diuji di sandbox tanpa Docker**: DB kosong, restart, reset+restore, token lama, reset+build (lihat `docs/SANDBOX.md`) |
| `Dockerfile`, `docker-compose.yml` | **Belum diuji** (tidak ada Docker di sandbox) |
| `.github/workflows/ci.yml` | **Belum dijalankan** |
| Railway | **Belum diuji** |
| Seed, PWA, integrasi, O2C, HRIS, dashboard, Coretax | Belum dibangun (M1–M10, `docs/SCOPE.md` §12) |

## Mulai (lokal, setelah Docker tersedia)
```bash
cp .env.example .env      # ubah kata sandi
docker compose up --build # Odoo di http://localhost:8069 (login: admin / ADMIN_LOGIN_PASSWORD)
```

## Peta
`addons/` addon `id_*` · `oca.lock` pin OCA · `scripts/` alat · `deploy/` init & seed · `docs/` dokumen.
Mulai membaca: `docs/SCOPE.md`, lalu `docs/DEVELOPMENT.md` dan `docs/HANDOFF.md`.
