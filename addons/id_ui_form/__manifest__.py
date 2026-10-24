# Part of odooca-fmcg. License LGPL-3.
{
    'name': 'ID UI Form: Chatter as Tab',
    'summary': 'In the sidebar layout the form chatter becomes the last notebook tab '
               'so forms use the full width',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'author': 'kolondam-dev',
    'license': 'LGPL-3',
    'depends': ['web', 'mail', 'id_ui_shell'],
    'assets': {
        'web.assets_backend': [
            'id_ui_form/static/src/form/id_chatter_page.js',
            'id_ui_form/static/src/form/id_chatter_page.xml',
            'id_ui_form/static/src/form/form_patch.js',
            'id_ui_form/static/src/form/id_form.scss',
        ],
    },
    'installable': True,
    'application': False,
}
