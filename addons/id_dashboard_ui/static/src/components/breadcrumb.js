/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class Breadcrumb extends VisualComponent {
    static props = {
        crumbs: { type: Array, optional: false },
        back: { type: String, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.Breadcrumb";
    renderVals() {
        const p = this.props;
        const cr = p.crumbs || ["Level 1", "Level 2"];
        return {
            crumbs: cr.map((t, i) => ({
                t,
                s: i ? "›" : "",
                c: i === cr.length - 1 ? "#12223f" : "var(--ac)",
                fw: i === cr.length - 1 ? 700 : 400,
            })),
            back: p.back || "← Kembali ke overview",
        };
    }
}
