"""Mutation tests: clean fixture passes; each corrupted relationship must fail."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    'gate', Path(__file__).resolve().parents[1] / 'scripts/ops/verify_seed_invariants.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class SeedGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.headers = {
            'data/registers/perpetual_order_rejections.csv': [
                'rejection_id', 'so_number', 'do_number', 'rejection_date',
                'sku_code', 'qty_cartons', 'carton_qty', 'unit_price_dpp', 'line_subtotal_dpp'
            ]
        }
        self.data = {
            'data/registers/customer_registry_354.csv': [dict(
                ref='C1', district_code='D1', subdistrict_code='V1', cohort_date='2026-07-01',
                payment_term_days='0')],
            'data/seed/partners_354.csv': [dict(ref='C1', district_code='D1', subdistrict_code='V1')],
            'data/seed/products_150.csv': [dict(default_code='P1', carton_qty='10')],
            'data/registers/pjp_july_2026_matrix.csv': [dict(
                customer='C1 - Customer', tanggal='2026-07-01', salesman='S1', frekuensi_call='F1')],
            'data/registers/perpetual_sales_orders.csv': [dict(
                so_number='SO1', customer='C1 - Customer', date_order='2026-07-01', salesman='S1',
                gross_dpp='200', discount_dpp='20', net_dpp='180')],
            'data/registers/perpetual_order_lines.csv': [dict(
                so_number='SO1', sku_code='P1', qty_cartons='2', carton_qty='10',
                unit_price_dpp='10', line_subtotal_dpp='200', lot_number='L1')],
            'data/registers/perpetual_deliveries.csv': [dict(
                do_number='DO1', so_number='SO1', scheduled_delivery_date='2026-07-02',
                gross_order_dpp='200', rejection_dpp='100', do_delivered_dpp='100')],
            'data/registers/perpetual_order_rejections.csv': [dict(
                rejection_id='R1', so_number='SO1', do_number='DO1', rejection_date='2026-07-02',
                sku_code='P1', qty_cartons='1', carton_qty='10', unit_price_dpp='10',
                line_subtotal_dpp='100')],
            'data/registers/perpetual_invoices.csv': [dict(
                invoice_number='I1', so_number='SO1', do_number='DO1', date_invoice='2026-07-02',
                due_date='2026-07-02', payment_term_days='0', dpp_amount='90', ppn_11_amount='9.90',
                total_invoice_with_ppn='99.90')],
            'data/registers/perpetual_ar_collections.csv': [dict(
                payment_id='PAY1', invoice_number='I1', payment_date='2026-07-02', invoice_dpp='90',
                early_payment_discount='0', net_cash_collected='90')],
            'data/registers/perpetual_daily_stock_cards.csv': [
                dict(date='2026-07-01', is_working_day='True'),
                dict(date='2026-07-02', is_working_day='True'),
                dict(date='2026-07-16', is_working_day='False'),
            ],
            'data/registers/initial_stock_20260701.csv': [dict(
                sku_code='P1', qty_cartons_on_hand='3', carton_qty='10', qty_units_on_hand='30',
                unit_cost_price='5', subtotal_dpp='150', lot_number='L1', expiry_date='2027-01-01')],
            'data/registers/inbound_po_intransit_june_headers.csv': [dict(
                po_number='PO1', arrival_maumbi_date='2026-07-03', total_dpp='50')],
            'data/registers/inbound_po_intransit_june_lines.csv': [dict(
                po_number='PO1', sku_code='P1', qty_cartons='1', carton_qty='10', unit_cost_price='5',
                subtotal_dpp='50', lot_number='L2', expiry_date='2028-01-01')],
        }
        p = self.root / 'addons/id_base/data/id_district_data.xml'
        p.parent.mkdir(parents=True)
        p.write_text('''<odoo><record id="district1" model="id.district"><field name="code">D1</field>
</record><record id="village1" model="id.subdistrict"><field name="code">V1</field>
<field name="district_id" ref="district1"/></record></odoo>''')

    def run_gate(self):
        for name, rows in self.data.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('w', newline='') as f:
                fields = rows[0].keys() if rows else self.headers.get(name, [])
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        violations, _ = gate.validate(self.root, sizes=(1, 1))
        return {v['invariant'] for v in violations}

    def mutate(self, filename, field, value, expected):
        self.data['data/registers/' + filename + '.csv'][0][field] = value
        self.assertIn(expected, self.run_gate())

    def test_clean_fixture(self):
        self.assertEqual(self.run_gate(), set())

    def test_future_customer(self):
        self.mutate('customer_registry_354', 'cohort_date', '2026-08-01', 'COHORT-SO')

    def test_future_visit(self):
        self.mutate('customer_registry_354', 'cohort_date', '2026-08-01', 'COHORT-PJP')

    def test_line_amount(self):
        self.mutate('perpetual_order_lines', 'line_subtotal_dpp', '101', 'LINE-MATH')

    def test_header_amount(self):
        self.mutate('perpetual_sales_orders', 'gross_dpp', '101', 'HEADER-MATH')

    def test_unknown_product(self):
        self.mutate('perpetual_order_lines', 'sku_code', 'unknown', 'TX-FK')

    def test_unreceived_lot(self):
        self.mutate('perpetual_order_lines', 'lot_number', 'L2', 'LOT-BALANCE')

    def test_fefo(self):
        self.data['data/registers/inbound_po_intransit_june_headers.csv'][0]['arrival_maumbi_date'] = '2026-07-01'
        self.mutate('perpetual_order_lines', 'lot_number', 'L2', 'LOT-FEFO')

    def test_expired_lot(self):
        self.mutate('initial_stock_20260701', 'expiry_date', '2026-06-30', 'LOT-EXPIRY')

    def test_due_date(self):
        self.mutate('perpetual_invoices', 'due_date', '2026-07-01', 'EVENT-ORDER')

    def test_top_mismatch(self):
        self.mutate('perpetual_invoices', 'payment_term_days', '14', 'MASTER-TOP')

    def test_sunday_delivery(self):
        self.mutate('perpetual_deliveries', 'scheduled_delivery_date', '2026-07-05', 'CALENDAR')

    def test_holiday_delivery(self):
        self.data['data/registers/perpetual_invoices.csv'][0]['date_invoice'] = '2026-07-16'
        self.data['data/registers/perpetual_invoices.csv'][0]['due_date'] = '2026-07-16'
        self.mutate('perpetual_deliveries', 'scheduled_delivery_date', '2026-07-16', 'CALENDAR')

    def test_period_cutoff_mismatch(self):
        self.mutate('perpetual_deliveries', 'scheduled_delivery_date', '2026-07-03', 'PERIOD-CUTOFF')

    def test_rejection_reconciliation(self):
        self.mutate('perpetual_deliveries', 'rejection_dpp', '10', 'RETURN-RECON')

    def test_rejection_fk_invalid(self):
        self.data['data/registers/perpetual_order_rejections.csv'] = [dict(
            rejection_id='R1', so_number='SO999', do_number='DO1', rejection_date='2026-07-02',
            sku_code='P1', qty_cartons='1', carton_qty='10', unit_price_dpp='10', line_subtotal_dpp='100')]
        self.assertIn('TX-FK', self.run_gate())

    def test_rejection_non_positive_qty(self):
        self.data['data/registers/perpetual_order_rejections.csv'] = [dict(
            rejection_id='R1', so_number='SO1', do_number='DO1', rejection_date='2026-07-02',
            sku_code='P1', qty_cartons='0', carton_qty='10', unit_price_dpp='10', line_subtotal_dpp='0')]
        self.assertIn('LINE-MATH', self.run_gate())

    def test_payment_before_invoice(self):
        self.mutate('perpetual_ar_collections', 'payment_date', '2026-07-01', 'COLLECTION')

    def test_geo_mapping(self):
        self.mutate('customer_registry_354', 'district_code', 'unknown', 'MASTER-GEO')

    def test_missing_visit(self):
        self.mutate('perpetual_sales_orders', 'salesman', 'other', 'PJP-SO')

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            gate.number('NaN')

    def test_count(self):
        self.data['data/seed/products_150.csv'].append(dict(default_code='P2', carton_qty='10'))
        self.assertIn('MASTER-COUNT', self.run_gate())

    def test_missing_file(self):
        self.run_gate()
        (self.root / 'data/seed/products_150.csv').unlink()
        with self.assertRaises(FileNotFoundError):
            gate.validate(self.root, sizes=(1, 1))


if __name__ == '__main__':
    unittest.main()
