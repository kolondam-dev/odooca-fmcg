"""Tes mutasi Kontrak Seed v2: fixture bersih lulus; setiap pelanggaran harus ditolak.

Gate v2 bersifat murni (tanpa Odoo). Baseline nyata (register Juli) juga harus lulus,
kecuali CASH-NONNEG yang memang gagal tanpa saldo awal (gap G-06, tanpa allowlist).
"""
import copy
import importlib.util
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('gates_v2', ROOT / 'scripts/ops/seed_v2_gates.py')
gates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gates)

TAX = dict(rate='0.11', source='https://pajak.go.id/index.php/id/artikel/pmk-1312024-tarif-ppn-sebelas-dua-belas',
           source_date='2026-11-04', effective_from='2025-01-01')


def clean():
    """Satu pack kecil 3-7 Agustus 2026 (Sen-Jum); SO 7 Agustus = carry-forward (DO/faktur 8 Agustus)."""
    pack = dict(
        sales_orders=[
            dict(so_number='SO-202608-0001', date_order='2026-08-03', customer='C1 - X',
                 gross_dpp='200', discount_dpp='20', net_dpp='180'),
            dict(so_number='SO-202608-0002', date_order='2026-08-07', customer='C2 - Y',
                 gross_dpp='100', discount_dpp='10', net_dpp='90')],
        deliveries=[
            dict(do_number='DO-202608-0001', so_number='SO-202608-0001', scheduled_delivery_date='2026-08-04',
                 rejection_dpp='0'),
            dict(do_number='DO-202608-0002', so_number='SO-202608-0002', scheduled_delivery_date='2026-08-08',
                 rejection_dpp='0')],
        invoices=[
            dict(invoice_number='INV-202608-0001', so_number='SO-202608-0001', do_number='DO-202608-0001',
                 date_invoice='2026-08-04', due_date='2026-08-04', payment_term_days='0',
                 dpp_amount='180', ppn_amount='19.80', total_invoice_with_ppn='199.80'),
            dict(invoice_number='INV-202608-0002', so_number='SO-202608-0002', do_number='DO-202608-0002',
                 date_invoice='2026-08-08', due_date='2026-08-22', payment_term_days='14',
                 dpp_amount='90', ppn_amount='9.90', total_invoice_with_ppn='99.90')],
        ar_collections=[
            dict(payment_id='PAY-AR-00002', invoice_number='INV-202608-0001', payment_date='2026-08-05',
                 net_cash_collected_total='199.80'),
            dict(payment_id='PAY-AR-00003', invoice_number='INV-202607-0100', payment_date='2026-08-04',
                 net_cash_collected_total='55')],
        po_headers=[
            dict(po_number='PO-2026-08-01', principal_code='PRIN-A', order_date='2026-08-03',
                 arrival_maumbi_date='2026-08-18', payment_term_days='21', due_date='2026-09-08',
                 rop_trigger_date='2026-08-03', rop_cover_days='12')],
        ap_payments=[
            dict(ap_payment_id='PAY-AP-02', po_number='PO-2026-07-09', payment_date='2026-08-05',
                 amount_paid_dpp='70')],
        opex=[dict(date='2026-08-05', category='x', amount='1000')],
        rejections=[],
        stock_events=[
            dict(event_id='EVT-000001', date='2026-08-03', event_type='SO_RESERVATION', sku_code='S1',
                 lot_number='L1', physical_impact='0', reserved_impact='10', quarantine_impact='0'),
            dict(event_id='EVT-000002', date='2026-08-04', event_type='DO_DISPATCH', sku_code='S1',
                 lot_number='L1', physical_impact='-10', reserved_impact='-10', quarantine_impact='0'),
            dict(event_id='EVT-000003', date='2026-08-07', event_type='SO_RESERVATION', sku_code='S1',
                 lot_number='L1', physical_impact='0', reserved_impact='5', quarantine_impact='0')])
    opening = dict(
        stock={('S1', 'L1'): dict(physical=Decimal(100), reserved=Decimal(0), quarantine=Decimal(0))},
        open_invoices={'INV-202607-0100': {'date_invoice': '2026-07-30', 'total_invoice_with_ppn': '55'}},
        carry_invoices={},
        open_po={'PO-2026-07-09': {'arrival_maumbi_date': '2026-07-28', 'total_dpp': '70'}},
        in_transit={},
        pending_dos={},
    )
    config = dict(pack_start='2026-08-03', pack_end='2026-08-07', tax=dict(TAX),
                  min_lead_days={'PRIN-A': 14}, opening_cash='100000')
    existing = {'SO-202607-0001', 'PAY-AR-00001', 'PAY-AP-01', 'PO-2026-06-01'}
    return dict(pack=pack, opening=opening, config=config, existing=existing)


