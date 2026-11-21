# Eksekusi penerimaan FIN01–FIN58 — snapshot 2026-11-19

**Status:** 0/58 `DITERIMA`; `REPORT_CATALOG.csv` tetap sumber status dan tidak
diubah oleh inventaris ini. Dokumen ini adalah urutan kerja dan register blocker,
bukan sign-off Finance/Tax atau persetujuan mengubah data production. Company
demo utama: **PT Manado Distribusi Utama** (ID 1). Dasar keputusan:
[`ACCEPTANCE_CONTRACT.md`](ACCEPTANCE_CONTRACT.md),
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), dan
[`OWNER_DECISIONS.md`](OWNER_DECISIONS.md).

## 0. Bukti awal dan gerbang bersama — sebelum menerima satu ID pun

1. **Bekukan baseline.** Catat full SHA image, versi modul *installed*, company,
   periode, journal/account mapping yang disahkan, snapshot DB + filestore dengan
   lokasi privat dan uji restore; jangan memasukkan dump atau workbook bisnis ke
   git. Pisahkan DB disposable/staging dari demo production. Pada production
   saat inventaris 2026-11-19: `id_finance_reporting 19.0.1.5.2`,
   `id_finance_foundation 19.0.1.1.0`, `account_financial_report 19.0.0.0.26`
   installed; `mis_builder`, `account_reconcile_oca`,
   `account_asset_management`, `hr_expense`, `payroll` uninstalled;
   `l10n_id_efaktur_coretax 19.0.1.0` installed. Status modul **bukan** bukti
   report/template/otoritas sudah siap.
2. **Tetapkan perimeter bersama Finance Controller.** Sahkan COA dan akun kontrol
   AR/AP/stok/GRNI/kas/pajak/ekuitas, tahun fiskal, tanggal posting vs dokumen,
   company/legal entity vs cabang, valuta/rate, kepemilikan stok dan kebijakan
   pembulatan. Ada 2 company di DB demo; FIN51 dan konsolidasi tidak otomatis
   boleh mencampur keduanya. Tanpa mapping/perimeter bertanggal, hasil numerik
   tidak dapat diterima.
3. **Dataset dan oracle independen.** Disposables: dua periode/dua company,
   opening, posted/draft, retur/reversal, partial reconcile, lot/UoM, nilai stok,
   FX, pajak dan cutoff. Expected dihitung dari AML/stock moves/partial reconcile,
   bukan dari fungsi laporan. Untuk tiap invariant jalankan baseline → mutasi
   satu fakta → oracle gagal pada alasan yang tepat → rollback → baseline lulus.
4. **Paket bukti per ID.** Simpan grain, source IDs dan version/full SHA;
   expected vs actual angka/coverage/exception; filter, drilldown, screen,
   XLSX/PDF ekuivalen, formula-injection/row-limit, scope company/ACL negatif,
   waktu eksekusi, persistent upgrade/replay, frozen close/digest, isu residual,
   serta sign-off bernama dan bertanggal. Bukti live bisnis di lokasi privat
   berotorisasi; repo publik hanya fixture sintetis dan rujukan teredaksi.
   Jalur status: `DISCOVERED → SOURCE_VERIFIED → NATIVE_INSTALLED → ORACLE_PASS
   → ACL_EXPORT_VISUAL_PASS → STAGING_UAT_PASS → ACCEPTED`. Jangan loncat gate.

