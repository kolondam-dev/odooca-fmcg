"""Disposable ci_db only: meaningful, synthetic native dashboard screenshot data."""
from datetime import datetime, timedelta
from odoo import fields

if env.cr.dbname != 'ci_db':  # noqa: F821
    raise RuntimeError('Dashboard visual fixtures are restricted to disposable ci_db')
company = env.company  # noqa: F821
# id_base supplies an IDR pricelist; a blank CI database can still have IDR archived.
# Activate its currency only inside the disposable fixture; preserve company currency.
env.ref('base.IDR').active = True  # noqa: F821
admin = env.ref('base.user_admin')  # noqa: F821
admin.group_ids = [(4, env.ref('sales_team.group_sale_manager').id)]  # noqa: F821
partner = env['res.partner'].create({'name': 'Dashboard QA Outlet', 'user_id': admin.id})  # noqa: F821
principal = env['id.principal'].create({'name': 'Dashboard QA Principal', 'code': 'DQA1'})  # noqa: F821
unsold = env['id.principal'].create({'name': 'QA No Sales', 'code': 'DQAZ'})  # noqa: F821
env['product.product'].create({'name': 'QA Unsold SKU', 'type': 'service', 'principal_id': unsold.id})  # noqa: F821
products = env['product.product']  # noqa: F821
for index in range(3):
    products |= env['product.product'].create({  # noqa: F821
        'name': f'Dashboard QA SKU {index + 1}', 'type': 'service', 'invoice_policy': 'order',
        'list_price': 100000, 'fmcg_category': 'food', 'principal_id': principal.id,
    })
order = env['sale.order'].create({  # noqa: F821
    'partner_id': partner.id, 'user_id': admin.id,
    'pricelist_id': env['product.pricelist'].create({'name': 'QA company currency',  # noqa: F821
        'currency_id': company.currency_id.id}).id,
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
# Distinct authoritative synthetic ledger cost for a positive book-margin visual case.
cost_account = env['account.account'].create({'name': 'QA Direct Cost', 'code': '990301',  # noqa: F821
    'account_type': 'expense_direct_cost', 'company_ids': [(6, 0, [company.id])]})
offset = env['account.account'].create({'name': 'QA Cost Clearing', 'code': '990302',  # noqa: F821
    'account_type': 'asset_current', 'company_ids': [(6, 0, [company.id])]})
journal = env['account.journal'].create({'name': 'QA Book Cost', 'code': 'QBC', 'type': 'general'})  # noqa: F821
env['account.move'].create({'date': fields.Date.today(), 'journal_id': journal.id,  # noqa: F821
    'line_ids': [(0, 0, {'account_id': cost_account.id, 'debit': 100000}),
                 (0, 0, {'account_id': offset.id, 'credit': 100000})]}).action_post()
for dimension, ident in [('salesman', admin.id), ('principal', principal.id)]:
    env['id.sales.segment.target'].create({'name': 'QA SO target', 'dimension': dimension,  # noqa: F821
        f'{dimension}_id': ident, 'date_from': '2026-07-01', 'date_to': '2026-07-31', 'target_amount': 4000000})
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
book = env['id.monetary.book.margin']._for_period(finance['period'])  # noqa: F821
assert book['available'] and book['direct_cost'] == 100000
assert book['margin'] == invoices.amount_untaxed_signed - 100000
# Explicit read-model fixture for the closed-order bridge (not an E2E stock-posting claim).
margin_product = env['product.product'].create({'name': 'QA Margin Stock', 'type': 'consu',  # noqa: F821
    'is_storable': True, 'invoice_policy': 'delivery', 'carton_qty': 1,
    'carton_length_cm': 100, 'carton_width_cm': 100, 'carton_height_cm': 100, 'carton_weight_kg': 5})
env['stock.quant']._update_available_quantity(margin_product, warehouse.lot_stock_id, 5)  # noqa: F821
margin_order = env['sale.order'].create({'partner_id': partner.id,  # noqa: F821
    'pricelist_id': order.pricelist_id.id,
    'order_line': [(0, 0, {'product_id': margin_product.id, 'product_uom_qty': 2,
        'price_unit': 1000, 'tax_ids': [(5, 0, 0)]})]})
margin_order.action_confirm()
margin_order.date_order = datetime(2026, 7, 16, 3, 0)
margin_moves = margin_order.order_line.move_ids
margin_moves.write({'quantity': 2, 'state': 'done'})
margin_invoice = margin_order._create_invoices()
margin_invoice.invoice_date = fields.Date.today()
margin_invoice.action_post()
margin_cost = env['account.move'].create({'date': fields.Date.today(), 'journal_id': journal.id,  # noqa: F821
    'line_ids': [(0, 0, {'account_id': cost_account.id, 'product_id': margin_product.id, 'debit': 1200}),
                 (0, 0, {'account_id': offset.id, 'product_id': margin_product.id, 'credit': 1200})]})
margin_cost.action_post()
margin_moves.account_move_id = margin_cost
bridge = env['id.sales.order.margin']._for_orders([('id', '=', margin_order.id)])  # noqa: F821
assert bridge['covered'] == 1 and bridge['margin'] == 800
history = env['id.ar.history']._snapshot()  # noqa: F821
assert history['available'] and abs(history['cross_scope_allocation']) < .01
assert abs(sum(row['net'] for row in history['buckets']) - history['net']) < .01
warehouse.write({'usable_volume_cbm': 20, 'capacity_basis': 'QA usable storage survey'})
asset_day = env['id.delivery.cohort']._data()['end']  # noqa: F821
assets = env['id.asset.utilization']._data(asset_day, asset_day)  # noqa: F821
warehouse_row = next(w for w in assets['warehouses'] if w['id'] == warehouse.id)
assert warehouse_row['volume'] > 0 and warehouse_row['occupancy'] is not None, warehouse_row
assert assets['trip_count'] == 0 and assets['volume_pct'] is None  # no invented historical trips
# New explicit QA departure event; never retrofit a trip to historical done DOs.
margin_product.write({'carton_qty': 1, 'carton_length_cm': 100, 'carton_width_cm': 100,
    'carton_height_cm': 100, 'carton_weight_kg': 5})
trip_order = env['sale.order'].create({'partner_id': partner.id,  # noqa: F821
    'pricelist_id': order.pricelist_id.id,
    'order_line': [(0, 0, {'product_id': margin_product.id, 'product_uom_qty': 2,
        'price_unit': 1000, 'tax_ids': [(5, 0, 0)]})]})
trip_order.action_confirm()
trip_picking = trip_order.picking_ids
trip_picking.fmcg_vehicle_id = vehicle
trip_picking.move_ids.write({'quantity': 2, 'state': 'assigned', 'picked': True})
asset_trip = env['id.asset.trip'].create({'name': 'QA Explicit Departure', 'vehicle_id': vehicle.id,  # noqa: F821
    'picking_ids': [(6, 0, trip_picking.ids)], 'odometer_start_km': 100})
asset_trip.action_depart()
trip_picking.move_ids.state = 'done'
asset_trip.write({'odometer_end_km': 110, 'fuel_cost': 200, 'cost_basis': 'QA synthetic receipt'})
asset_trip.action_close()
asset_day = env['id.delivery.cohort']._data()['end']  # noqa: F821
assets = env['id.asset.utilization']._data(asset_day, asset_day)  # noqa: F821
assert assets['trip_count'] == 1 and assets['closed_count'] == 1 and assets['km'] == 10
assert assets['cost_per_delivered_dpp'] == 10
env.cr.commit()  # noqa: F821
print('DASHBOARD_VISUAL_FIXTURE=PASS')
