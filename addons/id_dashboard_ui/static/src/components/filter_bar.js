/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class FilterBar extends VisualComponent {
    static props = {
        period: { type: String, optional: false },
        compare: { type: String, optional: true },
        count: { type: [String, Number], optional: true },
        note: { type: String, optional: true },
        chips: { type: Array, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.FilterBar";
    renderVals() {
        const p = this.props;
        const S = {
            n: ["var(--chip)", "1px solid transparent"],
            lock: ["#e9edf3", "1px solid transparent"],
            drill: ["#fff", "1px dashed var(--ac)"],
        };
        const ch = (p.chips || []).map((c) => {
            const s = S[c.k || "n"];
            return {
                t: c.t,
                bg: s[0],
                bd: s[1],
                lock: c.k === "lock",
                x: c.k !== "lock",
            };
        });
        return {
            period: p.period || "—",
            compare: p.compare || "—",
            count: p.count || ch.length,
            note: p.note || "",
            chips: ch,
        };
    }
}
