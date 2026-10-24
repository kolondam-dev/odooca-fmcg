#!/usr/bin/env python3
"""Pemeriksaan statis addon id_*: manifest, lisensi, versi, struktur. Exit 1 bila ada pelanggaran."""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDONS = ROOT / "addons"
REQUIRED = ("name", "version", "license", "depends", "installable")
errors = []

mods = sorted(p for p in ADDONS.iterdir() if p.is_dir() and not p.name.startswith("."))
names = {p.name for p in mods}
for mod in mods:
    mf = mod / "__manifest__.py"
    if not mf.exists():
        errors.append(f"{mod.name}: __manifest__.py tidak ada")
        continue
    try:
        m = ast.literal_eval(mf.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{mod.name}: manifest tidak valid ({e})")
        continue
    for k in REQUIRED:
        if k not in m:
            errors.append(f"{mod.name}: kunci '{k}' tidak ada")
    if not mod.name.startswith("id_"):
        errors.append(f"{mod.name}: nama addon harus berawalan 'id_'")
    if m.get("license") != "LGPL-3":
        errors.append(f"{mod.name}: license harus 'LGPL-3' (ada: {m.get('license')!r})")
    if not str(m.get("version", "")).startswith("19.0."):
        errors.append(f"{mod.name}: version harus berawalan '19.0.'")
    if not (mod / "__init__.py").exists():
        errors.append(f"{mod.name}: __init__.py tidak ada")
    for d in m.get("depends", []):
        if d.startswith("id_") and d not in names:
            errors.append(f"{mod.name}: depends '{d}' tidak ditemukan di addons/")
    for f in m.get("data", []):
        if not (mod / f).exists():
            errors.append(f"{mod.name}: berkas data '{f}' tidak ada")

if errors:
    print("PELANGGARAN MANIFEST:")
    print("\n".join(" - " + e for e in errors))
    sys.exit(1)
print(f"manifest ok: {len(mods)} addon ({', '.join(m.name for m in mods)})")
