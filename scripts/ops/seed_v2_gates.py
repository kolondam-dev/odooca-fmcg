#!/usr/bin/env python3
"""Gate Kontrak Seed v2 (docs/reviews/SEED_INVARIANT_CONTRACT_V2.md).

Murni: hanya stdlib, tidak membaca generator, tidak menghubungi Odoo. Setiap pelanggaran
berbentuk {"invariant", "record", "detail"} (sama dengan verify_seed_invariants.py).
Tidak ada allowlist atau pelebaran toleransi; toleransi uang tetap Rp0,01 (Decimal).

Gate inti selalu berjalan. Gate berbasis konfigurasi (CASH-NONNEG, NARRATIVE-ANCHORS,
PERIOD-CONTINUITY) hanya berjalan bila inputnya diberikan; pada penerimaan nyata gunakan
strict=True agar gate yang terlewat menjadi pelanggaran, bukan lolos diam-diam.
"""
import copy
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import importlib.util
import io
from pathlib import Path
import re

_SPEC = importlib.util.spec_from_file_location('fmcg_calendar_v2', Path(__file__).with_name('fmcg_calendar.py'))
calendar = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(calendar)

CALENDAR_YEARS = {2026}  # fmcg_calendar.py hanya memuat libur nasional 2026
TOLERANCE = Decimal('0.01')
ZERO = Decimal(0)

REQUIRED_TABLES = {
    'sales_orders': ['so_number', 'date_order', 'customer', 'gross_dpp', 'discount_dpp', 'net_dpp'],
    'deliveries': ['do_number', 'so_number', 'scheduled_delivery_date', 'rejection_dpp'],
    'invoices': ['invoice_number', 'so_number', 'do_number', 'date_invoice', 'due_date', 'payment_term_days',
                 'dpp_amount', 'total_invoice_with_ppn'],
    'ar_collections': ['payment_id', 'invoice_number', 'payment_date', 'net_cash_collected_total'],
    'opex': ['date', 'amount'],
    'stock_events': ['event_id', 'date', 'sku_code', 'lot_number', 'physical_impact', 'reserved_impact',
                     'quarantine_impact'],
}
OPTIONAL_TABLES = {
    'po_headers': ['po_number', 'principal_code', 'order_date', 'arrival_maumbi_date', 'payment_term_days',
                   'due_date'],
    'ap_payments': ['ap_payment_id', 'po_number', 'payment_date', 'amount_paid_dpp'],
    'rejections': ['rejection_id', 'rejection_date'],
}
NUMERIC = {
    'sales_orders': ['gross_dpp', 'discount_dpp', 'net_dpp'],
    'deliveries': ['rejection_dpp'],
    'invoices': ['payment_term_days', 'dpp_amount', 'total_invoice_with_ppn'],
    'ar_collections': ['net_cash_collected_total'],
    'po_headers': ['payment_term_days'],
    'ap_payments': ['amount_paid_dpp'],
    'opex': ['amount'],
    'stock_events': ['physical_impact', 'reserved_impact', 'quarantine_impact'],
}
STATE_KEYS = ('stock', 'open_invoices', 'carry_invoices', 'open_po', 'in_transit', 'pending_dos')
ANCHOR_METRICS = ('net_dpp', 'discount_pct', 'rejection_pct', 'active_outlets')

# (jenis, tabel, kolom nomor, pola, kolom tanggal untuk uji monoton)
NUMBER_KINDS = (
    ('SO', 'sales_orders', 'so_number', r'SO-(?P<grp>\d{6})-(?P<seq>\d{4})', 'date_order'),
    ('DO', 'deliveries', 'do_number', r'DO-(?P<grp>\d{6})-(?P<seq>\d{4})', 'scheduled_delivery_date'),
    ('INV', 'invoices', 'invoice_number', r'INV-(?P<grp>\d{6})-(?P<seq>\d{4})', 'date_invoice'),
    ('REJ', 'rejections', 'rejection_id', r'REJ-(?P<grp>\d{6})-(?P<seq>\d{3})', None),
    ('PAY-AR', 'ar_collections', 'payment_id', r'PAY-AR-(?P<seq>\d{5})', None),
    ('PAY-AP', 'ap_payments', 'ap_payment_id', r'PAY-AP-(?P<seq>\d{2,})', None),
    ('PO', 'po_headers', 'po_number', r'PO-(?P<grp>\d{4}-\d{2})-(?P<seq>\d{2})', None),
    ('EVT', 'stock_events', 'event_id', r'EVT-(?P<seq>\d{6})', None),
)


