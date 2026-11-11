/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class CoveragePanel extends Chart {
    static template = "id_dashboard_ui.CoveragePanel";
    static components = { GeoMap, BarRows };
    get mapProps() {
        const { vals, vb, off, th, suffix, legend, crumbs } = this.props;
        return {
            vals,
            crumbs,
            vb,
            off,
            th,
            suffix,
            legend,
            onDrill: this.props.onDrill,
        };
    }
    get tableProps() {
        return {
            bare: true,
            onDrill: this.props.onDrill,
            cols: 2,
            rowH: 28,
            rows: this.props.rows || [],
            headL: "City / regency",
            headR: this.props.headR || "",
            foot: this.props.foot || "",
        };
    }
}
