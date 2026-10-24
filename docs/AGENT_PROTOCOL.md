# AGENT_PROTOCOL — kolaborasi multi-agen

## 1. Agen dan peran
| Agen | Tanda tangan commit | Log | Tempat bekerja | Area utama **[A]** |
|---|---|---|---|---|
| `claude-dev` | `claude-dev agent` | `agent-log/claude-dev.log` | chat claude.ai + sandbox (Odoo penuh, tanpa kredensial git) | addon `id_*`, seed/verify, docs, skrip, CI; menyerahkan **patch zip** |
| `antigravity` | `antigravity-agent` | `agent-log/anti-gravity.log` | laptop pemilik + Railway CLI (tanpa Docker lokal) | Dockerfile, deploy, Railway, log build/deploy, commit/PR/push |
| `claude-design` | `claude-design agent` **[A: nama belum dikonfirmasi pemilik]** | `agent-log/claude-design.log` | Claude khusus desain | desain antarmuka/PWA (UI, aset) |
Pemilik (`kolondam-dev`) menulis semua commit dan me-merge PR. Karena itu **tanda tangan di pesan commit adalah satu-satunya penanda mesin-terbaca** siapa agen di balik commit; `whats_new.sh` bergantung padanya.

## 2. Sebelum aksi (wajib)
1. `bash scripts/agent/whats_new.sh <agen>` — fetch semua cabang; acuan = commit terakhir bertanda tangan agen Anda (bila belum ada: commit akar); daftar commit sejak acuan di semua cabang; berkas berubah; **entri baru `agent-log/*.log`**; peringatan bila ada cabang di depan `main`.
2. Baca `docs/HANDOFF.md` (entri teratas) dan, bila menyentuh area agen lain, log agen itu secara penuh.
3. Selaraskan basis kerja dengan ujung cabang yang relevan. Jangan membangun di atas salinan lama.

## 3. Sesudah aksi (wajib)
1. `bash scripts/agent/log_entry.sh <agen> INFO "<judul>" "<butir>" ...` — menambah entri ber-timestamp WIB dan mencetak tanda tangan commit.
2. Tambah entri `docs/HANDOFF.md` (berubah / diverifikasi / belum diuji / butir terbuka / menunggu).
3. Commit **bersama** perubahan log, dengan tanda tangan di baris terakhir.

## 4. Format pesan commit
```
<tipe>(<ruang-lingkup>): <ringkasan imperatif, ≤ 72 karakter>

<butir perubahan dan hasil verifikasi; apa yang belum diuji>

task managed by <agen> at <ISO8601 +07:00>
```
Contoh: `task managed by claude-dev agent at 2026-10-24T14:05:11+07:00`. Baris tanda tangan **huruf kecil, baris paling akhir**, tanpa teks sesudahnya.

## 5. Format log (`agent-log/<agen>.log`, append-only)
```
[2026-10-24T13:35:40+07:00] [INFO] Judul singkat
- butir 1
- butir 2
- Task managed by <agen> at 2026-10-24T13:35:40+07:00
```
Level: `INFO`, `WARN`, `ERROR`. Satu entri per aksi bermakna (bukan per perintah). **Jangan** menulis rahasia, token, kata sandi, atau ID yang memberi akses. Jangan mengubah entri lama; koreksi = entri baru. (Entri retroaktif ditandai di judul.)

## 6. Cabang dan merge
`main` layak deploy; perubahan lewat cabang `agen/<topik>` dan PR yang di-merge pemilik. Cabang yang berada di depan `main` ditandai oleh `whats_new.sh`. Auto-deploy memakai `main`; **perbaikan yang belum di-merge tidak ikut build**.

## 7. Konflik dan kepemilikan berkas
- Boleh mengubah berkas di area agen lain bila perlu, tetapi **wajib membaca log agen itu lebih dulu**, mencatat di log sendiri, dan menulis `Menunggu: <agen>` di HANDOFF bila butuh tindak lanjut.
- Dua agen menyentuh berkas yang sama: yang kedua rebase di atas commit pertama, membaca log-nya, dan mencatat penyelesaian.
- `docs/HANDOFF.md`: entri baru di atas, per agen; jangan menulis ulang entri agen lain.

## 8. Batasan yang jujur
Tanda tangan tidak diverifikasi otomatis; pemilik menulis commit sehingga tidak ada bukti kriptografis tentang agen. **Butir terbuka:** job CI yang menolak commit non-merge tanpa tanda tangan (belum dibuat), dan konfirmasi nama tanda tangan `claude-design`.
