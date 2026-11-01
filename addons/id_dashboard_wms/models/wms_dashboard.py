# Part of odooca-fmcg. License LGPL-3.
"""Aggregation service for the Warehouse & Logistics (WMS) Executive Dashboard."""

from odoo import _, api, models
from odoo.exceptions import AccessError

REJECT_LABELS = {
    "packaging_damaged": _("Kemasan Basah / Rusak di Perjalanan"),
    "near_expiry": _("Produk Mendekati Kadaluwarsa"),
    "wrong_sku_qty": _("Salah SKU / Kuantitas Tidak Sesuai"),
    "store_closed": _("Toko Tutup / Tolak Surat Jalan"),
    "not_recorded": _("Belum Dicatat / Lainnya"),
}


class WmsDashboard(models.AbstractModel):
    _name = "id.wms.dashboard"
    _description = "Warehouse & Logistics Executive Dashboard Service"

    @api.model
    def _check_access(self):
        user = self.env.user
        if not (user.has_group("stock.group_stock_user")
                or user.has_group("sales_team.group_sale_salesman")
                or user.has_group("base.group_system")):
            raise AccessError(_("Akses dashboard WMS memerlukan hak akses Gudang atau Penjualan."))

    @api.model
    def get_filters(self):
        self._check_access()
        # FMCG Categories from product template selection
        cat_field = self.env["product.template"]._fields.get("fmcg_category")
        categories = []
        if cat_field and hasattr(cat_field, "selection"):
            selection = cat_field.selection
            if callable(selection):
                selection = selection(self.env["product.template"])
            categories = [{"key": k, "label": label} for k, label in selection]

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
    def get_data(self, fmcg_category=None, vehicle_id=None):
        self._check_access()
        company_ids = self.env.companies.ids

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
            ["picking_name", "partner_id", "is_delivered", "is_late", "reject_reason", "delivered_value"]
        )

        total_deliveries = len(deliv_recs)
        delivered_count = sum(1 for d in deliv_recs if d["is_delivered"])
        late_count = sum(1 for d in deliv_recs if d["is_late"])
        delivered_value = sum(float(d["delivered_value"] or 0.0) for d in deliv_recs if d["is_delivered"])

        fulfillment_rate = (delivered_count / total_deliveries * 100.0) if total_deliveries > 0 else 100.0

        # Rejection breakdown
        RejectModel = self.env["id.wms.reject"]
        reject_recs = RejectModel.search_read(
            [("company_id", "in", company_ids)],
            ["reject_reason", "rejection_count", "rejection_share_percent"]
        )

        total_rejections = sum(r["rejection_count"] for r in reject_recs if r["reject_reason"] != "not_recorded")
        rejection_rate = (total_rejections / total_deliveries * 100.0) if total_deliveries > 0 else 0.0

        reject_list = []
        for r in reject_recs:
            reason = r["reject_reason"]
            reject_list.append({
                "reason": reason,
                "label": REJECT_LABELS.get(reason, reason),
                "count": r["rejection_count"],
                "share": float(r["rejection_share_percent"] or 0.0),
            })
        reject_list.sort(key=lambda x: x["count"], reverse=True)

        # ----------------------------------------------------------- 4. Fleet Efficiency
        fleet_domain = [("company_id", "in", company_ids)]
        if vehicle_id:
            fleet_domain.append(("vehicle_id", "=", int(vehicle_id)))

        FleetCostModel = self.env["id.wms.fleet.cost"]
        fleet_recs = FleetCostModel.search_read(
            fleet_domain,
            ["vehicle_id", "period_month", "total_cost", "total_delivered_value", "cost_ratio_percent"]
        )

        total_trip_cost = sum(float(f["total_cost"] or 0.0) for f in fleet_recs)
        total_fleet_delivered = sum(float(f["total_delivered_value"] or 0.0) for f in fleet_recs)
        fleet_ratio = (total_trip_cost / total_fleet_delivered * 100.0) if total_fleet_delivered > 0 else 0.0

        fleet_list = []
        for f in fleet_recs:
            fleet_list.append({
                "vehicle": f["vehicle_id"][1] if f["vehicle_id"] else "-",
                "month": f["period_month"] or "-",
                "cost": float(f["total_cost"] or 0.0),
                "delivered_value": float(f["total_delivered_value"] or 0.0),
                "ratio": float(f["cost_ratio_percent"] or 0.0),
            })

        return {
            "kpi": {
                "total_stock_value": total_stock_value,
                "total_stock_qty": total_stock_qty,
                "critical_expiry_val": critical_val,
                "critical_expiry_count": critical_count,
                "total_deliveries": total_deliveries,
                "delivered_count": delivered_count,
                "delivered_value": delivered_value,
                "fulfillment_rate": fulfillment_rate,
                "late_count": late_count,
                "total_rejections": total_rejections,
                "rejection_rate": rejection_rate,
                "total_trip_cost": total_trip_cost,
                "fleet_cost_ratio": fleet_ratio,
            },
            "expiry_buckets": expiry_buckets,
            "rejections": reject_list,
            "categories": cat_list,
            "fleet": fleet_list,
        }

