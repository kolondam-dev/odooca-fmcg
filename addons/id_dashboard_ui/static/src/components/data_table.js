/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class DataTable extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
        cols: { type: Array, optional: false },
        rows: { type: Array, optional: false },
        note: { type: String, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    openCell(cell) {
        if (cell.drill) this.props.onDrill?.(cell.drill);
    }
    static template = "id_dashboard_ui.DataTable";
    renderVals() {
        const p = this.props;
        const cols = p.cols || [];
        const rows = p.rows || [];
        const H = +(p.height || 0);
        const J = { left: "flex-start", right: "flex-end", center: "center" };
        const cells = [];
        rows.forEach((r) =>
            r.forEach((v, i) => {
                const o = v !== null && typeof v === "object" ? v : { t: v };
                const a = cols[i].a || "left";
                cells.push({
                    t: o.t,
                    drill: o.drill,
                    hasBar: o.bar != null,
                    bar: o.bar || 0,
                    c: o.c || "#12223f",
                    fw: o.b ? 700 : 400,
                    j: J[a] || "flex-start",
                    link: !!o.drill,
                    nolink: !o.drill,
                });
            }),
        );
        return {
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            gtc: cols.map((c) => c.w || "1fr").join(" "),
            head: cols.map((c) => ({ h: c.h, a: c.a || "left" })),
            cells,
            showNote: !!p.note,
            note: p.note || "",
        };
    }
}
