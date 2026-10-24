import { markup } from "@odoo/owl";

// Glyph UI sidebar (outline 24x24). Ikon aplikasi memakai ikon bawaan Odoo
// (webIconData / webIcon), bukan set ini.
const svg = (inner) => markup(`<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${inner}</svg>`);

export const ICONS = {
    search: svg('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>'),
    chevron: svg('<path d="m9 6 6 6-6 6"/>'),
    collapse: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>'),
};
