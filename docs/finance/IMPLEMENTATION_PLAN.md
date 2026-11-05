# Implementation plan — iterasi I0 sampai I8

Ini backlog implementasi wajib, bukan klaim fitur selesai. Setiap iterasi menghasilkan PR terpisah dari main terbaru, demo native Odoo 19, matriks bukti exact SHA, dan keputusan PASS/HOLD. Report ID merujuk REPORT_CATALOG.csv; tidak boleh dihapus ketika kandidat OCA gagal. Prioritas = risiko sumber terlebih dahulu, kemudian laporan dan presentasi.

## I0 — Audit runtime, containment pajak dan desain sumber

**Paket costing/ownership:** lihat `I0_COSTING_OWNERSHIP.md` untuk diagnostik
read-only dan fixture stok–GL. Ini fondasi sumber I0, bukan penerimaan I3 atau
seluruh FIN01–58; native CI exact SHA tetap gate terpisah.

**Input:** baseline main, akses read-only resmi ke database/role accounting, scope company dan periode. Branch berikut: `agen/finance-i0-runtime-audit`.

**Pekerjaan:** inventaris ir.module.module, versi registry, dependency closure, model/menu/actions dan access groups; bandingkan lock/image/installed tanpa menganggap repo downloaded=installed. Rekam chart/tax/currency/journal/warehouse/costing master dan saldo opening. Inventaris nomor faktur custom serta penggunaannya; rancang containment tombol/label CSV/NSFP lokal sebagai legacy/unverified, tanpa rewrite posted documents. Spike seluruh kandidat modul, pin full SHA dan lisensi/dependency termasuk external Python/system packages. Tentukan contract perusahaan/legal entity/cabang, cost attribution dan laporan berbasis ledger vs SO cohort.

**Output:** runtime inventory redacted, module activation matrix, decision register, ADR OCA/custom per gap, migration preview dan golden dataset. Update REPORT_CATALOG dengan bukti, bukan otomatis menandai ready. Keputusan blocking: COA, accounting/tax owner, currency, official-number provenance dan stock ownership.

**Gate:** audit read-only dapat diulang; negatif ACL/company gagal; setiap kandidat punya manifest/closure dan pemilik; containment diuji di disposable terlebih dahulu; seluruh data/register CSV existing tetap byte-identik. Ketiadaan akses live dicatat BLOCKED, tidak ditafsirkan uninstalled.

## I1 — Foundation, full menus dan aktivasi paket terukur

**Dependensi:** I0. Branch `agen/finance-i1-foundation`.

Pin/evaluasi account-financial-tools/account_usability; native account + l10n_id; kelompokkan paket laporan/reconcile/MIS menurut dependency closure yang lolos spike. Tambah activation profile/migration marker versioned untuk installed database, bukan mengandalkan upgrade_modules_v3 lama atau FORCE_UPGRADE permanen. Uji install baru dan upgrade database persisten; no demo data masuk produksi. Definisikan Finance Reader, Accountant, Accounting Manager, Tax PIC; sales/driver tidak memperoleh akses luas. Uji menu/action/report access, company rules, export dan technical groups.

COA mapping bersumber chart/account groups yang disahkan; perluasan akun memakai migrasi terkontrol, bukan mengganti chart pada database bertransaksi. Misahkan GL control AR/AP/stock/GRNI/cash transit/tax/equity. Perubahan costing/Anglo-Saxon tidak diaktifkan sebagai efek samping membuka menu: perlu ADR dan rehearsal khusus.

**Gate:** full menu tree dapat diakses role yang tepat; role tanpa hak ditolak server-side; module install/restart idempotent; tidak ada repost, renumber atau penghapusan transaksi. Menu lengkap baru menutup G02, belum menerima semua laporan.

## I2 — Paket buku besar dan subledger dasar

**Dependensi:** I1. Branch `agen/finance-i2-ledgers`. Coverage FIN01–09,36–38,51,55–57.

Konfigurasi OCA Financial Reports dan source drilldown; susun opening/movement/closing, journal ledger, AR/AP historical/open items/aging, multi-company TB. Aktifkan aset, accrual/prepayment/deferred dan FX dengan kandidat tervalidasi atau custom apabila gap Odoo19 terbukti. Tambahkan loan/lease/interest schedules berdasarkan kebijakan yang disahkan, payroll/reimbursement-to-GL bridge dan sales/purchase register; tax/payroll source yang belum resmi menjadi exception, bukan posting rekaan. Adapter historical harus menjelaskan rekonstruksi dari ledger/reconcile yang diamati sekarang dan dukungan frozen observation.

