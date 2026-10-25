# Snapshot Odoo - https://odooca-fmcg-demo.up.railway.app (db railway)

## 1. Server

- server: `19.0-20261015` | protokol 1 | url `https://odooca-fmcg-demo.up.railway.app` | db `railway` | login `admin` (uid 2)
- waktu snapshot (lokal): 2026-10-25T10:00:26

## 2. Modul

- status: {'installed': 97, 'uninstalled': 1049, 'uninstallable': 35}
- TERINSTAL (97): account, account_add_gln, account_edi_ubl_cii, account_fleet, account_payment, account_qr_code_sepa, analytic, api_doc, auth_passkey, auth_passkey_portal, auth_signup, auth_totp, auth_totp_mail, auth_totp_portal, barcodes, barcodes_gs1_nomenclature, base, base_geolocalize, base_iban, base_import, base_import_module, base_install_request, base_setup, base_vat, bus, calendar, calendar_sms, contacts, digest, fleet, google_gmail, hr, hr_attendance, hr_calendar, hr_fleet, hr_holidays, hr_holidays_attendance, hr_holidays_homeworking, hr_homeworking, hr_homeworking_calendar, hr_org_chart, hr_skills, html_editor, http_routing, iap, iap_mail, id_base, id_ui, id_ui_form, id_ui_shell, l10n_id, l10n_id_efaktur_coretax, mail, mail_bot, mail_bot_hr, microsoft_outlook, onboarding, partner_autocomplete, payment, phone_validation, portal, privacy_lookup, product, purchase, purchase_edi_ubl_bis3, purchase_product_template_tags, purchase_stock, resource, resource_mail, rpc, sale, sale_edi_ubl, sale_management, sale_pdf_quote_builder, sale_purchase, sale_purchase_stock, sale_sms, sale_stock, sales_team, sms, snailmail, snailmail_account, spreadsheet, spreadsheet_account, spreadsheet_dashboard, spreadsheet_dashboard_account, spreadsheet_dashboard_sale, spreadsheet_dashboard_stock_account, stock, stock_account, stock_sms, uom, utm, web, web_hierarchy, web_tour, web_unsplash
- APLIKASI (tile di app switcher) terinstal: Attendances (hr_attendance); Calendar (calendar); Contacts (contacts); Discuss (mail); Employees (hr); FMCG Distributor Base (id_base); Fleet (fleet); Inventory (stock); Invoicing (account); Purchase (purchase); Sales (sale_management); Skills Management (hr_skills); Time Off (hr_holidays)
- DIHARAPKAN tetapi BELUM terinstal (8): `product_expiry`[uninstalled], `stock_picking_batch`[uninstalled], `mis_builder`[uninstalled], `account_financial_report`[uninstalled], `queue_job`[uninstalled], `fastapi`[uninstalled], `sale_financial_risk`[uninstalled], `account_credit_control`[uninstalled]
- `id_base`: state=installed versi=19.0.1.0.0
- `id_ui`: state=installed versi=19.0.1.0.0
- `id_ui_shell`: state=installed versi=19.0.1.0.0
- `id_ui_form`: state=installed versi=19.0.1.0.0

## 3. Perusahaan, bahasa, parameter

- perusahaan: **My Company** | negara: Indonesia | mata uang: IDR | chart: id | vat: False
- bahasa AKTIF: en_US, id_ID
- bahasa & zona waktu user ini: lang=`en_US` tz=`Asia/Jakarta`
- parameter: web.base.url=https://odooca-fmcg-demo.up.railway.app, web.base.url.freeze=True

## 4. Akuntansi

- akun: 118 | jurnal: 8
- pajak (maks 40):
| nama | persen | jenis | aktif |
|---|---|---|---|
| 12% (Non-Luxury Good) | 11.0 | sale | True |
| 12% (Non-Luxury Good) | 11.0 | purchase | True |
| 12% | 12.0 | sale | True |
| 12% | 12.0 | purchase | True |
| 20% (STLG) | 20.0 | sale | True |
| 12% Pemungut PPN (Non-Luxury Good) | 11.0 | sale | True |
| 12% Pemungut PPN | 12.0 | sale | True |
| 20% Pemungut PPN (STLG) | 20.0 | sale | True |
| 0% | 0.0 | sale | True |
| 0% EXPORT | 0.0 | sale | True |
| 0% EXEMPT | 0.0 | sale | True |
| 0% | 0.0 | purchase | True |
| 0% EXEMPT | 0.0 | purchase | True |
| 20% (STLG) | 20.0 | purchase | True |
| 12% NCR | 0.0 | purchase | True |
| 12% IM | 11.0 | purchase | True |

