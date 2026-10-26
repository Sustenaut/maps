"""Build one area pack: a municipality's map tiles, zoom 8 to 15.

The pack covers every zoom-13 tile whose largest land overlap is this
municipality, so neighbouring packs meet without gaps or overlaps and the
coast is not cut off. Layers (each feature carries the zoom it first shows
at, as "mz"):

    road        class: primary, secondary, tertiary, link, street, minor,
                path, cycleway, track; name on named roads
    rail        class: rail, cable
    water       class: sea, lake, river; name
    waterway    class: river, stream, ditch; name
    landcover   class: forest, scrub, fen, bog, wet_meadow, farmland,
                grass, sand, open, yard, peat, other
    building    use (from the Building Register's use code): residential,
                lodging, shop, office, culture, education, health, sport,
                religious, farm, industry, ruin, other, unknown; zoom 14+
    place_label name, class: the settlement type
    trail       class: hiking, cycling, long_distance; name (RMK)
    poi         kind, name (RMK visitor sites)
    boundary    name, self: this municipality's border and its neighbours'
"""

from __future__ import annotations

import collections
import json
import math
import re
import subprocess
from pathlib import Path

from shapely import force_2d, make_valid
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

from .sources import municipalities, read

# The sources' licences ask that maps name them. MapLibre shows this on
# every map, from each pack's metadata and from index.json.
ATTRIBUTION = ('<a href="https://maaruum.ee" target="_blank" rel="noopener">© Maa- ja Ruumiamet</a> (ETAK, EHAK, EHR)'
               ' · <a href="https://www.rmk.ee" target="_blank" rel="noopener">© RMK</a>')
TILE_ZOOM = 13

ROAD = {10: ("primary", 8), 20: ("secondary", 8), 30: ("tertiary", 10), 40: ("link", 11),
        50: ("street", 12), 60: ("minor", 12), 70: ("path", 13), 80: ("cycleway", 13)}
RIVER = {10: ("river", 9), 30: ("stream", 11), 40: ("ditch", 13), 50: ("ditch", 13)}
LANDCOVER = {
    "wood": {10: ("forest", 9), 30: ("scrub", 11)},
    "wetland": {10: ("fen", 9), 20: ("bog", 9), 30: ("bog", 9), 40: ("wet_meadow", 11)},
    "field": {None: ("farmland", 11)},
    "open": {10: ("grass", 11), 20: ("sand", 11), 30: ("open", 11)},
    "yard": {None: ("yard", 12)},
    "peat": {None: ("peat", 10)},
    "other_lc": {None: ("other", 12)},
}


def building_use(code: str | None) -> str:
    """A coarse class from an EHR use code (CC-EST), such as 12111."""
    c = (code or "").split(";")[0]
    if not c:
        return "unknown"
    if c[:3] in ("111", "112", "113") or c == "12744":
        return "residential"
    for prefix, use in (("121", "lodging"), ("123", "shop"), ("122", "office"), ("1261", "culture"),
                        ("1262", "culture"), ("1263", "education"), ("1264", "health"), ("1265", "sport"),
                        ("1272", "religious"), ("1271", "farm"), ("124", "industry"), ("125", "industry")):
        if c.startswith(prefix):
            return use
    return "other"


def _tile_box(x: int, y: int, z: int):
    lon = lambda x: x / 2 ** z * 360 - 180
    lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))
    return box(lon(x), lat(y + 1), lon(x + 1), lat(y))


def _tile_range(minx, miny, maxx, maxy, z):
    x = lambda lon: int((lon + 180) / 360 * 2 ** z)
    y = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** z)
    return range(x(minx), x(maxx) + 1), range(y(maxy), y(miny) + 1)


def region(ov: dict[str, dict], name: str):
    """The part of the map this municipality's pack covers."""
    names = list(ov)
    shapes = [make_valid(shape(f["geometry"])).simplify(0.0003) for f in ov.values()]
    tree = STRtree(shapes)
    mine = prep(shapes[names.index(name)])
    xs, ys = _tile_range(*shapes[names.index(name)].bounds, TILE_ZOOM)
    tiles = []
    for x in xs:
        for y in ys:
            t = _tile_box(x, y, TILE_ZOOM)
            if not mine.intersects(t):
                continue
            best = max(tree.query(t), key=lambda i: shapes[i].intersection(t).area)
            if names[best] == name:
                tiles.append(t)
    if not tiles:
        raise SystemExit(f"maps: {name} owns no zoom-{TILE_ZOOM} tile")
    return unary_union(tiles), len(tiles)