**Yang sudah ada:** PR #151 merge `ace3df27b1f0ac39504c404584528c3e50b14ffc`;
run [44302027254](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/44302027254)
menunjukkan menu/wizard 8 action, FIN04 Juli Run dan XLSX berstruktur; run
[44302063284](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/44302063284)
menunjukkan dua route. XLSX asli tidak disimpan artifact; **isi sel live belum
direkonsiliasi**. Fixture disposable kini mempunyai pembanding isi FIN01/02/03/
04/51/57, tetapi hasil native untuk FIN01/02/03/51/57 masih [BU] sampai CI
exact-SHA menjalankannya. Bukti fixture bukan penerimaan ID atau bukti live.
Probe read-only Odoo pada company 1 menunjukkan
`FINANCE_SALES_SCOPE=UNAVAILABLE`: **tidak ada user aktif Sales-only** yang
berwenang pada company 1 untuk uji negatif production. Fixture Sales/Driver di
CI disposable pernah ditolak (`I2_EXPOSURE.md`), tetapi itu bukan bukti akun
production. Jangan membuat user atau memberi grup di DB live tanpa otorisasi.

## Urutan prioritas, cakupan lengkap, dan blocker yang menghentikan gate

**Batas slice/PR:** satu PR untuk satu paket fungsi dan oracle yang koheren;
**bukan satu PR per FINxx dan bukan PR khusus log**. I2a mencakup enam ID,
I2b lima, I2c lima (pecah hanya bila dependency asset/payroll menghalangi
integrasi aman), lalu I3/I4/I5/I6/I7 menurut sumber yang sama. Tiap PR membawa
implementasi atau test eksekutabel, bukti exact SHA, catatan log/HANDOFF, dan
daftar ID yang *masih* HOLD. Pengumpulan bukti privat serta sign-off I8 bisa
menyusul per ID tanpa PR baru jika tidak ada perubahan kode/katalog; perubahan
katalog digabung dalam PR paket fungsi yang relevan atau satu PR penerimaan
I8 setelah keputusan tertulis, bukan PR kosmetik per ID. **Slice I2a tetap HOLD
untuk penerimaan live:** pembanding fixture harus lolos CI exact-SHA, lalu bukti
finansial live dan izin role masih diperlukan. Laporkan saat commit/PR benar-benar terjadi beserta SHA/tautan,
bukan mengklaim submit dari working tree.

