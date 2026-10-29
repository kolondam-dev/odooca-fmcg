"""Acceptance mutations on a frozen copy of the actual committed dataset.

Fingerprint refresh is intentional: source correctness must survive a normal
report regeneration, rather than detecting corruption only via stale hashes.
"""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('acceptance', ROOT / 'scripts/ops/verify_seed_acceptance.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reg = self.root / 'data/registers'
        self.reg.mkdir(parents=True)
        for name in gate.FILES:
            shutil.copyfile(ROOT / 'data/registers' / (name + '.csv'), self.reg / (name + '.csv'))
        self.report_file = self.reg / 'canonical_financial_reconciliation_july_2026.json'
        shutil.copyfile(ROOT / 'data/registers' / self.report_file.name, self.report_file)
        (self.root / 'data/seed').mkdir()
        shutil.copyfile(ROOT / 'data/seed/products_150.csv', self.root / 'data/seed/products_150.csv')

    def rows(self, name):
        with (self.reg / (name + '.csv')).open(newline='', encoding='utf-8') as stream:
            return list(csv.DictReader(stream))

    def write(self, name, rows):
        with (self.reg / (name + '.csv')).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)

    def check(self, rule=None):
        # Rebind all input hashes, so each test exercises actual invariants.
        report = json.loads(self.report_file.read_text())
        import hashlib
        report['input_dataset_sha256'] = {
            name + '.csv': hashlib.sha256(gate.normalized((self.reg / (name + '.csv')).read_bytes())).hexdigest()
            for name in gate.FILES
        }
        self.report_file.write_text(json.dumps(report))
        violations, _ = gate.validate(self.root)
        if rule:
            self.assertIn(rule, {v['invariant'] for v in violations}, violations)
        else:
            self.assertEqual([], violations)

    def mutate(self, dataset, field, value, rule):
        rows = self.rows(dataset)
        rows[0][field] = value
        self.write(dataset, rows)
        self.check(rule)

    def test_clean_snapshot(self):
        self.check()

    def test_report_all_financial_and_inventory_fields(self):
        original = json.loads(self.report_file.read_text())
        for section, fields in original.items():
            if section in ('report_title', 'period', 'input_dataset_sha256'):
                continue
            for field in fields:
                with self.subTest(section=section, field=field):
                    report = json.loads(json.dumps(original))
                    value = report[section][field]
                    if field.endswith('_pct') or field == 'closing_date':
                        report[section][field] = 'incorrect'
                    else:
                        report[section][field] = str(gate.dec(value) + 100)
                    self.report_file.write_text(json.dumps(report))
                    self.check('REPORT-RECON')
        self.report_file.write_text(json.dumps(original))

    def test_report_missing_section(self):
        report = json.loads(self.report_file.read_text())
        del report['accounts_receivable_and_cash']
        self.report_file.write_text(json.dumps(report))
        self.check('REPORT-RECON')

    def test_report_missing_hash(self):
        report = json.loads(self.report_file.read_text())
        report['input_dataset_sha256'] = {}
        self.report_file.write_text(json.dumps(report))
        violations, _ = gate.validate(self.root)
        self.assertIn('REPORT-RECON', {v['invariant'] for v in violations})

    def test_ap_wrong_schedule(self):
        self.mutate('perpetual_ap_payments', 'payment_date', '2026-07-25', 'AP-RECON')

    def test_ap_wrong_due_date(self):
        self.mutate('perpetual_ap_payments', 'due_date', '2026-07-25', 'AP-RECON')

    def test_ap_wrong_po(self):
        self.mutate('perpetual_ap_payments', 'po_number', 'FAKE', 'AP-FK')

    def test_ap_underpayment(self):
        self.mutate('perpetual_ap_payments', 'amount_paid_dpp', '1', 'AP-RECON')

    def test_ap_duplicate(self):
        rows = self.rows('perpetual_ap_payments')
        rows.append(dict(rows[0]))
        self.write('perpetual_ap_payments', rows)
        self.check('AP-RECON')

    def test_ap_cumulative_overpayment_with_unique_id(self):
        rows = self.rows('perpetual_ap_payments')
        rows.append(dict(rows[0], ap_payment_id='EXTRA-PAYMENT', amount_paid_dpp='1'))
        self.write('perpetual_ap_payments', rows)
        self.check('AP-RECON')

    def test_ap_missing_payment(self):
        rows = self.rows('perpetual_ap_payments')[1:]
        self.write('perpetual_ap_payments', rows)
        self.check('AP-RECON')

    def test_ledger_unknown_document(self):
        self.mutate('perpetual_stock_event_ledger', 'reference', 'NONEXISTENT-DOCUMENT', 'LEDGER-SOURCE')

    def test_ledger_unknown_type(self):
        self.mutate('perpetual_stock_event_ledger', 'event_type', 'UNSUPPORTED', 'LEDGER-SOURCE')

    def test_ledger_wrong_quantity(self):
        self.mutate('perpetual_stock_event_ledger', 'qty_cartons', '999999', 'LEDGER-SOURCE')

    def test_ledger_unknown_lot(self):
        self.mutate('perpetual_stock_event_ledger', 'lot_number', 'FAKE', 'LEDGER-SOURCE')

    def test_ledger_outside_cutoff(self):
        self.mutate('perpetual_stock_event_ledger', 'date', '2026-08-01', 'LEDGER-SOURCE')

    def test_ledger_missing_event(self):
        rows = self.rows('perpetual_stock_event_ledger')[1:]
        self.write('perpetual_stock_event_ledger', rows)
        self.check('LEDGER-SOURCE')

    def test_ledger_duplicate_event_with_new_id(self):
        rows = self.rows('perpetual_stock_event_ledger')
        rows.append(dict(rows[0], event_id='EXTRA-EVENT'))
        self.write('perpetual_stock_event_ledger', rows)
        self.check('LEDGER-SOURCE')

    def test_ledger_wrong_impact(self):
        self.mutate('perpetual_stock_event_ledger', 'physical_impact', '-999999', 'LEDGER-SOURCE')

    def test_ledger_wrong_cost(self):
        self.mutate('perpetual_stock_event_ledger', 'total_cost_dpp', '0', 'LEDGER-SOURCE')

    def test_card_reserved_mismatch(self):
        self.mutate('perpetual_daily_stock_cards', 'reserved_stock_cartons', '0', 'LEDGER-REPLAY')

    def test_card_valuation_mismatch(self):
        self.mutate('perpetual_daily_stock_cards', 'closing_stock_val_dpp', '0', 'LEDGER-REPLAY')

    def test_ar_duplicate_settlement(self):
        rows = self.rows('perpetual_ar_collections')
        rows.append(dict(rows[0], payment_id='EXTRA-PAYMENT'))
        self.write('perpetual_ar_collections', rows)
        self.check('COLLECTION-MATH')

    def test_ar_wrong_total_cash(self):
        self.mutate('perpetual_ar_collections', 'net_cash_collected_total', '0', 'COLLECTION-MATH')

    def test_ar_future_payment(self):
        self.mutate('perpetual_ar_collections', 'payment_date', '2026-08-01', 'COLLECTION-MATH')

    def test_ar_negative_discount(self):
        self.mutate('perpetual_ar_collections', 'early_payment_discount', '-1', 'COLLECTION-MATH')

    def test_source_cost_mismatch(self):
        self.mutate('perpetual_order_lines', 'cogs_subtotal', '0', 'SOURCE-COGS')

    def test_crlf_inputs_pass(self):
        for path in self.reg.glob('*.csv'):
            path.write_bytes(gate.normalized(path.read_bytes()).replace(b'\n', b'\r\n'))
        self.check()
