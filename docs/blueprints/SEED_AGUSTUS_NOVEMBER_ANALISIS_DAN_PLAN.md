# Seeding transaksi historis Agustus – 4 November 2026: analisis, gap analysis, dan plan

**Penulis:** claude-dev · **Tanggal:** 2026-11-04, diperbarui 2026-11-05 (hari ini Kamis 5 November) · **Basis:** `main` `2b7cdd2` (PR #86)
**Status dokumen:** analisis dan rencana. Tidak ada data, register, loader, gate, atau server yang diubah. Keputusan pemilik K1–K4 dan tiga konfirmasi diterima 2026-11-05 (Bab 9A); K5–K9 memakai usulan sebagai default [A] sampai dikoreksi.
**Penandaan:** [F] fakta bersumber · [A] asumsi · [BU] belum diuji/diverifikasi (AGENTS.md butir 6).

**Acuan setelah keputusan 5 November:** Bab 9A mengesampingkan opsi/rekomendasi lama yang bertentangan. Batas pack adalah **5 November 2026** (81 hari kerja sejak 1 Agustus); mesin harian mulai **6 November**. Judul dan angka sampai 4 November di analisis awal adalah baseline historis perhitungan, bukan batas implementasi terbaru; estimasi volume/biaya perlu dihitung ulang sebelum F1. F6 mengikuti batas 5 November ini. Jalur terpilih adalah A (tambahan per hari-slice tanpa restore menimpa), Juli tetap beku, dan campuran principal organik. K5–K9 serta angka anchor bertanda [A] belum menjadi persetujuan nominal, toleransi, atau kebijakan akuntansi/pajak. Persetujuan rencana bukan izin mengeksekusi seed/menulis database live; preflight, kontrak, pembuktian disposable, serta otorisasi eksekusi sesuai fase tetap wajib. “0 draft” pada audit slice berlaku untuk dokumen seed yang seharusnya selesai pada cut-off, bukan perintah menyelesaikan draft live atau DO carry-forward yang memang harus terbuka.


---

## 0. Ringkasan eksekutif

**Misi.** Melanjutkan seeding transaksi dari 1 Agustus sampai 4 November 2026 di atas Juli yang sudah beku, terverifikasi, dan terpasang di demo Railway, sehingga narasi demo (krisis overstok Juli → hangover Agustus → konsolidasi September → rebound Oktober) terbaca benar di Odoo, PWA, dan dashboard.

**Kesimpulan utama.** Pekerjaan ini bukan "jalankan generator lagi untuk bulan berikutnya". Alasannya:

1. **Tidak ada mesin yang bisa melanjutkan.** `generate_perpetual_transactions.py` adalah mesin satu bulan: tanggal, penomoran (`SO-202607-`), diskon per channel, OPEX, payroll, dan PO (`PO-2026-06-*`) tertanam di kode, tanpa logika pembelian ulang. Loader memeriksa hash 15 register beku dan menegaskan hitungan tetap (1.324 SO, 967 AR, 4 AP, 30 OPEX, 150 SKU, 9 retur). Gate seed hanya mengenal periode 1–31 Juli.
2. **Juli yang beku tidak sama dengan narasi yang dijadikan acuan Agustus–Oktober.** Margin bersih Juli di register 4,12% (narasi 0,9%), OPEX Juli terkurang kira-kira Rp150 juta dari rincian narasi, tolakan Juli 0,038% dari omzet kotor (narasi 3,8%), pangsa MT 31,8% (narasi 44,5%), campuran principal berbeda jauh dari 34/28/20/18. Jika Agustus mengikuti narasi apa adanya, grafik margin dan tolakan akan bergerak ke arah yang salah.
3. **Tiga dokumen narasi saling bertentangan** (blueprint, macro ledger, `historical_simulation_summary.json`). Salah satu harus ditetapkan sebagai acuan.
4. **Dua fondasi akuntansi belum ada**: saldo kas/modal awal (arus kas Juli tanpa saldo awal minus Rp3,16 miliar) dan PPN masukan atas pembelian.
5. **Jalur deploy belum diputuskan.** Demo Railway berisi data hidup dan ada keputusan pemilik "tidak ada reset/restore yang menimpa data". Menambah ±3.500 SO langsung ke server dan membangun di sandbox lalu restore adalah dua jalur dengan risiko berbeda.

**Rekomendasi.** Bangun **"period pack"** per bulan (register baru bernama berbeda, manifest hash sendiri, Juli tidak disentuh) dengan **mesin lanjutan** yang membaca keadaan penutupan Juli, ditambah **Kontrak Seed v2** yang memperluas gate secara eksplisit (tanpa allowlist). Kerjakan Agustus sebagai pilot, tuning, lalu September, Oktober, dan 1–4 November. Pembuktian runtime di database disposable; jalur ke Railway menunggu keputusan pemilik.

**Keputusan yang dibutuhkan dari pemilik:** Bab 9. Empat yang memblokir desain: (1) batas "hari ini", (2) rekonsiliasi narasi dengan Juli beku, (3) jalur deploy, (4) campuran principal.

---

## 1. Cakupan dan kalender

**Periode.** Sabtu 1 Agustus – Rabu 4 November 2026 (80 hari kerja). Hari ini Kamis 5 November adalah hari kerja ke-81; rekomendasi: jadikan hari live, seed berhenti pada Rabu 4 November (Bab 9, K1).

**Hari kerja resmi** (Senin–Sabtu, dikurangi libur nasional) [F: `scripts/ops/fmcg_calendar.py`, dicocokkan dengan [setneg.go.id](https://setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2026), dibaca 2026-11-04]:

| Bulan | Hari kerja | Pengecualian |
|---|---|---|
| Agustus | 24 | Libur: Senin 17 Agu (HUT RI), Selasa 25 Agu (Maulid Nabi) |
| September | 26 | tidak ada libur nasional |
| Oktober | 27 | tidak ada libur nasional |
| 1–4 November | 3 (2, 3, 4 Nov) | 1 Nov Minggu |
| **Total** | **80** | tidak ada cuti bersama Juli–November; satu-satunya 24 Desember |

Catatan:
- Blueprint menulis hari kerja Juli 26 / Agustus 25 / September 25 / Oktober 22 dan menyebut Tahun Baru Islam di Juli serta Maulid di September. Itu **salah**: Tahun Baru Islam 1448 H jatuh 16 Juni dan Maulid 25 Agustus. `generate_historical_ledger.py` (macro ledger) memakai tanggal libur yang sama-sama salah (16 Jul, 4 Sep). Kalender kanonikal sudah benar; **acuan tunggal harus `fmcg_calendar.py`**.
- Docstring `fmcg_calendar.py` menyebut "SKB Nomor 1017 Tahun 2025". Dasar hukum menurut setneg: SKB Menag No. 1497, Menaker No. 2, MenPANRB No. 5 Tahun 2025. Koreksi docstring kecil, tanpa dampak data.
- 1 Agustus (Sabtu) hari kerja penuh: 48 DO/faktur carry-forward bertanggal 1 Agustus **dan** panggilan PJP 1 Agustus yang belum ada di register mana pun.

**Perkiraan volume [A]** dari target omzet narasi (Agu 4,235 M; Sep 3,96 M; Okt ≈ 6,3 M sebulan penuh dari 5,3 M MTD 24 Okt; 1–4 Nov ≈ 0,7 M), memakai rasio Juli (229 SO per Rp1 miliar omzet, 2,07 baris per SO):

| Item | Perkiraan |
|---|---|
| Omzet DPP bersih | ≈ Rp15,2 miliar |
| SO / DO / faktur | ≈ 3.500 masing-masing |
| Baris SO | ≈ 7.200 |
| Pelunasan AR | ≈ 3.000 (Juli: 967 dari 1.276 faktur ≈ 76% terbayar dalam bulan; ditambah 357 piutang Juli dan 1 Agustus yang terbawa) |
| PO masuk | ≈ 12–20 (ditentukan mesin ROP, bukan angka tetap) |
| Waktu loader | ≈ 65–80 menit (acuan: runner penuh 1.324 SO ≈ 25 menit di CI) |

---

## 2. Titik tolak: yang sudah ada

### 2.1 Data (Juli beku) [F]
- 15 register kanonikal di `data/registers/` beku (hash SHA-256 di `canonical_financial_reconciliation_july_2026.json`); pemilik melarang regenerasi (`docs/DEMO_ENVIRONMENT_SCOPE_DECISION.md`).
- Juli: 1.324 SO, 2.738 baris, gross DPP Rp6.065.892.600, diskon Rp281.242.486, net order Rp5.784.650.114; 1.276 faktur Juli (DPP Rp5.594.622.485) + 48 faktur carry-forward 1 Agustus (DPP Rp187.858.691,40); COGS diterima Rp4.969.777.800; laba kotor Rp624.844.685 (11,17%); OPEX Rp394.350.000; laba bersih Rp230.494.685 (4,12%).
- Keadaan 31 Juli: stok 53.837 karton (Rp9.001.139.000; reserved 1.038 untuk 48 DO 1 Agustus); AR terbuka DPP Rp2.135.470.252,80 (309 faktur); AP terbuka Rp2.899.971.200 (PO-2026-06-05 Unilever, jatuh tempo 8 Agustus); karantina 9 karton.
- Master: 354 outlet dengan `cohort_date` (Jul 182, Agu 30, Sep 30, Okt 112), 150 SKU, 4 principal, 7 salesman/canvasser, 6 kendaraan terpakai dari 9.

### 2.2 Sistem [F]
- Loader `CanonicalPerpetualAdapter` (3.184 baris) + runner disposable dua fase + runner upgrade; terbukti hijau di CI (`full-dataset-runtime`, `upgrade-runtime`): 1.324 SO / 1.324 faktur / 967 AR / 4 AP / 30 OPEX, replay zero-drift, 13.540 baris AML Juli imutabel.
- Gate lokal: `verify_seed_invariants.py` dan `verify_seed_acceptance.py`; kontrak `docs/reviews/SEED_INVARIANT_CONTRACT.md`.
- Railway live (`railway`): injeksi kanonikal dicatat berhasil 31 Okt (HANDOFF, PR #52); fixture mobile ditambahkan 30 Okt dengan perlindungan preservasi.

### 2.3 Yang belum ada [F]
Mesin lanjutan, PJP Agustus–November, logika pembelian ulang, saldo kas/modal awal, PPN masukan pembelian, kontrak gate di luar Juli.

---

## 3. Kaidah yang mengikat (dari instruksi pemilik dan kontrak)

| # | Kaidah | Sumber | Konsekuensi untuk Agu–Nov |
|---|---|---|---|
| R1 | Native Odoo dahulu, custom hanya bila perlu | Turn 2 | Pakai SO/picking/invoice/payment/PO native; tidak ada tabel seed khusus |
| R2 | Kerja Senin–Sabtu; Minggu dan libur nasional tutup | Turn 2, `fmcg_calendar.py` | Tidak ada gerakan fisik di Minggu, 17 dan 25 Agustus |
| R3 | Tidak ada celah tidak rasional; narasi dan dinamika presisi | Turn 2 | Anchor bulanan + gate naratif (Bab 8) |
| R4 | SO hanya atas stok yang ada pada hari itu; dirantai ke picklist, DO, faktur | Turn 8–9 | Mesin berbasis saldo fisik/reserved per SKU/lot, FEFO, tanpa stok minus |
| R5 | Pembelian dipicu stok menipis; penerimaan memutar stok | Turn 8 | Mesin ROP + lead time maritim per principal |
| R6 | Kas/transfer atas faktur dan PJP yang tepat; ada simulasi pemajuan tagihan | Turn 8 | Pelunasan terikat faktur; early-discount 1% yang sudah ada |
| R7 | Diskon, OPEX, gaji tanggal 30 bulan berjalan | Turn 8 | Payroll akhir bulan [A: tanggal 30 atau hari kerja terakhir sebelumnya; Juli memakai 31] |
| R8 | Kausalitas per baris sampai ledger | Turn 8, kontrak | Semua gate TX-FK, LINE/HEADER, EVENT-ORDER dipertahankan |
| R9 | Saldo awal dan PO in-transit menentukan SO hari pertama | Turn 9 | Mesin lanjutan wajib mewarisi saldo penutupan, termasuk 48 DO tertunda |
| R10 | Sebaran order per principal diperhatikan | Turn 9 | Lihat G-03 dan K4 |
| R11 | Satu SO satu principal | Pemilik 2026-10-26 (kontrak) | Gate SO-PRINCIPAL berlaku |
| R12 | Hindari angka genap; patokan harga barang | Turn 9 | Nilai dibentuk dari karton × harga × isi; gate heuristik angka bulat |
| R13 | Angka plan adalah DPP di luar PPN | Turn 9 | Semua anchor dalam DPP |
| R14 | Seed terikat model/modul terpasang; jangan terjebak valuasi stok bertanggal hari ini | Turn 9 | Backdating dengan teknik terbukti di loader (bukan SQL `create_date`); audit as-of per akhir bulan |
| R15 | Fakta pajak hanya dari sumber resmi bertanggal | AGENTS.md butir 5 | Lihat G-09 |
| R16 | Gate seed mengikuti kontrak; CI hijau dasar bukan penerimaan; dilarang melebarkan toleransi/allowlist | AGENTS.md butir 9, kontrak | Perluasan periode = perubahan kontrak eksplisit + tes mutasi |
| R17 | Tidak mengedit data server langsung; tidak ada dump di git | AGENTS.md butir 5 | Jalur deploy Bab 7.6 |
| R18 | Tidak ada reset, restore menimpa, atau regenerasi 15 register | Keputusan 30 Okt | Period pack baru; Juli tidak disentuh |

---

## 4. Narasi: acuan versus kenyataan Juli

### 4.1 Tiga sumber narasi yang bertentangan [F]

| Hal | Blueprint (`historical_simulation_and_turnover_model.md`) | Macro ledger (`historical_ledger_day_to_day.csv`) | Ringkasan lama (`historical_simulation_summary.json`) | Register kanonikal Juli |
|---|---|---|---|---|
| Omzet Juli | Rp5,5 M "Net Revenue (Omset DPP)" | gross 5,5 M, net 5,225 M | 5,5 M | invoiced 5,595 M; net order 5,785 M |
| Outlet aktif Juli | 272 | n/a (kolom `active_outlets` harian) | 177 | 178 yang benar-benar order (kohort 182) |
| Outlet Agu / Sep / Okt | 288 / 313 / 354 | n/a | 198 / 226 / 354 | kohort 212 / 242 / 354 |
| Hari libur | 16 Jul, 4 Sep (keliru) | 16 Jul, 4 Sep (keliru) | n/a | resmi: 17 dan 25 Agu |
| Pembelian Agustus–Oktober | PO 18 Agu Rp3,2 M (Mayora & Wings; catatan kausalnya menyebut Santos & Mayora) | masuk Sep 5,7 M, Okt 5,0 M | total inbound 18,27 M | belum ada |
| Stok | awal Rp10 M (stok awal + inbound Juni) | n/a | awal Rp4,3 M | saldo awal 1 Jul 00:00 Rp4,475 M (29.804 karton); puncak 3 Jul Rp10,68 M; 31 Jul Rp9,00 M (53.837 karton) |

**Rekomendasi (K2):** tetapkan acuan = *anchor bulanan yang pernah ditetapkan pemilik* (omzet DPP per bulan, arah margin/diskon/tolakan) **dikunci pada keadaan penutupan Juli kanonikal** dan kohort outlet di registri. Macro ledger, ringkasan lama, dan bagian blueprint yang bertentangan ditandai non-otoritatif.

### 4.2 Juli beku vs narasi Juli [F, dihitung dari register]

| Indikator Juli | Narasi | Register | Selisih dan akibat |
|---|---|---|---|
| Net revenue DPP | 5.500 jt | 5.595 jt (faktur) | +1,7%, dapat diterima |
| COGS / laba kotor | 4.906 jt / 594 jt (10,80%) | 4.970 jt / 625 jt (11,17%) | kecil |
| OPEX | 544,5 jt (9,9%) | 394,35 jt (7,05%) | **−150,15 jt**: tidak ada pemeliharaan armada (34,6 jt) dan "OPEX lain" hanya sewa 45 jt vs 164 jt |
| Laba bersih | 49,5 jt (**0,90%**) | 230,5 jt (**4,12%**) | titik terendah narasi tidak ada di data |
| Tolakan | 3,8% (±Rp209 jt) | 9 karton, Rp2,28 jt = **0,038%** gross | Agustus 2,4% akan terbaca *naik*, bukan membaik |
| Diskon efektif | 5,0% | 4,64% (MT 5,2; GT 4,8; INST 4,0; RTL 3,5) | selaras |
| Pangsa channel (gross) | MT 44,5 / GT 43,6 / Retail+Horeka 11,9 | MT 31,8 / GT 43,1 / RTL 18,0 / INST 7,1 | MT lebih kecil, retail lebih besar |
| Pangsa principal (gross) | Wings 34 / Mayora 28 / Kapal Api 20 / Unilever 18 | Wings 23,0 / Mayora 28,9 / Santos(Kapal Api) 20,6 / Unilever 27,5 | Wings −11 pt, Unilever +9,5 pt |
| Puncak okupansi gudang | 107,4% | 104,15% (kapasitas 2.500 CBM di generator vs 1.800 m³ di blueprint) | beda basis kapasitas |

Catatan: kontrak seed sendiri menyatakan proporsi principal, toleransi omzet, dan kapasitas gudang dari jawaban agen **belum menjadi ketetapan pemilik**. Maka bagian 34/28/20/18 dan 107,4% perlu ditetapkan atau dilepas (K4).

### 4.3 Konsekuensi untuk grafik demo
- **Margin:** narasi 0,9 → 2,5 → 3,7 → 5,0. Dengan Juli 4,12%, Agustus 2,5% tampak sebagai kemerosotan.
- **Tolakan:** narasi 3,8 → 2,4 → 1,8 → 0,8. Dengan Juli 0,038%, seluruh kurva tampak naik lalu turun.
- **Outlet aktif:** jalur 182 → 212 → 242 → 354 di data (loncatan 112 outlet pada 1 Okt, 105 di antaranya kios RTL), sedangkan narasi menggambarkan pertumbuhan bertahap +6%, +8%, lalu penuh.

Pilihan penyelesaian ada di K2.

---

## 5. Gap analysis

Prioritas: **P0** memblokir desain; **P1** harus selesai sebelum seed Agustus layak demo; **P2** kualitas dan kelengkapan.

| ID | P | Gap | Bukti | Dampak | Penutupan |
|---|---|---|---|---|---|
| G-01 | P0 | Narasi vs Juli beku (Bab 4.2–4.3) | register vs blueprint | Grafik margin/tolakan menyesatkan | Keputusan K2, lalu anchor bulanan terversi |
| G-02 | P0 | Acuan target bertentangan (Bab 4.1) | tiga dokumen | Tidak ada oracle tunggal untuk gate naratif | Tetapkan acuan; dokumen lain ditandai non-otoritatif |
| G-03 | P0 | Tidak ada mesin lanjutan; generator satu bulan, `random.seed` global, konstanta Juli, penomoran `202607` | `generate_perpetual_transactions.py` | Tidak bisa menghasilkan Agustus tanpa mengubah Juli | Mesin baru "continuation engine" + period pack (Bab 7) |
| G-04 | P0 | Loader dan gate terkunci Juli: `REQUIRED_CANONICAL_FILES`, hash 15 file, asersi 1.324/967/4/30/150/9; `verify_seed_acceptance` `START/END` Juli, `july()`, AR satu pelunasan penuh per faktur | `load_canonical_perpetual.py` baris 40–120, 2811+; `verify_seed_acceptance.py` baris 18–125 | Pack baru ditolak atau, lebih buruk, lolos tanpa diperiksa | Kontrak Seed v2 + loader berparameter manifest + tes mutasi |
| G-05 | P0 | Jalur deploy belum diputuskan; kondisi live `railway` belum diaudit; fixture mobile 30 Okt menyebut stok awal 100 karton × 150 SKU di WH/Stock dan tidak ada catatan pembersihan setelah injeksi kanonikal 31 Okt | HANDOFF 2026-10-30 19:40 dan 2026-10-31 07:45 | Stok live mungkin bukan 53.837 karton; penambahan transaksi di atas keadaan tak terverifikasi | Preflight read-only; keputusan K3 |
| G-06 | P1 | Tidak ada saldo kas/bank/modal awal. Arus kas register Juli tanpa saldo awal: **−Rp3.163,2 juta** (masuk Rp3.828,7 jt incl. PPN; AP Rp6.597,5 jt; OPEX Rp394,35 jt), titik terendah 31 Juli. Pembukaan stok dimuat via penyesuaian persediaan, bukan jurnal pembukaan ekuitas | analisis register; `load_opening_stock` | Neraca/arus kas dan "kas tidak negatif" tidak bisa dibuktikan; bank Odoo mungkin negatif [BU] | Putuskan saldo awal (K5) + audit bank/kas |
| G-07 | P1 | Tidak ada mesin pembelian: tanpa ROP, PO, lot baru, AP, PPN masukan. Faktur vendor dimuat satu baris lump-sum tanpa `tax_ids` eksplisit, tidak terhubung ke baris PO; pembayaran AP hanya DPP | `load_inbound_pos`, `perpetual_ap_payments.csv` | Tidak ada inbound Agustus–Oktober; PPN masukan tidak tercatat eksplisit (hasil pajak default Odoo [BU]); laporan PPN berpotensi satu sisi | ROP + PO + penerimaan berlot + bill berpajak |
| G-08 | P1 | Tidak ada PJP Agustus–November (hanya `pjp_july_2026_matrix.csv`); tidak ada model permintaan (ARPU per channel, musim, kohort, hari gajian/libur) | register | Tidak ada kunjungan untuk dipasangkan dengan SO (gate PJP-SO) | Generator PJP bulanan dari `pjp_schedule_354` + kohort |
| G-09 | P1 | Pajak: pemilik menyatakan "11% (belum 12%)" (Turn 9); sumber resmi: PMK 131/2024 berlaku 1 Jan 2025, tarif 12% atas DPP nilai lain 11/12, efektif 11% untuk barang non-mewah. Angka register tidak salah, tetapi label ("PPN 11% UU HPP") dan dokumentasi usang; konfigurasi Odoo `12% (Non-Luxury Good)` bernilai 11 sudah benar | [pajak.go.id](https://pajak.go.id/index.php/id/artikel/pmk-1312024-tarif-ppn-sebelas-dua-belas) dibaca 2026-11-04; snapshot Odoo | Risiko salah istilah saat demo pajak/Coretax | Koreksi label; PPN masukan memakai pajak yang sama; sumber bertanggal di kontrak |
| G-10 | P1 | OPEX hanya tiga komponen (logistik Rp3,55 jt/hari, gaji Rp185 jt, lembur Rp68,5 jt, sewa Rp45 jt di Juli). Tidak ada pemeliharaan armada, listrik, penyusutan, bunga/biaya bank, komisi. Teks "6 armada" vs 9 kendaraan. Blueprint Okt: gaji Rp165 jt (alasan tidak dijelaskan) | register OPEX; `vehicles_9.csv` | Margin Agu–Okt tidak bisa mengikuti narasi struktur biaya | Katalog biaya bulanan terversi (K2/K6) |
| G-11 | P1 | Retur/tolakan hampir tidak ada di Juli (9 kejadian); tidak ada nota kredit, penghapusan stok karantina, retur ke principal, atau selisih opname | register retur | Cerita "tolakan turun" dan "retur lama belum dikreditkan" (Sep) tidak punya dokumen | Model tolakan + disposisi karantina (butuh persetujuan lingkup, K7) |
| G-12 | P1 | Target dashboard: satu `id.monetary.target` 1 Jul–31 Okt Rp5,5 M (tafsir per bulan atau total tidak dinyatakan); tidak ada periode November | `id_monetary_target_data.xml` | Dashboard 1–4 Nov tanpa target; grafik target salah tafsir | Target bulanan bertanggal (K5) |
| G-13 | P2 | Semua lot yang ada kedaluwarsa paling cepat 31 Des 2027 | analisis lot | FEFO tidak tampak; cerita kedaluwarsa tidak mungkin | Lot PO baru dengan umur simpan bervariasi; opsional satu cerita near-expiry |
| G-14 | P2 | Armada: registri memakai 6 kendaraan, narasi Okt "9 armada, utilisasi 89%"; PR #81 menyatakan tidak mengarang trip historis | registry; HANDOFF 2026-11-03 | Dashboard utilisasi aset kosong atau tidak selaras dengan narasi | Keputusan lingkup trip (K7) |
| G-15 | P2 | Rentang waktu: loader tidak punya pemeriksaan kinerja untuk ±3.500 SO (memori Railway 1 GB; batch 200 sudah terbukti di Juli) | HANDOFF 31 Okt | Waktu dan kegagalan di tengah jalan | Pack bulanan + titik pulih per bulan |
| G-16 | P2 | Docstring usang: dasar hukum kalender keliru; cuti bersama 24 Des tidak ada di tabel; docstring generator menyebut saldo awal 32.748 karton padahal register 29.804 | `fmcg_calendar.py`; `generate_perpetual_transactions.py` | Tidak berdampak pada data; menyesatkan pembaca | Koreksi kecil |
| G-17 | P1 | Gate CALENDAR tidak independen: `verify_seed_invariants.py` memercayai kolom `is_working_day` dari kartu stok milik dataset sendiri; hanya Minggu yang dikeraskan di kode; pengiriman pada tanggal yang tidak ada di kartu stok lolos (`if deliv_day and ...`); `fmcg_calendar.py` tidak diimpor oleh gate | `verify_seed_invariants.py` baris 96, 163–177 | Pack yang menandai 17 atau 25 Agustus sebagai hari kerja akan lulus gate | Kontrak v2: gate mengimpor kalender tunggal, menolak tanggal di luar kartu stok; tes mutasi |
| G-18 | P1 | Dataset simulasi lama masih di repo: `data/seed/sales_orders_historical.csv` 3.762 SO (1 Jul–24 Okt; Agu 962, Sep 975, Okt 823; Juli 1.002 vs 1.324 di register). Loader lama melarangnya; `init.sh` hanya memanggil `load_fmcg_seed.py` | `data/seed`, `load_historical_simulation.py` baris 8, `deploy/init.sh` | Godaan memakainya sebagai "sumber Agustus–Oktober"; bertabrakan dengan register kanonikal | Tandai arsip non-otoritatif; tidak dipakai mesin baru |
| G-19 | P1 | Tidak ada piutang jatuh tempo di Juli: 0 dari 309 faktur terbuka lewat jatuh tempo pada 31 Juli; MT (TOP 30/45) rata-rata membayar 7,2 hari, GT 8,7, INST 9,8 (kisaran 5–14), selalu lunas sekali bayar. Sebaliknya 33 dari 59 outlet berpiutang terbuka (termasuk 48 faktur 1 Agustus) melampaui limit kredit (basis total incl. PPN [BU basis hitung `id_base`]; mis. CUST-MT-04 Rp166,9 jt vs limit Rp80 jt) karena loader memakai konteks `fmcg_seed_load` yang melewati pemeriksaan kredit | analisis register; `id_base/models/sale_order.py` baris 127, 249 | Aging AR dan dashboard kredit tanpa cerita (tidak ada bucket 1–30/31–60/61–90, tidak ada outlet menunggak), sekaligus limit `strict` dilanggar massal tanpa penjelasan | K9: perilaku bayar Agustus dst. dan perlakuan limit kredit |
| G-20 | P2 | Jebakan kunci alami: nama principal/outlet/produk sengaja difiksionalkan dengan ejaan khusus ("PT Sayapp Mas Utamma", "PT Mayyora Indahh Tbk", "PT Unilevr Indonezia Tbk", "FreshhMart ...", "Rroma ..."); loader mencari partner via kode lalu nama persis | header PO Juni; `load_canonical_perpetual.py` baris 1857 | PO/SO baru dengan ejaan "benar" gagal (KeyError) atau menggandakan partner | Mesin mengambil nama dari register/master, tidak mengetik ulang; gate identitas |
| G-21 | P1 | Modal kerja Agustus: tanpa saldo awal, kas kumulatif Juli minimum −Rp3,163 M (31 Juli); pelunasan Unilever Rp2,9 M jatuh tempo 8 Agustus mendahului sebagian besar tagihan Agustus. Estimasi kasar [A]: agar kas ≥ 0 hingga tanggal itu dibutuhkan saldo awal ± Rp4–4,5 M, atau fasilitas kredit modal kerja (overdraft) dengan bunga di OPEX | analisis register | "Krisis kas" dapat diceritakan tanpa saldo bank negatif palsu bila dimodelkan sebagai fasilitas | K5 diperluas: modal awal vs fasilitas |

---

## 6. Tantangan dan risiko

1. **Mengikat ke Juli yang beku sambil mengejar narasi.** Setiap penyimpangan Juli dari narasi harus dibaca sebagai fakta, bukan diperbaiki (K2).
2. **Kapasitas stok membatasi omzet.** Pada kecepatan Agustus (73% Juli), hanya 4 SKU (3 Santos, 1 Unilever) habis sebelum ±3 September tanpa pembelian baru; tetapi tingkat persediaan antar principal timpang (hari kerja cover pada laju Juli: Santos 35, Unilever 43, Wings 53, Mayora 55) dan 25 SKU punya cover < 30 hari kerja. Lonjakan Oktober (≈ Rp6,3 M) mengikis cover lebih cepat; stok-out akan muncul sebagai omzet hilang dan harus diatur mesin, bukan dipaksa.
3. **PO Agustus pada narasi menyasar principal yang salah.** Wings dan Mayora punya cover terbesar; yang paling perlu ROP lebih dulu adalah Santos dan Unilever. PO 18 Agustus "Mayora & Wings" tidak konsisten dengan posisi stok maupun dengan catatan kausal blueprint sendiri ("Santos & Mayora").
4. **Kebutuhan pembelian tidak bisa ditebak dari narasi saja.** COGS Agu–4 Nov ≈ Rp13,4 M terhadap stok 31 Juli Rp9,0 M. Jika stok akhir diharapkan ±Rp4,7–5 M (macro ledger 24 Okt), pembelian ≈ Rp9–10 M. Angka akhir ditentukan simulasi ROP dan harus tampak wajar di sisi AP (TOP 21/28/30/35 hari) dan kas.
5. **Beban kas.** Pelunasan Unilever Rp2,9 M jatuh tempo 8 Agustus; piutang terbuka DPP Rp2,14 M. Tanpa saldo awal, kas Agustus akan negatif di buku.
6. **Gate harus diperluas tanpa melonggar.** Kontrak melarang allowlist, pelebaran toleransi, dan `continue-on-error`. Setiap perubahan butuh tes mutasi yang gagal pada pelanggaran.
7. **Live demo berjalan di data yang sama.** Pengguna PWA dapat membuat SO live (PR #82). Seed historis harus berhenti sebelum "hari live" supaya aksi demo tidak bertabrakan dengan stok/reservasi seed.
8. **Pertentangan tahap operator:** keputusan 30 Okt melarang restore yang menimpa data, sementara membangun offline lalu restore adalah jalur yang paling aman secara runtime (Bab 7.6).
9. **Waktu dan memori loader pada 3.500 SO** (Bab 1) di Railway 1 GB.

---

## 7. Rancangan solusi

### 7.1 Prinsip
Planner murni (tanpa Odoo) menghasilkan register; eksekutor ORM memuatnya. Deterministik penuh. Juli tidak disentuh. Satu pack per bulan, bisa diverifikasi dan dimuat sendiri-sendiri (skill `odoo-seed-and-verify`: uji satu bulan dulu → tuning → seluruh periode).

### 7.2 Struktur berkas
```
data/registers/periods/2026-08/…   (SO, lines, deliveries, rejections, invoices,
data/registers/periods/2026-09/…    ar_collections, ap_payments, opex, stock_cards,
data/registers/periods/2026-10/…    stock_event_ledger, po_headers, po_lines,
data/registers/periods/2026-11/…    pjp_matrix, narrative_report.json)
data/registers/periods/MANIFEST.json   (hash tiap berkas, hash 15 register Juli, SHA commit generator,
                                        versi anchor, versi katalog biaya, tanggal sumber pajak)
```
Penomoran per bulan (`SO-202608-0001`, `DO-…`, `INV-…`, `PAY-AR-…`, `PO-2026-08-01`), tidak bertabrakan dengan Juli.

### 7.3 Mesin lanjutan (`scripts/ops/generate_period_pack.py`)
1. **Warisan keadaan** dari register Juli: replay `perpetual_stock_event_ledger` → saldo per SKU/lot/reserved/karantina; faktur terbuka (309 + 48), AP terbuka, 48 DO tertunda 1 Agustus. Bukti: hasil replay harus sama dengan laporan rekonsiliasi Juli (53.837 / 1.038 / 9).
2. **Aliran acak per tujuan:** `random.Random(sha256(seed, aliran, tanggal, kunci))`; tidak ada `random.seed` global; semua himpunan diurutkan; hasil identik pada beberapa `PYTHONHASHSEED`.
3. **PJP bulanan** dari `pjp_schedule_354` (frekuensi F1/F2/F4, hari panggil, salesman) dan `cohort_date`; tidak ada panggilan sebelum kohort aktif, tidak ada di Minggu/libur; 1 Agustus ikut.
4. **Model permintaan:** ARPU per channel per bulan sebagai indeks terhadap Juli (parameter terversi), pola mingguan, efek menjelang libur, hari gajian akhir bulan, kohort baru dengan kurva "ramp-up" (mis. kios baru memesan lebih kecil di bulan pertama). Untuk Agustus, mencapai Rp4,235 M dengan 212 outlet berarti ARPU per outlet turun ±38% dari Juli (Rp32,5 jt → ±20 jt): perlu dinyatakan sebagai pelemahan daya beli, bukan kebetulan hitung.
5. **Alokasi stok:** hanya stok available (fisik − reserved), FEFO, tidak kedaluwarsa; SO satu principal; pengecekan batas kredit outlet (mode `strict`/`limit` dari master) agar order tidak melampaui limit tanpa cerita.
6. **Pembelian:** ROP per SKU (cover target dalam hari kerja + stok pengaman), PO per principal, lead time maritim (Santos/Wings 10–12, Mayora 13–15, Unilever 14–16 hari kerja; blueprint Bab 5.B), tanggal terima mengikuti kalender, lot baru dengan umur simpan bervariasi, TOP principal (21/28/30/35). PO justifikasi tertulis di `po_headers` (cover prediksi saat order).
7. **AR/AP:** pelunasan terikat faktur; early-discount 1% sebagaimana Juli; pembayaran parsial hanya jika kontrak v2 menambahkan skema; satu kasus piutang macet bila disetujui (K7). AP dibayar pada jatuh tempo, dengan PPN masukan.
8. **OPEX dan payroll** dari katalog biaya bulanan terversi (logistik harian proporsional ritase, gaji, lembur, sewa/listrik, pemeliharaan armada, penyusutan, biaya bank), sesuai keputusan K2 dan K6.
9. **Keluaran tambahan:** `narrative_report.json` (omzet, diskon, margin, tolakan, outlet aktif, okupansi, DSI, kas, AR/AP per bulan) untuk dibandingkan dengan anchor.

### 7.4 Loader
Perluas `CanonicalPerpetualAdapter` agar menerima manifest period pack: nama berkas, penanda opening/cut-off, dan asersi hitungan dibaca dari manifest (bukan konstanta 1.324/967/…); fingerprint 15 register Juli tetap diverifikasi; pack diverifikasi dengan manifest tersendiri. Teknik backdating yang sudah terbukti di Juli dipakai ulang, bukan SQL `create_date` (pemeriksaan model valuasi aktual Odoo 19 tetap dilakukan sebelum implementasi, sesuai kontrak). Idempotensi: replay harus membuat 0 record.

### 7.5 Kontrak Seed v2 (`docs/reviews/SEED_INVARIANT_CONTRACT.md`)
Perubahan eksplisit dengan referensi instruksi pemilik; tanpa allowlist baseline. Gate baru di Bab 8.

### 7.6 Jalur deploy (K3)

| | A. Tambah bertahap ke DB live `railway` | B. Bangun di sandbox/CI, dump, restore ke Railway |
|---|---|---|
| Sesuai keputusan 30 Okt (tidak menimpa data) | ya | **tidak** tanpa otorisasi baru |
| Risiko ke akun/fixture TEST dan sesi PWA | rendah | akun TEST/fixture ikut tertimpa kecuali dimigrasi |
| Risiko runtime | tinggi: 1 GB RAM, ±70 menit, kegagalan di tengah menyisakan keadaan sebagian | rendah: dibuktikan di disposable, restore ±menit |
| Pembuktian | audit terhadap server hidup (mutasi di prod) | snapshot dibandingkan dengan referensi (pipeline verify) |
| Yang dibutuhkan | preflight read-only, backup, jendela pemeliharaan, guard `railway` di runner disposable harus dibahas | backup, `RESET_DB` + `SEED_URL/SHA256`, rencana migrasi fixture |

Rekomendasi [A]: **B bila pemilik mau memberi otorisasi satu kali**; jika tidak, **A per bulan** dengan titik pulih (backup sebelum tiap bulan). Keduanya didahului preflight read-only keadaan live (G-05).

---

## 8. Gate penerimaan yang diusulkan (Kontrak v2)

**Dipertahankan dan diperluas ke Juli + seluruh pack:** MASTER-*, COHORT-PJP/SO, SO-PRINCIPAL, PJP-SO, CALENDAR (kalender resmi), LINE/HEADER/PO/STOCK-MATH, TX-FK/COVERAGE/IDENTITY, EVENT-ORDER, COLLECTION, LOT-BALANCE/FEFO/EXPIRY, INPUT-SCHEMA.

**Baru:**

| ID | Invariant |
|---|---|
| PERIOD-CONTINUITY | Pembukaan setiap pack = penutupan pack/Juli sebelumnya per SKU/lot, faktur terbuka, AP terbuka, DO tertunda |
| NUMBERING | Nomor dokumen unik, monoton, tidak bertabrakan dengan Juli |
| STOCK-NONNEG | Tidak ada stok fisik/available negatif per SKU/lot per hari |
| PO-CAUSALITY | Setiap PO punya pemicu ROP; terima ≥ order + lead time minimal principal; terima di hari kerja |
| AP-TERMS / AR-TERMS | Jatuh tempo = terima/faktur + TOP; pembayaran terikat dokumen dan tidak mendahului |
| CASH-NONNEG | Saldo kas/bank harian tidak negatif, diberi saldo awal yang disahkan (K5) |
| TAX-SOURCE | PPN keluaran/masukan dari konfigurasi pajak bertanggal dan bersumber resmi (R15), bukan angka dari ingatan |
| NARRATIVE-ANCHORS | Omzet, diskon, margin, tolakan, outlet aktif per bulan dalam pita yang ditetapkan pemilik; konfigurasi terversi, tidak dapat dilebarkan oleh worker |
| FLEET-CAPACITY | Karton/CBM per kendaraan per hari ≤ kapasitas (analisis Turn 7) |
| ROUND-NUMBER | Total SO/faktur/pembayaran tidak berupa angka bulat buatan (R12) |

**Runtime Odoo (database disposable, image dan modul persis calon deploy):** neraca saldo seimbang; GL persediaan = Σ valuasi; AR/AP aging = GL; PPN masukan/keluaran = laporan pajak; analytic terisi; tidak ada dokumen draft tertinggal; jumlah dokumen per jenis; margin per channel dalam rentang wajar; replay 0 record baru; imutabilitas Juli (13.540 baris AML) dan akhir tiap bulan; hasil identik pada tiga `PYTHONHASHSEED`; snapshot dibandingkan dengan referensi. Semua dalam bentuk skrip PASS/FAIL, bukan pemeriksaan manual.

---

## 9. Keputusan dan konfirmasi yang dibutuhkan

| # | Pertanyaan | Opsi dan rekomendasi |
|---|---|---|
| **K1** | Batas "hari ini" (hari ini Kamis 5 Nov) | (a) Kamis 5 Nov **sebagai hari live**: seed sampai Rabu 4 Nov, DO 5 Nov berupa dokumen siap kirim [rekomendasi, aman bagi demo live dan PWA]; (b) seed termasuk 5 Nov dengan SO terbuka |
| **K2** | Juli beku vs narasi (margin 4,12 vs 0,9; tolakan 0,038 vs 3,8; OPEX −Rp150 jt) | (a) **Juli tetap**, anchor Agu–Okt dikalibrasi ulang agar arah sejalan (margin naik dari 4,12%, tolakan turun dari level kecil); narasi "Juli krisis margin 0,9%" tidak tampil; (b) catat biaya Juli yang tak terekam sebagai jurnal bertanggal 31 Juli (Rp150,15 jt) lewat perubahan kontrak imutabilitas; dampaknya Juli berubah; (c) regenerasi Juli: **dilarang**. Rekomendasi: (a) kecuali pemilik ingin tampilan margin 0,9% |
| **K3** | Jalur deploy | A atau B (Bab 7.6) |
| **K4** | Campuran principal dan pangsa channel | Pakai organik Juli (W 23 / M 29 / KA 21 / U 27,5; MT 32%) atau tetapkan 34/28/20/18 dan MT 44,5% sebagai mandat, dengan konsekuensi pergeseran bertahap |
| K5 | Saldo awal kas/modal atau fasilitas kredit modal kerja (G-21); basis dan toleransi target bulanan (gross/net/tolakan); target Nov di `id.monetary.target` | Usulan: modal/kas awal ditetapkan agar kas minimum Juli–Nov ≥ 0; anchor = net DPP setelah diskon, sebelum tolakan; pita ±3% |
| K6 | Katalog biaya (pemeliharaan armada, listrik, penyusutan, bunga/bank, komisi) dan tanggal gaji | Usulan: ikuti rincian blueprint Juli–Okt; gaji tanggal 30 (atau hari kerja sebelumnya); jelaskan gaji Okt Rp165 jt |
| K7 | Plot opsional: 1 piutang macet, retur/tolakan dengan disposisi karantina, selisih opname, backorder, trip armada | Pilih yang masuk; default hanya yang menopang narasi tolakan |
| K8 | PPN masukan dan label pajak | Usulan: faktur vendor berpajak sama dengan konfigurasi Odoo; label "PPN 12% atas DPP nilai lain 11/12 (efektif 11%)" |
| K9 | Perilaku bayar dan limit kredit (G-19) | Usulan: mulai Agustus sebagian MT/GT membayar mendekati atau lewat TOP (terbentuk bucket aging), 2–3 outlet menunggak, satu kasus macet bila K7 setuju; limit kredit `strict` dipatuhi mulai Agustus, dan pelanggaran Juli dibaca sebagai plot "limit dilonggarkan saat krisis push" |

---

## 9A. Keputusan pemilik (2026-11-05) dan dampaknya pada desain

| # | Keputusan | Dampak |
|---|---|---|
| K1 | Batas seed Kamis 5 Nov (hari kerja ke-81; DO 6 Nov berstatus siap kirim, pola carry-forward 1 Agustus). Mesin harian dengan pemicu manual **hanya untuk 6 Nov dan seterusnya** | Dua mekanisme, satu planner: (1) **period pack** Agustus–5 Nov dihasilkan offline dari penutupan Juli; (2) **mesin harian** 6 Nov+ yang membaca keadaan dari database. Planner murni yang sama dipakai keduanya; tes kontinuitas membuktikan hasil pack sampai 5 Nov sama dengan keadaan awal mesin harian |
| K2 | Juli beku. Kalibrasi hanya perilaku Agustus+: biaya (katalog OPEX), retur/tolakan (nota kredit, karantina, penghapusan), dan diskon (disetujui) | Kurva sasaran [A]: margin bersih 4,1 → ±2,5 → ±3,7 → ±5,0 (Jul→Okt); tolakan 0,04 → 2,4 → 1,8 → 0,8. Titik "Juli 0,9%" dilepas dan skrip demo memakai kalimat yang benar. Pita NARRATIVE-ANCHORS dikunci di konfigurasi terversi |
| K3 | Opsi A: tambah ke database live, tanpa timpa/restore. Micro-slicing wajib **presisi** | Lihat spesifikasi slice di bawah. Guard loader (menolak `railway`) harus diadaptasi, direview, dan diuji di disposable berisi data pembanding sebelum menyentuh server (keputusan 30 Okt). Backup DB + filestore sebelum tiap blok bulan |
| K4 | Opsi A: campuran principal organik | Titik awal W23 / M29 / KA21 / U27 (data Juli: campuran sama di semua channel, jadi tidak bergeser sendiri). Tanpa mandat 34/28/20/18; laporan naratif hanya mencatat deviasinya |
| Diskon | Ikut dikalibrasi (4,64% → ±2,5% → 2,0%) | Pengungkit utama margin kotor; konfigurasi terversi per bulan |
| Pemicu | **Perintah shell**, dijalankan antigravity atas permintaan pemilik (bukan wizard di Odoo) | `scripts/ops/seed_day.py` via `odoo shell`; default dry-run (cetak rencana, digest, preflight), `--apply` eksplisit; satu tanggal per eksekusi; binding exact project/environment/database dan opt-in demo; hasil dicatat di agent-log dan HANDOFF oleh pelaksana |
| Dokumen live PWA | **Fakta** | Stok tersedia dikurangi reservasi/penjualan dokumen live; mesin tidak mengubah, menghapus, atau membayarkan dokumen live (dilaporkan sebagai item terbuka) [A]. Dokumen live = tanpa penanda `fmcg_seed_batch` |

**Spesifikasi slice (presisi, toleransi nol, `Decimal`):**
1. **Satu slice = satu hari kerja, atomik.** Gagal berarti rollback penuh; tidak pernah setengah hari.
2. **Preflight:** stok per SKU/lot dan reservasi, AR/AP terbuka, nomor urut terakhir per jenis dokumen, dan penanda penutupan slice sebelumnya harus sama dengan keadaan database, selisih hanya boleh berasal dari dokumen live yang dikenali dan dicatat. Selain itu: berhenti dan lapor, tidak menebak.
3. **Idempoten:** kunci = tanggal + digest rencana; ulang = 0 record baru; slice tidak boleh melompati hari yang belum ada.
4. **Deterministik:** aliran acak per (tanggal, aliran), himpunan diurutkan, zona WITA, hasil sama pada `PYTHONHASHSEED` berbeda.
5. **Audit penutupan per slice** (PASS/FAIL tercatat): stok fisik ≥ 0 dan reserved ≤ fisik; AR/AP terbuka = buku besar; 0 draft; jumlah dan nilai dokumen = rencana; kalender resmi; SO satu principal; penomoran monoton.
6. **Penanda penutupan** ditulis di akhir slice (tanggal, digest, jumlah dokumen, saldo) dan menjadi dasar preflight berikutnya.

Gate baru yang ditambahkan ke Kontrak v2: SLICE-ATOMIC, SLICE-IDEMPOTENT, LIVE-AS-FACT, PACK-TO-DAILY-CONTINUITY.

K5–K9 belum dijawab; usulan pada Bab 9 dipakai sebagai default [A] dan akan dikoreksi bila pemilik berbeda.

---

## 10. Plan bertahap

| Fase | Isi | Keluaran | Gate keluar |
|---|---|---|---|
| F0 | Jawab K1–K8; preflight **read-only** keadaan live; rekonsiliasi dengan penutupan Juli kanonikal | `state_20260801.json`, keputusan tercatat | Pemilik menyetujui; keadaan live dipahami (stok, kas, fixture, pajak) |
| F1 | Kontrak v2 + spesifikasi pack + tes mutasi (merah dulu) | PR dokumen/tes | Tes baru gagal pada pelanggaran |
| F2 | Mesin lanjutan + PJP + demand + ROP + katalog biaya | generator, tes reprodusibilitas | Hash sama di tiga `PYTHONHASHSEED` |
| F3 | **Pilot Agustus** (+ pengecekan arah ke September) | pack 2026-08, `narrative_report` vs anchor | Gate lokal v2 hijau; tinjauan pemilik terhadap grafik |
| F4 | Loader berparameter manifest | PR loader + tes | Juli identik, replay 0 record |
| F5 | Runtime disposable penuh: Juli+1 Agu → Agustus | laporan audit | GL/stok/AR/AP/PPN cocok; imutabilitas Juli |
| F6 | September, Oktober, 1–3/4 November (satu per satu) | pack 09/10/11 | idem per bulan |
| F7 | Verifikasi menyeluruh: dump, snapshot, perbandingan, dashboard PWA vs oracle, `DEMO_SCRIPT` | referensi snapshot, skrip demo | Semua gate hijau pada SHA akhir |
| F8 | Deploy sesuai K3 (opsi A): pack dimuat ke database live per hari-slice, backup per bulan, probe pascadeploy, HANDOFF. Dijalankan antigravity | bukti | Persetujuan pemilik |
| F9 | **Mesin harian 6 Nov+** (`seed_day.py`): uji di disposable berantai 5→6→7 Nov, uji drift (sisipkan SO live, ubah stok, ulang tanggal, gagal di tengah slice) | skrip, tes, runbook pemicu | Semua gate slice hijau; drift terdeteksi dan berhenti, bukan menebak |

Catatan perubahan 2026-11-05: F2 membangun satu planner murni yang dipakai pack dan mesin harian; F4 menambah slice loader dan adaptasi guard database live; F0 mencakup snapshot read-only database live (`scripts/ops/odoo_snapshot.py`, dijalankan pemilik/antigravity tanpa menaruh kredensial di repo).

Setiap fase: cabang `agen/<topik>`, PR, CI hijau, entri HANDOFF/agent-log, commit bertanda tangan agen.

---

## 11. Narasi demo yang akan terbaca (usulan `DEMO_SCRIPT`)

1. **Awal Agustus:** pelunasan Unilever Rp2,9 M (jatuh tempo 8 Agu) ditopang tagihan piutang Juli; tekanan kas.
2. **Agustus "hangover":** omzet turun ±23%, diskon dinormalkan, belum ada kontainer masuk, lembur dipangkas.
3. **17 dan 25 Agustus:** libur; order menumpuk di hari kerja sebelumnya.
4. **Pertengahan Agustus:** PO pertama dipicu ROP (Santos dan Unilever lebih dulu), tiba awal September.
5. **September:** inbound masuk ke lokasi rak, FEFO berjalan, +30 outlet (Tuminting/Singkil RTL; GT Tomohon, Madidir, dst).
6. **1 Oktober:** +112 outlet (105 kios RTL), utilisasi armada naik; **Oktober** rebound menuju ≈ Rp6,3 M, sinyal tambah armada.
7. **Akhir Oktober–awal November:** stok awal festival akhir tahun.
8. Plot opsional K7.

---

## 12. Sumber

- Repo: `docs/blueprints/historical_simulation_and_turnover_model.md`; `docs/reviews/FULL_CONVERSATION_TRANSCRIPT_2026-10-25.md` (Turn 2, 8, 9); `docs/reviews/ARCHITECTURAL_DECISIONS_AND_ROLLBACK_2026-10-25.md`; `docs/reviews/SEED_INVARIANT_CONTRACT.md`; `docs/reviews/FULL_DATASET_RUNNER_AND_CUTOFF_PLAN.md`; `docs/DEMO_ENVIRONMENT_SCOPE_DECISION.md`; `docs/DEMO_EXISTING_ACTIVATION.md`; `docs/finance/GAP_ANALYSIS.md`, `ACCEPTANCE_CONTRACT.md`; `docs/HANDOFF.md` (entri 2026-10-30/31); `data/registers/canonical_financial_reconciliation_july_2026.md`; `scripts/ops/generate_perpetual_transactions.py`; `scripts/load_canonical_perpetual.py`; `scripts/ops/verify_seed_*.py`; `scripts/ops/fmcg_calendar.py`.
- Hari libur 2026: [setneg.go.id – SKB 3 Menteri](https://setneg.go.id/baca/index/inilah_skb_3_menteri_libur_nasional_dan_cuti_bersama_2026), dibaca 2026-11-04.
- PPN: [pajak.go.id – PMK 131/2024](https://pajak.go.id/index.php/id/artikel/pmk-1312024-tarif-ppn-sebelas-dua-belas), dibaca 2026-11-04. Verifikasi ulang sebelum dikunci di kontrak.
- Angka perhitungan Bab 4–6 diturunkan langsung dari berkas `data/registers/*.csv` pada `2b7cdd2`.

**Belum diuji [BU]:** isi database live `railway` (stok, saldo bank, fixture, pajak PO bill); kecocokan estimasi waktu loader untuk ±3.500 SO; perilaku model valuasi Odoo 19 pada backdating Agustus–November; ketersediaan jendela deploy.
