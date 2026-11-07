# Handover brief — Finance/Accounting/Tax untuk agent `antigravity` (WSL)

Dari: `codex` (supervisor sesi sebelumnya). Tanggal: 5 November 2026.
Baseline `main`: `d9c7e5f05dc7a023cb28c3bf60678c86f7820700` (merge PR #96 dari
HEAD integrasi `192defae41e6d4a18b2caffcc10fd346b08095ca`).
Status brief: koordinasi kerja, **bukan** penerimaan report, bukan otorisasi
deployment/seed/aktivasi demo.

---

## 1. Ringkasan satu menit

- Roadmap Finance–Accounting–Tax terdiri dari **9 tahap I0–I8** dan **58 report ID**
  pada `docs/finance/REPORT_CATALOG.csv`. Saat ini **58/58 masih `BELUM_DITERIMA`**.
- Yang sudah merged: audit/containment I0, golden ledger, ledger security,
  diagnostik costing–ownership, dan **persiapan I1** (role/menu/profil aktivasi).
- Yang belum: penutupan penuh I0 (snapshot live terbaru + sign-off COA), aktivasi
  demo, serta seluruh I2–I8.
- Pekerjaan berikutnya yang disarankan: **I2 — buku besar dan subledger dasar**
  (FIN01–09, 36–38, 51, 55–57), dipecah menjadi 2–3 PR kohesif.
- **Deployment, seed, aktivasi modul di demo, dan perubahan data/role/chart/costing
  di demo tetap ditunda** sampai pemilik memberi instruksi eksplisit.

---

## 2. Baca dulu, dalam urutan ini

1. `AGENTS.md` — aturan repo, tanda tangan commit, log append-only, tag [F]/[A]/[BU].
2. `docs/AGENT_PROTOCOL.md` — koordinasi antar-agen dan kepemilikan branch.
3. `docs/HANDOFF.md` — 20–40 baris teratas.
4. `docs/finance/README.md` — paket dokumen dan batas bukti.
5. `docs/finance/IMPLEMENTATION_PLAN.md` — kontrak I0–I8 dan gate tiap tahap.
6. `docs/finance/ACCEPTANCE_CONTRACT.md` — oracle independen dan status evidence.
7. `docs/finance/GAP_ANALYSIS.md` — G01–G12 dan keputusan OCA-first.
8. `docs/finance/I0_RUNTIME_AUDIT.md`, `I0_GOLDEN_LEDGER.md`,
   `I0_LEDGER_SECURITY.md`, `I0_COSTING_OWNERSHIP.md`.
9. `docs/finance/I1_FOUNDATION.md`, `I1_FOUNDATION_HANDOFF.md`.
10. `docs/finance/REPORT_CATALOG.csv` — 58 baris, semua masih `BELUM_DITERIMA`.

Catatan: dua entri HANDOFF untuk PR #96 **tidak** ada di `docs/HANDOFF.md`
(pemilik mempertahankan versi main saat resolusi konflik). Keduanya disimpan di
`docs/finance/I1_FOUNDATION_HANDOFF.md`. Jangan "memindahkannya" tanpa alasan.

---

## 3. Posisi roadmap dan bukti yang sudah ada

| Tahap | Status | Bukti / batas |
|---|---|---|
| I0 audit runtime, containment, golden ledger, security | **PASS terbatas per paket** | PR #86, #89–#91, #95. Snapshot runtime lama; belum observasi live terbaru. |
| I0 costing/ownership + stock–GL diagnostics | **Merged, PASS sesuai scope** | PR #95, HEAD `b2bd88e`; merge `abef7bb`. P2 unmatched-GL ditutup dengan mutasi native 1×/7×. Bukan I3/COGS penuh. |
| I1 foundation (role/menu/profil aktivasi) | **Persiapan merged** | PR #96, `d9c7e5f`. Native install/upgrade + fingerprint preservation + role probes PASS. **Belum aktivasi demo, belum full I1 accepted.** |
| I2–I8 dan FIN01–58 | **Belum dikerjakan** | Semua report `BELUM_DITERIMA`; belum ada oracle per report. |
| Seed F0–F2 (track terpisah) | Berjalan di branch lain | PR #93/#94 merged; branch `agen/seed-f0b-stock-reconcile` (`857e2e6`) belum merged. **Jangan dicampur ke PR finance.** |
| Deployment / demo | **Ditunda oleh pemilik** | Tidak ada deploy, seed, aktivasi, atau tulis demo dari sesi sebelumnya. |

