# Business Meta & Playbook Distributor FMCG

*Versi 0.4 (draft kerja). Disusun dari brief bisnis distributor FMCG Indonesia. Bagian bertanda **\[Validasi\]** perlu dikonfirmasi ke klien atau versi Odoo yang dipakai.*

### Catatan Perubahan v0.4 (2026-10-23)
- **Format:** heading §3 diperbaiki (judul menyatu dengan paragraf dan ada heading kosong); "Lima proses wajib" → "Enam proses wajib" di §3.2 (tabel memuat enam proses, termasuk Payroll); escape asterisk di §3.1; baris HRIS di tabel §5 diseragamkan; butir tambahan di §7 dan §8 memakai penanda daftar yang sama.
- **Keputusan baru:** aplikasi mobile terpadu dengan tab dinamis menurut *app role* (§4.3, §5.3); aplikasi mobile selalu sinkron ke Odoo sebagai stack utama, sinkronisasi ke legacy DMS lewat ekspor manual (§5.2, §5.3); antarmuka Indonesia penuh + English, istilah umum FMCG dipertahankan (§5.3).
- **Pemetaan §6:** baris bertanda "terverifikasi 2026-10-23" diperiksa pada source Odoo 19 CE dan OCA 19.0 (keberadaan modul, belum diuji berjalan).
- **§10:** jawaban pertanyaan 1, 2, 14 dicatat; pertanyaan 16–18 ditambahkan.

## 1. Tujuan dan Cara Memakai Dokumen

Dokumen ini punya dua bagian. **Business Meta** adalah peta konteks bisnis distributor FMCG: siapa pelakunya, bagaimana uang, barang, dan dokumen bergerak, serta di mana risikonya. **Playbook** adalah panduan bisnis distributor: kebijakan dan aturan main (harga, diskon, kredit, approval, biaya), master data, kontrol, dan kebutuhan sistem. Panduan implementasi Odoo yang rinci dibahas di dokumen terpisah; bagian 6 dan 7 di sini hanya jembatan ke dokumen tersebut.

Dokumen ini dipakai untuk menyamakan bahasa antara tim implementor dan klien, sebagai bahan discovery workshop, dan sebagai baseline scope sebelum masuk desain solusi.

## 2. Business Meta

### 2.1 Hierarki Ekosistem

Rantai nilainya: **Principal → Distributor → Customer**.

- **Principal**: pemilik brand/pabrik yang menunjuk distributor lewat PKS (perjanjian kerja sama). Distributor bisa *tunggal* (satu principal) atau *multi-principal*.
- **Distributor**: membeli dari principal, menyimpan di gudang, menjual dan mengirim ke outlet dalam area coverage resmi.
- **Customer**: outlet (modern trade, general trade, retail, institusional) maupun perorangan.

Implikasi desain: sistem harus memisahkan data, target, harga, dan laporan **per principal**, karena tiap principal punya aturan, target, dan format pelaporan sendiri. Pada distributor multi-principal, ini menjadi dimensi utama (bukan sekadar filter).

### 2.2 Principal, Produk, dan Target

- Kategori utama: food, healthcare, personal care, home cleaning, dan lainnya.
- Hierarki produk mengikuti kode brand dan sub-brand milik principal: Principal → Kategori → Brand → Sub-brand → SKU (beserta kemasan/UoM).
- Tiap brand/kategori punya **segmen customer sasaran**.
- Tiap principal menetapkan **target dan KPI performa** selama masa PKS (sell-in, sell-out/coverage, active outlet, distribusi numerik, dsb.). **\[Validasi\]** KPI mana yang dipantau di sistem.
- Principal membagi "kue" distributorship per area, jadi hak distribusi per brand per wilayah harus tercatat.

### 2.3 Coverage Area dan Stratifikasi Harga

- Area dibagi menurut **jangkauan** (dalam kota vs luar kota) dan menurut **tipe kepadatan** (urban, rural, dsb.).
- Coverage resmi dari principal membatasi ke mana distributor boleh menjual.
- Area memengaruhi **harga dan margin**: outlet luar kota umumnya mendapat harga lebih tinggi / margin berbeda. Harga bisa berasal dari kebijakan principal maupun kebijakan internal distributor.

Implikasi: pricelist tidak cukup berdasarkan produk. Harga ditentukan oleh kombinasi **principal/brand × channel × area × tier customer × kuantitas/promo**.

### 2.4 Channel Penjualan

| Channel | Contoh outlet | Karakter |
| --- | --- | --- |
| Modern Trade (MT) | Supermarket, hypermarket, National Key Account | Kontrak/listing, syarat dagang khusus, TOP lebih panjang |
| General Trade (GT) | Grosir, toko kelontong besar, supermarket lokal | Volume tinggi, kunjungan rutin |
| Retail | Perorangan, rombong, kios | Volume kecil, jumlah outlet banyak, sering tunai |
| Institusional | Yayasan, kampus, rumah sakit | Pesanan terjadwal/kontrak, dokumen administratif ketat |

Setiap channel punya aturan harga, diskon, TOP, dan alur dokumen sendiri.

### 2.5 Model Penjualan

1. **Taking Order (TO)**: salesman berkunjung sesuai PJP, ambil order, barang dikirim kemudian oleh tim logistik.
2. **Canvassing**: salesman membawa stok di kendaraan dan menjual serta menyerahkan barang di tempat.
3. **Direct Selling**: penjualan langsung (kantor/gudang/key account).

Sistem harus mendukung ketiganya, termasuk stok kendaraan canvass sebagai lokasi stok tersendiri dan rekonsiliasi saat closing.

### 2.6 Alur Taking Order sampai Cash (End-to-End)

1. **PJP (Personal Journey Plan)**: tiap salesman punya daftar outlet harian sesuai channel dan area, dengan rute yang sudah dioptimasi.
2. **Kunjungan**: salesman menjalankan guideline penjualan principal (mis. prinsip 7S). Check-in harus tervalidasi lokasi (geotag outlet terdaftar).
3. **Pencatatan order**: manual (WhatsApp group) atau lewat aplikasi mobile ordering. Target: seluruhnya via aplikasi, masuk ke server otomatis.
4. **Sales Admin**: menerima order, validasi stok real-time, kadang konfirmasi manual ke supervisor gudang untuk SKU tertentu, lalu sinkronisasi menjadi **Sales Order (SO)**.
5. **Picking list**: gudang menerbitkan picking list berdasarkan satu atau beberapa SO, dengan urutan pengambilan yang sistematis (batch picking).
6. **Pick, Pack, Ship**: barang dipick, divalidasi, lalu dibuat packing list / **Delivery Order (DO)** oleh admin gudang atau kepala gudang.
7. **Invoice**: DO menjadi dasar penerbitan faktur dan dokumen dasar pengiriman.
8. **Routing pengiriman**: DO dikelompokkan ke kendaraan dengan prinsip efisiensi jarak, coverage, dan utilisasi armada (okupansi dan kubikasi).
9. **Pengiriman**: satu kendaraan dengan satu driver dan satu atau lebih helper. Outlet menerima barang dan menandatangani faktur.
10. **Pembayaran sesuai TOP**:
    - **Cash**: driver menerima uang tunai atau bukti transfer. Bukti transfer wajib dikonfirmasi ke admin yang mengontrol mutasi rekening sebelum divalidasi.
    - **Kredit**: faktur menjadi piutang (AR).