class _Report:
    def __init__(self):
        self.items = []

    def fail(self, rule, record, detail):
        self.items.append({'invariant': rule, 'record': str(record), 'detail': detail})


def _dec(value):
    result = Decimal(str(value).strip())
    if not result.is_finite():
        raise InvalidOperation
    return result


def _date(value):
    try:
        return dt.date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def _whole(value):
    return value == value.to_integral_value()


def _ym(date):
    return f'{date.year:04d}{date.month:02d}'


# ---------------------------------------------------------------- loader

def read_csv(path, allow_empty=False):
    """Baca CSV (LF-kanonikal) -> (baris, sha256). Berkas kosong ditolak kecuali allow_empty."""
    data = Path(path).read_bytes()
    normalized = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    rows = list(csv.DictReader(io.StringIO(normalized.decode('utf-8-sig'))))
    if not rows and not allow_empty:
        raise ValueError(f'empty required dataset: {path}')
    return rows, hashlib.sha256(normalized).hexdigest()


def load_pack(root, names):
    """names: {tabel: nama berkas}. Tabel opsional boleh berkas berisi header saja."""
    pack = {}
    for table, filename in names.items():
        pack[table], _ = read_csv(Path(root) / filename, allow_empty=table in OPTIONAL_TABLES)
    return pack


# ---------------------------------------------------------------- INPUT-SCHEMA

def _check_schema(pack, rpt):
    for table, columns in REQUIRED_TABLES.items():
        if table not in pack:
            rpt.fail('INPUT-SCHEMA', table, 'required table missing')
    seen = set()
    for table, columns in {**REQUIRED_TABLES, **OPTIONAL_TABLES}.items():
        for index, row in enumerate(pack.get(table, [])):
            for column in columns:
                if column not in row and (table, column) not in seen:
                    seen.add((table, column))
                    rpt.fail('INPUT-SCHEMA', f'{table}.{column}', f'required column missing (row {index})')
    for index, row in enumerate(pack.get('invoices', [])):
        if 'ppn_amount' not in row and 'ppn_11_amount' not in row and ('invoices', 'ppn') not in seen:
            seen.add(('invoices', 'ppn'))
            rpt.fail('INPUT-SCHEMA', 'invoices.ppn_amount', f'ppn_amount/ppn_11_amount missing (row {index})')
    if rpt.items:
        return
    for table, columns in NUMERIC.items():
        for index, row in enumerate(pack.get(table, [])):
            for column in columns:
                try:
                    _dec(row[column])
                except (InvalidOperation, ValueError):
                    rpt.fail('INPUT-SCHEMA', f'{table}[{index}].{column}', f'invalid number: {row[column]!r}')
    for index, row in enumerate(pack.get('invoices', [])):
        try:
            _dec(_ppn(row))
        except (InvalidOperation, ValueError):
            rpt.fail('INPUT-SCHEMA', f'invoices[{index}].ppn', f'invalid number: {_ppn(row)!r}')


def _ppn(row):
    return row['ppn_amount'] if 'ppn_amount' in row else row['ppn_11_amount']


def _window(config, rpt):
    start, end = _date(config.get('pack_start')), _date(config.get('pack_end'))
    if not start or not end or start > end:
        rpt.fail('PERIOD-WINDOW', 'config', 'pack_start/pack_end missing, invalid or inverted')
        return None
    return start, end


# ---------------------------------------------------------------- CALENDAR-OFFICIAL

DATE_FIELDS = (
    ('sales_orders', 'so_number', 'date_order'),
    ('deliveries', 'do_number', 'scheduled_delivery_date'),
    ('invoices', 'invoice_number', 'date_invoice'),
    ('rejections', 'rejection_id', 'rejection_date'),
    ('po_headers', 'po_number', 'order_date'),
    ('po_headers', 'po_number', 'arrival_maumbi_date'),
    ('ap_payments', 'ap_payment_id', 'payment_date'),
    ('opex', None, 'date'),
    ('stock_events', 'event_id', 'date'),
)  # tanggal pembayaran AR sengaja tidak diuji: transfer bank dapat jatuh pada hari non-kerja (25 kasus di Juli)


