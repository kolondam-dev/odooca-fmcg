"""Disposable CI database only: two quotations and an explicit sidebar user."""
import json

admin = env.ref('base.user_admin')  # noqa: F821
admin.write({'login': 'admin', 'password': 'ci-ui'})
env['res.users.settings']._find_or_create_for_user(admin).set_res_users_settings(  # noqa: F821
    {'id_ui_shell': 'sidebar'})
partner = env['res.partner'].create({'name': 'UI Smoke Customer'})  # noqa: F821
product = env['product.product'].create({'name': 'UI Smoke Product', 'type': 'service', 'list_price': 100})  # noqa: F821
orders = env['sale.order']  # noqa: F821
for i in range(2):
    orders |= env['sale.order'].create({  # noqa: F821
        'partner_id': partner.id,
        'user_id': admin.id,
        'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': i + 1, 'price_unit': 100})],
    })
env.cr.commit()  # noqa: F821
print('UI_FIXTURE=' + json.dumps({'order': orders[0].id}))
