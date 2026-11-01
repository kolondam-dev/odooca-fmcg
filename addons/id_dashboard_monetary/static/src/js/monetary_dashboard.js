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

export class MonetaryDashboard extends Component {
    static template = "id_dashboard_monetary.MonetaryDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            areaIds: [],
            salesmanIds: [],
            filters: { areas: [], salesmen: [], today: null },
            data: null,
            subTab: "customers", // 'customers', 'areas', 'salesmen'
        });

        onWillStart(async () => {
            try {
                this.state.filters = await this.orm.call("id.monetary.dashboard", "get_filters", []);
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
            this.state.data = await this.orm.call("id.monetary.dashboard", "get_data", [], {
                area_ids: this.state.areaIds,
                salesman_ids: this.state.salesmanIds,
            });
        } catch (err) {
            this.state.error = err?.data?.message || err?.message || String(err);
        } finally {
            this.state.loading = false;
        }
    }

    toggleArea(id) {
        const idx = this.state.areaIds.indexOf(id);
        if (idx >= 0) {
            this.state.areaIds.splice(idx, 1);
        } else {
            this.state.areaIds.push(id);
        }
        this.load();
    }

    toggleSalesman(id) {
        const idx = this.state.salesmanIds.indexOf(id);
        if (idx >= 0) {
            this.state.salesmanIds.splice(idx, 1);
        } else {
            this.state.salesmanIds.push(id);
        }
        this.load();
    }

    reset() {
        this.state.areaIds = [];
        this.state.salesmanIds = [];
        this.load();
    }

    // Formatting helpers
    money(v) { return money(v); }
    moneyShort(v) { return moneyShort(v); }
    pct(v) { return pct(v); }
    int(v) { return NF.format(v || 0); }

    // Drilldowns
    openAgingMatrix() {
        this.action.doAction("id_dashboard_monetary.action_id_ar_aging");
    }

    openFunnel() {
        this.action.doAction("id_dashboard_monetary.action_id_monetary_funnel");
    }

    openOverdueInvoices() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Faktur Jatuh Tempo"),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: [["bucket", "!=", "not_due"]],
        });
    }

    openCustomerInvoices(partnerId, partnerName) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t(`Faktur Terbuka - ${partnerName}`),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: [["partner_id", "=", partnerId]],
        });
    }

    openAllInvoices() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Semua Piutang Terbuka"),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: [],
        });
    }
}

registry.category("actions").add("id_dashboard_monetary.monetary_dashboard", MonetaryDashboard);

