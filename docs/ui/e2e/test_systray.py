"""Browser regression tests using the real shell SCSS and divider observer."""
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright
import sass

ROOT = Path(__file__).resolve().parents[3]
SHELL = ROOT / 'addons/id_ui_shell/static/src/shell'


class SystrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        cls.css = sass.compile(filename=str(SHELL / 'id_shell.scss'))
        cls.script = (SHELL / 'systray_dividers.js').read_text().replace('export function ', 'function ')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 860})
        self.addCleanup(self.page.close)
        self.page.set_content('''<style>
            .d-none { display:none!important; }
            @media(min-width:768px) { .d-md-block { display:block!important; } }
            .o_menu_systray > div > button { width:30px; height:30px; }
            </style><style>''' + self.css + '''</style>
            <body class="id-shell-sidebar"><header class="o_navbar"><nav class="o_main_navbar">
            <div class="o_menu_systray">
              <div id="first"><button>1</button></div>
              <div id="hidden" class="d-none"><button>Hidden</button></div>
              <div id="responsive" class="d-none d-md-block"><button>Company</button></div>
              <div id="invisible" style="visibility:hidden"><button>Hidden</button></div>
              <div id="empty"></div>
              <div><button class="o_mobile_menu_toggle">Mobile</button></div>
              <div id="last"><button>User</button></div>
            </div></nav></header></body>''')
        self.page.add_script_tag(content=self.script + '''
            window.cleanup = observeSystrayDividers(document.querySelector('.o_menu_systray'));
        ''')
        self.settle()

    def settle(self):
        self.page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')

    def test_native_hidden_items_remain_hidden(self):
        self.assertFalse(self.page.locator('#hidden').is_visible())
        self.assertFalse(self.page.locator('#invisible').is_visible())
        self.assertEqual(self.page.locator('.id_systray_item').count(), 3)
        self.assertEqual(self.page.locator('.id_systray_divider').count(), 2)
        self.assertFalse(self.page.locator('#first').evaluate("e => e.classList.contains('id_systray_divider')"))

    def test_responsive_visibility_and_dividers(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.wait_for_function("!document.querySelector('#responsive').classList.contains('id_systray_item')")
        self.assertFalse(self.page.locator('#responsive').is_visible())
        self.assertEqual(self.page.locator('.id_systray_divider').count(), 1)
        self.page.set_viewport_size({'width': 1440, 'height': 860})
        self.page.wait_for_function("document.querySelector('#responsive').classList.contains('id_systray_item')")
        self.assertEqual(self.page.locator('.id_systray_divider').count(), 2)

    def test_dynamic_first_item_and_hidden_transition(self):
        self.page.locator('#first').evaluate("e => e.style.display = 'none'")
        self.page.wait_for_function("!document.querySelector('#responsive').classList.contains('id_systray_divider')")
        self.assertEqual(self.page.locator('.id_systray_divider').count(), 1)
        self.page.locator('#last').evaluate('e => e.remove()')
        self.page.wait_for_function("document.querySelectorAll('.id_systray_divider').length === 0")

    def test_observers_disconnect_on_cleanup(self):
        self.page.evaluate('window.cleanup()')
        self.page.locator('#hidden').evaluate("e => e.classList.remove('d-none')")
        self.settle()
        self.assertEqual(self.page.locator('.id_systray_item, .id_systray_divider').count(), 0)
