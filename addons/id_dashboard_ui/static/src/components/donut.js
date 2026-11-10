/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class Donut extends Chart {
    static template = "id_dashboard_ui.Donut";
    get items() {
        const items = this.props.items || [];
        const sum = items.reduce((a, b) => a + (Number(b.v) || 0), 0);
        let offset = 0;
        return items.map((r, i) => {
            const part = sum > 0 ? (100 * (Number(r.v) || 0)) / sum : 0;
            const row = {
                ...r,
                index: i,
                part,
                offset,
                color: r.c || `var(--chart-${i % 6})`,
            };
            offset += part;
            return row;
        });
    }
}
