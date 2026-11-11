"""Restore the D1 action when this optional module is removed."""
def uninstall_hook(env):
    action = env.ref("id_dashboard_sales.action_sales_productivity", raise_if_not_found=False)
    if action and action.tag == "id_dashboard_redesign.d1":
        action.write({"tag": "id_dashboard_sales.sales_productivity", "name": "Sales Productivity"})
    default = env.ref("id_dashboard_redesign.action_dashboard_default", raise_if_not_found=False)
    original = env.ref("spreadsheet_dashboard.ir_actions_dashboard_action", raise_if_not_found=False)
    if default and original:
        for xmlid in ("spreadsheet_dashboard_menu_root", "spreadsheet_dashboard_menu_dashboard"):
            menu = env.ref("spreadsheet_dashboard." + xmlid, raise_if_not_found=False)
            if menu and menu.action == default:
                menu.action = original
