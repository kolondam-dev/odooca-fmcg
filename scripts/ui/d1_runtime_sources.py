"""Hash the actual two addon trees inside the Odoo image for the CI evidence chain."""
import hashlib
import json
from pathlib import Path

root = Path("/opt/id-addons")
files = {}
for addon in ("id_dashboard_ui", "id_dashboard_redesign"):
    for file in sorted((root / addon).rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts:
            files["addons/" + str(file.relative_to(root))] = hashlib.sha256(file.read_bytes()).hexdigest()
print(json.dumps(files, indent=2))
