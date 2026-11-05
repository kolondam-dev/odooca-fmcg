#!/usr/bin/env python3
"""Compare runtime candidate manifests with exact project OCA pins.

Input is private inventory JSON; output contains only software metadata. An image
manifest match is not a module installation/functional acceptance claim.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request


def verify(name, source, pins):
    row = {"module": name, **source}
    row["pin_verification"] = "NOT_OCA_OR_NO_SOURCE"
    paths = source.get("paths", [])
    if len(paths) != 1 or not paths[0].startswith("/opt/oca/"):
        return row
    repo = paths[0].split("/")[3]
    sha = pins.get(repo)
    row.update(repository=repo, source_sha=sha)
    if not sha:
        row["pin_verification"] = "MISSING_LOCK_PIN"
        return row
    url = f"https://raw.githubusercontent.com/OCA/{repo}/{sha}/{name}/__manifest__.py"
    row["manifest_url"] = url
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            digest = hashlib.sha256(response.read()).hexdigest()
        row["pin_verification"] = "MATCH" if digest == source.get("sha256") else "MISMATCH"
    except (OSError, urllib.error.URLError) as exc:
        row["pin_verification"] = "FETCH_FAILED"
        row["error_type"] = type(exc).__name__
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--lock", type=Path, default=Path("oca.lock"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # PowerShell redirection may produce UTF-16; handle it without modifying input.
    raw = args.inventory.read_bytes()
    inventory = json.loads(raw.decode("utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig"))
    pins = {}
    for line in args.lock.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            repo, _branch, sha = line.split()
            pins[repo] = sha
    sources = inventory["sources"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda item: verify(item[0], item[1], pins), sorted(sources.items())))
    installed = {item["name"]: item for item in inventory["database"].get("modules", [])}
    for row in rows:
        state = installed.get(row["module"], {})
        row["registry_state"] = state.get("state", "NOT_IN_REGISTRY")
        row["registry_version"] = state.get("latest_version")
    output = {
        "observed_at": inventory["observed_at"],
        "lock_sha256": hashlib.sha256(args.lock.read_bytes()).hexdigest(),
        "candidates": inventory["candidates"], "modules": rows,
        "acceptance": "MANIFEST_AND_REGISTRY_ONLY; no install, ACL, or report acceptance",
    }
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = [r["module"] for r in rows if r["pin_verification"] in (
        "MISSING_LOCK_PIN", "MISMATCH", "FETCH_FAILED",
    )]
    print(f"Modules: {len(rows)}; OCA matches: {sum(r['pin_verification'] == 'MATCH' for r in rows)}")
    print(f"Pin verification failures: {failures}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
