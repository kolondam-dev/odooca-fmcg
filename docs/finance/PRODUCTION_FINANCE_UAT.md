# Verifikasi produksi — finance reports dan HPP (daftar klik)

Status: **daftar langkah untuk pemilik; belum dijalankan.** Aktivasi di production
sudah tercatat di [I2_ACTIVATION.md](I2_ACTIVATION.md#status-produksi-bukti-read-only-2026-11-15),
tetapi belum ada bukti bahwa admin demo benar-benar melihat menu, menjalankan
laporan, dan mengunduh XLSX dari aplikasi yang live. Langkah 1–4 punya jalur
otomatis lewat harness UI live; langkah 5–6 dan pemeriksaan isi XLSX tetap
manual.

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

## Jalur otomatis (harness UI live)

Sebagian langkah di atas dapat dijalankan tanpa klik manual memakai harness
[`Remote Live UI Proof`](../LIVE_UI_HARNESS.md). Spec ada di
`pwa/tests/live/finance-uat.spec.ts`; profil route ada di
`pwa/tests/live-profiles/finance-uat.json`.

| Langkah manual | Bukti otomatis |
|---|---|
| 1. Company | setiap action Finance menampilkan `company_id` **PT Manado Distribusi Utama** |
| 2. Menu | app **Finance** → section **Finance Reports** memuat 8 entri berlabel FIN04…FIN38 |
| 3. Jalankan laporan | kedelapan action membuka wizard dengan `report_type` yang sesuai dan tombol **Run Report**/**Export XLSX** terlihat di header; FIN04 dijalankan untuk 2026-07-01..2026-07-31 dan ringkasan memuat `FIN04` |
| 4. Unduh XLSX | **Export XLSX** menghasilkan `FIN04-audit-trail-2026-07-01_2026-07-31.xlsx`; spec memeriksa header ZIP `PK`, `[Content_Types].xml` memuat `spreadsheetml.sheet.main+xml`, dan `xl/workbook.xml` memuat sheet `Summary`, bukan halaman error |

Prasyarat remote: Environment `demo-ui` berisi Variables `LIVE_UI_ODOO_URL` dan
`LIVE_UI_PWA_URL`, serta Secrets `ODOO_DEMO_LOGIN`/`ODOO_DEMO_PASSWORD`; setiap
run menunggu approval pemilik. Nilai rahasia tidak boleh ditempel ke chat atau
log.

```bash
# wizard, Run, Export XLSX (8 action + FIN04 Juli 2026)
gh workflow run live-ui-proof.yml --ref main \
  -f source_ref=<branch-atau-SHA-yang-direview> \
  -f suite=odoo -f project=desktop \
  -f purpose="finance UAT read-only"

# screenshot route FIN04 dan FIN51
gh workflow run live-ui-proof.yml --ref main \
  -f source_ref=<branch-atau-SHA-yang-direview> \
  -f suite=routes -f project=desktop \
  -f route_file=tests/live-profiles/finance-uat.json \
  -f purpose="finance UAT routes read-only"
```

Ambil artifact `live-ui-<suite>-<project>-<sha>` (retensi 3 hari). Bukti yang
dipakai: screenshot per langkah, nama berkas XLSX, struktur `[Content_Types].xml`
dan `xl/workbook.xml`, serta ringkasan `FIN04`. Jalankan dengan
`project=desktop`; test menu sengaja dilewati pada viewport telepon karena
navbar-nya memakai sidebar.

Batas otomatis: spec tidak menulis data bisnis. Satu-satunya penulisan adalah
record transient `id.finance.report.wizard` yang dibuat oleh klik itu sendiri
(`action_run`/`action_export_xlsx` menyimpan pratinjau dan ekspor di sana), jadi
`LIVE_UI_ALLOW_WRITE` tetap `NO`.

Sisa yang tetap manual:

- rekonsiliasi isi XLSX terhadap payload: nilai sel, kolom `__nested`, dan catatan
  batas 20.000 baris / 32.000 karakter / 200.000 karakter payload (struktur
  workbook sudah diperiksa otomatis oleh spec);
- penolakan peran user Sales (langkah 5);
- nilai **Costing Method** dan **Inventory Valuation** dua kategori (langkah 6).

### Perbaikan tombol wizard (2026-11-18)

[F] Temuan 2026-11-17: kedelapan action memakai `target: current`, sedangkan
tombol **Run Report** dan **Export XLSX** hanya ada di `<footer>`. Pada Odoo 19
footer dirender hanya ketika form berada di dialog: `form_controller.xml`
menggerbangi slot `layout-buttons` dengan `t-if="env.inDialog"`,
`form_controller.js` memindahkan footer ke arsip dialog ("if we are in a
dialog"), dan `action_service.js` memetakan `target: "new"` ke mode `inDialog`.
Akibatnya tombol tidak muncul pada form halaman penuh.

[F] Keputusan pemilik: laporan tetap halaman penuh, tombol dipindahkan ke
`<header>`, dan kedelapan action tetap `target: current`. `<footer>` wizard
dihapus, termasuk tombol **Close** `special="cancel"` yang tidak berarti pada
halaman penuh. Dua wizard lain di repo (`id_base/coretax_export_wizard`,
`id_promo_governance/promo_sku_wizard`) tetap memakai pola footer + dialog
karena memang `target: new`; keduanya tidak diubah.

[F] Guard regresi ada di `scripts/ops/verify_finance_activation_demo.py`, yang
dijalankan job `init-test`: view ter-resolve harus punya `action_run` dan
`action_export_xlsx` di `<header>`, tidak boleh menduplikasinya di `<footer>`,
dan kedelapan action harus `res_model = id.finance.report.wizard`,
`view_mode` memuat `form`, serta `target = current`. Ringkasan tombol dan target
dicetak di JSON `INIT_FINANCE_ACTIVATION`.

[BU] Jalur UI live (menu, Run, download XLSX) belum dijalankan ulang pada commit
perbaikan ini; dispatch butuh Secrets `ODOO_DEMO_LOGIN`/`ODOO_DEMO_PASSWORD` di
Environment `demo-ui` dan approval pemilik. Spec kini gagal bila tombol kembali
ke footer atau berkas unduhan bukan workbook XLSX.

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
