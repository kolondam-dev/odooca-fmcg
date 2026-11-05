# I0 — audit runtime dan containment legacy

Tanggal: 5 November 2026. Pelaksana: codex (implementer, bukan reviewer independen).
Baseline main: `565e8a46fdec4d9d4f4f8a7f34c52d3f2e957493`.
PR rencana #86 merged pada `2b7cdd2e31f8cf700bd029ecacfb345c0f36a7a3`.
Branch mengikuti panduan: `agen/finance-i0-runtime-audit`.

## Keputusan pemilik sesi ini

[F] Pemilik memilih **demo company 1, IDR, chart Indonesia existing**, dan menjadi
pemberi keputusan Finance/Tax untuk demo. Pilihan ini bukan penerimaan filing
pajak resmi atau persetujuan otomatis semua mapping laporan. FIN01–58 tetap wajib.

## Bukti runtime

Target: project `569df00d-48e8-411a-93a5-df39ba97f16b`, environment
`47b72704-4054-4941-b978-d42c1befca55`, service Odoo
`56186eb1-eec2-4604-92d3-f449504cba4a`.
Deployment `b082e2dd-221f-4f54-ad38-0917a0fe5645`, source baseline di atas,
status SUCCESS; image
`sha256:9ae2c05cc4fb3937d9222db27949fed734f27256449f9cd0f435cc7c6ef28731`.

Audit dijalankan melalui SSH resmi dengan `finance_i0_inventory.py`. PostgreSQL
`REPEATABLE READ`, `READ ONLY`, timeout 20 detik per statement, rollback akhir;
tidak menginisialisasi registry atau mengubah data. Seluruh bagian query berhasil.
JSON mentah disimpan lokal di direktori temporary OpenCode, bukan git; mengandung
metadata akses yang tidak sama dengan acceptance ACL aplikasi.

- [F] Company 1 aktif, chart `id`, currency IDR; company 2 nonaktif.
- [F] `account`, `stock_account`, `l10n_id`, **`l10n_id_efaktur_coretax` installed**.
  Versi registry Coretax `19.0.1.0`; manifest image `1.0`, lisensi LGPL-3.
- [F] OCA financial report, tax balance, MIS/budget/cashflow, partner statement,
  reconcile, XLSX statement import, credit control dan financial risk uninstalled.
- [F] 29 kategori memiliki property eksplisit company 1 FIFO + real_time;
  3 kategori standard tanpa property valuation eksplisit; 14 kategori keduanya
  null. Nilai null SQL belum membuktikan nilai efektif ORM, karena default/inheritance.
- [F] 1.324 invoice pelanggan posted, 35 bill posted, 2.619 journal entry posted,
  2 invoice pelanggan draft. Semua kelompok: **0 referensi pajak custom terisi,
  0 flag CSV legacy exported** pada snapshot. Tidak ada nomor resmi disimpulkan
  dari hasil ini; field native memiliki sumber/status terpisah.
- [F] Field native `l10n_id_kode_transaksi`, `l10n_id_coretax_document`, dan
  identitas buyer/NIK/TKU tersedia bersama field legacy kustom. Jalur custom
  bukan pengganti jalur native yang sudah terpasang.

## Sumber dan keputusan OCA/custom

`I0_MODULE_EVIDENCE.json` memuat 22 kandidat dan closure 67 nama modul,
path/version/license/dependencies/external dependencies/hooks/hash manifest,
status registry, serta full SHA untuk sumber OCA. **19 manifest OCA cocok byte
dengan upstream pada pin proyek**. Manifest bukan bukti seluruh source identik
atau instal/upgrade berhasil. Image core Odoo berasal dari tag mutable `odoo:19.0`;
digest deployment di atas mengikat observasi, bukan full source commit core.

| Keputusan | Hasil / tindak lanjut |
|---|---|
| ADR-I0-01 laporan | Utamakan account_financial_report + closure date_range/report_xlsx; spike instal dan oracle I2 wajib sebelum diterima |
| ADR-I0-02 MIS | mis_builder, budget, cash_flow tersedia pada pin; templates dan mapping belum diterima |
| ADR-I0-03 bank | account_reconcile_oca + import sheet XLSX tersedia; format bank demo dan duplicate import perlu fixture |
| ADR-I0-04 Coretax | Reuse native installed; hentikan generator nomor/CSV custom, pertahankan field historis, tanpa konversi ke nomor/status resmi |
| ADR-I0-05 missing source | account_usability, account_asset_management, account_cutoff_base, account_multicurrency_revaluation, payroll_account tidak ditemukan di image/registry; belum berarti tidak tersedia upstream 19 |
| ADR-I0-06 lisensi | OCA reports/MIS/reconcile AGPL-3, native LGPL-3; custom baru mengikuti LGPL-3 repo. Lisensi kandidat dicatat per modul |

