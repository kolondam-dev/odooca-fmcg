# Part of odooca-fmcg. License LGPL-3.
from odoo import api, fields, models

SHELL_MODES = [('sidebar', 'Sidebar'), ('classic', 'Classic')]


class ResUsersSettings(models.Model):
    """Preferensi shell per pengguna.

    Satu-satunya jejak DB addon ini. Semua field model ini otomatis tersedia di
    ``user.settings`` pada web client, tanpa endpoint tambahan.
    """
    _inherit = 'res.users.settings'

    id_ui_shell = fields.Selection(
        SHELL_MODES, string="Interface layout", required=True,
        default=lambda self: self._id_ui_shell_default())

    @api.model
    def _id_ui_shell_default(self):
        """Bawaan untuk pengguna baru; ubah lewat parameter sistem
        ``id_ui_shell.default_mode`` (``sidebar`` atau ``classic``)."""
        value = self.env['ir.config_parameter'].sudo().get_param(
            'id_ui_shell.default_mode', 'sidebar')
        return value if value in dict(SHELL_MODES) else 'sidebar'
