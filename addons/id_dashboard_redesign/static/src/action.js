/** @odoo-module **/
import { Component, onWillStart, onWillDestroy, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ApprovedControls } from "@id_dashboard_ui/components/approved_controls";
import { DashboardShell } from "@id_dashboard_ui/pages/dashboard";
import { adaptSource } from "@id_dashboard_redesign/adapters";

export class RedesignAction extends Component {
    static template = "id_dashboard_redesign.Action";
    static components = { DashboardShell, ApprovedControls };
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const release = this.env.services.id_shell?.enterDashboard?.();
        this.generation = 0;
        this.state = useState({ loading: true, error: null, data: null, filters: {}, scope: {} });
        onWillDestroy(() => { this.generation++; release?.(); });
        onWillStart(async () => {
            try {
                const info = await this.orm.call("id.dashboard.redesign", "get_filters", ["D1"]);
                this.state.filters = info.filters;
                this.state.scope = info.scope;
                const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Makassar" }).format(new Date());
                const end = info.filters.period_max < today ? info.filters.period_max : today;
                this.initialQuery = { period: { preset: "custom", from: end.slice(0, 8) + "01", to: end,
                    compare: false, compareMode: "previous", align: false, customFrom: end, customTo: end }, filters: {} };
                await this.load(this.initialQuery);
            } catch (error) {
                this.state.error = error?.data?.message || error.message;
                this.state.loading = false;
            }
        });
    }
    get dashboard() { return "D1"; }
    controlOptions(query) {
        const labels = { salesman: _t("Salesperson"), channel: _t("Channel"), area: _t("Coverage area"),
            city: _t("City / regency"), principal: _t("Principal"), brand: _t("Brand"), sku: _t("SKU") };
        return {
            today: new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Makassar" }).format(new Date()),
            initialQuery: query, scopeLabel: _t("Company") + ": " + this.state.scope.company_names.join(", "),
            dimensions: Object.entries(this.state.filters.dimensions).map(([id, rows]) => ({
                id, name: labels[id], short: labels[id], group: _t("Filters"),
                values: rows.map(r => [String(r.id), r.name, String(r.principal || ""), String(r.brand || "")]),
            })), demo: false, workdayAlignment: false, maxDays: 366,
        };
    }
    async load(query) {
        const token = ++this.generation;
        this.state.loading = true;
        this.state.error = null;
        const request = JSON.parse(JSON.stringify(query));
        for (const spec of Object.values(request.filters)) spec.ids = spec.ids.map(Number);
        try {
            const response = await this.orm.call("id.dashboard.redesign", "get_data", ["D1"], { params: { query: request } });
            if (token !== this.generation) return false;
            const data = adaptSource("D1", response, this.state.scope);
            data.geoLoad = parent => this.orm.call("id.dashboard.redesign", "get_geo_boundaries", ["D1", parent]);
            data.controlOptions = this.controlOptions(query);
            this.state.data = data;
            this.query = JSON.parse(JSON.stringify(query));
            return true;
        } catch (error) {
            if (token === this.generation) this.state.error = error?.data?.message || error.message;
            return false;
        } finally {
            if (token === this.generation) this.state.loading = false;
        }
    }
    get recoveryOptions() { return this.controlOptions(this.query || this.initialQuery); }
    apply(query) { return this.load(query); }
    openDocument(drill) {
        if (this.state.loading || !drill) return;
        if (drill.dimension === "city_code") drill = this.state.data.cityDrills[drill.code];
        if (!drill || !["sale.order", "sale.order.line", "account.move.line"].includes(drill.model) || !Array.isArray(drill.domain)) return;
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Source documents"),
            res_model: drill.model, views: [[false, "list"], [false, "form"]], domain: drill.domain });
    }
}
registry.category("actions").add("id_dashboard_redesign.d1", RedesignAction);