### Artefak yang harus dipakai ulang

- `addons/id_finance_reporting/` — guard TB/role/company, stock bridge,
  `stock_compare.compare_stock_gl`.
- `addons/id_finance_foundation/` — role Reader/Accountant/Manager/Tax PIC, shortcut
  lima wizard OCA, render guard GL/journal/open-items/aging.
- `scripts/ops/finance_activation.py` — planner/attestation profil versioned.
- `scripts/ops/verify_finance_golden_ledger.py` — fixture dua company/periode,
  `build_fixture`, `make_entry`, `trial_balance`, `assert_figures`, `JULY`.
- `scripts/ops/verify_finance_ledger_security.py` — helper `actor`, `denied`,
  isolated company/role probes.
- `scripts/ops/verify_finance_stock_bridge.py` — fixture stok native + mutasi P2.
- `scripts/ops/verify_finance_foundation.py` — fingerprint preservasi + role probes.
- `.github/workflows/finance-i0-spike.yml` — 6 profil kandidat + gate finance.
- `.github/workflows/upgrade-runtime.yml` — upgrade persisten + replay zero drift.

---

## 4. Aturan yang tidak boleh dilanggar

1. **Sebelum aksi:** `bash scripts/agent/whats_new.sh antigravity`, lalu baca
   `docs/HANDOFF.md` dan `docs/DEVELOPMENT.md`.
2. **Sesudah aksi:** entri `agent-log/antigravity.log` lewat
   `bash scripts/agent/log_entry.sh antigravity INFO "<judul>" "<butir>"...`,
   plus entri `docs/HANDOFF.md`. Log agen lain **append-only**; jangan edit/hapus.
3. **Commit:** branch `agen/<topik>` dari main terbaru, PR ke `main`, baris terakhir
   `task managed by antigravity-agent at <ISO8601 +07:00>` (keluaran
   `scripts/agent/log_entry.sh antigravity --sig-only`). Penulis commit tetap pemilik.
4. **Rahasia:** jangan pernah menulis token, password, kredensial Railway/DB,
   NPWP lengkap, atau data bisnis live ke repo/log.
5. **Data:** jangan dump DB/filestore ke git. Jangan edit data server langsung.
   Jangan seed/reset/repost/renumber transaksi.
6. **Klaim:** [F] fakta bersumber, [A] asumsi, [BU] belum diuji. CI hijau dasar
   **bukan** penerimaan seed/report. Jangan menandai `ACCEPTED`/`N/A` tanpa bukti
   dan sign-off bernama.
7. **Keputusan pemilik:** demo company 1, IDR, chart Indonesia existing. Pemilik
   adalah pemberi keputusan Finance/Tax. Jangan menambah company demo; company
   fixture hanya boleh di DB disposable dan di-rollback.
8. **Deployment:** hanya setelah instruksi eksplisit ("deploy sekarang"), dengan
   backup/restore rehearsal dan runbook. Railway bersifat read-only sampai itu.

---

## 5. Setup awal di WSL (30 menit pertama)

```bash
bash scripts/agent/whats_new.sh antigravity
git switch main
git pull --ff-only
git status --short --branch

python -m ruff check .
python scripts/check_manifests.py
python -m unittest discover -s tests -p 'test_finance*.py' -v
python -m unittest tests.test_state_20260801 tests.test_seed_v2_gates -v

gh pr list --state open
gh run list --workflow finance-i0-spike.yml --limit 5
gh run list --workflow upgrade-runtime.yml --limit 5
```

Interpretasi:
- `test_finance*.py` harus 23 tes PASS.
- Suite penuh repo bisa time-out di lingkungan lokal; gunakan subset bertarget,
  jangan mengklaim PASS dari run yang terpotong.
- Docker native gate dijalankan di GitHub Actions (kebijakan laptop pemilik:
  tidak ada Docker lokal). Jika WSL memang punya Docker, **hanya** untuk DB
  disposable bernama `finance_i0_reports_disposable`; jangan pernah mengarah ke
  Railway/live.