def _check_calendar(pack, rpt):
    for table, key, column in DATE_FIELDS:
        for index, row in enumerate(pack.get(table, [])):
            record = row[key] if key else f'{table}[{index}]'
            date = _date(row[column])
            if date is None:
                rpt.fail('CALENDAR-OFFICIAL', record, f'{column}: invalid date {row[column]!r}')
            elif date.year not in CALENDAR_YEARS:
                rpt.fail('CALENDAR-OFFICIAL', record, f'{column} {date}: official calendar covers {sorted(CALENDAR_YEARS)} only')
            elif not calendar.is_working_day(date):
                rpt.fail('CALENDAR-OFFICIAL', record, f'{column} {date}: not an official working day')


# ---------------------------------------------------------------- PERIOD-WINDOW

def _check_window(pack, start, end, rpt):
    follow = calendar.get_next_working_day(end)
    rules = (
        ('sales_orders', 'so_number', 'date_order', start, end),
        ('deliveries', 'do_number', 'scheduled_delivery_date', start, follow),
        ('invoices', 'invoice_number', 'date_invoice', start, follow),
        ('rejections', 'rejection_id', 'rejection_date', start, follow),
        ('stock_events', 'event_id', 'date', start, end),
        ('ar_collections', 'payment_id', 'payment_date', start, end),
        ('ap_payments', 'ap_payment_id', 'payment_date', start, end),
        ('opex', None, 'date', start, end),
        ('po_headers', 'po_number', 'order_date', None, end),
    )
    for table, key, column, low, high in rules:
        for index, row in enumerate(pack.get(table, [])):
            date = _date(row[column])
            if date is None:
                continue  # dilaporkan CALENDAR-OFFICIAL
            record = row[key] if key else f'{table}[{index}]'
            if (low and date < low) or date > high:
                rpt.fail('PERIOD-WINDOW', record, f'{column} {date} outside [{low or "-"}, {high}]')


# ---------------------------------------------------------------- NUMBERING

def _check_numbering(pack, existing, rpt):
    existing = set(existing)
    for kind, table, column, pattern, date_column in NUMBER_KINDS:
        regex = re.compile(pattern + r'$')
        rows = pack.get(table, [])
        numbers = [row[column] for row in rows]
        if len(set(numbers)) != len(numbers):
            for number in sorted({n for n in numbers if numbers.count(n) > 1}):
                rpt.fail('NUMBERING', number, f'{kind}: duplicate number within pack')
        for number in sorted(set(numbers) & existing):
            rpt.fail('NUMBERING', number, f'{kind}: collides with an already existing document number')
        parsed = {}
        for row in rows:
            match = regex.fullmatch(row[column])
            if not match:
                rpt.fail('NUMBERING', row[column], f'{kind}: malformed number')
                continue
            group = match.groupdict().get('grp') or ''
            parsed.setdefault(group, []).append((int(match.group('seq')), row))
        for group in sorted(parsed):
            floor = 0
            for number in existing:
                match = regex.fullmatch(number)
                if match and (match.groupdict().get('grp') or '') == group:
                    floor = max(floor, int(match.group('seq')))
            sequence = sorted({seq for seq, _ in parsed[group]})
            expected = list(range(floor + 1, floor + 1 + len(sequence)))
            if sequence != expected:
                rpt.fail('NUMBERING', f'{kind}-{group or "*"}',
                         f'sequence must be contiguous from {floor + 1}; observed {sequence[:3]}...{sequence[-1:]}')
            if date_column:
                dates = [_date(row[date_column]) for _, row in sorted(parsed[group], key=lambda item: item[0])]
                dates = [d for d in dates if d]
                if dates != sorted(dates):
                    rpt.fail('NUMBERING', f'{kind}-{group or "*"}', f'number order is not monotone with {date_column}')
            if group and kind in ('SO', 'PO'):
                month_column = 'date_order' if kind == 'SO' else 'order_date'
                for _, row in parsed[group]:
                    date = _date(row[month_column])
                    expected_group = _ym(date) if kind == 'SO' and date else (
                        f'{date.year:04d}-{date.month:02d}' if date else None)
                    if date and group != expected_group:
                        rpt.fail('NUMBERING', row[column], f'{kind}: number month {group} differs from {month_column} {date}')


