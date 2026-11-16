# CI selection, required gates, dan full regression

Dokumen ini adalah panduan operasional pemilihan workflow. Sumber kebenaran
mesin adalah `.ci/test-impact.yml`; implementasinya `scripts/ci/plan.py` dan
kontraknya `tests/test_ci_impact.py`.

## 1. Prinsip

1. **Static selalu berjalan.** Pemilihan hanya menghindari runtime yang tidak
   relevan, bukan menghindari lint, manifest, syntax, atau kontrak planner.
2. **Fail-closed.** Path baru yang belum dipetakan menjalankan semua suite.
3. **Perubahan control-plane menjalankan semua suite.** Ini mencakup workflow,
   impact map, planner, dan test planner.
4. **Override hanya menambah.** Label/manual input tidak dapat menghapus suite
   minimum hasil planner.
5. **Required context selalu muncul.** Suite yang tidak relevan selesai sebagai
   no-op PASS dengan alasan, bukan hilang sebagai expected check.
6. **Exact SHA.** Bukti release mengunci SHA sebelum suite dimulai. PASS tidak
   memberi izin merge atau deployment.

## 2. Mengetahui suite sebelum membuka PR

Sinkronkan basis, lalu jalankan:

```bash
python scripts/ci/plan.py --base origin/main --head HEAD
```

Keluaran mencantumkan file, suite, alasan per suite, path tidak dikenal, dan
apakah full regression dipilih. Agen wajib menyalin ringkasannya ke deskripsi
PR/HANDOFF. Agen boleh meminta cakupan tambahan dengan label `full-ci`,
`pwa-ci`, atau `seed-ci`; label tidak dapat mengurangi cakupan otomatis.

## 3. Pemetaan tingkat tinggi

| Perubahan | Suite minimum |
|---|---|
| `pwa/**` | PWA quality, browser, container |
| addon Odoo umum | install modul + persisted upgrade |
| dashboard/UI Odoo | install + UI/browser/D1 + upgrade |
| mobile API | install + provisioning mobile + upgrade |
| finance | install + init + finance profiles + upgrade |
| seed/register/loader | init + invariant + full dataset + upgrade |
| Docker/OCA/deploy | Odoo install/init/UI/mobile/finance/upgrade/full dataset |
| docs/log saja | static; runtime menjadi no-op PASS |
| path tidak dikenal atau aturan CI | semua suite |

File PO di bawah addon mengikuti suite addon nyata. Validasi syntax saja tidak
cukup karena importer terjemahan Odoo dapat gagal saat registry dimuat.

## 4. Struktur gate

- `CI`: planner, static, targeted Odoo install/UI/mobile, dan init.
- `PWA quality`: planner, quality, browser, container, `pwa-gate`.
- `Seed supervision`: planner, unit/invariant, `seed-invariants`.
- `Finance I0 candidate spike`: planner dan `finance-gate`.
- `Upgrade Runtime Verification`: planner dan `upgrade-gate`.
- `Full Dataset Runtime Verification`: planner dan `full-dataset-gate`.

Ruleset `main-quality-gate` harus mewajibkan context stabil berikut setelah
workflow ini tersedia di default branch:

```text
static
install-test
init-test
pwa-gate
invariant-tests
seed-invariants
finance-gate
upgrade-gate
full-dataset-gate
```

Tiga gate terakhir selalu hadir pada PR, tetapi menjadi PASS/no-op saat planner
tidak memilih suite tersebut. Jangan menambah required context job internal
yang conditional karena job itu sah untuk berstatus skipped.

## 5. Menambah atau mengubah test

Test baru tidak boleh langsung ditumpuk ke `install-test`. PR test baru wajib
mendokumentasikan:

| Kontrak | Isi wajib |
|---|---|
| Suite | area pemilik, mis. `dashboard` atau `seed` |
| Risiko | kegagalan produksi yang dicegah |
| Trigger | path yang harus memilih suite |
| Budget | L0 <1m, L1 <5m, L2 5–15m, L3 20–90m |
| Isolasi | unit, DB disposable, browser, dataset penuh |
| Bukti | log/report/screenshot yang diunggah |
| Jadwal | PR targeted, nightly, release, atau kombinasi |
| Pemilik | agen/area yang menindaklanjuti failure |

Perubahan `.ci/test-impact.yml` harus disertai counterexample di
`tests/test_ci_impact.py`. Path baru default full bukan alasan untuk membiarkan
map tidak terawat; tambahkan aturan setelah dampaknya dipahami.

## 6. Nightly dan release gate

`Full Regression Gate` berjalan tiap hari pukul 01:00 WITA dan dapat dijalankan
manual dengan input branch/tag/SHA. Job `resolve` mengubah input menjadi exact
SHA, lalu menjalankan core, PWA, seed, finance, persisted upgrade, dan full
dataset terhadap SHA yang sama.

- **Nightly** mengaudit integrasi `main`, flakiness, dan kesalahan impact map.
- **Release** wajib dipakai sebelum deployment production untuk perubahan
  high-risk atau rilis terjadwal.
- `FULL_REGRESSION_GATE=PASS` adalah bukti verifikasi, bukan otorisasi deploy.
- Jika Railway auto-deploy dari `main`, nightly tidak melindungi interval antara
  merge dan malam hari. Untuk release terkontrol, matikan auto-deploy dan
  promosikan exact SHA yang lulus setelah persetujuan pemilik.

Perubahan high-risk yang wajib memakai `full-ci` atau release gate: Dockerfile,
`oca.lock`, `deploy/init.sh`, workflow/impact planner, migrasi/model bersama,
chart/accounting, loader seed, dan dependency lintas addon.

## 7. Cache dan duplikasi

- BuildKit `type=gha` menyimpan layer di GitHub Actions, terpisah dari cache
  laptop dan Railway. Cache mempercepat build; ia tidak menggantikan test.
- Browser Playwright disimpan di cache GitHub berdasarkan OS/lockfile/versi.
  Dependency sistem tetap diverifikasi oleh `playwright install --with-deps`.
- Feature branch tidak lagi memakai trigger `push` untuk PWA/seed. PR memakai
  event `pull_request`; `push` hanya untuk `main`, sehingga SHA yang sama tidak
  menjalankan suite dua kali.

## 8. Menangani kegagalan

1. Baca `CI impact plan` dan pastikan suite memang dipilih karena path yang
   benar. Jika tidak, koreksi map dan tambahkan test planner—jangan skip test.
2. Bedakan job instalasi, init, PWA, seed, finance, upgrade, dan full dataset.
3. Retry hanya untuk membuktikan flakiness; retry hijau bukan penyelesaian.
4. Kegagalan nightly yang lolos PR targeted adalah bukti selector kurang luas.
   Tambahkan trigger dan counterexample.
5. Jangan melemahkan grep ERROR, invariant, atau oracle agar PR cepat hijau.