11. **Validasi pengiriman** di aplikasi delivery: omset dan penerimaan tercatat real-time.
12. **Closing harian**: kepala gudang memvalidasi barang keluar. Kasir/finance memvalidasi faktur yang dibawa, terbayar, menjadi piutang (faktur asli kembali), dan tertolak. Setoran uang dicocokkan dengan dokumen.

### 2.7 Penanganan Faktur Tertolak dan Pending

SOP berbeda tiap distributor: ada yang mewajibkan **pembatalan faktur**, ada yang mengizinkan **pending** dan kirim ulang selama beberapa hari. Umumnya distributor tidak ingin faktur pending menumpuk karena mengganggu operasional dan membuka celah fraud. Karena itu sistem perlu **parameter kebijakan per distributor**: batas hari pending, aturan pembatalan, dan siapa yang berwenang menyetujui.

### 2.8 Piutang (AR) dan Penagihan

- Faktur kredit menjadi dokumen tambahan yang dibawa salesman sesuai **PJP dan jatuh tempo**: tanggal jatuh tempo harus selaras dengan rute kunjungan.
- Perlu fleksibilitas konfigurasi: faktur boleh dibawa di luar rute atau di luar jatuh tempo dengan persetujuan/kondisi tertentu.
- Fokus finance di sisi DMS: memaksimalkan potensi AR, meminimalkan kebocoran, menjaga cash flow, serta notifikasi efisiensi diskon, audit trail, approval diskon dan SO, analisa AR, dan analisa produktivitas.

### 2.9 Gudang

- Satu distributor dapat memiliki **lebih dari satu gudang fisik**. Tiap gudang bisa terdiri atas area: gudang utama, inbound/receiving, dan outbound (kadang digabung, kadang terpisah).
- Penerimaan dan pengeluaran barang mengikuti SOP masing-masing, dengan common practice yang serupa.
- Kebutuhan lanjutan (WMS): zoning dan penempatan barang, layout/stacking/racking, penelusuran **batch/kode produksi dan ED (expired date)**, visualisasi fast vs slow moving, deteksi potensi **bad stock**, peringatan terkait procurement, efisiensi routing di dalam gudang, dan idealnya visualisasi layout 3D dengan tingkat kesesuaian aktual (target ≥95% bila semua comply).

### 2.10 Armada Logistik

Armada FMCG umumnya dibagi menurut tipe operasional, misalnya: 6 roda long/standard (cold diesel double), 4 roda long/standard (cold diesel engkel), L300 box, Grand Max (box, blind van, bak terbuka). **\[Validasi\]** daftar tipe aktual klien.

Setiap tipe wajib punya master data: **dimensi, kubikasi, tonase, dan batas tonase menurut KIR**. Data ini menjadi dasar perhitungan okupansi dan utilisasi.

### 2.11 Titik Risiko dan Kontrol Utama

| Area | Risiko | Kontrol yang dibutuhkan |
| --- | --- | --- |
| Order | Order fiktif / di luar lokasi | Validasi geotag, foto bertimestamp |
| Stok | Selisih fisik vs sistem, ED terlewat | FEFO, lot tracking, cycle count |
| Pengiriman | Barang tidak sampai, DO tertahan | Stock on Delivery, foto serah terima, batas pending |
| Uang | Uang di jalan hilang, bukti transfer palsu | Money in Transit, konfirmasi mutasi rekening, rekonsiliasi setoran |
| Diskon | Diskon di luar kebijakan | Matriks approval, audit trail |
| AR | Piutang macet | Aging, limit kredit, jadwal tagih mengikuti PJP |

## 3. Aturan Bisnis dan Kontrol

Bagian ini memuat aturan yang membedakan distributor FMCG dari dagang biasa: diskon berlapis, persetujuan berjenjang, biaya operasional yang terklasifikasi, analitik multi-dimensi, dan kepatuhan pajak.

### 3.1 Diskon Bertingkat dan Fleksibel

Diskon bekerja di dua level dan harus bisa diatur lewat konfigurasi maupun aturan, tanpa pengembangan ulang setiap ada skema baru.

| Level | Jumlah | Cara kerja |
| --- | --- | --- |
| **Line discount** (per baris item) | 1 sampai 5 kolom | Dihitung berurutan per baris. Kolom yang aktif bisa berbeda per principal, channel, atau jenis dokumen. |
| **Footer discount** (per dokumen) | 1 sampai 2 baris | Dikenakan pada total dokumen/faktur, misalnya diskon tunai atau diskon kontrak. |

- **By config**: jumlah kolom diskon aktif, nama kolom, urutan hitung, dan pembatasan input manual.
- **By rules**: diskon otomatis berdasarkan kondisi: principal, brand, SKU, channel, area, tier customer, periode, kuantitas, nilai transaksi, atau kombinasi produk.
- Tiap diskon membawa kode, **sumber pendanaan** (principal atau distributor), batas persentase atau nilai, dan jalur approval (lihat 3.2).
- Data diskon harus bisa dipakai untuk **klaim ke principal** dan analisa efisiensi diskon.

**\[Validasi\]** Default: line discount dihitung **berantai (cascading)**, dan metode hitung (berantai atau dijumlahkan) tersedia sebagai konfigurasi per principal atau channel. Footer discount mengikuti pola umum: dikenakan atas subtotal setelah line discount dan sebelum PPN. Perlu dikonfirmasi apakah kolom diskon harus tampil terpisah di faktur cetak.

### 3.2 Approval Workflow

Enam proses wajib melewati persetujuan berjenjang. Ambang batas di bawah adalah contoh dan perlu ditetapkan klien.

