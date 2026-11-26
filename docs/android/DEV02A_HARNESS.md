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

## APK → HTTPS → Odoo

Pakai emulator disposable dengan ADB dan target HTTPS yang disetujui Lead. Operator backend menyiapkan DB kosong bernama `fmcg_staging_…` dengan `id_mobile_api` dan `id_approval`, mengaktifkan IDR, lalu menjalankan `scripts/ops/provision_mobile_staging.py` melalui Odoo shell. Provisioner membuat dan commit fixture TEST. Gunakan kata sandi acak sekali pakai dalam bentuk heksadesimal untuk kedua akun TEST dan pilih hari operasional WITA. Selesaikan sekali jalan sebelum pergantian hari. Android memakai endpoint TLS yang sertifikatnya dipercaya emulator.

Pada checkout kandidat, konfigurasi APK dengan origin HTTPS tanpa garis miring akhir dan nama DB fixture. Instal APK serta APK tes pada emulator baru.

```bash
cd android
./gradlew --no-daemon :app:assembleDebug :app:assembleDebugAndroidTest \
  "-Podooca.baseUrl=$DEV02A_BASE_URL" "-Podooca.database=$FMCG_STAGING_DATABASE"
app=app/build/outputs/apk/debug/app-debug.apk
tests=app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
sha256sum "$app" "$tests"
adb install "$app"
adb install "$tests"
cd ..
```

Tetapkan `DEV02A_UUID` satu kali dengan `python3 -c 'import uuid; print(uuid.uuid4())'`. Pada host Odoo, ambil tiga checkpoint melalui Odoo shell dengan konfigurasi fixture. Pakai `FMCG_STAGING_DISPOSABLE=YES`, nama DB yang sama, dan UUID tersebut pada ketiga eksekusi `scripts/ops/verify_mobile_dev02a_receipt.py`. Simpan hanya objek JSON stdout dari setiap checkpoint. Contoh audit baseline di host Odoo dengan variabel fixture yang sudah diekspor.

```bash
odoo shell -c "$DEV02A_ODOO_CONF" -d "$FMCG_STAGING_DATABASE" --no-http \
  < scripts/ops/verify_mobile_dev02a_receipt.py | sed -n '/^{"approvals":/p' > before.json
```

Urutannya harus sebagai berikut.

| Urutan | Aksi | Bukti |
| --- | --- | --- |
| 1 | Audit sebelum submit. | `before.json`, company fixture belum memiliki ledger atau order. |
| 2 | Jalankan instrumentation fase `first`. | `first.json`, login dan snapshot berhasil dari APK, lalu receipt dari HTTPS. |
| 3 | Audit setelah submit dan sebelum replay. | `after.json`, satu ledger dan satu sales order. |
| 4 | Jalankan fase `replay` dengan UUID, akun dan `snapshot_version` dari fase pertama. | `replay.json`, payload dan receipt harus sama. |
| 5 | Audit setelah replay. | `after_replay.json`, checkpoint harus identik dengan langkah 3. |

Gunakan credential akun pertama hanya di runner ephemeral. Jalankan cuplikan berikut di host ADB dengan `set -euo pipefail`, `set +x` dan `umask 077`. Jangan sertakan raw stdout atau logcat dalam artefak.

```bash
run_apk_phase() {
  local phase=$1 version=${2:-} raw
  [[ $phase == first || $phase == replay ]]
  [[ $DEV02A_TEST_PASSWORD =~ ^[a-f0-9]{48}$ ]]
  [[ $DEV02A_UUID =~ ^[a-f0-9-]{36}$ ]]
  [[ -z $version || $version =~ ^odoo-read-v1:[a-f0-9]{64}$ ]]
  raw=$(printf '%s\n' "am instrument -w -r \
    -e class com.kolondam.odooca.field.DisposableOdooReceiptTest \
    -e dev02a true -e phase $phase -e uuid $DEV02A_UUID \
    -e fixturePassword $DEV02A_TEST_PASSWORD -e snapshotVersion '${version}' \
    com.kolondam.odooca.field.test/androidx.test.runner.AndroidJUnitRunner" \
    | timeout 120 adb shell)
  grep -Fxq 'OK (1 test)' <<< "${raw//$'\r'/}"
  sed -n 's/^INSTRUMENTATION_STATUS: dev02a_evidence=//p' <<< "${raw//$'\r'/}" > "$phase.json"
}

# Jalankan setelah before.json tersedia.
run_apk_phase first

# Jalankan setelah after.json tersedia.
version=$(python3 -c 'import json; print(json.load(open("first.json"))["request"]["payload"]["snapshot_version"])')
run_apk_phase replay

# Jalankan setelah after_replay.json tersedia.
python3 android/tools/verify_dev02a_apk.py first.json replay.json before.json after.json after_replay.json
```

Verifier mencocokkan UUID, status, referensi, fingerprint payload, scope akun, dan order dengan ledger Odoo. Verifier juga membandingkan ledger, order, picking, invoice, dan approval fixture sebelum dan setelah replay. Instrumentation berjalan di proses APK dan memakai `AppContainer`, sesi serta klien HTTP produksi. Skenario menguji jalur klien backend. Interaksi UI order dan pengiriman lewat antrean Android memiliki acceptance terpisah.

Simpan lima JSON tersanitasi dan hasil verifier, SHA integrasi Android/Odoo, hash kedua APK, API/ABI dan image emulator, versi Odoo/PostgreSQL/addon/fixture, serta bukti cleanup. Operator menghentikan emulator dan menghapus DB, filestore, dan resource TLS disposable pada jalur sukses maupun gagal. Pastikan resource yang berlabel run sudah hilang sebelum menutup checkpoint.