## 5. Menu

- total menu: 397 | menu tingkat atas (muncul di app switcher): 17
| menu tingkat atas | jumlah anak langsung | ikon | aksi |
|---|---|---|---|
| Dashboards | 2 | ya | ir.actions.client,297 |
| Calendar | 2 | ya |  |
| Sales | 5 | ya |  |
| Contacts | 2 | ya |  |
| Inventory | 5 | ya |  |
| FMCG Distribution | 1 | ya |  |
| Invoicing | 7 | ya |  |
| Purchase | 4 | ya |  |
| Fleet | 3 | ya |  |
| Employees | 7 | ya |  |
| Attendances | 5 | ya |  |
| Time Off | 5 | ya |  |
| Discuss | 4 | ya | ir.actions.client,119 |
| Link Tracker | 1 | ya |  |
| Apps | 4 | ya |  |
| Settings | 6 | ya |  |
| Tests | 0 | ya |  |

### Pohon menu `FMCG Distribution`:
- FMCG Distribution
  - Master Data
    - Principals -> ir.actions.act_window,307
    - Brands -> ir.actions.act_window,308
    - Distribution Channels -> ir.actions.act_window,309
    - Customer Tiers -> ir.actions.act_window,310
    - Coverage Areas -> ir.actions.act_window,311
    - Tipe Armada Operasional -> ir.actions.act_window,312
    - Kabupaten / Kota -> ir.actions.act_window,313
    - Kecamatan -> ir.actions.act_window,314
    - Kelurahan & Kode Pos -> ir.actions.act_window,315

## 6. Jumlah data per model

| model | jumlah |
|---|---|
| res.partner | 356 |
| product.template | 150 |
| product.product | 150 |
| uom.uom | 14 |
| product.category | 3 |
| product.pricelist | 0 |
| id.principal | 4 |
| id.brand | 29 |
| id.sub.brand | 0 |
| id.channel | 4 |
| id.tier | 4 |
| id.coverage.area | 4 |
| id.fleet.type | 9 |
| id.city | 15 |
| id.district | 18 |
| id.subdistrict | 14 |
| hr.employee | 1 |
| hr.department | 1 |
| hr.job | 0 |
| fleet.vehicle | 0 |
| stock.warehouse | 1 |
| stock.location | 6 |
| stock.picking | 0 |
| stock.lot | 0 |
| sale.order | 0 |
| sale.order.line | 0 |
| purchase.order | 0 |
| account.move | 0 |
| account.payment | 0 |
| res.users | 1 |

## 7. Outlet / customer

- outlet/customer (domain `[('ref', '=like', 'CUST-%')]`): **354**
- per channel: Retail: 260, General Trade: 72, Modern Trade: 12, Institusional: 10
- per tier: (kosong): 354
- per kecamatan: Wenang: 83, Malalayang: 75, Mapanget: 74, Airmadidi: 61, Tomohon Tengah: 8, Sario: 8, Tikala: 8, Maesa: 7
- per kota (city): (kosong): 354
- per provinsi: (kosong): 354
- per negara: (kosong): 354

Kelengkapan field pada outlet:
| field | terisi | % |
|---|---|---|
| street | 354/354 | 100% |
| city | 0/354 | 0% |
| state_id | 0/354 | 0% |
| country_id | 0/354 | 0% |
| zip | 354/354 | 100% |
| vat | 94/354 | 27% |
| partner_latitude | 354/354 | 100% |
| partner_longitude | 354/354 | 100% |
| property_payment_term_id | 0/354 | 0% |
| user_id | 0/354 | 0% |
| credit_limit | 354/354 | 100% |
| ref | 354/354 | 100% |
| channel_id | 354/354 | 100% |
| tier_id | 0/354 | 0% |
| coverage_area_id | 0/354 | 0% |
| district_id | 354/354 | 100% |
| subdistrict_id | 354/354 | 100% |
| category_id | 0/354 | 0% |
| pic_name | 0/354 | 0% |