| Proses | Contoh pemicu approval | Pemberi approval (contoh) |
| --- | --- | --- |
| **Sales ordering** | Melebihi limit kredit, order di luar PJP, stok kurang, harga di luar pricelist | Supervisor sales, kepala cabang |
| **Diskon** | Diskon di atas batas per role atau per principal, diskon di luar rules | Supervisor, manajer sales, direksi (bertingkat) |
| **Double invoice (faktur baru saat ada piutang)** | Customer masih punya piutang terbuka dan kebijakan kredit (3.6) mewajibkan approval untuk faktur baru, atau limit terlampaui | Finance atau manajer yang ditunjuk |
| **Pemajuan tagihan** | Faktur dibawa ke penagihan sebelum jatuh tempo atau di luar rute PJP | Supervisor sales, finance |
| **Pengeluaran biaya operasional** | Setiap pengeluaran melewati nilai tertentu atau di luar anggaran | Kepala gudang/logistik, finance, direksi (sesuai nominal) |
| Payroll | Setiap periode payroll sebelum jurnal diposting | Owner |

Aturan umum: matriks approval per **nominal dan peran**, eskalasi otomatis bila melewati SLA, delegasi saat approver cuti, approval lewat web maupun mobile, dan **audit trail** lengkap (siapa, kapan, alasan, perubahan nilai).

### 3.3 Biaya Logistik dan Warehouse

Semua biaya wajib punya akun, cost center, dimensi analitik (3.4), bukti (nota/foto), dan jalur approval. Kolom "Sumber" menandai apakah jenis biaya berasal dari brief atau usulan tambahan.

| Kelompok | Jenis biaya | Sumber |
| --- | --- | --- |
| Gudang | Biaya bongkar inbound | Brief |
| Gudang | Biaya bongkar outbound | Brief |
| Gudang | Biaya pemusnahan barang | Brief |
| Gudang | Biaya maintenance bangunan | Brief |
| Gudang | Material pengemasan dan pallet; APD dan K3 gudang; asuransi stok; keamanan dan kebersihan gudang; selisih stok dan penyusutan | Usulan |
| Logistik dan armada | BBM logistik | Brief |
| Logistik dan armada | BBM canvassing | Brief |
| Logistik dan armada | BBM penjualan | Brief |
| Logistik dan armada | Parkir dan retribusi | Brief |
| Logistik dan armada | Maintenance logistik | Brief |
| Logistik dan armada | Sewa kendaraan | Brief |
| Logistik dan armada | Tol; pajak kendaraan (1 tahun dan 5 tahun) dan KIR; ban; asuransi kendaraan; denda/tilang; uang makan crew | Usulan |
| Kantor dan umum | Maintenance kantor | Brief |
| Kantor dan umum | ATK | Brief |
| Kantor dan umum | Listrik | Brief |
| Kantor dan umum | PDAM | Brief |
| Kantor dan umum | Konsumsi dan rumah tangga | Brief |
| Kantor dan umum | Telepon dan internet; sewa gudang/kantor; perizinan dan legal; langganan software; biaya bank | Usulan |
| Lainnya | Biaya umum lainnya (akun penampung dengan batas nilai dan wajib keterangan) | Brief |

Kontrol khusus: BBM dibandingkan dengan jarak tempuh dan kendaraan (rasio per kendaraan), maintenance dan ban terkait ke kendaraan tertentu, dan biaya bongkar terkait ke dokumen penerimaan atau pengeluaran.

### 3.4 Analytical Accounting

Setiap transaksi dan biaya membawa dimensi analitik agar laba rugi dapat dipotong dari banyak sudut.

| Dimensi | Terisi otomatis dari | Pertanyaan yang dijawab |
| --- | --- | --- |
| Produk (principal, brand, kategori) | Baris produk | Margin dan biaya per principal dan brand |
| Customer | Master partner | Profitabilitas outlet dan piutang per outlet |
| Channel | Master customer | Margin MT vs GT vs retail vs institusional |
| Area | Master customer | Biaya dan harga luar kota vs dalam kota |
| Bisnis / departemen | Pengguna atau dokumen | Beban per departemen |
| Cost center | Karyawan, kendaraan, gudang | Biaya per unit kerja |
| Salesman / tim | Order dan PJP | Produktivitas dan biaya penjualan |
| Kendaraan dan gudang | Pengiriman dan biaya | Biaya per drop, per armada, per gudang |

Dimensi yang relevan **wajib terisi** pada transaksi dan baris biaya. **\[Validasi\]** penggunaan fitur analytic plans bergantung versi Odoo.

### 3.5 Perpajakan: e-Faktur dan Coretax

