"""Disposable ci_db only: meaningful, synthetic native dashboard screenshot data."""
from datetime import datetime, timedelta
from odoo import fields

if env.cr.dbname != 'ci_db':  # noqa: F821
    raise RuntimeError('Dashboard visual fixtures are restricted to disposable ci_db')
company = env.company  # noqa: F821
admin = env.ref('base.user_admin')  # noqa: F821
admin.group_ids = [(4, env.ref('sales_team.group_sale_manager').id)]  # noqa: F821
partner = env['res.partner'].create({'name': 'Dashboard QA Outlet', 'user_id': admin.id})  # noqa: F821
products = env['product.product']  # noqa: F821
for index in range(3):
    products |= env['product.product'].create({  # noqa: F821
        'name': f'Dashboard QA SKU {index + 1}', 'type': 'service', 'invoice_policy': 'order',
        'list_price': 100000, 'fmcg_category': 'food',
    })
order = env['sale.order'].create({  # noqa: F821
    'partner_id': partner.id, 'user_id': admin.id,
    'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': 5, 'price_unit': 100000,
                           'discount': 10}) for p in products],
})
order.action_confirm()
order.date_order = datetime(2026, 7, 15, 3, 0)
invoices = order._create_invoices()
invoices.write({'invoice_date': fields.Date.today(), 'invoice_date_due': fields.Date.today() - timedelta(days=5)})
invoices.action_post()
# Assert actual SQL-backed finance payload, not just a populated-looking screen.
period_start = fields.Date.today().replace(day=1)
period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
env['id.monetary.target'].create({'name': 'Dashboard QA Current Period',  # noqa: F821
    'date_from': period_start, 'date_to': period_end, 'target_revenue': 10000000,
    'company_id': company.id, 'currency_id': company.currency_id.id})
finance = env['id.monetary.dashboard'].get_data(period_key=f'{period_start}/{period_end}')  # noqa: F821
exposure = next(c for c in finance['top_customers'] if c['id'] == partner.id)
assert exposure['overdue_balance'] == invoices.amount_residual_signed > 0
assert finance['kpi']['realized_revenue'] == invoices.amount_untaxed_signed
brand = env['fleet.vehicle.model.brand'].create({'name': 'Dashboard QA'})  # noqa: F821
model = env['fleet.vehicle.model'].create({'name': 'Box QA', 'brand_id': brand.id})  # noqa: F821
vehicle = env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'QA-ONLY',  # noqa: F821
    'capacity_cbm': 12, 'capacity_ton': 3})
env['id.delivery.trip.cost'].create({'vehicle_id': vehicle.id, 'fuel_cost': 200000, 'helper_cost': 50000})  # noqa: F821
warehouse = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)  # noqa: F821
stock_product = env['product.product'].create({'name': 'Dashboard QA Physical Stock',  # noqa: F821
    'type': 'consu', 'is_storable': True, 'tracking': 'lot', 'fmcg_category': 'food', 'standard_price': 10000,
    'carton_qty': 12, 'carton_length_cm': 30, 'carton_width_cm': 20, 'carton_height_cm': 20})
lot = env['stock.lot'].create({'name': 'QA-EXPIRY', 'product_id': stock_product.id,  # noqa: F821
    'company_id': company.id, 'expiration_date': fields.Datetime.now() + timedelta(days=10)})
env['stock.quant']._update_available_quantity(stock_product, warehouse.lot_stock_id, 120, lot_id=lot)  # noqa: F821
picking = env['stock.picking'].create({'picking_type_id': warehouse.out_type_id.id,  # noqa: F821
    'location_id': warehouse.lot_stock_id.id, 'location_dest_id': partner.property_stock_customer.id,
    'partner_id': partner.id, 'fmcg_vehicle_id': vehicle.id, 'fmcg_reject_reason': 'store_closed'})
picking.action_cancel()
env.flush_all()  # noqa: F821
env.cr.commit()  # noqa: F821
print('DASHBOARD_VISUAL_FIXTURE=PASS')
