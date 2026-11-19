#!/usr/bin/env python3
"""Generate Compose design tokens from pwa/design/tokens.json (sumber kebenaran tunggal).

Pemakaian:
  python3 android/tools/gen_design_tokens.py pwa/design/tokens.json \
      android/core/designsystem/src/main/kotlin/com/kolondam/odooca/field/designsystem/Tokens.kt
"""
import json
import sys

src, out = sys.argv[1], sys.argv[2]
tokens = json.load(open(src, encoding="utf-8"))


def leaves(node, path=()):
    for key, value in node.items():
        if isinstance(value, dict):
            if "$value" in value:
                yield path + (key,), value["$value"]
            else:
                yield from leaves(value, path + (key,))


def cap(name):
    return name[:1].upper() + name[1:]


def argb(hex_value):
    h = hex_value.lstrip("#").upper()
    assert len(h) == 6, hex_value
    return "0xFF" + h


lines = [
    "// GENERATED FILE. Jangan diedit manual.",
    (
        "// Sumber: pwa/design/tokens.json. Regenerasi: "
        "python3 android/tools/gen_design_tokens.py <tokens.json> <Tokens.kt>"
    ),
    "package com.kolondam.odooca.field.designsystem",
    "",
    "import androidx.compose.ui.graphics.Color",
    "import androidx.compose.ui.unit.dp",
    "",
    "object OdoocaColors {",
]
seen = set()
for path, value in leaves(tokens["color"]):
    name = cap(path[-1])
    assert name not in seen, "nama token warna ganda: " + name
    seen.add(name)
    lines.append(f"    val {name} = Color({argb(value)})")
lines += ["}", "", "object OdoocaSpacing {"]
for path, value in leaves(tokens["spacing"]):
    lines.append(f"    val S{path[-1]} = {int(value)}.dp")
lines += ["}", "", "object OdoocaRadius {"]
for path, value in leaves(tokens["radius"]):
    lines.append(f"    val {cap(path[-1])} = {int(value)}.dp")
lines += ["}", "", "object OdoocaSize {"]
for path, value in leaves(tokens["size"]):
    if path[-1] in ("screenW", "screenH"):
        continue  # ukuran artboard desain, bukan token UI
    lines.append(f"    val {cap(path[-1])} = {int(value)}.dp")
lines += [
    "}",
    "",
    "/** Spesifikasi tipografi: bobot, ukuran (sp), tinggi baris (sp). */",
    "data class TypeSpec(val weight: Int, val sizeSp: Float, val lineHeightSp: Float)",
    "",
    "object OdoocaTypeSpecs {",
]
for name, spec in tokens["typography"].items():
    v = spec["$value"]
    lines.append(
        f"    val {cap(name)} = TypeSpec({int(v['fontWeight'])}, {float(v['fontSize'])}f, {float(v['lineHeight'])}f)"
    )
lines += ["}", ""]
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("generated", out, "| warna:", len(seen))
