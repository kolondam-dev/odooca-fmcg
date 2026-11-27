# Paket uji fixture POCO M3

Lead menggunakan prosedur ini setelah integrasi kandidat. Bukti awal untuk M2010J19CG, Android 10/API 29, MIUI V12.0.7.0.QJFIDXM ada di handoff. Ulangi install dan cold start pada APK fixture. Redmi 4X tetap [BU] sampai validasi end-to-end sebelum full deploy.

## Opsi HTTPS langsung · Trust sistem Android

Gunakan setelah Lead mengunci origin HTTPS dan nama database aktual. Input berupa origin DNS HTTPS tanpa path, query, fragment atau userinfo. Nama database harus diberikan secara eksplisit. Job build menolak gabungan origin langsung dan CA fixture. Artefak tetap dua APK, checksum dan metadata SHA, origin serta mode TLS. APK fixture memakai ID terpisah dan konfigurasi TLS sistem Android.

```bash
gh workflow run android.yml --ref "$INTEGRATION_BRANCH" \
  -f ref="$INTEGRATION_SHA" -f device_fixture=true -f force_all=false \
  -f device_origin="$APPROVED_HTTPS_ORIGIN" -f device_database="$APPROVED_DB"
```

Di Windows, cocokkan dua hash dengan artefak lalu instal dua paket fixture. Mode ini memakai jaringan HP. Lead dapat menjalankan fase preflight dari fungsi PowerShell di bawah sebelum tes login. Fase itu mengharapkan HTTP 401 untuk bootstrap dan snapshot melalui TLS Android, dengan sesi lokal kosong dan tanpa kredensial. Langkah loopback, SSH forward, CA fixture dan adb reverse hanya berlaku untuk prosedur loopback di bawah.

Jalankan isolation dengan opsi Direct setelah dua nama dan password TEST serta assignment terpisah disetujui. Login uji diteruskan melalui stdin ADB. Hasil kedaluwarsa alami masih [BU] sampai TTL target diketahui dan dapat diuji tanpa revoke. Jangan gunakan TTL contoh loopback untuk gateway demo. Tidak ada perintah operator sampai Lead mengonfirmasi kesiapan.

## Lead · Fixture dan build

1. Pada host Docker yang disetujui, checkout SHA integrasi. Siapkan image Odoo repo dan PostgreSQL 16. Jalankan fixture dalam terminal khusus. Lease berjalan maksimal dua jam dan berhenti dengan Ctrl+C atau SIGTERM. DB, password dan CA baru dibuat setiap kali.

   ```bash
   HANDOFF="$(mktemp -d)/fixture"
   printf '%s\n' "$HANDOFF"
   DEV02B_IDLE_SECONDS=180 bash android/tools/start_dev02b_device_fixture.sh "$HANDOFF"
   ```

2. Dari terminal berbeda, set `HANDOFF` ke path yang dicetak, lalu tunggu `ready.tsv`. Berkas itu memuat SHA, DB, TTL, versi backend dan fingerprint CA. `accounts.env` memuat dua password TEST sementara untuk `staging.capture.1` dan `staging.capture.2`. Gunakan kanal yang disetujui untuk memberikannya ke operator. File ini hanya untuk host privat dan tidak dikirim ke GitHub. Pastikan endpoint dengan CA fixture mengembalikan 401 tanpa sesi.

   ```bash
   curl -q --noproxy 127.0.0.1 --cacert "$HANDOFF/fixture-ca.pem" \
     -s -o /dev/null -w '%{http_code}\n' https://127.0.0.1:18443/api/v1/me/bootstrap
   ```

3. Build CI lewat branch yang memuat definisi workflow. Pakai SHA penuh yang sama dengan `ready.tsv` dan kirim **hanya** CA publik yang di-base64 serta nama database disposable.

   ```bash
   gh workflow run android.yml --ref "$INTEGRATION_BRANCH" \
     -f ref="$INTEGRATION_SHA" -f device_fixture=true -f force_all=false \
     -f device_database="$FIXTURE_DB" -f device_ca_base64="$(base64 -w0 "$HANDOFF/fixture-ca.pem")"
   ```

   Artefak berisi dua APK, `apk.sha256`, dan `build.txt`. Cocokkan SHA, DB, dan fingerprint dengan fixture aktif. Paket debug `com.kolondam.odooca.field.fixture` bisa dipasang berdampingan dengan APK awal. CA publik ditambatkan ke `127.0.0.1` pada build debug fixture. APK release tidak memuat CA fixture.