# ---------------------------------------------------------------- STOCK-NONNEG

def _check_stock(pack, opening_stock, rpt):
    state = {key: dict(value) for key, value in opening_stock.items()}
    for key, value in sorted(state.items()):
        if any(value[field] < 0 for field in ('physical', 'reserved', 'quarantine')) or value['reserved'] > value['physical']:
            rpt.fail('STOCK-NONNEG', f'opening:{key[0]}/{key[1]}', f'invalid opening balance {value}')
    seen, previous = set(), None
    for row in pack.get('stock_events', []):
        event = row['event_id']
        if event in seen:
            rpt.fail('STOCK-NONNEG', event, 'duplicate event id')
        seen.add(event)
        date = _date(row['date'])
        if date and previous and date < previous:
            rpt.fail('STOCK-NONNEG', event, f'events are not in date order ({date} after {previous})')
        previous = date or previous
        impacts = {field: _dec(row[f'{field}_impact']) for field in ('physical', 'reserved', 'quarantine')}
        if not all(_whole(v) for v in impacts.values()):
            rpt.fail('STOCK-NONNEG', event, 'cartons must be whole numbers')
        balance = state.setdefault((row['sku_code'], row['lot_number']),
                                   dict(physical=ZERO, reserved=ZERO, quarantine=ZERO))
        for field, delta in impacts.items():
            balance[field] += delta
        if balance['physical'] < 0 or balance['reserved'] < 0 or balance['quarantine'] < 0:
            rpt.fail('STOCK-NONNEG', event, f'negative balance after event: {balance}')
        elif balance['reserved'] > balance['physical']:
            rpt.fail('STOCK-NONNEG', event, f'reserved exceeds physical after event: {balance}')


# ---------------------------------------------------------------- PERIOD-CONTINUITY

def replay_closing(opening, pack, config):
    """Keadaan penutupan pack dari keadaan pembukaannya (stok, piutang, hutang, DO tertunda)."""
    end = _date(config['pack_end'])
    stock = {key: dict(value) for key, value in opening.get('stock', {}).items()}
    for row in pack.get('stock_events', []):
        balance = stock.setdefault((row['sku_code'], row['lot_number']),
                                   dict(physical=ZERO, reserved=ZERO, quarantine=ZERO))
        for field in ('physical', 'reserved', 'quarantine'):
            balance[field] += _dec(row[f'{field}_impact'])
    paid_invoices = {row['invoice_number'] for row in pack.get('ar_collections', [])}
    invoices = dict(opening.get('open_invoices', {}))
    invoices.update(opening.get('carry_invoices', {}))
    invoices.update({row['invoice_number']: row['date_invoice'] for row in pack.get('invoices', [])})
    paid_po = {row['po_number'] for row in pack.get('ap_payments', [])}
    pos = dict(opening.get('open_po', {}))
    pos.update(opening.get('in_transit', {}))
    pos.update({row['po_number']: row['arrival_maumbi_date'] for row in pack.get('po_headers', [])})
    return {
        'stock': stock,
        'open_invoices': {n: d for n, d in sorted(invoices.items())
                          if _date(d) and _date(d) <= end and n not in paid_invoices},
        'carry_invoices': {n: d for n, d in sorted(invoices.items())
                           if _date(d) and _date(d) > end and n not in paid_invoices},
        'open_po': {n: d for n, d in sorted(pos.items()) if _date(d) and _date(d) <= end and n not in paid_po},
        'in_transit': {n: d for n, d in sorted(pos.items()) if _date(d) and _date(d) > end},
        'pending_dos': {row['do_number']: row['scheduled_delivery_date'] for row in pack.get('deliveries', [])
                        if _date(row['scheduled_delivery_date']) and _date(row['scheduled_delivery_date']) > end},
    }


