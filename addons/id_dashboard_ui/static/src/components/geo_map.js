/** @odoo-module **/
import { useState } from "@odoo/owl";
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class GeoMap extends VisualComponent {
    static props = {
        vals: { type: Object, optional: false },
        vb: { type: Array, optional: true },
        viewport: { type: Array, optional: true },
        off: { type: Object, optional: true },
        th: { type: Array, optional: true },
        w: { type: [String, Number], optional: true },
        h: { type: [String, Number], optional: true },
        suffix: { type: String, optional: true },
        legend: { type: String, optional: true },
        crumbs: { type: Array, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    setup() {
        this.view = useState({
            vb: [...(this.props.vb || [54.2, 172.8, 99.8, 82.4])],
        });
        this.drag = null;
    }
    zoom(factor) {
        const [x, y, w, h] = this.view.vb;
        const width = Math.max(5, Math.min(500, w * factor));
        const height = (h * width) / w;
        this.view.vb = [
            x + (w - width) / 2,
            y + (h - height) / 2,
            width,
            height,
        ];
    }
    mapClick(ev) {
        const command = ev.target.closest("button")?.dataset.command;
        if (command === "in") this.zoom(0.8);
        if (command === "out") this.zoom(1.25);
        if (command === "reset") this.view.vb = [0, 0, 250, 278.1];
        const code = ev.target.closest("[data-code]")?.dataset.code;
        if (code) this.props.onDrill?.({ dimension: "city_code", code });
    }
    startPan(ev) {
        if (ev.button !== 0 || ev.target.closest("button")) return;
        this.drag = { x: ev.clientX, y: ev.clientY, vb: [...this.view.vb] };
        ev.currentTarget.setPointerCapture?.(ev.pointerId);
    }
    movePan(ev) {
        if (!this.drag) return;
        const box = ev.currentTarget.getBoundingClientRect();
        const d = this.drag;
        this.view.vb = [
            d.vb[0] - ((ev.clientX - d.x) / box.width) * d.vb[2],
            d.vb[1] - ((ev.clientY - d.y) / box.height) * d.vb[3],
            d.vb[2],
            d.vb[3],
        ];
    }
    stopPan() {
        this.drag = null;
    }
    mapKey(ev) {
        if (ev.key === "Enter" || ev.key === " ") this.mapClick(ev);
    }
    static template = "id_dashboard_ui.GeoMap";
    renderVals() {
        const p = this.props;
        const W = +(p.w || 400),
            H = +(p.h || 330);
        const vb = this.view.vb || p.vb || [63.7, 172.8, 99.8, 82.4];
        const vals = p.vals || {};
        const th = p.th || [60, 120, 300];
        const off = p.off || {};
        const sf = p.suffix || "";
        const CENT = {
            71.01: [54.1, 251.6],
            71.02: [110.7, 220.1],
            71.03: [151.0, 75.9],
            71.04: [229.2, 31.3],
            71.05: [81.9, 230.6],
            71.06: [116.9, 202.2],
            71.07: [100.2, 235.1],
            71.08: [22.8, 248.3],
            71.09: [140.5, 128.4],
            "71.10": [85.2, 252.2],
            71.11: [66.2, 268.1],
            71.71: [109.4, 203.0],
            71.72: [126.4, 203.4],
            71.73: [104.7, 214.4],
            71.74: [74.4, 252.2],
        };
        const NM = {
            71.01: "Bolmong",
            71.02: "Minahasa",
            71.03: "Sangihe",
            71.04: "Talaud",
            71.05: "Minsel",
            71.06: "Minut",
            71.07: "Mitra",
            71.08: "Bolmut",
            71.09: "Sitaro",
            "71.10": "Boltim",
            71.11: "Bolsel",
            71.71: "Manado",
            71.72: "Bitung",
            71.73: "Tomohon",
            71.74: "Kotamobagu",
        };
        const col = (v) =>
            v >= th[2]
                ? "var(--dk)"
                : v >= th[1]
                  ? "var(--ac)"
                  : v >= th[0]
                    ? "var(--ac2)"
                    : "var(--ac3)";
        const f = {},
            labels = [];
        for (const k in CENT) {
            const v = vals[k];
            f["c" + k.replace(".", "_")] = v == null ? "var(--tint2)" : col(v);
            const c = CENT[k];
            if (
                v != null &&
                c[0] >= vb[0] &&
                c[0] <= vb[0] + vb[2] &&
                c[1] >= vb[1] &&
                c[1] <= vb[1] + vb[3]
            ) {
                const o = off[k] || [0, 0];
                labels.push({
                    n: NM[k],
                    v: new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(v) + sf,
                    l: (
                        ((c[0] - vb[0]) / vb[2]) * 100 +
                        (o[0] / W) * 100
                    ).toFixed(2),
                    t: (
                        ((c[1] - vb[1]) / vb[3]) * 100 +
                        (o[1] / H) * 100
                    ).toFixed(2),
                });
            }
        }
        const cr = p.crumbs || [
            "Province",
            "City / regency",
            "District",
            "Village",
        ];
        return {
            mapId: "sulutgeo-" + this.__owl__.id,
            w: W,
            h: H,
            vb: vb.join(" "),
            vx: vb[0],
            vy: vb[1],
            vw: vb[2],
            vh: vb[3],
            f,
            labels,
            lgt: p.legend || "Revenue (million)",
            lg: [
                { c: "var(--ac3)", t: "<" + th[0] },
                { c: "var(--ac2)", t: th[0] + "–" + (th[1] - 1) },
                { c: "var(--ac)", t: th[1] + "–" + (th[2] - 1) },
                { c: "var(--dk)", t: "≥" + th[2] },
            ],
            crumbs: cr.map((t, i) => ({
                t,
                s: i ? "›" : "",
                fw: i === 0 ? 700 : 400,
                c: i === 0 ? "#12223f" : "#52627f",
            })),
        };
    }
}
