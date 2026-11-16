#!/usr/bin/env python3
"""Reject PO occurrence comments that Odoo 19's importer cannot parse."""

from __future__ import annotations

import argparse
from pathlib import Path


ODOO_OCCURRENCE_PREFIXES = ("code:", "model:", "model_terms:")


def invalid_occurrences(path: Path) -> list[tuple[int, str]]:
    invalid: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.startswith("#: "):
            continue
        for occurrence in line[3:].split():
            if not occurrence.startswith(ODOO_OCCURRENCE_PREFIXES):
                invalid.append((number, occurrence))
    return invalid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted(Path("addons").glob("*/i18n/*.po"))
    failures = [(path, row) for path in paths for row in invalid_occurrences(path)]
    for path, (number, occurrence) in failures:
        print(f"{path}:{number}: invalid Odoo PO occurrence: {occurrence}")
    if failures:
        print("Use Odoo occurrences such as code:addons/<module>/<file>:0, not bare source paths.")
        return 1
    print(f"PO occurrences ok: {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