| Prioritas / iterasi | ID (jumlah) | Paket kerja dan acceptance terukur | Blocker penting / pelepasnya |
|---|---|---|---|
| P0 — I2a: ledger dasar | **FIN01, FIN02, FIN03, FIN04, FIN51, FIN57** (6) | GL opening + debit − credit = closing; TB debit=credit; sequence jurnal/drilldown; FIN04 AML posted/reversal; FIN57 invoice/bill/refund tanpa duplikasi; FIN51 per-company TB + rate, jelas **combined ≠ consolidated**. Cocokkan UI dan seluruh sel XLSX dengan oracle native, termasuk batas halaman/row. | Mapping chart dan dua-company perimeter disahkan Controller; workbook asli + digest di storage privat; user Sales ditolak server-side dan browser; freeze periode serta QA/Controller sign-off per ID. Menu/XLSX `PK` saja tidak cukup. |
| P1 — I2b: AR/AP | **FIN05, FIN06, FIN07, FIN08, FIN09** (5) | AR dan AP dipisah; partnerless/credit/debit exception eksplisit; residual *as-of* dari partial allocation bertanggal; signed bucket aging = subledger + GL control; pembayaran setelah cutoff tidak mengubah snapshot historis yang dibekukan. | Approved control accounts, periode frozen, kasus parsial/unreconcile dan credit notes. Label current-observed reconstruction tidak boleh dipasarkan sebagai snapshot historis yang tak berubah. |
| P2 — I2c: sumber khusus | **FIN36, FIN37, FIN38, FIN55, FIN56** (5) | FIN36 asset/depreciation/disposal ke GL; FIN37 jadwal accrual/releases ke GL tanpa double posting; FIN38 realized/unrealized FX per rate/tanggal; FIN55 liabilitas pinjaman/sewa + bunga/pembayaran; FIN56 approved payroll/expense→GL, pembayaran dan pajak terpisah. | FIN36: spike/install OCA `account_asset_management` + closure + coverage aset. FIN55: parameter kontrak pokok/bunga/jadwal/akun/dokumen **bertanggal** dan sign-off Controller; tanpa itu exception bernominal, bukan angka rekaan. FIN56: `payroll`/`hr_expense` belum installed, perlu alur persetujuan/slip-jurnal dan sumber statutory PPh21/BPJS resmi bertanggal + Tax PIC. FIN37/38 sudah ada snapshot, belum acceptance per ID. |
| P3 — I3: HPP dan stok | **FIN10, FIN11, FIN12, FIN13, FIN14, FIN15, FIN16, FIN17, FIN18, FIN53, FIN54, FIN58** (12) | Ikat stock.move→posted cost journal secara unik; opening+movement=closing qty/value; stock GL, HPP delivery−return, GRNI, landed cost sesudah jual, scrap/expiry, consignment/transit, purchase variance, delivered-not-invoiced dan margin invoice-cohort dipisah basisnya. Tidak ada selisih tak dijelaskan atau alokasi harga rekaan. | Diagnostik read-only demo pada 2026-11-19: 51 kategori (29 FIFO+real_time; 22 standard+periodic), 7 produk storable berbiaya standar nol, 3.091 move bernilai; **profil FIFO seragam adalah asumsi salah**. Controller harus menyetujui metode/mapping per kategori dan penyebab zero-cost sebelum oracle I3; jangan ubah kategori atau transaksi live untuk menyamakan asumsi. |
| P4 — I4: statements/MIS | **FIN19, FIN20, FIN21, FIN22, FIN23, FIN31, FIN32, FIN33, FIN34, FIN35** (10) | BS balance; P&L ke GL/HPP; cashflow direct/indirect ke perubahan kas yang sama; equity rollforward; MIS KPI/rasio/budget/dimensi versioned, unallocated eksplisit dan pembagi nol unavailable. | `mis_builder` belum installed; template, budget/forecast approved, basis cash-equivalents dan alokasi cabang/principal/channel/warehouse belum disahkan. Menunggu I2+I3 dan keputusan Finance/Business Head. |
| P5 — I5: bank/settlement | **FIN24, FIN25, FIN26, FIN27, FIN28, FIN29, FIN30, FIN39, FIN40** (9) | Statement, partial/overpayment, promise-to-pay hanya cash cocok, cash/bank book, BRS, clearing/transit, driver collection, credit hold dan rebate klaim ke posted GL. Duplicate import/unreconcile/refund/transfer diuji. | `account_reconcile_oca` belum installed; format bank, sumber POD vs kas riil, bukti settlement/approval, batas retensi rekening dan role belum disahkan. Sales tidak boleh match bank/approve kas. |
| P6 — I6: tax/Coretax | **FIN41, FIN42, FIN43, FIN44, FIN45, FIN46, FIN47, FIN48** (8) | PPN output/input dan balance ke tax GL; Coretax identity, XML/status, koreksi original→replacement; withholding, NTPN dan SPT working papers dengan bukti resmi. `exported ≠ accepted ≠ paid`. | `l10n_id_efaktur_coretax` terpasang tetapi belum membuktikan template, identity, fiscal mapping atau status DJP. **Tax PIC** harus menyetujui sumber resmi beserta tanggal berlaku, PPh/PPN/pengecualian, dokumen dan mekanisme uji; jangan membuat NSFP/NPWP atau mengirim ke DJP tanpa izin khusus. Bergantung I5 untuk bukti pembayaran. |
| P7 — I7: close/konsolidasi | **FIN49, FIN50, FIN52** (3) | Checklist cutoff/lock, opening berikut=closing lalu, intercompany simetris, translation/CTA + eliminasi approved = consolidated BS/P&L/cashflow/equity (FIN19–23). | Tunggu I2–I6, perimeter legal entity vs cabang, rate & elimination policy, backup/restore rehearsal dan otorisasi close/reopen. Combined TB FIN51 tidak memenuhi konsolidasi. |
| P8 — I8: penerimaan satu per satu | **FIN01–FIN58** (58) | Untuk setiap ID telusuri semua gate bersama di atas, uji UI/export/performance/migrasi pada exact SHA, lakukan staging UAT, tanda tangan Finance Controller + QA atau Tax PIC + Finance Controller (FIN41–48), lalu ubah hanya baris terkait di katalog dengan rujukan bukti. N/A hanya aktivitas terbukti tidak berlaku + sign-off dan trigger evaluasi ulang. | Tidak ada staging/restore rehearsal yang dibuktikan untuk paket penuh; nama penanggung jawab, tanggal sign-off dan penyimpanan bukti privat belum diberikan. **Asisten tidak dapat menggantikan sign-off bisnis/pajak atau mengubah status otomatis.** |

