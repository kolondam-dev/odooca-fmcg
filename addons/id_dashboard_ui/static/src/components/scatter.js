/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class Scatter extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        pts: { type: Array, optional: false },
        xr: { type: Array, optional: false },
        yr: { type: Array, optional: false },
        xt: { type: Array, optional: true },
        yt: { type: Array, optional: true },
        xl: { type: String, optional: true },
        yl: { type: String, optional: true },
        note: { type: String, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.Scatter";
    openPoint(item) {
        if (item.drill) this.props.onDrill?.(item.drill);
    }
    keyPoint(event, item) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.openPoint(item);
        }
    }
    renderVals() {
        const p = this.props;
        const xr = p.xr || [0, 10],
            yr = p.yr || [0, 10];
        const px = (x) => ((x - xr[0]) / (xr[1] - xr[0] || 1)) * 100,
            py = (y) => 100 - ((y - yr[0]) / (yr[1] - yr[0] || 1)) * 100;
        const H = +(p.height || 0);
        return {
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            ph: H ? H - 120 : 210,
            yt: (p.yt || yr).map((v) => ({
                t: String(v),
                p: py(v).toFixed(1),
            })),
            xt: (p.xt || xr).map((v) => ({
                t: String(v),
                p: px(v).toFixed(1),
            })),
            pts: (p.pts || []).map((q) => ({
                l: px(q.x).toFixed(1),
                t: py(q.y).toFixed(1),
                d: q.r,
                m: `${-q.r / 2}px 0 0 ${-q.r / 2}px`,
                n: q.l || "",
                label: q.showLabel === false ? "" : q.l || "",
                drill: q.drill,
            })),
            xl: p.xl || "",
            yl: p.yl || "",
            note: p.note || "",
        };
    }
}