Per Oktober 2026, penerbitan faktur pajak berjalan di Coretax DJP, yang sejak 2025 menggantikan aplikasi e-Faktur desktop ([pajak.go.id](https://pajak.go.id/en/node/113576)). Faktur dianggap selesai setelah berstatus approved. Sebagian PKP tertentu masih diizinkan memakai aplikasi e-Faktur lama sebagai saluran tambahan, dan datanya dimigrasikan ke Coretax ([DDTCNews](https://news.ddtc.co.id/berita/nasional/1808885/migrasi-data-faktur-dari-e-faktur-ke-coretax-paling-lambat-2-hari)).

| Kebutuhan | Implikasi untuk implementasi |
| --- | --- |
| Faktur pajak lewat Coretax (XML, H2H atau portal, status write-back) | *Terverifikasi 2026-10-23:* `l10n_id_efaktur_coretax` ada di CE 19 (XML faktur keluaran/retur, NITKU, NIK, PKP). Kustom untuk kesiapan data, pelacakan status, dan antrean kirim ulang; H2H/PJAP fase lanjut | Konfigurasi + kustomisasi (H2H: integrasi) |
| Validasi real-time | Faktur ditolak bila data tidak lengkap, jadi kualitas data partner (NPWP, nama, alamat) menjadi kontrol pajak ([VATCalc](https://www.vatcalc.com/?p=7787)) |
| Jalur integrasi | Volume tinggi dapat memakai host-to-host (H2H); lainnya lewat portal atau penyedia (PJAP) |
| Status faktur | Status Coretax (dalam proses, approved, ditolak) dikembalikan ke faktur di Odoo |
| Pembeli dan kredit pajak masukan | Pembeli baru dapat mengkreditkan PPN bila faktur penjual sudah tervalidasi, sehingga keterlambatan terbit berdampak ke customer |
| Bukti potong (e-Bupot) | Dihasilkan dari payroll (PPh 21) dan transaksi pemotongan lain |

**\[Validasi\]** status PKP klien (apakah tergolong PKP tertentu), tarif PPN yang berlaku, dukungan Coretax pada lokalisasi Indonesia untuk versi Odoo yang dipilih, dan perlu tidaknya konektor kustom atau PJAP. Ketentuan DJP berubah cepat, jadi verifikasi ke sumber resmi sebelum desain final.

### 3.6 Kebijakan Kredit dan Piutang Baru

Apakah customer yang masih berpiutang boleh dibuatkan faktur baru berbeda di tiap distributor: ada yang mengizinkan selama limit belum tercapai, ada yang mengunci sampai faktur lama lunas. Karena itu kebijakan ini disediakan sebagai mode yang dikonfigurasi, bukan satu aturan tetap.

| Mode | Aturan | Gunakan bila (contoh) |
| --- | --- | --- |
| **1. Strict lock** | Tidak ada faktur baru selama masih ada piutang terbuka; wajib lunas dulu | Customer baru atau berisiko tinggi |
| **2. Berbasis limit** | Faktur baru boleh selama piutang terbuka ditambah order baru tidak melebihi limit kredit | Customer reguler |
| **3. Limit dan jatuh tempo** | Seperti mode 2, tetapi diblok bila ada faktur lewat jatuh tempo lebih dari N hari | Penagihan ketat |
| **4. Override dengan approval** | Pelanggaran limit atau aturan memicu approval, bukan blokir mutlak | Pengecualian bisnis |

- Kebijakan default ditetapkan per distributor dan dapat ditimpa per principal, channel, atau customer.
- Setiap partner wajib memiliki **limit kredit** dan **TOP** (bagian 4.1).
- Titik pemeriksaan (input order, konfirmasi SO, penerbitan DO/faktur, sebelum pengiriman) dapat dipilih lewat konfigurasi.
- Bila terblokir, order tertahan, salesman dan sales admin mendapat notifikasi, dan jalur approval (3.2) berjalan dengan alasan serta audit trail.
- Pemajuan tagihan (sebelum jatuh tempo maupun di luar rute PJP) mengikuti jalur approval yang sama.

**Eksposur kredit** yang dibandingkan dengan limit mencakup piutang terbuka, **SO pending** (belum difaktur), dan **barang dalam pengiriman** (stock on delivery). Ketiga komponen ini dapat diaktifkan atau dimatikan satu per satu di pengaturan invoice, sehingga tiap distributor menyesuaikan sesuai kebijakannya. **\[Validasi\]** komponen yang aktif secara default.

## 4. Master Data dan Entitas

Kualitas master data menentukan kualitas kontrol: validasi lokasi, faktur pajak, penugasan armada, dan analitik semuanya bergantung pada data partner, kendaraan, dan karyawan yang lengkap.

### 4.1 Partner (Vendor dan Customer)

| Kelompok data | Isi | Status |
| --- | --- | --- |
| Identitas legal partner | Jenis (perorangan/badan usaha), nama legal, NPWP, NIK (perorangan), dokumen badan usaha, status PKP | Wajib |
| PIC | Nama, jabatan, identitas legal (NIK dan foto identitas) | Wajib |
| Kontak PIC | Nomor HP | Wajib |
| Kontak PIC | Nomor telepon kantor | Opsional |
| Alamat utama | Provinsi, kabupaten/kota, kecamatan, desa/kelurahan, jalan, penanda lokasi, **geotag** (koordinat) | Wajib |
| Alamat tambahan | Alamat gudang atau pengiriman yang berbeda dari alamat utama, tiap lokasi dengan alamat presisi, geotag, dan **PIC sendiri** | Wajib bila ada |
| Kredit | Limit kredit (plafon piutang atau utang) dan TOP (term of payment) | Wajib |

Catatan: wilayah administratif dari provinsi sampai desa/kelurahan sebaiknya dipilih dari master wilayah resmi (bukan teks bebas) agar laporan per area konsisten. **\[Validasi\]** sumber data wilayah yang dipakai.

### 4.2 Kendaraan

| Kelompok | Data | Status |
| --- | --- | --- |
| Identitas (semua kendaraan) | Brand, tipe, warna, tahun pembuatan, nomor polisi, nomor rangka, nomor mesin | Wajib |
| Pajak (semua kendaraan) | Tanggal jatuh tempo pajak 1 tahun, tanggal jatuh tempo pajak 5 tahun | Wajib |
| Khusus logistik | KIR (nomor) dan tanggal jatuh tempo KIR | Wajib |
| Khusus logistik | Dimensi, maksimum kubikasi, maksimum tonase | Wajib |
| Khusus logistik | Kode ban | Wajib |

Tanggal jatuh tempo memicu **notifikasi bertahap** sebelum kedaluwarsa. Usulan aturan: kendaraan dengan KIR atau pajak kedaluwarsa tidak dapat dijadwalkan untuk pengiriman tanpa approval. **\[Validasi\]** jadwal notifikasi dan aturan pemblokiran.

### 4.3 Karyawan

- **Semua karyawan**: nomor HP, nomor HP keluarga atau kontak darurat (nama, hubungan, nomor), dan **cost center**, semuanya wajib.
- **App role** (field tambahan, terpisah dari jabatan dan divisi): menentukan tab yang tampil di aplikasi mobile (§5.3). HRIS tampil untuk semua role. **[Validasi]** satu atau beberapa role per karyawan (mis. canvasser menjual sekaligus mengantar).
- **Salesman dan driver**: wajib SIM, yaitu foto SIM, tipe SIM, nomor SIM, dan masa berlaku. Notifikasi sebelum masa berlaku habis; usulan aturan: driver dengan SIM kedaluwarsa atau tipe SIM tidak sesuai kendaraan tidak dapat ditugaskan.
- Data kepegawaian lain (arsip, absensi, cuti, payroll) dikelola di HRIS (bagian 5).

### 4.4 Ringkasan Master Data

| Domain | Atribut kunci |
| --- | --- |
| **Principal** | Kode, PKS, masa berlaku, target dan KPI, aturan pelaporan |
| **Produk** | Principal, kategori, brand, sub-brand, SKU, UoM dan kemasan, dimensi/volume/berat, shelf life |
| **Customer / outlet** | Identitas legal, PIC, channel, tipe area, tier harga, TOP, limit kredit, alamat presisi dan geotag, alamat tambahan, hari kunjungan, salesman |
| **Vendor** | Identitas legal, PIC, status PKP, alamat presisi, rekening, limit, TOP |
| **Area / coverage** | Hierarki wilayah, kategori (dalam/luar kota, urban/rural), hak distribusi per principal |
| **Harga dan diskon** | Pricelist per kombinasi principal/channel/area/tier, kolom diskon (1 sampai 5 baris item, 1 sampai 2 footer), rules, batas approval |
| **Salesman dan PJP** | Tim, channel, area, jadwal outlet harian, rute |
| **Karyawan** | Kontak dan kontak darurat, cost center, app role, SIM (salesman dan driver), data HRIS |
| **Gudang** | Gudang, zona, rak, lokasi, lokasi transit dan canvass |
| **Armada** | Identitas, pajak, KIR, dimensi, kubikasi, tonase, kode ban, driver dan helper |
| **Keuangan** | Chart of accounts, jurnal kas/bank, akun perantara uang di jalan, jenis biaya (3.3), kebijakan pajak |
| **Dimensi analitik** | Produk, customer, channel, area, departemen, cost center, salesman, kendaraan, gudang |

## 5. Arsitektur Sistem: Lima Stack

| Stack | Peran | Pengguna utama |
| --- | --- | --- |
| **1. ERP / DMS** | Rumah sistem: master data, sales, inventory, purchasing, finance/accounting, laporan | Sales admin, finance, manajemen |
| **2. Sales Ordering App (mobile)** | PJP, kunjungan, order, canvassing, penagihan | Salesman, supervisor |
| **3. Delivery / Logistics App** | Eksekusi pengiriman, bukti serah terima, penerimaan uang | Driver, helper, admin logistik |
| **4. WMS** | Optimasi gudang, batch/ED, slotting, insight lanjutan | Kepala gudang, admin gudang |
| **5. HRIS** | Arsip karyawan digital, absensi mobile (geotag + face recognition), cuti, payroll, payslip, PPh 21 dan bukti potong, notifikasi perusahaan | HR, karyawan, atasan, finance, manajemen |

**Persyaratan lintas aplikasi (sales dan logistik):**

- Validasi lokasi presisi terhadap geotag outlet yang terdaftar (order dan pengiriman hanya sah bila dilakukan di lokasi).
- Foto bertimestamp untuk serah terima uang, barang, dan faktur, dengan ketentuan teknis foto yang dapat dikonfigurasi.
- Visibilitas **Stock on Delivery** dan **Money in Transit**.

**Persyaratan UX untuk DMS:** admin distributor terbiasa dengan aplikasi sederhana yang dioperasikan cepat via keyboard (tab, panah). Form web ERP yang panjang menghambat input order berintensitas tinggi. Perlu layar input order khusus yang ringkas, cepat, dan mendukung keyboard-first, meski sumber order dominan datang lewat sinkronisasi API dari aplikasi mobile.

### 5.1 Persyaratan HRIS (Stack 5)

HRIS mengelola data dan siklus kerja karyawan, dan terhubung ke ERP/DMS untuk penugasan, kehadiran, dan biaya.

| Area | Kebutuhan |
| --- | --- |
| Data dan arsip karyawan | Manajemen data karyawan dan arsip hasil scan (identitas, kontrak, SIM, dokumen lain) dengan akses berbasis peran |
| Absensi | Absensi lewat mobile dengan **geotagging** dan **face recognition**, jadwal/shift, dan monitoring kehadiran langsung di ERP/DMS |
| Payroll | Odoo menyiapkan data dan rincian payroll (komponen gaji, tunjangan, lembur, potongan), menghasilkan file payroll, dan memposting jurnal setelah disetujui owner; transfer dana tidak dikelola langsung. Termasuk **payslip** digital |
| Pajak karyawan | PPh 21 dan **bukti potong** (terhubung ke ketentuan Coretax, bagian 3.5) |
| Cuti | Pengajuan, approval berjenjang, saldo dan kalender cuti |
| Notifikasi perusahaan | Pengumuman, pengingat (SIM dan dokumen kedaluwarsa), pemberitahuan approval |

Keterkaitan dengan stack lain: cost center karyawan menjadi dimensi analitik; data kehadiran dipakai untuk penugasan PJP dan pengiriman; masa berlaku SIM memengaruhi penugasan driver.

Data identitas, kontak darurat, dan biometrik (wajah) adalah data pribadi. Perlu persetujuan karyawan, pembatasan akses, dan aturan retensi sesuai UU Pelindungan Data Pribadi. **\[Validasi\]** kebijakan retensi, kepatuhan BPJS, dan apakah face recognition memakai komponen Odoo, aplikasi mobile terpisah, atau penyedia pihak ketiga.

### 5.2 Mode Operasional Odoo: Primary atau Secondary

Odoo dapat berperan sebagai sistem utama atau sistem sekunder. Mode dipilih per distributor saat discovery dan menentukan dari mana data operasional berasal serta di mana kontrol dijalankan.

| Mode | Peran Odoo | Konsekuensi |
| --- | --- | --- |
| **Primary** | Sistem operasional utama. Transaksi dibuat dan diproses di Odoo, dan aturan di bagian 2 dan 3 berjalan sebagai *business as usual*. | Kontrol kredit, diskon, dan approval aktif penuh di Odoo |
| **Secondary** | Odoo menerima **feeding data operasional** dari sistem lain (DMS atau ERP yang sudah ada) untuk akuntansi, rekonsiliasi, pelaporan, dan analitik. | Kontrol operasional tetap di sistem sumber; di Odoo aturan kredit dan approval bersifat informatif kecuali dikonfigurasi lain |

**Data yang disuplai pada mode secondary:** sales order, stok (saldo per gudang, lot, dan ED), invoice, dan update AR (pembayaran, pelunasan, saldo piutang). **Master data** (customer, produk, harga) disinkronkan secara **incremental** mengikuti **SOP manual perusahaan**: setiap ada master baru, perubahan master lama, atau penonaktifan master lama, Odoo **wajib** ikut diperbarui. Transaksi yang merujuk master yang belum tersinkron ditolak validasi sampai master diperbarui. Penerbitan faktur pajak dari Odoo pada mode secondary menjadi **opsi** yang diaktifkan lewat konfigurasi; bila nonaktif, status faktur pajak diterima dari sistem sumber.

**Asal dokumen dan arah sinkronisasi (keputusan 2026-10-23):** pada mode secondary, dokumen yang berasal dari legacy DMS masuk lewat integrasi dan kontrolnya bersifat informatif. Dokumen yang dibuat di Odoo atau di aplikasi mobile berasal dari Odoo dan menjalankan kontrol penuh (kredit, diskon, approval). Setiap dokumen membawa penanda sistem asal dan kunci unik agar tidak terduplikasi. Arah Odoo → legacy DMS dilakukan **manual lewat ekspor data** (template ekspor bernomor versi) disertai laporan rekonsiliasi. **[Validasi]** kebijakan kontrol untuk dokumen asal Odoo pada tiap distributor.

**Tiga metode integrasi** yang harus tersedia:

1. **Import CSV/XLSX**: manual atau terjadwal, memakai template standar.
2. **API sync**: tarik atau dorong data, terjadwal maupun berbasis kejadian.
3. **Listener tambahan (aplikasi desktop)**: agen lokal di komputer atau server distributor yang membaca sumber data (database, file, atau folder) lalu mengirimkannya ke Odoo, untuk sistem lama yang tidak punya API.

#### Modul Integrasi Data

Penanganan mode secondary dibuat sebagai modul tersendiri dengan konfigurasi lengkap.

| Kemampuan | Isi |
| --- | --- |
| Konfigurasi mode | Primary atau secondary per perusahaan atau cabang |
| Konfigurasi sumber | Per jenis data (SO, stok, invoice, AR): metode, jadwal, pemetaan kolom, dan kunci unik agar pengiriman ulang tidak menggandakan data |
| Validasi sebelum posting | Kelengkapan kolom, kecocokan kode customer dan SKU dengan master, deteksi duplikat, total yang tidak seimbang |
| Log dan monitoring | Status tiap batch, error per baris, kirim ulang, proses ulang, audit trail |
| Rekonsiliasi | Perbandingan stok dan saldo AR di Odoo dengan sistem sumber, selisih ditandai |
| Perubahan data | Penanganan faktur dibatalkan, retur, dan koreksi dari sistem sumber |
| Hak akses | Pembatasan siapa yang boleh mengimpor, memproses ulang, dan mengubah konfigurasi |
| Sinkronisasi master data | Incremental: hanya perubahan dan penambahan sejak sinkronisasi terakhir, dipicu mengikuti SOP manual perusahaan (master baru, perubahan master lama, penonaktifan), dengan penanda waktu perubahan dan status aktif |
| Faktur pajak | Penerbitan dari Odoo pada mode secondary bersifat opsi (aktif atau nonaktif), terhubung ke alur Coretax di bagian 3.5 |
| Ekspor ke legacy DMS | Ekspor manual dari Odoo (XLSX/CSV, template bernomor versi per jenis data), menandai dokumen yang sudah diekspor, laporan selisih terhadap legacy |

#### Template Import dan Panduan Pengisian

Setiap jenis data wajib punya template yang bisa diunduh dari modul, disertai **panduan pengisian**. Template berformat XLSX dan CSV, diberi nomor versi, dan terdiri dari tiga bagian: lembar panduan, lembar contoh terisi, dan lembar kosong.

Panduan memuat per kolom: nama kolom, wajib atau opsional, tipe dan format data, contoh isian, nilai yang diizinkan, dan aturan validasinya.

| Template | Kolom pokok (usulan) |
| --- | --- |
| Sales order | Nomor SO, tanggal, kode customer, salesman, kode SKU, jumlah dan UoM, harga, diskon line (1 sampai 5), diskon footer, TOP, gudang |
| Stok | Tanggal snapshot, gudang, kode SKU, lot/batch, ED, jumlah dan UoM |
| Invoice | Nomor invoice, tanggal, jatuh tempo, kode customer, referensi SO/DO, rincian item, DPP, PPN, total, status faktur pajak (bila ada) |
| Update AR | Nomor invoice, tanggal bayar, jumlah, metode bayar, referensi setoran, sisa piutang |
| Master data (sinkronisasi incremental) | Customer, produk, harga sesuai bagian 4.4, ditambah penanda waktu perubahan dan status aktif |

### 5.3 Aplikasi Mobile Terpadu, App Role, dan Bahasa

- **Satu aplikasi** (tahap demo: PWA; setelah proyek disetujui: aplikasi native Android) menggabungkan tiga stack lapangan: HRIS, Sales Ordering, dan Logistic Delivery. Menu/tab **dinamis**, dibentuk dari data di Odoo.
- **App role** adalah field tambahan pada karyawan, terpisah dari jabatan dan divisi. HRIS (absensi, cuti, payslip) tampil untuk **semua role**; Sales Ordering untuk role salesman; Logistic Delivery untuk role logistic. Daftar tab per role dikonfigurasi di Odoo. Hak akses ditegakkan di server, bukan hanya di antarmuka.
- **Semua data aplikasi mobile selalu disinkronkan ke Odoo** sebagai stack utama, termasuk pada distributor yang memakai legacy DMS. Sinkronisasi ke legacy DMS dilakukan manual lewat ekspor (§5.2).
- **Offline:** antrean sinkron di perangkat; harga, diskon, dan kredit dihitung ulang server saat sinkron, dengan status diterima, butuh approval, atau ditolak.
- **Absensi:** foto dan validasi geotag; face recognition pada fase lanjutan.
- **Bahasa:** antarmuka Indonesia penuh dengan terjemahan English. Istilah umum FMCG dipertahankan apa adanya (mis. Principal, Outlet, SKU, PJP, Canvassing, Sales Order, Delivery Order, FEFO, Stock on Delivery, Money in Transit). Daftar istilah dikelola di glosarium terpisah.

## 6. Jembatan ke Implementasi: Pemetaan Awal ke Odoo

Bagian ini hanya memetakan kebutuhan bisnis di atas ke kemampuan Odoo sebagai bahan masuk ke dokumen implementasi. Detail fit-gap, desain, dan eksekusi dibahas di playbook implementasi terpisah.

**\[Validasi\]** Kemampuan tepat bergantung pada versi Odoo (Community vs Enterprise) dan edisi lokalisasi Indonesia. Tabel berikut adalah hipotesis awal untuk diuji pada discovery.

| Kebutuhan | Pendekatan di Odoo | Perkiraan fit |
| --- | --- | --- |
| Master customer, channel, area, tier | Contacts + tag/kategori + field kustom (channel, area, geotag, tier) | Konfigurasi + sedikit kustomisasi |
| Partner: identitas legal, PIC, alamat presisi, alamat gudang dengan PIC | Contacts dengan child contacts (alamat pengiriman) + field kustom + master wilayah provinsi sampai desa | Konfigurasi + kustomisasi |
| Hierarki produk principal/brand/sub-brand | Product categories + atribut/field kustom, analytic account/tag per principal | Konfigurasi |
| Harga bertingkat (principal × channel × area × tier) | Pricelists + rules; kombinasi kompleks perlu logika tambahan | Konfigurasi + kustomisasi |
| Diskon bertingkat: line 1 sampai 5 kolom, footer 1 sampai 2 baris, by config dan by rules | Discount per line standar hanya satu kolom; kolom berlapis dan rules engine perlu pengembangan | Kustomisasi |
| Approval workflow (sales ordering, diskon, double invoice, pemajuan tagihan, biaya operasional) | Modul approval kustom dengan matriks nominal dan peran. *Terverifikasi 2026-10-23:* `approvals` (Enterprise) tidak ada di CE 19 dan `base_tier_validation` belum ada di OCA 19.0 | Kustomisasi |
| Analytical accounting multi-dimensi | Analytic plans dan accounts (produk, customer, channel, departemen, cost center, dst.) dengan pengisian otomatis | Konfigurasi + sedikit kustomisasi |
| Biaya operasional logistik dan gudang | Vendor bills / expenses + akun biaya + analytic + approval | Konfigurasi |
| Multi-gudang, lokasi, kendaraan canvass sebagai lokasi stok | Inventory: warehouses, locations, routes | Standar |
| Lot/batch dan ED, FEFO | Lots/serial numbers + expiration dates + removal strategy FEFO. *Terverifikasi 2026-10-23:* `product_expiry` ada di CE 19 | Standar |
| Putaway, zoning, slotting | Putaway rules, storage categories | Standar (dasar) |
| Picking batch / wave | Batch transfers. *Terverifikasi 2026-10-23:* `stock_picking_batch` ada di CE 19; wave transfer belum diperiksa **[Validasi]** | Standar |
| Picking list → DO → invoice | Sales order → delivery order → invoice | Standar |
| Kendaraan: identitas, pajak 1 dan 5 tahun, KIR, dimensi, kubikasi, tonase, kode ban | Fleet + field kustom + pengingat jatuh tempo | Konfigurasi + kustomisasi |
| Routing pengiriman dan utilisasi armada | Kapasitas kendaraan di Fleet; optimasi rute lewat aplikasi/integrasi eksternal | Kustomisasi + integrasi |
| Stock on Delivery | Lokasi transit / status pengiriman + laporan | Konfigurasi + laporan |
| Money in Transit, setoran dan rekonsiliasi kas | Payment/journal khusus (akun perantara), alur setoran kustom | Kustomisasi |
| AR, aging, limit kredit, penagihan sesuai PJP | Accounting + credit limit + laporan dan view jadwal tagih kustom | Konfigurasi + kustomisasi |
| Faktur pajak lewat Coretax (XML, H2H atau portal, status write-back) | Lokalisasi Indonesia sebagai dasar; konektor Coretax kustom atau PJAP | Integrasi (periksa versi) |
| Input order cepat (keyboard-first) | Layar custom / view ringkas; atau input via integrasi aplikasi mobile | Kustomisasi UX |
| Mobile sales app dan delivery app | Gunakan aplikasi khusus (build/beli) terintegrasi API | Integrasi |
| WMS lanjutan (3D layout, slow/fast moving, bad stock, alert procurement) | Odoo Inventory sebagai inti; fitur lanjutan lewat reporting kustom atau WMS eksternal | Integrasi / fase lanjutan |
| Karyawan: kontak darurat, cost center, SIM (foto, tipe, nomor, masa berlaku) | Employees + field kustom + pengingat masa berlaku | Konfigurasi + kustomisasi |
| HRIS: arsip digital dan scan | Employees + modul dokumen | Konfigurasi (periksa edisi) |
| HRIS: absensi mobile, geotag, foto, face recognition, monitoring di ERP/DMS | Attendance sebagai dasar (CE 19 menyimpan koordinat masuk/keluar, tanpa foto). Foto dan validasi geofence kustom di aplikasi mobile; face recognition fase lanjutan | Kustomisasi + integrasi |
| HRIS: cuti dan approval | Time Off + approval | Standar |
| HRIS: payroll, payslip, PPh 21, bukti potong | Payroll Enterprise tidak ada di CE. Mesin OCA `payroll` (19.0) sebagai dasar; aturan Indonesia (PPh 21, BPJS) dan posting jurnal setelah approval owner kustom; tanpa transfer langsung; e-Bupot fase lanjutan | Kustomisasi + integrasi |
| HRIS: notifikasi perusahaan | Notifikasi bawaan, email, atau push lewat aplikasi mobile | Konfigurasi |
| Pelaporan per principal | Dashboard/BI per principal | Konfigurasi + BI |
| Kebijakan kredit: limit dan TOP wajib, empat mode (strict, limit, limit + jatuh tempo, override approval) | Credit limit + konfigurasi kebijakan per distributor/principal/channel/customer + workflow approval | Konfigurasi + kustomisasi |
| Mode primary/secondary dan modul integrasi data (import CSV/XLSX, API sync, listener desktop, template dan panduan) | Fitur import bawaan terbatas untuk alur ini; perlu modul kustom dengan konfigurasi sumber, validasi, log, dan rekonsiliasi, serta aplikasi listener terpisah | Kustomisasi + integrasi |

| Aplikasi mobile terpadu (HRIS, Sales Ordering, Logistic Delivery; tab dinamis menurut app role) | PWA (Preact + Vite) berbicara ke API di Odoo; native Android setelah proyek disetujui. Odoo web untuk peran back-office | Integrasi |

**Prinsip keputusan:** gunakan standar Odoo sebisa mungkin; kustomisasi hanya untuk yang menjadi pembeda operasional (harga bertingkat, kontrol uang/stok di jalan, UX input order); aplikasi lapangan dan WMS lanjutan diperlakukan sebagai komponen terintegrasi, bukan dipaksakan masuk Odoo inti.

## 7. Kerangka Fase Implementasi (Acuan Awal)

Kerangka berikut hanya acuan awal agar kebutuhan bisnis di dokumen ini terbawa ke tiap fase. Rencana proyek rinci disusun di playbook implementasi terpisah.

### Fase 0 — Discovery dan Framing (2–4 minggu)

- Workshop per fungsi: sales, sales admin, gudang, logistik, finance/kasir, manajemen.
- Dokumentasikan **SOP as-is** dan identifikasi variasi dari common practice.
- Kumpulkan: daftar principal dan PKS, struktur brand, area dan channel, tipe armada, gudang, dokumen yang dipakai, laporan wajib.
- Keluaran: process map as-is/to-be, fit-gap final, daftar integrasi, estimasi scope.

- Inventarisasi kebutuhan lanjutan: struktur diskon (kolom dan rules), matriks approval, daftar jenis biaya, dimensi analitik, status PKP dan jalur Coretax, serta lingkup HRIS.

### Fase 1 — Desain Solusi

- Rancang struktur master data (lihat bagian 4) dan matriks harga/diskon.
- Rancang arsitektur integrasi antara ERP, sales app, delivery app, dan WMS (alur data, frekuensi sinkronisasi, penanganan konflik).
- Rancang kebijakan kontrol (approval, pending faktur, tolerance selisih).
- Keluaran: dokumen desain solusi dan persetujuan klien.

- Rancang struktur diskon, matriks approval, plan analitik, jalur integrasi Coretax, dan integrasi HRIS (absensi, payroll, cost center).

### Fase 2 — Konfigurasi dan Pengembangan

- Bangun core ERP: sales, inventory, purchase, accounting.
- Kembangkan kustomisasi prioritas dan layar input order.
- Bangun/konfigurasi integrasi API.
- Siapkan laporan per principal dan dashboard manajemen.

- Bangun modul HRIS (data dan arsip, absensi, cuti, payroll) dan konektor faktur pajak Coretax.

### Fase 3 — Migrasi Data

- Bersihkan dan standarkan data customer (termasuk geotag), produk, harga, saldo AR, saldo stok per lot/ED.
- Lakukan trial migration minimal dua kali sebelum cut-over.
- Stock opname menjelang go-live sebagai dasar saldo awal.

- Lengkapi data partner (identitas legal, PIC, alamat presisi, geotag), data kendaraan, dan data karyawan beserta arsipnya sebelum migrasi.

### Fase 4 — Pengujian

- **SIT**: uji alur end-to-end: order → SO → picking → DO → invoice → pengiriman → pembayaran → closing.
- **UAT** dengan skenario nyata per peran, termasuk skenario negatif: stok kurang, faktur tertolak, transfer tidak valid, faktur pending, retur.
- Uji beban input order jam sibuk.

- Uji skenario diskon berlapis, approval, penerbitan dan penolakan faktur di Coretax, absensi geotag dan face recognition, serta satu siklus payroll penuh.

### Fase 5 — Pelatihan dan Go-Live

- Pelatihan per peran. Sales admin dan kepala gudang adalah kelompok paling kritis.
- Pertimbangkan go-live bertahap: per gudang, per principal, atau per area, agar risiko terkendali. Untuk satu-dua minggu pertama jalankan hypercare dengan tim siaga.
- Siapkan rencana fallback untuk hari-hari awal.

- Pelatihan karyawan untuk absensi mobile, pengajuan cuti, dan payslip; pelatihan HR untuk payroll dan bukti potong.

### Fase 6 — Stabilisasi dan Optimasi

- Tinjau KPI: akurasi stok, lead time order-to-delivery, rasio faktur tertolak, DSO, utilisasi armada, produktivitas salesman.
- Prioritaskan fase lanjutan: WMS advance, optimasi rute, analitik.

## 8. Kontrol, Audit Trail, dan KPI

**Kontrol wajib:** geovalidasi order dan pengiriman; foto bertimestamp; approval diskon dan SO di luar kebijakan; konfirmasi bukti transfer sebelum validasi; rekonsiliasi harian barang dan uang; batas pending faktur.

**KPI yang disarankan:**

- *Sales*: sell-in/sell-out per principal, active outlet, effective call, produktivitas salesman.
- *Gudang*: akurasi stok, fill rate, % barang mendekati ED, bad stock.
- *Logistik*: on-time delivery, rasio faktur tertolak, utilisasi kubikasi/tonase, biaya per drop.
- *Finance*: DSO, aging AR, collection rate, selisih setoran.

- *SDM*: tingkat kehadiran, keterlambatan, sisa cuti, jumlah SIM dan dokumen mendekati kedaluwarsa.
- *Biaya*: biaya per drop, BBM per kilometer per kendaraan, biaya operasional per principal dan channel.

## 9. Risiko Proyek dan Mitigasi

| Risiko | Mitigasi |
| --- | --- |
| Resistensi pengguna karena UX form ERP dirasa lambat | Layar input order khusus, pelatihan, melibatkan sales admin sejak desain |
| SOP tiap distributor berbeda sehingga scope melebar | Template playbook dengan parameter kebijakan; batasi kustomisasi ke yang disepakati |
| Kualitas data awal buruk (geotag, harga, stok) | Fase migrasi dengan cleansing, dan opname sebelum go-live |
| Integrasi dengan aplikasi mobile tidak stabil (koneksi lapangan) | Desain offline-first, antrean sinkronisasi, penanganan konflik |
| Over-customization Odoo menyulitkan upgrade | Gunakan standar dulu, modul kustom terisolasi, dokumentasi dan pengujian regresi |
| Fraud lapangan tetap terjadi | Kontrol lokasi/foto, rekonsiliasi harian, batas pending, audit trail |
| Faktur ditolak Coretax karena data partner tidak lengkap | Validasi NPWP, nama, dan alamat di master partner; antrean kirim ulang dan penanganan status |
| Struktur diskon dan approval terlalu kompleks sejak awal | Mulai dari aturan inti, uji skenario nyata, tambah rules bertahap |
| Data pribadi dan biometrik karyawan bocor atau disalahgunakan | Persetujuan karyawan, akses berbasis peran, enkripsi, aturan retensi |

## 10. Pertanyaan Terbuka untuk Pembahasan Berikutnya

1. Versi dan edisi Odoo yang dituju (Community/Enterprise, cloud/on-premise)?
2. Aplikasi sales dan delivery: dibangun sendiri, dibeli, atau sudah ada? *Terjawab (2026-10-23): dibangun sendiri, PWA untuk demo, native Android setelah proyek disetujui.*
3. WMS: modul Odoo saja pada fase awal, atau langsung produk WMS terpisah?
4. Seberapa kompleks matriks harga dan diskon dari principal yang harus ditangani sistem?
5. Apakah distributor target adalah single-principal, multi-principal, atau keduanya?
6. Kebutuhan pelaporan ke principal (format, frekuensi, integrasi data)?
7. Kebijakan faktur pending dan tertolak yang menjadi default?
8. Kebutuhan akuntansi spesifik: konsolidasi antar gudang/cabang dan chart of accounts standar?
9. Ambang dan jalur approval untuk kebijakan kredit (piutang baru), termasuk "double invoice" dan "pemajuan tagihan"?
10. Diskon: apakah default berantai dan footer discount sebelum PPN sudah sesuai untuk klien?
11. Status PKP klien dan jalur Coretax yang dipakai (portal, penyedia PJAP, atau H2H)?
12. Daftar jenis biaya usulan (bagian 3.3) sudah sesuai, dan apakah klien punya kode akun biaya yang harus dipertahankan?
13. Payroll: format file payroll yang dibutuhkan (bank atau aplikasi payroll) dan ketentuan BPJS?
14. Face recognition: komponen Odoo, aplikasi mobile terpisah, atau penyedia pihak ketiga? *Ditunda ke fase lanjutan; demo memakai foto + geotag.*
15. Sumber master wilayah (provinsi sampai desa/kelurahan) yang dipakai?
16. App role: satu atau beberapa per karyawan? (mis. canvasser menjual dan mengantar sendiri)
17. Format ekspor ke legacy DMS per distributor (kolom, frekuensi, siapa yang mengunggah)?
18. Untuk distributor mode secondary: apakah dokumen yang berasal dari Odoo/aplikasi mobile menjalankan kontrol kredit dan approval penuh, atau sebagian?

## 11. Langkah Berikutnya yang Disarankan

1. Validasi dokumen ini dengan satu distributor pilot.
2. Perdalam bagian accounting dan finance (COA, AR, kas, pajak) sesuai praktik di Indonesia.
3. Susun detail fit-gap per modul beserta estimasi usaha.
4. Rancang spesifikasi integrasi aplikasi sales, delivery, dan WMS.
