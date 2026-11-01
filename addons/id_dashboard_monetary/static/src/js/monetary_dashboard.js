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

export class MonetaryDashboard extends Component {
    static template = "id_dashboard_monetary.MonetaryDashboard";
    static props = ["*"];

    setup() {
        this.requestVersion = 0;
        onWillUnmount(() => { this.requestVersion++; });
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            areaIds: [],
            salesmanIds: [],
            filters: { areas: [], salesmen: [], today: null },
            data: null,
            periodKey: null,
            subTab: "customers", // 'customers', 'areas', 'salesmen'
        });

        onWillStart(async () => {
            try {
                this.state.filters = await this.orm.call("id.monetary.dashboard", "get_filters", []);
                this.state.periodKey = this.state.filters.periods[0]?.key || null;
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
            const data = await this.orm.call("id.monetary.dashboard", "get_data", [], {
                period_key: this.state.periodKey,
                area_ids: this.state.areaIds,
                salesman_ids: this.state.salesmanIds,
            });
            if (version === this.requestVersion) this.state.data = data;
        } catch (err) {
            if (version === this.requestVersion) { this.state.data = null; this.state.error = err?.data?.message || err?.message || String(err); }
        } finally {
            if (version === this.requestVersion) this.state.loading = false;
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

    onPeriodChange(ev) { this.state.periodKey = ev.target.value; this.load(); }

    reset() {
        this.state.areaIds = [];
        this.state.salesmanIds = [];
        this.load();
    }

    // Formatting helpers
    money(v) { return money(v, this.state.data?.currency); }
    moneyShort(v) { return moneyShort(v, this.state.data?.currency); }
    pct(v) { return pct(v); }
    int(v) { return NF.format(v || 0); }

    // Drilldowns
    openAgingMatrix() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction("id_dashboard_monetary.action_id_ar_aging");
    }

    openFunnel() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({type:"ir.actions.act_window", name:_t("Target Period"),
            res_model:"id.monetary.funnel.stage", views:[[false,"list"],[false,"graph"]],
            domain:this.state.data.domains.funnel});
    }

    openOverdueInvoices() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Faktur Jatuh Tempo"),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: [...this.state.data.domains.aging, ["bucket", "!=", "not_due"]],
        });
    }

    openCustomerInvoices(partnerId, partnerName, companyId) {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t(`Faktur Terbuka - ${partnerName}`),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: [...this.state.data.domains.aging, ["partner_id", "=", partnerId], ["company_id", "=", companyId]],
        });
    }

    openAllInvoices() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Semua Piutang Terbuka"),
            res_model: "id.ar.aging",
            views: [[false, "list"], [false, "form"]],
            domain: this.state.data.domains.aging,
        });
    }
}

registry.category("actions").add("id_dashboard_monetary.monetary_dashboard", MonetaryDashboard);

