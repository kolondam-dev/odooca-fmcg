#!/usr/bin/env python3
"""Select the minimum safe CI suites from a Git diff.

Selection is intentionally fail-closed. Unknown paths and changes to CI
selection/control files select every suite. Explicit overrides can only add
suites or force the full plan; they can never remove an automatically selected
suite.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".ci" / "test-impact.yml"


@dataclass(frozen=True)
class Selection:
    files: tuple[str, ...]
    suites: tuple[str, ...]
    reasons: dict[str, tuple[str, ...]]
    unknown: tuple[str, ...]
    full: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "suites": list(self.suites),
            "reasons": {key: list(value) for key, value in self.reasons.items()},
            "unknown": list(self.unknown),
            "full": self.full,
        }


def _matches(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    return fnmatch.fnmatchcase(path, pattern)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError(f"Unsupported impact config: {path}")
    all_suites = data.get("all_suites")
    if not isinstance(all_suites, list) or not all_suites:
        raise ValueError("all_suites must be a non-empty list")
    if len(all_suites) != len(set(all_suites)):
        raise ValueError("all_suites contains duplicates")
    known = set(all_suites)
    for rule in data.get("rules", []):
        unknown = set(rule.get("suites", [])) - known
        if unknown:
            raise ValueError(f"Rule {rule.get('name')} has unknown suites: {unknown}")
    return data


def select(
    files: list[str],
    config: dict[str, Any],
    *,
    force_all: bool = False,
    force_suites: tuple[str, ...] = (),
) -> Selection:
    normalized_paths: set[str] = set()
    for item in files:
        path = item.strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path:
            normalized_paths.add(path)
    normalized = tuple(sorted(normalized_paths))
    all_suites = tuple(config["all_suites"])
    known = set(all_suites)
    invalid_forced = set(force_suites) - known
    if invalid_forced:
        raise ValueError(f"Unknown forced suites: {sorted(invalid_forced)}")

    selected: set[str] = set(force_suites)
    reasons: dict[str, list[str]] = {suite: ["explicit additive override"] for suite in force_suites}
    unknown_paths: list[str] = []
    full = force_all
    if force_all:
        selected.update(all_suites)
        for suite in all_suites:
            reasons.setdefault(suite, []).append("full regression requested")

    for changed in normalized:
        if any(_matches(changed, pattern) for pattern in config.get("always_full", [])):
            full = True
            selected.update(all_suites)
            for suite in all_suites:
                reasons.setdefault(suite, []).append(f"control-plane change: {changed}")
            continue

        matching_rules = [
            rule
            for rule in config.get("rules", [])
            if any(_matches(changed, pattern) for pattern in rule.get("paths", []))
        ]
        if matching_rules:
            for rule in matching_rules:
                for suite in rule["suites"]:
                    selected.add(suite)
                    reasons.setdefault(suite, []).append(f"{rule['name']}: {changed}")
            continue

        if any(_matches(changed, pattern) for pattern in config.get("ignore_runtime", [])):
            continue

        # A new top-level area must not silently evade runtime verification.
        unknown_paths.append(changed)
        full = True
        selected.update(all_suites)
        for suite in all_suites:
            reasons.setdefault(suite, []).append(f"unmapped path (fail-closed): {changed}")

    ordered = tuple(suite for suite in all_suites if suite in selected)
    return Selection(
        files=normalized,
        suites=ordered,
        reasons={suite: tuple(dict.fromkeys(reasons.get(suite, []))) for suite in ordered},
        unknown=tuple(unknown_paths),
        full=full,
    )


def changed_files(base: str, head: str) -> list[str]:
    command = ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    return [line for line in result.stdout.splitlines() if line.strip()]


def write_github_outputs(path: Path, selection: Selection, all_suites: list[str]) -> None:
    selected = set(selection.suites)
    with path.open("a", encoding="utf-8") as handle:
        for suite in all_suites:
            handle.write(f"{suite}={'true' if suite in selected else 'false'}\n")
        handle.write(f"full={'true' if selection.full else 'false'}\n")
        handle.write(f"has_runtime={'true' if selection.suites else 'false'}\n")
        handle.write(f"plan={json.dumps(selection.as_dict(), separators=(',', ':'))}\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Git base revision")
    parser.add_argument("--head", default="HEAD", help="Git head revision")
    parser.add_argument("--files", nargs="*", help="Explicit changed paths (mainly for tests/local use)")
    parser.add_argument("--files-from", type=Path, help="Read changed paths from a newline-delimited file")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--force-all", action="store_true")
    parser.add_argument("--force-suite", action="append", default=[])
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.files is not None:
        files = args.files
    elif args.files_from:
        files = args.files_from.read_text(encoding="utf-8").splitlines()
    elif args.base:
        files = changed_files(args.base, args.head)
    else:
        raise SystemExit("Provide --base, --files, or --files-from")

    config = load_config(args.config)
    result = select(
        files,
        config,
        force_all=args.force_all,
        force_suites=tuple(args.force_suite),
    )
    payload = json.dumps(result.as_dict(), indent=2, sort_keys=True)
    print(payload)
    if args.json_out:
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    if args.github_output:
        write_github_outputs(args.github_output, result, config["all_suites"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
