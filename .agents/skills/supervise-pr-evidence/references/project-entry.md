# Entry odooca-fmcg

Repo https://github.com/kolondam-dev/odooca-fmcg. Odoo19 CE+OCA19, PWA distributor FMCG demo Manado. Jangan memakai pos-inventory dari link awal yang dikoreksi.

Baca AGENTS.md, docs/AGENT_PROTOCOL.md, docs/DEVELOPMENT.md, docs/HANDOFF.md, docs/reviews/SUPERVISOR_HANDOFF.md pada ref terbaru. Jika estafet masih di PR, baca branch yang diserahkan; jangan menganggap sudah merged. Skill menyimpan metode, bukan status PR hidup.

Aktor: Franky/kolondam-dev pemilik; codex supervisor; Antigravity seed/accounting/runtime/operator bila CLI tersedia; codex-pwa PWA/API/evidence/provisioning; claude-design UI native; claude-dev fondasi sesuai log. Akses harus diverifikasi, tidak diwariskan dari nama.

Kontrak: freeze15CSV data/registers sejak fae5835. Business timezone Asia/Makassar/WITA; koordinasi/commit Asia/Jakarta/WIB. Guard accounting id_base memakai batch SO/invoice persisten, seed company config/XMLID dan native stock.move.account_move_id/AML. Jangan mengembalikan fuzzy references/reversal bypass.

Keputusan30Oktober2026: environment Railway production dipakai demo, data existing tanpa reset, company/akun TEST terpisah. Tiga aplikasi+Postgres dipertahankan. PWA build staging dalam production bukan live bisnis. Baca docs/DEMO_ENVIRONMENT_SCOPE_DECISION.md dan catatan deployment; larangan production lama sudah digantikan untuk scope ini.

Verifikasi ulang ruleset main-quality-gate25827644: snapshot30Oktober enam context static/install-test/init-test/pwa-gate/invariant-tests/seed-invariants, strict up-to-date. Full-dataset runtime adalah acceptance domain tambahan; enam required contexts berbeda dari sembilan job PR unik.

PR14 dahulu menuju agen/transaksi-historis-perpetual; PR15 menuju branch supervisi, bukan main. Integrasi main melalui PR37. Periksa ancestry, jangan hanya membaca judul merge.

Refresh PR36/UI,39/full-dataset,46/gateway,47/provisioning atau penggantinya. Jangan mengeluarkan verdict dari snapshot skill.
