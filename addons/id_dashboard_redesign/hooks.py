"""Restore the D1 action when this optional module is removed."""
def uninstall_hook(env):
    action = env.ref("id_dashboard_sales.action_sales_productivity", raise_if_not_found=False)
    if action and action.tag == "id_dashboard_redesign.d1":
        action.write({"tag": "id_dashboard_sales.sales_productivity", "name": "Sales Productivity"})
