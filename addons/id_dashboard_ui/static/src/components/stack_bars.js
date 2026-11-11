/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class StackBars extends Chart {
    static template = "id_dashboard_ui.StackBars";
    get rows() {
        const raw = this.props.rows || [];
        const totals = raw.map((r) =>
            (r.segs || []).reduce((s, a) => s + (Number(a.v) || 0), 0),
        );
        const max = Math.max(1, ...totals);
        return raw.map((r, i) => ({
            ...r,
            index: i,
            total: totals[i],
            segs: (r.segs || []).map((s, j) => ({
                ...s,
                index: j,
                color: s.c || `var(--chart-${j % 6})`,
                width: safeGeometry.ratio(
                    s.v,
                    this.props.mode === "pct" ? totals[i] : max,
                ),
            })),
        }));
    }
}