def _nonzero_stock(stock):
    return {key: value for key, value in stock.items() if any(value[field] != 0 for field in value)}


def check_continuity(declared, expected):
    """Pembukaan yang dideklarasikan pack harus identik dengan penutupan pack sebelumnya."""
    rpt = _Report()
    for key in STATE_KEYS:
        left, right = declared.get(key, {}), expected.get(key, {})
        if key == 'stock':
            left, right = _nonzero_stock(left), _nonzero_stock(right)
        for item in sorted(set(left) | set(right), key=str):
            if left.get(item) != right.get(item):
                label = '/'.join(item) if isinstance(item, tuple) else item
                rpt.fail('PERIOD-CONTINUITY', f'{key}:{label}',
                         f'declared opening {left.get(item)!r} differs from previous closing {right.get(item)!r}')
    return rpt.items


# ---------------------------------------------------------------- PO-CAUSALITY / terms

def _check_po(pack, start, min_lead, rpt):
    for row in pack.get('po_headers', []):
        po = row['po_number']
        order, arrival = _date(row['order_date']), _date(row['arrival_maumbi_date'])
        if not order or not arrival:
            continue
        if arrival < order:
            rpt.fail('PO-CAUSALITY', po, f'arrival {arrival} before order {order}')
            continue
        if order < start:
            continue  # PO yang dipesan sebelum pack = in-transit pada pembukaan
        trigger = _date(row.get('rop_trigger_date', ''))
        if trigger is None:
            rpt.fail('PO-CAUSALITY', po, 'rop_trigger_date missing: a purchase must be triggered by reorder point')
        elif trigger > order:
            rpt.fail('PO-CAUSALITY', po, f'trigger {trigger} after order {order}')
        elif not calendar.is_working_day(trigger):
            rpt.fail('PO-CAUSALITY', po, f'trigger {trigger} is not a working day')
        try:
            cover = _dec(row.get('rop_cover_days', ''))
            if cover <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            rpt.fail('PO-CAUSALITY', po, 'rop_cover_days must be a positive number')
        principal = row['principal_code']
        if principal not in min_lead:
            rpt.fail('PO-CAUSALITY', po, f'no minimum lead-time parameter for {principal}')
        elif (arrival - order).days < int(min_lead[principal]):
            rpt.fail('PO-CAUSALITY', po, f'lead time {(arrival - order).days} days < minimum {min_lead[principal]}')


def _term(value):
    term = _dec(value)
    return int(term) if _whole(term) and term >= 0 else None


def _check_terms(pack, opening, rpt):
    invoices = dict(opening.get('open_invoices', {}))
    invoices.update(opening.get('carry_invoices', {}))
    for row in pack.get('invoices', []):
        invoices[row['invoice_number']] = row['date_invoice']
        term, date, due = _term(row['payment_term_days']), _date(row['date_invoice']), _date(row['due_date'])
        if term is None:
            rpt.fail('AR-TERMS', row['invoice_number'], 'payment_term_days must be a non-negative whole number')
        elif date and (due is None or due != date + dt.timedelta(days=term)):
            rpt.fail('AR-TERMS', row['invoice_number'], f'due_date {row["due_date"]} != invoice date + {term} days')
    counts = {}
    for row in pack.get('ar_collections', []):
        invoice = row['invoice_number']
        counts[invoice] = counts.get(invoice, 0) + 1
        if invoice not in invoices:
            rpt.fail('AR-TERMS', row['payment_id'], f'payment for unknown invoice {invoice}')
        elif _date(row['payment_date']) and _date(invoices[invoice]) and _date(row['payment_date']) < _date(invoices[invoice]):
            rpt.fail('AR-TERMS', row['payment_id'], f'payment {row["payment_date"]} before invoice {invoices[invoice]}')
    for invoice in sorted(n for n, c in counts.items() if c > 1):
        rpt.fail('AR-TERMS', invoice, 'invoice has more than one payment (partial payment needs a schema extension)')
    arrivals = dict(opening.get('open_po', {}))
    arrivals.update(opening.get('in_transit', {}))
    for row in pack.get('po_headers', []):
        arrivals[row['po_number']] = row['arrival_maumbi_date']
        term, arrival, due = _term(row['payment_term_days']), _date(row['arrival_maumbi_date']), _date(row['due_date'])
        if term is None:
            rpt.fail('AP-TERMS', row['po_number'], 'payment_term_days must be a non-negative whole number')
        elif arrival and (due is None or due != arrival + dt.timedelta(days=term)):
            rpt.fail('AP-TERMS', row['po_number'], f'due_date {row["due_date"]} != arrival + {term} days')
    for row in pack.get('ap_payments', []):
        po = row['po_number']
        if po not in arrivals:
            rpt.fail('AP-TERMS', row['ap_payment_id'], f'payment for unknown PO {po}')
        elif _date(row['payment_date']) and _date(arrivals[po]) and _date(row['payment_date']) < _date(arrivals[po]):
            rpt.fail('AP-TERMS', row['ap_payment_id'], f'payment {row["payment_date"]} before receipt {arrivals[po]}')


