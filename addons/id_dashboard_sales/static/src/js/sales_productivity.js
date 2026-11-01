/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODES = [
    { key: "day", label: _t("Daily") },
    { key: "week", label: _t("Weekly") },
    { key: "month", label: _t("Monthly") },
];
const NF = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const NF1 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function pad(n) {
    return String(n).padStart(2, "0");
}
function iso(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
function parse(value) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d);
}

export class SalesProductivity extends Component {
    static template = "id_dashboard_sales.SalesProductivity";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.modes = MODES;
        this.state = useState({
            loading: true,
            error: null,
            mode: "month",
            anchor: null,
            salesmanIds: [],
            channelIds: [],
            dimension: "salesman",
            penKind: "principal",
            filters: { salesmen: [], channels: [], period_min: null, period_max: null, lpo_target: 4 },
            data: null,
        });
        onWillStart(async () => {
            this.state.filters = await this.orm.call("id.sales.productivity", "get_filters", []);
            this.state.anchor = this.state.filters.period_min;
            await this.load();
        });
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call("id.sales.productivity", "get_data", [], {
                mode: this.state.mode,
                anchor: this.state.anchor,
                salesman_ids: this.state.salesmanIds,
                channel_ids: this.state.channelIds,
            });
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    // ---- filters
    setMode(mode) {
        this.state.mode = mode;
        this.load();
    }
    setAnchor(ev) {
        this.clampAndSet(ev.target.value);
    }
    clampAndSet(value) {
        const { period_min: lo, period_max: hi } = this.state.filters;
        if (!value) {
            return;
        }
        this.state.anchor = value < lo ? lo : value > hi ? hi : value;
        this.load();
    }
    shift(direction) {
        const date = parse(this.state.anchor);
        if (this.state.mode === "day") {
            date.setDate(date.getDate() + direction);
        } else if (this.state.mode === "week") {
            date.setDate(date.getDate() + 7 * direction);
        } else {
            date.setMonth(date.getMonth() + direction, 1);
        }
        this.clampAndSet(iso(date));
    }
    toggle(listName, id) {
        const list = this.state[listName];
        const index = list.indexOf(id);
        if (index >= 0) {
            list.splice(index, 1);
        } else {
            list.push(id);
        }
        this.load();
    }
    reset() {
        this.state.mode = "month";
        this.state.anchor = this.state.filters.period_min;
        this.state.salesmanIds = [];
        this.state.channelIds = [];
        this.load();
    }
    get canPrev() {
        return this.state.data && this.state.data.period.start > this.state.filters.period_min;
    }
    get canNext() {
        return this.state.data && this.state.data.period.end < this.state.filters.period_max;
    }

    // ---- formatting
    money(value) {
        return value === null || value === undefined ? "–" : `Rp ${NF.format(value)}`;
    }
    moneyShort(value) {
        if (value === null || value === undefined) {
            return "–";
        }
        const abs = Math.abs(value);
        if (abs >= 1e9) {
            return `Rp ${NF1.format(value / 1e9)} M`;
        }
        if (abs >= 1e6) {
            return `Rp ${NF1.format(value / 1e6)} jt`;
        }
        return `Rp ${NF.format(value)}`;
    }
    int(value) {
        return value === null || value === undefined ? "–" : NF.format(value);
    }
    pct(value) {
        return value === null || value === undefined ? "–" : `${NF1.format(value * 100)}%`;
    }
    num1(value) {
        return value === null || value === undefined ? "–" : NF1.format(value);
    }
    get periodLabel() {
        const p = this.state.data?.period;
        if (!p) {
            return "";
        }
        return p.start === p.end ? p.start : `${p.start} → ${p.end}`;
    }
    get rows() {
        return this.state.data ? (this.state.dimension === "salesman" ? this.state.data.salesmen : this.state.data.channels) : [];
    }
    get pjp() {
        return this.state.data?.total?.pjp || { available: false };
    }
    get pjpReason() {
        return this.state.data?.pjp_status?.reason || "";
    }
    get pjpScopeOwn() {
        return this.state.data?.pjp_status?.scope === "own";
    }
    get lpoClass() {
        const ok = this.state.data?.total?.lpo_ok;
        return ok === null || ok === undefined ? "" : ok ? "is-ok" : "is-low";
    }
    get lpoPercent() {
        const lpo = this.state.data?.total?.lpo;
        const target = this.state.data?.lpo_target || 4;
        if (!lpo) return 0;
        return Math.min(100, Math.round((lpo / target) * 100));
    }
    get fulfillmentPercent() {
        const val = this.state.data?.total?.fulfillment;
        return val ? Math.min(100, Math.round(val * 100)) : 0;
    }
    get pjpCompliancePercent() {
        const val = this.pjp?.compliance;
        return val ? Math.min(100, Math.round(val * 100)) : 0;
    }
    get ecRatioPercent() {
        const val = this.pjp?.ec_ratio;
        return val ? Math.min(100, Math.round(val * 100)) : 0;
    }

    // ---- penetration
    get penetration() {
        const block = this.state.data?.penetration?.[this.state.dimension]?.[this.state.penKind] || [];
        return block;
    }
    penCell(item, row) {
        return item.cells[String(row.id)] || { sold: 0, penetration: null };
    }
    heat(value) {
        if (value === null || value === undefined) {
            return "";
        }
        if (value >= 0.6) {
            return "heat-3";
        }
        if (value >= 0.3) {
            return "heat-2";
        }
        return value > 0 ? "heat-1" : "heat-0";
    }

    // ---- trend (SVG bars)
    get trendBars() {
        const points = this.state.data?.trend || [];
        const max = Math.max(1, ...points.map((p) => p.net));
        const width = 100 / Math.max(points.length, 1);
        return points.map((p, i) => ({
            ...p,
            x: i * width + width * 0.15,
            w: width * 0.7,
            h: (p.net / max) * 90,
            y: 100 - (p.net / max) * 90,
            label: p.date.slice(8),
        }));
    }

    // ---- drill-down
    openOrders(extra = []) {
        const domain = [...this.state.data.domains.orders, ...extra];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Sales Orders"),
            res_model: "sale.order",
            views: [[false, "list"], [false, "form"]],
            domain,
        });
    }
    openDiscounted() {
        this.openOrders([["order_line.discount", ">", 0]]);
    }
    openPickings() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Delivered DO"),
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain: this.state.data.domains.pickings,
        });
    }
    openRow(row) {
        if (!row.id) {
            return;
        }
        const field = this.state.dimension === "salesman" ? "user_id" : "partner_id.channel_id";
        this.openOrders([[field, "=", row.id]]);
    }
}

registry.category("actions").add("id_dashboard_sales.sales_productivity", SalesProductivity);
