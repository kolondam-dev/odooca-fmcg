"""Regression tests for production title guards and editor activation."""
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


SOURCE = Path(__file__).resolve().parents[3] / "addons/id_ui_form/static/src/form/form_patch.js"


def _production_function_source(name):
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(rf"export function {re.escape(name)}\(block\)\s*\{{", source)
    assert match, f"production {name} function not found"
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
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "\`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1].replace("export function", "function", 1)
    raise AssertionError(f"unbalanced {name} function")


class TestReadTitleSpec(unittest.TestCase):
    def test_fails_closed_and_focuses_the_same_validated_input(self):
        spec_source = _production_function_source("readTitleSpec")
        input_source = _production_function_source("getEditableTitleInput")
        focus_source = _production_function_source("focusEditableTitleInput")
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
            ("hidden before supported input", '<div class="oe_title"><h1><input type="hidden" value="metadata"><input type="text" value="DRAFT"></h1></div>', "editable"),
            ("hidden only with readonly text", '<div class="oe_title"><h1><input type="hidden" value="metadata">Vehicle</h1></div>', "readonly"),
            ("hidden plus second visible input", '<div class="oe_title"><h1><input type="hidden" value="metadata"><input value="DRAFT"><input value="OTHER"></h1></div>', None),
        ]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            results = page.evaluate(
                """({ specSource, inputSource, focusSource, fixtures }) => {
                    const getEditableTitleInput = new Function("return (" + inputSource + ")")();
                    const focusEditableTitleInput = new Function("getEditableTitleInput", "return (" + focusSource + ")")(getEditableTitleInput);
                    const readTitleSpec = new Function("getEditableTitleInput", "return (" + specSource + ")")(getEditableTitleInput);
                    return fixtures.map(([name, markup, expected]) => {
                        const wrapper = document.createElement("div");
                        wrapper.innerHTML = markup;
                        const block = wrapper.firstElementChild;
                        const actual = readTitleSpec(block);
                        const editableInput = getEditableTitleInput(block);
                        const kind = actual === null ? null : actual.editable ? "editable" : "readonly";
                        if (name === "hidden before supported input") {
                            const focusedInput = focusEditableTitleInput(block);
                            const expectedInput = block.querySelector('input[type="text"]');
                            return { name, expected, kind, pass: actual?.editable === true && editableInput === expectedInput && focusedInput === expectedInput && document.activeElement === expectedInput && block.classList.contains("id_title_editing") };
                        }
                        if (name === "hidden only with readonly text") {
                            const focusedInput = focusEditableTitleInput(block);
                            return { name, expected, kind, pass: actual?.editable === false && editableInput === null && focusedInput === null && !block.classList.contains("id_title_editing") };
                        }
                        return { name, expected, kind, pass: kind === expected };
                    });
                }""",
                {"specSource": spec_source, "inputSource": input_source, "focusSource": focus_source, "fixtures": fixtures},
            )
            browser.close()
        failures = [item for item in results if not item["pass"]]
        assert not failures, f"title guard/editor activation regression failures: {failures}"