def build(data: Path, name: str, path: str, out: Path, tmp: Path) -> dict:
    """Write the pack for municipality `name` (its source data under
    data/areas/<path>) to `out`, and return what the index says of it."""
    src = data / "areas" / path
    ov = municipalities(data)
    area = make_valid(shape(ov[name]["geometry"]))
    covered, tile_count = region(ov, name)
    pr = prep(covered)

    def feats(layer):
        p = src / f"{layer}.geojsonl"
        if p.exists():
            for f in read(p):
                yield f["geometry"], f["properties"]

    def clip(g):
        g = shape(g)
        if not pr.intersects(g):
            return None
        if pr.contains(g):
            return g
        g = make_valid(g).intersection(covered)
        return None if g.is_empty else g

    layers = collections.defaultdict(list)

    def add(layer, g, props, minzoom):
        g = clip(g)
        if g is not None:
            props = {k: v for k, v in props.items() if v not in (None, "", "None")}
            layers[layer].append({"type": "Feature", "geometry": mapping(force_2d(g)), "properties": {**props, "mz": minzoom}})

    for g, p in feats("road"):
        k = ROAD.get(int(p["tyyp"]))
        if k:
            named = k[0] in ("street", "primary", "secondary", "tertiary")
            add("road", g, {"class": k[0], "name": p.get("nimetus") if named else None}, k[1])
    for g, p in feats("rail"):
        add("rail", g, {"class": "cable" if int(p["tyyp"]) == 30 else "rail"}, 9)
    for g, p in feats("cutline"):
        add("road", g, {"class": "track"}, 13)

    for g, p in feats("sea"):
        add("water", g, {"class": "sea"}, 8)
    for g, p in feats("lake"):
        m2 = shape(g).area * 3.6e9  # roughly, at 57-59° N
        add("water", g, {"class": "lake", "name": p.get("nimetus")}, 8 if m2 > 5e5 else 10 if m2 > 5e4 else 12)
    for g, p in feats("river_a"):
        add("water", g, {"class": "river", "name": p.get("nimetus")}, 10)
    for g, p in feats("river_l"):
        k = RIVER.get(int(p["tyyp"]), ("ditch", 13))
        add("waterway", g, {"class": k[0], "name": p.get("nimetus")}, k[1])

    for layer, classes in LANDCOVER.items():
        for g, p in feats(layer):
            k = classes[None] if None in classes else classes.get(int(p["tyyp"]))
            if k:
                add("landcover", g, {"class": k[0]}, k[1])

    for g, p in feats("building"):
        t = int(p["tyyp"])
        if t in (30, 60):  # foundations, cellars
            continue
        add("building", g, {"use": "ruin" if t == 40 else building_use(p.get("kaos_kood")), "name": p.get("nimetus")}, 14)

    for g, p in feats("settlement"):
        point = make_valid(shape(g)).representative_point()
        if pr.contains(point):
            label = re.sub(r" (küla|alevik|alev|linn)$", "", p["asustusyksus"])
            layers["place_label"].append({"type": "Feature", "geometry": mapping(point),
                                          "properties": {"name": label, "class": p["tyyp"], "mz": 11 if p["tyyp"] == "küla" else 8}})
    for layer, cls in (("rmk_hike", "hiking"), ("rmk_bike", "cycling"), ("rmk_route", "long_distance")):
        for g, p in feats(layer):
            add("trail", g, {"class": cls, "name": p.get("nimi")}, 11)
    for g, p in feats("rmk_poi"):
        if pr.contains(shape(g)):
            add("poi", g, {"kind": p["tyypnimi"].replace("RMK külastustaristu ", ""), "name": p["nimi"]}, 12)

    neighbours = []
    for other, f in ov.items():
        g = make_valid(shape(f["geometry"]))
        touches = other != name and g.buffer(1e-5).intersects(area)
        if touches:
            neighbours.append(other)
        if other == name or touches:
            add("boundary", mapping(g.boundary), {"name": other, "self": other == name}, 8)

    if not layers:
        raise SystemExit(f"maps: no features for {name} in {src}")
    tmp.mkdir(parents=True, exist_ok=True)
    args = []
    for layer, features in layers.items():
        fn = tmp / f"{layer}.geojson"
        fn.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
        args += ["-L", f"{layer}:{fn}"]
    # Each feature's first zoom, through the "mz" attribute: tippecanoe
    # 2.49's per-feature "tippecanoe" key keeps one feature per tile.
    zoom_filter = ["any"] + [["all", ["==", "mz", z], [">=", "$zoom", z]] for z in range(8, 16)]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tippecanoe", "-q", "-f", "-o", str(out), "-Z8", "-z15",
                    "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--detect-shared-borders",
                    "-n", name, "-A", ATTRIBUTION, "-j", json.dumps({"*": zoom_filter}), *args], check=True)
    return {
        "name": name,
        "ehak": ov[name]["properties"].get("ehak_kood"),
        "bbox": [round(v, 5) for v in covered.bounds],
        "neighbours": sorted(neighbours),
        "tiles": tile_count,
    }
