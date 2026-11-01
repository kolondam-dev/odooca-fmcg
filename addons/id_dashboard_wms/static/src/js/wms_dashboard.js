/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
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
        this.requestVersion = 0;
        onWillUnmount(() => { this.requestVersion++; });
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            fmcgCategory: "",
            vehicleId: null,
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
            });
            if (version === this.requestVersion) this.state.data = data;
        } catch (err) {
            if (version === this.requestVersion) { this.state.data = null; this.state.error = err?.data?.message || err?.message || String(err); }
        } finally {
            if (version === this.requestVersion) this.state.loading = false;
        }
    }

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

