/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class FilterPopup extends VisualComponent {
    static props = {
        groups: { type: Array, optional: true },
        current: { type: String, optional: true },
        search: { type: String, optional: true },
        values: { type: Array, optional: true },
        tip: { type: String, optional: true },
        chips: { type: Array, optional: true },
        match: { type: String, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.FilterPopup";
    renderVals() {
        const p = this.props;
        const g = p.groups || [];
        const dims = [];
        g.forEach((x) => {
            dims.push({
                head: true,
                row: false,
                n: String(x.g).toUpperCase(),
                b: "",
                bg: "transparent",
                fw: 400,
            });
            x.items.forEach((i) =>
                dims.push({
                    head: false,
                    row: true,
                    n: i.n,
                    b: i.b || "",
                    bg: i.act ? "var(--chip)" : "transparent",
                    fw: i.act ? 600 : 400,
                }),
            );
        });
        return {
            dims,
            cur: p.current || "Dimensi",
            search: p.search || "Cari…",
            vals: (p.values || []).map((v) => ({
                a: v.a,
                b: v.b || "",
                bg: v.sel ? "var(--ac)" : "#ffffff",
                m: v.sel ? "✓" : "",
            })),
            hint: p.tip || "",
            chips: (p.chips || []).map((c) => ({
                t: c.t,
                bg: c.k === "lock" ? "#e9edf3" : "var(--chip)",
            })),
            match: p.match || "",
        };
    }
}
