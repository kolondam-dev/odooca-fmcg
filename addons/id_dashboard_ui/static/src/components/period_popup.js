/** @odoo-module **/
import { VisualComponent } from "@id_dashboard_ui/components/base_visual";
import { safeGeometry } from "@id_dashboard_ui/core/geometry";
export class PeriodPopup extends VisualComponent {
    static props = {
        presets: { type: Array, optional: true },
        cmpOptions: { type: Array, optional: true },
        sel: { type: Array, optional: true },
        cmp: { type: Array, optional: true },
        legend: { type: String, optional: true },
        gran: { type: Array, optional: true },
        align: { type: String, optional: true },
        onEvent: { type: Function, optional: true },
        onDrill: { type: Function, optional: true },
    };
    static template = "id_dashboard_ui.PeriodPopup";
    renderVals() {
        const p = this.props;
        const MN = [
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ];
        const mk = (a) => {
            const [y, m, d1, d2, bg, fg] = a;
            const first = (new Date(y, m - 1, 1).getDay() + 6) % 7,
                n = new Date(y, m, 0).getDate();
            const out = [];
            ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"].forEach((t) =>
                out.push({ t, bg: "transparent", c: "#52627f" }),
            );
            for (let i = 0; i < first; i++)
                out.push({ t: "", bg: "transparent", c: "#12223f" });
            for (let d = 1; d <= n; d++) {
                const s = d >= d1 && d <= d2;
                out.push({
                    t: String(d),
                    bg: s ? bg : "transparent",
                    c: s ? fg : "#12223f",
                });
            }
            return out;
        };
        const now = new Date();
        const sel = p.sel || [
                now.getFullYear(),
                now.getMonth() + 1,
                1,
                now.getDate(),
            ],
            cmp = p.cmp || sel;
        const pr = p.presets || [];
        const co = p.cmpOptions || [];
        return {
            presets: pr.map((x) => ({
                a: x.a,
                b: x.b,
                bg: x.sel ? "var(--ac)" : "transparent",
                c: x.sel ? "#ffffff" : "#12223f",
                c2: x.sel ? "var(--chip)" : "#52627f",
            })),
            m1: MN[cmp[1] - 1] + " " + cmp[0],
            m2: MN[sel[1] - 1] + " " + sel[0],
            cal1: mk([cmp[0], cmp[1], cmp[2], cmp[3], "var(--ac3)", "#12223f"]),
            cal2: mk([sel[0], sel[1], sel[2], sel[3], "var(--ac)", "#ffffff"]),
            legend:
                p.legend ||
                "Biru tua: periode utama · biru muda: pembanding · Minggu libur operasional",
            gran: (p.gran || ["Harian", "Mingguan", "Bulanan"]).map((t, i) => ({
                t,
                bg: i === 0 ? "var(--ac)" : "#ffffff",
                c: i === 0 ? "#ffffff" : "#12223f",
            })),
            cmp: co.map((x) => ({
                a: x.a,
                b: x.b || "",
                bg: x.sel ? "var(--ac)" : "#ffffff",
            })),
            align: p.align || "Sejajarkan per hari kerja",
        };
    }
}
