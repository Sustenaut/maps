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

With --cache, each pack is made through `pubkit cache run`, by the entries
of pubkit.json's cache block (`packs` per area, `overview`): a pack whose inputs (its data, the municipality
boundaries, mapbuild's code and tippecanoe's version) have not changed is
copied from the cache instead of made again, and `pubkit cache prune`
then drops what this build did not use.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import area, municipalities as municipality_list, overview
from .places import checked
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


def pubkit() -> str:
    """The pubkit to make packs through: MAPS_PUBKIT, this repository's
    .venv, or the one on PATH."""
    venv = ROOT / ".venv" / "bin" / "pubkit"
    return os.environ.get("MAPS_PUBKIT") or (str(venv) if venv.exists() else "pubkit")


def cached(root: Path, name: str, unit: str | None, outputs: list[Path], command: list[str]) -> bool:
    """Make `outputs` with `command` through `pubkit cache run`, in `root`,
    where pubkit.json's cache entries are; True when they were reused."""
    args = [pubkit(), "cache", "run", name, *([f"--unit={unit}"] if unit is not None else []),
            *[f"--output={o}" for o in outputs], "--", *command]
    env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    done = subprocess.run(args, cwd=root, stdout=subprocess.PIPE, text=True, env=env)
    if done.returncode:
        raise SystemExit(f"maps: pubkit cache run {name} failed (exit {done.returncode})")
    return done.stdout.startswith("reused")


def build(data: Path, out: Path, areas_file: Path, node_modules: Path, tmp: Path, centres: Path,
          cache: Path | None = None) -> dict:
    """Write the site. With `cache`, the directory holding pubkit.json's
    cache entries (the repository, as a rule), packs are made through
    `pubkit cache run` there. The entries name the data as `data/` in that
    directory, so --data must be it."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    areas = json.loads(areas_file.read_text(encoding="utf-8"))["areas"]
    for entry in areas:
        checked(entry["path"])
    unknown = [a["name"] for a in areas if a["name"] not in municipalities(data)]
    if unknown:
        raise SystemExit(f"maps: not municipalities in {data / 'boundaries.geojsonl'}: {', '.join(unknown)}")

    index = {"version": 1, "attribution": area.ATTRIBUTION, "overview": None, "areas": []}
    data = data.resolve()
    if cache and data != (cache / "data").resolve():
        raise SystemExit(f"maps: --cache fingerprints the data at {cache / 'data'} (pubkit.json's cache "
                         f"entries), so build from it, not from {data}")
    hits, made = 0, 0
    if (data / "national").exists():
        pack = tmp / "overview.pmtiles"
        if cache:
            hits += cached(cache, "overview", None, [pack],
                           [sys.executable, "-m", "mapbuild", "build-overview", "--data", str(data), "--pack", str(pack)])
        else:
            overview.build(data, pack, tmp / "overview")
        made += 1
        index["overview"] = pieces(pack, out, "eesti")
    for entry in areas:
        pack = tmp / entry["path"] / "map.pmtiles"
        meta_file = tmp / entry["path"] / "meta.json"
        if cache:
            hits += cached(cache, "packs", entry["path"], [pack, meta_file],
                           [sys.executable, "-m", "mapbuild", "build-area", "--data", str(data),
                            "--pack", str(pack), "--meta", str(meta_file),
                            # After --, a name is never read as an option.
                            "--", entry["name"], entry["path"]])
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        else:
            meta = area.build(data, entry["name"], entry["path"], pack, tmp / entry["path"] / "layers")
        made += 1
        index["areas"].append({"path": entry["path"], **meta, "pack": pieces(pack, out, entry["path"])})
    if cache:
        subprocess.run([pubkit(), "cache", "prune"], cwd=cache, check=True, stdout=subprocess.DEVNULL)

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
        print(f"maps: reused {hits} of {made} pack(s) through pubkit cache")
    return index

