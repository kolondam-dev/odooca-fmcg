/** @odoo-module **/
import { Component, onWillStart, onWillDestroy, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const NF = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function money(n, currency = "IDR") {
    const prefix = currency === "IDR" ? "Rp" : currency;
    if (n === null || n === undefined) return "—";
    return `${prefix} ${NF.format(Math.round(n))}`;
}

function moneyShort(n, currency = "IDR") {
    const prefix = currency === "IDR" ? "Rp" : currency;
    if (n === null || n === undefined) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e9) {
        return `${prefix} ${NF1.format(n / 1e9)} M`;
    }
    if (abs >= 1e6) {
        return `${prefix} ${NF1.format(n / 1e6)} jt`;
    }
    if (abs >= 1e3) {
        return `${prefix} ${NF.format(Math.round(n / 1e3))} rb`;
    }
    return `${prefix} ${NF.format(Math.round(n))}`;
}

function pct(n) {
    if (n === null || n === undefined) return "—";
    return `${NF1.format(n)}%`;
}

export class WmsDashboard extends Component {
    static template = "id_dashboard_wms.WmsDashboard";
    static props = ["*"];

    setup() {
        const releaseWorkspace = this.env.services.id_shell?.enterDashboard?.();
        this.requestVersion = 0;
        onWillDestroy(() => { this.requestVersion++; releaseWorkspace?.(); });
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            fmcgCategory: "",
            vehicleId: null,
            cohortStart: "", cohortEnd: "",
            filters: { categories: [], vehicles: [] },
            data: null,
            activeTab: "expiry", // 'expiry', 'rejections', 'categories', 'fleet'
        });

        onWillStart(async () => {
            try {
                this.state.filters = await this.orm.call("id.wms.dashboard", "get_filters", []);
                await this.load();
            } catch (err) {
                this.state.error = err?.data?.message || err?.message || String(err);
                this.state.loading = false;
            }
        });
    }

    async load() {
        const version = ++this.requestVersion;
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call("id.wms.dashboard", "get_data", [], {
                fmcg_category: this.state.fmcgCategory || false,
                vehicle_id: this.state.vehicleId || false,
                cohort_start: this.state.cohortStart || null, cohort_end: this.state.cohortEnd || null,
            });
            if (version === this.requestVersion) this.state.data = data;
        } catch (err) {
            if (version === this.requestVersion) { this.state.data = null; this.state.error = err?.data?.message || err?.message || String(err); }
        } finally {
            if (version === this.requestVersion) this.state.loading = false;
        }
    }

    onCohortDate(ev) { this.state[ev.target.dataset.field] = ev.target.value; this.load(); }
    physical(v) {
        if (v === null || v === undefined) return "—";
        if (v > 0 && v < 0.0001) return "<0,0001";
        return new Intl.NumberFormat("id-ID", {maximumFractionDigits: 4}).format(v);
    }
    assetMoney(v) {
        if (v === null || v === undefined) return "—";
        const c = this.state.data?.currency || "IDR", digits = this.state.data?.currency_digits ?? 2;
        return `${c === "IDR" ? "Rp" : c} ${new Intl.NumberFormat("id-ID", {
            minimumFractionDigits: digits, maximumFractionDigits: digits}).format(v)}`;
    }
    openAssetTrip(id) {
        if (this.state.loading || !this.state.data?.assets) return;
        this.action.doAction({type: "ir.actions.act_window", name: _t("Load and Trip Records"),
            res_model: "id.asset.trip", views: id ? [[false, "form"]] : [[false, "list"], [false, "form"]],
            ...(id ? {res_id: id} : {domain: this.state.data.assets.trip_domain})});
    }
    openAssetQuants(row) {
        if (this.state.loading || !this.state.data?.assets) return;
        this.action.doAction({type: "ir.actions.act_window", name: _t("Physical stock positions"),
            res_model: "stock.quant", views: [[false, "list"]], domain: row.domain});
    }
    openAssetCapacity() {
        if (!this.state.loading) this.action.doAction("id_dashboard_wms.action_asset_warehouses");
    }
    openCohort() {
        if (this.state.loading || !this.state.data?.cohort) return;
        this.action.doAction({type: "ir.actions.act_window", name: _t("Delivery cohort source"),
            res_model: "stock.picking", views: [[false, "list"], [false, "form"]],
            domain: [["id", "in", this.state.data.cohort.source_ids]]});
    }
    cohortReason(key) {
        return {store_closed: _t("Store closed / delivery refused"), packaging_damaged: _t("Packaging damaged"),
            near_expiry: _t("Near expiry"), wrong_sku_qty: _t("Wrong SKU or quantity")}[key] || _t("Not recorded");
    }
    hours(value) { return value === null || value === undefined ? "—" : NF1.format(value); }

    onCategoryChange(ev) {
        this.state.fmcgCategory = ev.target.value;
        this.load();
    }

    onVehicleChange(ev) {
        this.state.vehicleId = ev.target.value ? parseInt(ev.target.value) : null;
        this.load();
    }

    reset() {
        this.state.fmcgCategory = "";
        this.state.vehicleId = null;
        this.load();
    }

    get totalRejections() {
        if (this.state.data?.kpi?.total_rejections !== undefined) {
            return this.state.data.kpi.total_rejections;
        }
        return (this.state.data?.rejections || []).reduce((sum, r) => sum + (r.count || 0), 0);
    }

    // Formatting helpers
    money(v) { return money(v, this.state.data?.currency); }
    moneyShort(v) { return moneyShort(v, this.state.data?.currency); }
    pct(v) { return pct(v); }
    int(v) { return NF.format(v || 0); }

    // Drilldowns
    openCriticalStock() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type: "ir.actions.act_window", name: _t("Critical expiry lots"),
            res_model: "id.wms.expiry", views: [[false, "list"], [false, "form"]],
            domain: [...this.state.data.domains.expiry, ["bucket", "=", "critical"]]});
    }

    openExpiryMatrix() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window",name:_t("Dashboard Details"),res_model:"id.wms.expiry",views:[[false,"list"],[false,"form"]],domain:this.state.data.domains.expiry});
    }

    openDeliveryFulfillment() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window",name:_t("Dashboard Details"),res_model:"id.wms.delivery",views:[[false,"list"],[false,"form"]],domain:this.state.data.domains.deliveries});
    }

    openRejectAnalysis() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window",name:_t("Dashboard Details"),res_model:"id.wms.delivery",views:[[false,"list"],[false,"form"]],domain:this.state.data.domains.rejections});
    }

    openFleetCostAnalysis() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window",name:_t("Dashboard Details"),res_model:"id.wms.fleet.cost",views:[[false,"list"],[false,"form"]],domain:this.state.data.domains.fleet});
    }

    openStockCategories() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window",name:_t("Dashboard Details"),res_model:"id.wms.stock.category",views:[[false,"list"],[false,"form"]],domain:this.state.data.domains.stock});
    }
}

registry.category("actions").add("id_dashboard_wms.wms_dashboard", WmsDashboard);

