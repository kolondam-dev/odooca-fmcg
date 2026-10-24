"""Smoke test UI (Playwright). Prasyarat: Odoo berjalan, id_ui, id_ui_shell, id_ui_form
terpasang, pengguna admin/admin punya akses Penjualan, ada minimal satu order.

    python smoke_ui.py http://localhost:8069 <id_sale_order>
"""
import asyncio
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
        await page.fill("input[name=login]", "admin")
        await page.fill("input[name=password]", "admin")
        await page.click("button[type=submit]")
        await page.wait_for_timeout(12000)
        await page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/{ORDER}")
        await page.wait_for_timeout(8000)

        check("body punya kelas sidebar", "id-shell-sidebar" in await page.evaluate("document.body.className"))
        check("sidebar berisi aplikasi", await page.locator(".id_sidebar [data-nav]").count() >= 3)
        check("judul topbar = nama aplikasi", (await page.locator(".o_menu_brand").first.inner_text()).strip() != "")
        check("pencarian menu ada", await page.locator(".id_menu_search").count() == 1)
        tabs = await page.evaluate("[...document.querySelectorAll('.o_notebook_headers .nav-link')].map(e=>e.textContent.trim())")
        check("chatter jadi tab terakhir", bool(tabs) and tabs[-1] in ("Messages & Activities", "Pesan & Aktivitas"))
        check("tidak ada chatter di samping", await page.locator(".o-aside").count() == 0)
        h = await page.evaluate("[document.documentElement.scrollHeight, window.innerHeight]")
        check("halaman tidak scroll", h[0] <= h[1])

        await page.keyboard.press("Alt+m")
        focus = await page.evaluate("document.activeElement.classList.contains('id_item')")
        check("Alt+M memfokuskan sidebar", focus)
        await page.keyboard.press("Alt+b")
        await page.wait_for_timeout(400)
        check("Alt+B menciutkan", "id-shell-collapsed" in await page.evaluate("document.body.className"))
        await page.keyboard.press("Alt+b")

        check("tanpa error JS", not errors)
        await browser.close()
    sys.exit(1 if failures else 0)


asyncio.run(main())
