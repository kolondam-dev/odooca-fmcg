# SANDBOX — menjalankan Odoo penuh di sandbox agen (tanpa Docker)

Tujuan: agen dapat **menjalankan Odoo 19 sungguhan** untuk memodifikasi, memeriksa, dan memverifikasi kode sebelum diserahkan sebagai patch. Terbukti pada 2026-10-23 (Ubuntu 24.04, root, 1 CPU, ±3,9 GB RAM, Postgres 16, Python 3.12, Odoo commit `f4378f29`).

## Setup satu kali
`scripts/sandbox/sandbox_setup.sh` (apt, source Odoo di SHA terpin, venv, 26 repo OCA dari `oca.lock`, dependensi pip). Disk (`/opt`, `/home/claude`) bertahan; **proses tidak**.

## Awal SETIAP sesi/pemanggilan
`scripts/sandbox/sandbox_up.sh` — menghidupkan Postgres (mati di batas giliran), peran `odoo`, wrapper `odoo` (menambah addons inti ke `--addons-path`, meniru image resmi), symlink `/opt/id-addons`, dan menyalin `deploy/*.sh` ke `/opt/deploy`.
Sandbox bisa di-restart penuh (uptime reset); berkas tetap ada, `/tmp` bisa dianggap sementara.

## Penyesuaian setelah `init.sh` mulai sebagai root (AntiGravity, 2026-10-24)
`deploy/init.sh` kini mulai sebagai root, men-`chown` `$DATA_DIR`, lalu turun ke user `odoo` (gosu/runuser/su). Agar uji sandbox meniru Railway, `sandbox_up.sh` membuat user `odoo` (seperti image resmi), **menyalin** addons ke `/opt/id-addons` (bukan symlink; user `odoo` tidak boleh bergantung pada izin `/home/claude`), dan menghapus `/tmp/odoo.conf` sisa proses root. Uji ulang A dan B dengan versi ini lulus (Odoo berjalan sebagai `odoo`, data dir `odoo:odoo`).

## Uji yang sudah terbukti
| Uji | Perintah | Hasil 2026-10-23 |
|---|---|---|
| Instal + uji `id_base` | `odoo -d ci_db ... -i id_base --test-tags /id_base --stop-after-init` | 0 failed, 0 error; log bersih |
| Instal 65 modul core+OCA | `-i id_base,<daftar>` pada DB kosong | 165 modul terinstal, 0 ERROR; 6 modul `installable: False` (lihat SCOPE §5.3) |
| `init.sh` A: DB kosong | `test_init.sh testA` | HTTP 200 ±66 s, build `base`→ID/IDR→modul |
| B: restart | `test_init.sh testB` | 6 s; semua langkah dilewati |
| C: reset + restore | dump di `/opt/deploy/seed/`, `RESET_DB=tokC1` | 17 s; objek dimiliki `odoo_app` |
| D: token reset lama | `RESET_DB=tokC1` lagi | diabaikan; data utuh |
| E: reset tanpa dump | `RESET_DB=tokC2` | reset lalu build penuh ±69 s |

## Jebakan sandbox (terbukti)
- `pkill -f "odoo-bin"` yang ditulis langsung di perintah **membunuh shell itu sendiri** (hasil `-1`, tanpa keluaran). Pakai `pkill -f "[o]doo-bin"`.
- Shell sandbox adalah `sh` untuk perintah langsung: tidak ada `time (...)`, `disown`, atau `{a,b}` brace expansion. Bungkus dengan `bash -c`/skrip ber-shebang bash.
- Heredoc bersarang: jangan pakai penanda yang sama untuk luar dan dalam (mis. `PY` di dalam `<<'PY'`).
- `apt install node-less` memicu "held broken packages"; tidak diperlukan.
- Proses latar harus `setsid nohup ... &` dan diperiksa lagi di pemanggilan berikutnya; pemanggilan sangat panjang bisa habis waktu, pecah per langkah.
- Postgres mati di batas giliran → selalu mulai dengan `sandbox_up.sh`.