Contoh 3 outlet pertama (VAT disamarkan):
- {"ref": "CUST-MT-01", "name": "Indomaret DC Manado", "street": "Jl. AA Maramis KM 10 Paniki", "city": false, "state_id": false, "country_id": false, "channel_id": "Modern Trade", "tier_id": false, "district_id": "Mapanget", "subdistrict_id": "Paniki Bawah", "credit_limit": 250000000.0, "credit_mode": "strict", "property_payment_term_id": false, "user_id": false, "partner_latitude": 1.528, "partner_longitude": 124.908, "vat": "****************.000"}
- {"ref": "CUST-MT-02", "name": "Alfamidi DC Manado", "street": "Kawasan Pergudangan Kairagi Dua", "city": false, "state_id": false, "country_id": false, "channel_id": "Modern Trade", "tier_id": false, "district_id": "Mapanget", "subdistrict_id": "Paniki Bawah", "credit_limit": 200000000.0, "credit_mode": "strict", "property_payment_term_id": false, "user_id": false, "partner_latitude": 1.519, "partner_longitude": 124.897, "vat": "****************.000"}
- {"ref": "CUST-MT-03", "name": "FreshMart Superstore Bahu Mall", "street": "Bahu Mall Blok A No. 1", "city": false, "state_id": false, "country_id": false, "channel_id": "Modern Trade", "tier_id": false, "district_id": "Malalayang", "subdistrict_id": "Bahu (FreshMart Bahu Mall)", "credit_limit": 120000000.0, "credit_mode": "limit", "property_payment_term_id": false, "user_id": false, "partner_latitude": 1.458, "partner_longitude": 124.825, "vat": "****************.000"}

## 8. Produk

- produk ber-kode: **150** dari 150 template
- per principal: PT Mayora Indah Tbk: 44, PT Unilever Indonesia Tbk: 42, PT Santos Jaya Abadi: 32, Wings Food: 32
- per brand (top): Kapal Api: 16, Mie Sedaap: 12, Kopi ABC: 10, Roma: 10, Torabika: 10, Lifebuoy: 8
- per divisi: food: 70, rtd: 34, personal_care: 20, home_care: 16, confectionery: 10
- per UoM: Units: 150
- per tipe: consu: 150

Kelengkapan field pada produk:
| field | terisi | % |
|---|---|---|
| principal_id | 150/150 | 100% |
| brand_id | 150/150 | 100% |
| sub_brand_id | 0/150 | 0% |
| fmcg_category | 150/150 | 100% |
| inner_qty | 150/150 | 100% |
| carton_qty | 150/150 | 100% |
| barcode | 150/150 | 100% |
| list_price | 150/150 | 100% |
| standard_price | 150/150 | 100% |
| weight | 150/150 | 100% |
| volume | 0/150 | 0% |
| is_storable | 0/150 | 0% |
| uom_po_id | FIELD TIDAK ADA | - |
| taxes_id | 150/150 | 100% |
| categ_id | 0/150 | 0% |
- UoM yang ada: Days, Hours, KWH, L, Minutes, Pack of 6, Ton, Units, g, kg, m, ml, mm, m²
- model kemasan `product.uom`: 0 baris

Contoh 3 produk pertama:
- {"default_code": "MYR-RMA-01", "name": "Roma Kelapa 300g", "principal_id": "PT Mayora Indah Tbk", "brand_id": "Roma", "fmcg_category": "food", "uom_id": "Units", "inner_qty": 1, "carton_qty": 30, "list_price": 8500.0, "categ_id": false, "type": "consu"}
- {"default_code": "MYR-RMA-02", "name": "Roma Marie Susu 115g", "principal_id": "PT Mayora Indah Tbk", "brand_id": "Roma", "fmcg_category": "food", "uom_id": "Units", "inner_qty": 1, "carton_qty": 30, "list_price": 8500.0, "categ_id": false, "type": "consu"}
- {"default_code": "MYR-RMA-03", "name": "Roma Sandwich Cokelat 216g", "principal_id": "PT Mayora Indah Tbk", "brand_id": "Roma", "fmcg_category": "food", "uom_id": "Units", "inner_qty": 1, "carton_qty": 30, "list_price": 8500.0, "categ_id": false, "type": "consu"}

## 9. User

- jumlah user: 1 (internal: 1)
| login | nama | aktif | lang | internal | jml grup |
|---|---|---|---|---|---|
| admin | Administrator | True | en_US | True | 11 |

## 10. HR, armada, gudang

- karyawan: 1 | per departemen: Administration: 1 | per jabatan: (kosong): 1
- kendaraan (fleet.vehicle): 0 | per model: 
- gudang: My Company[WH] | lokasi internal: 1

## 11. Transaksi

- `sale.order`: 0 baris
- `purchase.order`: 0 baris
- `account.move`: 0 baris

## 12. Langkah manual tambahan (tidak dijalankan skrip ini)

- Log boot `[init]` dan seed: `railway logs --service <nama-service> | grep -E "\[init\]|seed|ERROR|Traceback"` (tempel baris yang relevan).
- Penanda init di DB (butuh akses psql): `railway connect Postgres` lalu `select * from id_meta.marks order by at;` dan `select * from id_meta.reset_log;`.
