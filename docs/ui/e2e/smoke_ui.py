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
        page.on("pageerror", lambda e: errors.append(str(e)))
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

        # --- Form: judul di statusbar (idempoten, tanpa sisa di sheet), footer sticky ---
        await page.keyboard.press("Escape")
        t = await page.evaluate("({inBar: document.querySelectorAll('.o_form_statusbar > .id_statusbar_title').length, inSheet: document.querySelectorAll('.o_form_sheet > .oe_title').length})")
        check("judul form tepat satu di statusbar, tidak tersisa di sheet", t["inBar"] == 1 and t["inSheet"] == 0)
        check("footer total sticky", await page.evaluate("(() => { const f = document.querySelector('.o_form_sheet .o_group:has(.oe_subtotal_footer)'); return !!f && getComputedStyle(f).position === 'sticky'; })()"))

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
        title = page.locator(".o_form_statusbar > .id_statusbar_title")
        first_title = (await title.inner_text()).strip()
        next_button = page.locator(".o_pager_next")
        if not await next_button.count() or not await next_button.is_enabled():
            raise AssertionError("Pager requires at least two accessible orders; navigation was not tested")
        await next_button.click()
        await page.wait_for_function(
            "first => document.querySelector('.id_statusbar_title')?.textContent.trim() !== first",
            arg=first_title,
        )
        second_title = (await title.inner_text()).strip()
        check("pager membuka record berbeda", bool(second_title) and second_title != first_title)
        check("judul tunggal pada record kedua", await title.count() == 1)
        await page.locator(".o_pager_previous").click()
        await page.wait_for_function(
            "first => document.querySelector('.id_statusbar_title')?.textContent.trim() === first",
            arg=first_title,
        )
        check("pager kembali ke record pertama", (await title.inner_text()).strip() == first_title)
        check("judul tetap satu setelah pager", await title.count() == 1)

        # --- Ganti ke tata letak klasik: judul kembali ke sheet; lalu pulihkan ke sidebar ---
        async def switch_layout(label):
            await page.click(".o_user_menu button")
            await page.get_by_text(label).first.click()
            await page.wait_for_timeout(2500)
        try:
            await switch_layout("Layout: switch to Classic")
            back = await page.evaluate("({inBar: document.querySelectorAll('.o_form_statusbar > .oe_title').length, inSheet: document.querySelectorAll('.o_form_sheet > .oe_title').length})")
            check("mode klasik: judul kembali ke sheet", back["inBar"] == 0 and back["inSheet"] == 1)
        finally:
            await switch_layout("Layout: switch to Sidebar")
        check("kembali ke sidebar: judul di statusbar lagi", await page.locator(".o_form_statusbar > .id_statusbar_title").count() == 1)

        check("tanpa error JS", not errors)
        await browser.close()
    sys.exit(1 if failures else 0)


asyncio.run(main())
