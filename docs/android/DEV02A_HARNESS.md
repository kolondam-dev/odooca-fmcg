# DEV-02A · Harness Odoo B09

Jalankan dari commit kandidat. Docker perlu memiliki image yang dibangun dari Dockerfile repo dan image PostgreSQL 16. Runner memilih image lokal melalui ID dan mencatat ID serta versi yang benar-benar dipakai. Pakai ID dari laporan untuk mengulang dengan image yang sama bila masih tersedia.

```sh
docker build -t odooca-fmcg-odoo:latest .
docker pull postgres:16
bash android/tools/verify_dev02a.sh
```

Setel `DEV02A_ODOO_IMAGE` dan `DEV02A_POSTGRES_IMAGE` bila memakai image lokal lain. Harness memasang `id_mobile_api` dan `id_approval` dari arsip commit pada database kosong tanpa data demo. PostgreSQL dan Odoo berada di jaringan Docker internal tanpa port publik. Odoo menerima HTTP melalui loopback di kontainernya. Akun TEST A dan TEST B memiliki assignment, outlet dan produk berbeda dalam satu company IDR dan berbagi kantor berkoordinat sintetis. Skenario memakai HTTP Odoo melalui `HttpCase`.

| Skenario | Bukti penerimaan |
| --- | --- |
| 401 | Snapshot tanpa sesi terautentikasi mengembalikan 401 dan `not_authenticated`. |
| Login dan scope | Kedua akun login lewat JSON-RPC. Bootstrap mengembalikan identitas dan CSRF. Snapshot memuat company, warehouse, hari, produk, outlet dan kantor sesuai assignment. |
| 403 | TEST B mendapat 403 saat membaca gambar outlet TEST A setelah snapshot sendiri berhasil. |
| Command | `sales.order.submit` dikirim dengan versi snapshot dan CSRF. Receipt 200 mencocokkan UUID, status serta referensi ke ledger Odoo dan tepat satu sales order. |
| Rollover WITA | Clock tes berpindah dari malam 16 November menuju 17 November. Snapshot berganti hari dan versi. Versi kemarin menghasilkan 409 tanpa menyimpan command. |
| Scope dicabut | Assignment hari berjalan dinonaktifkan. Sesi yang sama mendapat 403 dari snapshot dan command, tanpa command baru di ledger. |
| Cleanup | Runner menghapus container, volume database dan network fixture. Pemeriksaan akhir memastikan nol resource dengan label run. |

Laporan hanya mencatat rute, status HTTP, metadata versi, identitas TEST, payload sintetis dan kolom receipt yang dipilih. Simpan stdout untuk checkpoint. Batas startup PostgreSQL 90 detik, eksekusi Odoo 15 menit. Untuk latihan jalur gagal, ulangi dengan `DEV02A_ODOO_IMAGE=postgres:16`. Harapkan exit nonzero, `result=failed` dan `cleanup=passed`. Pengaturan ini membuat DB fixture sebelum gagal memulai Odoo.

Tes HTTP B09 dipilih lewat tag opt-in `dev02a`. Saat rollover, Odoo bisa mencatat percobaan tulis pada cursor read-only sebelum otomatis mengulang request dengan cursor read/write. Suite wajib dan pemeriksaan log CI tetap berlaku. Path tes memicu `odoo_install`, `mobile`, dan `upgrade`. Path runner memicu `android`. Jalankan harness manual untuk bukti B09 dan cleanup. Dev memelihara fixture dan laporan. Lead/maintainer backend meninjau perubahan perilaku Odoo. Untuk acceptance lewat APK, Lead perlu menyepakati target disposable HTTPS yang dapat dijangkau runner Android, lalu mengulang alur dengan APK pada SHA yang sama.

## Bukti runtime Cloud

Uji positif memakai image lokal Odoo 19 dan PostgreSQL 16. Bukti HTTP di bawah berasal dari Odoo dan database yang dibuat ulang dari commit yang tercatat. Pemeriksaan ledger dilakukan di transaksi `HttpCase` sebelum rollback. Rollover 16→17 November WITA memicu retry bawaan Odoo ke cursor read/write dan HTTP akhirnya mengembalikan 200. Tes B09 dipilih manual supaya gate log suite wajib tetap dapat mendeteksi ERROR dan Traceback.

### Jalur sukses

