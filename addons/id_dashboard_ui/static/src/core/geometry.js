/** @odoo-module **/
export const safeGeometry = {
    series(values) {
        const clean = (values || []).filter(Number.isFinite);
        return clean.length ? clean : [0];
    },
    ratio(value, max) {
        return Number.isFinite(value) && Number.isFinite(max) && max > 0
            ? Math.max(0, Math.min(100, (100 * value) / max))
            : 0;
    },
};
