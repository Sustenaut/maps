"""Build the whole site: every area pack areas.json lists, the overview,
the index, and the map package.

    out/index.json                    what is here: the overview and each area
                                      pack, with where its pieces are
    out/packs/eesti/<hash>/<n>.bin    the overview, in pieces
    out/packs/<path>/<hash>/<n>.bin   one pack per area, in pieces
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
# Cloudflare Pages answers no range request: it always sends the whole
# file, and a PMTiles reader needs a few kilobytes at a time. So each pack
# is served as pieces of this size, named by number, and the map package
# reads the pieces a request needs. Clustered PMTiles keep neighbouring
# tiles together, so one piece usually holds a view's tiles.
# MAPS_CHUNK (bytes) lets the tests split small packs.
CHUNK = int(os.environ.get("MAPS_CHUNK", 128 * 1024))

# The map library the package loads, copied from node_modules.
VENDOR = {
    "maplibre/maplibre-gl.mjs": "maplibre-gl/dist/maplibre-gl.mjs",
    "maplibre/maplibre-gl-worker.mjs": "maplibre-gl/dist/maplibre-gl-worker.mjs",
    "maplibre/maplibre-gl.css": "maplibre-gl/dist/maplibre-gl.css",
    "maplibre/LICENSE.txt": "maplibre-gl/LICENSE.txt",
    "pmtiles.js": "pmtiles/dist/pmtiles.js",
}

HEADERS = """\
# Any site may use the maps.
/*
  Access-Control-Allow-Origin: *
/index.json
  Cache-Control: public, max-age=300
/packs/*
  Cache-Control: public, max-age=31536000, immutable
/lib/*
  Cache-Control: public, max-age=3600
"""


def pieces(pack: Path, out: Path, path: str) -> dict:
    """Split a pack into out/packs/<path>/<hash>/<n>.bin and remove it. The
    hash of its content names the folder, so a changed pack gets new names
    and browsers can cache every piece for good."""
    data = pack.read_bytes()
    folder = Path("packs") / path / hashlib.sha256(data).hexdigest()[:12]
    (out / folder).mkdir(parents=True)
    for n, start in enumerate(range(0, len(data), CHUNK)):
        (out / folder / f"{n}.bin").write_bytes(data[start:start + CHUNK])
    pack.unlink()
    return {"dir": folder.as_posix(), "size": len(data), "chunk": CHUNK}


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
        pack = tmp / "overview.pmtiles"
        overview.build(data, pack, tmp / "overview")
        index["overview"] = pieces(pack, out, "eesti")
    for entry in areas:
        pack = tmp / entry["path"] / "map.pmtiles"
        meta = area.build(data, entry["name"], entry["path"], pack, tmp / entry["path"] / "layers")
        index["areas"].append({"path": entry["path"], **meta, "pack": pieces(pack, out, entry["path"])})

    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shutil.copytree(ROOT / "lib", out / "lib")
    for target, source in VENDOR.items():
        dest = out / "lib" / "v1" / "vendor" / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(node_modules / source, dest)
    shutil.copytree(ROOT / "site", out, dirs_exist_ok=True)
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    return index

