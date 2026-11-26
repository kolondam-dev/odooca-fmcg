# PR #110 — Acceptance Paket A

Acuan frozen adalah register Juli dan Agustus 2026. Gunakan tanggal bisnis WITA. Untuk baris dengan tanggal saja, dispatcher menjalankan PO, receipt dan bill, SO, dispatch, retur, invoice, penerimaan AR, pembayaran AP, kemudian OPEX. Referensi sumber menentukan urutan di dalam fase. Ini aturan rekonstruksi untuk ketelitian data harian. Register tidak menyediakan jam kejadian.

| ID | Sumber dan business key | Action dan pelaku | Prasyarat, state dan dampak | Oracle, kontrol negatif dan bukti | Status |
| --- | --- | --- | --- | --- | --- |
| A-01 | PO `PO-2026-08-16`, baris `WNG-SGD-02`, lot `LOT-SGD-202608-NEW-01` | Buyer mengonfirmasi PO dan gudang memvalidasi receipt. Loader memisahkan tanggal kedua action. | PO terkonfirmasi sebelum receipt. Receipt tertaut ke purchase line dan menambah 4.800 unit lot dengan basis Rp88.800.000. | Fixture native `TestFmcgOperationalGoldenChain`. Mini-pack memakai seluruh PO asli. Mutasi receipt 29 Agustus harus menggagalkan dispatch 28 Agustus dan membatalkan write awal. | PASS |
| A-02 | Bill dari PO yang sama | Akuntansi memposting bill. Loader membuat bill dari purchase line saat receipt dan menggunakan interim 113900. | Receipt selesai. Bill posted tertaut ke PO dan AP tercatat Rp197.136.000 sebelum pembayaran. | Mini-pack membandingkan binding purchase line dan residual dengan register. AP lintas periode diperiksa dalam probe F4. | PASS |
| A-03 | `SO-202608-1059`, 27 Agustus | Sales membuat SO. Approver yang berwenang mengambil keputusan. Loader mengimpor owner dan tanggal dari register. | Aksi native memblokir order sebelum izin yang diperlukan. Histori impor memakai konteks seed dengan pengecualian approval karena sumber tidak merekam actor atau keputusan. | Native test berperan Sales, manager, director dan gudang. Pending, rejected, dan wrong-role tetap diuji. Mini-pack memeriksa hasil dokumenter setelah impor. | PASS |
| A-04 | `DO-202608-1059`, 28 Agustus | Gudang memvalidasi stock picking dan move line. Loader memeriksa saldo lot pada tanggal dispatch. | SO sudah terkonfirmasi. Dispatch mengurangi 48 unit pada lot yang diterima dan mencatat HPP Rp888.000. | Mini-pack membandingkan tanggal line, lot, kuantitas, nilai move dan saldo lot 4.752 unit. Audit seluruh pack merekonstruksi saldo dari pembukaan, PO dan DO serta membandingkan lot dan kuantitas transaksi Odoo. | PASS |
| A-05 | `INV-202608-1059` dan `PAY-AR-02066` | Akuntansi memposting invoice dan merekonsiliasi pembayaran. Loader mencari invoice posted tepat per referensi, perusahaan, customer dan tanggal. | Dispatch harus selesai sebelum invoice. Invoice line tertaut ke SO, AR Rp1.158.094,08, residual nol setelah jurnal pembayaran yang tepat. | Mini-pack memeriksa relasi sale line dan reconciliation edge. Replay dengan target lain bernominal sama ditolak dan rollback mempertahankan digest. | PASS |
| A-06 | `PAY-AP-05` dan bill `PO-2026-06-05` | Akuntansi memposting AP payment dan merekonsiliasi bill sebelumnya. | Bill posted dan saldo yang diotorisasi tersedia untuk pelunasan. | Probe F4 mengubah residual, mengharuskan rollback tanpa drift, lalu recovery menguji target asli. | PASS |
| A-07 | Register penuh dan 48 carry-forward Juli | Loader meneruskan Juli, menjalankan event, lalu replay. | Dokumen dan angka frozen tetap dapat direkonsiliasi pada cutoff. | Dua database F4 harus lulus pada SHA yang sama. Digest A/B, rollback, replay dan audit angka tetap wajib. | PASS |
| A-08 | Aktivitas PJP dan saldo tersedia pada setiap reservasi | Sales dengan assignment dan role yang valid. Gudang menjalankan reservasi sesuai lot. | Validasi jadwal, ownership, reservasi parsial dan backorder. | Mini-pack ini menguji ketersediaan saat dispatch. Proof PJP dan per-event reservasi masih diperlukan. | PARTIAL |

Mini-pack mengambil baris melalui referensi sumber, tanpa salinan CSV yang dapat berubah terpisah. Mutasi tanggal hanya ada di savepoint pengujian. Script verifikasi adalah `scripts/ops/verify_disposable_period_pack.py`, melalui workflow Period Pack Runtime Verification. Bukti native ada di `addons/id_approval/tests/test_operational_golden_chain.py` dan tes dispatcher/oracle ada di `tests/test_period_pack_loader.py`.

Saldo dan pemetaan likuiditas per rekening menunggu K5. A-01 sampai A-07 lulus untuk cakupan kronologi dan irisan yang diuji pada `2cb0b6a`. [F4 integrasi](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/45093700739/job/137428709998). A-08 tetap terbuka untuk PJP dan reservasi per event.


## Bukti integrasi dan remaining playbook

Pada `284e31f809316a2112493aa9c365b3050106d242`, [F4](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/45610697265/artifacts/15025901192) mengulang mini-pack, kontrol future receipt dan pembayaran salah, audit kronologi, digest dua DB, replay/rollback/recovery serta rekonsiliasi GL. A-01–A-07 lulus dalam cakupan tabel.

