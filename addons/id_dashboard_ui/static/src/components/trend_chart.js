/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class TrendChart extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        series: { type: Array, optional: false },
        legend: { type: Array, optional: true },
        target: { type: [String, Number], optional: true },
        min: { type: [String, Number], optional: true },
        max: { type: [String, Number], optional: true },
        ticks: { type: Array, optional: true },
        xl: { type: Array, optional: true },
        unit: { type: String, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.TrendChart";
    renderVals() {
        const p = this.props;
        const s = p.series || [{ v: [] }, { v: [] }];
        const mn = +(p.min || 0),
            mx = +(p.max || 20);
        const n = Math.max(1, ...s.map((a) => a.v.length));
        const X = (i) => (i / Math.max(1, n - 1)) * 100;
        const Y = (v) => 100 - ((v - mn) / (mx - mn || 1)) * 100;
        const pt = (a) =>
            a.v
                .map((v, i) => `${X(i).toFixed(2)},${Y(v).toFixed(2)}`)
                .join(" ");
        const s1 = s[0] || { v: [] },
            s2 = s[1] || { v: [] };
        const hasT = p.target != null && p.target !== "";
        const ticks = (p.ticks || [mn, mx]).map((v) => ({
            t: String(v),
            top: Y(v).toFixed(1),
        }));
        const lg = (p.legend || []).map((g) => ({
            t: g.t,
            bd: (g.d ? "2px dashed " : "3px solid ") + g.c,
        }));
        const H = +(p.height || 0);
        return {
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            legend: lg,
            unit: p.unit || "",
            ph: H ? H - 100 : 190,
            ticks,
            a1: `0,100 ${pt(s1)} ${X(s1.v.length - 1)},100`,
            p1: pt(s1),
            p2: pt(s2),
            ty: hasT ? Y(+p.target).toFixed(2) : 0,
            to: hasT ? 1 : 0,
            dots: s1.v.map((v, i) => ({
                l: X(i).toFixed(2),
                t: Y(v).toFixed(2),
            })),
            xl: (p.xl || []).map((t, i) => ({ t, l: X(i).toFixed(2) })),
        };
    }
}
