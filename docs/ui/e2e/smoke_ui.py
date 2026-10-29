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
        check("footer total sticky", await page.evaluate("(() => { const f = document.querySelector('.o_form_sheet .o_group:has(.oe_subtotal_footer):not(:has(.o_group .oe_subtotal_footer))'); return !!f && getComputedStyle(f).position === 'sticky'; })()"))

        # Shared geometry audit for both real populated transaction forms. The script
        # determines the sticky threshold from the footer's natural position and the
        # scrollport geometry; percentages alone are not evidence of sticky engagement.
        FOOTER_SCROLL_AUDIT = """((lineFieldName) => {
            const footerGroups = [...document.querySelectorAll('.o_form_sheet .o_group:has(.oe_subtotal_footer):not(:has(.o_group .oe_subtotal_footer))')];
            const stickyGroups = footerGroups.filter(e => getComputedStyle(e).position === 'sticky');
            if (stickyGroups.length !== 1) return { ok: false, reason: 'expected exactly one sticky footer group', footerGroupCount: footerGroups.length, stickyGroupCount: stickyGroups.length };
            const footer = stickyGroups[0];
            let owner = footer.parentElement;
            while (owner && owner !== document.body) {
                const style = getComputedStyle(owner);
                if (owner.scrollHeight > owner.clientHeight + 4 && /(auto|scroll)/.test(style.overflowY)) break;
                owner = owner.parentElement;
            }
            if (!owner || owner === document.body) return { ok: false, reason: 'no overflowing scroll owner' };
            const list = document.querySelector('.o_form_sheet [name="' + lineFieldName + '"]');
            if (!list) return { ok: false, reason: 'transaction line field missing', lineFieldName };
            const rows = [...list.querySelectorAll('.o_data_row')];
            if (rows.length < 10) return { ok: false, reason: 'populated line list required', rowCount: rows.length };
            const maxScroll = Math.max(0, owner.scrollHeight - owner.clientHeight);
            if (maxScroll < 40) return { ok: false, reason: 'form did not produce meaningful vertical overflow', maxScroll };
            const initialScroll = owner.scrollTop;
            owner.scrollTop = 0;
            const ownerRect = owner.getBoundingClientRect();
            const scrollportBottomAtZero = ownerRect.top + owner.clientTop + owner.clientHeight;
            // Measure the footer's true normal-flow geometry: disable sticky only for
            // this measurement, then restore the exact inline style before assertions.
            const originalStyle = footer.getAttribute('style');
            footer.style.setProperty('position', 'static', 'important');
            footer.style.setProperty('bottom', 'auto', 'important');
            const naturalRect = footer.getBoundingClientRect();
            const naturalFooterBottom = naturalRect.bottom;
            const naturalFooterHeight = naturalRect.height;
            const containingBlock = footer.parentElement;
            const containingRect = containingBlock.getBoundingClientRect();
            const containingBottomAtZero = containingRect.bottom;
            if (originalStyle === null) footer.removeAttribute('style');
            else footer.setAttribute('style', originalStyle);
            const naturalFooterTop = naturalRect.top;
            const stickyTopOffset = window.innerHeight - 300;
            const stickyTopAtZero = ownerRect.top + owner.clientTop + stickyTopOffset;
            const threshold = Math.max(0, Math.ceil(naturalFooterTop - stickyTopAtZero));
            // A top-sticky box remains pinned only while the containing block can
            // contain the whole footer at the sticky top offset.
            const pinEnd = Math.min(maxScroll, Math.max(0, containingBottomAtZero - (stickyTopAtZero + naturalFooterHeight)));
            const pinStart = Math.min(maxScroll, threshold);
            const pinSpan = Math.max(0, pinEnd - pinStart);
            const samples = [...new Set([
                Math.max(0, pinStart - 12),
                pinStart + Math.min(8, pinSpan / 4),
                pinStart + pinSpan / 2,
                pinEnd - Math.min(8, pinSpan / 4),
                maxScroll
            ].map(y => Math.max(0, Math.min(maxScroll, Math.round(y)))))].sort((a,b) => a-b);
            const pinned = [];
            for (const y of samples.filter(y => y >= pinStart && y <= pinEnd && pinSpan >= 12)) {
                owner.scrollTop = y;
                const fr = footer.getBoundingClientRect();
                const or = owner.getBoundingClientRect();
                const sampleStickyTop = or.top + owner.clientTop + stickyTopOffset;
                const sampleScrollportBottom = or.top + owner.clientTop + owner.clientHeight;
                const cr = containingBlock.getBoundingClientRect();
                pinned.push({
                    scrollTop: owner.scrollTop,
                    footerTop: fr.top,
                    stickyTop: sampleStickyTop,
                    footerBottom: fr.bottom,
                    scrollportBottom: sampleScrollportBottom,
                    containingBlockBottom: cr.bottom,
                    drift: Math.abs(fr.top - sampleStickyTop),
                    insideContainingBlock: fr.top >= or.top + owner.clientTop - 2
                        && fr.bottom <= cr.bottom + 2
                        && fr.bottom <= sampleScrollportBottom + 2
                });
            }
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
            const scrollportTop = scrollport.top + owner.clientTop;
            const scrollportBottom = scrollport.top + owner.clientTop + owner.clientHeight;
            const lastRow = rows[rows.length - 1];
            lastRow.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            const rowRect = lastRow.getBoundingClientRect();
            const footerAfterRowScroll = footer.getBoundingClientRect();
            const visibleTop = Math.max(scrollportTop, footerAfterRowScroll.top);
            const isRowVisibleAndUncovered = (rect, top, bottom, footerTop) =>
                rect.top >= top - 2 && rect.bottom <= footerTop + 2
                && rect.bottom <= bottom + 2 && rect.top < footerTop;
            const lastRowVisible = isRowVisibleAndUncovered(
                rowRect, scrollportTop, scrollportBottom, footerAfterRowScroll.top
            );
            // Negative control: a row fully above the scrollport must never pass.
            const hiddenRowRejected = !isRowVisibleAndUncovered(
                { top: scrollportTop - 50, bottom: scrollportTop - 10 },
                scrollportTop, scrollportBottom, footerAfterRowScroll.top
            );
            const form = document.querySelector('.o_form_sheet');
            const lastCell = lastRow.querySelector('td:not(.o_list_record_selector)');
            const result = {
                ok: true,
                lineFieldName,
                maxScroll,
                rowCount: rows.length,
                stickyGroupCount: stickyGroups.length,
                naturalFooterBottom,
                naturalFooterTop,
                stickyTopOffset,
                stickyTopAtZero,
                naturalFooterHeight,
                stickyThreshold: threshold,
                stickyPinEnd: pinEnd,
                containingBlockBottomAtZero: containingBottomAtZero,
                computedSticky: { position: getComputedStyle(footer).position, bottom: getComputedStyle(footer).bottom, marginTop: getComputedStyle(footer).marginTop, marginBottom: getComputedStyle(footer).marginBottom },
                overflowAncestors,
                stickySamples: pinned,
                stickyEngagedAtLeastTwice: pinSpan >= 12 && pinned.length >= 2,
                stickyPinned: pinSpan >= 12 && pinned.length >= 2 && pinned.every(p => p.drift <= 3 && p.insideContainingBlock),
                footerInScrollport: footerAfterRowScroll.top >= scrollportTop - 2 && footerAfterRowScroll.bottom <= scrollportBottom + 2,
                lastRowVisibleAndUncovered: lastRowVisible,
                hiddenRowCounterexampleRejected: hiddenRowRejected,
                horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
                    || owner.scrollWidth > owner.clientWidth + 1
                    || footer.scrollWidth > footer.clientWidth + 1
                    || (!!form && form.scrollWidth > form.clientWidth + 1),
                horizontalMetrics: {
                    viewport: { client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth },
                    owner: { client: owner.clientWidth, scroll: owner.scrollWidth },
                    form: form ? { client: form.clientWidth, scroll: form.scrollWidth } : null,
                    footer: { client: footer.clientWidth, scroll: footer.scrollWidth },
                    footerBox: { left: footer.getBoundingClientRect().left, right: footer.getBoundingClientRect().right },
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
                lastCellPresent: !!lastCell,
            };
            owner.scrollTop = initialScroll;
            return result;
        })""";
        async def audit_footer(form_label, line_field):
            result = await page.evaluate(f"({FOOTER_SCROLL_AUDIT})({line_field!r})")
            print(f"{form_label} footer scroll diagnostics:", result, flush=True)
            check(f"{form_label}: real scroll owner and populated transaction rows",
                  result.get("ok") and result.get("maxScroll", 0) >= 40 and result.get("rowCount", 0) >= 10)
            check(f"{form_label}: sticky threshold derived from geometry and sampled after engagement",
                  result.get("ok") and result.get("stickyEngagedAtLeastTwice"))
            check(f"{form_label}: footer remains pinned to scrollport in sticky phase",
                  result.get("ok") and result.get("stickyPinned"))
            check(f"{form_label}: footer stays inside scrollport",
                  result.get("ok") and result.get("footerInScrollport"))
            check(f"{form_label}: last transaction row is visible and uncovered",
                  result.get("ok") and result.get("lastRowVisibleAndUncovered"))
            check(f"{form_label}: no horizontal overflow in page, scroll owner, or footer",
                  result.get("ok") and not result.get("horizontalOverflow"))
            if result.get("ok") and result.get("lastCellPresent"):
                cell = page.locator(f'.o_form_sheet [name="{line_field}"] .o_data_row').last.locator("td:not(.o_list_record_selector)").first
                try:
                    await cell.click(trial=True, timeout=3000)
                    check(f"{form_label}: last transaction row passes Playwright actionability", True)
                    post_actionability = await page.evaluate("""(lineFieldName) => {
                        const footer = document.querySelector('.o_form_sheet .o_group:has(.oe_subtotal_footer):not(:has(.o_group .oe_subtotal_footer))');
                        const list = document.querySelector('.o_form_sheet [name="' + lineFieldName + '"]');
                        const row = list && list.querySelector('.o_data_row:last-child');
                        let owner = row && row.parentElement;
                        while (owner && owner !== document.body) {
                            const cs = getComputedStyle(owner);
                            if (owner.scrollHeight > owner.clientHeight + 4 && /(auto|scroll)/.test(cs.overflowY)) break;
                            owner = owner.parentElement;
                        }
                        if (!owner || owner === document.body) {
                            const fallback = document.querySelector('.o_form_sheet_bg');
                            if (fallback && fallback.scrollHeight > fallback.clientHeight + 4) owner = fallback;
                        }
                        if (!footer || !row || !owner || owner === document.body) return {
                            ok: false, reason: 'missing footer, row, or scroll owner after trial click',
                            footerFound: !!footer, rowFound: !!row,
                            candidateScroll: owner && owner !== document.body ? {
                                className: String(owner.className || ''),
                                scrollHeight: owner.scrollHeight,
                                clientHeight: owner.clientHeight
                            } : null
                        };
                        const fr = footer.getBoundingClientRect(), rr = row.getBoundingClientRect(), or = owner.getBoundingClientRect();
                        const top = or.top + owner.clientTop, bottom = top + owner.clientHeight;
                        return {
                            ok: true, scrollTop: owner.scrollTop,
                            row: { top: rr.top, bottom: rr.bottom },
                            footer: { top: fr.top, bottom: fr.bottom },
                            scrollport: { top, bottom },
                            visibleAndUncovered: rr.top >= top - 2 && rr.bottom <= bottom + 2 && rr.bottom <= fr.top + 2 && rr.top < fr.top
                        };
                    }""", line_field)
                    print(f"{form_label} geometry after trial actionability:", post_actionability, flush=True)
                    check(f"{form_label}: last row remains visible and uncovered after Playwright actionability",
                          post_actionability.get("ok") and post_actionability.get("visibleAndUncovered"))
                except Exception as exc:
                    print(f"{form_label} last-row actionability:", str(exc), flush=True)
                    check(f"{form_label}: last transaction row passes Playwright actionability", False)
            else:
                check(f"{form_label}: last transaction row passes Playwright actionability", False)

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
        zoom_before_so = await page.evaluate("({ innerWidth, outerWidth, dpr: devicePixelRatio, scale: visualViewport?.scale ?? null })")
        await page.keyboard.press("Control+Shift+Equal")
        await page.wait_for_timeout(700)
        zoom_after_so = await page.evaluate("({ innerWidth, outerWidth, dpr: devicePixelRatio, scale: visualViewport?.scale ?? null })")
        print("SO browser zoom metrics:", {"before": zoom_before_so, "after": zoom_after_so}, flush=True)
        check("SO browser zoom actually changes effective browser metrics",
              zoom_before_so["innerWidth"] != zoom_after_so["innerWidth"]
              or zoom_before_so["dpr"] != zoom_after_so["dpr"]
              or zoom_before_so["scale"] != zoom_after_so["scale"])
        await audit_footer("SO browser zoom", "order_line")
        await page.keyboard.press("Control+0")
        await page.wait_for_timeout(300)

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
        zoom_before_invoice = await page.evaluate("({ innerWidth, outerWidth, dpr: devicePixelRatio, scale: visualViewport?.scale ?? null })")
        await page.keyboard.press("Control+Equal")
        await page.wait_for_timeout(700)
        zoom_after_invoice = await page.evaluate("({ innerWidth, outerWidth, dpr: devicePixelRatio, scale: visualViewport?.scale ?? null })")
        print("Invoice browser zoom metrics:", {"before": zoom_before_invoice, "after": zoom_after_invoice}, flush=True)
        check("Invoice browser zoom actually changes effective browser metrics",
              zoom_before_invoice["innerWidth"] != zoom_after_invoice["innerWidth"]
              or zoom_before_invoice["dpr"] != zoom_after_invoice["dpr"]
              or zoom_before_invoice["scale"] != zoom_after_invoice["scale"])
        await audit_footer("Invoice browser zoom", "invoice_line_ids")
        await page.keyboard.press("Control+0")
        await page.wait_for_timeout(300)

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
