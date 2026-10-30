---
name: supervise-pr-evidence
description: Supervise pull requests and multi-agent work through exact-SHA CI verification, production-source review, executable counterexamples, actionable acceptance criteria, and separate merge/deployment authorization. Use for agent reports, re-reviews, runtime/data audits, PASS/HOLD verdicts, merge readiness, deployment readiness, or taking over a repository supervisor role. Covers Odoo, PWA sessions/media, browser geometry, accounting/stock oracles and infrastructure evidence.
---

# Supervisor PR berbasis bukti

## Mulai dari scope aktual

1. Tentukan repository, nomor PR, base, full HEAD SHA, draft/state dan tujuan bisnis. Jangan menganggap PR turunan menuju main.
2. Baca AGENTS.md, DEVELOPMENT, HANDOFF, kontrak domain, log relevan dan review terakhir. Bedakan keputusan pemilik terbaru dari sejarah. Untuk odooca-fmcg, baca [project-entry.md](references/project-entry.md).
3. Ambil diff, commit history, perubahan sesudah verdict, workflow dan ruleset melalui connector. Jalankan pengujian dalam checkout/worktree terisolasi; jangan mengubah branch implementer saat review.
4. Nyatakan apa yang sedang diaudit, asumsi dan batas bukti. Gunakan bahasa pengguna.

## Bangun matriks bukti

Catat klaim → invariant bisnis → source/line → tes aktual → hasil → batas pembuktian.

- Kaitkan workflow/job dengan SHA dan event. Bedakan HEAD, synthetic PR merge dan main. Jika memakai hasil synthetic merge, buktikan Git tree identik atau audit diff integrasinya.
- Hitung job PR unik; jangan menambahkan duplikat push. Periksa conclusion, skipped jobs, log tes, artifact dan failure diagnostics, bukan hanya badge hijau.
- Pisahkan unit/mock, browser HTTP fixture, native ORM/HttpCase, real PostgreSQL, representative slice, full dataset, replay, persistent-baseline upgrade, staging nyata dan perangkat. Jangan mengangkat satu tingkat menjadi bukti tingkat lain.
- Buktikan baseline benar dahulu; mutasi harus ditolak assertion yang relevan, rollback, lalu baseline kembali lulus. Zero-drift Run2 tidak membuktikan Run1 benar.
- Jangan menyatakan siap deploy dari healthz200/SUCCESS saja. Buktikan image/build mode, routing, auth, modul/schema aktif dan smoke sesuai scope.
- Gunakan [test-techniques.md](references/test-techniques.md); jalankan tes paling menentukan dahulu, perluas bila ada perubahan atau ketidakpastian material.

## Buktikan finding

1. Telusuri entrypoint produksi hingga write/read/validation boundary. Periksa no-op write, swallowed exception, guard setelah mutasi, empty filters dan identity fallback.
2. Bentuk counterexample terkecil dengan satu invariant berubah dan kontrol lain tetap. Panggil fungsi produksi asli; jangan menguji salinan algoritma.
3. Nyatakan tingkat reproduksi dengan tepat: local fixture/AST/mock bukan PostgreSQL nyata. Source observation boleh dilaporkan, tetapi bedakan dari bug yang direproduksi.
4. Untuk setiap finding, tulis trigger, expected/actual, dampak, file:line, prosedur reproduksi dan acceptance yang dapat dieksekusi. Jangan menyerahkan “perlu dicek” tanpa kriteria lulus/gagal.
5. Kaitkan severity dengan dampak: P1 untuk kerusakan/false-PASS material pada scope inti; P2 untuk kesalahan terbatas; P3 pemeliharaan. Jangan menaikkan formatting menjadi blocker utama.
6. Gunakan HOLD/BLOCKED bila bukti penting tidak tersedia; jangan mengubah kekurangan akses menjadi tuduhan bug. Jangan menambah temuan demi mempertahankan loop review.

## Re-review dan verdict

- Klasifikasikan finding lama CLOSED / OPEN / PARTIAL beserta bukti. Audit fix dan regresinya; jangan memindahkan acceptance diam-diam.
- Pertahankan invariant ketika tes gagal. Perbaiki fixture/parser/clock/model pengukuran yang salah; jangan melonggarkan assertion agar hijau.
- Beri PASS hanya untuk scope terbukti; pisahkan gap di luar scope. Beri HOLD untuk bug dalam scope atau bukti wajib belum beres.
- Terbitkan komentar/review GitHub bila alur review repository telah diotorisasi pengguna. Jika belum, siapkan draf. Jangan mengirim pesan kepada orang/layanan lain tanpa izin.
- Gunakan [review-template.md](references/review-template.md). Final ke pemilik memuat verdict, SHA, bukti/finding utama, tautan review dan status merge/deploy.

## Merge dan deploy secara terpisah

1. Review saja tidak mengotorisasi merge. Ikuti izin untuk PR/scope yang tepat; jangan meminta ulang izin yang sudah diberikan.
2. Sebelum merge, baca ulang HEAD/base, draft, strict up-to-date, required checks dan unresolved threads. Gunakan expected_head_sha; jika HEAD berubah, audit delta dan CI baru. Jangan bypass ruleset.
3. Selesaikan konflik hanya pada branch yang berwenang, pertahankan kedua riwayat log/HANDOFF, lalu ulang CI integrasi. Mergeable mekanis bukan kelayakan merge.
4. Verifikasi hasil server: merge SHA dan base tujuan. Jangan mengklaim main jika base adalah branch integrasi.
5. Deploy hanya pada target berotorisasi. Verifikasi project/environment/service/database, sumber SHA/image, konfigurasi dan pemulihan bila mengubah data. Nama production bukan izin reset.
6. Pisahkan kode merged, image dibangun, modul terpasang, provisioning/migrasi dieksekusi dan acceptance pengguna. Laporkan masing-masing sesuai bukti.
7. Bila connector tidak cukup, jelaskan kemampuan yang hilang; pakai fallback yang diizinkan. Jangan mengekstrak token/cookie, melewati penolakan keamanan atau mengulang login jika blocker sebenarnya shell/backup. Serahkan aksi operator yang memang tidak dapat dijalankan dengan akses tersedia.

## Koordinasi dan estafet

- Tetapkan pelaksana berdasarkan kompetensi dan akses, bukan nama agent. Nyatakan siapa mengeksekusi aksi dan bukti yang harus dikembalikan agar tidak saling menunggu.
- Ungkapkan bila Anda mengimplementasikan fix; jangan menyebut pemeriksaan sendiri sebagai review independen. Minta review independen untuk perubahan material.
- Jangan mengatribusikan agent hanya dari akun GitHub bersama; gunakan signature/log dengan batas identitas yang jujur.
- Catat waktu, SHA/run/job, finding, otorisasi, gap dan langkah berikutnya. Status cepat berubah wajib ditandai snapshot dan diverifikasi ulang.
- Pertahankan catatan append-only; jangan menyimpan credential, dump, filestore, token atau tautan QR/OTP.
- Saat terblock, hasilkan prosedur operator konkret dengan target dan acceptance, bukan sekadar “menunggu agent/admin”.
