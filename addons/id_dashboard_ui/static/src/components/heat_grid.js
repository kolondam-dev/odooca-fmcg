/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class HeatGrid extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        rows: { type: Array, optional: false },
        cols: { type: Array, optional: false },
        vals: { type: Array, optional: false },
        unit: { type: String, optional: true },
        lo: { type: [String, Number], optional: true },
        hi: { type: [String, Number], optional: true },
        ac: { type: String, optional: true },
        note: { type: String, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.HeatGrid";
    renderVals() {
        const p = this.props;
        const rl = p.rows || [],
            cl = p.cols || [],
            v = p.vals || [
                [10, 20],
                [30, 40],
            ],
            u = p.unit || "";
        const flat = [].concat(...v);
        const lo = +(p.lo != null ? p.lo : Math.min(...flat)),
            hi = +(p.hi != null ? p.hi : Math.max(...flat));
        const H = +(p.height || 0);
        const A = [238, 243, 251],
            B = [31, 95, 191];
        const lum = (c) => {
            const f = (x) => {
                x /= 255;
                return x <= 0.03928
                    ? x / 12.92
                    : Math.pow((x + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
        };
        const cells = [
            {
                t: "",
                bg: "transparent",
                c: "#12223f",
                fw: 400,
                j: "flex-start",
            },
        ];
        cl.forEach((t) =>
            cells.push({
                t,
                bg: "transparent",
                c: "#52627f",
                fw: 600,
                j: "center",
            }),
        );
        rl.forEach((r, i) => {
            cells.push({
                t: r,
                bg: "transparent",
                c: "#12223f",
                fw: 600,
                j: "flex-start",
            });
            v[i].forEach((x) => {
                const t = Math.max(0, Math.min(1, (x - lo) / (hi - lo || 1)));
                const c = A.map((a, k) => Math.round(a + (B[k] - a) * t));
                const L = lum(c);
                const w = 1.05 / (L + 0.05),
                    d = (L + 0.05) / (lum([18, 34, 63]) + 0.05);
                cells.push({
                    t: String(x).replace(".", ",") + u,
                    bg: `rgb(${c[0]},${c[1]},${c[2]})`,
                    c: w > d ? "#ffffff" : "#12223f",
                    fw: 600,
                    j: "center",
                });
            });
        });
        return {
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            gtc: `96px repeat(${cl.length},minmax(0,1fr))`,
            cells,
            showNote: !!p.note,
            note: p.note || "",
        };
    }
}
