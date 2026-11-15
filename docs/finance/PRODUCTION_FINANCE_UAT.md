# Verifikasi produksi — finance reports dan HPP (daftar klik)

Status: **daftar langkah untuk pemilik; belum dijalankan.** Aktivasi di production
sudah tercatat di [I2_ACTIVATION.md](I2_ACTIVATION.md#status-produksi-bukti-read-only-2026-11-15),
tetapi belum ada bukti bahwa admin demo benar-benar melihat menu, menjalankan
laporan, dan mengunduh XLSX dari aplikasi yang live.

Tujuan daftar ini: mengubah bukti log menjadi bukti pemakaian, tanpa mengubah
data. Semua langkah **read-only** dari sisi data; jangan menyimpan pengaturan,
mengubah kategori, atau memposting jurnal.

## Prasyarat

- Akses `https://odooca-fmcg-demo.up.railway.app` sebagai admin demo
  (`admin`), company **PT Manado Distribusi Utama** (company ID 1).
- Jangan login sebagai Sales/Driver untuk langkah utama; user itu dipakai hanya
  pada pemeriksaan penolakan di langkah 5.
- Catat waktu (WIB) dan commit `main` yang sedang live saat pengujian.

## Langkah

1. **Masuk dan cek company.** Login, pastikan nama company di pojok kanan atas
   adalah **PT Manado Distribusi Utama**, bukan "Demo company". Catat tangkapan
   layar.
2. **Menu terlihat.** Buka **Finance → Finance Reports**. Harus ada 8 pilihan:
   FIN04 Audit Trail, FIN05/FIN06 Partner Ledger, FIN07 Open Items, FIN08/FIN09
   Aged Partner Balance, FIN51 Combined Trial Balance, FIN57 Sales and Purchase
   Register, FIN37 Accrual/Prepayment, FIN38 FX Revaluation.
3. **Jalankan satu laporan.** Pilih **FIN04**, periode Juli 2026, klik **Run**.
   Yang harus terlihat: ringkasan berisi ID laporan, tabel pratinjau, dan tidak
   ada halaman error. Ulangi untuk **FIN51** dengan dua company bila tersedia;
   bila tidak, catat sebagai tidak berlaku.
4. **Unduh XLSX.** Dari laporan yang sama, klik **Export XLSX**, buka berkasnya.
   Periksa: sheet **Summary** ada; kolom `__nested` ada bila baris punya nilai
   bersarang; catatan batas menyebut 20.000 baris / 32.000 karakter /
   200.000 karakter payload; tidak ada sel yang dieksekusi sebagai formula.
   Simpan nama berkas dan satu tangkapan layar Summary.
5. **Penolakan peran.** Logout, login sebagai user Sales (bila tersedia). Menu
   **Finance Reports** tidak boleh muncul; bila memanggil action langsung,
   harus ditolak. Kembali login sebagai admin.
6. **HPP/valuasi (I3).** Buka **Inventory/Inventory → Configuration → Product
   Categories**, buka dua kategori yang dipakai produk demo. Catat nilai
   **Costing Method** dan **Inventory Valuation** apa adanya. Bandingkan dengan
   keluaran `FINANCE_I3_COSTING` di [I3_COSTING.md](I3_COSTING.md); jangan ubah
   nilainya pada langkah ini.

## Bukti yang diminta

Kirim ke catatan PR/HANDOFF:

```
waktu (WIB):
commit live:
company tampil:
menu Finance Reports: ada/tidak
laporan dijalankan: FINxx, hasil (ringkasan/tabel/error)
XLSX: nama berkas, sheet Summary ada/tidak, catatan batas terbaca/tidak
user Sales: menu tersembunyi/ditolak
kategori: <nama> — cost method ..., valuation ...
catatan lain:
```

## Batas

- Tidak ada perubahan konfigurasi, kategori, produk, atau jurnal selama daftar
  ini dijalankan; temuan dicatat, bukan diperbaiki di tempat.
- Bila ada langkah gagal, berhenti dan catat langkah terakhir yang berhasil
  beserta pesan layar.
- Hasil daftar ini belum menjadi penerimaan katalog. `REPORT_CATALOG.csv` tetap
  58/58 `BELUM_DITERIMA` sampai tie-out dan sign-off ada.
