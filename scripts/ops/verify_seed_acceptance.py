#!/usr/bin/env python3
"""Independent July acceptance: source-linked ledger, scheduled AP, full report.

Never executes a generator. Complements verify_seed_invariants.py in the same CI
job. July is the explicit acceptance period; August documents are commitments,
not July movements. Current AR format represents one full settlement per invoice.
"""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import subprocess

START = '2026-07-01'
END = '2026-07-31'
ZERO = Decimal('0')
FILES = (
    'customer_registry_354', 'initial_stock_20260701',
    'inbound_po_intransit_june_headers', 'inbound_po_intransit_june_lines',
    'pjp_july_2026_matrix', 'perpetual_sales_orders', 'perpetual_order_lines',
    'perpetual_deliveries', 'perpetual_order_rejections', 'perpetual_invoices',
    'perpetual_ar_collections', 'perpetual_ap_payments', 'perpetual_opex_payroll',
    'perpetual_daily_stock_cards', 'perpetual_stock_event_ledger',
)


def dec(value):
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError('non-finite amount')
    return value


def normalized(data):
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def validate(root):
    root = Path(root)
    violations, hashes, data = [], {}, {}

    def fail(rule, key, detail):
        violations.append(dict(invariant=rule, record=str(key), detail=detail))

    def equal(rule, key, actual, expected):
        if abs(dec(actual) - dec(expected)) > Decimal('0.01'):
            fail(rule, key, f'expected {expected}; observed {actual}')

    def unique(rows, field, rule):
        result = {}
        for row in rows:
            key = row[field]
            if not key or key in result:
                fail(rule, key, 'missing or duplicate identity')
            result[key] = row
        return result

    def total(rows, field):
        return sum((dec(row[field]) for row in rows), ZERO)

    def july(value):
        dt.date.fromisoformat(value)
        return START <= value <= END

    for name in FILES:
        path = f'data/registers/{name}.csv'
        raw = normalized((root / path).read_bytes())
        hashes[path] = hashlib.sha256(raw).hexdigest()
        data[name] = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    products_raw = normalized((root / 'data/seed/products_150.csv').read_bytes())
    hashes['data/seed/products_150.csv'] = hashlib.sha256(products_raw).hexdigest()
    products = unique(list(csv.DictReader(products_raw.decode().splitlines())), 'default_code', 'MASTER-IDENTITY')
    opening = data['initial_stock_20260701']
    headers = unique(data['inbound_po_intransit_june_headers'], 'po_number', 'AP-FK')
    receipts = data['inbound_po_intransit_june_lines']
    orders = unique(data['perpetual_sales_orders'], 'so_number', 'TX-IDENTITY')
    lines = data['perpetual_order_lines']
    deliveries = unique(data['perpetual_deliveries'], 'do_number', 'TX-IDENTITY')
    invoices = unique(data['perpetual_invoices'], 'invoice_number', 'TX-IDENTITY')
    rejections = data['perpetual_order_rejections']
    payments = data['perpetual_ar_collections']
    ap = data['perpetual_ap_payments']
    opex = data['perpetual_opex_payroll']
    cards = unique(data['perpetual_daily_stock_cards'], 'date', 'LEDGER-REPLAY')
    expected_dates = {(dt.date(2026, 7, 1) + dt.timedelta(days=i)).isoformat() for i in range(31)}
    if set(cards) != expected_dates:
        fail('LEDGER-REPLAY', 'calendar', 'expected exactly 31 July daily cards')

    # AP amounts/dates are derived per PO, never from a fixed monthly total.
    unique(ap, 'ap_payment_id', 'AP-RECON')
    paid_by_po = defaultdict(Decimal)
    for row in ap:
        key = row['ap_payment_id']
        header = headers.get(row['po_number'])
        if not header:
            fail('AP-FK', key, 'unknown PO')
            continue
        amount = dec(row['amount_paid_dpp'])
        paid_by_po[row['po_number']] += amount
        if amount <= 0 or not july(row['payment_date']):
            fail('AP-RECON', key, 'positive payment within July required')
        if row['payment_date'] != header['ap_payment_date'] or row['due_date'] != header['due_date']:
            fail('AP-RECON', key, 'payment/due date differs from source schedule')
        if row['principal_name'] != header['principal_name']:
            fail('AP-FK', key, 'principal differs from PO')
    for key, header in headers.items():
        expected = dec(header['total_dpp']) if july(header['ap_payment_date']) else ZERO
        equal('AP-RECON', key, paid_by_po[key], expected)
        if paid_by_po[key] > dec(header['total_dpp']):
            fail('AP-RECON', key, 'cumulative overpayment')

    # Build expected movement multiset exclusively from source documents.
    expected_events = Counter()
    lot_cost = {}

    def event(day, kind, ref, row, qty, cost):
        qty, cost = dec(qty), dec(cost)
        if qty <= 0 or qty != qty.to_integral_value():
            fail('LEDGER-SOURCE', ref, 'positive whole cartons required')
        if not july(day):
            return  # Future delivery is explicitly reserved at July cutoff.
        impacts = {'INITIAL_STOCK': (qty, ZERO, ZERO), 'PO_RECEIPT': (qty, ZERO, ZERO),
                   'SO_RESERVATION': (ZERO, qty, ZERO), 'DO_DISPATCH': (-qty, -qty, ZERO),
                   'QUARANTINE_RECEIPT': (ZERO, ZERO, qty)}[kind]
        expected_events[(day, kind, ref, row['sku_code'], row['lot_number'], qty, *impacts)] += 1

    for row in opening:
        lot_cost[(row['sku_code'], row['lot_number'])] = dec(row['unit_cost_price'])
        event(START, 'INITIAL_STOCK', 'OPENING-20260701', row, row['qty_cartons_on_hand'], row['unit_cost_price'])
    for row in receipts:
        header = headers[row['po_number']]
        lot_cost[(row['sku_code'], row['lot_number'])] = dec(row['unit_cost_price'])
        event(header['arrival_maumbi_date'], 'PO_RECEIPT', row['po_number'], row, row['qty_cartons'], row['unit_cost_price'])
    by_so = defaultdict(list)
    source_cogs = defaultdict(Decimal)
    for row in lines:
        key = row['so_number']
        by_so[key].append(row)
        cost = lot_cost[(row['sku_code'], row['lot_number'])]
        expected_cost = dec(row['qty_cartons']) * dec(row['carton_qty']) * cost
        equal('SOURCE-COGS', key, row['cogs_subtotal'], expected_cost)
        source_cogs[key] += expected_cost
        event(orders[key]['date_order'], 'SO_RESERVATION', key, row, row['qty_cartons'], cost)
    for key, order in orders.items():
        equal('SOURCE-COGS', key, order['cogs_dpp'], source_cogs[key])
    unique(rejections, 'rejection_id', 'RETURN-RECON')
    rejected_cost = defaultdict(Decimal)
    rejected_qty = defaultdict(Decimal)
    for row in rejections:
        key = (row['so_number'], row['sku_code'], row['lot_number'])
        rejected_qty[key] += dec(row['qty_cartons'])
        shipped = sum((dec(line['qty_cartons']) for line in by_so[key[0]]
                       if (line['sku_code'], line['lot_number']) == key[1:]), ZERO)
        if rejected_qty[key] > shipped:
            fail('RETURN-RECON', row['rejection_id'], 'cumulative rejection exceeds shipped lot')
        cost = lot_cost[(row['sku_code'], row['lot_number'])]
        value = dec(row['qty_cartons']) * dec(row['carton_qty']) * cost
        equal('SOURCE-COGS', row['rejection_id'], row['cogs_subtotal'], value)
        rejected_cost[row['so_number']] += value
        event(row['rejection_date'], 'QUARANTINE_RECEIPT', row['rejection_id'], row, row['qty_cartons'], cost)
    for key, delivery in deliveries.items():
        for row in by_so[delivery['so_number']]:
            event(delivery['scheduled_delivery_date'], 'DO_DISPATCH', key, row, row['qty_cartons'],
                  lot_cost[(row['sku_code'], row['lot_number'])])

    ledger = data['perpetual_stock_event_ledger']
    unique(ledger, 'event_id', 'LEDGER-SOURCE')
    actual_events = Counter()
    for row in ledger:
        signature = (row['date'], row['event_type'], row['reference'], row['sku_code'], row['lot_number'],
                     dec(row['qty_cartons']), dec(row['physical_impact']),
                     dec(row['reserved_impact']), dec(row['quarantine_impact']))
        actual_events[signature] += 1
        if signature not in expected_events:
            fail('LEDGER-SOURCE', row['event_id'], 'event date/type/reference/lot/quantity/impacts not in source documents')
        cost = lot_cost.get((row['sku_code'], row['lot_number']))
        if cost is not None:
            equal('LEDGER-SOURCE', row['event_id'], row['unit_cost_price'], cost)
            equal('LEDGER-SOURCE', row['event_id'], row['total_cost_dpp'],
                  dec(row['qty_cartons']) * dec(products[row['sku_code']]['carton_qty']) * cost)
    for signature, count in (expected_events - actual_events).items():
        fail('LEDGER-SOURCE', signature[:5], f'missing {count} source movement(s)')
    for signature, count in (actual_events - expected_events).items():
        fail('LEDGER-SOURCE', signature[:5], f'{count} unexpected/duplicate movement(s)')

    # Replay all events in recorded sequence within each date; source multiset
    # enforces movement coverage, while replay enforces available physical stock.
    states = defaultdict(lambda: [ZERO, ZERO, ZERO])
    events_by_date = defaultdict(list)
    for row in ledger:
        events_by_date[row['date']].append(row)
    valuations, quarantine_values, volumes = {}, {}, {}
    for day in sorted(cards):
        for row in events_by_date[day]:
            state = states[(row['sku_code'], row['lot_number'])]
            for i, field in enumerate(('physical_impact', 'reserved_impact', 'quarantine_impact')):
                state[i] += dec(row[field])
            if min(state) < 0 or state[1] > state[0]:
                fail('LEDGER-REPLAY', row['event_id'], 'negative stock or reserved exceeds physical')
        sums = [sum((v[i] for v in states.values()), ZERO) for i in range(3)]
        card = cards[day]
        for field, expected in zip(('physical_stock_cartons', 'reserved_stock_cartons', 'quarantine_stock_cartons'), sums):
            equal('LEDGER-REPLAY', day + ':' + field, card[field], expected)
        equal('LEDGER-REPLAY', day + ':available', card['available_stock_cartons'], sums[0] - sums[1])
        value = quarantine = volume = ZERO
        for (sku, lot), (physical, reserved, bad) in states.items():
            if sku not in products or (sku, lot) not in lot_cost:
                continue  # Unknown source already reported above.
            pack = dec(products[sku]['carton_qty'])
            value += physical * pack * lot_cost[(sku, lot)]
            quarantine += bad * pack * lot_cost[(sku, lot)]
            volume += (physical + bad) * dec(products[sku]['carton_volume_cbm'])
        valuations[day], quarantine_values[day], volumes[day] = value, quarantine, volume
        equal('LEDGER-REPLAY', day + ':valuation', card['closing_stock_val_dpp'], value)
        equal('LEDGER-REPLAY', day + ':volume', card['closing_stock_cbm'], volume.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

    # Full-settlement AR contract: unique payment and invoice, positive cash,
    # no future payment counted in July, no duplicate settlement of same invoice.
    unique(payments, 'payment_id', 'COLLECTION-MATH')
    settled = unique(payments, 'invoice_number', 'COLLECTION-MATH')
    for row in payments:
        key = row['payment_id']
        inv = invoices.get(row['invoice_number'])
        if inv is None:
            fail('COLLECTION-MATH', key, 'unknown invoice')
            continue
        if not july(row['payment_date']) or row['payment_date'] < inv['date_invoice']:
            fail('COLLECTION-MATH', key, 'payment outside July or before invoice')
        discount = dec(row['early_payment_discount'])
        if discount < 0 or discount > dec(inv['dpp_amount']):
            fail('COLLECTION-MATH', key, 'invalid payment discount')
        for field, source in (('invoice_dpp', 'dpp_amount'), ('invoice_ppn', 'ppn_11_amount'),
                              ('invoice_total_with_ppn', 'total_invoice_with_ppn')):
            equal('COLLECTION-MATH', key + ':' + field, row[field], inv[source])
        equal('COLLECTION-MATH', key + ':cash', row['net_cash_collected'], dec(inv['dpp_amount']) - discount)
        equal('COLLECTION-MATH', key + ':grosscash', row['net_cash_collected_total'], dec(inv['total_invoice_with_ppn']) - discount)

    # Recompute every numeric report field from source rows, without invoking or
    # importing the report generator. Percentages follow the published formatting.
    j_inv = [v for v in invoices.values() if july(v['date_invoice'])]
    a_inv = [v for v in invoices.values() if v['date_invoice'] > END]
    a_do = [v for v in deliveries.values() if v['scheduled_delivery_date'] > END]
    a_so = {v['so_number'] for v in a_do}
    cogs_j = sum((v for k, v in source_cogs.items() if k not in a_so), ZERO) - sum(
        (dec(r['cogs_subtotal']) for r in rejections if july(r['rejection_date'])), ZERO)
    cogs_a = sum((v for k, v in source_cogs.items() if k in a_so), ZERO) - sum(
        (dec(r['cogs_subtotal']) for r in rejections if r['rejection_date'] > END), ZERO)
    revenue = total(j_inv, 'dpp_amount')
    expenses = total(opex, 'amount')
    for row in opex:
        if not july(row['date']) or dec(row['amount']) < 0:
            fail('REPORT-RECON', 'opex', 'expense outside July or negative')
    profit = revenue - cogs_j
    net = profit - expenses
    open_inv = [v for v in j_inv if v['invoice_number'] not in settled]
    cash = total(payments, 'net_cash_collected')
    discount = total(payments, 'early_payment_discount')
    open_ar = total(open_inv, 'dpp_amount')
    equal('REPORT-RECON', 'AR-DPP-BRIDGE', cash + discount + open_ar, revenue)
    equal('REPORT-RECON', 'AR-GROSS-BRIDGE', total(payments, 'net_cash_collected_total') + discount
          + total(open_inv, 'total_invoice_with_ppn'), total(j_inv, 'total_invoice_with_ppn'))
    paid = total(ap, 'amount_paid_dpp')
    open_pos = [v for k, v in headers.items() if paid_by_po[k] == 0]
    open_ap = sum((dec(v['total_dpp']) - paid_by_po[k] for k, v in headers.items()), ZERO)
    last = cards[END]
    expected = {
        'sales_orders_booked_july': dict(so_count=len(orders), gross_dpp=total(orders.values(), 'gross_dpp'),
            discount_dpp=total(orders.values(), 'discount_dpp'), net_dpp=total(orders.values(), 'net_dpp'),
            total_cogs_dpp=sum(source_cogs.values(), ZERO), lines_count=len(lines),
            lines_gross_dpp=total(lines, 'line_subtotal_dpp'), lines_cogs_dpp=total(lines, 'cogs_subtotal')),
        'delivery_orders_reconciliation': dict(do_count=len(deliveries), gross_order_dpp=total(deliveries.values(), 'gross_order_dpp'),
            rejection_dpp=total(rejections, 'line_subtotal_dpp'), rejection_cogs_dpp=total(rejections, 'cogs_subtotal'),
            do_delivered_dpp=total(deliveries.values(), 'do_delivered_dpp'), rejections_count=len(rejections),
            rejections_cartons=total(rejections, 'qty_cartons')),
        'period_cutoff_july_invoiced': dict(invoice_count=len(j_inv), invoiced_dpp=revenue,
            ppn_11_amount=total(j_inv, 'ppn_11_amount'), total_invoice_with_ppn=total(j_inv, 'total_invoice_with_ppn'),
            delivered_cogs_accepted=cogs_j, gross_profit=profit, operating_expenses_payroll=expenses,
            net_operating_profit=net, gross_margin_pct=f'{profit / revenue * 100:.2f}%',
            net_margin_pct=f'{net / revenue * 100:.2f}%'),
        'carry_forward_august': dict(invoice_count=len(a_inv), do_delivered_dpp=total(a_do, 'do_delivered_dpp'),
            invoiced_dpp=total(a_inv, 'dpp_amount'), ppn_11_amount=total(a_inv, 'ppn_11_amount'),
            total_invoice_with_ppn=total(a_inv, 'total_invoice_with_ppn'), cogs_accepted=cogs_a,
            rejections_count=sum(r['rejection_date'] > END for r in rejections)),
        'accounts_receivable_and_cash': dict(collections_count=len(payments), net_cash_collected_dpp=cash,
            early_payment_discount_dpp=discount, total_cash_and_discount_dpp=cash + discount,
            net_cash_collected_total_with_ppn=total(payments, 'net_cash_collected_total'),
            open_ar_july_invoices_count=len(open_inv), open_ar_july_dpp=open_ar,
            open_ar_july_total_with_ppn=total(open_inv, 'total_invoice_with_ppn'),
            reconciled_invoice_dpp_total=cash + discount + open_ar),
        'accounts_payable_reconciliation': dict(total_po_june_intransit_count=len(headers),
            total_po_june_intransit_dpp=total(headers.values(), 'total_dpp'), ap_payments_july_count=len(ap),
            ap_payments_july_dpp=paid, open_ap_po_count=len(open_pos), open_ap_july_dpp=open_ap,
            reconciled_ap_dpp_total=paid + open_ap),
        'inventory_warehouse_reconciliation': dict(closing_date=END, physical_on_hand_cartons=last['physical_stock_cartons'],
            reserved_cartons=last['reserved_stock_cartons'], available_for_sale_cartons=last['available_stock_cartons'],
            quarantine_bad_stock_cartons=last['quarantine_stock_cartons'],
            saleable_physical_stock_valuation_dpp=valuations[END], quarantine_asset_val_cogs=quarantine_values[END],
            total_warehouse_stock_valuation_dpp=valuations[END] + quarantine_values[END],
            closing_stock_valuation_dpp=valuations[END],
            peak_warehouse_occupancy_pct=f'{max(dec(c["warehouse_occupancy_pct"]) for c in cards.values()):.1f}%'),
    }
    report_path = 'data/registers/canonical_financial_reconciliation_july_2026.json'
    raw = normalized((root / report_path).read_bytes())
    hashes[report_path] = hashlib.sha256(raw).hexdigest()
    report = json.loads(raw)
    declared = report.get('input_dataset_sha256', {})
    required = {name + '.csv' for name in FILES}
    if set(declared) != required:
        fail('REPORT-RECON', 'input_dataset_sha256', 'required input fingerprint set missing/extra')
    for name in required:
        if declared.get(name) != hashes['data/registers/' + name]:
            fail('REPORT-RECON', name, 'canonical LF input hash mismatch')
    for section, fields in expected.items():
        observed = report.get(section, {})
        if set(observed) != set(fields):
            fail('REPORT-RECON', section, 'required report fields missing/extra')
        for field, value in fields.items():
            if field not in observed:
                continue
            if field.endswith('_pct') or field == 'closing_date':
                if observed[field] != value:
                    fail('REPORT-RECON', section + ':' + field, f'expected {value}')
            else:
                equal('REPORT-RECON', section + ':' + field, observed[field], value)
    return violations, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        violations, hashes = validate(args.root)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        violations, hashes = [dict(invariant='INPUT-SCHEMA', record='dataset', detail=str(error))], {}
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=args.root, capture_output=True, text=True).stdout.strip()
    result = dict(schema_version=1, commit=sha, scope='July source artifacts; not Odoo runtime acceptance',
                  status='FAIL' if violations else 'PASS', input_sha256=hashes,
                  counts=dict(Counter(v['invariant'] for v in violations)), violations=violations)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], counts=result['counts'])))
    return int(bool(violations))


if __name__ == '__main__':
    raise SystemExit(main())
