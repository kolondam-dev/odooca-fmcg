# Gap analysis Finance–Accounting–Tax

## 1. Baseline dan batas bukti

[F] Source baseline main `f65b41a`; file `oca.lock`, `deploy/init.sh`, `docs/SCOPE.md`, addon dashboard dan `id_base` diperiksa. [F] `INIT_MODULES` memuat core/custom dan `l10n_id`, tetapi tidak memuat laporan OCA/MIS/reconcile atau `l10n_id_efaktur_coretax`. Ini bukti daftar aktivasi default, **bukan bukti bahwa setiap addon tersebut uninstalled pada database live**. [BU] Inventaris live terbaru, grup user, menu/action, versi registry, chart mapping dan saldo pembukaan belum dibaca dengan akses accounting yang sah.

[F] Manifest berikut dibaca pada SHA lock, bukan hanya README cabang terbaru:

| Modul | Repo / SHA | Bukti | Belum dibuktikan |
|---|---|---|---|
| account_financial_report | account-financial-reporting / f48b4ea777c444256aa1c215ec3117d604b5feff | 19.0.0.0.26; installable=True; depends account,date_range,report_xlsx; GL/TB/journal/open-items/aging/VAT views | Instal/upgrade di DB proyek; ACL; nilai laporan |
| mis_builder | mis-builder / 7d519f31e1a553d7a5499571a9146f7e3ea49ea4 | 19.0.1.2.1; installable=True; depends account,board,report_xlsx,date_range | Template BS/P&L/cashflow dan mapping; penerimaan pengguna |
| account_reconcile_oca | account-reconcile / 14ddec26314e5a8b0470f301b95fa79ca2c2fd7d | Manifest 19.0.1.1.0; depends account_statement_base | Closure dependensi; rekonsiliasi bank; konflik dengan alur existing |

Modul lain di katalog adalah **kandidat**, bukan daftar addon yang semuanya telah diverifikasi installable. I0 harus merekam path, manifest/version, full SHA, lisensi, closure, hook dan hasil runtime untuk setiap modul. `account_usability` tersedia di upstream 19.0, tetapi repo account-financial-tools belum ada pada lock baseline. Jangan mengambil HEAD upstream tanpa pin dan pengujian.

## 2. Register gap

| ID | Prioritas | Kondisi / gap | Dampak | Penutupan yang dapat diverifikasi |
|---|---|---|---|---|
| G01 | P1 | Inventaris accounting runtime dan role belum diaudit | Diagnosis menu dan readiness tidak pasti | I0: snapshot read-only module/menu/role/company yang bertanggal; data sensitif disamarkan |
| G02 | P1 | Repo di image tidak sama dengan aktivasi addon; default install list belum mencakup paket laporan | Menu Accounting/laporan belum lengkap | I1: dependency closure dan activation profile; native install/upgrade/ACL browser |
| G03 | P1 | Coretax custom CSV dan nomor lokal berlabel resmi | Risiko salah memakai dokumen demo untuk pajak | I0 containment; I6 jalur XML native dan bukti penerimaan yang sah |
| G04 | P1 | COA, retained earnings dan mapping statements belum disahkan | BS/P&L/MIS bisa tampak lengkap tetapi salah | I1/I4: mapping versioned, unassigned-account exception dan sign-off finance |
| G05 | P1 | Belum ada acceptance GL/TB/partner/journal report terhadap oracle ledger | Selisih laporan tidak terlihat | I2: FIN01–FIN09/36–38/51 direkonsiliasi per company/currency |
| G06 | P1 | HPP order, expense GL, cost valuation dan stock snapshot berbeda basis | Double count atau margin palsu | I3: FIN10–18,53–54; movement-to-posted-journal bridge dan exception detail |
| G07 | P1 | BS/P&L/cashflow/equity/MIS belum menjadi paket laporan standar | Belum bisa financial close | I4: FIN19–23,31–35; template versioned dan ledger tie-out |
| G08 | P1 | Bank, payment allocation dan AR/AP historical belum diterima end-to-end | Cash dicatat seolah cleared; aging masa lalu berubah tanpa jejak | I5: FIN24–30/39–40; bank match, cutoff, allocation provenance |
| G09 | P1 | VAT, withholding dan tax-to-GL bridge belum diterima | CSV/VAT report generik disalahartikan SPT resmi | I6: FIN41–48; mapping bertanggal dan reviewer pajak |
| G10 | P1 | Close/lock/cutoff/carry-forward belum punya paket operasional | Periode closed dapat drift | I7: FIN49–50/52; rehearsal dan baseline immutable |
| G11 | P2 | Budget, dimensi cabang/principal dan intercompany/consolidation belum punya kontrak | Angka antarcabang tidak comparable | I4/I7: segment allocation, FX, eliminasi dan hasil konsolidasi |
| G12 | P2 | Ekspor, pagination, performa, pembulatan dan ACL belum diuji sebagai satu paket | Kebocoran data/angka UI beda ekspor | I8: semua ID; browser, XLSX/PDF dan ledger oracle |

## 3. Temuan Coretax yang memerlukan containment

Source `addons/id_base/models/account_move.py::action_generate_nsfp` membentuk nomor dari ID invoice dan prefix tahun `26`. Wizard `coretax_export_wizard.py` menghasilkan CSV, mengisi NPWP/alamat fallback dan menandai `l10n_id_coretax_exported=True`. Tes existing hanya membuktikan pola nomor dan CSV terbentuk. Itu **bukan bukti nomor resmi, validasi DJP atau faktur diterima**.