4. Sediakan TCP forward privat dari loopback Windows port 18443 ke loopback host fixture port 18443. Contoh bila Windows memiliki OpenSSH bawaan dan Lead sudah menyiapkan akses SSH serta host key yang tepercaya:

   ```powershell
   ssh.exe -N -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -L 127.0.0.1:18443:127.0.0.1:18443 "$env:FIXTURE_SSH_TARGET"
   ```

   Jangan membuka gateway atau Postgres ke publik. Bila belum ada forward privat yang disetujui atau OpenSSH/akses tidak tersedia, tandai transport [BU]. Lead memverifikasi HTTPS dari laptop dan perangkat sebelum operator melanjutkan.

## Operator Windows · Setelah Lead mengonfirmasi

Gunakan perangkat POCO M3 yang sudah terhubung dan direktori artefak. Simpan `fixture-ca.pem` publik di situ. Dengan `curl.exe` bawaan yang mendukung `--cacert`, preflight dari laptop harus menghasilkan 401. Tahan langkah install sampai Lead memverifikasi TLS dan transport.

```powershell
curl.exe -q --noproxy 127.0.0.1 --cacert .\fixture-ca.pem -s -o NUL -w "%{http_code}" https://127.0.0.1:18443/api/v1/me/bootstrap
Get-FileHash .\poco-fixture.apk, .\poco-fixture-test.apk -Algorithm SHA256
adb reverse --no-rebind tcp:18443 tcp:18443
adb install .\poco-fixture.apk
adb install .\poco-fixture-test.apk
adb shell am force-stop com.kolondam.odooca.field.fixture
adb shell am start -W -n com.kolondam.odooca.field.fixture/com.kolondam.odooca.field.MainActivity
```

Catat cold start yang benar-benar menampilkan Login. Periksa login dan logout dari UI, refresh snapshot, permission denied/precise serta approximate bila tersedia, GPS indoor/outdoor, dan lock/unlock sesuai [matriks perangkat](DEV02B_DEVICES.md). Pada Android 10/API 29, tandai opsi approximate Android 12 sebagai tidak didukung bila dialog OS mengonfirmasinya. Catat state, umur dan kualitas fix tanpa membagikan koordinat. Temuan overlap status bar tetap terpisah.

Untuk bukti Keystore dan outbox, jalankan instrumentation di APK fixture. Masukkan password TEST melalui prompt dan tulis argumen hanya ke stdin ADB. Jangan aktifkan PowerShell transcript, menyimpan teks mentah, atau membagikan perintah yang sudah berisi nilai password. Selesaikan uji UI dan logout sebelum fase isolation agar antrean sintetis tidak mengganggu catatan manual.

```powershell
function Quote-FixtureArg([string]$Value) {
    if ($Value -notmatch '\A[\x20-\x7E]+\z') { throw 'Argumen TEST harus berupa ASCII tercetak' }
    "'" + $Value.Replace("'", "'" + [char]92 + "''") + "'"
}
function Invoke-FixtureCase([ValidateSet('preflight','isolation','idle_begin','idle_end')][string]$Phase,
                           [int]$IdleSeconds=180, [switch]$Direct) {
    if ($IdleSeconds -lt 15 -or $IdleSeconds -gt 600) { throw 'TTL di luar batas fixture' }
    $secretArgs = ''
    if ($Phase -in 'isolation','idle_begin') {
        $secretA = [pscredential]::new('TEST', (Read-Host 'Password TEST A' -AsSecureString))
        $a = $secretA.GetNetworkCredential().Password
        $secretArgs = "-e passwordA $(Quote-FixtureArg $a)"
        if ($Direct) {
            $loginA = Read-Host 'Nama akun TEST A yang disetujui'
            $secretArgs += " -e loginA $(Quote-FixtureArg $loginA)"
        }
    }
    if ($Phase -eq 'isolation') {
        $secretB = [pscredential]::new('TEST', (Read-Host 'Password TEST B' -AsSecureString))
        $b = $secretB.GetNetworkCredential().Password
        $secretArgs += " -e passwordB $(Quote-FixtureArg $b)"
        if ($Direct) {
            $loginB = Read-Host 'Nama akun TEST B yang disetujui'
            $secretArgs += " -e loginB $(Quote-FixtureArg $loginB)"
        }
    }
    try {
        $run = "am instrument -w -r -e class com.kolondam.odooca.field.DeviceFixtureSessionTest -e dev02b true -e phase $Phase -e idleSeconds $IdleSeconds $secretArgs com.kolondam.odooca.field.fixture.test/androidx.test.runner.AndroidJUnitRunner"
        $raw = $run | adb shell 2>&1
        $exitCode = $LASTEXITCODE
        $marker = @($raw | ForEach-Object { "$_".Trim() } | Where-Object { $_ -eq "INSTRUMENTATION_STATUS: dev02b_result=$Phase=passed" })
        $passed = @($raw | ForEach-Object { "$_".Trim() } | Where-Object { $_ -eq 'OK (1 test)' })
        if ($exitCode -ne 0 -or $marker.Count -ne 1 -or $passed.Count -ne 1) { throw "Fixture $Phase gagal atau bukti tidak lengkap" }
        "$Phase=passed"
    } finally {
        Remove-Variable a,b,secretA,secretB,loginA,loginB,secretArgs,run,raw -ErrorAction SilentlyContinue
    }
}
# HTTPS langsung sebelum login: Invoke-FixtureCase preflight -Direct
# Setelah Lead menyetujui akun untuk HTTPS langsung: Invoke-FixtureCase isolation -Direct
# Contoh loopback berikut memakai TTL fixture.
Invoke-FixtureCase isolation
# Ganti 180 dengan idle_seconds di ready.tsv.
Invoke-FixtureCase idle_begin 180
adb shell am force-stop com.kolondam.odooca.field.fixture
Start-Sleep -Seconds 190
Invoke-FixtureCase idle_end 180
```