Pemilik teknis discovery/spike: codex; keputusan demo: pemilik repo. FIN36–38,
55–56 tetap terbuka bila kandidat gagal; cari kandidat exact SHA atau ADR custom
dengan oracle yang sama. Tidak menandai N/A karena modul absen.

### Discovery upstream tambahan (belum masuk lock/image)

[F] account-financial-tools pada full SHA
`c23fd09977c870eb3db071fca5958b83f699bc4a` menyediakan:

- `account_usability` 19.0.1.1.0, AGPL-3, depends account, Python
  openupgradelib. Pre-init menambah alias XMLID menu; post-init memperbarui
  terjemahan. Manifest/hook dibaca pada SHA tersebut. Aktivasi tidak membenarkan
  mengubah Anglo-Saxon/costing melalui settings.
- `account_asset_management` 19.0.1.0.3, AGPL-3, depends account dan
  report_xlsx_helper, Python python-dateutil; excludes account_asset.

[F] Tree account-closing `8ce0077fd0762d49e928ea7520555341d7936a9e` hanya
menampilkan account_fiscal_year_closing dan account_invoice_start_end_dates sebagai
addon. Kandidat cutoff/revaluation belum tersedia pada tree yang diperiksa.
Tree payroll pada pin proyek hanya memiliki addon payroll, bukan payroll_account.
I1 perlu proposal pin tools beserta spike; absensi paket belum membenarkan custom
posting tanpa kajian sumber lebih lanjut.

Workflow `finance-i0-spike.yml` menguji lima profil terpisah (reports, MIS, bank,
credit, native/payroll) dari lock existing pada DB disposable PostgreSQL 16:
install -> upgrade DB yang sama -> inventory registry dengan assertion semua
modul permintaan installed. Artifact log/inventory selalu diunggah. Gate ini
membuktikan kompatibilitas instal/upgrade, bukan oracle angka atau acceptance ACL.

## Containment dan migration preview

Patch `id_base` 19.0.1.3.1 menolak kedua RPC legacy sebelum query/write, menghapus
tombol generate, mengganti label menjadi legacy/unverified, serta membatasi menu
legacy ke Accounting Manager. Field/kolom/XMLID tetap ada. Tidak mengubah nomor,
flag historis, posted AML atau native export. Native Coretax acceptance tetap I6.

Upgrade yang diperlukan: `-u id_base` pada disposable/persistent rehearsal,
baru target demo berotorisasi. Boot marker existing tidak diasumsikan menjalankan
upgrade baru. Acceptance: view resolved tanpa tombol generator, direct RPC kedua
method ditolak, field lama tetap identik, ledger tetap identik, jalur native tidak
tertutup. Test native pada `test_credit_limit_approval.py` menegakkan penolakan dan
preservasi journal items serta nilai legacy existing. Bukti CI dicatat di PR.

## Gate yang masih terbuka

Status iterasi I0 keseluruhan: **HOLD**, bukan acceptance 58 laporan.

1. Spike install/upgrade kandidat OCA pada disposable, termasuk external packages
   `xlsxwriter`/`xlrd`, menu/action dan role/company negatives.
2. Saldo opening per akun, effective category costing/stock ownership, dan mapping
   COA demo disetujui sebelum I1/I2. SQL metadata belum membuktikan ORM security.
3. Golden dataset dua company/dua periode dengan angka expected per jurnal;
   kasus minimum mengikuti ACCEPTANCE_CONTRACT §C. Fixture harus berada di test,
   bukan CSV register kanonikal atau company demo existing.
4. Runtime native/upgrade containment dan review independen exact HEAD.

Pemecahan ini mengikuti IMPLEMENTATION_PLAN §Aturan pemecahan PR: discovery dan
containment adalah paket awal I0; gate belum boleh dilompati ke aktivasi produksi.

## Ulang audit

Jalankan `scripts/ops/finance_i0_inventory.py` dalam image Odoo target melalui SSH
resmi, menggunakan environment PG yang sudah tersedia; simpan stdout di lokasi
privat. Jangan mencetak environment atau memasukkan credential ke command/log.
Kemudian, dari checkout yang cocok dengan deployment:

```text
python scripts/ops/finance_i0_source_evidence.py <private-inventory.json> --out <software-evidence.json>
python -m unittest discover -s tests -p test_finance_i0_inventory.py -v
python -m ruff check .
python scripts/check_manifests.py
```

Query gagal menghasilkan PARTIAL dan exit 2. Source pin fetch/mismatch menghasilkan
exit nonzero. Missing candidate source tetap dicatat eksplisit. Tidak ada hasil
alat ini yang mempromosikan status FINxx secara otomatis.
