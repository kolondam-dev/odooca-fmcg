"""Extract JavaScript blocks embedded in the Playwright smoke script.

The smoke script keeps its browser-side code in Python triple-quoted strings, so
Python's compiler and linters never parse it as JavaScript. These helpers let the
unit suite extract the real production strings and hand them to ``node --check``
or to a controlled Chromium fixture.
"""
from pathlib import Path
import re

SMOKE_UI = Path(__file__).with_name("smoke_ui.py")
_JS_BLOCK = re.compile(r'^\s*(\w+) = """(.*?)"""', re.S | re.M)


def js_blocks():
    """Return ``{variable_name: javascript_source}`` for every inline JS block."""
    source = SMOKE_UI.read_text(encoding="utf-8")
    return {match.group(1): match.group(2) for match in _JS_BLOCK.finditer(source)}