- File untracked `full_dataset_runtime_report.json` dan
  `full_dataset_runtime_summary.md` adalah sisa observasi lama; **jangan commit,
  jangan hapus** tanpa konfirmasi pemilik.

Setelah verifikasi, tulis entri log "resume" + HANDOFF berisi HEAD yang dibaca,
hasil tes, dan paket yang akan diambil. Jangan mulai menulis kode sebelum itu.

---

## 6. Paket berikutnya yang disarankan — I2

Target: **FIN01–09, FIN36–38, FIN51, FIN55–57** (16 report). Pecah menjadi tiga PR
agar masing-masing punya oracle dan review yang jelas.

### I2a — GL/TB/journal + register (`agen/finance-i2-ledgers-core`)

Report: **FIN01, FIN02, FIN03, FIN04, FIN51, FIN57**.

Deliverable:
- Fixture disposable dua company + dua periode: opening sebelum periode,
  invoice/refund, pembayaran parsial, unreconcile, supplier credit, partnerless
  entry, dan (bila disetujui) valuta asing.
- Oracle independen dari `account.move.line` posted (bukan memanggil report yang
  diuji): `opening + debit − credit = closing` per akun, total debit = credit,
  filter journal/company/year konsisten.
- Bandingkan hasil aktual `_get_report_values` OCA (dict, bukan tampilan) dengan
  oracle.
- FIN51: TB per entity + rate/source translation; **combined ≠ consolidated**.
- FIN57: register invoice/bill/refund tanpa duplikasi baris; total revenue/
  purchase/tax tie ke GL.
- Counterexample wajib: ubah satu invariant (salah company, jurnal hilang,
  duplikasi baris) → assertion menolak → rollback → baseline kembali lulus.

### I2b — AR/AP subledger (`agen/finance-i2-arap`)

Report: **FIN05, FIN06, FIN07, FIN08, FIN09**.

Deliverable:
- Partner ledger AR/AP; partnerless exception eksplisit.
- Open items as-of dari **partial reconcile bertanggal**, bukan saldo sekarang.
- Aging bucket bertanda; `sum(buckets) = subledger = GL control`.
- Supplier debit/kredit dipisah; credit note dan refund tidak dianggap cash.
- Negative cases: partner beda company, akses Sales, filter tanggal, unreconcile.

### I2c — Schedules dan register non-inti (`agen/finance-i2-schedules`)

Report: **FIN36, FIN37, FIN38, FIN55, FIN56**.

Deliverable hanya untuk sumber/kebijakan yang disahkan:
- Fixed asset register + disposal/depreciation → control GL.
- Accrual/prepayment/deferred schedule; release posted, tanpa double posting.
- FX revaluation: functional/transaction/presentation dipisah; realized vs
  unrealized tie ke jurnal.
- Loan/lease/interest schedule sesuai kebijakan pemilik.
- Payroll/reimbursement bridge hanya bila sumber payroll resmi tersedia.
- Jika sumber belum ada: hasilkan **exception/unavailable dengan coverage**,
  bukan angka sintetis atau N/A.

Urutan aman: **I2a → I2b → I2c**. Jangan mulai I3 sebelum oracle ledger I2 stabil.

---

## 7. Definition of done per PR I2

1. Branch dari `main` terbaru; tidak mencampur perubahan seed.
2. Fixture + oracle independen + counterexample rollback.
3. Native CI exact SHA hijau (`finance-i0-spike.yml`), plus upgrade/replay bila
   mengubah modul/DB.
4. Role/company negatives diuji server-side, tanpa sudo.
5. Tidak ada perubahan posted AML/ID/nomor dokumen; tidak ada reset/reseed.
6. `REPORT_CATALOG.csv` diperbarui ke status berurutan
   `DISCOVERED → SOURCE_VERIFIED → NATIVE_INSTALLED → ORACLE_PASS →
   ACL_EXPORT_VISUAL_PASS → STAGING_UAT_PASS → ACCEPTED`, dengan bukti run/job.
7. `docs/HANDOFF.md` + `agent-log/antigravity.log` diperbarui; batas bukti jujur.
8. Review independen memberi PASS/HOLD. **Merge/deploy terpisah dari PASS CI.**

