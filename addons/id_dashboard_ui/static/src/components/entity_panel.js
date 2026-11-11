/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class EntityPanel extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        mini: { type: Array, optional: false },
        spark: { type: Array, optional: true },
        sparkTitle: { type: String, optional: true },
        ex: { type: Array, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.EntityPanel";
    renderVals() {
        const p = this.props;
        const sp = p.spark || [1, 2, 3];
        const mx = Math.max(...sp),
            mn = Math.min(...sp);
        const H = +(p.height || 0);
        return {
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            mini: p.mini || [],
            sparkTitle: p.sparkTitle || "",
            pts: sp
                .map(
                    (v, i) =>
                        `${((i * 100) / Math.max(1, sp.length - 1)).toFixed(1)},${(26 - ((v - mn) / (mx - mn || 1)) * 22).toFixed(1)}`,
                )
                .join(" "),
            ex: (p.ex || []).map((e) => ({ t: e.t, c: e.c || "#12223f" })),
        };
    }
}