```text
fixture=dev02a-v1 commit=bb6a8008b3cd07f2a7329a1468be1c35196fd783 android_commit=97c09a1853e7d2b7ff88652a5500251976d8b461 odoo_image=sha256:70d5f32e8911218b9c844653213631e8261571ac70d463d2dd645f9e003c3fef postgres_image=sha256:6b7038c60456795649816e6ad91b015284a75af3bca7d236b7c6124b56a1d9a3
tracked_tree=clean
transport=HTTP loopback inside Odoo container; no published ports
postgres_version=16.16 (Debian 16.16-1.pgdg13+1)
ODOO_VERSION=19.0.20261112
{"scenario": "installed_addons", "versions": {"id_approval": "19.0.1.0.0", "id_base": "19.0.1.3.4", "id_mobile_api": "19.0.1.4.0"}}
{"error": "not_authenticated", "http": 401, "method": "GET", "route": "/api/v1/sync/snapshot", "scenario": "unauthenticated"}
{"actor": "TEST B", "http": 200, "method": "POST", "route": "/web/session/authenticate", "scenario": "login"}
{"actor": "TEST B", "business_date": "2026-11-16", "http": 200, "method": "GET", "route": "/api/v1/me/bootstrap", "scenario": "bootstrap"}
{"actor": "TEST B", "error": "forbidden", "http": 403, "method": "GET", "own_snapshot_http": 200, "route": "/api/v1/outlets/{outlet_id}/image", "scenario": "other_account_scope"}
{"actor": "TEST A", "http": 200, "method": "POST", "route": "/web/session/authenticate", "scenario": "login"}
{"actor": "TEST A", "business_date": "2026-11-16", "http": 200, "method": "GET", "route": "/api/v1/me/bootstrap", "scenario": "bootstrap"}
{"actor": "TEST A", "business_date": "2026-11-16", "catalog_items": 1, "http": 200, "method": "GET", "office": "test", "outlets": 1, "route": "/api/v1/sync/snapshot", "scenario": "snapshot", "utc": "2026-11-16T15:59:00Z", "version": "odoo-read-v1:96f16b3e1c018c10993d8641ad025ac64e3263cdaeba57f3efade6d1d957ae85"}
{"http": 200, "method": "POST", "receipt": {"client_uuid": "ee4bdfc8-fc02-48d6-89fb-42509a8415b0", "reference": "S00001", "status": "accepted"}, "request": {"client_uuid": "ee4bdfc8-fc02-48d6-89fb-42509a8415b0", "payload": {"lines": [{"product_id": "1", "qty": "1", "uom": "carton"}], "outlet_id": "12", "snapshot_version": "odoo-read-v1:96f16b3e1c018c10993d8641ad025ac64e3263cdaeba57f3efade6d1d957ae85"}, "type": "sales.order.submit"}, "route": "/api/v1/sync/commands", "scenario": "command_receipt"}
{"after_utc": "2026-11-16T16:00:01Z", "after_wita": "2026-11-17T00:00:01+08:00", "before_wita": "2026-11-16T23:59:00+08:00", "business_date": "2026-11-17", "http": 200, "method": "GET", "route": "/api/v1/sync/snapshot", "scenario": "wita_rollover", "stale_command_http": 409, "version": "odoo-read-v1:0dc5947c1a11dc416239637675ce0e064fb07315b01d52a235864d5c0b16b70a"}
{"command_http": 403, "command_persisted": false, "http": 403, "method": "GET", "route": "/api/v1/sync/snapshot", "same_session": true, "scenario": "scope_revoked"}
cleanup=passed run=odooca-b09-tE8dW2zZKO containers=0 volumes=0 networks=0
result=passed
```

### Jalur gagal yang disengaja

Image PostgreSQL dipilih sebagai pengganti Odoo untuk memicu kegagalan setelah DB siap.

```text
fixture=dev02a-v1 commit=bb6a8008b3cd07f2a7329a1468be1c35196fd783 android_commit=97c09a1853e7d2b7ff88652a5500251976d8b461 odoo_image=sha256:6b7038c60456795649816e6ad91b015284a75af3bca7d236b7c6124b56a1d9a3 postgres_image=sha256:6b7038c60456795649816e6ad91b015284a75af3bca7d236b7c6124b56a1d9a3
tracked_tree=clean
transport=HTTP loopback inside Odoo container; no published ports
postgres_version=16.16 (Debian 16.16-1.pgdg13+1)
cleanup=passed run=odooca-b09-RKzx0rShhV containers=0 volumes=0 networks=0
result=failed phase=odoo exit=1
observed_exit=1
```

### Gate Android

Gate lokal dengan `ANDROID_GATE_BASE=f0b3632 bash android/tools/integration_gate.sh --gradle` lulus pada `bb6a800`. Toolchain memakai JDK 17.0.17, Gradle 9.9.1, AGP 9.5.1, SDK 37 dan Build Tools 36.0.0. Pemeriksaan statis mencakup Ruff, 15 manifest, 34 tes CI dan token desain. Laporan Gradle memuat 72 tes domain dan 3 tes data/Robolectric tanpa kegagalan. Lint, APK debug, tiga sampel OpenAPI positif dan empat kasus negatif lulus. SHA-256 APK debug `924f7368595d703ac94b413668c4660d51225a84b1ac9b70f1041aa2dcb16e56`.

Planner memilih `android`, `odoo_install`, `mobile` dan `upgrade`. **Dampak test — TAMBAH.** Tes HTTP opt-in menutup risiko receipt tidak cocok, isolasi assignment antarakun, scope nonaktif, command dengan snapshot kedaluwarsa dan resource fixture tertinggal. Suite remote pilihan planner perlu diverifikasi oleh Lead saat integrasi.

**[BU] APK → HTTPS Odoo disposable.** Bukti di atas berasal dari HTTP loopback di Odoo. Untuk menutup jalur APK, Lead perlu menyepakati target disposable HTTPS dan fixture TEST yang tersedia bagi runner, lalu mengumpulkan bukti login, snapshot dan receipt dari APK pada SHA integrasi. DEV-02B tetap menunggu slice perangkat fisik dan identity.