Selama jeda TTL, biarkan aplikasi tidak aktif, jangan buka dari launcher, jangan ubah jam, jangan reboot, dan jangan lakukan revoke/logout manual. `idle_end` memerlukan identitas dari storage setelah sesi dibuka ulang dan memeriksa 401 serta pembersihan cookie/CSRF/identitas. Ini memeriksa kedaluwarsa alami **cookie fixture** pada klien. Keputusan TTL native dan bukti pembersihan sesi lama di server tetap di B01. Jika fixture memakai TTL berbeda, sesuaikan jeda ke TTL + 10 detik. Bila kebijakan atau waktu tidak bisa diverifikasi, tandai [BU].

`isolation` memeriksa alias Android Keystore, penyimpanan ciphertext dan pembacaan kembali melalui adapter, logout, isolasi antrean dan pemulihan oleh owner asal. Enqueue bersifat sintetis dan tidak membuat command bisnis. Bukti ini tidak menetapkan tingkat hardware-backed key atau kebijakan registrasi perangkat.

## Cleanup dan bukti

Simpan SHA, fingerprint CA publik, hash kedua APK, API/MIUI, hasil per fase instrumentation dan matriks perangkat. Hapus reverse lalu uninstall hanya dua paket fixture setelah Lead meminta cleanup.

```powershell
adb reverse --remove tcp:18443
adb uninstall com.kolondam.odooca.field.fixture.test
adb uninstall com.kolondam.odooca.field.fixture
```

Tutup forward privat. Lead menghentikan lease dan memeriksa gateway serta inventaris Docker dengan output cleanup tersanitasi. APK awal tetap terpasang. PR #207 menunggu review cakupan POCO M3 dan bukti perangkat.

## Pra-verifikasi Dev

Pada sumber `4832426`, fixture Odoo `19.0.20261112` dan PostgreSQL `16.16` siap lewat HTTPS loopback. Dua akun TEST lulus login, bootstrap dan snapshot. Smoke host memakai TTL 15 detik. Setelah jeda alami, klien tidak lagi mengirim cookie kedaluwarsa dan bootstrap mendapat 401 tanpa revoke manual. Penghentian lease menghapus kredensial sementara, menutup gateway, dan menyisakan nol container, volume serta network fixture.

Kedua APK lokal lulus build dengan CA publik fixture tersebut. Package ID debug dan instrumentation terkonfirmasi berbeda dari APK awal. SHA-256 APK lokal `d0e5bb3fc446580943fa44f0fc05da54bd94e935e7bcaa702ce91c602b5645a4` dan APK tes `7f95b9272075a812993082358bf6a0b9e35b5cf061508a47143d756b17d19fe5`. Lease lokal telah ditutup. Operator memakai artefak CI baru yang cocok dengan lease aktif.

**[BU]** Forward privat ke laptop operator, `adb reverse` dan koneksi TLS dari POCO M3 belum diuji pada checkpoint ini. Keystore, outbox, TTL perangkat, GPS dan lock/unlock menunggu hasil perangkat. TTL cookie dari host tidak membuktikan garbage collection sesi di server.
