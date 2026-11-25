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
| B-02 | Sales, promo eligible, Supervisor | Pending memblokir, Supervisor menyetujui, program tidak eligible ditolak | Wizard native `test_governed_native_promo_requires_supervisor` dan siklus monitoring existing. Kontrak budget dan outlet masih terbuka | PARTIAL |
| B-03 | Sales, tactical Tier0, Supervisor untuk monitoring promo | Batas persis Tier0, promo tetap monitoring | `test_21c_mixed_order_in_free_zone_still_needs_supervisor_promo_monitoring` | CLOSED |
| B-04 | Sales, approval berjenjang, line dan footer | Rp1 juta → Rp950.000 → Rp940.500 → Rp900.000. Tolak pergantian line walau total tetap | `test_tactical_line_stack_and_footer_to_reconciliation` lulus dengan role nyata dan mutasi komposisi total tetap. Kombinasi satu promo nominal resmi dan satu line dibuktikan lewat `test_fixed_official_promo_before_tactical_stack_and_footer`. Matriks program-first yang lebih luas masih terbuka | PARTIAL |
| B-05 | Sales, beberapa SKU dan principal | Alokasi nominal presisi, remainder, aturan principal, kontrol pergeseran alokasi | `test_footer_rounding_remainder_is_allocated_once` dan existing tier per principal. Integrasi multi-principal dengan promo belum diuji | PARTIAL |
| B-06 | Sales dan approver, riwayat pada window WITA | Boundary tier, crossing, bobot nilai, isolasi company/outlet/salesman | Existing `test_approval_engine.py` memberi regresi dasar | CLOSED |
| B-07 | Sales, approver, gudang, akuntansi | Harga, diskon, DPP, pajak, invoice link, residual, jurnal, replay dan rollback | Golden chain tactical sampai rekonsiliasi dan mini-pack historis lulus secara lokal. Golden chain gabungan satu promo nominal dan satu line mencapai settlement. Cakupan historis gabungan tetap terbatas oleh register | PARTIAL |

## Dependency order v2

DS_RECONCILIATION K4/K13 B2, kontrak order v2 dan feature gate `features.order_pricing_v2`. PWA mendukung preview line/footer dan program. Handler backend legacy belum menerima pricing v2 maupun memberikan snapshot program yang sah. PR backend terpisah diperlukan untuk schema submit/revise, quote dan validasi otoritatif, budget lifecycle, idempotensi UUID, serta integrasi browser/backend. Owner pekerjaan adalah pelaksana backend mobile yang ditunjuk project. Status OPEN, belum ada PR backend yang teridentifikasi untuk aktivasi ini. Flag live tetap mati. K5 tidak memblokir Paket B.

## Implementasi dan batas pembuktian

- Aksi server tactical menyimpan stack dan footer teralokasi. Aplikasi diskon memakai diskon efektif native supaya tagihan hanya memotong sekali. Presisi yang tidak bisa dinyatakan pada line native ditolak. Aksi ini mendukung satu promo nominal resmi dengan satu line barang. Reward native tetap terpisah dan menjadi basis alokasi. Kombinasi lain masih membutuhkan pembuktian. Integrasi promo + tactical existing tetap memiliki satu rantai tactical.
- Snapshot approval mengikat komposisi dan diskon, SKU/UoM, kuantitas, harga, pajak, program/reward dan konteks perusahaan/outlet/Sales. Aksi validasi tier memeriksa actor. Perubahan komposisi bernilai total sama, penulisan state langsung, dan role yang salah diuji.
- Mini-pack mengambil `PO-2026-08-01` → `SO-202608-1007` → `INV-202608-1007` → `PAY-AR-02000` langsung dari register. Oracle menguji kode promo sumber, harga, qty, diskon, relasi invoice, nominal dan payment edge. Mutasi metadata promo melalui ORM mempertahankan total, ditolak oracle, lalu di-rollback. Regresi Python menukar persen antar-SKU dengan total yang sama.
- Seluruh 769 line berkode disimpan sebagai referensi historis belum terpetakan. Snapshot dari loader lama yang berisi binding fuzzy perlu ditinjau sebelum replay karena guard akan menolaknya. Kode sumber tidak menjadi klaim atau rekam approval.
- Governance native membatasi promo berpemilik principal ke status approved/active, company sesuai dan order yang produknya satu principal yang cocok. SKU/minimum dan periode memakai engine native. Coverage budget rupiah (termasuk kompetisi transaksi), outlet/channel tambahan, serta integrasi kontrak mobile v2 tetap terbuka.

Bukti lokal memakai Odoo 19 disposable. Mini-pack lokal mengganti setup kontinuitas Juli dengan fixture master. F4 GitHub menjalankan preflight dan pembanding dua database penuh. Status keseluruhan Paket B tetap HOLD.