I0 merencanakan penghentian label/tombol resmi pada jalur ini, pemisahan referensi internal dari nomor resmi, serta status legacy/unverified. Jangan menghapus dokumen lama, mengganti nomor resmi, mengubah posted AML, atau mengartikan exported sebagai accepted. Sebelum perubahan: inventaris usage dan snapshot field; migrasi harus dapat diulang dan diaudit. Kebutuhan final mengutamakan native `l10n_id_efaktur_coretax`; custom hanya memperluas readiness, batch provenance, approval/status dan koreksi. Nomor resmi berasal dari bukti sistem penerbit; tidak disintesis dari ID Odoo.

DJP menjelaskan impor XML sesuai template. Snapshot dokumentasi bukan izin membekukan tarif, kode transaksi atau versi schema untuk semua masa. I6 merekam sumber resmi, tanggal berlaku, versi template/hash dan review pajak; tidak ada hardcoded tarif tahun berjalan pada rencana ini. XML valid lokal belum berarti accepted oleh DJP. H2H/PJAP harus diberi status tersendiri, bukan diasumsikan tersedia dari kemampuan ekspor.

## 4. Keputusan OCA dahulu, custom untuk gap

| Kebutuhan | Kandidat utama | Custom bila gap nyata | Batas |
|---|---|---|---|
| Menu dan usability accounting | account_usability; core account | id_finance_foundation untuk profile/menu/ACL yang kurang | Tidak menyalin engine posting Odoo; role sales tidak diberi akses accounting luas |
| GL/TB/journal/open items/aging/VAT | account_financial_report | adapter drilldown/as-of/audit bila OCA belum memenuhi kontrak | Jangan membangun GL kedua jika OCA dapat direkonsiliasi |
| BS/P&L/equity/cashflow/MIS/budget | mis_builder; mis_builder_budget; mis_builder_cash_flow | id_finance_reports untuk template ID/version/mapping dan gap statement | Kandidat cashflow/budget/statement tidak dianggap lengkap otomatis |
| AR/AP dan collection | partner_statement; credit-control candidates; native partial reconcile | id_finance_subledger untuk historical/frozen evidence yang kurang | Reuse ar_history/ar_commitment; jangan menggandakan sumber saldo |
| HPP dan stok | core stock_account; native move/journal links | id_finance_cost_bridge, laporan HPP/valuation/variance/landed cost | Actual posted cost; tidak standard-price/pro-rata fallback untuk menutupi source hilang |
| Bank/import/reconcile | account_reconcile_oca, account_statement_import_sheet_file_xlsx + closure | id_finance_bank untuk parser/mapping/settlement exception bila perlu | Import bank tidak otomatis mem-post/match semua baris |
| Indonesia tax/Coretax | l10n_id; l10n_id_efaktur_coretax | id_coretax_prep; id_tax_reconciliation untuk gap yang dikonfirmasi | Tax balance OCA bukan SPT/Coretax completion |
| Assets/accrual/FX/consolidation | Evaluasi modul OCA 19 yang benar-benar tersedia di I0 | id_finance_close / adapter native yang diperlukan | Nama addon/fitur tidak diada-adakan; absensi OCA tidak menghapus kewajiban laporan |

Nama custom merupakan rancangan, bukan addon yang sudah ada. Hindari addon monolitik; pemisahan final mengikuti dependency graph dan batas write/read. Setiap kandidat yang tidak lolos spike harus punya ADR pengganti custom, owner dan oracle yang sama, tanpa mencoret report ID.

## 5. Keputusan bisnis yang harus dicatat

Finance controller: COA/group mapping, fiscal year, posting/cutoff, basis accrual/cash presentation, metode costing per kategori, stock ownership, biaya yang boleh dikapitalisasi, materialitas display. Finance + business head: branch vs company/legal entity, principal/channel/warehouse dimensions, allocation policy dan budget owners. Tax PIC: PKP/NPWP/NITKU, kategori pajak, withholding scope, official number provenance dan template berlaku. Owner: role matrix, close/reopen authority, konsolidasi serta eliminasi. Tidak memakai toleransi materialitas untuk menyembunyikan selisih ledger.

Semua report ID wajib dibangun. `N/A` hanya untuk aktivitas yang terbukti tidak berlaku (misalnya transaksi mata uang asing atau PPh tertentu), dengan sign-off finance/tax dan trigger evaluasi ulang ketika aktivitas muncul. Bukan pengganti custom karena modul OCA belum tersedia.

## 6. Sumber yang diperiksa

- Repo proyek pada baseline: oca.lock; deploy/init.sh; docs/SCOPE.md §5–8; id_base/models/account_move.py; wizard/coretax_export_wizard.py; test_credit_limit_approval.py; docs/dashboard/3B_CLOSURE.md.
- https://github.com/OCA/account-financial-reporting/blob/f48b4ea777c444256aa1c215ec3117d604b5feff/account_financial_report/__manifest__.py
- https://github.com/OCA/mis-builder/blob/7d519f31e1a553d7a5499571a9146f7e3ea49ea4/mis_builder/__manifest__.py
- https://github.com/OCA/account-reconcile/blob/14ddec26314e5a8b0470f301b95fa79ca2c2fd7d/account_reconcile_oca/__manifest__.py
- https://github.com/OCA/account-financial-tools/blob/19.0/README.md (discovery account_usability; belum pin proyek).
- https://www.pajak.go.id/coretaxpedia/cara-membuat-faktur dan https://www.pajak.go.id/reformdjp/coretax/template-xml-dan-converter-excel-ke-xml (dibaca 2026-11-04; verifikasi ulang saat implementasi dan sebelum perubahan masa).
