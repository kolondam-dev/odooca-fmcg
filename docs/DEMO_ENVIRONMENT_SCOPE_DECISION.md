# Keputusan pemilik: environment production untuk demo

Tanggal persetujuan: 30 Oktober 2026 (Asia/Jakarta). Status: otorisasi scope; bukan bukti deployment.

## Keputusan yang berlaku

[F] Pemilik menyetujui perubahan scope: environment Railway `production` pada proyek `pleasant-caring` digunakan sebagai tempat demo dan acceptance PWA. Persetujuan ini menggantikan batas sebelumnya yang mengecualikan production dan rencana wajib membuat environment baru `staging-remote` untuk pekerjaan PR #44.

[F] PR #44 sudah merged pada `49739350127b9514af8fb3cd096ac2bc3b1adbc5`. Penyebutan “staging” pada build PWA tetap berarti mode aplikasi untuk pengujian integrasi; mode tersebut dapat dijalankan dalam environment Railway bernama production. Ini tidak mengaktifkan mode live/transaksi bisnis yang masih terkunci.

## Scope yang disetujui dan batasnya

- Gunakan layanan Odoo, Postgres dan field-pwa existing untuk demo; siapkan gateway satu origin sesuai kebutuhan implementasi yang telah direview.
- Pertahankan data existing. Tidak ada otorisasi reset database, penghapusan data/filestore, restore yang menimpa data, atau regenerasi 15 register kanonikal.
- Company, akun uji dan assignment TEST harus dipisahkan dari data/company existing. Label koordinat TEST tetap wajib; status verified memerlukan sumber koordinat/radius yang dikonfirmasi.
- Perubahan konfigurasi dan restart/deployment layanan demo dapat menyebabkan downtime selama pelaksanaan. Jangan menafsirkan status demo sebagai izin untuk menghapus data existing.
- Tidak ada izin membuka database ke publik, mempublikasikan credential admin/database/Railway, melemahkan auth/ACL/geofence, atau mengaktifkan bypass remote secara diam-diam.
- Guard provisioning PR #44 tetap berlaku. Skrip hanya menerima database disposable dengan prefix staging dan tidak boleh langsung dipaksakan ke `fmcg_base`. Adaptasi untuk target demo existing harus diimplementasikan, direview dan diuji sebelum provisioning server; jangan mengganti nama database atau melewati guard untuk meloloskan eksekusi.

## Urutan eksekusi

1. Baca ulang kondisi aktual Railway dan runtime Odoo: service/environment/database target, deployment SHA, addon terpasang, volume, domain dan konfigurasi relevan. Jangan mengasumsikan nama database atau kesesuaian runtime dari nama environment.
2. Siapkan pemulihan database + filestore dan catat baseline sebelum perubahan yang dapat memengaruhi data. Jangan memasukkan dump atau credential ke git.
3. Adaptasikan provisioning target demo secara eksplisit: exact project/environment/database binding, opt-in khusus demo, ownership fixture, penolakan takeover akun existing, transaksi atomik, serta idempotensi. Uji pada database disposable berisi data pembanding dan buktikan data non-fixture tetap utuh.
4. Deploy SHA yang disetujui, addon yang dibutuhkan, build PWA mode staging dan gateway HTTPS satu origin. Jangan menjalankan init/reset ulang terhadap data existing.
5. Provision dua akun uji dengan company/assignment TEST, lalu smoke login, bootstrap/snapshot, maps, cookie dan isolasi foto antar-akun.
6. Lakukan acceptance perangkat dan catat hasil aktual. Preview map bukan check-in/POD; keberhasilan upload evidence tetap tunduk pada geofence strict.

## Status pembuktian

[BU] Deployment scope baru, adaptasi provisioning untuk database demo existing, pembuatan akun server, serta acceptance perangkat belum dibuktikan oleh keputusan ini. Login dashboard sebelumnya belum selesai. Tidak ada perubahan resource/runtime Railway yang dilakukan saat penulisan keputusan ini.

Dokumen STAGING_ACCEPTANCE_KIT.md menyimpan runbook environment terisolasi sebagai alternatif historis. Perintah disposable di sana bukan instruksi langsung untuk database demo existing. HANDOFF dan log lama dipertahankan sebagai riwayat; keputusan ini menjadi rujukan scope terbaru.
