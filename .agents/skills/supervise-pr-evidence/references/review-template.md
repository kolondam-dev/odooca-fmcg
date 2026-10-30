# Template verdict dan delegasi

## Komentar PR

Verdict PASS/HOLD/BLOCKED pada full HEAD, base ref/SHA dan waktu. Nyatakan scope. Tabel finding lama CLOSED/OPEN/PARTIAL. Catat run/job/event/SHA, tes lokal dan lingkungan/batas bukti.

Setiap finding memuat severity; file:line; trigger; baseline→mutasi→entrypoint produksi; expected/actual; tingkat fixture/mock/ORM/PostgreSQL/browser/device; dampak; acceptance perbaikan, negative case, rollback/baseline, positive path dan CI yang perlu diulang.

Tutup dengan kondisi draft/behind/conflict/required checks, izin merge/deploy terpisah, dan pelaksana langkah berikutnya. Hindari “mungkin/perlu dicek” sebagai satu-satunya dasar bug.

## Brief implementer

Berikan repo/branch/base/expected HEAD, review comment, scope dan data beku. Tetapkan acceptance per finding, bukti yang harus disertakan dan otorisasi pemilik yang sudah ada. Nyatakan capability blocker nyata. Minta HEAD/diff/commands/results/run/job/gap final; jangan memicu commit dokumentasi hanya untuk polling status.

## Final pemilik

PR#N pada SHA: VERDICT. Dua–tiga bukti/finding utama, tautan review dan tindakan berikutnya. Klaim merged ke BASE pada MERGE_SHA hanya setelah konfirmasi server; klaim deploy/acceptance hanya setelah runtime terbukti.

## Estafet

Sertakan waktu/main SHA, sumber hidup, aktor/akses, domain, topology PR, environment/service/database, otorisasi terbaru, finding per HEAD, batas tooling dan tiga langkah pertama. Tandai fakta snapshot/asumsi/belum diuji; tanpa credential/session/QR/OTP.
