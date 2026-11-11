/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class BarRows extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        rows: { type: Array, optional: false },
        cols: { type: [String, Number], optional: true },
        rowH: { type: [String, Number], optional: true },
        height: { type: [String, Number], optional: true },
        bare: { type: [String, Boolean], optional: true },
        headL: { type: String, optional: true },
        headR: { type: String, optional: true },
        foot: { type: String, optional: true },
        max: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    openRow(row) {
        if (row.drill) this.props.onDrill?.(row.drill);
    }
    rowKey(ev, row) {
        if (ev.key === "Enter" || ev.key === " ") this.openRow(row);
    }
    static template = "id_dashboard_ui.BarRows";
    renderVals() {
        const p = this.props;
        const rows = p.rows || [];
        const cols = +(p.cols || 1),
            rowH = +(p.rowH || 0),
            bare = p.bare === "true" || p.bare === true;
        const data = rows.filter((r) => !r.total);
        const mx = +(p.max || Math.max(...data.map((r) => Math.abs(r.v)), 1));
        const first = rows.findIndex((r) => !r.total);
        const items = rows.map((r, i) => ({
            n: r.n,
            t: r.t,
            drill: r.drill,
            tip: r.tip || "",
            w: r.total ? 0 : ((Math.abs(r.v) / mx) * 100).toFixed(1),
            fill: r.c || (r.v < 0 ? "#b3261e" : i === first ? "var(--ac2)" : "var(--ac3)"),
            bg: r.total ? "transparent" : "var(--tint2)",
            bt: r.total ? "1px solid #d5e0f2" : "0",
            rad: r.total ? "0" : "4px",
            fw: r.total ? 700 : 600,
        }));
        const per = Math.max(1, Math.ceil(items.length / cols));
        return {
            card: bare
                ? ""
                : "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: p.height ? p.height + "px" : "auto",
            showTitle: !bare && !!p.title,
            title: p.title || "",
            showHead: !!p.headL,
            heads: Array.from({ length: cols }, () => ({
                l: p.headL || "",
                r: p.headR || "",
            })),
            gtc: `repeat(${cols},minmax(0,1fr))`,
            gtr: rowH
                ? `repeat(${per},${rowH}px)`
                : `repeat(${per},minmax(22px,1fr))`,
            items,
            showFoot: !!p.foot,
            foot: p.foot || "",
        };
    }
}
