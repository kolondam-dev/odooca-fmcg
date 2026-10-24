# Part of odooca-fmcg. License LGPL-3.
{
    'name': 'ID UI: Theme, Navigation and Language',
    'summary': 'Backend theme, menu order and interface terms (Indonesian/English) '
               'for FMCG distributors',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'author': 'kolondam-dev',
    'license': 'LGPL-3',
    # Modul yang menunya diatur urutan/namanya (SCOPE: stack inti). Dengan depends,
    # menu mereka sudah ada saat urutan diterapkan, apa pun urutan instal INIT_MODULES.
    'depends': [
        'web',
        'mail',
        'sale_management',
        'stock',
        'purchase',
        'account',
        'hr',
        'fleet',
        'hr_attendance',
        'hr_holidays',
        'spreadsheet_dashboard',
    ],
    'data': [
        'data/navigation_data.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'id_ui/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'id_ui/static/src/scss/backend.scss',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
}
