"""Which areas to build: those areas.json lists, and every municipality a
place of the sites that use the maps is in.

areas.json:

    "places":  where sites list their places ({"version": 1, "places":
               [{"id", "lat", "lng"}]}, as visit.ee's /map-places.json),
               an https address or a file
    "areas":   areas built whether or not a place is in them, by EHAK
               name (and a path of their own, which wins over the one
               made up)

An area's path is its county and its name: Rõuge vald, in Võru maakond,
is vorumaa/rouge.

`maps download` writes the result to data/areas.json, each area with the
places in it, and `maps build` builds what it says. An area's places are
kept beside its data (data/areas/<path>/places.json): when they change,
its layers are downloaded again, so a pack is made again only when a
place is added to or removed from its area (or the cache is refreshed).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .sources import municipalities

PLAN = "areas.json"
# An area's path: lower-case words joined by - and /, such as vorumaa/rouge.
AREA_PATH = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*")


def checked(path: str) -> str:
    """The path, when it is an area's. It names folders under data/areas,
    the build's and the site's, so one such as ../x would reach outside
    them."""
    if not isinstance(path, str) or not AREA_PATH.fullmatch(path):
        raise SystemExit(f"maps: not an area path: {path!r}")
    return path


def read_places(source: str, base: Path) -> list[dict]:
    """The places one site lists, from an https address or a file."""
    if source.startswith(("https://", "http://")):
        request = urllib.request.Request(source, headers={"User-Agent": "maps.sustenaut.eu"})
        with urllib.request.urlopen(request, timeout=60) as response:
            listed = json.load(response)
    else:
        listed = json.loads((base / source).read_text(encoding="utf-8"))
    if listed.get("version") != 1:
        raise SystemExit(f"maps: {source}: not a places list of version 1")
    return listed["places"]


def slug(name: str, names: set[str]) -> str:
    """A municipality's part of the path: Rõuge vald is rouge, Võru linn
    voru, and Võru vald, beside it, voru-vald."""
    base = name
    for kind in (" vald", " linn"):
        if name.endswith(kind):
            base = name[: -len(kind)]
            if kind == " vald" and base + " linn" in names:
                base = name
    folded = unicodedata.normalize("NFKD", base.lower()).encode("ascii", "ignore").decode()
    return "-".join(folded.split())


def county(name: str) -> str:
    """A county's part of the path: Võru maakond is vorumaa, Ida-Viru
    maakond ida-virumaa."""
    return slug(name.removesuffix(" maakond") + "maa", set())


def plan(data: Path, areas_file: Path) -> list[dict]:
    """The areas to build, each with the ids of the places in it, sorted by
    path. Places outside every municipality are named and left out."""
    config = json.loads(areas_file.read_text(encoding="utf-8"))
    boundaries = municipalities(data)
    names = sorted(boundaries)
    shapes = [shape(boundaries[n]["geometry"]) for n in names]
    tree = STRtree(shapes)

    found: dict[str, set[str]] = {}
    outside = []
    for source in config.get("places", []):
        for place in read_places(source, areas_file.parent):
            point = Point(place["lng"], place["lat"])
            hits = [names[i] for i in tree.query(point, predicate="intersects")]
            if hits:
                found.setdefault(hits[0], set()).add(place["id"])
            else:
                outside.append(place["id"])
    if outside:
        print(f"maps: in no municipality, so no area: {', '.join(sorted(outside))}", file=sys.stderr)

    listed = {a["name"]: a.get("path") for a in config.get("areas", [])}
    unknown = sorted(n for n in listed if n not in boundaries)
    if unknown:
        raise SystemExit(f"maps: not municipalities in {data / 'boundaries.geojsonl'}: {', '.join(unknown)}")
    every = set(names)
    out = []
    for name in sorted(set(listed) | set(found)):
        path = listed.get(name)
        if not path:
            home = boundaries[name]["properties"].get("maakond")
            if not home:
                raise SystemExit(f"maps: {name} has no county in {data / 'boundaries.geojsonl'}")
            path = f"{county(home)}/{slug(name, every)}"
        out.append({"name": name, "path": checked(path), "places": sorted(found.get(name, ()))})
    return sorted(out, key=lambda a: a["path"])


def write_plan(data: Path, areas: list[dict]) -> Path:
    path = data / PLAN
    path.write_text(json.dumps({"areas": areas}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def keep(data: Path, entry: dict) -> bool:
    """Note the area's places beside its data. When they differ from what
    was noted, its layers are dropped, so the download fetches them again
    and the pack is made again; True then."""
    folder = data / "areas" / checked(entry["path"])
    noted = folder / "places.json"
    places = json.dumps(entry["places"], ensure_ascii=False) + "\n"
    changed = noted.is_file() and noted.read_text(encoding="utf-8") != places
    if changed:
        for f in folder.iterdir():
            if f.name.endswith((".geojsonl", ".done")):
                f.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    noted.write_text(places, encoding="utf-8")
    return changed
