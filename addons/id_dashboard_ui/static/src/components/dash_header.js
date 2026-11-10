/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class DashHeader extends VisualComponent {
    static props = {
        title: { type: String, optional: false },
        sub: { type: String, optional: true },
        sync: { type: String, optional: true },
        role: { type: String, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.DashHeader";
    renderVals() {
        const p = this.props;
        return {
            title: p.title || "Dashboard title",
            sub: p.sub || "",
            sync: p.sync || "—",
            role: p.role || "—",
        };
    }
}
