# Kontrak invariant seed dan workflow supervisi

Basis requirement: FULL_CONVERSATION_TRANSCRIPT_2026-10-25.md, khususnya Turn 2
(native, Senin-Sabtu), Turn 3 (register, PJP, ledger sebelum injeksi), Turn 8
(kausalitas per baris), Turn 9 (stok awal, transit, harga barang, periode historis,
model/modul aktual). Angka proporsi principal, toleransi omzet, tarif pajak, dan
kapasitas gudang dari jawaban agen belum otomatis menjadi ketetapan pemilik.

## Alur penerimaan bersama
1. Worker memperbarui branch tugas, data dan generatornya. Jangan merge baseline
   gagal atau melakukan injeksi baru hanya karena lint/HTTP login lulus.
2. Jalankan `python -m unittest discover -s tests -p test_seed_invariants.py -v`.
3. Jalankan `python scripts/ops/verify_seed_invariants.py --report /tmp/invariant-report.json`.
4. Push: workflow Seed supervision berjalan di main, seluruh agen/**, dan PR.
   `invariant-tests` menguji validator; `seed-invariants` memeriksa artefak calon
   merge. Pada PR, checkout standar GitHub memeriksa hasil merge sementara.
5. Supervisor menilai laporan, diff, dan bukti requirement. Laporan menyertakan
   SHA commit dan SHA256 input; buktinya hanya berlaku pada snapshot tersebut.
6. Perubahan requirement/validator/workflow wajib dijelaskan dengan referensi
   instruksi pemilik di PR dan HANDOFF. Jangan menghapus tes, memperlebar toleransi,
   memakai continue-on-error, atau menyembunyikan check agar baseline terlihat hijau.
7. Pemilik memutuskan merge setelah gate wajib sukses. Tidak ada baseline exemption
   atau allowlist pelanggaran di validator ini.

## Gate artefak lokal (dapat dieksekusi sekarang)
| ID | Invariant | Sumber |
|---|---|---|
| MASTER-COUNT/IDENTITY | 354 customer, 150 SKU; identitas wajib dan unik | konteks master + Turn 3 |
| MASTER-SYNC | register dan seed mempunyai key serta nilai field bersama yang sama | Turn 3 |
| MASTER-GEO | kode kecamatan/kelurahan resolve ke pasangan XML yang dipakai loader | Turn 3/9 |
| COHORT-PJP/SO | kunjungan dan order tidak sebelum tanggal aktif customer | narasi coverage bertahap |
| SO-PRINCIPAL | Setiap SO hanya berisi SKU dari tepat satu principal_code pada master produk; principal kosong/hilang dan campuran prinsipal menggagalkan gate. Banyak SKU/brand/lot dari prinsipal sama diperbolehkan. | Instruksi langsung pemilik 2026-10-26 |
| PJP-SO | order mempunyai visit customer/salesman/tanggal yang cocok | Turn 8 |
| CALENDAR | Minggu tanpa call/delivery; SO hanya pada hari kerja kartu stok | Turn 2/8 |
| LINE/HEADER/PO/STOCK-MATH | perkalian dan jumlah antar-artefak konsisten (Decimal, toleransi Rp0,01) | Turn 8/9 |
| TX-FK/COVERAGE/IDENTITY | SO, delivery, invoice, produk, PO memiliki relasi dan cakupan konsisten | Turn 8 |
| EVENT-ORDER | delivery tidak sebelum order; jatuh tempo tidak sebelum invoice | Turn 8 |
| COLLECTION | pembayaran mengenal invoice, tidak sebelum invoice, aritmetika DPP/discount benar | Turn 8 |
| LOT-BALANCE/FEFO/EXPIRY | alokasi per lot tidak melebihi penerimaan, tidak expired, mendahulukan expiry | Turn 8 |
| INPUT-SCHEMA | file hilang/kosong, field wajib hilang, atau angka tidak valid menggagalkan gate | bukti yang dapat direproduksi |

Lot diputar ulang menurut tanggal: saldo awal, receipt sebelum alokasi SO di hari
sama, lalu pengurangan lot yang tercatat pada baris order. Ini menguji FEFO dan
ketersediaan harian; belum membuktikan jam 08:00. Tidak menganggap retur tersedia
untuk dijual kembali: dataset harus menyediakan mutasi/karantina yang eksplisit
sebelum kontrak replay diperluas. Pembayaran dicek pada basis DPP dataset saat ini;
ini BUKAN bukti faktur termasuk pajak telah lunas. Tidak memaksa semua delivery H+1;
same-day diperbolehkan sesuai Turn 9. Hari libur nasional belum dijadikan konstanta
baru: daftar bersumber/bertanggal harus disatukan oleh worker, lalu ditambahkan ke gate.

## Bukti runtime Odoo (BELUM diimplementasikan sebagai gate otomatis)
Sebelum injeksi/penerimaan final wajib disediakan pada DB staging disposable,
menggunakan image/modul persis calon deploy dan dataset yang lulus gate lokal:
- Snapshot versi image, modul terinstal, manifest, konfigurasi valuasi dan hash seed.
- Pemuatan master lalu baca ulang: salesperson bukan fallback admin, TOP tepat,
  rasio UoM benar, kategori tidak silang, wilayah resolve, jumlah dan identitas cocok.
- Uji seed kedua kali: key dan jumlah tidak bertambah, saldo tidak berubah.
- Uji DB kosong dan upgrade dari baseline persisten sebelumnya.
- Rekonsiliasi SKU/lot, stok fisik vs reserved/transit, receipt/delivery/return,
  invoice/payment dan saldo AR/AP; laporan persediaan vs GL per akhir periode.
- Bukti Juli tetap masuk Juli walaupun loader dijalankan sekarang. Periksa model
  valuasi aktual Odoo 19 sebelum memilih teknik backdating; SQL create_date bukan
  requirement pemilik dan bukan bukti laporan benar dengan sendirinya.
- Pajak dari konfigurasi lokal bersumber dan bertanggal; jangan mengunci satu tarif
  dari pernyataan agen. Jelaskan basis omzet gross/net/retur, toleransi, kapasitas,
  biaya dan cohort; belum diotomatisasikan sebagai target penerimaan numerik.

Railway tidak dibutuhkan untuk gate lokal. Pengujian runtime memerlukan akses
staging Odoo dan bukti runtime; bisa dari CI disposable atau staging Railway.
Jangan menaruh credential di repo/artifact, jangan menjalankan loader di production
untuk membuktikan gate. Plugin Railway belum tersedia dalam sesi supervisor ini.

## Penguncian GitHub (pengaturan admin, belum aktif)
Workflow sendiri hanya melaporkan; tidak dapat melarang merge/push tanpa ruleset.
Pemilik/admin perlu membuat ruleset main dan branch integrasi yang dipakai:
- require pull request dan required checks `invariant-tests`, `seed-invariants`,
  serta `static`, `install-test`, `init-test` dari CI yang sudah ada;
- require up-to-date branch, cegah force push/deletion, batasi bypass/direct push;
- review perubahan gate/kontrak secara eksplisit. Semua agen memakai akun pemilik
  sehingga approval oleh identitas GitHub yang sama bukan independent review.
Nama required checks harus dipilih dari run aktual. Jangan menyatakan merge/deploy
sudah diblokir sebelum ruleset dan perilaku Railway benar-benar diverifikasi.
Jika Railway auto-deploy mengikuti main, pastikan hanya commit yang diterima gate
bisa masuk main. GitHub tidak otomatis mengendalikan `railway up` dari laptop.

## Baseline pengujian awal
Basis implementasi: 57f5768. Validator lulus 17 uji fixture/mutasi; baseline dataset
GAGAL: MASTER-GEO 77, COHORT-PJP 228, COHORT-SO 219, CALENDAR 84,
EVENT-ORDER 331, LOT-BALANCE 770. Angka adalah jumlah kejadian, bukan unique defect.
Laporan JSON CI menjadi daftar kerja worker. Belum ada perbaikan data bisnis atau
injeksi Odoo oleh supervisor. Draft PR gate tetap merah sampai dataset dibenahi;
merah ini tidak boleh diganti klaim selesai melalui dokumen.

## Penutupan gate supervisor (2026-10-26)
Job wajib `seed-invariants` menjalankan **dua** pemeriksa independen:
`verify_seed_invariants.py` dan `verify_seed_acceptance.py`. Keduanya harus PASS;
artifact memuat `invariant-report.json` dan `acceptance-report.json`, masing-masing
terikat commit dan SHA-256 input LF kanonikal. Pemeriksa kedua tidak mengimpor atau
menjalankan generator transaksi/laporan. Jalankan lokal:

```bash
python scripts/ops/verify_seed_acceptance.py --report /tmp/acceptance-report.json
```

- AP: expected payment per PO diturunkan dari `ap_payment_date`, `due_date`,
  `total_dpp` dan principal pada header sumber, bukan total bulanan konstan.
  Alokasi pembayaran boleh beberapa baris pada tanggal yang dijadwalkan, dengan
  ID unik dan jumlah kumulatif tepat. Perubahan jadwal harus eksplisit di sumber.
- Ledger: multiset event harus identik dengan opening/receipt/SO/DO/rejection
  sumber pada tingkat tanggal, jenis, referensi, SKU, lot, qty dan tiga impact.
  Event hilang/berlebih, ID duplikat, referensi fiktif dan impact salah ditolak.
  Replay memeriksa physical/reserved/quarantine, available, cost dan volume harian.
- Report: seluruh field numerik tujuh bagian laporan, persentase dan tanggal
  closing diperiksa ulang. Identitas set 15 fingerprint wajib lengkap.
  Accepted COGS berasal dari biaya lot sumber dikurangi quarantine; cash + discount
  + open AR direkonsiliasi pada DPP dan total faktur, serta AP paid + open AP.
- Kontrak saat ini: periode 1–31 Juli 2026; dokumen Agustus merupakan carry-forward,
  bukan event fisik Juli. AR mendukung satu pelunasan penuh per invoice. Pembayaran
  parsial AR memerlukan perluasan schema, aturan dan tes, bukan bypass validator.
  Nilai pajak tetap berasal dari dataset dan pemeriksa dasar; perubahan konfigurasi
  pajak harus disertai bukti sumber dan pengujian sendiri.
- Tes `test_seed_acceptance.py` memakai salinan snapshot repo yang terisolasi;
  hash diperbarui setelah mutasi sumber untuk membuktikan gate memeriksa kausalitas,
  bukan sekadar menemukan checksum usang. CI `test_*.py` menjalankan seluruh tes.

PASS artefak lokal tidak membuktikan loader, backdating, upgrade, GL atau runtime
Odoo. Checklist runtime terdahulu tetap berlaku. Perluasan periode/schema wajib
mengubah kontrak dan tes secara eksplisit; jangan menambah allowlist baseline.