def run(case, **extra):
    kwargs = dict(opening=case['opening'], config=case['config'], existing_numbers=case['existing'])
    kwargs.update(extra)
    return gates.validate_pack(case['pack'], **kwargs)


def rules(violations):
    return {v['invariant'] for v in violations}


class V2GateTests(unittest.TestCase):
    def setUp(self):
        self.case = copy.deepcopy(clean())

    def expect(self, rule, **extra):
        found = run(self.case, **extra)
        self.assertIn(rule, rules(found), found)

    # ---- baseline
    def test_clean_fixture_passes(self):
        self.assertEqual(run(self.case), [])

    def test_ar_payment_on_sunday_is_allowed(self):
        self.case['pack']['ar_collections'][0]['payment_date'] = '2026-08-09'
        self.case['config']['pack_end'] = '2026-08-09'
        self.assertEqual([v for v in run(self.case) if v['invariant'] == 'CALENDAR-OFFICIAL'], [])

    # ---- INPUT-SCHEMA
    def test_missing_column_rejected(self):
        del self.case['pack']['sales_orders'][0]['net_dpp']
        self.expect('INPUT-SCHEMA')

    def test_missing_required_table_rejected(self):
        del self.case['pack']['sales_orders']
        self.expect('INPUT-SCHEMA')

    # ---- CALENDAR-OFFICIAL
    def test_sunday_order(self):
        self.case['pack']['sales_orders'][0]['date_order'] = '2026-08-02'
        self.expect('CALENDAR-OFFICIAL')

    def test_national_holiday_delivery(self):
        self.case['config'].update(pack_start='2026-08-14', pack_end='2026-08-18')
        self.case['pack']['deliveries'][0]['scheduled_delivery_date'] = '2026-08-17'
        self.expect('CALENDAR-OFFICIAL')

    def test_year_outside_official_calendar(self):
        self.case['pack']['opex'][0]['date'] = '2027-08-05'
        self.expect('CALENDAR-OFFICIAL')

    def test_invalid_date(self):
        self.case['pack']['sales_orders'][0]['date_order'] = '2026-13-45'
        self.expect('CALENDAR-OFFICIAL')

    def test_po_arrival_on_holiday(self):
        self.case['pack']['po_headers'][0]['arrival_maumbi_date'] = '2026-08-25'
        self.case['pack']['po_headers'][0]['due_date'] = '2026-09-15'
        self.expect('CALENDAR-OFFICIAL')

    # ---- PERIOD-WINDOW
    def test_order_before_window(self):
        self.case['pack']['sales_orders'][0]['date_order'] = '2026-07-31'
        self.expect('PERIOD-WINDOW')

    def test_order_after_window(self):
        self.case['pack']['sales_orders'][1]['date_order'] = '2026-08-08'
        self.expect('PERIOD-WINDOW')

    def test_delivery_beyond_next_working_day(self):
        self.case['pack']['deliveries'][1]['scheduled_delivery_date'] = '2026-08-10'
        self.expect('PERIOD-WINDOW')

    def test_stock_event_outside_window(self):
        self.case['pack']['stock_events'][2]['date'] = '2026-08-08'
        self.expect('PERIOD-WINDOW')

    def test_payment_outside_window(self):
        self.case['pack']['ar_collections'][0]['payment_date'] = '2026-08-10'
        self.expect('PERIOD-WINDOW')

    # ---- NUMBERING
    def test_duplicate_so_number(self):
        self.case['pack']['sales_orders'][1]['so_number'] = 'SO-202608-0001'
        self.expect('NUMBERING')

    def test_gap_in_sequence(self):
        self.case['pack']['sales_orders'][1]['so_number'] = 'SO-202608-0003'
        self.expect('NUMBERING')

    def test_collision_with_existing(self):
        self.case['existing'].add('INV-202608-0001')
        self.expect('NUMBERING')

    def test_so_number_month_differs_from_date(self):
        self.case['pack']['sales_orders'][0]['so_number'] = 'SO-202607-0001'
        self.case['pack']['sales_orders'][1]['so_number'] = 'SO-202607-0002'
        self.expect('NUMBERING')

    def test_number_order_not_monotone_with_date(self):
        so = self.case['pack']['sales_orders']
        so[0]['date_order'], so[1]['date_order'] = so[1]['date_order'], so[0]['date_order']
        self.expect('NUMBERING')

    def test_global_sequence_must_continue_after_existing(self):
        self.case['pack']['ar_collections'][0]['payment_id'] = 'PAY-AR-00005'
        self.expect('NUMBERING')

    def test_malformed_number(self):
        self.case['pack']['invoices'][0]['invoice_number'] = 'INV-8-1'
        self.expect('NUMBERING')

    # ---- STOCK-NONNEG
    def test_negative_physical(self):
        self.case['opening']['stock'][('S1', 'L1')]['physical'] = Decimal(5)
        self.expect('STOCK-NONNEG')

    def test_reserved_exceeds_physical(self):
        self.case['pack']['stock_events'][0]['reserved_impact'] = '500'
        self.expect('STOCK-NONNEG')

    def test_negative_quarantine(self):
        self.case['pack']['stock_events'][1]['quarantine_impact'] = '-1'
        self.expect('STOCK-NONNEG')

    def test_events_not_in_date_order(self):
        ev = self.case['pack']['stock_events']
        ev[0], ev[2] = ev[2], ev[0]
        self.expect('STOCK-NONNEG')

    def test_duplicate_event_id(self):
        self.case['pack']['stock_events'][1]['event_id'] = 'EVT-000001'
        self.expect('STOCK-NONNEG')

    def test_non_numeric_impact_is_a_schema_violation(self):
        self.case['pack']['stock_events'][1]['physical_impact'] = 'abc'
        self.expect('INPUT-SCHEMA')

    def test_fractional_carton_impact(self):
        self.case['pack']['stock_events'][1]['physical_impact'] = '-10.5'
        self.expect('STOCK-NONNEG')

    # ---- PERIOD-CONTINUITY
    def expected_closing(self):
        return gates.replay_closing(self.case['opening'], self.case['pack'], self.case['config'])

    def test_closing_state_is_exact(self):
        closing = self.expected_closing()
        self.assertEqual(closing['stock'][('S1', 'L1')],
                         dict(physical=Decimal(90), reserved=Decimal(5), quarantine=Decimal(0)))
        self.assertEqual(closing['open_invoices'], {})
        self.assertEqual(closing['carry_invoices'], {'INV-202608-0002': '2026-08-08'})
        self.assertEqual(closing['pending_dos'], {'DO-202608-0002': '2026-08-08'})
        self.assertEqual(closing['open_po'], {})
        self.assertEqual(closing['in_transit'], {'PO-2026-08-01': '2026-08-18'})

    def test_continuity_passes_when_equal(self):
        closing = self.expected_closing()
        self.assertEqual(gates.check_continuity(closing, copy.deepcopy(closing)), [])

    def test_continuity_stock_off_by_one(self):
        closing = self.expected_closing()
        declared = copy.deepcopy(closing)
        declared['stock'][('S1', 'L1')]['physical'] += 1
        found = gates.check_continuity(declared, closing)
        self.assertIn('PERIOD-CONTINUITY', rules(found))

    def test_continuity_missing_open_invoice(self):
        closing = self.expected_closing()
        closing['open_invoices']['INV-X'] = '2026-08-01'
        declared = self.expected_closing()
        self.assertIn('PERIOD-CONTINUITY', rules(gates.check_continuity(declared, closing)))

    def test_continuity_extra_pending_do(self):
        closing = self.expected_closing()
        declared = copy.deepcopy(closing)
        declared['pending_dos']['DO-GHOST'] = '2026-08-08'
        self.assertIn('PERIOD-CONTINUITY', rules(gates.check_continuity(declared, closing)))

    def test_continuity_zero_rows_equal_missing_rows(self):
        closing = self.expected_closing()
        declared = copy.deepcopy(closing)
        declared['stock'][('S9', 'L9')] = dict(physical=Decimal(0), reserved=Decimal(0), quarantine=Decimal(0))
        self.assertEqual(gates.check_continuity(declared, closing), [])

    def test_validate_pack_checks_declared_opening_against_previous_closing(self):
        previous_closing = copy.deepcopy(self.case['opening'])
        previous_closing['stock'][('S1', 'L1')]['physical'] = Decimal(99)
        self.expect('PERIOD-CONTINUITY', previous_closing=previous_closing)

    # ---- PO-CAUSALITY
    def test_po_without_trigger(self):
        self.case['pack']['po_headers'][0]['rop_trigger_date'] = ''
        self.expect('PO-CAUSALITY')

    def test_po_trigger_after_order(self):
        self.case['pack']['po_headers'][0]['rop_trigger_date'] = '2026-08-04'
        self.expect('PO-CAUSALITY')

    def test_po_non_positive_cover(self):
        self.case['pack']['po_headers'][0]['rop_cover_days'] = '0'
        self.expect('PO-CAUSALITY')

    def test_po_lead_time_too_short(self):
        self.case['pack']['po_headers'][0]['arrival_maumbi_date'] = '2026-08-12'
        self.case['pack']['po_headers'][0]['due_date'] = '2026-09-02'
        self.expect('PO-CAUSALITY')

    def test_po_without_lead_parameter(self):
        self.case['config']['min_lead_days'] = {}
        self.expect('PO-CAUSALITY')

    def test_po_arrival_before_order(self):
        self.case['pack']['po_headers'][0]['arrival_maumbi_date'] = '2026-08-01'
        self.case['pack']['po_headers'][0]['due_date'] = '2026-08-22'
        self.expect('PO-CAUSALITY')

    def test_po_ordered_before_window_is_exempt_from_trigger(self):
        h = self.case['pack']['po_headers'][0]
        h.update(order_date='2026-07-10', rop_trigger_date='', rop_cover_days='')
        self.assertEqual([v for v in run(self.case) if v['invariant'] == 'PO-CAUSALITY'], [])

    # ---- AR-TERMS / AP-TERMS
    def test_ar_due_date_mismatch(self):
        self.case['pack']['invoices'][1]['due_date'] = '2026-08-23'
        self.expect('AR-TERMS')

    def test_ar_payment_before_invoice(self):
        self.case['pack']['ar_collections'][0]['payment_date'] = '2026-08-03'
        self.expect('AR-TERMS')

    def test_ar_payment_unknown_invoice(self):
        self.case['pack']['ar_collections'][0]['invoice_number'] = 'INV-GHOST'
        self.expect('AR-TERMS')

    def test_ar_double_payment(self):
        self.case['pack']['ar_collections'][1]['invoice_number'] = 'INV-202608-0001'
        self.expect('AR-TERMS')

    def test_ar_negative_term(self):
        self.case['pack']['invoices'][0]['payment_term_days'] = '-1'
        self.expect('AR-TERMS')

    def test_ap_due_date_mismatch(self):
        self.case['pack']['po_headers'][0]['due_date'] = '2026-09-09'
        self.expect('AP-TERMS')

    def test_ap_payment_before_arrival(self):
        self.case['pack']['ap_payments'][0]['payment_date'] = '2026-07-27'
        self.case['config']['pack_start'] = '2026-07-27'
        self.expect('AP-TERMS')

    def test_ap_payment_unknown_po(self):
        self.case['pack']['ap_payments'][0]['po_number'] = 'PO-GHOST'
        self.expect('AP-TERMS')

    # ---- TAX-SOURCE
    def test_ppn_wrong(self):
        self.case['pack']['invoices'][0]['ppn_amount'] = '20.00'
        self.expect('TAX-SOURCE')

    def test_total_wrong(self):
        self.case['pack']['invoices'][0]['total_invoice_with_ppn'] = '200.00'
        self.expect('TAX-SOURCE')

    def test_tax_config_without_source(self):
        self.case['config']['tax']['source'] = ''
        self.expect('TAX-SOURCE')

    def test_tax_config_without_date(self):
        del self.case['config']['tax']['source_date']
        self.expect('TAX-SOURCE')

    def test_invoice_before_effective_date(self):
        self.case['config']['tax']['effective_from'] = '2026-08-05'
        self.expect('TAX-SOURCE')

    def test_legacy_ppn_column_name_is_accepted(self):
        for row in self.case['pack']['invoices']:
            row['ppn_11_amount'] = row.pop('ppn_amount')
        self.assertEqual([v for v in run(self.case) if v['invariant'] == 'TAX-SOURCE'], [])

    # ---- CASH-NONNEG
    def test_cash_negative_day(self):
        self.case['config']['opening_cash'] = '10'
        self.expect('CASH-NONNEG')

    def test_cash_requires_opening_balance_in_strict_mode(self):
        del self.case['config']['opening_cash']
        self.assertEqual(run(self.case), [])  # non-strict: dilaporkan sebagai gates_skipped
        self.expect('CASH-NONNEG', strict=True)

    def test_invalid_opening_cash(self):
        self.case['config']['opening_cash'] = 'abc'
        self.expect('CASH-NONNEG')

    # ---- strict mode / pelaporan gate
    def test_skipped_gates_are_reported_and_fail_in_strict_mode(self):
        del self.case['config']['opening_cash']
        report = gates.validate_pack_report(
            self.case['pack'], opening=self.case['opening'], config=self.case['config'],
            existing_numbers=self.case['existing'])
        self.assertEqual(report['gates_skipped'], ['CASH-NONNEG', 'NARRATIVE-ANCHORS', 'PERIOD-CONTINUITY'])
        strict = run(self.case, strict=True)
        self.assertEqual(rules(strict), {'CASH-NONNEG', 'NARRATIVE-ANCHORS', 'PERIOD-CONTINUITY'})

    def test_strict_clean_when_all_inputs_given(self):
        closing_before = copy.deepcopy(self.case['opening'])
        found = run(self.case, strict=True, bands={'net_dpp': ['200', '300']}, previous_closing=closing_before)
        self.assertEqual(found, [])

    def test_schema_violation_stops_further_checks(self):
        del self.case['pack']['invoices'][0]['dpp_amount']
        report = gates.validate_pack_report(
            self.case['pack'], opening=self.case['opening'], config=self.case['config'])
        self.assertEqual(report['gates_run'], ['INPUT-SCHEMA'])

    def test_invalid_window_config(self):
        self.case['config']['pack_end'] = '2026-08-01'
        self.expect('PERIOD-WINDOW')

    def test_cash_zero_balance_is_allowed(self):
        # opening 0 + AR 255,0 (199,80 + 55) - AP 70 - OPEX 1000 < 0 -> pas dibuat nol dengan saldo awal tepat
        total = Decimal('199.80') + Decimal('55') - Decimal('70') - Decimal('1000')
        self.case['config']['opening_cash'] = str(-total)
        self.assertEqual([v for v in run(self.case) if v['invariant'] == 'CASH-NONNEG'], [])

    # ---- NARRATIVE-ANCHORS
    def bands(self):
        return {'net_dpp': ['200', '300'], 'discount_pct': ['9', '11'], 'rejection_pct': ['0', '1'],
                'active_outlets': ['2', '2']}

    def test_anchors_clean(self):
        self.assertEqual([v for v in run(self.case, bands=self.bands()) if v['invariant'] == 'NARRATIVE-ANCHORS'], [])

    def test_anchor_net_out_of_band(self):
        self.case['pack']['sales_orders'][0]['net_dpp'] = '500'
        self.expect('NARRATIVE-ANCHORS', bands=self.bands())

    def test_anchor_discount_out_of_band(self):
        b = self.bands()
        b['discount_pct'] = ['0', '5']
        self.expect('NARRATIVE-ANCHORS', bands=b)

    def test_anchor_active_outlets_out_of_band(self):
        b = self.bands()
        b['active_outlets'] = ['5', '9']
        self.expect('NARRATIVE-ANCHORS', bands=b)

    def test_anchor_unknown_metric(self):
        b = self.bands()
        b['magic'] = ['0', '1']
        self.expect('NARRATIVE-ANCHORS', bands=b)

    def test_anchor_invalid_band(self):
        b = self.bands()
        b['net_dpp'] = ['300', '200']
        self.expect('NARRATIVE-ANCHORS', bands=b)

    # ---- loader
    def test_loader_normalizes_line_endings_and_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.csv'
            path.write_bytes(b'x,y\r\n1,2\r\n')
            rows, digest = gates.read_csv(path)
            self.assertEqual(rows, [dict(x='1', y='2')])
            path.write_bytes(b'x,y\n1,2\n')
            self.assertEqual(gates.read_csv(path)[1], digest)

    def test_loader_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.csv'
            path.write_text('x,y\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                gates.read_csv(path)


class JulyBaselineTests(unittest.TestCase):
    """Register Juli yang sudah beku harus lulus gate v2 yang berlaku untuknya."""

    @classmethod
    def setUpClass(cls):
        reg = ROOT / 'data/registers'
        cls.pack = gates.load_pack(reg, dict(
            sales_orders='perpetual_sales_orders.csv', deliveries='perpetual_deliveries.csv',
            invoices='perpetual_invoices.csv', ar_collections='perpetual_ar_collections.csv',
            po_headers='inbound_po_intransit_june_headers.csv', ap_payments='perpetual_ap_payments.csv',
            opex='perpetual_opex_payroll.csv', rejections='perpetual_order_rejections.csv',
            stock_events='perpetual_stock_event_ledger.csv'))
        cls.config = dict(pack_start='2026-07-01', pack_end='2026-07-31', tax=dict(TAX), min_lead_days={})

    def validate(self, **extra):
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        return gates.validate_pack(self.pack, opening=opening, config=self.config, existing_numbers=set(), **extra)

    def test_july_passes_all_gates_that_apply(self):
        self.assertEqual(self.validate(), [])

    def test_july_closing_state_matches_reconciliation_report(self):
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        closing = gates.replay_closing(opening, self.pack, self.config)
        self.assertEqual(sum(v['physical'] for v in closing['stock'].values()), 53837)
        self.assertEqual(sum(v['reserved'] for v in closing['stock'].values()), 1038)
        self.assertEqual(sum(v['quarantine'] for v in closing['stock'].values()), 9)
        self.assertEqual(len(closing['open_invoices']), 309)
        self.assertEqual(len(closing['carry_invoices']), 48)
        self.assertEqual(len(closing['pending_dos']), 48)
        self.assertEqual(sorted(closing['open_po']), ['PO-2026-06-05'])

    def test_july_cash_without_opening_balance_is_a_known_gap(self):
        # G-06: tanpa saldo awal, kas kumulatif Juli minimum -Rp3.163.173.047,71 pada 31 Juli.
        cfg = dict(self.config, opening_cash='0')
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        found = gates.validate_pack(self.pack, opening=opening, config=cfg, existing_numbers=set())
        cash = [v for v in found if v['invariant'] == 'CASH-NONNEG']
        self.assertTrue(cash)
        self.assertEqual(gates.minimum_cash_balance(self.pack, Decimal(0)), (Decimal('-3163173047.71'), '2026-07-31'))

    def test_july_mutation_is_detected(self):
        mutated = copy.deepcopy(self.pack)
        mutated['sales_orders'][0]['date_order'] = '2026-07-05'  # Minggu
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set())
        self.assertIn('CALENDAR-OFFICIAL', rules(found))

    def test_supervisor_counterexample_invalid_ar_payment_date_fails_strict(self):
        mutated = copy.deepcopy(self.pack)
        target_inv = mutated['ar_collections'][0]['invoice_number']
        mutated['ar_collections'][0]['payment_date'] = 'NOT-A-DATE'
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        detected_rules = rules(found)
        self.assertIn('CALENDAR-OFFICIAL', detected_rules)
        self.assertIn('PERIOD-WINDOW', detected_rules)
        self.assertIn('AR-TERMS', detected_rules)

        # Closing replay must not mark target invoice as paid with invalid payment date
        closing = gates.replay_closing(opening, mutated, self.config)
        self.assertIn(target_inv, closing['open_invoices'])

    def test_supervisor_counterexample_po_without_recorded_debt_rejected(self):
        # PO dari saldo awal tanpa nominal tercatat: pelunasan Rp0,01 wajib ditolak dan tidak boleh menghapus PO
        mutated = copy.deepcopy(self.pack)
        mutated['ap_payments'][0]['po_number'] = 'PO-2026-05-99'
        mutated['ap_payments'][0]['amount_paid_dpp'] = '0.01'
        opening = dict(
            stock={},
            open_invoices={},
            carry_invoices={},
            open_po={'PO-2026-05-99': '2026-06-15'},  # string date only, tanpa nominal tercatat
            in_transit={},
            pending_dos={},
        )
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        self.assertIn('AP-TERMS', rules(found))

        # Replay closing must preserve debt in open_po
        closing = gates.replay_closing(opening, mutated, self.config)
        self.assertIn('PO-2026-05-99', closing['open_po'])

    def test_invoice_without_recorded_receivable_rejected(self):
        # Faktur dari saldo awal tanpa nominal tercatat: pelunasan wajib ditolak dan tidak boleh menghapus faktur
        mutated = copy.deepcopy(self.pack)
        mutated['ar_collections'][0]['invoice_number'] = 'INV-202606-9999'
        mutated['ar_collections'][0]['net_cash_collected_total'] = '0.01'
        opening = dict(
            stock={},
            open_invoices={'INV-202606-9999': '2026-06-25'},  # string date only, tanpa nominal tercatat
            carry_invoices={},
            open_po={},
            in_transit={},
            pending_dos={},
        )
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        self.assertIn('AR-TERMS', rules(found))

        closing = gates.replay_closing(opening, mutated, self.config)
        self.assertIn('INV-202606-9999', closing['open_invoices'])

    def test_supervisor_counterexample_zero_ap_payment_fails_and_preserves_debt(self):
        mutated = copy.deepcopy(self.pack)
        target_po = mutated['ap_payments'][0]['po_number']
        mutated['ap_payments'][0]['amount_paid_dpp'] = '0'
        opening = dict(
            stock={},
            open_invoices={},
            carry_invoices={},
            open_po={'PO-2026-06-01': '2026-07-01', 'PO-2026-06-05': '2026-07-01'},
            in_transit={},
            pending_dos={},
        )
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        detected_rules = rules(found)
        self.assertIn('AP-TERMS', detected_rules)

        # Replay closing must NOT clear debt for Rp0 payment
        closing = gates.replay_closing(opening, mutated, self.config)
        self.assertIn(target_po, closing['open_po'])

    def test_ar_underpayment_fails_terms(self):
        mutated = copy.deepcopy(self.pack)
        mutated['ar_collections'][0]['net_cash_collected_total'] = '1000'
        opening = dict(stock={}, open_invoices={}, carry_invoices={}, open_po={}, in_transit={}, pending_dos={})
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        self.assertIn('AR-TERMS', rules(found))

    def test_ap_underpayment_fails_terms(self):
        mutated = copy.deepcopy(self.pack)
        mutated['ap_payments'][0]['amount_paid_dpp'] = '1000'
        opening = dict(
            stock={},
            open_invoices={},
            carry_invoices={},
            open_po={'PO-2026-06-01': {'arrival_maumbi_date': '2026-07-01', 'total_dpp': '1849772800.0'}},
            in_transit={},
            pending_dos={},
        )
        found = gates.validate_pack(mutated, opening=opening, config=self.config, existing_numbers=set(), strict=True)
        self.assertIn('AP-TERMS', rules(found))


if __name__ == '__main__':
    unittest.main()