Total kelompok sebelum I8: **16 + 12 + 10 + 9 + 8 + 3 = 58 ID**, tanpa duplikasi.
Urutan ini bukan izin mass-install, reset/reseed, posting, pajak resmi, atau merge
tanpa review. Implementasi tiap paket di branch/PR terpisah dari `main` terbaru;
CI minimal `scripts/ci/plan.py`, suite natif/upgrade/live yang relevan, dan
bukti exact SHA. Jika gate gagal, tulis trigger, expected/actual, counterexample,
owner dan rerun—bukan mengubah oracle atau menyembunyikan exception.

## Langkah berikut yang dapat dieksekusi sekarang

1. **Controller + QA:** tandatangani scope/COA dan dua periode/two-company golden
   ledger; pilih jalur penyimpanan privat untuk XLSX dan screenshot. Untuk
   produksi jangan menyalin raw AML/identitas pajak ke repo/issue publik.
2. **Implementer I2a:** mulai FIN01/02/03/04/51/57 dari kode existing; susun
   matriks expected per ID (angka, source IDs, filter, URL drilldown, isi ekspor)
   dan negative control pada DB disposable, lalu replay data historis.
3. **Controller stok:** tandatangani apakah kategori campuran diterima per
   kategori atau perlu migrasi bertahap; selidiki 7 zero-cost products secara
   read-only. Jangan samakan profil dengan `FIFO+real_time` secara massal.
4. **Pemilik/Tax PIC:** berikan parameter FIN55 dan sumber payroll/statutory
   FIN56; putuskan kebijakan mapping tax, bank, dan close sebelum paketnya.
5. **UAT per ID:** baru setelah hasil per-ID lengkap dan sign-off diberikan,
   ubah status katalog satu baris per keputusan. Tidak ada target tanggal
   acceptance yang sah sebelum blocker di atas dilepas.

### I2a: tie-out nilai XLSX pada fixture disposable (bukan bukti live)

`scripts/ops/verify_finance_i2_xlsx.py` membaca XLSX tanpa Odoo dan menolak
formula, angka yang tersimpan sebagai teks, header/coverage hilang, kode
duplikat, serta nilai yang tidak cocok. `verify_finance_i2_ledgers_core.py`
menghasilkan workbook lewat wizard/report asli pada dua company sintetis lalu:

- FIN01: opening, detail debit/credit, ending, jumlah AML dan filter jurnal;
- FIN02: semua account termasuk zero row, period balance dan ending;
- FIN03: debit/credit serta jumlah detail per jurnal, termasuk filter jurnal;
- FIN51: semua combined account, identitas balance, dan seluruh totals pada
  perimeter 1× + 7× (combined, tanpa eliminasi);
- FIN57: tepat satu invoice/bill/refund per tipe, net/tax/gross; semua entri
  duplicate list ditolak tanpa bergantung tipe sel; coverage akun tie-out unik
  dan nilai register/GL/non-register per akun dibandingkan dengan pembacaan AML
  posted independen; distinct non-register move/line juga dipatok;
- FIN04: seluruh AML/value melalui pembanding independen di bawah.

