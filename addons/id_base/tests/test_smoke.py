from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSmoke(TransactionCase):
    def test_module_installed(self):
        mod = self.env["ir.module.module"].search([("name", "=", "id_base")])
        self.assertEqual(mod.state, "installed")
