/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class ComboChart extends VisualComponent {
    static props = {
        title: { type: String, optional: true },
    lineColor: { type: String, optional: true },
        bars: { type: Array, optional: false },
        line: { type: Array, optional: false },
        barMax: { type: [String, Number], optional: true },
        lineMin: { type: [String, Number], optional: true },
        lineMax: { type: [String, Number], optional: true },
        limit: { type: Object, optional: true },
        note: { type: String, optional: true },
        height: { type: [String, Number], optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.ComboChart";
    openBar(item) {
        if (item.drill) this.props.onDrill?.(item.drill);
    }
    keyBar(event, item) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.openBar(item);
        }
    }
    renderVals() {
        const p = this.props;
        const bars = p.bars || [];
        const line = p.line || [];
        const H = +(p.height || 0),
            ch = H ? H - 80 : 190,
            zt = 64,
            // Reserve the line-label band even when the percentage is at the bottom of its scale.
            bz = Math.max(0, ch - zt - 20 - 28);
        const bm = +(p.barMax || 6.5),
            lmn = +(p.lineMin || 0),
            lmx = +(p.lineMax || 10);
        const n = bars.length;
        const LY = (v) => 100 - ((v - lmn) / (lmx - lmn || 1)) * 100;
        const lim = p.limit;
        return {
      lineColor:p.lineColor || "var(--hl)",
            card: "background:#fff;border:1px solid #d5e0f2;border-radius:6px;padding:12px 14px;",
            hh: H ? H + "px" : "auto",
            showTitle: !!p.title,
            title: p.title || "",
            note: p.note || "",
            ch,
            zt,
            cols: bars.map((b, i) => ({
                l: b.l,
                drill: b.drill,
                bv: b.t,
                bh: Math.round((Math.abs(b.v) / bm) * bz * 0.92),
                bc: b.c || (b.v < 0 ? "#b3261e" : "var(--ac)"),
                lineTop: LY(Number.isFinite(line[i]?.v) ? line[i].v : lmn).toFixed(1),
                hasLine: Number.isFinite(line[i]?.v),
                lv: line[i]?.t || "",
            })),
            lp: line.map((q, i) => Number.isFinite(q.v)
                ? `${i && Number.isFinite(line[i - 1]?.v) ? "L" : "M"}${(((i + 0.5) / Math.max(1, n)) * 100).toFixed(2)},${LY(q.v).toFixed(2)}`
                : "").join(" "),
            ly: lim ? LY(lim.v).toFixed(2) : 0,
            lo: lim ? 1 : 0,
            limitText: lim ? lim.t : "",
            lyp: lim ? ((LY(lim.v) / 100) * zt).toFixed(1) : 0,
        };
    }
}
