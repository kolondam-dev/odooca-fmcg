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
    header = root.locator('header').first
    initial_top = (await header.bounding_box())['y']
    seen = set()
    for index, position in enumerate(positions):
        position = round(position)
        if position in seen:
            continue
        seen.add(position)
        await root.evaluate('(el, top) => {el.scrollTop=top;}', position)
        await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        header_top = (await header.bounding_box())['y']
        if abs(header_top - initial_top) > 2:
            raise AssertionError(f'Dashboard context moved during scroll: {name}')
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
        for size in [{'width': 1440, 'height': 900}, {'width': 1024, 'height': 768},
                     {'width': 768, 'height': 1024}]:
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
                if name == 'sales':
                    await root.get_by_text('QA No Sales', exact=True).wait_for(state='visible')
                    await root.locator('[aria-label="Target segmen SO"]').wait_for(state='visible')
                if name == 'monetary':
                    await root.get_by_role('button', name='Jurnal sumber', exact=True).wait_for(state='visible')
                panel_labels = {'sales': 'Traceable order margin', 'monetary': 'Historical AR subledger',
                                'wms': 'Scheduled delivery cohort'}
                new_panel = root.locator('section[aria-label="' + panel_labels[name] + '"]')
                await new_panel.wait_for(state='visible')
                await new_panel.scroll_into_view_if_needed()
                await page.screenshot(path=str(OUTPUT / f'{name}-{size["width"]}-stage3b.png'))
                await root.evaluate('el => {el.scrollTop=0;}')
                extra_labels = {'sales': 'Eligible outlet distribution', 'monetary': 'Payment promises',
                                'wms': 'Accepted POD bridge'}
                closure = root.locator('section[aria-label="' + extra_labels[name] + '"]')
                await closure.wait_for(state='visible')
                await closure.scroll_into_view_if_needed()
                await page.screenshot(path=str(OUTPUT / f'{name}-{size["width"]}-3b-closure.png'))
                await root.evaluate('el => {el.scrollTop=0;}')
                if name == 'wms':
                    assets = root.locator('section[aria-label="Physical asset utilization"]')
                    await assets.wait_for(state='visible')
                    await assets.scroll_into_view_if_needed()
                    await page.screenshot(path=str(OUTPUT / f'wms-{size["width"]}-assets.png'))
                    await root.evaluate('el => {el.scrollTop=0;}')
                filters = root.locator('.dashboard-filters')
                await filters.locator('summary').click()
                await root.locator('[class$=__filter-bar]').wait_for(state='visible')
                await filters.locator('summary').click()
                await root.locator('[class$=__filter-bar]').wait_for(state='hidden')
                panel = page.locator('.id_panel__toggle')
                if await panel.is_visible() and await panel.get_attribute('aria-expanded') != 'false':
                    raise AssertionError('Dashboard should start with a compact native section panel')
                if name == 'sales' and size['width'] == 1440:
                    await panel.click()
                    await page.locator('.id_panel__body').wait_for(state='visible')
                    await panel.click()
                    await page.locator('.id_panel__body').wait_for(state='hidden')
                    if await page.evaluate("localStorage.getItem('id_ui_shell.panel_collapsed')") is not None:
                        raise AssertionError('Dashboard panel toggle must not persist user preferences')
                await page.screenshot(path=str(OUTPUT / f'{name}-{size["width"]}.png'), full_page=True)
                await capture_scroll(page, root, f'{name}-{size["width"]}')
                metrics = await root.evaluate('''el => ({width:el.clientWidth,scrollWidth:el.scrollWidth,
                    height:el.clientHeight,scrollHeight:el.scrollHeight,
                    title:el.querySelector('h1')?.textContent,
                    documentWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth})''')
                if metrics['documentWidth'] > size['width'] + 1:
                    raise AssertionError(f'Document overflow: {name}, {metrics}')
                observations.append({'dashboard': name, 'viewport': size, **metrics})
                for button in await root.locator('button').all():
                    # Capture additional analytical tabs, not transaction actions.
                    text = (await button.inner_text()).strip()
                    if text in ['Sebaran per Wilayah', 'Sebaran per Salesman',
                                'Alasan Tolakan', 'Stok per Kategori', 'Efisiensi Armada']:
                        await button.click()
                        await capture_scroll(page, root, f'{name}-{size["width"]}-{text.replace(" ", "-")}')
        # SPA drill-down destroys the dashboard; native panel preference returns immediately.
        await page.get_by_role('button', name='Periksa lot', exact=True).click()
        await page.locator('.o_list_view').wait_for(state='visible')
        await page.locator('.id_panel__body').wait_for(state='visible')
        await page.get_by_text('QA-EXPIRY', exact=True).first.wait_for(state='visible')
        report = {'observations': observations, 'errors': errors}
        (OUTPUT / 'observations.json').write_text(json.dumps(report, indent=2))
        if errors:
            raise AssertionError(errors)
        await browser.close()
    print('DASHBOARD_VISUAL_NATIVE=PASS')


if __name__ == '__main__':
    asyncio.run(main())
