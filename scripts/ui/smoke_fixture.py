"""Disposable CI database only: two long quotations, one populated invoice, and sidebar user."""
import json

from lxml import etree

admin = env.ref('base.user_admin')  # noqa: F821
admin.write({'login': 'admin', 'password': 'ci-ui'})
env['res.users.settings']._find_or_create_for_user(admin).set_res_users_settings(  # noqa: F821
    {'id_ui_shell': 'sidebar'})
partner = env['res.partner'].create({'name': 'UI Smoke Customer'})  # noqa: F821
product = env['product.product'].create(  # noqa: F821
    {
        'name': 'UI Smoke Product',
        'type': 'service',
        'invoice_policy': 'order',
        'list_price': 100,
    }
)
orders = env['sale.order']  # noqa: F821
for i in range(2):
    line_commands = [
        (0, 0, {
            'product_id': product.id,
            'name': f'UI Smoke Line {line_number}',
            'product_uom_qty': line_number + i,
            'price_unit': 100,
        })
        for line_number in range(1, 19)
    ]
    orders |= env['sale.order'].create({  # noqa: F821
        'partner_id': partner.id,
        'user_id': admin.id,
        'order_line': line_commands,
    })
# Create a real draft invoice from a confirmed long order so the invoice scroll test
# exercises account.move/invoice_line_ids, not an empty /new form.
invoice_order = env['sale.order'].create({  # noqa: F821
    'partner_id': partner.id,
    'user_id': admin.id,
    'order_line': [
        (0, 0, {
            'product_id': product.id,
            'name': f'UI Smoke Invoice Line {line_number}',
            'product_uom_qty': line_number,
            'price_unit': 100,
        })
        for line_number in range(1, 19)
    ],
})
invoice_order.action_confirm()
invoices = invoice_order._create_invoices()
if len(invoices) != 1 or len(invoices.invoice_line_ids) < 10:
    raise RuntimeError('UI smoke fixture must create one invoice with at least 10 invoice lines')
# Capture evidence from the installed registry and resolved form architectures.
# This is runtime evidence from the same disposable CI DB used by browser smoke.
audit = {'installed_modules': env['ir.module.module'].search([('state', '=', 'installed')]).mapped('name')}  # noqa: F821
for model_name, view_xmlid, wanted in (
    ('sale.order', 'sale.view_order_form', [
        'note', 'amount_untaxed', 'amount_tax', 'amount_total', 'tax_totals',
        'discount', 'discount_amount', 'footer_discount_1', 'footer_discount_2',
    ]),
    ('account.move', 'account.view_move_form', [
        'narration', 'amount_untaxed', 'amount_tax', 'amount_total', 'tax_totals',
        'discount', 'discount_amount', 'footer_discount_1', 'footer_discount_2',
    ]),
):
    model = env[model_name]  # noqa: F821
    view = env.ref(view_xmlid)  # noqa: F821
    resolved = model.get_view(view_id=view.id, view_type='form')
    root = etree.fromstring(resolved['arch'].encode())
    footer_groups = root.xpath(
        './/group[.//field[@name="tax_totals"] or .//field[@name="note"] or .//field[@name="narration"]]'
    )
    audit[model_name] = {
        'view_xmlid': view_xmlid,
        'view_id': view.id,
        'view_model': view.model,
        'fields_present_in_registry': sorted(set(wanted) & set(model._fields)),
        'resolved_view_field_names': sorted(
            {node.get('name') for node in root.xpath('.//field[@name]') if node.get('name')}
        ),
        'resolved_groups': [
            {'name': node.get('name'), 'class': node.get('class'),
             'field_names': [field.get('name') for field in node.xpath('.//field[@name]')]}
            for node in footer_groups
        ],
    }
print('UI_RUNTIME_AUDIT=' + json.dumps(audit, sort_keys=True))
env.cr.commit()  # noqa: F821
print('UI_FIXTURE=' + json.dumps({'order': orders[0].id, 'invoice': invoices[0].id}))