**Gate:** seluruh laporan cocok oracle AML native untuk periode kosong, opening sebelum periode, invoice/refund, pembayaran parsial, unreconcile, supplier credit, partnerless entry dan foreign currency. AR/AP buckets tie ke control GL dengan credits terpisah; combined TB tidak dilabeli consolidated. Fixed asset/disposal/reversal dan schedules cocok akun kontrol. Export/full dataset tidak terpotong diam-diam.

## I3 — HPP, valuasi dan inventory-to-GL bridge FMCG

**Dependensi:** I2. Branch `agen/finance-i3-cogs-valuation`. Coverage FIN10–18,53–54,58.

Bangun id_finance_cost_bridge bila OCA/native belum mencukupi: stock movement, ownership, UoM/lot, posted stock-accounting journal, invoice/return/refund dan adjustment provenance. Reuse singular native stock.move.account_move_id sesuai kontrak proyek; cek actual metadata 19 sebelum memilih sumber lain. Pisahkan COGS pengiriman, reverse COGS retur, scrap/expiry, GRNI, landed cost, purchase variance dan koreksi biaya. Internal transfer satu company tidak menciptakan revenue/HPP fiktif. COGS GL per tanggal posting dibedakan dari recognized margin cohort SO dan snapshot stok saat ini.

**Gate:** FIFO/AVCO atau metode kategori yang disahkan; partial delivery/invoice; return+refund; multi-lot/UoM; landed cost sesudah sebagian terjual; consigned stock; goods in transit; negatif stok dan cost correction; shared cost journal ambigu wajib exception. HPP customer movements cocok GL mapped accounts; stock rollforward cocok valuation/GL; unexplained variance=0. Tidak menggunakan harga standar/pro-rata untuk membuat angka terlihat lengkap.

## I4 — Financial statements, MIS, budget dan dimensi

**Dependensi:** I2 dan I3 untuk HPP/stock. Branch `agen/finance-i4-statements-mis`. Coverage FIN19–23,31–35.

Bangun template versioned Balance Sheet, P&L, equity, direct/indirect cashflow dan MIS pack. Prioritaskan mis_builder dan kandidat budget/cashflow; custom mengisi mapping/gap. Sediakan monthly/YTD/prior-period/prior-year, actual vs approved budget dan forecast, branch/company/principal/channel/warehouse dimension dengan unallocated bucket. Jangan membagi biaya hanya menurut omzet tanpa kebijakan allocation yang disahkan. Rasio menyertakan basis periode/average balance; pembagi nol unavailable.

**Gate:** BS balance; P&L tie ke GL dan HPP; equity rollforward; direct dan indirect cashflow menjelaskan perubahan cash yang sama; noncash/FX/transfer tidak dianggap operating receipt. Semua akun aktif terpetakan atau terlihat sebagai exception; MIS template/formula dan budget version dapat diaudit. Segment+unallocated=company; branch bukan otomatis legal entity.

## I5 — Bank, receivables/payables dan settlement operasional

**Dependensi:** I2; data operasi yang sah. Branch `agen/finance-i5-settlement`. Coverage FIN24–30,39–40.

Aktifkan bank statement import/reconcile dengan format bank yang disahkan. Bedakan cash received, posted payment, allocated AR/AP, bank matched, in-transit, credit/write-off dan pending approval. Bangun BRS, cash/bank book, customer/supplier statement, claims/rebates dan money-in-transit bridge ke source operasional. Reuse frozen AR evidence dan promise guard PR83. Source POD/queue lokal bukan posted receipt; tampilkan sumber belum resmi sebagai exception, bukan ledger.

**Gate:** duplicate import/idempotency, transfer antar rekening, fee, partial matching, overpayment, refund, chargeback, reversal/unreconcile, cross-company mismatch dan period cutoff. Nilai statement/bank book/control GL/allocations direkonsiliasi. Kreditan noncash tidak memenuhi janji bayar. Pengguna sales tidak bisa bank-match atau approve pembayaran karena akses dashboard.

## I6 — Indonesia tax dan Coretax resmi

**Dependensi:** I0 containment, I1 roles/localization, I2 tax ledger; I5 settlement untuk bukti bayar. Branch `agen/finance-i6-tax-coretax`. Coverage FIN41–48.

Integrasikan l10n_id_efaktur_coretax native setelah dependency/license/field conflict spike. Custom id_coretax_prep untuk readiness, NPWP/NIK/NITKU, traceable batch hash/source/template version, status, correction/return/cancellation lineage, re-export dan duplicate guards. Pisahkan legacy custom fields dari native official number, reference internal, export status dan acceptance evidence. Jangan memigrasikan nomor lokal menjadi nomor resmi atau mengubah posted AML.

