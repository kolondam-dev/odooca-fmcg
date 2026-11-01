/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const NF = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function money(n) {
    if (n === null || n === undefined) return "Rp 0";
    return `Rp ${NF.format(Math.round(n))}`;
}

function moneyShort(n) {
    if (n === null || n === undefined) return "Rp 0";
    const abs = Math.abs(n);
    if (abs >= 1e9) {
        return `Rp ${NF1.format(n / 1e9)} M`;
    }
    if (abs >= 1e6) {
        return `Rp ${NF1.format(n / 1e6)} jt`;
    }
    if (abs >= 1e3) {
        return `Rp ${NF.format(Math.round(n / 1e3))} rb`;
    }
    return `Rp ${NF.format(Math.round(n))}`;
}

function pct(n) {
    if (n === null || n === undefined) return "0%";
    return `${NF1.format(n)}%`;
}

export class WmsDashboard extends Component {
    static template = "id_dashboard_wms.WmsDashboard";
    static props = ["*"];

    setup() {
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
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call("id.wms.dashboard", "get_data", [], {
                fmcg_category: this.state.fmcgCategory || false,
                vehicle_id: this.state.vehicleId || false,
            });
        } catch (err) {
            this.state.error = err?.data?.message || err?.message || String(err);
        } finally {
            this.state.loading = false;
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
    money(v) { return money(v); }
    moneyShort(v) { return moneyShort(v); }
    pct(v) { return pct(v); }
    int(v) { return NF.format(v || 0); }

    // Drilldowns
    openExpiryMatrix() {
        this.action.doAction("id_dashboard_wms.action_id_wms_expiry");
    }

    openDeliveryFulfillment() {
        this.action.doAction("id_dashboard_wms.action_id_wms_delivery");
    }

    openRejectAnalysis() {
        this.action.doAction("id_dashboard_wms.action_id_wms_reject");
    }

    openFleetCostAnalysis() {
        this.action.doAction("id_dashboard_wms.action_id_wms_fleet_cost");
    }

    openStockCategories() {
        this.action.doAction("id_dashboard_wms.action_id_wms_stock_category");
    }
}

registry.category("actions").add("id_dashboard_wms.wms_dashboard", WmsDashboard);

