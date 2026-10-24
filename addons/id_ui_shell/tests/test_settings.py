# Part of odooca-fmcg. License LGPL-3.
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestShellSettings(TransactionCase):

    def test_default_mode_follows_parameter(self):
        params = self.env['ir.config_parameter'].sudo()
        Settings = self.env['res.users.settings']
        params.set_param('id_ui_shell.default_mode', 'classic')
        self.assertEqual(Settings._id_ui_shell_default(), 'classic')
        params.set_param('id_ui_shell.default_mode', 'sidebar')
        self.assertEqual(Settings._id_ui_shell_default(), 'sidebar')
        params.set_param('id_ui_shell.default_mode', 'nonsense')
        self.assertEqual(Settings._id_ui_shell_default(), 'sidebar')

    def test_user_can_switch_own_mode(self):
        user = self.env['res.users'].create({
            'name': 'Admin Gudang', 'login': 'gudang_test', 'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        settings = self.env['res.users.settings'].with_user(user)._find_or_create_for_user(user)
        settings.set_res_users_settings({'id_ui_shell': 'classic'})
        self.assertEqual(settings.id_ui_shell, 'classic')

    def test_exposed_to_web_client(self):
        """Field tampil di format settings yang dibaca JS (user.settings)."""
        settings = self.env['res.users.settings']._find_or_create_for_user(self.env.user)
        self.assertIn('id_ui_shell', settings._res_users_settings_format())
