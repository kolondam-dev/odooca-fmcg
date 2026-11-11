/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class Bullet extends Chart {
    static template = "id_dashboard_ui.Bullet";
    get rows() {
        return (this.props.rows || []).map((r, i) => ({
            ...r,
            index: i,
            width: safeGeometry.ratio(r.v, Number(this.props.max) || 100),
            targetPos: safeGeometry.ratio(
                r.target,
                Number(this.props.max) || 100,
            ),
        }));
    }
}
