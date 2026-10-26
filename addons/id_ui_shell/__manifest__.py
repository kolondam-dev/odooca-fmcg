# Part of odooca-fmcg. License LGPL-3.
{
    'name': 'ID UI Shell: Sidebar and Keyboard Navigation',
    'summary': 'Sidebar-based backend shell (side by side with the classic layout, '
               'chosen per user), keyboard navigation, viewport-sized layout',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'author': 'kolondam-dev',
    'license': 'LGPL-3',
    'depends': ['web', 'id_ui'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'id_ui_shell/static/src/shell/id_icons.js',
            'id_ui_shell/static/src/shell/id_shell_service.js',
            'id_ui_shell/static/src/shell/id_sidebar.js',
            'id_ui_shell/static/src/shell/id_sidebar.xml',
            'id_ui_shell/static/src/shell/id_section_panel.js',
            'id_ui_shell/static/src/shell/id_section_panel.xml',
            'id_ui_shell/static/src/shell/id_menu_search.js',
            'id_ui_shell/static/src/shell/id_menu_search.xml',
            'id_ui_shell/static/src/shell/systray_dividers.js',
            'id_ui_shell/static/src/shell/navbar_patch.js',
            'id_ui_shell/static/src/shell/navbar_patch.xml',
            'id_ui_shell/static/src/shell/webclient_patch.js',
            'id_ui_shell/static/src/shell/webclient_patch.xml',
            'id_ui_shell/static/src/shell/user_menu_item.js',
            'id_ui_shell/static/src/shell/id_shell.scss',
        ],
    },
    'installable': True,
    'application': False,
}
