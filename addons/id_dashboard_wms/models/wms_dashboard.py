# Part of odooca-fmcg. License LGPL-3.
"""WMS & Logistics Executive Dashboard aggregator service."""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

REJECT_LABELS = {
    "not_recorded": _("Tidak tercatat"),
    "store_closed": _("Toko tutup / menolak surat jalan"),
    "packaging_damaged": _("Kemasan rusak dalam perjalanan"),
    "near_expiry": _("Mendekati kedaluwarsa"),
    "wrong_sku_qty": _("SKU atau kuantitas tidak sesuai"),
}


class WmsDashboard(models.TransientModel):
    _name = "id.wms.dashboard"
    _description = "WMS & Logistics Dashboard Service"

    name = fields.Char(default="WMS Dashboard Service", readonly=True)

    def _check_access(self):
        user = self.env.user
        if not (
            user.has_group("stock.group_stock_user")
            or user.has_group("stock.group_stock_manager")
            or user.has_group("base.group_system")
        ):
            raise AccessError(_("Anda tidak memiliki izin untuk melihat Dashboard Logistik & Gudang."))

    @api.model
    def get_filters(self):
        self._check_access()
        # FMCG Categories
        categories = []
        if "id.wms.stock.category" in self.env:
            cat_groups = self.env["id.wms.stock.category"].read_group(
                [], ["fmcg_category"], ["fmcg_category"]
            )
            for cg in cat_groups:
                c_val = cg.get("fmcg_category")
                if c_val:
                    categories.append({"id": c_val, "name": c_val})

        # Fleet vehicles
        vehicles = []
        if "fleet.vehicle" in self.env:
            v_recs = self.env["fleet.vehicle"].search_read([], ["id", "name", "license_plate"], order="name")
            for v in v_recs:
                name = v.get("license_plate") or v.get("name")
                vehicles.append({"id": v["id"], "name": name})

        return {
            "categories": categories,
            "vehicles": vehicles,
        }

    @api.model
    def get_data(self, fmcg_category=None, vehicle_id=None, **kwargs):
        self._check_access()
        company_ids = self.env.companies.ids
        if len(self.env.companies.currency_id) != 1:
            raise UserError(_("Select companies with the same currency before aggregating monetary values."))

        # ----------------------------------------------------------- 1. Stock by FMCG Category
        cat_domain = [("company_id", "in", company_ids)]
        if fmcg_category:
            cat_domain.append(("fmcg_category", "=", fmcg_category))

        CategoryModel = self.env["id.wms.stock.category"]
        category_recs = CategoryModel.search_read(
            cat_domain,
            ["fmcg_category", "qty_on_hand", "stock_value", "product_count"]
        )

        total_stock_value = sum(float(r["stock_value"] or 0.0) for r in category_recs)
        total_stock_qty = sum(float(r["qty_on_hand"] or 0.0) for r in category_recs)

        cat_list = []
        for r in category_recs:
            val = float(r["stock_value"] or 0.0)
            cat_list.append({
                "category": r["fmcg_category"] or _("Lainnya"),
                "product_count": r["product_count"],
                "qty": float(r["qty_on_hand"] or 0.0),
                "value": val,
                "share": (val / total_stock_value * 100.0) if total_stock_value > 0 else 0.0,
            })
        cat_list.sort(key=lambda x: x["value"], reverse=True)

        # ----------------------------------------------------------- 2. FEFO Expiry
        expiry_domain = [("company_id", "in", company_ids)]
        if fmcg_category:
            expiry_domain.append(("fmcg_category", "=", fmcg_category))

        ExpiryModel = self.env["id.wms.expiry"]
        expiry_recs = ExpiryModel.search_read(
            expiry_domain,
            ["bucket", "days_to_expiry", "stock_value", "qty_on_hand", "lot_name", "product_id"]
        )

        critical_val = 0.0
        critical_count = 0
        warning_val = 0.0
        warning_count = 0
        good_val = 0.0
        good_count = 0

        for r in expiry_recs:
            val = float(r["stock_value"] or 0.0)
            b = r["bucket"]
            if b == "critical":
                critical_val += val
                critical_count += 1
            elif b == "warning":
                warning_val += val
                warning_count += 1
            else:
                good_val += val
                good_count += 1

        total_fefo_val = critical_val + warning_val + good_val
        expiry_buckets = [
            {
                "key": "critical",
                "label": _("Kritis (< 30 Hari) - Retur Principal"),
                "value": critical_val,
                "count": critical_count,
                "share": (critical_val / total_fefo_val * 100.0) if total_fefo_val > 0 else 0.0,
            },
            {
                "key": "warning",
                "label": _("Waspada (30–90 Hari) - Bundling / Promo"),
                "value": warning_val,
                "count": warning_count,
                "share": (warning_val / total_fefo_val * 100.0) if total_fefo_val > 0 else 0.0,
            },
            {
                "key": "good",
                "label": _("Aman (> 90 Hari) - Rotasi Normal"),
                "value": good_val,
                "count": good_count,
                "share": (good_val / total_fefo_val * 100.0) if total_fefo_val > 0 else 0.0,
            },
        ]

        # ----------------------------------------------------------- 3. Delivery & Fulfillment
        deliv_domain = [("company_id", "in", company_ids)]
        if vehicle_id:
            deliv_domain.append(("vehicle_id", "=", int(vehicle_id)))

        DeliveryModel = self.env["id.wms.delivery"]
        deliv_recs = DeliveryModel.search_read(
            deliv_domain,
            ["picking_name", "partner_id", "state", "is_delivered", "is_late", "reject_reason", "delivered_value"]
        )

        total_deliveries = len(deliv_recs)
        delivered_count = sum(1 for d in deliv_recs if d["is_delivered"])
        late_count = sum(1 for d in deliv_recs if d["is_late"])
        delivered_value = sum(float(d["delivered_value"] or 0.0) for d in deliv_recs if d["is_delivered"])

        fulfillment_rate = (delivered_count / total_deliveries * 100.0) if total_deliveries > 0 else None

        # Use the filtered DO population for BOTH numerator and denominator.
        reject_groups = {}
        for delivery in deliv_recs:
            reason = delivery["reject_reason"] or "not_recorded"
            if reason != "not_recorded" or delivery["state"] == "cancel":
                reject_groups[reason] = reject_groups.get(reason, 0) + 1
        reject_recs = [{"reason": reason, "picking_count": count} for reason, count in reject_groups.items()]

        total_rejections = sum(r["picking_count"] for r in reject_recs)
        rejection_rate = (total_rejections / total_deliveries * 100.0) if total_deliveries > 0 else None

        reject_list = []
        for r in reject_recs:
            reason = r["reason"]
            count = r["picking_count"]
            share = (count / total_rejections * 100.0) if total_rejections > 0 else 0.0
            reject_list.append({
                "reason": reason,
                "label": REJECT_LABELS.get(reason, reason),
                "count": count,
                "share": round(share, 1),
            })
        reject_list.sort(key=lambda x: x["count"], reverse=True)

        # ----------------------------------------------------------- 4. Fleet Efficiency
        fleet_domain = [("company_id", "in", company_ids)]
        if vehicle_id:
            fleet_domain.append(("vehicle_id", "=", int(vehicle_id)))

        FleetCostModel = self.env["id.wms.fleet.cost"]
        fleet_recs = FleetCostModel.search_read(
            fleet_domain,
            ["id", "vehicle_id", "period_month", "fuel_cost", "helper_cost", "total_cost", "delivered_value"]
        )

        total_fleet_cost = sum(float(r["total_cost"] or 0.0) for r in fleet_recs)
        fleet_ratio = (total_fleet_cost / delivered_value * 100.0) if delivered_value > 0 and fleet_recs else None

        fleet_list = []
        for r in fleet_recs:
            veh = r["vehicle_id"]
            delivered = float(r["delivered_value"] or 0.0)
            tcost = float(r["total_cost"] or 0.0)
            ratio = (tcost / delivered * 100.0) if delivered > 0 else None
            fleet_list.append({
                "key": r["id"],
                "period_month": str(r["period_month"]),
                "vehicle_id": veh[0] if veh else 0,
                "name": veh[1] if veh else "-",
                "fuel_cost": float(r["fuel_cost"] or 0.0),
                "helper_cost": float(r["helper_cost"] or 0.0),
                "total_cost": tcost,
                "delivered_value": delivered,
                "cost_ratio": round(ratio, 2) if ratio is not None else None,
            })
        fleet_list.sort(key=lambda x: x["cost_ratio"] if x["cost_ratio"] is not None else -1, reverse=True)

        return {
            "currency": self.env.company.currency_id.name,
            "domains": {"stock": cat_domain, "expiry": expiry_domain, "deliveries": deliv_domain,
                        "fleet": fleet_domain, "rejections": deliv_domain +
                        ["|", ("reject_reason", "!=", "not_recorded"), ("state", "=", "cancel")]},
            "kpi": {
                "total_stock_value": total_stock_value,
                "total_stock_qty": total_stock_qty,
                "critical_stock_value": critical_val,
                "critical_stock_count": critical_count,
                "critical_stock_share": (critical_val / total_stock_value * 100.0) if total_stock_value > 0 else 0.0,
                "total_deliveries": total_deliveries,
                "delivered_count": delivered_count,
                "late_count": late_count,
                "total_rejections": total_rejections,
                "delivered_value": delivered_value,
                "fulfillment_rate": round(fulfillment_rate, 1) if fulfillment_rate is not None else None,
                "rejection_rate": round(rejection_rate, 1) if rejection_rate is not None else None,
                "total_fleet_cost": total_fleet_cost,
                "fleet_cost_ratio": round(fleet_ratio, 2) if fleet_ratio is not None else None,
            },
            "expiry_buckets": expiry_buckets,
            "rejections": reject_list,
            "categories": cat_list,
            "fleet": fleet_list,
        }
