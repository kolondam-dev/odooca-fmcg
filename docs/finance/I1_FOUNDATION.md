# I1 preparation — roles, navigation dan profil aktivasi versioned

## Scope dan status

[F] Baseline main `abef7bb`: PR95 diterima pemilik pada `b2bd88e`, P2 unmatched
stock GL ditutup dengan regresi native1×/7×, lalu merged. Paket PR95 PASS dalam
scope diagnostik; bukan I0/I3 penuh atau FIN01–58.

[F] Pemilik meminta implementasi lanjut dan deployment ditangani sekaligus
belakangan. Paket ini **persiapan I1**, bukan melompati gate I0 untuk aktivasi
demo. `deploy/init.sh`, default INIT_MODULES, company1, chart, metode costing,
seed dan data demo tidak disentuh. Tidak menjalankan Railway/deployment.

## ADR-I1-01 — OCA account_usability

Tambahkan repo `account-financial-tools` pada exact SHA
`c23fd09977c870eb3db071fca5958b83f699bc4a`, yang telah ditemukan pada audit I0.
Manifest account_usability 19.0.1.1.0, AGPL-3, depends account dan Python
openupgradelib. Docker existing memasang requirements repo (termasuk
openupgradelib); tidak mengambil branch HEAD. Manifest/hook/security/view pada
pin dibaca ulang saat rancangan. Pre-init membuat alias XMLID menu; post-init
memperbarui terjemahan. Tidak ada setting costing/Anglo-Saxon yang dipilih.

OCA mengubah label grup accounting native dan membuat native manager mengimplikasi
native account user. Ini perubahan otorisasi yang disengaja untuk full accounting
menus, bukan sekadar kosmetik; tidak memberi grup accounting kepada Sales/driver.
Native preservation dan negative-role probes wajib lulus sebelum penerimaan.
Pin ini juga membawa source asset tools, **bukan otomatis instalasi asset tools**.

## Role dan navigation

Addon `id_finance_foundation` LGPL-3 bergantung account_usability dan
id_finance_reporting. Tidak menambahkan ACL write atau posting engine sendiri.

| Role baru | Native implied | Batas |
|---|---|---|
| Finance Reader | account readonly | Baca ledger, tanpa posting |
| Finance Accountant | Reader + account user | Posting native, bukan konfigurasi manager |
| Finance Manager | Accountant + account manager | Konfigurasi sesuai native manager |
| Tax PIC (Read-only Preparation) | Reader | Bukan hak upload/sign/filing resmi; belum role pajak final I6 |

Grup tidak diberikan otomatis ke user demo. Hak bersifat aditif: user Reader
yang juga diberi Accountant tetap memiliki hak Accountant; label Reader tidak
mencabut hak grup lain. Operator harus mereview kombinasi role saat rollout.

Menu Finance menunjuk wizard OCA Trial Balance, General Ledger, Journal Ledger,
Open Items dan Aged Partner Balance. Account_usability membuka menu native yang
hilang; custom hanya shortcut. Render GL/journal/open-items/aging diberi guard
accounting/company sebelum query, memakai guard Trial Balance existing. Sales
dan foreign active company ditolak oleh server, tidak bergantung menu tersembunyi.
Penerimaan numeric/export/browser untuk empat laporan tambahan tetap bagian I2/I8;
menu terpasang tidak berarti laporan tersebut accepted.

## Profil `finance_reports_v1`

`scripts/ops/finance_activation.py` menyediakan `plan(env)` tanpa write dan
`attest(env)` maintenance-superuser only. Planner merekam state/version **seluruh
dependency closure** registry; unknown profile/missing dependency ditolak.
Attestation ditolak jika ada dependency belum installed. Marker
`id_finance.activation.finance_reports_v1` hanya dibuat setelah seluruh closure
installed; pemanggilan ulang identik menghasilkan UNCHANGED tanpa write. Versi
berubah menolak overwrite: buat versi profil baru melalui review. Modul ini
tidak melakukan install, commit atau mengubah chart/role/costing.

Marker membuktikan registry saat observasi, **bukan** pengesahan COA, UAT, bukti
full source integrity/image digest, atau izin deployment. Manifest/source pin dan
artifact image tetap bukti terpisah. Attestation via Python maintenance bukan RPC.

Runbook berikut **belum dijalankan di demo**; hanya untuk rollout berotorisasi:
1. Selesaikan gate I0, backup+restore rehearsal, inventory/image source dan audit
   user/company aktif. Review perubahan role OCA dan maintenance window.
2. Dari Odoo shell pada image yang benar, import finance_activation dan baca plan.
3. Jalankan CLI normal `-i id_finance_foundation --without-demo=true`, bukan reset,
   reseed, FORCE_UPGRADE permanen atau install saat worker masih melayani transaksi.
4. Verifikasi snapshot business sources sebelum/sesudah, menu/role/company dan
   report smoke. Baru panggil attest dan commit terkontrol. Marker tidak mengganti
   langkah verifikasi tersebut.
5. Restart dan ulang plan/attest; harus UNCHANGED. Upgrade versi baru melalui profil
   baru yang direview; jangan menghapus marker untuk menutupi drift.

## CI native yang dirancang

Database reports disposable mula-mula memasang profil lama, lalu fixture persisten
dua-company ledger dan satu-company stock (quotation receipt/delivery/return,
internal/consignment/grouped journal). Fingerprint mencakup IDs/state/date/nama
jurnal, debit/credit/balance/account/product/partner AML, accounts/company membership,
native stock move/journal links, quant/reservation/owner/lot, category/company
costing/valuation/currency/chart, dan partial reconcile records.

Urutan terpisah proses: prepare+commit fixture -> install foundation -> verify+
attest -> upgrade foundation -> verify+attest. Kedua verify wajib fingerprint
identik, profile replay UNCHANGED, native five-role menu visibility dan Trial
Balance oracle; Reader/Tax create journal ditolak, Accountant/Manager posting
positif, Sales render dan foreign-company render lima report ditolak. User probes
tanpa sudo, rollback di akhir. Fixture permanen **hanya di DB CI disposable**;
tidak menambah company pada demo.

[BU] Native install/upgrade dan source preservation masih menunggu CI exact HEAD;
definisi workflow bukan bukti PASS. Tidak ada browser acceptance yang diklaim.

## Gate I0/roadmap yang tetap terbuka

| Gate | Status |
|---|---|
| Audit runtime/containment, golden ledger/security, costing foundation PR89–95 | PASS sesuai scope PR; snapshot runtime lama bukan observasi terbaru |
| Current effective costing/ownership dan saldo opening company1, diakses resmi | Perlu observasi/read-only terbaru sebelum aktivasi demo |
| COA/control-account mapping final dan kebijakan report/Tax | Perlu persetujuan pemilik; existing chart ID bukan otomatis mapping accepted |
| Official-number provenance dan UAT Coretax | I6, tidak disintesis |
| I1 install/upgrade/menu/role/profile | Disiapkan paket ini; belum native PASS/full I1 accepted |
| I2–I8 / FIN01–58 | Tetap backlog dan gate per IMPLEMENTATION_PLAN |

Tidak menandai N/A/ACCEPTED pada katalog karena menu atau source tersedia.
