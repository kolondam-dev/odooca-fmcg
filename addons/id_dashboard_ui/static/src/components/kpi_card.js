/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class KpiCard extends VisualComponent {
    static props = {
        kpi: { type: Object, optional: false },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.KpiCard";
    renderVals() {
        const k = this.props.kpi || {
            label: "Metric",
            num: "—",
            spark: [],
            delta: "",
            good: true,
        };
        const Ci = (x, y, r) =>
            `M${x - r} ${y}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
        const I = {
            chart: "M4 20V10M10 20V4M16 20v-8M22 20H2",
            undo: "M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3",
            wallet: "M3 7h16a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7zM3 7l12-3v3M16 14h3",
            target: Ci(12, 12, 9) + Ci(12, 12, 4.5),
            phone: "M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z",
            clock: Ci(12, 12, 9) + "M12 7v5l3 2",
            cart:
                "M3 4h2l2.5 11h10L20 8H6.5" + Ci(9, 19, 1.4) + Ci(17, 19, 1.4),
            pct: "M19 5L5 19" + Ci(7, 7, 2.3) + Ci(17, 17, 2.3),
            store: "M4 9l1.5-5h13L20 9M4 9v11h16V9M9 20v-6h6v6",
            truck:
                "M2 6h11v10H2zM13 9h4l3 3v4h-7" + Ci(7, 18, 2) + Ci(17, 18, 2),
            box: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
            cash: "M2 7h20v10H2z" + Ci(12, 12, 2.5),
            alert: "M12 3l10 18H2zM12 10v5M12 18v.5",
            calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
            users:
                Ci(9, 8, 3) +
                "M3 20a6 6 0 0112 0M17 8a3 3 0 010 6M21 20a5 5 0 00-4-5",
            layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
            trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
            flag: "M5 21V4M5 4h12l-2 4 2 4H5",
        };
        const sp = safeGeometry.series(k.spark),
            mx = Math.max(...sp),
            mn = Math.min(...sp);
        const pts = sp
            .map(
                (x, i) =>
                    `${((i * 100) / Math.max(1, sp.length - 1)).toFixed(1)},${(34 - ((x - mn) / (mx - mn || 1)) * 30).toFixed(1)}`,
            )
            .join(" ");
        let h = 0;
        for (const ch of String(k.label)) h = (h * 31 + ch.charCodeAt(0)) | 0;
        const up = String(k.delta).startsWith("+");
        return {
            icon: I[k.icon] || I.chart,
            label: k.label,
            menuLabel: "Source documents: " + k.label,
            gid: "id-kpi-" + this.__owl__.id + "-" + Math.abs(h),
            col: k.good ? "#1a7f4b" : "#b3261e",
            pts,
            hasPre: !!k.pre,
            pre: k.pre || "",
            hasCur: !!k.cur,
            cur: k.cur || "",
            num: k.num,
            unit: k.unit || "",
            hasBar: k.bar != null,
            bar: k.bar || 0,
            delta: k.delta,
            txt: k.txt || "",
            arrow: up ? "M12 19V5M6 11l6-6 6 6" : "M12 5v14M6 13l6 6 6-6",
        };
    }
}
