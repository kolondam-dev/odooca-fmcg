"""Native Odoo visual audit. No mocked dashboard RPCs, no production data writes."""
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8069'
OUTPUT = Path('dashboard-visual')
ACTIONS = [
    ('sales', 'id_dashboard_sales.action_sales_productivity', '.id-sp', '.id-sp__cards'),
    ('monetary', 'id_dashboard_monetary.action_monetary_dashboard', '.id-md', '.id-md__cards'),
    ('wms', 'id_dashboard_wms.action_wms_dashboard', '.id-wms', '.id-wms__cards'),
]


async def capture_scroll(page, root, name):
    # Dashboard owns an internal scroll area: full_page alone cannot expose its lower sections.
    positions = await root.evaluate('''el => [0, Math.max(0, (el.scrollHeight-el.clientHeight)/2),
        Math.max(0, el.scrollHeight-el.clientHeight)]''')
    seen = set()
    for index, position in enumerate(positions):
        position = round(position)
        if position in seen:
            continue
        seen.add(position)
        await root.evaluate('(el, top) => {el.scrollTop=top;}', position)
        await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        await page.screenshot(path=str(OUTPUT / f'{name}-scroll-{index}.png'))
    await root.evaluate('el => {el.scrollTop=0;}')


async def main():
    OUTPUT.mkdir(exist_ok=True)
    observations = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(f'{BASE}/web/login')
        await page.locator('input[name=login]').fill(os.environ.get('UI_TEST_LOGIN', 'admin'))
        await page.locator('input[name=password]').fill(os.environ['UI_TEST_PASSWORD'])
        await page.locator('button[type=submit]').click()
        await page.wait_for_url('**/odoo**')
        for size in [{'width': 1440, 'height': 900}, {'width': 1024, 'height': 768}]:
            await page.set_viewport_size(size)
            for name, action, root_selector, ready in ACTIONS:
                await page.goto(f'{BASE}/odoo/action-{action}')
                root = page.locator(root_selector)
                await root.locator(ready).first.wait_for(state='visible')
                await page.wait_for_function("!document.querySelector('.is-loading')")
                if await root.locator('[role=alert]').count():
                    raise AssertionError(await root.locator('[role=alert]').all_text_contents())
                if not await page.locator('.o_main_navbar').is_visible():
                    raise AssertionError('Native Odoo navigation must remain visible')
                await page.screenshot(path=str(OUTPUT / f'{name}-{size["width"]}.png'), full_page=True)
                await capture_scroll(page, root, f'{name}-{size["width"]}')
                metrics = await root.evaluate('''el => ({width:el.clientWidth,scrollWidth:el.scrollWidth,
                    height:el.clientHeight,scrollHeight:el.scrollHeight,
                    title:el.querySelector('h1')?.textContent,
                    documentWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth})''')
                observations.append({'dashboard': name, 'viewport': size, **metrics})
                for button in await root.locator('button').all():
                    # Capture additional analytical tabs, not transaction actions.
                    text = (await button.inner_text()).strip()
                    if text in ['Sebaran per Wilayah', 'Sebaran per Salesman',
                                'Alasan Tolakan', 'Stok per Kategori', 'Efisiensi Armada']:
                        await button.click()
                        await capture_scroll(page, root, f'{name}-{size["width"]}-{text.replace(" ", "-")}')
        report = {'observations': observations, 'errors': errors}
        (OUTPUT / 'observations.json').write_text(json.dumps(report, indent=2))
        if errors:
            raise AssertionError(errors)
        await browser.close()
    print('DASHBOARD_VISUAL_NATIVE=PASS')


if __name__ == '__main__':
    asyncio.run(main())
