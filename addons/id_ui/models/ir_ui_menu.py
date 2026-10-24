# Part of odooca-fmcg. License LGPL-3.
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

LANG_ID = 'id_ID'

# Urutan menu utama (beranda aplikasi), mengikuti alur kerja harian distributor:
# jual -> gudang -> faktur -> beli -> armada -> SDM -> komunikasi.
# (xmlid, sequence, nama Indonesia atau None bila tidak diubah)
# Nama Indonesia mengikuti GLOSSARY.md; baris bertanda [usulan] belum ada di glosarium.
ROOT_MENUS = [
    ('spreadsheet_dashboard.spreadsheet_dashboard_menu_root', 5, None),
    ('sale.sale_menu_root', 10, 'Penjualan'),
    ('stock.menu_stock_root', 20, 'Gudang & Stok'),            # [usulan]
    ('account.menu_finance', 30, 'Faktur'),
    ('purchase.menu_purchase_root', 40, 'Pembelian'),
    ('fleet.menu_root', 50, 'Armada'),                          # [usulan]
    ('hr.menu_hr_root', 60, 'Karyawan'),
    ('hr_attendance.menu_hr_attendance_root', 70, 'Absensi'),
    ('hr_holidays.menu_hr_holidays_root', 80, 'Cuti'),
    ('mail.menu_root_discuss', 200, 'Diskusi'),                 # [usulan]
]

# Istilah glosarium bagian B (Dwi) pada submenu. Istilah bagian A (Tetap)
# sengaja tidak ada di sini karena tidak diterjemahkan.
SUBMENU_NAMES = [
    ('sale.res_partner_menu', 'Pelanggan'),
    ('account.menu_finance_receivables', 'Pelanggan'),
    ('account.menu_account_customer', 'Pelanggan'),
    ('account.menu_action_move_out_invoice_type', 'Faktur'),
    ('sale.menu_product_pricelist_main', 'Daftar Harga'),
]


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _id_ui_apply_navigation(self):
        """Terapkan urutan menu utama dan nama menu menurut glosarium.

        Aman dijalankan berulang. Menu dari modul yang tidak terpasang dilewati.
        Nama Indonesia hanya ditulis bila ``id_ID`` dan ``en_US`` aktif; nama
        English (sumber) tidak diubah.
        """
        # Syarat: id_ID dan en_US aktif. Jika en_US nonaktif, ORM menimpa nilai
        # sumber (en_US) dengan teks Indonesia.
        lang_active = bool(self.env['res.lang']._lang_get(LANG_ID)
                           and self.env['res.lang']._lang_get('en_US'))
        for xmlid, sequence, name_id in ROOT_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            if menu.sequence != sequence:
                menu.sequence = sequence
            if name_id and lang_active:
                menu.with_context(lang=LANG_ID).name = name_id
        if lang_active:
            for xmlid, name_id in SUBMENU_NAMES:
                menu = self.env.ref(xmlid, raise_if_not_found=False)
                if menu:
                    menu.with_context(lang=LANG_ID).name = name_id
        return True
