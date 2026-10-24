# AGENTS.md
**Konteks:** Odoo 19 CE + OCA 19.0 untuk demo distributor FMCG Manado; data fiktif; dokumen berbahasa Indonesia.
**Agen:** `claude-dev` (chat + sandbox: kode, docs, verifikasi) · `antigravity` (laptop pemilik + Railway: deploy) · `claude-design` (desain). Penulis commit selalu pemilik; identitas agen = **tanda tangan commit + `agent-log/`**. Aturan lengkap: `docs/AGENT_PROTOCOL.md`.

1. **SEBELUM aksi:** `bash scripts/agent/whats_new.sh <agen>` (fetch, commit sejak commit terakhir Anda, entri baru `agent-log/*.log`). Lalu baca `docs/HANDOFF.md` (entri teratas) dan `docs/DEVELOPMENT.md`.
2. **SESUDAH aksi:** tambah entri ke `agent-log/<agen>.log` (`bash scripts/agent/log_entry.sh <agen> INFO "<judul>" "<butir>"...`) dan entri `docs/HANDOFF.md`.
3. **Commit:** pesan deskriptif; **baris terakhir wajib** `task managed by <agen> at <ISO8601 +07:00>` (claude-dev: `task managed by claude-dev agent at ...`).
4. **Cabang:** `main` layak deploy; kerja di `agen/<topik>` lewat PR. Bangun di atas ujung cabang terbaru, bukan salinan lama.
5. **Larangan:** rahasia/token/kata sandi (juga di log); dump DB atau filestore di git (pakai Release asset); mengedit data server langsung; fakta pajak tanpa sumber resmi bertanggal; mengubah/menghapus entri log agen lain (log append-only).
6. **Penandaan:** [F] fakta bersumber · [A] asumsi · [BU] belum diuji/diverifikasi.
7. **Verifikasi sebelum PR:** `ruff check . && python scripts/check_manifests.py`; CI hijau; modul baru terinstal di DB kosong.
8. Addon baru berawalan `id_`, `license: LGPL-3`, versi `19.0.x`; string sumber English, terjemahan di `i18n/id.po`; istilah FMCG mengikuti `docs/GLOSSARY.md`.
