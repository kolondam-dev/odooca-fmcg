"""Reviewable evidence writer for the native D1 browser runner."""
import atexit
import hashlib
import html
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(os.environ.get("D1_SCREENSHOT_DIR", "d1-visual"))
DIRECTORY.mkdir(parents=True, exist_ok=True)
PAGE = None
REPORT = {"status": "FAIL", "checks": [], "screenshots": [], "failures": [],
          "level": "native Odoo HTTP/OWL; one deliberate initial get_data RPC fault", "source_sha256": {}}


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


REPORT["source_head"] = os.environ.get("D1_SOURCE_SHA", git("rev-parse", "HEAD"))
REPORT["checkout_sha"] = git("rev-parse", "HEAD")
REPORT["checkout_tree"] = git("rev-parse", "HEAD^{tree}")
REPORT["run_id"] = os.environ.get("GITHUB_RUN_ID")
REPORT["source_worktree_dirty"] = bool(git("status", "--porcelain", "--", "addons/id_dashboard_ui",
    "addons/id_dashboard_redesign", "scripts/ui", ".github/workflows/ci.yml"))
for addon in ("id_dashboard_ui", "id_dashboard_redesign"):
    for file in sorted((ROOT / "addons" / addon).rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts:
            REPORT["source_sha256"][str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
if runtime_file := os.environ.get("D1_RUNTIME_SOURCES_FILE"):
    runtime = json.loads(Path(runtime_file).read_text())
    if runtime != REPORT["source_sha256"]:
        raise AssertionError("Odoo image source differs from the checked-out D1 source")
    REPORT["runtime_source_verified"] = True
REPORT["image_digest"] = os.environ.get("D1_IMAGE_DIGEST")
reference = DIRECTORY / "reference"
reference.mkdir(exist_ok=True)
for file in (ROOT / "scripts/ui/reference/d1").iterdir():
    if file.is_file():
        shutil.copyfile(file, reference / file.name)
        REPORT["source_sha256"][str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()


def set_page(page):
    global PAGE
    PAGE = page


def capture(page, name):
    file = DIRECTORY / f"{name}.png"
    page.screenshot(path=str(file), full_page=True)
    if file.name not in REPORT["screenshots"]:
        REPORT["screenshots"].append(file.name)


def full_dashboard(page, name):
    """Stitch actual scroll captures, without changing DOM/CSS or the layout."""
    host = page.locator(".id-dash-action")
    box = host.bounding_box()
    metrics = host.evaluate("el => ({height:el.scrollHeight, client:el.clientHeight, top:el.scrollTop})")
    width, height = round(box["width"]), metrics["height"]
    canvas = Image.new("RGB", (width, height), "white")
    top = 0
    while True:
        host.evaluate("(el, top) => el.scrollTop = top", top)
        page.wait_for_timeout(80)
        actual = host.evaluate("el => el.scrollTop")
        piece = DIRECTORY / f"{name}-scroll-{actual}.png"
        page.screenshot(path=str(piece), clip={"x": box["x"], "y": box["y"],
                                             "width": width, "height": metrics["client"]})
        canvas.paste(Image.open(piece).convert("RGB"), (0, actual))
        REPORT["screenshots"].append(piece.name)
        if actual + metrics["client"] >= height:
            break
        top = min(actual + metrics["client"], height - metrics["client"])
    file = DIRECTORY / f"{name}-full.png"
    canvas.save(file)
    if file.name not in REPORT["screenshots"]:
        REPORT["screenshots"].append(file.name)
    host.evaluate("(el, top) => el.scrollTop = top", metrics["top"])
    REPORT.setdefault("stitched_views", []).append({"file": file.name, "method": "unaltered native scroll captures",
                                                   "width": width, "height": height})


def checked(ok, name):
    if not ok:
        REPORT["failures"].append(name)
        if PAGE and not PAGE.is_closed():
            capture(PAGE, "failure")
        raise AssertionError(name)
    REPORT["checks"].append(name)


def write_report():
    for name in REPORT["screenshots"]:
        file = DIRECTORY / name
        with Image.open(file) as picture:
            REPORT.setdefault("images", {})[name] = {"sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                                                     "width": picture.width, "height": picture.height}
    (DIRECTORY / "report.json").write_text(json.dumps(REPORT, indent=2) + "\n")
    cards = "".join(f'<section><h2>{html.escape(name)}</h2><a href="{name}"><img src="{name}"/></a></section>'
                    for name in REPORT["screenshots"])
    (DIRECTORY / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>D1 native evidence</title>'
        '<style>body{font:14px system-ui;margin:24px}img{max-width:100%;border:1px solid #ddd}'
        'section{margin:24px 0}</style>'
        f'<h1>D1 native evidence: {REPORT["status"]}</h1><p>Source HEAD: {REPORT["source_head"]}</p>'
        '<p><a href="report.json">Browser report and image hashes</a> · '
        '<a href="fixture.json">Native reconciliation and roles</a> · '
        '<a href="reference/approved.png">Approved PNG</a> · '
        '<a href="reference/approved-controls.html">Approved v2 controls</a> · '
        '<a href="reference/DEVIATIONS.md">Recorded deviations and acceptance limits</a></p>' + cards)


atexit.register(write_report)
