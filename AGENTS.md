# AGENTS.md
**Konteks:** Odoo 19 CE + OCA 19.0 untuk demo distributor FMCG Manado; data fiktif; dokumen berbahasa Indonesia.

1. Baca `docs/HANDOFF.md` (entri teratas), lalu `docs/DEVELOPMENT.md`. Acuan bisnis: `docs/SCOPE.md`, `docs/PLAYBOOK_DISTRIBUTOR_FMCG.md`.
2. **Cabang:** `main` = layak deploy. Kerja di `agen/<topik>` atau `feat/<topik>`, lewat PR. Penulis commit = pemilik repo.
3. **Larangan:** rahasia/token/kata sandi; dump DB atau filestore di git (pakai Release asset); mengedit data server langsung; fakta pajak tanpa sumber resmi bertanggal.
4. **Penandaan:** [F] fakta bersumber · [A] asumsi · [BU] belum diuji/diverifikasi.
5. **Verifikasi sebelum PR:** `ruff check . && python scripts/check_manifests.py`; CI harus hijau; modul baru terinstal di DB kosong.
6. **Wajib:** tulis entri `docs/HANDOFF.md` di akhir setiap sesi (berubah / diverifikasi / belum diuji / butir terbuka / menunggu).
7. Addon baru berawalan `id_`, `license: LGPL-3`, versi `19.0.x`; string sumber English, terjemahan di `i18n/id.po`; istilah FMCG mengikuti `docs/GLOSSARY.md`.
