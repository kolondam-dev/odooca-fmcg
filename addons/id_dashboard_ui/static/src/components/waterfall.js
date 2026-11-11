/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class Waterfall extends Chart {
    static template = "id_dashboard_ui.Waterfall";
    get bars() {
        let sum = 0;
        const raw = (this.props.steps || []).map((s, i) => {
            const from = s.k === "total" ? 0 : sum;
            sum = s.k === "total" ? s.v : sum + s.v;
            return { ...s, index: i, from, to: sum };
        });
        const max = Math.max(1, ...raw.flatMap((x) => [x.from, x.to]));
        const min = Math.min(0, ...raw.flatMap((x) => [x.from, x.to]));
        const scale = max - min || 1;
        return raw.map((s) => ({
            ...s,
            y: 20 + ((max - Math.max(s.from, s.to)) / scale) * 155,
            h: Math.max(1, (Math.abs(s.to - s.from) / scale) * 155),
            x: 38 + s.index * (490 / Math.max(1, raw.length)),
            w: Math.min(66, 350 / Math.max(1, raw.length)),
            color:
                s.c ||
                (s.k === "total"
                    ? "var(--dk)"
                    : s.v < 0
                      ? "#1a7f4b"
                      : "#dfa721"),
        }));
    }
}