# ---------------------------------------------------------------- TAX-SOURCE

def _check_tax(pack, config, rpt):
    tax = config.get('tax') or {}
    rate = None
    try:
        rate = _dec(tax.get('rate'))
        if not 0 < rate < 1:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        rpt.fail('TAX-SOURCE', 'config.tax.rate', 'tax rate missing or invalid')
    if not str(tax.get('source', '')).strip():
        rpt.fail('TAX-SOURCE', 'config.tax.source', 'official source reference required')
    if _date(tax.get('source_date')) is None:
        rpt.fail('TAX-SOURCE', 'config.tax.source_date', 'dated source required (ISO date)')
    effective = _date(tax.get('effective_from'))
    if effective is None:
        rpt.fail('TAX-SOURCE', 'config.tax.effective_from', 'effective date required (ISO date)')
    if rate is None:
        return
    for row in pack.get('invoices', []):
        number, dpp, ppn, total = row['invoice_number'], _dec(row['dpp_amount']), _dec(_ppn(row)), _dec(row['total_invoice_with_ppn'])
        date = _date(row['date_invoice'])
        if effective and date and date < effective:
            rpt.fail('TAX-SOURCE', number, f'invoice {date} before tax effective date {effective}')
        if abs(ppn - (dpp * rate).quantize(TOLERANCE, ROUND_HALF_UP)) > TOLERANCE:
            rpt.fail('TAX-SOURCE', number, f'PPN {ppn} != DPP {dpp} x {rate}')
        if abs(total - (dpp + ppn)) > TOLERANCE:
            rpt.fail('TAX-SOURCE', number, f'total {total} != DPP + PPN {dpp + ppn}')


# ---------------------------------------------------------------- CASH-NONNEG

def _daily_cash(pack):
    flows = {}
    for row in pack.get('ar_collections', []):
        flows[row['payment_date']] = flows.get(row['payment_date'], ZERO) + _dec(row['net_cash_collected_total'])
    for row in pack.get('ap_payments', []):
        flows[row['payment_date']] = flows.get(row['payment_date'], ZERO) - _dec(row['amount_paid_dpp'])
    for row in pack.get('opex', []):
        flows[row['date']] = flows.get(row['date'], ZERO) - _dec(row['amount'])
    return sorted(flows.items())


def minimum_cash_balance(pack, opening_cash):
    """(saldo penutupan harian terendah, tanggal). Kas masuk AR basis total termasuk PPN; AP basis DPP (gap G-07)."""
    balance, lowest = Decimal(opening_cash), (Decimal(opening_cash), None)
    for date, flow in _daily_cash(pack):
        balance += flow
        if balance < lowest[0]:
            lowest = (balance, date)
    return lowest


def _check_cash(pack, opening_cash, rpt):
    balance, negative, lowest = Decimal(opening_cash), 0, (Decimal(opening_cash), None)
    for date, flow in _daily_cash(pack):
        balance += flow
        if balance < 0:
            negative += 1
        if balance < lowest[0]:
            lowest = (balance, date)
    if negative:
        rpt.fail('CASH-NONNEG', lowest[1], f'closing cash negative on {negative} day(s); minimum {lowest[0]}')


# ---------------------------------------------------------------- NARRATIVE-ANCHORS

