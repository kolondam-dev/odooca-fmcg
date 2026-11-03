"""Redacted, read-only accepted POD projection. No media/recipient/raw payload exposure."""
from collections import Counter, defaultdict
import json

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from .delivery_cohort import local_day

SQL = """
CREATE VIEW id_delivery_attempt AS (
 WITH decoded AS (
  SELECT c.*, CASE WHEN pg_input_is_valid(c.payload_json,'jsonb') THEN c.payload_json::jsonb ELSE '{}'::jsonb END j
  FROM id_mobile_command c WHERE c.status='accepted'
    AND c.command_type IN ('delivery.pod.submit','delivery.proof.submit')
 ), parsed AS (
  SELECT d.*, CASE WHEN jsonb_typeof(j->'payload')='object' THEN j->'payload' ELSE j END p FROM decoded d
 )
 SELECT d.id, d.id AS command_id, d.company_id, d.user_id AS driver_id, d.client_uuid,
        COALESCE(d.occurred_at,d.create_date) AS accepted_at, sp.id AS picking_id,
        (sp.id IS NOT NULL) AS binding_valid,
        CASE WHEN d.p->>'outcome' IN ('delivered','partial','rejected','cancel_delivery','pending_requested')
             THEN d.p->>'outcome' ELSE 'unclassified' END AS outcome,
        COALESCE(d.p->>'supersedes_uuid','') AS supersedes_uuid,
        COALESCE(d.p#>>'{source,version}','') AS source_version,
        CASE WHEN d.p->>'do_reason' IN ('TOKO TUTUP','TOKO TIDAK PUNYA UANG','TOKO TIDAK DAPAT DIAKSES',
          'TOKO TIDAK ORDER','ORDER MELEBIHI KEMAMPUAN TOKO','SKU TIDAK SESUAI ORDER','REQUEST PENDING KIRIM')
          THEN d.p->>'do_reason' ELSE 'not_recorded' END AS do_reason,
        COALESCE((SELECT jsonb_agg(x->>'item_reason') FROM jsonb_array_elements(
         CASE WHEN jsonb_typeof(d.p->'lines')='array' THEN d.p->'lines' ELSE '[]'::jsonb END) x
         WHERE x->>'item_reason' IN ('ITEM RUSAK','ITEM EXPIRED','SALAH SKU','QTY TERLALU BANYAK')),'[]'::jsonb)::text
         AS item_reasons_json
 FROM parsed d LEFT JOIN stock_picking sp ON sp.company_id=d.company_id
  AND sp.name=COALESCE(d.p#>>'{source,id}',d.p->>'do_id')
  AND sp.origin=COALESCE(d.p#>>'{source,trip}',d.p->>'trip_id',d.p->>'manifest_id')
  AND sp.partner_id::text=COALESCE(d.p#>>'{source,outlet_id}',d.p->>'outlet_id',sp.partner_id::text)
  AND (d.p#>>'{source,business_date}' IS NULL OR d.p#>>'{source,business_date}'=
       to_char(COALESCE(d.occurred_at,d.create_date) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Makassar','YYYY-MM-DD'))
  AND sp.picking_type_id IN (SELECT id FROM stock_picking_type WHERE code='outgoing')
)
"""


class DeliveryAttempt(models.Model):
    _name = "id.delivery.attempt"
    _description = "Accepted POD Event (Redacted)"
    _auto = False
    _rec_name = "client_uuid"
    _order = "accepted_at, id"

    command_id = fields.Integer(readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    driver_id = fields.Many2one("res.users", readonly=True)
    client_uuid = fields.Char(readonly=True)
    accepted_at = fields.Datetime(readonly=True)
    picking_id = fields.Many2one("stock.picking", readonly=True)
    binding_valid = fields.Boolean(readonly=True)
    outcome = fields.Char(readonly=True)
    supersedes_uuid = fields.Char(readonly=True)
    source_version = fields.Char(readonly=True)
    do_reason = fields.Char(readonly=True)
    item_reasons_json = fields.Text(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL)

    @api.model
    def _for_deliveries(self, picking_ids):
        domain = [("company_id", "in", self.env.companies.ids), ("picking_id", "in", picking_ids)]
        if self.search_count(domain, limit=50001) > 50000:
            raise UserError(_("Too many POD events; narrow the delivery cohort."))
        events = self.search(domain)
        by_key = {(e.company_id.id, e.driver_id.id, e.client_uuid): e for e in events}
        children, bad = defaultdict(list), set()
        for event in events:
            if not event.supersedes_uuid:
                continue
            parent = by_key.get((event.company_id.id, event.driver_id.id, event.supersedes_uuid))
            if (not parent or parent.picking_id != event.picking_id or parent.source_version != event.source_version
                    or local_day(parent.accepted_at) != local_day(event.accepted_at)
                    or (parent.accepted_at, parent.id) >= (
                    event.accepted_at, event.id)):
                bad.add(event.id)
            else:
                children[parent.id].append(event)
        for parent, values in children.items():
            if len(values) > 1:
                bad.add(parent)
                bad.update(v.id for v in values)
        outcomes, do_reasons, item_reasons = Counter(), Counter(), Counter()
        first, leaves, invalid = {}, [], 0
        for event in events:
            if event.supersedes_uuid:
                continue
            node, seen = event, set()
            while node.id not in bad and len(children[node.id]) == 1 and node.id not in seen:
                seen.add(node.id)
                node = children[node.id][0]
            if node.id in bad or node.id in seen:
                invalid += 1
                continue
            first[event.picking_id.id] = min(first.get(event.picking_id.id, event.accepted_at), event.accepted_at)
            leaves.append(node)
            outcomes[node.outcome] += 1
            do_reasons[node.do_reason] += 1
            item_reasons.update(json.loads(node.item_reasons_json))
        invalid += sum(e.id in bad and bool(e.supersedes_uuid) for e in events)
        return {"domain": domain, "source_events": len(events), "attempts": len(leaves),
                "observed_deliveries": len(first), "delivery_documents": len(set(picking_ids)),
                "corrections": len(events)-len([e for e in events if not e.supersedes_uuid]),
                "invalid_lineage": invalid, "outcomes": dict(outcomes), "do_reasons": dict(do_reasons),
                "item_reasons": dict(item_reasons),
                "first_events": [{"picking_id": k, "accepted_at": str(v)} for k, v in sorted(first.items())]}
