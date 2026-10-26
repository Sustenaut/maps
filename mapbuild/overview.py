"""Build the national overview: all of Estonia at zoom 5 to 10, with the
same layer names as the area packs, plus municipality borders and labels
(area_label) so a map can show which area to open."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from shapely import force_2d, make_valid
from shapely.geometry import mapping, shape

from .area import ATTRIBUTION
from .sources import municipalities, read

ROAD = {10: ("primary", 5), 20: ("secondary", 7), 30: ("tertiary", 9)}


def build(data: Path, out: Path, tmp: Path) -> None:
    src = data / "national"
    layers: dict[str, list] = {}

    def add(layer, g, props, minzoom):
        props = {k: v for k, v in props.items() if v not in (None, "", "None")}
        layers.setdefault(layer, []).append({"type": "Feature", "geometry": mapping(force_2d(g)), "properties": {**props, "mz": minzoom}})

    def feats(name):
        for f in read(src / f"{name}.geojsonl"):
            yield shape(f["geometry"]), f["properties"]

    for g, p in feats("sea"):
        add("water", g, {"class": "sea"}, 5)
    for g, p in feats("lake"):
        m2 = g.area * 3.6e9
        add("water", g, {"class": "lake", "name": p.get("nimetus") if m2 > 1e6 else None}, 5 if m2 > 5e6 else 7 if m2 > 5e5 else 9)
    for g, p in feats("river"):
        add("waterway", g, {"class": "river", "name": p.get("nimetus")}, 8)
    for g, p in feats("road"):
        cls, minzoom = ROAD[int(p["tyyp"])]
        add("road", g, {"class": cls}, minzoom)
    for g, p in feats("rail"):
        add("rail", g, {"class": "rail"}, 7)
    for g, p in feats("wood"):
        add("landcover", g, {"class": "forest"}, 8)
    for g, p in feats("wetland"):
        add("landcover", g, {"class": "bog" if int(p["tyyp"]) == 20 else "fen"}, 8)
    for g, p in feats("county"):
        add("boundary", make_valid(g).boundary, {"level": "county", "name": p["maakond"]}, 5)

    # Towns, and the cities that are municipalities of their own (Tartu
    # linn, Võru linn), which the settlement layer does not always list.
    labelled = set()
    for g, p in feats("town"):
        name = re.sub(r" (alevik|alev|linn)$", "", p["asustusyksus"])
        labelled.add(name)
        add("place_label", make_valid(g).representative_point(), {"name": name, "class": p["tyyp"]}, 5 if "linn" in p["tyyp"] else 8)
    for name, f in municipalities(data).items():
        g = make_valid(shape(f["geometry"]))
        add("boundary", g.boundary, {"level": "municipality", "name": name}, 7)
        add("area_label", g.representative_point(), {"name": name, "ehak": f["properties"].get("ehak_kood")}, 8)
        city = re.sub(r" linn$", "", name)
        if name.endswith(" linn") and city not in labelled:
            add("place_label", g.representative_point(), {"name": city, "class": "linn"}, 5)

    tmp.mkdir(parents=True, exist_ok=True)
    args = []
    for layer, features in layers.items():
        fn = tmp / f"{layer}.geojson"
        fn.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
        args += ["-L", f"{layer}:{fn}"]
    zoom_filter = ["any"] + [["all", ["==", "mz", z], [">=", "$zoom", z]] for z in range(5, 11)]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tippecanoe", "-q", "-f", "-o", str(out), "-Z5", "-z10",
                    "--drop-smallest-as-needed", "--coalesce-densest-as-needed", "--simplification=4",
                    "-n", "Eesti", "-A", ATTRIBUTION, "-j", json.dumps({"*": zoom_filter}), *args], check=True)
