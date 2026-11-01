/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
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
        this.requestVersion = 0;
        onWillUnmount(() => { this.requestVersion++; });
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
        const version = ++this.requestVersion;
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call("id.sales.productivity", "get_data", [], {
                mode: this.state.mode,
                anchor: this.state.anchor,
                salesman_ids: this.state.salesmanIds,
                channel_ids: this.state.channelIds,
            });
            if (version === this.requestVersion) this.state.data = data;
        } catch (error) {
            if (version === this.requestVersion) { this.state.data = null; this.state.error = error?.data?.message || error?.message || String(error); }
        } finally {
            if (version === this.requestVersion) this.state.loading = false;
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

    // ---- comparison with previous period
    delta(key, kind = "change", neutral = false) {
        const none = { text: "", cls: "" };
        const cur = this.state.data?.total?.[key];
        const prev = this.state.data?.previous?.[key];
        if (!this.state.data?.previous?.orders || cur === null || cur === undefined || prev === null || prev === undefined) {
            return none;
        }
        let diff;
        let text;
        if (kind === "pp") {
            diff = (cur - prev) * 100;
            text = `${NF1.format(Math.abs(diff))} pp`;
        } else if (kind === "abs") {
            diff = cur - prev;
            text = NF1.format(Math.abs(diff));
        } else {
            if (!prev) {
                return none;
            }
            diff = ((cur - prev) / Math.abs(prev)) * 100;
            text = `${NF1.format(Math.abs(diff))}%`;
        }
        if (Math.abs(diff) < 0.05) {
            return { text: `= ${_t("vs previous period")}`, cls: "is-flat" };
        }
        const up = diff > 0;
        return {
            text: `${up ? "▲" : "▼"} ${text} ${_t("vs previous period")}`,
            cls: neutral ? "is-flat" : up ? "is-up" : "is-down",
        };
    }

    get salesCards() {
        const t = this.state.data.total;
        const gross = t.gross;
        return [
            { key: "gross", title: _t("Gross Revenue"), icon: "fa-line-chart", tone: "navy",
              value: this.moneyShort(t.gross), meta: `${this.int(t.orders)} ${_t("orders")} · ${this.money(t.gross)}`,
              delta: this.delta("gross"), action: () => this.openOrders() },
            { key: "discount", title: _t("Discount Given"), icon: "fa-percent", tone: "amber",
              value: this.moneyShort(t.discount),
              meta: `${this.pct(gross ? t.discount / gross : null)} ${_t("of gross")}`,
              delta: this.delta("discount", "change", true), action: () => this.openDiscounted() },
            { key: "net", title: _t("Net Revenue"), icon: "fa-money", tone: "emerald",
              value: this.moneyShort(t.net), meta: `${_t("ex-tax (DPP)")} · ${this.money(t.net)}`,
              delta: this.delta("net"), action: () => this.openOrders() },
            { key: "do", title: _t("Delivered DO"), icon: "fa-truck", tone: "blue",
              value: this.int(t.do_count), meta: _t("by delivery date"),
              delta: this.delta("do_count"), action: () => this.openPickings() },
        ];
    }

    get fieldCards() {
        const t = this.state.data.total;
        const pjp = this.pjp;
        const na = { text: "", cls: "" };
        return [
            { key: "pjp", title: _t("PJP Call Compliance"), icon: "fa-map-marker", tone: "blue",
              value: pjp.available ? this.pct(pjp.compliance) : "N/A", cls: pjp.available ? "" : "is-na",
              meta: pjp.available ? `${this.int(pjp.completed)} / ${this.int(pjp.planned)} ${_t("planned outlets")}` : this.pjpReason,
              delta: na },
            { key: "ec", title: _t("Effective Call Ratio"), icon: "fa-check-circle", tone: "emerald",
              value: pjp.available ? this.pct(pjp.ec_ratio) : "N/A", cls: pjp.available ? "" : "is-na",
              meta: pjp.available ? `${this.int(pjp.effective)} / ${this.int(pjp.visits)} ${_t("visits with order")}` : this.pjpReason,
              delta: na },
            { key: "lpo", title: _t("Lines per Order"), icon: "fa-list-ol", tone: "navy",
              value: this.num1(t.lpo), cls: this.lpoClass,
              meta: `${_t("Target ≥")} ${this.num1(this.state.data.lpo_target)} ${_t("SKU/order")}`,
              delta: this.delta("lpo", "abs") },
            { key: "sku", title: _t("SKU Sold"), icon: "fa-cubes", tone: "amber",
              value: this.int(t.sku_sold), cls: "", meta: _t("distinct SKU"),
              delta: this.delta("sku_sold") },
            { key: "ful", title: _t("Fulfillment-to-Invoice"), icon: "fa-file-text-o", tone: "emerald",
              value: this.pct(t.fulfillment), cls: "", meta: _t("delivered and posted-invoiced value"),
              delta: this.delta("fulfillment", "pp") },
        ];
    }

    // ---- horizontal bars
    _bars(rows, valueOf, max = null) {
        const top = max || Math.max(...rows.map(valueOf), 0) || 1;
        return rows.map((row) => ({ id: row.id, name: row.name, row, width: Math.max(0, Math.min(100, (valueOf(row) / top) * 100)) }));
    }
    get salesmanBars() {
        const rows = [...(this.state.data?.salesmen || [])].sort((a, b) => b.net - a.net);
        return this._bars(rows, (r) => r.net).map((b) => ({ ...b, net: b.row.net }));
    }
    get channelBars() {
        const rows = [...(this.state.data?.channels || [])].sort((a, b) => b.net - a.net);
        return this._bars(rows, (r) => r.net).map((b) => ({ ...b, net: b.row.net }));
    }
    get lpoScaleMax() {
        const values = (this.state.data?.salesmen || []).map((r) => r.lpo || 0);
        return Math.max(this.state.data?.lpo_target || 4, ...values) * 1.15;
    }
    get lpoTargetPos() {
        return ((this.state.data?.lpo_target || 4) / this.lpoScaleMax) * 100;
    }
    get lpoBars() {
        const rows = (this.state.data?.salesmen || []).filter((r) => r.lpo !== null);
        return this._bars(rows, (r) => r.lpo || 0, this.lpoScaleMax).map((b) => ({ ...b, lpo: b.row.lpo, ok: b.row.lpo_ok }));
    }
    get fulfillmentBars() {
        const rows = (this.state.data?.salesmen || []).filter((r) => r.fulfillment !== null);
        return this._bars(rows, (r) => r.fulfillment || 0, 1).map((b) => ({ ...b, value: b.row.fulfillment }));
    }
    get trendMax() {
        return Math.max(0, ...(this.state.data?.trend || []).map((p) => p.net));
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
        if (this.state.loading || !this.state.data) return;
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
        if (this.state.loading || !this.state.data) return;
        this.openOrders([["order_line.discount", ">", 0]]);
    }
    openPickings() {
        if (this.state.loading || !this.state.data) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Delivered DO"),
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain: this.state.data.domains.pickings,
        });
    }
    openRow(row) {
        if (this.state.loading || !this.state.data) return;
        if (!row.id) {
            return;
        }
        const field = this.state.dimension === "salesman" ? "user_id" : "partner_id.channel_id";
        this.openOrders([[field, "=", row.id]]);
    }
}

registry.category("actions").add("id_dashboard_sales.sales_productivity", SalesProductivity);
