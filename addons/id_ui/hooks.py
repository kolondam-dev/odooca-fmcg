# Part of odooca-fmcg. License LGPL-3.
import logging

_logger = logging.getLogger(__name__)

LANG_ID = 'id_ID'


def _post_init_hook(env):
    """Aktifkan bahasa Indonesia, jadikan bawaan untuk partner/pengguna baru,
    lalu terapkan urutan menu dan istilah glosarium.

    Dapat dimatikan dengan parameter sistem ``id_ui.set_default_lang`` = ``False``.
    """
    # English harus aktif sebelum menulis terjemahan: bila en_US nonaktif, ORM
    # ikut menimpa nilai sumber (en_US) dengan teks Indonesia.
    env['res.lang']._activate_and_install_lang('en_US')
    lang = env['res.lang']._activate_and_install_lang(LANG_ID)
    if not lang:
        _logger.warning("Bahasa %s tidak ditemukan; lewati pengaturan bahasa.", LANG_ID)
    else:
        param = env['ir.config_parameter'].sudo().get_param('id_ui.set_default_lang', 'True')
        if param not in ('False', '0', ''):
            env['ir.default'].sudo().set('res.partner', 'lang', LANG_ID)
    env['ir.ui.menu']._id_ui_apply_navigation()