Unit offline sintetis menutup 28 kasus positif/counterexample. [BU] Render OCA
native dan workbook custom pada DB disposable hanya dijalankan oleh Finance I0
CI; hasil belum boleh disebut PASS sebelum check exact-SHA hijau. Tidak ada
workbook bisnis, AML live, atau status katalog yang berubah.

### I2b: tie-out XLSX AR/AP pada fixture disposable (bukan bukti live)

`verify_finance_i2_arap_subledger.py` mengekspor workbook wizard nyata untuk
FIN05/FIN06 (dua periode × customer/supplier, ditambah satu `all`), FIN07 (empat
as-of × dua tipe) dan FIN08/FIN09 (tiga as-of × dua tipe) pada dua company
sintetis. `verify_finance_i2_xlsx.py` membandingkan setiap sel terpilih dengan
oracle AML/partial independen:

- FIN05/FIN06: coverage unik `(partner, tipe akun)`, opening/debit/credit/
  closing per baris, identitas movement dan closing, totals + `partner_count`,
  split `by_account_type`, serta subledger↔GL tie-out;
- FIN07: coverage line unik, move/account/partner/tipe/tanggal/balance/matched/
  residual per line, grup `line_ids` per partner, total akun, dan tie-out GL;
  ekspor kosong hanya diterima sebagai placeholder resmi dengan GL nol;
- FIN08/FIN09: urutan bucket dan edges, total per bucket, bucket per partner,
  residual per partner, detail line per bucket, total akun dan tie-out GL.

Filter `date_from`/`partner_ids` FIN07 belum tersedia di jalur export wizard,
jadi slice terfilter tetap diverifikasi pada oracle native dan tidak diklaim
tercakup XLSX. Field snapshot skalar (mis. `total_residual`) tidak ditulis ke
workbook; nilainya diturunkan dari baris dan dipatok ke oracle. Unit offline
menutup 24 kasus I2b (52 total pada berkas XLSX); [BU] render native hanya
dijalankan Finance I0 CI pada exact SHA. Tidak ada workbook bisnis, AML live,
atau status katalog yang berubah.

### FIN04: pembanding XLSX ↔ AML independen (belum dijalankan pada live)

`scripts/ops/verify_finance_fin04_workbook.py` membandingkan **semua** `aml_id`, debit,
credit dan balance pada sheet `rows` dengan CSV AML yang diekspor **langsung dari
sumber Odoo, bukan dari payload FIN04**. CSV wajib berisi header
`aml_id,company_id,date,parent_state,journal_id,account_id,display_type,debit,credit,balance`;
masukkan semua baris dari scope terotorisasi agar bukti eksklusi draft/company
lain bisa diuji. Query sumber harus mendokumentasikan domain dan read ACL,
jumlah baris sebelum/sesudah filter, periode, company, SHA data/berkas dan
identitas pengambilnya. Contoh menjalankan **di workstation privat**, bukan CI
publik (ganti path sesuai kebijakan penyimpanan):

```text
python scripts/ops/verify_finance_fin04_workbook.py --source <private>/aml.csv --workbook <private>/FIN04.xlsx --company 1 --from-date 2026-07-01 --to-date 2026-07-31
python -m unittest tests.test_finance_fin04_workbook
```

Filter `--journal <id>` / `--account <id>` harus sama dengan wizard; opsi
`--include-draft` hanya bila wizard juga mengaktifkannya. Comparator gagal pada
ID hilang/duplikat, sel nominal yang disimpan sebagai string, jumlah berbeda,
formula, dan salah domain; output hanya status/jumlah/agregat (tetap sensitif,
jangan diunggah tanpa izin). Unit test sintetis membuktikan 8 kasus, **bukan**
rekonsiliasi produksi. Belum memverifikasi autentikasi sumber CSV, materi
transaksi di luar FIN04, *source drilldown*, frozen close, sign-off ataupun
metode costing. Ukuran di atas 20.000 AML perlu filter terpisah dan tie-out
antarpartisi sebelum FIN04 dapat diterima; jangan menganggap partisi tunggal
sebagai lengkap.