Buat PPN input/output, VAT-to-GL, withholding payable/receivable sesuai aktivitas, bukti potong, billing/payment/NTPN reconciliation dan SPT working papers/fiscal reconciliation. Tax PIC menyetujui aturan bertanggal dan template resmi; OCA VAT report generik bukan pengganti semua formulir Indonesia. Corporate SPT/withholding working papers harus punya mapping dan status filing tersendiri. H2H/PJAP adalah subfase integrasi terpisah dengan API/akun resmi; tidak menjadi syarat tersembunyi untuk ekspor manual, dan tidak boleh disebut sudah ada.

**Gate:** native valid/invalid source cases, refunds, downpayment bila berlaku, correction linkage, duplicate export, malformed XML, schema/template version, required identities, tax-base/rounding/GL reconciliation. Golden expected XML dibandingkan struktur dan nilai; schema validation saja belum accepted. UAT oleh tax PIC pada mekanisme resmi yang tersedia; tidak mengunggah atau menandatangani ke DJP tanpa otorisasi spesifik. Tidak ada NSFP sintetis, fallback NPWP/alamat yang disamarkan sebagai valid, atau exported=accepted.

## I7 — Close, intercompany dan konsolidasi

**Dependensi:** I2–I6. Branch `agen/finance-i7-close-consolidation`. Coverage FIN49–50,52.

Close checklist: AR/AP/bank/stock/GRNI/HPP/assets/accrual/FX/tax/intercompany; period lock dan documented reopen; income-to-equity/carry-forward yang sesuai perilaku native. Tentukan perimeter konsolidasi, functional/presentation currency, rate types/period, account mapping, intercompany matching dan eliminasi. Holding/branch/commercial principal tidak dicampur menjadi company hierarchy yang palsu.

**Gate:** rehearsal dua periode berurutan; opening bulan berikut=closing sebelumnya; tahun baru/equity tidak menggandakan P&L. Posting bertanggal locked ditolak; reopening terekam. Combined TB berbeda jelas dari consolidated statements. Translation/CTA dan eliminasi punya bukti; mismatches tidak disapu ke rounding. Snapshot close+digest immutable terhadap transaksi bulan berikut.

## I8 — Acceptance penuh, performa dan rollout

**Dependensi:** semua iterasi terkait PASS. Branch `agen/finance-i8-acceptance-rollout`. Coverage semua FIN01–FIN58.

Jalankan gold dataset, historical project dataset dan persistent upgrade/replay; cocokkan output screen/XLSX/PDF dan source IDs. PDF tidak memotong kolom; XLSX nilai numerik, formula injection ditangkal, timezone/currency jelas. Uji filter/grain/pagination, concurrency, record rules, company switching, audit export, penguncian periode dan browser native desktop/tablet. Ukur cold/warm timing pada volume snapshot dan proyeksi cabang/retensi: proposed p95 summary<=5s, detail first page<=10s, export100k lines<=120s; ukur hardware/dataset/row limits, finance/ops menyetujui revisi sebelum gate final. Tidak ada silent truncation.

Rollout: disposable -> staging dengan data tersamarkan -> branch/per-company pilot -> kelompok cabang -> full. Sebelum production migration: backup DB+filestore, restore rehearsal, baseline saldo/IDs/hash, dependency/source lock, release/migration runbook dan maintenance window. Instal modul tidak boleh menjadi reset/reseed. Jika schema berubah, rollback image saja tidak cukup: pilih forward fix atau restore terkontrol dengan rekonsiliasi transaksi setelah backup dan otorisasi khusus bila destructive.

**Gate akhir:** 58/58 report IDs diterima atau applicability N/A bersign-off; tidak ada blocker P1/P2; CI exact SHA; native/upgrade/source/visual evidence; role UAT Finance Controller + Tax PIC + pemilik. Detail PASS per laporan wajib terhubung ke run/test/artifact. Tidak ada klaim siap hanya karena 192 tes existing atau dashboard terlihat benar.

## Aturan pemecahan PR dan estimasi

Setiap iterasi boleh menjadi beberapa PR (spike, source/ACL, reports, migration, UAT) dengan report IDs/gap IDs dan final SHA. I3 dapat dimulai setelah ledger oracle I2 stabil; I4/I5 dapat dikerjakan terpisah setelah kontrak sumber disepakati. I6 tidak menunggu semua kosmetik laporan untuk menangani containment, tetapi penerimaan tax bergantung ledger. Jangan menggabungkan semua aktivasi sekaligus.

Belum menetapkan tanggal selesai: effort ditentukan setelah spike I0 menguji closure OCA19, runtime access, data quality dan kapasitas tim. Review setiap akhir iterasi: temuan -> counterexample -> perbaikan -> ulang acceptance -> keputusan PASS/HOLD -> perbarui matriks. Gate yang gagal tetap terbuka; scope tidak diperkecil agar jadwal terlihat selesai.