| Area | Correctness fakta sumber | Batas histori untuk re-review | Fitur lanjutan |
| --- | --- | --- | --- |
| A-08 PJP dan reservasi | Owner SO, tanggal, dan ketersediaan lot saat dispatch telah diuji. Pertahankan kontrol receipt masa depan dan audit owner pada SHA integrasi. | Register penjualan tidak merekam kunjungan PJP atau urutan reservasi per jam. Rekam sebagai UNKNOWN jika reviewer menerima batas ini. | Assignment/frekuensi kunjungan, reservation/backorder pada setiap event dan bukti role native. |
| C Trip, FEFO dan delivery | SO → DO, kuantitas dan lot mengikuti register. Metrik logistik terbit sebagai agregat harian. Ketidaksesuaian dokumen/lot yang tercatat tetap memblokir. | Agregat kendaraan/rute/personel tidak menetapkan relasi ke tiap DO, picking atau packing. Picking/packing historis, trip, dan driver per DO tidak tercatat. Rekomendasi reviewer adalah menerima UNKNOWN hanya untuk atribut tersebut. Lihat keputusan akhir di bawah. | Chain picking/packing, trip dan driver. Uji FEFO/ED native dengan batas kedaluwarsa dan override berotorisasi. |
| C Retur dan karantina | PASS pada `b258705` untuk 47 transfer, keterlacakan DO, SKU/lot/qty, alasan dan bukti sumber, termasuk replay dan rollback. DPP invoice setelah penolakan cocok dengan register. | Bukti yang kosong tetap kosong. ID insiden atau bukti yang tercatat tidak boleh dihilangkan. | Bukti alur koreksi komersial native dan role untuk varian retur yang belum diuji. |
| Coretax | PASS pada `b258705` untuk 1.240 payload native buyer. F4 membuktikan DPP/PPN dan relasi invoice. | Identitas yang kosong dinyatakan UNKNOWN. Jangan mengisi NIK/NPWP dari dugaan. | Bukti output Coretax per profil dan alur operasional koreksi. |
| D Kas/payment | Pembayaran harus tertaut ke invoice/bill yang benar, bertanggal sumber dan cocok dengan residual/GL. PASS pada `b258705` untuk payment edge dan saldo, termasuk rekening AP BNK1/101401. AR menyediakan referensi, tanggal dan nominal tanpa rekening sumber per baris. | Atribusi rekening AR yang tidak tercatat tetap UNKNOWN. Rekomendasi reviewer adalah memisahkan likuiditas K5 ke slice tersendiri. Lihat keputusan akhir di bawah. | Pemetaan metode/rekening lengkap dan pembuktian likuiditas harian. |
| D Biaya | Pertahankan kategori, tanggal, nominal, jurnal dan audit OPEX. Salah akun, saldo atau relasi yang didukung register wajib diperbaiki. | Register OPEX berisi tanggal, nominal, kategori dan deskripsi. Advance, evidence dan approval historis yang tidak tercatat tetap UNKNOWN. | Advance → realisasi → liability/pelunasan, bukti dan approval native. |

Correctness yang masih perlu bukti atau adjudikasi tercantum di kolom kedua. Kolom batas histori adalah cakupan yang diajukan untuk re-review, tanpa menganggap persetujuan atas 769 baris promo berlaku ke seluruh A/C/D. Fitur lanjutan tetap OPEN sampai ada bukti atau keputusan scope untuk tahap berikutnya.

[Keputusan pemilik dan gate merge](PR110_PACKET_B_ACCEPTANCE.md#keputusan-pemilik-dan-gate-merge) mencatat dasar keputusan. Verdict merge berada pada supervisor/reviewer.


## Tiga kontrol correctness sumber untuk re-review

- Retur menyimpan relasi picking outgoing, referensi DO, alasan, ID insiden, jenis dan referensi bukti. F4 mengaudit 47 baris termasuk carry-forward 1 September dan menguji mutasi provenance melalui replay dan savepoint. Transfer lama yang belum memiliki metadata hanya diperkaya setelah fakta fisik cocok.
- Coretax menyiapkan partner komersial yang dibaca oleh pembentuk payload native. F4 memeriksa profil buyer NIK, NPWP16 dan TIN_0 untuk 1.240 invoice. Bila identitas penjual kosong pada DB sintetis, fixture sementara disimpan di savepoint dan di-rollback. Bukti ini untuk isi payload buyer di disposable.
- `Bank Mandiri Rekening Operasional` dipetakan eksplisit ke jurnal `BNK1` dan default liquidity account `101401` pada chart company disposable. Loader memeriksa mapping sebelum pelunasan dan saat replay. F4 mencatat jurnal/akun aktual. Rekening sumber AR tidak tercatat. Lihat keputusan akhir di bawah.


## Keputusan akhir picking, packing, trip, driver dan K5

Rekomendasi reviewer untuk menerima UNKNOWN atas picking/packing historis, trip, dan driver per DO serta memisahkan analisis likuiditas K5 ke slice tersendiri **menunggu persetujuan eksplisit pemilik**. Otorisasi yang sudah tercatat tetap berlaku sesuai cakupannya. Status lain tidak memerlukan persetujuan ulang. Histori UNKNOWN tidak mengubah fakta tercatat, stock-to-GL, atau bukti SO→DO dan payment edge.

[Artefak F4 yang menutup tiga gate sumber pada b258705](https://github.com/kolondam-dev/odooca-fmcg/actions/runs/45733400853/artifacts/15082712066). Merge dan apply ke database demo adalah keputusan terpisah.
