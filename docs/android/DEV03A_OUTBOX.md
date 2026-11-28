# DEV-03A · Outbox dan pemulihan receipt

Acuan awal `cbb3e78`, main yang diambil `5b216da`, arahan `4646eec`. Scope ini memakai kontrak command yang sudah aktif. Migrasi dan kebijakan storage mengikuti DEV-03B.

## Cakupan dan bukti

| Pemeriksaan | Oracle |
| --- | --- |
| Odoo sudah commit, respons hilang | Gateway B09 memutus respons setelah menerima body upstream. Probe membuktikan klien gagal menerima receipt pertama. Audit pasca-putus harus sudah menemukan satu ledger dan satu order. |
| Retry | Request memakai byte payload dan UUID yang sama. Receipt replay harus cocok dengan ledger. Audit setelah replay harus identik dengan hasil pasca-putus. |
| 401 pertama dan pergantian akun | Tes HTTP/Room mengikat request ke owner/lease, menghentikan batch pada 401 pertama dan memulihkan item dengan UUID yang sama hanya setelah autentikasi owner asal. |
| Worker overlap | Tes menahan respons saat row `SENDING`, lalu memanggil flush kedua pada repositori singleton yang dipakai worker. Row tetap `SENDING` sampai pengiriman aktif selesai. Jumlah request dan attempt tetap satu. |
| Dependensi | Item dependen dengan waktu enqueue lebih awal menunggu receipt induk, termasuk selama retry/backoff. |
| Recovery Room | Tes membatalkan coroutine setelah commit pada server HTTP sintetis. Row tertinggal sebagai `SENDING` di database file. Setelah database dan repository dibuka ulang, retry memakai payload yang sama dan memulihkan receipt. |
| APK setelah force-stop dan reboot emulator | [BU] Instrumentation tersedia. Cloud tidak menyediakan KVM. |

### Host HTTPS ke Odoo disposable

Dari checkout yang sudah di-commit, gunakan image Odoo repo yang tersedia dan PostgreSQL 16.

```bash
bash android/tools/verify_dev03a_replay.sh
```

Laporan hanya memuat identitas commit, versi image/backend dan fixture, UUID sintetis, hash payload, status/reference receipt, jumlah ledger/order, serta cleanup. Receipt pertama yang hilang ditautkan melalui ledger Odoo. Probe host tidak menjalankan APK.

### Emulator ber-KVM · Prosedur untuk Lead

Gunakan emulator dan fixture disposable baru dari kandidat yang sama. Reuse provisioning SDK/AVD B09. Saat provisioning backend melalui `dev02a_backend.sh`, panggil `backend_start --drop-first-command-receipt`, lalu pertahankan fixture sepanjang pengujian. Gunakan CA fixture khusus debug, `https://127.0.0.1:18443`, nama DB fixture, dan `adb reverse tcp:18443 tcp:18443` sesuai B09. Build `:app:assembleDebug` dan `:app:assembleDebugAndroidTest`, kemudian rekam SHA dan SHA-256 kedua APK. Pakai satu UUIDv4 baru sebagai `DEV02A_UUID` untuk audit Odoo dan instrumentation.

1. Ambil audit `before` melalui `backend_audit` dan pastikan fixture kosong. Jalankan `com.kolondam.odooca.field.OutboxRecoveryFixtureTest` pada AndroidJUnitRunner dengan argumen `dev03a=true`, `phase=first`, `uuid` dan `fixturePassword`. Berikan password hanya melalui stdin ADB dengan fixture sementara. Simpan marker `dev03a_evidence` tersanitasi dan hasil sukses satu test. Audit `after` harus sudah memuat satu order dan satu ledger, sementara APK melaporkan QUEUED, attempt 1, dan hash payload.
2. Lakukan `adb shell am force-stop com.kolondam.odooca.field` pada satu run. Pada run lain, gunakan fixture dan UUID baru, lalu reboot emulator dengan `adb reboot` dan tunggu boot lengkap. Pasang ulang reverse setelah reboot. Jangan hapus data aplikasi.
3. Jalankan kelas yang sama dengan `phase=recover` dan UUID sama. Cek test lulus, hash payload sama, attempt 2 dan referensi receipt cocok dengan ledger. Ambil audit `after_replay` dan bandingkan dengan `after`. Rekam kondisi restart, API/ABI/image, dan cleanup. Marker tanpa hasil instrumentation lulus tidak dianggap bukti.
4. Pengujian file-backed Room menutup skenario `SENDING` akibat pembatalan sebelum receipt diproses. Bila menguji penghentian APK sewaktu request masih aktif, laporkan sebagai skenario terpisah dan buktikan row SENDING serta ledger pasca-putus.

Satu proses aplikasi memiliki satu repositori outbox yang dipakai WorkManager. WorkManager menjadwalkan unique work per owner. Mutex repositori melindungi pembacaan rencana, recovery, dan pengiriman pada pemanggilan yang bertumpuk. Lease sesi tetap menjaga owner dan generation. Status resmi berasal dari receipt Odoo yang cocok dengan UUID.
