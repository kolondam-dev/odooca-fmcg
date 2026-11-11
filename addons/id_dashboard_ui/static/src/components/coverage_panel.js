/** @odoo-module **/
import { Chart } from "@id_dashboard_ui/components/base_chart";
import { onWillUpdateProps, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { GeoMap, BarRows } from "@id_dashboard_ui/components/ported";
export class CoveragePanel extends Chart {
    static template = "id_dashboard_ui.CoveragePanel";
    static components = { GeoMap, BarRows };
    setup() {
        this.geo = useState({ levels: [], loading: false, error: "", selected: null });
        this.geoRequest = 0;
        onWillUpdateProps(next => {
            if (next.geoLoad !== this.props.geoLoad) {
                this.geoRequest++;
                Object.assign(this.geo, { levels: [], loading: false, error: "", selected: null });
            }
        });
    }
    get level() { return this.geo.levels.at(-1); }
    get head() {
        return this.geo.levels.length === 2 ? _t("Village / ward") : _t("District");
    }
    async descend({ code, name }) {
        if (this.geo.loading) return;
        if (this.geo.levels.length === 2) {
            this.geo.selected = code;
            return;
        }
        const request = ++this.geoRequest;
        this.geo.loading = true;
        this.geo.error = "";
        try {
            const features = await this.props.geoLoad(code);
            if (request !== this.geoRequest) return;
            if (!features.length) {
                this.geo.error = _t("No boundary data for this region.");
                return;
            }
            const bounds = [Infinity, Infinity, -Infinity, -Infinity];
            const shapes = features.map(feature => {
                const geometry = feature.geometry;
                const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
                const path = polygons.flatMap(polygon => polygon.map(ring =>
                    ring.map(([longitude, latitude], index) => {
                        const x = longitude, y = -latitude;
                        bounds[0] = Math.min(bounds[0], x);
                        bounds[1] = Math.min(bounds[1], y);
                        bounds[2] = Math.max(bounds[2], x);
                        bounds[3] = Math.max(bounds[3], y);
                        return (index ? "L" : "M") + x + "," + y;
                    }).join("") + "Z")).join("");
                return { code: feature.code, name: feature.name, path };
            });
            const [left, top, right, bottom] = bounds;
            const width = right - left, height = bottom - top;
            const pad = Math.max(width, height) * 0.05;
            const viewBox = [left - pad, top - pad, width + 2 * pad, height + 2 * pad].join(" ");
            this.geo.levels.push({ code, name, shapes, viewBox });
        } catch {
            if (request === this.geoRequest) this.geo.error = _t("Could not load geographic boundaries. Try again.");
        } finally {
            if (request === this.geoRequest) this.geo.loading = false;
        }
    }
    up() {
        this.geoRequest++;
        this.geo.levels.pop();
        Object.assign(this.geo, { loading: false, error: "", selected: null });
    }
    get amounts() { return this.props.geoAmounts?.[this.level?.code] || {}; }
    get ranking() {
        const amounts = this.amounts;
        const total = Object.values(amounts).reduce((sum, amount) => sum + amount, 0);
        const codes = new Set(this.level.shapes.map(shape => shape.code));
        const unassigned = Object.entries(amounts).reduce((sum, [code, amount]) =>
            codes.has(code) ? sum : sum + amount, 0);
        const rows = this.level.shapes.map(shape => ({ ...shape, net: amounts[shape.code] || 0 }));
        if (Object.keys(amounts).some(code => !codes.has(code))) {
            rows.push({ code: "", name: _t("Unassigned / outside map"), net: unassigned });
        }
        return rows.sort((a, b) => b.net - a.net || a.name.localeCompare(b.name)).map(row => ({
            ...row, value: this.num(row.net / 1e6),
            share: total ? this.num(row.net / total * 100) + "%" : "—",
        }));
    }
    fill(code) {
        if (code === this.geo.selected) return "var(--dk)";
        const amount = this.amounts[code] || 0;
        if (amount < 0) return "#f0a4a0";
        if (amount >= 300e6) return "var(--dk)";
        if (amount >= 120e6) return "var(--ac)";
        if (amount >= 60e6) return "var(--ac2)";
        return amount ? "var(--ac3)" : "var(--tint2)";
    }
    polygonKey(event, shape) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.descend(shape);
        }
    }
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
            geographic: Boolean(this.props.geoLoad),
            onDrill: this.props.geoLoad ? drill => this.descend(drill) : this.props.onDrill,
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
