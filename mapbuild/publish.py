"""Build the whole site: every area pack areas.json lists, the overview,
the index, and the map package.

    out/index.json                    what is here: the overview and each area
                                      pack, with content-hashed file names
    out/eesti/overview.<hash>.pmtiles
    out/<path>/map.<hash>.pmtiles     one per area, at the area's path
    out/lib/v1/...                    the map package (lib/v1 in the repository)
    out/_headers                      CORS and caching for Cloudflare Pages
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from . import area, overview
from .sources import municipalities

ROOT = Path(__file__).resolve().parents[1]
# Cloudflare Pages serves no file over 25 MiB. MAPS_MAX_FILE (bytes) lets
# the tests reach the limit with small packs.
MAX_FILE = int(os.environ.get("MAPS_MAX_FILE", 25 * 1024 * 1024))

# The map library the package loads, copied from node_modules.
VENDOR = {
    "maplibre/maplibre-gl.mjs": "maplibre-gl/dist/maplibre-gl.mjs",
    "maplibre/maplibre-gl-worker.mjs": "maplibre-gl/dist/maplibre-gl-worker.mjs",
    "maplibre/maplibre-gl.css": "maplibre-gl/dist/maplibre-gl.css",
    "maplibre/LICENSE.txt": "maplibre-gl/LICENSE.txt",
    "pmtiles.js": "pmtiles/dist/pmtiles.js",
}

HEADERS = """\
# Any site may use the maps: the tiles are read with range requests.
/*
  Access-Control-Allow-Origin: *
  Access-Control-Allow-Headers: Range
  Access-Control-Expose-Headers: Content-Length, Content-Range, ETag
/index.json
  Cache-Control: public, max-age=300
/*.pmtiles
  Cache-Control: public, max-age=31536000, immutable
/lib/*
  Cache-Control: public, max-age=3600
"""


def hashed(path: Path) -> Path:
    """Rename map.pmtiles to map.<hash>.pmtiles, so a changed pack gets a
    new name and browsers can cache each one for good."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    target = path.with_name(f"{path.stem}.{digest}{path.suffix}")
    path.replace(target)
    size = target.stat().st_size
    if size > MAX_FILE:
        raise SystemExit(f"maps: {target} is {size} bytes, over the Pages limit of {MAX_FILE}")
    return target


def build(data: Path, out: Path, areas_file: Path, node_modules: Path, tmp: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    areas = json.loads(areas_file.read_text(encoding="utf-8"))["areas"]
    unknown = [a["name"] for a in areas if a["name"] not in municipalities(data)]
    if unknown:
        raise SystemExit(f"maps: not municipalities in {data / 'boundaries.geojsonl'}: {', '.join(unknown)}")

    index = {"version": 1, "attribution": area.ATTRIBUTION, "overview": None, "areas": []}
    if (data / "national").exists():
        ov = hashed(_built(lambda p: overview.build(data, p, tmp / "overview"), out / "eesti" / "overview.pmtiles"))
        index["overview"] = ov.relative_to(out).as_posix()
    for entry in areas:
        pack = out / entry["path"] / "map.pmtiles"
        meta = area.build(data, entry["name"], entry["path"], pack, tmp / entry["path"])
        index["areas"].append({"path": entry["path"], **meta, "file": hashed(pack).relative_to(out).as_posix()})

    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shutil.copytree(ROOT / "lib", out / "lib")
    for target, source in VENDOR.items():
        dest = out / "lib" / "v1" / "vendor" / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(node_modules / source, dest)
    shutil.copytree(ROOT / "site", out, dirs_exist_ok=True)
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    return index


def _built(make, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    make(path)
    return path
