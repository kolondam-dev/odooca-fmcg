# PR #110 — Acceptance Paket B

Acuan [mandat supervisor](https://github.com/kolondam-dev/odooca-fmcg/pull/110#issuecomment-7091069205) dan [Paket A](PR110_PACKET_A_ACCEPTANCE.md). Historical import menggunakan harga dan diskon efektif sumber. Fixture operasional menggunakan keputusan approval dan pengguna Odoo eksplisit.

## Inventaris

- Juli memiliki 1.324 SO dengan diskon header Rp281.242.486. Sebanyak 2.738 line Juli tidak memuat stack, footer, kode program, atau keputusan approval.
- Agustus memiliki 2.350 line. Diskon efektif line Rp108.961.922,80. Kolom stack, footer, actor dan keputusan approval tidak tersedia. Tanggal, referensi pelanggan, SKU, harga, kuantitas, lot, nominal diskon, dan DPP tersedia.
- Sebanyak 1.581 line tanpa kode promo memiliki diskon Rp33.719.139,40. Nilai pada line berkode promo adalah diskon efektif keseluruhan. Atribusi rupiah per komponen belum diketahui.

| Kode sumber Agustus | Line | Diskon efektif |
| --- | ---: | ---: |
| PROMO-2026-MAYORA-FMCG | 255 | Rp18.357.939,00 |
| PROMO-2026-SANTOS-KOPI | 143 | Rp7.702.611,20 |
| TIER-VOL-UNILEVER-8 | 225 | Rp39.688.166,00 |
| TIER-VOL-WINGS-10 | 146 | Rp9.494.067,20 |

Register tidak mendeklarasikan relasi yang diotorisasi ke ID eksternal program Odoo. Nama program master yang mirip tidak memberikan relasi tersebut.

## Matriks

| ID | Pelaku, kondisi dan action | Oracle dan kontrol negatif | Bukti awal | Status |
| --- | --- | --- | --- | --- |
| B-01 | Sales, order tanpa diskon, evaluasi approval | Zero discount, nol tactical request | `TestApprovalEngine.test_03d_mobile_auto_request_noop_without_discount` | CLOSED |
| B-02 | Sales, promo eligible, Supervisor | Pending memblokir, Supervisor menyetujui, program tidak eligible ditolak | Wizard native `test_governed_native_promo_requires_supervisor` meliputi status, tanggal, company, principal, SKU dan minimum. Kontrak budget serta outlet/channel masih terbuka | PARTIAL |
| B-03 | Sales, tactical Tier0, Supervisor untuk monitoring promo | Batas persis Tier0, promo tetap monitoring | `test_21c_mixed_order_in_free_zone_still_needs_supervisor_promo_monitoring` | CLOSED |
| B-04 | Sales, approval berjenjang, line dan footer | Rp1 juta → Rp950.000 → Rp940.500 → Rp900.000. Tolak pergantian line walau total tetap | `test_tactical_line_stack_and_footer_to_reconciliation` lulus dengan role nyata dan mutasi komposisi total tetap. Tes satu line dan `test_multi_sku_fixed_promo_rounding_and_stale_approval` mencakup fixed program-first sampai settlement. Stack dengan reward persen ditolak server | PARTIAL |
| B-05 | Sales, beberapa SKU dan principal | Alokasi nominal presisi, remainder, aturan principal, kontrol pergeseran alokasi | `test_multi_sku_fixed_promo_rounding_and_stale_approval` mengikat alokasi dua SKU dan menolak tiga mutasi dengan total sama. `test_governed_native_promo_requires_supervisor` mencakup pemisahan SO lintas principal | PARTIAL |
| B-06 | Sales dan approver, riwayat pada window WITA | Boundary tier, crossing, bobot nilai, isolasi company/outlet/salesman | Existing `test_approval_engine.py` memberi regresi dasar | CLOSED |
| B-07 | Sales, approver, gudang, akuntansi | Harga, diskon, DPP, pajak, invoice link, residual, jurnal, replay dan rollback | Golden chain tactical sampai rekonsiliasi dan mini-pack historis lulus secara lokal. Golden chain gabungan satu promo nominal dengan satu dan dua line mencapai settlement. Cakupan historis gabungan tetap terbatas oleh register | PARTIAL |

## Oracle native dua SKU

| Komponen | SKU A | SKU B |
| --- | ---: | ---: |
| DPP awal | 1.000.000,00 | 500.000,00 |
| Bagian DPP promo | 40.000,00 | 20.000,00 |
| DPP sesudah promo | 960.000,00 | 480.000,00 |
| Tactical berurutan | 5% → 912.000,00, lalu 1% → 902.880,00 | 2% → 470.400,00 |
| Bagian footer 101,01 | 66,41 | 34,60 |
| DPP line barang pada invoice | 942.813,59 | 490.365,40 |

Reward native Rp66.000 termasuk pajak tercatat terpisah sebagai DPP −60.000,00. Setelah reward, total DPP Rp1.373.178,99, pajak fixture 10% Rp137.317,90 dan piutang Rp1.510.496,89. Pencatatan piutang dan relasi pembayaran diperiksa sampai residual nol. Pengujian memindahkan alokasi promo, alokasi footer atau diskon efektif antar-SKU sambil menjaga total. Approval lama menolak setiap mutasi. Minimum program yang berubah setelah approval turut memblokir konfirmasi.

## Mapping historis yang menunggu otorisasi

Principal SKU berasal dari join `order_lines.csv` dengan `data/seed/products_150.csv`. Cakupan register di bawah adalah Agustus 2026. Periode berlakunya program dan external ID perlu dikonfirmasi pemilik register sebelum loader dapat mengikat referensi.

Semua kode teramati dari 1 sampai 31 Agustus 2026. Nominal di bawah adalah diskon efektif dari register.

| Kode sumber | Principal SKU | Line | Diskon efektif | Kandidat dan hasil pemeriksaan |
| --- | --- | ---: | ---: | --- |
| PROMO-2026-MAYORA-FMCG | PRIN-MAYORA | 255 | Rp18.357.939,00 | `id_promo_governance.promo_mayora_torabika_2026`, 1 Agustus–31 Desember. Principal dan tanggal cocok. Register meliputi SKU di luar Torabika dan tidak menautkan MoU atau external ID. |
| PROMO-2026-SANTOS-KOPI | PRIN-SANTOS | 143 | Rp7.702.611,20 | `id_promo_governance.promo_santos_kapalapi_2026`, 15 Agustus–31 Desember. Principal cocok, tetapi ada transaksi sebelum 15 Agustus. Kandidat ini gagal mencakup seluruh kode. |
| TIER-VOL-UNILEVER-8 | PRIN-UNILEVER | 225 | Rp39.688.166,00 | Master repo yang diperiksa tidak memuat kandidat. |
| TIER-VOL-WINGS-10 | PRIN-WINGS | 146 | Rp9.494.067,20 | Master repo yang diperiksa tidak memuat kandidat. |

Sumber kandidat adalah `addons/id_promo_governance/data/id_promo_demo_data.xml`. Pemilik register dapat mengesahkan mapping dengan bukti per cakupan, menyetujui master referensi historis dalam perubahan terpisah, atau menerima status UNKNOWN dan mempertahankan referensi sumber.

## Keputusan eligibility dan budget

Pagu rupiah memerlukan keputusan produk/Finance tentang basis DPP atau gross, mata uang dan konversi, scope company/program/periode, waktu reserve dan expiry, titik consume, serta pelepasan karena cancel, retur, revisi atau retry. Setelah aturan ditetapkan, gate integrasi memerlukan dua transaksi PostgreSQL independen untuk membuktikan satu klaim menang atas sisa pagu yang sama dan retry tidak menghitung pemakaian dua kali. Dimensi outlet/channel memerlukan kontrak eligibility yang disetujui. Field sumber biaya pada program saat ini hanya mengklasifikasikan beban.

## Dependency order v2

DS_RECONCILIATION K4/K13 B2, kontrak order v2 dan feature gate `features.order_pricing_v2`. PWA mendukung preview line/footer dan program. Handler backend legacy belum menerima pricing v2 maupun memberikan snapshot program yang sah. PR backend terpisah diperlukan untuk schema submit/revise, quote dan validasi otoritatif, budget lifecycle, idempotensi UUID, serta integrasi browser/backend. Status OPEN. Owner dan PR backend v2 menunggu penugasan eksplisit. Flag live tetap mati. K5 tidak memblokir Paket B.

## Implementasi dan batas pembuktian

- Aksi server tactical menyimpan stack dan footer teralokasi. Aplikasi diskon memakai diskon efektif native supaya tagihan hanya memotong sekali. Presisi yang tidak bisa dinyatakan pada line native ditolak. Aksi ini mendukung satu reward nominal tetap berlingkup order, dengan satu profil pajak barang. Basis alokasi adalah nilai DPP reward native. Reward tetap menjadi line tersendiri pada invoice. Reward persen, cakupan SKU khusus dan profil pajak campuran ditolak pada jalur kombinasi ini. Integrasi promo + tactical existing tetap memiliki satu rantai tactical.
- Snapshot approval mengikat komposisi dan diskon, SKU/UoM, kuantitas, harga, pajak, program/reward dan konteks perusahaan/outlet/Sales. Aksi validasi tier memeriksa actor. Perubahan komposisi bernilai total sama, penulisan state langsung, dan role yang salah diuji.
- Mini-pack mengambil `PO-2026-08-01` → `SO-202608-1007` → `INV-202608-1007` → `PAY-AR-02000` langsung dari register. Oracle menguji kode promo sumber, harga, qty, diskon, relasi invoice, nominal dan payment edge. Mutasi metadata promo melalui ORM mempertahankan total, ditolak oracle, lalu di-rollback. Regresi Python menukar persen antar-SKU dengan total yang sama.
- Seluruh 769 line berkode disimpan sebagai referensi historis belum terpetakan. Snapshot dari loader lama yang berisi binding fuzzy perlu ditinjau sebelum replay karena guard akan menolaknya. Kode sumber tidak menjadi klaim atau rekam approval.
- Governance native membatasi promo berpemilik principal ke status approved/active, company sesuai dan order yang produknya satu principal yang cocok. SKU/minimum dan periode memakai engine native. Coverage budget rupiah (termasuk kompetisi transaksi), outlet/channel tambahan, serta integrasi kontrak mobile v2 tetap terbuka.

Bukti lokal memakai Odoo 19 disposable. Mini-pack lokal mengganti setup kontinuitas Juli dengan fixture master. F4 GitHub menjalankan preflight dan pembanding dua database penuh. Status keseluruhan Paket B tetap HOLD.

## Audit efek samping loader

`load_period_pack.py` mengisi harga DPP, diskon efektif dan `fmcg_seed_promo_ref` pada sale line. `PERIOD_` membatasi promo governed saat load, dan `fmcg_seed_load` menandai konfirmasi impor yang melewati approval native. Log mencatat exception tersebut. Loader tidak membuat pengajuan atau keputusan approval dan tidak mengikat `promo_program_id` untuk 769 referensi. Klaim nominal pada alur invoice membutuhkan binding program. Pemeriksaan ini membuktikan jalur kode loader. Oracle runtime menghitung approval, riwayat penggunaan loyalty dan atribusi promo/klaim pada SO serta invoice. Budget enforcement dengan ledger pagu tersendiri tetap di luar acceptance implementasi saat ini.

Replay batch lama menolak referensi berbeda atau binding promo melalui `_validate_existing_so` pada baris seed. F4 membuktikan mutasi referensi total-sama ditolak oracle, rollback bersih, dan replay bersih. Probe mini-pack baru memasukkan binding legacy tanpa mengubah total, menjalankan replay, memeriksa digest setelah penolakan, lalu mengulang replay bersih.

## Keputusan pemilik dan gate merge

Pemilik menyetujui status UNKNOWN untuk metadata 769 referensi promo yang tidak tercatat, dengan audit harga efektif dan referensi sumber wajib lulus. Cakupan operasional pricing fase ini adalah satu reward nominal tetap, beberapa SKU dalam satu principal dan satu profil pajak. Budget enforcement dan backend order v2 menjadi gate aktivasi terpisah.

Gate operasional disusun bertahap. Correctness atas fakta sumber menjadi syarat merge seeding. Butir playbook yang masih parsial dicatat untuk penetapan cakupan saat re-review. Keputusan merge dan penilaian kecukupan bukti berada pada supervisor/reviewer.

Bukti pada `284e31f809316a2112493aa9c365b3050106d242`: 29 checks lulus. [Install-test 338 tes Odoo](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/45610697200/job/139193371850) dan [artefak F4](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/45610697265/artifacts/15025901192). F4 membuktikan 2.350 line, 769 referensi belum terpetakan, digest dua DB identik, replay zero drift, rollback dan recovery. GL stok Rp11.997.744.800, AR Rp2.368.135.989,94 dan AP Rp7.666.137.600 cocok.

| Gate | Syarat penutupan | Status |
| --- | --- | --- |
| Correctness loader | Harga, identitas, owner, kronologi, lot, dokumen dan ledger mengikuti sumber. Sertakan native role chain, kontrol negatif, audit seluruh dataset dan bukti CI exact SHA. Probe replay binding lama dan assertion efek samping historis harus lulus pada F4 exact SHA. | PARTIAL |
| Cakupan B-04/B-05 | Native fixed order reward, satu principal, profil pajak seragam, alokasi beberapa SKU, footer dan mutasi total-sama sudah terbukti. Pemilik menyetujui batas kombinasi ini. Tunggu penilaian supervisor atas hasil integrasi. | PARTIAL |
| Cakupan B-07 | Audit harga efektif dan linkage historis lulus. Pemilik menerima UNKNOWN untuk komposisi, aktor approval dan atribusi yang hilang. Bukti oracle tambahan menunggu F4 exact SHA. | PARTIAL |
| Acceptance playbook A/C/D | Tetapkan PJP/reservasi, trip/FEFO, retur, identitas Coretax, kas dan alur biaya per butir. Ketidaktepatan pada fakta yang tersedia memblokir merge. Keterbatasan sumber memerlukan batas dan persetujuan eksplisit. | OPEN |
| Aktivasi fitur | Budget enforcement memerlukan kebijakan dan tes concurrency ketika diimplementasikan. Order v2 memerlukan owner, PR, dan integrasi terpisah. Flag live tetap OFF. | OPEN |

Cakupan playbook per tahap tetap tunduk pada re-review supervisor. Rekomendasi kebijakan budget dan pembagian beban tetap usulan supervisor. Status B-01/B-03/B-06 tetap CLOSED.
