/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class Gauge extends Chart {
    static template = "id_dashboard_ui.Gauge";
    get cfg() {
        return this.props.cfg || {};
    }
    get angle() {
        return safeGeometry.ratio(this.cfg.value, 100) * 1.8;
    }
    get arc() {
        const a = (this.angle * Math.PI) / 180;
        return `M 20 110 A 90 90 0 0 1 ${110 - 90 * Math.cos(a)} ${110 - 90 * Math.sin(a)}`;
    }
    get targetLine() {
        const a = (safeGeometry.ratio(this.cfg.target, 100) * Math.PI) / 100;
        return `M ${110 - 78 * Math.cos(a)} ${110 - 78 * Math.sin(a)} L ${110 - 106 * Math.cos(a)} ${110 - 106 * Math.sin(a)}`;
    }
}
