# Part of odooca-fmcg. License LGPL-3.
from odoo.tests import TransactionCase, tagged

from ..models.ir_ui_menu import LANG_ID, ROOT_MENUS, SUBMENU_NAMES


@tagged('post_install', '-at_install')
class TestNavigation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_and_install_lang(LANG_ID)
        cls.env['ir.ui.menu']._id_ui_apply_navigation()

    def test_root_menu_order(self):
        """Menu utama yang terpasang berurutan sesuai ROOT_MENUS."""
        sequences = []
        for xmlid, sequence, _name in ROOT_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertEqual(menu.sequence, sequence, xmlid)
                sequences.append(menu.sequence)
        self.assertEqual(sequences, sorted(sequences))
        self.assertGreaterEqual(len(sequences), 5)

    def test_glossary_names_id(self):
        """Nama Indonesia mengikuti glosarium, nama English tetap sumber."""
        sale = self.env.ref('sale.sale_menu_root')
        self.assertEqual(sale.with_context(lang=LANG_ID).name, 'Penjualan')
        self.assertEqual(sale.with_context(lang='en_US').name, 'Sales')
        for xmlid, name_id in SUBMENU_NAMES:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertEqual(menu.with_context(lang=LANG_ID).name, name_id, xmlid)

    def test_idempotent(self):
        before = {x: self.env.ref(x).sequence for x, _s, _n in ROOT_MENUS
                  if self.env.ref(x, raise_if_not_found=False)}
        self.env['ir.ui.menu']._id_ui_apply_navigation()
        after = {x: self.env.ref(x).sequence for x in before}
        self.assertEqual(before, after)

    def test_tetap_terms_not_translated(self):
        """Istilah bagian A glosarium (Tetap) tidak boleh punya terjemahan sendiri."""
        keep = {'Sales Order', 'Delivery Order', 'Picking list', 'Principal', 'Outlet'}
        for _xmlid, _seq, name_id in ROOT_MENUS:
            self.assertNotIn(name_id, keep)
