"""Regression tests for the production readTitleSpec guard.

Run with: python -m pytest docs/ui/e2e/test_title_spec.py
The function body is extracted from form_patch.js so these cases exercise production logic,
not a copied implementation. Chromium supplies the DOM implementation.
"""
from pathlib import Path
import re

from playwright.sync_api import sync_playwright


SOURCE = Path(__file__).resolve().parents[3] / "addons/id_ui_form/static/src/form/form_patch.js"


def _read_title_spec_source():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"export function readTitleSpec\(block\)\s*\{", source)
    assert match, "production readTitleSpec function not found"
    start = match.start()
    brace = source.index("{", match.start())
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1].replace("export function", "function", 1)
    raise AssertionError("unbalanced readTitleSpec function")


def test_read_title_spec_fails_closed_for_unsupported_controls():
    function_source = _read_title_spec_source()
    fixtures = [
        ("readonly title", '<div class="oe_title"><h1>SO001</h1></div>', "readonly"),
        ("supported invoice draft", '<div class="oe_title"><label class="o_form_label">Customer Invoice</label><h1><input value="DRAFT-001"></h1></div>', "editable"),
        ("multiple inputs", '<div class="oe_title"><h1><input value="FIELD-A"><input value="FIELD-B"></h1></div>', None),
        ("contenteditable", '<div class="oe_title"><h1 contenteditable="true">Editable title</h1></div>', None),
        ("required input", '<div class="oe_title"><h1><input required value="REQUIRED"></h1></div>', None),
        ("aria-required input", '<div class="oe_title"><h1><input aria-required="true" value="REQUIRED"></h1></div>', None),
        ("Odoo required modifier", '<div class="oe_title"><h1><span class="o_required_modifier"><input value="REQUIRED"></span></h1></div>', None),
        ("select control", '<div class="oe_title"><h1><select><option>Choice</option></select></h1></div>', None),
        ("textarea control", '<div class="oe_title"><h1><textarea>Text</textarea></h1></div>', None),
        ("input outside heading", '<div class="oe_title"><h1>Vehicle</h1><input value="plate"></div>', None),
        ("number input", '<div class="oe_title"><h1><input type="number" value="123"></h1></div>', None),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        results = page.evaluate(
            """({ source, fixtures }) => {
                const readTitleSpec = new Function("return (" + source + ")")();
                return fixtures.map(([name, markup, expected]) => {
                    const wrapper = document.createElement("div");
                    wrapper.innerHTML = markup;
                    const actual = readTitleSpec(wrapper.firstElementChild);
                    const kind = actual === null ? null : actual.editable ? "editable" : "readonly";
                    return { name, expected, kind, pass: kind === expected };
                });
            }""",
            {"source": function_source, "fixtures": fixtures},
        )
        browser.close()
    failures = [item for item in results if not item["pass"]]
    assert not failures, f"readTitleSpec regression failures: {failures}"