---

## 8. Jebakan teknis Odoo 19 yang sudah terbukti

- `stock.move` **tidak punya field `name`**; `reference` diturunkan dari
  `picking_id.name`. Fixture harus membuat picking/operation native, bukan move
  telanjang.
- Link valuasi memakai **singular** `stock.move.account_move_id` (bukan `_ids`).
- Inverse quantity pada receipt consignment **tidak** mewarisi
  `restrict_partner_id`; set owner eksplisit pada move line.
- Company golden harus dibuat dengan
  `.with_context(chart_template_load=True).create(...)`.
- Rollback rule memerlukan `env.registry.clear_cache()` + `env.invalidate_all()`.
- Probe `accountant` butuh **dua** grup: `account.group_account_user` dan
  `stock.group_stock_user`.
- Nama DB fixture hard-coded `finance_i0_reports_disposable`; jangan longgarkan
  tanpa alasan.
- OCA `account_usability` mengubah label grup native dan membuat manager
  mengimplikasi account user. Itu perubahan otorisasi yang disengaja; uji ulang
  negative role bila menyentuhnya.
- Laporan OCA `_get_report_values(docids, data)` adalah entry point yang diuji;
  jangan menguji hanya keberadaan menu/XML.

---

## 9. Keputusan yang harus diminta ke pemilik sebelum diklaim selesai

1. **COA/control-account mapping** final (AR, AP, stock, GRNI, cash transit, tax,
   equity) — chart existing belum otomatis accepted.
2. **Snapshot live terbaru** costing/ownership/saldo opening company 1 (read-only,
   teredaksi) — gate I0 yang masih terbuka.
3. **Kebijakan costing/Anglo-Saxon** — jangan aktifkan sebagai efek samping menu.
4. **Tax PIC** dan sumber resmi bertanggal untuk I6 (bukan CSV/NSFP sintetis).
5. **Periode/volume UAT** dan siapa penandatangan tiap report.
6. **Otorisasi deployment/seed/aktivasi demo** — saat ini belum ada.

---

## 10. Red flags — hentikan dan tanyakan

- Ada permintaan "aktifkan semua modul sekaligus" atau "deploy sekarang" tanpa
  backup/runbook/otorisasi.
- Test lulus karena memanggil salinan algoritma report, atau karena hanya mengecek
  menu/XML.
- Angka kosong diisi 0, N/A, atau pro-rata agar laporan "terlihat lengkap".
- Perubahan pada posted journal, nomor dokumen, chart, atau costing tanpa ADR +
  rehearsal.
- HANDOFF/log agen lain ditimpa, atau rahasia/data live masuk repo.
- Klaim PASS dari CI yang belum selesai / run push parsial.

---

## 11. Format laporan balik ke pemilik

Setiap paket selesai, laporkan:

- Branch, PR, HEAD exact SHA, base main.
- Report ID dan status katalog yang berubah (dengan bukti run/job).
- Oracle: apa yang dihitung independen, hasil angka, counterexample.
- Role/company/export/browser coverage — atau nyatakan belum.
- Upgrade/replay/fingerprint bila menyentuh modul/DB.
- Batas bukti [BU] dan keputusan pemilik yang masih terbuka.
- Pernyataan eksplisit: tidak ada deploy/seed/demo write (kecuali diotorisasi).

---

## 12. Titik mulai yang konkret

1. Jalankan checklist §5 dan catat hasilnya di log.
2. Minta konfirmasi pemilik untuk dua hal: **(a)** lanjut I2a, **(b)** apakah
   snapshot live/COA sign-off akan disediakan sekarang atau ditunda.
3. Buat `agen/finance-i2-ledgers-core` dari `main` terbaru.
4. Mulai dari fixture + oracle FIN01/FIN02 (opening, invoice/refund, partial,
   unreconcile, partnerless), lalu FIN03/FIN04/FIN51/FIN57.
5. Push PR, tunggu CI exact SHA, minta review independen. Jangan merge sendiri.

---

_Brief ini tidak mengubah kode, data, role, chart, costing, seed, atau deployment.
Semua angka/klaim di atas merujuk dokumen dan commit yang disebut; bila ragu,
perlakukan sebagai [BU] dan verifikasi ulang._
