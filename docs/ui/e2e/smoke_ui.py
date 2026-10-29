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
        check("footer total sticky", await page.evaluate("(() => { const f = document.querySelector('.o_form_sheet .o_group:has(.oe_subtotal_footer)'); return !!f && getComputedStyle(f).position === 'sticky'; })()"))

        # Exercise the actual scroll container with a long CI quotation. A CSS declaration
        # alone is not sufficient: the last order line must remain reachable and uncovered.
        footer_scroll = await page.evaluate("""(() => {
            const footer = document.querySelector('.o_form_sheet .o_group:has(.oe_subtotal_footer)');
            if (!footer) return { ok: false, reason: 'missing sticky footer group' };
            let owner = footer.parentElement;
            while (owner && owner !== document.body) {
                const style = getComputedStyle(owner);
                if (owner.scrollHeight > owner.clientHeight + 4 && /(auto|scroll)/.test(style.overflowY)) break;
                owner = owner.parentElement;
            }
            if (!owner || owner === document.body) return { ok: false, reason: 'no overflowing scroll owner' };
            const rows = [...document.querySelectorAll('.o_field_x2many_list .o_data_row, .o_field_one2many .o_data_row')];
            const maxScroll = Math.max(0, owner.scrollHeight - owner.clientHeight);
            if (maxScroll < 40) return { ok: false, reason: 'form did not produce meaningful vertical overflow', maxScroll };
            const top = owner.scrollTop;
            owner.scrollTop = 0;
            const topY = footer.getBoundingClientRect().top;
            owner.scrollTop = Math.floor(maxScroll / 2);
            const middleY = footer.getBoundingClientRect().top;
            owner.scrollTop = maxScroll;
            const footerRect = footer.getBoundingClientRect();
            const ownerRect = owner.getBoundingClientRect();
            const lastRowRect = rows.length ? rows[rows.length - 1].getBoundingClientRect() : null;
            const result = {
                ok: true,
                maxScroll,
                rowCount: rows.length,
                // A sticky footer should remain stable relative to the scrollport,
                // not move with the document as the scroll position changes.
                footerTopDrift: Math.max(topY, middleY, footerRect.top) - Math.min(topY, middleY, footerRect.top),
                footerInScrollport: footerRect.top >= ownerRect.top - 2 && footerRect.bottom <= ownerRect.bottom + 2,
                lastRowNotCovered: !!lastRowRect && lastRowRect.bottom <= footerRect.top + 2,
                horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
            };
            owner.scrollTop = top;
            return result;
        })()""")
        print("SO footer scroll diagnostics:", footer_scroll, flush=True)
        check("SO: scroll test uses a real overflowing container and multiple lines",
              footer_scroll.get("ok") and footer_scroll.get("maxScroll", 0) >= 40 and footer_scroll.get("rowCount", 0) >= 10)
        check("SO: sticky footer remains stable through top/middle/bottom scrolling",
              footer_scroll.get("ok") and footer_scroll.get("footerTopDrift", 999) <= 3)
        check("SO: sticky footer remains inside the scrollport at bottom",
              footer_scroll.get("ok") and footer_scroll.get("footerInScrollport"))
        check("SO: last transaction row is not covered by footer",
              footer_scroll.get("ok") and footer_scroll.get("lastRowNotCovered"))
        check("SO: no horizontal page overflow after scrolling",
              footer_scroll.get("ok") and not footer_scroll.get("horizontalOverflow"))

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

        # --- Judul murni vs blok berisi field (faktur draft vs kendaraan) ---
        await page.goto(f"{BASE}/odoo/action-account.action_move_out_invoice_type/new")
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
