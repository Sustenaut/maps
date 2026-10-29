"""Build the whole site: every area pack areas.json lists, the overview,
the index, and the map package.

    out/index.json                    what is here: the overview and each area
                                      pack, with where its pieces are
    out/municipalities.json           every municipality: its name, where to
                                      label it, its box and its centre
    out/packs/eesti/<hash>/<n>.bin    the overview, in pieces
    out/packs/<path>/<hash>/<n>.bin   one pack per area, in pieces
    out/lib/v1/...                    the map package (lib/v1 in the repository)
    out/_headers                      CORS and caching for Cloudflare Pages

With a cache directory, a pack whose inputs have not changed is not built
again: each pack is kept there under a fingerprint of what made it (its
data files, the municipality boundaries, mapbuild's code and tippecanoe's
version), and reused while the fingerprint matches. Packs no longer made
are removed from the cache after each build, so it never grows past one
build's packs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import area, municipalities as municipality_list, overview
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
/municipalities.json
  Cache-Control: public, max-age=3600
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


def code_fingerprint() -> str:
    """What every pack depends on besides its data: mapbuild's code and
    tippecanoe's version."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "mapbuild").glob("*.py")):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    try:
        version = subprocess.run(["tippecanoe", "--version"], capture_output=True, text=True).stderr
    except FileNotFoundError:
        version = "no tippecanoe"
    h.update(version.strip().encode())
    return h.hexdigest()


def fingerprint(base: str, *inputs: Path, label: str) -> str:
    """A pack's fingerprint: `base`, `label`, and every file in `inputs`
    (a file, or a directory read whole), by name and content."""
    h = hashlib.sha256(base.encode() + b"\0" + label.encode() + b"\0")
    for root in inputs:
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root] if root.exists() else []
        for f in files:
            h.update(str(f.relative_to(root.parent)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:32]


class PackCache:
    """Packs kept under their fingerprints: <key>.pmtiles, and <key>.json for
    what the index says of an area. No directory: nothing is kept."""

    def __init__(self, root: Path | None):
        self.root, self.used, self.hits = root, set(), 0
        if root:
            root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, pack: Path) -> dict | None:
        if not self.root or not (self.root / f"{key}.pmtiles").exists():
            return None
        pack.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.root / f"{key}.pmtiles", pack)
        meta = self.root / f"{key}.json"
        self.used.add(key)
        self.hits += 1
        return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}

    def put(self, key: str, pack: Path, meta: dict | None = None) -> None:
        if not self.root:
            return
        shutil.copy(pack, self.root / f"{key}.pmtiles")
        if meta is not None:
            (self.root / f"{key}.json").write_text(json.dumps(meta), encoding="utf-8")
        self.used.add(key)

    def prune(self) -> None:
        if self.root:
            for f in self.root.iterdir():
                if f.stem not in self.used:
                    f.unlink()


def build(data: Path, out: Path, areas_file: Path, node_modules: Path, tmp: Path, centres: Path,
          cache: Path | None = None) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    areas = json.loads(areas_file.read_text(encoding="utf-8"))["areas"]
    unknown = [a["name"] for a in areas if a["name"] not in municipalities(data)]
    if unknown:
        raise SystemExit(f"maps: not municipalities in {data / 'boundaries.geojsonl'}: {', '.join(unknown)}")

    index = {"version": 1, "attribution": area.ATTRIBUTION, "overview": None, "areas": []}
    kept = PackCache(cache)
    code = code_fingerprint()
    boundaries = data / "boundaries.geojsonl"
    if (data / "national").exists():
        pack = tmp / "overview.pmtiles"
        key = fingerprint(code, data / "national", boundaries, label="overview")
        if kept.get(key, pack) is None:
            overview.build(data, pack, tmp / "overview")
            kept.put(key, pack)
        index["overview"] = pieces(pack, out, "eesti")
    for entry in areas:
        pack = tmp / entry["path"] / "map.pmtiles"
        key = fingerprint(code, data / "areas" / entry["path"], boundaries,
                          label=f"{entry['name']}\0{entry['path']}")
        meta = kept.get(key, pack)
        if meta is None:
            meta = area.build(data, entry["name"], entry["path"], pack, tmp / entry["path"] / "layers")
            kept.put(key, pack, meta)
        index["areas"].append({"path": entry["path"], **meta, "pack": pieces(pack, out, entry["path"])})
    kept.prune()
    index_hits = kept.hits

    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    listed = municipality_list.build(data, centres)
    (out / "municipalities.json").write_text(json.dumps(listed, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copytree(ROOT / "lib", out / "lib")
    for target, source in VENDOR.items():
        dest = out / "lib" / "v1" / "vendor" / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(node_modules / source, dest)
    shutil.copytree(ROOT / "site", out, dirs_exist_ok=True)
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    if cache:
        print(f"maps: reused {index_hits} of {len(areas) + (1 if index['overview'] else 0)} pack(s) from {cache}")
    return index

