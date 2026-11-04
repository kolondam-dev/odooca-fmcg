# Kontrak penerimaan laporan dan ledger

## A. Kontrak bersama

Setiap FINxx mencatat grain, source model/field/journal IDs, company scope, posting date vs invoice date vs event date, WITA boundary, currency, posted/draft policy, reversal handling, opening/closing, tax sign dan report/template version. Default laporan keuangan = posted ledger dan company yang boleh dibaca; draft diberi mode eksplisit terpisah. Header screen/export wajib membawa filter dan waktu observasi.

Rekonsiliasi memakai company currency dan native rounding; selisih di luar pembulatan deterministik harus dijelaskan per source, tidak ditutup dengan konstanta epsilon/materialitas arbitrer. Pisahkan balances functional currency, transaction currency, exchange rate source/date dan presentation currency. Rounding residual ditampilkan, bukan disebar diam-diam.

Missing source/ambiguity/ACL-incomplete source harus unavailable/exception dengan coverage; bukan 0 atau margin100%. Domain UI/drilldown/export harus sama dengan domain report. Detail terpaginasikan tidak boleh membuat aggregate hanya menjumlah halaman pertama. Consolidation harus memisahkan legal entity dari branch dimensi.

## B. Oracle independen

Oracle dibangun dari AML posted/native moves/partial reconciles, tidak memanggil fungsi report yang sedang diuji. SQL kontrol hanya di lingkungan uji resmi, scoped company, tanpa sudo bypass pada endpoint produk. Chart mapping disahkan finance; expected figures fixture dihitung independen.

| Kelompok | Invariant minimum |
|---|---|
| GL/TB/journal | Opening+period debit-period credit=closing tiap akun; total debit=credit; filter journal/company/year konsisten |
| AR/AP | Partner control totals+partnerless exceptions=GL; residual as-of dan signed credits jelas; seluruh bucket=saldo subledger |
| HPP | Unique source movements/cost AML; delivery cost-return cost+classified adjustments=posted mapped HPP; selisih attribution vs posting terurai |
| Stock | Opening value+signed valuation movements=closing; owned stock vs stock GL; consignment/transit/GRNI/writeoff dilaporkan terpisah |
| Statements | BS assets=liabilities+equity; P&L/HPP ke GL; equity opening+movements=closing; no duplicate retained earnings |
| Cashflow/bank | Opening+cash movement=closing; direct/indirect tie; cash equivalent perimeter dan noncash/FX explicit; BRS items explain bank-vs-book |
| Budget/MIS | Actual=GL; budget version/approval/date locked; formulas versioned; segment+unallocated=total; no double allocation |
| Tax | Invoice/bill/refund bases and taxes=tax GL by signed mapping; exported/accepted/paid distinct; document/template provenance |
| Close/consolidation | Opening next period=closing prior; translated TB+eliminations=consolidated; combined sum alone insufficient |

## C. Golden dataset dan expected cases

Buat dataset disposable dengan nominal sederhana yang disahkan finance: opening balances balanced; purchase+receipt+bill dengan beda tanggal; partial delivery/invoice; customer return+refund; vendor return; multilot/multi-UoM; landed cost sebelum/sesudah sale; stock scrap/expiry; consignment dan in-transit; bank fee/internal transfer; partial payment/overpayment/unallocated credit; bank matching/unreconcile; writeoff; foreign currency invoice/payment/period FX; fixed asset+disposal; accrual/prepayment; downpayment; intercompany unmatched/matched+elimination; tax normal/refund/correction dan missing identity. Catat expected journal entries/totals per kasus sebelum menjalankan report.

Dua periode dan dua company minimum; berbeda currency bila consolidation/FX berlaku. Periode kosong, batas tengah malam WITA, tanggal fiscal year, backdated posting, archived partner/SKU/account, restricted record rules, missing journals dan duplicate UUID/source IDs adalah wajib. Perusahaan tanpa transaksi tidak otomatis zero jika source tidak terbaca. Jangan memutasi CSV kanonikal proyek untuk menambahkan fixture.

Counterexample: baseline lulus -> ubah satu invariant (cost link hilang, salah company, partial reconcile date, duplicate bank import, unassigned account, invalid tax identity/schema, wrong official-number provenance) -> assertion yang relevan wajib menolak -> rollback -> baseline kembali lulus. Jangan hanya menguji salinan algoritma atau keberadaan file/menu.

## D. Histori, freeze dan perubahan data

As-of yang dihitung dari ledger/reconcile saat observasi bukan jaminan mengetahui keadaan sistem historis sebelum edit/unreconcile. Label basis tersebut dan sediakan freeze payload/source/digest saat close/capture. Digest mendeteksi perubahan payload, bukan tanda tangan pihak ketiga atau perlindungan terhadap admin DB. Janji bayar tidak boleh memakai kredit/writeoff sebagai cash, dan alokasi yang sama tidak memenuhi dua janji aktif.

Migration acceptance: inventory registry/versions; backup+restore rehearsal; pre/post AML IDs/balances/posted states/stock quantities/reservation/payment allocations/master relations; replay no duplicate documents; schema/view/constraint checks; no renumber/repost/reset. Koreksi legacy Coretax memisahkan status unverified tanpa mengubah nomor resmi yang dibuktikan valid.

## E. Definisi DONE dan evidence ledger

Per report ID simpan: module/full SHA/license/closure; requirement dan approved mapping; fixture expected; native test/run/job; result angka/coverage; source drilldown; XLSX/PDF/screenshot; company/role negatives; performance volume/timing; persistent upgrade/replay; migration rehearsal; Finance/Tax/UAT sign-off dan residual issues. Tidak menyimpan credential, raw bank statement, NPWP lengkap atau data bisnis live dalam public repo.

Status berurutan: DISCOVERED -> SOURCE_VERIFIED -> NATIVE_INSTALLED -> ORACLE_PASS -> ACL_EXPORT_VISUAL_PASS -> STAGING_UAT_PASS -> ACCEPTED. Gagal gate = HOLD dengan trigger/expected/actual/acceptance executable. Evidence live memakai ringkasan teredaksi dan lokasi penyimpanan berotorisasi; dokumen publik hanya fixture sintetis.

Completion paket mensyaratkan semua FIN01–FIN58 accepted atau N/A yang dibuktikan karena aktivitas tidak berlaku, dengan persetujuan bernama per peran dan tanggal. Tidak tersedia OCA19 bukan alasan N/A: lakukan spike/ADR lalu custom untuk report yang sama. Production deployment dan penerimaan pajak resmi dicatat terpisah dari merge/CI.
