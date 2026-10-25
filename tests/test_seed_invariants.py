"""Mutation tests: clean fixture passes; each corrupted relationship must fail."""
import csv
import hashlib
import importlib.util
import json
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
                'sku_code', 'lot_number', 'qty_cartons', 'carton_qty', 'unit_price_dpp', 'line_subtotal_dpp'
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
                sku_code='P1', lot_number='L1', qty_cartons='1', carton_qty='10', unit_price_dpp='10',
                line_subtotal_dpp='100')],
            'data/registers/perpetual_invoices.csv': [dict(
                invoice_number='I1', so_number='SO1', do_number='DO1', date_invoice='2026-07-02',
                due_date='2026-07-02', payment_term_days='0', dpp_amount='90', ppn_11_amount='9.90',
                total_invoice_with_ppn='99.90')],
            'data/registers/perpetual_ar_collections.csv': [dict(
                payment_id='PAY1', invoice_number='I1', payment_date='2026-07-02', invoice_dpp='90',
                early_payment_discount='0', net_cash_collected='90')],
            'data/registers/perpetual_ap_payments.csv': [dict(
                ap_payment_id='PAY-AP-1', po_number='PO1', principal_name='Prin1', payment_date='2026-07-22',
                amount_paid_dpp='50')],
            'data/registers/perpetual_opex_payroll.csv': [dict(
                entry_id='OPEX-1', date='2026-07-01', amount='1000')],
            'data/registers/perpetual_daily_stock_cards.csv': [
                dict(date='2026-07-01', is_working_day='True', physical_stock_cartons='3',
                     reserved_stock_cartons='2', quarantine_stock_cartons='0'),
                dict(date='2026-07-02', is_working_day='True', physical_stock_cartons='2',
                     reserved_stock_cartons='0', quarantine_stock_cartons='1'),
                dict(date='2026-07-16', is_working_day='False', physical_stock_cartons='2',
                     reserved_stock_cartons='0', quarantine_stock_cartons='1'),
            ],
            'data/registers/initial_stock_20260701.csv': [dict(
                sku_code='P1', qty_cartons_on_hand='3', carton_qty='10', qty_units_on_hand='30',
                unit_cost_price='5', subtotal_dpp='150', lot_number='L1', expiry_date='2027-01-01')],
            'data/registers/inbound_po_intransit_june_headers.csv': [dict(
                po_number='PO1', principal_name='Prin1', order_date='2026-06-15',
                arrival_maumbi_date='2026-07-03', total_dpp='50')],
            'data/registers/inbound_po_intransit_june_lines.csv': [dict(
                po_number='PO1', sku_code='P1', qty_cartons='1', carton_qty='10', unit_cost_price='5',
                subtotal_dpp='50', lot_number='L2', expiry_date='2028-01-01')],
            'data/registers/perpetual_stock_event_ledger.csv': [
                dict(event_id='EVT-1', date='2026-07-01', sku_code='P1', lot_number='L1',
                     physical_impact='3', reserved_impact='0', quarantine_impact='0'),
                dict(event_id='EVT-2', date='2026-07-01', sku_code='P1', lot_number='L1',
                     physical_impact='0', reserved_impact='2', quarantine_impact='0'),
                dict(event_id='EVT-3', date='2026-07-02', sku_code='P1', lot_number='L1',
                     physical_impact='-1', reserved_impact='-1', quarantine_impact='0'),
                dict(event_id='EVT-4', date='2026-07-02', sku_code='P1', lot_number='L1',
                     physical_impact='0', reserved_impact='-1', quarantine_impact='1'),
            ],
        }
        self.custom_report = None
        p = self.root / 'addons/id_base/data/id_district_data.xml'
        p.parent.mkdir(parents=True)
        p.write_text('''<odoo><record id="district1" model="id.district"><field name="code">D1</field>
</record><record id="village1" model="id.subdistrict"><field name="code">V1</field>
<field name="district_id" ref="district1"/></record></odoo>''')

    def run_gate(self):
        input_hashes = {}
        for name, rows in self.data.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('w', newline='', encoding='utf-8') as f:
                fields = rows[0].keys() if rows else self.headers.get(name, [])
                writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
            # Simpan kanonikal LF hash
            data_bytes = p.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            if name.startswith('data/registers/'):
                input_hashes[Path(name).name] = hashlib.sha256(data_bytes).hexdigest()

        # Generate canonical reconciliation JSON for the fixture
        report_file = self.root / 'data/registers/canonical_financial_reconciliation_july_2026.json'
        if self.custom_report is not None:
            report_data = self.custom_report
        else:
            report_data = {
                'report_title': 'LAPORAN REKONSILIASI KANONIKAL',
                'period': '1 Juli 2026 s/d 31 Juli 2026',
                'input_dataset_sha256': input_hashes,
                'sales_orders_booked_july': {'gross_dpp': '200', 'net_dpp': '180'},
                'period_cutoff_july_invoiced': {'invoiced_dpp': '90'},
                'accounts_payable_reconciliation': {'ap_payments_july_dpp': '50'},
                'inventory_warehouse_reconciliation': {
                    'physical_on_hand_cartons': '2',
                    'quarantine_bad_stock_cartons': '1',
                },
            }
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report_data, indent=2) + '\n', encoding='utf-8')

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
            sku_code='P1', lot_number='L1', qty_cartons='1', carton_qty='10',
            unit_price_dpp='10', line_subtotal_dpp='100')]
        self.assertIn('TX-FK', self.run_gate())

    def test_rejection_invalid_lot(self):
        self.mutate('perpetual_order_rejections', 'lot_number', 'NONEXISTENT', 'RETURN-RECON')

    def test_rejection_date_before_do(self):
        self.mutate('perpetual_order_rejections', 'rejection_date', '2026-06-01', 'EVENT-ORDER')

    def test_rejection_qty_exceeds_line(self):
        self.mutate('perpetual_order_rejections', 'qty_cartons', '99', 'RETURN-RECON')

    def test_rejection_duplicate_id(self):
        row = dict(self.data['data/registers/perpetual_order_rejections.csv'][0])
        self.data['data/registers/perpetual_order_rejections.csv'].append(row)
        self.assertIn('TX-IDENTITY', self.run_gate())

    def test_rejection_non_positive_qty(self):
        self.data['data/registers/perpetual_order_rejections.csv'] = [dict(
            rejection_id='R1', so_number='SO1', do_number='DO1', rejection_date='2026-07-02',
            sku_code='P1', lot_number='L1', qty_cartons='0', carton_qty='10',
            unit_price_dpp='10', line_subtotal_dpp='0')]
        self.assertIn('LINE-MATH', self.run_gate())

    def test_invoice_dpp_mismatch(self):
        self.mutate('perpetual_invoices', 'dpp_amount', '80', 'INVOICE-MATH')

    def test_payment_dpp_mismatch(self):
        self.mutate('perpetual_ar_collections', 'invoice_dpp', '80', 'COLLECTION-MATH')

    def test_payment_before_invoice(self):
        self.mutate('perpetual_ar_collections', 'payment_date', '2026-07-01', 'COLLECTION')

    def test_geo_mapping(self):
        self.mutate('customer_registry_354', 'district_code', 'unknown', 'MASTER-GEO')

    def test_missing_visit(self):
        self.mutate('perpetual_sales_orders', 'salesman', 'other', 'PJP-SO')

    # Mutasi Uji Baru untuk Temuan Supervisor:
    def test_ap_invalid_po(self):
        self.mutate('perpetual_ap_payments', 'po_number', 'PO-NONEXISTENT', 'AP-FK')

    def test_ap_principal_mismatch(self):
        self.mutate('perpetual_ap_payments', 'principal_name', 'Wrong Principal', 'AP-FK')

    def test_ap_overpayment(self):
        self.mutate('perpetual_ap_payments', 'amount_paid_dpp', '999999', 'AP-RECON')

    def test_ap_payment_before_order(self):
        self.mutate('perpetual_ap_payments', 'payment_date', '2026-06-01', 'EVENT-ORDER')

    def test_ledger_negative_physical(self):
        self.mutate('perpetual_stock_event_ledger', 'physical_impact', '-999999', 'LEDGER-REPLAY')

    def test_ledger_reserved_exceeds_physical(self):
        self.data['data/registers/perpetual_stock_event_ledger.csv'][1]['reserved_impact'] = '999'
        self.assertIn('LEDGER-REPLAY', self.run_gate())

    def test_ledger_card_mismatch(self):
        self.data['data/registers/perpetual_daily_stock_cards.csv'][0]['physical_stock_cartons'] = '999'
        self.assertIn('LEDGER-REPLAY', self.run_gate())

    def test_report_hash_mismatch(self):
        self.custom_report = {
            'report_title': 'FAKE',
            'period': '1 Juli 2026 s/d 31 Juli 2026',
            'input_dataset_sha256': {'perpetual_sales_orders.csv': 'badhash0000000000000000000000000000000000'},
            'sales_orders_booked_july': {'gross_dpp': '200', 'net_dpp': '180'},
            'period_cutoff_july_invoiced': {'invoiced_dpp': '90'},
            'accounts_payable_reconciliation': {'ap_payments_july_dpp': '50'},
            'inventory_warehouse_reconciliation': {
                'physical_on_hand_cartons': '2',
                'quarantine_bad_stock_cartons': '1',
            },
        }
        self.assertIn('REPORT-RECON', self.run_gate())

    def test_report_aggregate_mismatch(self):
        self.custom_report = {
            'report_title': 'FAKE',
            'period': '1 Juli 2026 s/d 31 Juli 2026',
            'input_dataset_sha256': {},
            'sales_orders_booked_july': {'gross_dpp': '9999', 'net_dpp': '180'},
            'period_cutoff_july_invoiced': {'invoiced_dpp': '90'},
            'accounts_payable_reconciliation': {'ap_payments_july_dpp': '50'},
            'inventory_warehouse_reconciliation': {
                'physical_on_hand_cartons': '2',
                'quarantine_bad_stock_cartons': '1',
            },
        }
        self.assertIn('REPORT-RECON', self.run_gate())

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