def _check_anchors(pack, bands, rpt):
    gross = sum((_dec(r['gross_dpp']) for r in pack['sales_orders']), ZERO)
    metrics = {
        'net_dpp': sum((_dec(r['net_dpp']) for r in pack['sales_orders']), ZERO),
        'active_outlets': Decimal(len({r['customer'].split(' - ')[0] for r in pack['sales_orders']})),
    }
    if gross > 0:
        metrics['discount_pct'] = sum((_dec(r['discount_dpp']) for r in pack['sales_orders']), ZERO) / gross * 100
        metrics['rejection_pct'] = sum((_dec(r['rejection_dpp']) for r in pack['deliveries']), ZERO) / gross * 100
    for name in sorted(bands):
        if name not in ANCHOR_METRICS:
            rpt.fail('NARRATIVE-ANCHORS', name, f'unknown metric; allowed {ANCHOR_METRICS}')
            continue
        try:
            low, high = (_dec(x) for x in bands[name])
            if low > high:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            rpt.fail('NARRATIVE-ANCHORS', name, f'invalid band {bands[name]!r}')
            continue
        if name not in metrics:
            rpt.fail('NARRATIVE-ANCHORS', name, 'metric cannot be computed (zero gross sales)')
        elif not low <= metrics[name] <= high:
            rpt.fail('NARRATIVE-ANCHORS', name, f'observed {metrics[name].quantize(TOLERANCE)} outside [{low}, {high}]')


# ---------------------------------------------------------------- orkestrasi

def validate_pack_report(pack, *, opening, config, existing_numbers=(), previous_closing=None, bands=None,
                         strict=False):
    """-> {'violations', 'gates_run', 'gates_skipped'}. strict=True: gate yang terlewat menjadi pelanggaran."""
    rpt = _Report()
    _check_schema(pack, rpt)
    run = ['INPUT-SCHEMA']
    if rpt.items:
        return {'violations': rpt.items, 'gates_run': run, 'gates_skipped': []}
    window = _window(config, rpt)
    if window is None:
        return {'violations': rpt.items, 'gates_run': run, 'gates_skipped': []}
    start, end = window
    core = (
        ('CALENDAR-OFFICIAL', lambda: _check_calendar(pack, rpt)),
        ('PERIOD-WINDOW', lambda: _check_window(pack, start, end, rpt)),
        ('NUMBERING', lambda: _check_numbering(pack, existing_numbers, rpt)),
        ('STOCK-NONNEG', lambda: _check_stock(pack, opening.get('stock', {}), rpt)),
        ('PO-CAUSALITY', lambda: _check_po(pack, start, config.get('min_lead_days') or {}, rpt)),
        ('AR-TERMS/AP-TERMS', lambda: _check_terms(pack, opening, rpt)),
        ('TAX-SOURCE', lambda: _check_tax(pack, config, rpt)),
    )
    for name, action in core:
        action()
        run.append(name)
    skipped = []
    if 'opening_cash' in config:
        try:
            _check_cash(pack, _dec(config['opening_cash']), rpt)
        except (InvalidOperation, ValueError):
            rpt.fail('CASH-NONNEG', 'config.opening_cash', 'opening cash invalid')
        run.append('CASH-NONNEG')
    else:
        skipped.append(('CASH-NONNEG', 'config.opening_cash belum ditetapkan'))
    if bands is not None:
        _check_anchors(pack, bands, rpt)
        run.append('NARRATIVE-ANCHORS')
    else:
        skipped.append(('NARRATIVE-ANCHORS', 'bands belum diberikan'))
    if previous_closing is not None:
        rpt.items.extend(check_continuity(copy.deepcopy(opening), previous_closing))
        run.append('PERIOD-CONTINUITY')
    else:
        skipped.append(('PERIOD-CONTINUITY', 'previous_closing belum diberikan'))
    if strict:
        for name, reason in skipped:
            rpt.fail(name, 'gate', f'tidak dijalankan: {reason}')
    return {'violations': rpt.items, 'gates_run': run, 'gates_skipped': [name for name, _ in skipped]}


def validate_pack(pack, **kwargs):
    return validate_pack_report(pack, **kwargs)['violations']
