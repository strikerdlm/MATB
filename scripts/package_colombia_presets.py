import json, subprocess, os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
regions = json.loads(
    (root / "webui/frontend/public/geography/regions.json").read_text(encoding="utf-8")
)
for site in regions[1:]:
    output = root / "webui/frontend/public/scenes" / f'{site["id"]}-v1'
    if output.exists():
        continue
    command = [
        os.sys.executable,
        "-X",
        "utf8",
        str(root / "scripts/package_suas_scene.py"),
        "--output",
        str(output),
        "--lat",
        str(site["lat"]),
        "--lon",
        str(site["lon"]),
        "--title",
        site["title"],
        "--region",
        site["region"],
        "--end-date",
        "2026-09-08",
    ]
    result = subprocess.run(command, cwd=root)
    print(site["id"], result.returncode, flush=True)
