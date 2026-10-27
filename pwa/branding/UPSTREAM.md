# Odoo brand assets

Official Odoo 19 source tree `b7a10b63a65dcb803948410b0b9ad2e83d5fc0be`.

- Wordmark: `addons/web/static/img/odoo_logo.svg`.
- oi-odoo: outline extracted from `addons/web/static/lib/odoo_ui_icons/fonts/odoo_ui_icons.woff2`; glyph identified through sibling style.css. No complete icon font shipped.
- Icon license copied to public/licenses/Odoo-icons-LICENSE.md; Odoo wordmark/trademarks belong to Odoo SA.
- Navy background, FMCG badge and Mobile composition follow owner reference.
- Runtime assets use vector outlines, no remote font or CDN.

Display wordmark recolors original gray/purple to #b7c8e3/#d3a5c4 for navy contrast. Typography outlines for FMCG/Mobile use Inter Variable at weight 650 (existing OFL font). icon.svg and brand-logo.svg are editable vector sources; committed PNGs are raster derivatives at their declared dimensions.
