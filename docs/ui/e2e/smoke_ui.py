"""Smoke test UI (Playwright). Prasyarat: Odoo berjalan, id_ui, id_ui_shell, id_ui_form
terpasang, pengguna uji punya akses Penjualan, ada minimal dua order. Tes pager
gagal bila tidak ada record kedua; tidak boleh lulus tanpa navigasi. Pengujian mengganti tata letak pengguna ke klasik lalu
memulihkannya ke sidebar.

    python smoke_ui.py http://localhost:8069 <id_sale_order>
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8069"
ORDER = sys.argv[2] if len(sys.argv) > 2 else "1"
INVOICE = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("UI_TEST_INVOICE")
if not INVOICE:
    raise SystemExit("UI smoke requires the populated invoice id from UI_FIXTURE as argument 3")


TITLE_STATE = """(() => {
    const sb = document.querySelector('.o_form_statusbar');
    const h = sb && sb.querySelector(':scope > .id_header_title');
    const blk = document.querySelector('.o_form_sheet > .oe_title');
    const left = sb && sb.querySelector('.o_statusbar_buttons');
    const right = sb && sb.querySelector('.o_field_statusbar, .o_statusbar_status');
    const r = (e) => e.getBoundingClientRect();
    const off = h && left && right ? Math.round((r(h).left + r(h).right) / 2 - (r(left).right + r(right).left) / 2) : null;
    return {
        headers: sb ? sb.querySelectorAll(':scope > .id_header_title').length : 0,
        main: h && h.querySelector('.id_header_title__main') ? h.querySelector('.id_header_title__main').textContent : null,
        caption: h && h.querySelector('.id_header_title__caption') ? h.querySelector('.id_header_title__caption').textContent : null,
        blockDisplay: blk ? getComputedStyle(blk).display : null,
        blockControls: blk ? blk.querySelectorAll('input:not([type=hidden]), select, textarea').length : 0,
        centerOffset: off,
    };
})()"""


PAGE_BOX_PROBE = """(() => {
    const box = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return {
            tag: el.tagName,
            className: String(el.className || '').slice(0, 120),
            left: Math.round(r.left * 100) / 100,
            right: Math.round(r.right * 100) / 100,
            width: Math.round(r.width * 100) / 100,
            offsetWidth: el.offsetWidth,
            clientWidth: el.clientWidth,
            scrollWidth: el.scrollWidth,
            computedWidth: cs.width,
            boxSizing: cs.boxSizing,
            paddingLeft: cs.paddingLeft,
            paddingRight: cs.paddingRight,
            overflowX: cs.overflowX,
            scrollbarWidth: el.offsetWidth - el.clientWidth
        };
    };
    return {
        viewport: { client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth },
        content: box(document.querySelector('.o_content')),
        formView: box(document.querySelector('.o_form_view')),
        listView: box(document.querySelector('.o_list_view')),
        listRenderer: box(document.querySelector('.o_list_renderer'))
    };
})()"""


async def main():
    failures = []

    def check(name, ok):
        print(("PASS " if ok else "FAIL ") + name)
        if not ok:
            failures.append(name)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 860})
        errors = []
        def record_error(error):
            detail = error.stack or str(error)
            errors.append(detail)
            print("BROWSER ERROR:", detail, flush=True)
        page.on("pageerror", record_error)
        await page.goto(f"{BASE}/web/login")
        await page.fill("input[name=login]", os.environ.get("UI_TEST_LOGIN", "admin"))
        await page.fill("input[name=password]", os.environ.get("UI_TEST_PASSWORD", "admin"))
        await page.click("button[type=submit]")
        await page.wait_for_timeout(12000)
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/{ORDER}")
        await page.wait_for_timeout(8000)

        check("body punya kelas sidebar", "id-shell-sidebar" in await page.evaluate("document.body.className"))
        check("sidebar berisi aplikasi", await page.locator(".id_sidebar [data-nav]").count() >= 3)
        check("judul topbar = nama aplikasi", (await page.locator(".o_menu_brand").first.inner_text()).strip() != "")
        check("pencarian menu ada", await page.locator(".id_menu_search").count() == 1)
        check("fokus awal di pencarian menu", await page.evaluate("document.activeElement.classList.contains('id_menu_search')"))
        sh = await page.evaluate("(() => { const s = document.querySelector('.id_menu_search').getBoundingClientRect(); const n = document.querySelector('.o_main_navbar').getBoundingClientRect(); return [s.height, Math.abs((s.top + s.height / 2) - (n.top + n.height / 2))]; })()")
        check("pencarian pendek dan rata tengah", sh[0] <= 40 and sh[1] <= 2)
        check("navbar tanpa garis bawah", await page.evaluate("getComputedStyle(document.querySelector('.o_main_navbar')).borderBottomWidth") == "0px")
        check("tab seksi tidak ada di navbar", not await page.locator(".o_main_navbar .o_menu_sections").is_visible())
        order = await page.evaluate("(() => { const s = document.querySelector('.id_menu_search').getBoundingClientRect(); const t = document.querySelector('.o_menu_brand').getBoundingClientRect(); const y = document.querySelector('.o_menu_systray').getBoundingClientRect(); return [s.right <= t.left, t.right <= y.left]; })()")
        check("pencarian di kiri, judul di tengah", order[0] and order[1])
        check("FMCG brandbox sudut tegas (tanpa rounded)", await page.evaluate("getComputedStyle(document.querySelector('.id_brandbox')).borderRadius") == "0px")
        check("ikon aplikasi duo-tone saat diam", await page.evaluate("getComputedStyle(document.querySelector('.id_item:not(.is-current) .id_appicon--duo')).filter.includes('id_duotone')"))
        before = await page.evaluate("document.querySelector('.id_sidebar__nav').clientWidth")
        await page.hover(".id_item:not(.is-current)")
        await page.wait_for_timeout(600)
        after = await page.evaluate("[document.querySelector('.id_sidebar__nav').clientWidth, document.querySelector('.id_sidebar__nav').offsetWidth]")
        check("hover tidak menyusutkan menu (tanpa scrollbar)", after[0] == before and after[0] == after[1])
        check("ikon berwarna asli saat hover", await page.evaluate("getComputedStyle(document.querySelector('.id_item:hover .id_appicon--color')).opacity") == "1")
        check("menu panel aktif tebal tanpa latar", await page.evaluate("(() => { const a = document.querySelector('.id_pitem.is-active'); const c = getComputedStyle(a); return a && +c.fontWeight >= 700 && c.backgroundColor === 'rgba(0, 0, 0, 0)'; })()"))
        check("panel seksi ada", await page.locator(".id_panel .id_pitem").count() >= 3)
        check("item aktif sidebar persegi", await page.evaluate("getComputedStyle(document.querySelector('.id_item.is-current')).borderRadius") == "0px")
        tabs = await page.evaluate("[...document.querySelectorAll('.o_notebook_headers .nav-link')].map(e=>e.textContent.trim())")
        check("chatter jadi tab terakhir", bool(tabs) and tabs[-1] in ("Messages & Activities", "Pesan & Aktivitas"))
        check("tidak ada chatter di samping", await page.locator(".o-aside").count() == 0)
        h = await page.evaluate("[document.documentElement.scrollHeight, window.innerHeight]")
        check("halaman tidak scroll", h[0] <= h[1])

        await page.keyboard.press("Tab")
        check("Tab dari pencarian ke sidebar", await page.evaluate("document.activeElement.classList.contains('id_item')"))
        await page.keyboard.press("Tab")
        check("Tab dari sidebar ke isi", await page.evaluate("!!document.activeElement.closest('.o_action_manager')"))
        await page.keyboard.press("Alt+m")
        focus = await page.evaluate("document.activeElement.classList.contains('id_item')")
        check("Alt+M memfokuskan sidebar", focus)
        await page.keyboard.press("ArrowRight")
        check("panah kanan masuk ke panel seksi", await page.evaluate("!!document.activeElement.closest('.id_panel')"))
        await page.keyboard.press("Alt+m")
        await page.keyboard.press("Alt+b")
        await page.wait_for_timeout(400)
        check("Alt+B menciutkan", "id-shell-collapsed" in await page.evaluate("document.body.className"))
        await page.keyboard.press("Alt+b")

        # --- Form: judul murni di tengah statusbar (field tidak dipindah), footer sticky ---
        await page.keyboard.press("Escape")
        t = await page.evaluate(TITLE_STATE)
        check("judul murni tepat satu di header statusbar", t["headers"] == 1)
        check("blok judul asli di sheet disembunyikan (tanpa duplikat)", t["blockDisplay"] == "none")
        check("judul tepat di tengah antara tombol aksi dan pipeline", t["centerOffset"] is not None and abs(t["centerOffset"]) <= 2)
        check("footer total sticky", await page.evaluate("(() => { const s = document.querySelector('.o_form_sheet .oe_subtotal_footer'); let f = s; while (f && f !== document.body && getComputedStyle(f).position !== 'sticky') f = f.parentElement; return !!f && f !== document.body; })()"))

        # Shared geometry audit for both real populated transaction forms. The script
        # determines the sticky threshold from the footer's natural position and the
        # scrollport geometry; percentages alone are not evidence of sticky engagement.
        FOOTER_SCROLL_AUDIT = """((lineFieldName) => {
            const subtotals = [...document.querySelectorAll('.o_form_sheet .oe_subtotal_footer')];
            if (!subtotals.length) return { ok: false, reason: 'subtotal footer missing' };
            // Collect every sticky ancestor of the native subtotal panel. More than
            // one means nested sticky containers, which the audit must reject.
            const stickySet = new Set();
            for (const panel of subtotals) {
                let node = panel;
                while (node && node !== document.body) {
                    if (getComputedStyle(node).position === 'sticky') stickySet.add(node);
                    node = node.parentElement;
                }
            }
            const stickyGroups = [...stickySet];
            if (stickyGroups.length !== 1) return { ok: false, reason: 'expected exactly one sticky footer container', stickyGroupCount: stickyGroups.length, subtotalCount: subtotals.length };
            const footer = stickyGroups[0];
            const describeBox = (el) => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return {
                    tag: el.tagName,
                    className: String(el.className || '').slice(0, 120),
                    left: Math.round(r.left * 100) / 100,
                    right: Math.round(r.right * 100) / 100,
                    width: Math.round(r.width * 100) / 100,
                    offsetWidth: el.offsetWidth,
                    clientWidth: el.clientWidth,
                    scrollWidth: el.scrollWidth,
                    computedWidth: cs.width,
                    boxSizing: cs.boxSizing,
                    paddingLeft: cs.paddingLeft,
                    paddingRight: cs.paddingRight,
                    borderLeft: cs.borderLeftWidth,
                    borderRight: cs.borderRightWidth,
                    marginLeft: cs.marginLeft,
                    marginRight: cs.marginRight,
                    overflowX: cs.overflowX,
                    scrollbarWidth: el.offsetWidth - el.clientWidth
                };
            };
            let owner = footer.parentElement;
            while (owner && owner !== document.body) {
                const style = getComputedStyle(owner);
                if (owner.scrollHeight > owner.clientHeight + 4 && /(auto|scroll)/.test(style.overflowY)) break;
                owner = owner.parentElement;
            }
            if (!owner || owner === document.body) return { ok: false, reason: 'no overflowing scroll owner' };
            const lineField = document.querySelector('.o_form_sheet [name="' + lineFieldName + '"]');
            if (!lineField) return { ok: false, reason: 'transaction line field missing', lineFieldName };
            let items = [...lineField.querySelectorAll('.o_data_row')];
            let itemKind = 'list-row';
            if (!items.length) {
                items = [...lineField.querySelectorAll('.o_kanban_record')];
                itemKind = 'kanban-card';
            }
            if (items.length < 10) return { ok: false, reason: 'populated transaction line items required', itemCount: items.length, itemKind };
            const maxScroll = Math.max(0, owner.scrollHeight - owner.clientHeight);
            if (maxScroll < 40) return { ok: false, reason: 'form did not produce meaningful vertical overflow', maxScroll };
            const initialScroll = owner.scrollTop;
            owner.scrollTop = 0;
            const ownerRect = owner.getBoundingClientRect();
            const scrollportTop = ownerRect.top + owner.clientTop;
            const scrollportBottom = scrollportTop + owner.clientHeight;
            const computed = getComputedStyle(footer);
            const bottomInset = parseFloat(computed.bottom) || 0;
            // Measure the true normal-flow box: sticky is disabled only for this
            // measurement, then the original inline style is restored exactly.
            const originalStyle = footer.getAttribute('style');
            footer.style.setProperty('position', 'static', 'important');
            footer.style.setProperty('top', 'auto', 'important');
            footer.style.setProperty('bottom', 'auto', 'important');
            const naturalRect = footer.getBoundingClientRect();
            const containingBlock = footer.parentElement;
            const containingRect = containingBlock.getBoundingClientRect();
            footer.style.removeProperty('bottom');
            footer.style.removeProperty('top');
            footer.style.removeProperty('position');
            if (originalStyle === null) footer.removeAttribute('style');
            else footer.setAttribute('style', originalStyle);
            const naturalFooterTop = naturalRect.top;
            const naturalFooterBottom = naturalRect.bottom;
            const naturalFooterHeight = naturalRect.height;
            const containingBlockTopAtZero = containingRect.top;
            const containingBlockBottomAtZero = containingRect.bottom;
            const containingBlockHeight = containingRect.height;
            // A sticky box may only shift while its *margin box* stays inside the
            // containing block's content box, so the interval has to use the
            // padding box (padding + border) and the element's own margins.
            const cbStyle = getComputedStyle(containingBlock);
            const cbBorderTop = parseFloat(cbStyle.borderTopWidth) || 0;
            const cbBorderLeft = parseFloat(cbStyle.borderLeftWidth) || 0;
            const cbPadTop = parseFloat(cbStyle.paddingTop) || 0;
            const cbPadBottom = parseFloat(cbStyle.paddingBottom) || 0;
            const cbPadLeft = parseFloat(cbStyle.paddingLeft) || 0;
            const cbPadRight = parseFloat(cbStyle.paddingRight) || 0;
            const containingBlockContentTop = containingRect.top + cbBorderTop + cbPadTop;
            const containingBlockContentBottom = containingRect.top + cbBorderTop
                + containingBlock.clientHeight - cbPadBottom;
            const containingBlockContentLeft = containingRect.left + cbBorderLeft + cbPadLeft;
            const containingBlockContentWidth = containingBlock.clientWidth - cbPadLeft - cbPadRight;
            const marginTop = parseFloat(computed.marginTop) || 0;
            const marginBottom = parseFloat(computed.marginBottom) || 0;
            const pinnedBottom = scrollportBottom - bottomInset;
            const pinnedTop = pinnedBottom - naturalFooterHeight;
            // Bottom sticky pins while the normal-flow bottom is still below the
            // scrollport inset, and only while the containing block can surround
            // the shifted margin box. It releases once the natural bottom crosses
            // the inset (or the containing block ends first).
            const releaseAt = Math.max(0, Math.round(naturalFooterBottom - pinnedBottom));
            const earliestPinnedTop = containingBlockContentTop + marginTop;
            const latestPinnedBottom = containingBlockContentBottom - marginBottom;
            const pinStart = Math.max(0, Math.min(maxScroll, Math.ceil(earliestPinnedTop - pinnedTop)));
            const pinEnd = Math.max(0, Math.min(maxScroll, Math.floor(releaseAt), Math.floor(latestPinnedBottom - pinnedBottom)));
            const pinSpan = Math.max(0, pinEnd - pinStart);
            const candidates = [
                pinStart,
                pinStart + pinSpan * 0.25,
                pinStart + pinSpan * 0.5,
                pinStart + pinSpan * 0.75,
                pinEnd
            ].map(y => Math.max(0, Math.min(maxScroll, Math.round(y))));
            const samples = [...new Set(candidates)].sort((a, b) => a - b);
            const pinned = [];
            for (const y of samples) {
                if (y < pinStart - 1 || y > pinEnd + 1 || pinSpan < 8) continue;
                owner.scrollTop = y;
                const fr = footer.getBoundingClientRect();
                const or = owner.getBoundingClientRect();
                const cr = containingBlock.getBoundingClientRect();
                const sampleScrollportTop = or.top + owner.clientTop;
                const sampleScrollportBottom = sampleScrollportTop + owner.clientHeight;
                const samplePinnedBottom = sampleScrollportBottom - bottomInset;
                const cbs = getComputedStyle(containingBlock);
                const sampleCbContentTop = cr.top + (parseFloat(cbs.borderTopWidth) || 0) + (parseFloat(cbs.paddingTop) || 0);
                const sampleCbContentBottom = cr.top + (parseFloat(cbs.borderTopWidth) || 0)
                    + containingBlock.clientHeight - (parseFloat(cbs.paddingBottom) || 0);
                pinned.push({
                    scrollTop: owner.scrollTop,
                    footerTop: fr.top,
                    footerBottom: fr.bottom,
                    pinnedBottom: samplePinnedBottom,
                    scrollportTop: sampleScrollportTop,
                    scrollportBottom: sampleScrollportBottom,
                    containingBlockTop: cr.top,
                    containingBlockBottom: cr.bottom,
                    containingBlockContentTop: sampleCbContentTop,
                    containingBlockContentBottom: sampleCbContentBottom,
                    drift: Math.abs(fr.bottom - samplePinnedBottom),
                    insideScrollport: fr.top >= sampleScrollportTop - 2 && fr.bottom <= sampleScrollportBottom + 2,
                    insideContainingBlock: fr.top - marginTop >= sampleCbContentTop - 1
                        && fr.bottom + marginBottom <= sampleCbContentBottom + 1,
                    insideContainingBlockHorizontally: fr.left >= containingBlockContentLeft - 1
                        && fr.right <= containingBlockContentLeft + containingBlockContentWidth + 1
                });
            }
            owner.scrollTop = 0;
            const startFooterRect = footer.getBoundingClientRect();
            const footerVisibleAtStart = startFooterRect.top < scrollportBottom - 1 && startFooterRect.bottom > scrollportTop + 1;
            // A bottom-sticky box cannot pin while its containing block still starts
            // below the pinned position; it is then clamped to the containing block
            // content edge. Record that honestly instead of treating it as drift.
            const startOverflowBelow = Math.max(0, startFooterRect.bottom - scrollportBottom);
            const startClampExplained = startOverflowBelow <= 0
                || startFooterRect.top <= containingBlockContentTop + marginTop + 1;
            const overflowAncestors = [];
            let ancestor = footer.parentElement;
            while (ancestor && ancestor !== document.body) {
                const cs = getComputedStyle(ancestor);
                if (/(auto|scroll|hidden|clip)/.test(cs.overflowX + ' ' + cs.overflowY)) {
                    overflowAncestors.push({
                        tag: ancestor.tagName,
                        className: String(ancestor.className || '').slice(0, 160),
                        overflowX: cs.overflowX,
                        overflowY: cs.overflowY,
                        clientWidth: ancestor.clientWidth,
                        scrollWidth: ancestor.scrollWidth,
                        clientHeight: ancestor.clientHeight,
                        scrollHeight: ancestor.scrollHeight
                    });
                }
                ancestor = ancestor.parentElement;
            }
            owner.scrollTop = maxScroll;
            const footerRect = footer.getBoundingClientRect();
            const scrollport = owner.getBoundingClientRect();
            const endScrollportTop = scrollport.top + owner.clientTop;
            const endScrollportBottom = endScrollportTop + owner.clientHeight;
            const endPinnedBottom = endScrollportBottom - bottomInset;
            const lastItem = items[items.length - 1];
            lastItem.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            const itemRect = lastItem.getBoundingClientRect();
            const footerAfterItemScroll = footer.getBoundingClientRect();
            const isItemVisibleAndUncovered = (rect, top, bottom, footerTop) =>
                rect.top >= top - 2 && rect.bottom <= footerTop + 2
                && rect.bottom <= bottom + 2 && rect.top < footerTop;
            const lastItemVisibleAndUncovered = isItemVisibleAndUncovered(
                itemRect, endScrollportTop, endScrollportBottom, footerAfterItemScroll.top
            );
            // Negative control: an item wholly above the scrollport must never pass.
            const hiddenItemRejected = !isItemVisibleAndUncovered(
                { top: endScrollportTop - 50, bottom: endScrollportTop - 10 },
                endScrollportTop, endScrollportBottom, footerAfterItemScroll.top
            );
            const form = document.querySelector('.o_form_sheet');
            const firstCell = lastItem.querySelector('td:not(.o_list_record_selector)') || lastItem;
            const result = {
                ok: true,
                lineFieldName,
                itemKind,
                maxScroll,
                itemCount: items.length,
                rowCount: items.filter(e => e.classList.contains('o_data_row')).length,
                stickyGroupCount: stickyGroups.length,
                stickyElement: { tag: footer.tagName, className: String(footer.className || '').slice(0, 160) },
                naturalFooterTop,
                naturalFooterBottom,
                naturalFooterHeight,
                scrollportTop,
                scrollportBottom,
                containingBlockTopAtZero,
                containingBlockBottomAtZero,
                containingBlockHeight,
                containingBlockContentTop,
                containingBlockContentBottom,
                containingBlockContentLeft,
                containingBlockContentWidth,
                containingBlockPadding: { top: cbPadTop, bottom: cbPadBottom, left: cbPadLeft, right: cbPadRight },
                footerMargin: { top: marginTop, bottom: marginBottom },
                bottomInset,
                pinnedTop,
                releaseAt,
                pinStart,
                pinEnd,
                pinSpan,
                computedSticky: {
                    position: computed.position,
                    top: computed.top,
                    bottom: computed.bottom,
                    marginTop: computed.marginTop,
                    marginBottom: computed.marginBottom
                },
                overflowAncestors,
                stickySamples: pinned,
                stickyEngagedAtLeastTwice: pinSpan >= 8 && pinned.length >= 2,
                stickyPinned: pinSpan >= 8 && pinned.length >= 2
                    && pinned.every(p => p.drift <= 1 && p.insideScrollport && p.insideContainingBlock
                        && p.insideContainingBlockHorizontally),
                footerVisibleAtStart,
                startOverflowBelow,
                startClampExplained,
                footerInScrollport: footerAfterItemScroll.top >= endScrollportTop - 2 && footerAfterItemScroll.bottom <= endScrollportBottom + 2,
                releasedAtEnd: maxScroll > pinEnd + 8 ? footerAfterItemScroll.bottom < endPinnedBottom - 8 : null,
                lastItemVisibleAndUncovered,
                lastRowVisibleAndUncovered: lastItemVisibleAndUncovered,
                hiddenRowCounterexampleRejected: hiddenItemRejected,
                horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
                    || owner.scrollWidth > owner.clientWidth + 1
                    || footer.scrollWidth > footer.clientWidth + 1
                    || (!!form && form.scrollWidth > form.clientWidth + 1),
                ownerHorizontalOverflow: owner.scrollWidth > owner.clientWidth + 1,
                horizontalMetrics: {
                    viewport: { client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth },
                    owner: describeBox(owner),
                    formView: describeBox(document.querySelector('.o_form_view')),
                    sheet: describeBox(form),
                    footer: describeBox(footer),
                    footerBox: { left: footerRect.left, right: footerRect.right },
                    ownerChildren: [...(owner ? owner.children : [])].map(describeBox),
                    unclippedOverflowNodes: [...(form ? form.querySelectorAll('*') : [])]
                        .map(el => ({ el, rect: el.getBoundingClientRect() }))
                        .filter(({ el, rect }) => el.offsetWidth || el.offsetHeight)
                        .filter(({ el, rect }) => {
                            const sheetRect = form.getBoundingClientRect();
                            const outside = rect.right > sheetRect.right + 1 || rect.left < sheetRect.left - 1;
                            if (!outside) return false;
                            let n = el.parentElement;
                            while (n && n !== form) {
                                const cs = getComputedStyle(n);
                                if (/(hidden|clip|auto|scroll)/.test(cs.overflowX)) return false;
                                n = n.parentElement;
                            }
                            return true;
                        })
                        .map(({ el, rect }) => {
                            const cs = getComputedStyle(el);
                            return {
                                tag: el.tagName,
                                className: String(el.className || '').slice(0, 120),
                                left: Math.round(rect.left * 100) / 100,
                                right: Math.round(rect.right * 100) / 100,
                                width: Math.round(rect.width * 100) / 100,
                                computedWidth: cs.width,
                                minWidth: cs.minWidth,
                                overflowX: cs.overflowX
                            };
                        })
                        .slice(0, 10),
                    culpritNodes: [...document.querySelectorAll('body *')].map(el => {
                        const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
                        return {
                            tag: el.tagName,
                            id: el.id || '',
                            className: String(el.className || '').slice(0, 140),
                            left: Math.round(r.left * 100) / 100,
                            right: Math.round(r.right * 100) / 100,
                            width: Math.round(r.width * 100) / 100,
                            clientWidth: el.clientWidth,
                            scrollWidth: el.scrollWidth,
                            minWidth: cs.minWidth,
                            computedWidth: cs.width,
                            overflowX: cs.overflowX
                        };
                    }).filter(x => x.scrollWidth > x.clientWidth + 2 || x.right > document.documentElement.clientWidth + 2 || x.left < -2)
                      .sort((a,b) => Math.max(b.scrollWidth-b.clientWidth, b.right-document.documentElement.clientWidth, -b.left) - Math.max(a.scrollWidth-a.clientWidth, a.right-document.documentElement.clientWidth, -a.left))
                      .slice(0, 12)
                },
                lastCellPresent: !!firstCell,
            };
            owner.scrollTop = initialScroll;
            return result;
        })""";

        async def audit_footer(form_label, line_field):
            result = await page.evaluate(f"({FOOTER_SCROLL_AUDIT})({line_field!r})")
            print(f"{form_label} footer scroll diagnostics:", result, flush=True)
            check(f"{form_label}: real scroll owner and populated transaction line items",
                  result.get("ok") and result.get("maxScroll", 0) >= 40 and result.get("itemCount", 0) >= 10)
            check(f"{form_label}: footer is visible at the start of the scroll contract",
                  result.get("ok") and result.get("footerVisibleAtStart"))
            check(f"{form_label}: any footer offset at scroll start is the containing-block clamp, not drift",
                  result.get("ok") and result.get("startClampExplained"))
            check(f"{form_label}: sticky interval derived from normal-flow and containing-block geometry",
                  result.get("ok") and result.get("stickyEngagedAtLeastTwice"))
            check(f"{form_label}: footer remains pinned to scrollport in the derived sticky interval",
                  result.get("ok") and result.get("stickyPinned"))
            check(f"{form_label}: footer stays inside scrollport",
                  result.get("ok") and result.get("footerInScrollport"))
            if result.get("releasedAtEnd") is not None:
                check(f"{form_label}: footer releases after the pinned interval",
                      result.get("ok") and result.get("releasedAtEnd"))
            check(f"{form_label}: last transaction item is visible and uncovered",
                  result.get("ok") and result.get("lastRowVisibleAndUncovered"))
            check(f"{form_label}: no horizontal overflow in page, scroll owner, or footer",
                  result.get("ok") and not result.get("horizontalOverflow"))
            if result.get("ok") and result.get("lastCellPresent"):
                if result.get("itemKind") == "kanban-card":
                    cell = page.locator(f'.o_form_sheet [name="{line_field}"] .o_kanban_record').last
                else:
                    cell = page.locator(f'.o_form_sheet [name="{line_field}"] .o_data_row').last.locator("td:not(.o_list_record_selector)").first
                try:
                    await cell.click(trial=True, timeout=3000)
                    check(f"{form_label}: last transaction item passes Playwright actionability", True)
                    post_actionability = await page.evaluate("""(lineFieldName) => {
                        const subtotal = document.querySelector('.o_form_sheet .oe_subtotal_footer');
                        let footer = subtotal;
                        while (footer && footer !== document.body && getComputedStyle(footer).position !== 'sticky') {
                            footer = footer.parentElement;
                        }
                        if (footer === document.body) footer = null;
                        const list = document.querySelector('.o_form_sheet [name="' + lineFieldName + '"]');
                        let items = list ? [...list.querySelectorAll('.o_data_row')] : [];
                        if (list && !items.length) items = [...list.querySelectorAll('.o_kanban_record')];
                        const item = items.length ? items[items.length - 1] : null;
                        let owner = item && item.parentElement;
                        while (owner && owner !== document.body) {
                            const cs = getComputedStyle(owner);
                            if (owner.scrollHeight > owner.clientHeight + 4 && /(auto|scroll)/.test(cs.overflowY)) break;
                            owner = owner.parentElement;
                        }
                        if (!owner || owner === document.body) {
                            const fallback = document.querySelector('.o_form_sheet_bg');
                            if (fallback && fallback.scrollHeight > fallback.clientHeight + 4) owner = fallback;
                        }
                        if (!footer || !item || !owner || owner === document.body) return {
                            ok: false, reason: 'missing footer, item, or scroll owner after trial click',
                            footerFound: !!footer, itemFound: !!item,
                            candidateScroll: owner && owner !== document.body ? {
                                className: String(owner.className || ''),
                                scrollHeight: owner.scrollHeight,
                                clientHeight: owner.clientHeight
                            } : null
                        };
                        const fr = footer.getBoundingClientRect(), rr = item.getBoundingClientRect(), or = owner.getBoundingClientRect();
                        const top = or.top + owner.clientTop, bottom = top + owner.clientHeight;
                        return {
                            ok: true, scrollTop: owner.scrollTop,
                            item: { top: rr.top, bottom: rr.bottom },
                            footer: { top: fr.top, bottom: fr.bottom },
                            scrollport: { top, bottom },
                            visibleAndUncovered: rr.top >= top - 2 && rr.bottom <= bottom + 2 && rr.bottom <= fr.top + 2 && rr.top < fr.top
                        };
                    }""", line_field)
                    print(f"{form_label} geometry after trial actionability:", post_actionability, flush=True)
                    check(f"{form_label}: last item remains visible and uncovered after Playwright actionability",
                          post_actionability.get("ok") and post_actionability.get("visibleAndUncovered"))
                except Exception as exc:
                    print(f"{form_label} last-item actionability:", str(exc), flush=True)
                    check(f"{form_label}: last transaction item passes Playwright actionability", False)
            else:
                check(f"{form_label}: last transaction item passes Playwright actionability", False)

        await audit_footer("SO", "order_line")

        # --- Divider systray: jumlah = item tampil - 1 (normal dan mode debug) ---
        COUNT = """(() => { const k = [...document.querySelector('.o_menu_systray').children].filter(e => e.offsetWidth > 0 && !e.querySelector(':scope > .o_mobile_menu_toggle')); const d = k.filter(e => getComputedStyle(e, '::before').content === '\"\"').length; return [k.length, d]; })()"""
        n, d = await page.evaluate(COUNT)
        check(f"divider systray = item - 1 (normal: {n} item, {d} divider)", d == n - 1)
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/{ORDER}?debug=1")
        await page.wait_for_timeout(8000)
        n, d = await page.evaluate(COUNT)
        check(f"divider systray = item - 1 (debug: {n} item, {d} divider)", d == n - 1)

        # --- Navigasi form (pager) dari daftar: tanpa error, judul tetap satu ---
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding")
        await page.wait_for_timeout(6000)
        # Filter bawaan "Penawaran Saya" bisa kosong dan memunculkan data contoh; lepas filternya.
        if await page.locator(".o_facet_remove").count():
            await page.locator(".o_facet_remove").first.click()
            await page.wait_for_timeout(2500)
        await page.locator(".o_data_row").first.click()
        await page.wait_for_timeout(3000)
        title = page.locator(".o_form_statusbar > .id_header_title .id_header_title__main")
        first_title = (await title.inner_text()).strip()
        next_button = page.locator(".o_pager_next")
        if not await next_button.count() or not await next_button.is_enabled():
            raise AssertionError("Pager requires at least two accessible orders; navigation was not tested")
        await next_button.click()
        await page.wait_for_function(
            "first => document.querySelector('.id_header_title__main')?.textContent.trim() !== first",
            arg=first_title,
        )
        second_title = (await title.inner_text()).strip()
        check("pager membuka record berbeda", bool(second_title) and second_title != first_title)
        check("judul tunggal pada record kedua", await title.count() == 1)
        await page.locator(".o_pager_previous").click()
        await page.wait_for_function(
            "first => document.querySelector('.id_header_title__main')?.textContent.trim() === first",
            arg=first_title,
        )
        check("pager kembali ke record pertama", (await title.inner_text()).strip() == first_title)
        check("judul tetap satu setelah pager", await title.count() == 1)

        # --- Layar kecil memakai NavBar bawaan: tidak ada header judul buatan ---
        await page.set_viewport_size({"width": 390, "height": 800})
        await page.wait_for_timeout(2000)
        check("layar kecil: tanpa header judul buatan", (await page.evaluate(TITLE_STATE))["headers"] == 0)
        await page.set_viewport_size({"width": 1440, "height": 860})
        await page.wait_for_timeout(2000)
        check("layar besar lagi: header judul kembali", (await page.evaluate(TITLE_STATE))["headers"] == 1)

        # --- Ganti ke tata letak klasik: judul kembali ke sheet; lalu pulihkan ke sidebar ---
        async def switch_layout(label):
            await page.click(".o_user_menu button")
            await page.get_by_text(label).first.click()
            await page.wait_for_timeout(2500)
        try:
            await switch_layout("Layout: switch to Classic")
            back = await page.evaluate(TITLE_STATE)
            check("mode klasik: header judul dibuang, blok judul tampil di sheet", back["headers"] == 0 and back["blockDisplay"] not in (None, "none"))
        finally:
            await switch_layout("Layout: switch to Sidebar")
        check("kembali ke sidebar: judul murni di header lagi", (await page.evaluate(TITLE_STATE))["headers"] == 1)

        # --- SO footer: desktop, mobile, and verified browser zoom ---
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/{ORDER}")
        await page.wait_for_selector(".o_form_sheet", timeout=30000)
        await page.wait_for_timeout(2500)
        await audit_footer("SO desktop", "order_line")
        await page.set_viewport_size({"width": 390, "height": 800})
        await page.wait_for_timeout(500)
        await audit_footer("SO mobile", "order_line")
        await page.set_viewport_size({"width": 1440, "height": 860})
        await page.wait_for_timeout(400)
        # Headless Chromium ignores Ctrl+/-; emulate 125% browser zoom through CDP
        # (1152x688 CSS viewport, devicePixelRatio 1.25) and prove the metrics change.
        cdp = await page.context.new_cdp_session(page)

        async def zoom_metrics():
            return await page.evaluate(
                "({ innerWidth, outerWidth, dpr: devicePixelRatio, scale: visualViewport?.scale ?? null })"
            )

        async def set_browser_zoom(factor):
            await cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": round(1440 / factor),
                "height": round(860 / factor),
                "deviceScaleFactor": factor,
                "mobile": False,
            })
            await page.wait_for_timeout(400)

        async def clear_browser_zoom():
            await cdp.send("Emulation.clearDeviceMetricsOverride")
            await page.wait_for_timeout(300)
            await page.set_viewport_size({"width": 1440, "height": 860})

        zoom_before_so = await zoom_metrics()
        await set_browser_zoom(1.25)
        zoom_after_so = await zoom_metrics()
        print("SO browser zoom metrics:", {"before": zoom_before_so, "after": zoom_after_so}, flush=True)
        check("SO browser zoom actually changes effective browser metrics",
              zoom_before_so["innerWidth"] != zoom_after_so["innerWidth"]
              or zoom_before_so["dpr"] != zoom_after_so["dpr"]
              or zoom_before_so["scale"] != zoom_after_so["scale"])
        await audit_footer("SO browser zoom", "order_line")
        await clear_browser_zoom()

        # --- Judul murni vs blok berisi field (faktur draft vs kendaraan) ---
        await page.goto(f"{BASE}/odoo/action-account.action_move_out_invoice_type/{INVOICE}")
        await page.wait_for_selector(".o_form_statusbar", timeout=30000)
        await page.wait_for_timeout(3000)
        inv = await page.evaluate(TITLE_STATE)
        check("faktur: label form kecil di atas nomor draft, di tengah header",
              inv["headers"] == 1 and bool(inv["caption"]) and bool(inv["main"]) and inv["centerOffset"] is not None and abs(inv["centerOffset"]) <= 2)
        title_button = page.locator(".o_form_statusbar > button.id_header_title--editable")
        check("faktur: judul editable adalah tombol native yang dapat ditab",
              await title_button.count() == 1 and await title_button.get_attribute("type") == "button"
              and int(await title_button.evaluate("(el) => el.tabIndex")) >= 0
              and bool(await title_button.get_attribute("aria-label")))
        check("faktur: field Customer tetap di sheet", await page.locator(".o_form_sheet .o_field_widget[name=partner_id]").count() == 1)

        # Uji keyboard nyata: Enter dan Space membuka field OWL asli; blur memperbarui judul.
        action_buttons = page.locator(".o_form_statusbar .o_statusbar_buttons button")
        if await action_buttons.count():
            await action_buttons.last.focus()
            await page.keyboard.press("Tab")
            check("Tab memfokuskan tombol judul setelah tombol aksi",
                  await title_button.evaluate("(el) => document.activeElement === el"))
        else:
            check("Tab memfokuskan tombol judul setelah tombol aksi", False)
        await page.keyboard.press("Enter")
        draft_input = page.locator(".o_form_sheet > .oe_title h1 input")
        await draft_input.wait_for(state="visible", timeout=5000)
        check("Enter membuka dan memfokuskan input nomor asli",
              await draft_input.evaluate("(el) => document.activeElement === el"))
        await draft_input.fill("DRAFT-KEYBOARD-TEST")
        await draft_input.press("Tab")
        await page.wait_for_function(
            "() => document.querySelector('.id_header_title__main')?.textContent.trim() === 'DRAFT-KEYBOARD-TEST'",
            timeout=5000,
        )
        check("blur memperbarui header tanpa duplikasi",
              (await page.locator(".o_form_statusbar > .id_header_title").count()) == 1
              and (await page.locator(".id_header_title__main").inner_text()).strip() == "DRAFT-KEYBOARD-TEST")
        await title_button.focus()
        await page.keyboard.press("Space")
        await draft_input.wait_for(state="visible", timeout=5000)
        check("Space membuka dan memfokuskan input nomor asli",
              await draft_input.evaluate("(el) => document.activeElement === el"))
        await draft_input.press("Escape")
        await page.wait_for_timeout(200)
        check("Escape menutup editor, mengembalikan fokus, dan mempertahankan satu judul",
              await page.locator(".o_form_statusbar > .id_header_title").count() == 1
              and await title_button.evaluate("(el) => document.activeElement === el")
              and await page.locator(".o_form_sheet > .oe_title").evaluate("(el) => getComputedStyle(el).display") == "none")
        await audit_footer("Invoice", "invoice_line_ids")

        # Re-run the populated invoice scroll contract at mobile width and browser zoom.
        await page.set_viewport_size({"width": 390, "height": 800})
        await page.wait_for_timeout(500)
        await audit_footer("Invoice mobile", "invoice_line_ids")
        await page.set_viewport_size({"width": 1440, "height": 860})
        await page.wait_for_timeout(400)
        zoom_before_invoice = await zoom_metrics()
        await set_browser_zoom(1.25)
        zoom_after_invoice = await zoom_metrics()
        print("Invoice browser zoom metrics:", {"before": zoom_before_invoice, "after": zoom_after_invoice}, flush=True)
        check("Invoice browser zoom actually changes effective browser metrics",
              zoom_before_invoice["innerWidth"] != zoom_after_invoice["innerWidth"]
              or zoom_before_invoice["dpr"] != zoom_after_invoice["dpr"]
              or zoom_before_invoice["scale"] != zoom_after_invoice["scale"])
        await audit_footer("Invoice browser zoom", "invoice_line_ids")
        # Control: measure the same shell boxes on a list view we do not style.
        # If the content area reports the same extra width there, the discrepancy
        # belongs to the Odoo shell at this emulated zoom level, not to the
        # transaction footer or the form sheet.
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding")
        await page.wait_for_selector(".o_list_view", timeout=30000)
        await page.wait_for_timeout(1500)
        list_control = await page.evaluate(PAGE_BOX_PROBE)
        print("List view geometry control at emulated 125% zoom:", list_control, flush=True)
        check("list view control measures shell geometry at emulated zoom",
              list_control.get("content") is not None
              and list_control.get("formView") is None
              and list_control["viewport"]["client"] < 1440)
        await clear_browser_zoom()

        await page.goto(f"{BASE}/odoo/action-fleet.fleet_vehicle_action/new")
        await page.wait_for_selector(".o_form_sheet", timeout=30000)
        await page.wait_for_timeout(3000)
        veh = await page.evaluate(TITLE_STATE)
        check("kendaraan: blok judul berisi field tidak diangkat ke header",
              veh["headers"] == 0 and veh["blockDisplay"] not in (None, "none") and veh["blockControls"] >= 2)

        if errors:
            await page.screenshot(path="ui-smoke-failure.png", full_page=True)
        check("tanpa error JS", not errors)
        await browser.close()
    sys.exit(1 if failures else 0)


asyncio.run(main())
