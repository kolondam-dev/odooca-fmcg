# Implementasi tindak lanjut audit UX PWA — 1 November 2026

[F] Basis: `main` f3d9a72, termasuk PR67. Branch `agen/pwa-ux-improvements`.
Permintaan pemilik: tuntaskan perbaikan temuan/rekomendasi audit UX, tanpa deployment.
Audit sumber: `Audit_UX_UI_PWA_2026-11-01.md` (13 temuan UX01–UX13).
Tidak menyertakan kredensial, foto pengguna, atau hasil transaksi server dalam repo.

## Perubahan dan bukti regresi

| Temuan | Perilaku setelah perubahan | Bukti utama |
|---|---|---|
| UX01 Back/history | History API berscope user/company/tanggal; role dan outlet diperiksa. Back menutup kamera/search terlebih dahulu, lalu form, lalu halaman. Query, scroll daftar, dan fase toko dipertahankan dalam workspace. Reload memulihkan route dan draft persisten; media/GPS tidak masuk history. | `ux-improvements`, `route-workflow`, `navigation.test` |
| UX02 toolbar bertumpuk | Tab order memiliki tinggi tetap; toolbar pencarian/principal sticky pada offset tab. | Regresi geometri POS 393×430 |
| UX03 toast menutup CTA | Status mempunyai ruang sendiri di shell, tidak melayang di atas tombol, hilang setelah 3 detik. | Geometri status vs main dalam regresi kamera |
| UX04 viewport pendek | Footer total dan CTA diringkas; header/footer compact pada landscape. Tinggi shell mengikuti visual viewport saat keyboard muncul, tanpa mematikan zoom aksesibilitas. | Geometri viewport pendek; IME fisik masih [BU] |
| UX05 pencarian vertikal | Label pencarian eksplisit horizontal, input 16px; override margin `!important` dihapus. | Posisi tengah ikon/input dan tinggi toolbar |
| UX06 referensi biaya | Trip/DO dipilih dari manifest snapshot bila tersedia. DO hanya muncul pada lingkup pengiriman; pilihan DO mengikuti trip. Tanpa manifest, referensi tetap kosong/manual, tidak dibuat-buat. Server tetap otoritas scope/approval. | `expense references`, `field`, `expense` |
| UX07 outcome terpotong | Label pendek `Order diajukan`, enum/domain tetap. | Alur penutupan Sales dan regresi order |
| UX08 ergonomi | Target profil, satuan, principal dan +/- minimal 44px. Tanggal native menampilkan pendamping tanggal Indonesia; penyimpanan tetap ISO. | Geometri/form tanggal dan alur order |
| UX09 panduan/kontrol teknis | Satu badge mode uji tetap jelas; kontrol simulator respons, approval/pencairan dan lokasi acuan hanya ada pada build QA eksplisit. Rincian integrasi/bukti menjadi disclosure, caption kunjungan dipersingkat. Status lokal/review, validasi, privasi tile, attribution tetap jujur. | `check-qa-tools.mjs disabled/enabled`, build live/staging, regresi existing QA |
| UX10 lokasi/foto berulang | Sales mengambil GPS saat membuka toko; Delivery saat membuka DO dan setelah foto berubah. Retry sekunder tetap ada. Kamera otomatis menyimpan paket foto/hash; setelah tersimpan tidak meminta lokasi/simpan lagi. Upload file manual tetap jalur pemulihan. Check-in membawa pengguna ke fase order. | Regresi kamera; Sales/Delivery workflow dan evidence |
| UX11 reset maps | Leaflet 1.9.4 lazy-load setelah persetujuan tile. GPS memindahkan marker/akurasi tanpa mengganti consent/zoom/pan. Reset pada target berubah; tombol center eksplisit. Diagram offline, timeout/gagal tile dan attribution dipertahankan. | Tile gagal/opt-in, GPS update, pinch CDP pada phone |
| UX12 fokus kamera bocor | Primitive dialog bersama: stack, inert background, focus trap, Escape dan pemulihan fokus. Hanya dialog teratas aria-modal. Lock scroll dimiliki stack, sehingga pergantian akun dengan kamera terbuka tetap memulihkan body. Error kamera dilokalkan. | Back kamera sebelum form; Tab tetap di kamera; Escape pencarian |
| UX13 profil statis | Gudang berasal dari `warehouseName` snapshot assignment (fallback ID, lalu belum tersedia). Status sesi dibedakan belum dibuka/aktif/selesai. Tidak lagi memakai nama gudang/status aktif hardcoded. | Assertion snapshot native; schema OpenAPI; alur sesi |

## Efisiensi dan batas desain

- [F] Jam detik menjadi komponen sendiri; katalog/workspace tidak dirender ulang setiap detik.
- [F] Filter produk dimemoisasi; katalog 500 SKU dirender bertahap per 60 tanpa library virtualisasi tambahan. Pencarian dan kuantitas produk di luar DOM tetap dipertahankan.
- [F] Form tugas dipisah dari `App.tsx`; hidrasi manifest dipisah dari editor Delivery. Fokus dialog tidak lagi diimplementasikan tiga kali. Aturan shell/scroll disatukan dan beberapa override lama dihapus.
- [F] Ringkasan cart memakai jumlah SKU dan `Karton setara`, menghindari jumlah unit campuran disebut item.
- [F] Waktu sampel GPS kamera diteruskan terpisah dari waktu foto; paket kamera menyertakan hash dan pemeriksaan generation sesudah penyimpanan, sehingga hasil lama tidak menggantikan pengambilan ulang.
- [F] Caption foto memakai identitas workspace. Alamat tujuan tidak diklaim sebagai alamat aktual GPS; tanpa alamat perangkat tidak melakukan reverse geocoding diam-diam.
- [F] HTML/body menahan overscroll dan setiap workspace memiliki scroll owner. Gesture Leaflet hanya di area peta; scroll wheel tidak mengambil alih halaman. Zoom browser untuk aksesibilitas tetap tersedia. Refresh browser eksplisit tidak diblokir; draft dipulihkan.
- [F] Build operator default tidak menyertakan kontrol QA. `VITE_QA_TOOLS=true` hanya berlaku pada mode demo untuk regresi; live/staging selalu false. CI memeriksa kedua build sebelum browser menjalankan artifact QA. Flag ini bukan ACL atau integrasi approval resmi.

## Verifikasi dan batas penerimaan

[F] Pengujian lokal: unit, typecheck, format, kontrak OpenAPI, hosting, semua mode build/budget, Ruff dan manifest. Browser mencakup phone/tablet, viewport pendek, 500 SKU, offline/reload, account separation, evidence tampering/replay dan workflow Sales/Delivery. Jumlah final dicatat di HANDOFF dan PR pada HEAD yang diuji.

[BU] Odoo native/upgrade/transport Docker hanya dianggap terverifikasi setelah CI pada HEAD final; tidak ada Odoo/Postgres lokal dalam sandbox ini. Acceptance iOS/Android fisik, keyboard nyata, GPS/kamera nyata dan endpoint staging bisnis tetap terpisah. Tidak ada merge/deploy atau transaksi live yang dilakukan untuk task ini.

[F] Geofence, binding owner/company/sesi/outlet, freshness evidence, idempotensi UUID, approval, posting stok/akuntansi dan batas live tidak dilonggarkan. Business command demo masih lokal/simulasi; penanda mode dan status tersebut tidak dihapus. PR68/PJP dan perubahan master agen lain tidak disentuh.
