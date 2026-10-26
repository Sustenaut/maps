"""Download the source data: the municipality boundaries, each area's
layers (its bounding box plus 1 km), and the national overview's layers.

    data/boundaries.geojsonl          every municipality (EHAK)
    data/areas/<path>/<layer>.geojsonl
    data/national/<layer>.geojsonl
"""

from __future__ import annotations

import concurrent.futures as cf
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import transform
from shapely.geometry import shape

from . import wfs

BOUNDARIES = "ehak:omavalitsuste_piirid"

# Each area's layers, by the name the pack build reads them under.
AREA_LAYERS = {
    "road": "etak:e_501_tee_j",
    "rail": "etak:e_502_roobastee_j",
    "cutline": "etak:e_503_siht_j",
    "sea": "etak:e_201_meri_a",
    "lake": "etak:e_202_seisuveekogu_a",
    "river_a": "etak:e_203_vooluveekogu_a",
    "river_l": "etak:e_203_vooluveekogu_j",
    "wood": "etak:e_305_puittaimestik_a",
    "wetland": "etak:e_306_margala_a",
    "field": "etak:e_303_haritav_maa_a",
    "open": "etak:e_304_lage_a",
    "yard": "etak:e_302_ou_a",
    "peat": "etak:e_307_turbavali_a",
    "other_lc": "etak:e_301_muu_kolvik_a",
    "building": "etak_tuletis:etak_ehr_hooned",
    "settlement": "ehak:asustusyksuste_piirid",
    "rmk_hike": "huvipunkt:rmk_matkarada_j",
    "rmk_bike": "huvipunkt:rmk_rattarada_j",
    "rmk_route": "huvipunkt:rmk_matkatee_j",
    "rmk_poi": "huvipunkt:rmk_kylastustaristu",
}

# The overview's layers, all of Estonia, filtered to what shows at zoom 5-10.
NATIONAL_LAYERS = {
    "sea": ("etak:e_201_meri_a", "INCLUDE"),
    "lake": ("etak:e_202_seisuveekogu_a", "tyyp=10"),
    "road": ("etak:e_501_tee_j", "tyyp IN (10,20,30)"),
    "rail": ("etak:e_502_roobastee_j", "tyyp=10"),
    "river": ("etak:e_203_vooluveekogu_j", "tyyp=10"),
    "county": ("ehak:maakondade_piirid", "INCLUDE"),
    "town": ("ehak:asustusyksuste_piirid", "tyyp<>'küla'"),
    "wood": ("etak:e_305_puittaimestik_a", "tyyp=10"),
    "wetland": ("etak:e_306_margala_a", "tyyp IN (10,20)"),
}


def read(path: Path):
    """Each feature of a GeoJSONSeq file that has a geometry."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            feature = json.loads(line)
            if feature.get("geometry"):
                yield feature


def municipalities(data: Path) -> dict[str, dict]:
    return {f["properties"]["omavalitsus"]: f for f in read(data / "boundaries.geojsonl")}


def boundaries(data: Path) -> None:
    wfs.fetch(BOUNDARIES, data / "boundaries.geojsonl", cql="INCLUDE")


def area(data: Path, name: str, path: str) -> None:
    ov = municipalities(data)
    if name not in ov:
        raise SystemExit(f"maps: there is no municipality {name!r} in {BOUNDARIES}")
    to3301 = Transformer.from_crs(4326, 3301, always_xy=True)
    g = transform(shape(ov[name]["geometry"]), lambda c: np.column_stack(to3301.transform(c[:, 0], c[:, 1])))
    bbox = [round(v) for v in g.buffer(1000).bounds]
    out = data / "areas" / path
    with cf.ThreadPoolExecutor(5) as pool:
        list(pool.map(lambda kv: wfs.fetch(kv[1], out / f"{kv[0]}.geojsonl", bbox=bbox), AREA_LAYERS.items()))


def national(data: Path, centres: Path) -> None:
    out = data / "national"
    layers = dict(NATIONAL_LAYERS)
    # The settlements municipalities are run from (centres.json), villages
    # among them, which the town layer leaves out.
    seats = sorted({s for s in json.loads(centres.read_text(encoding="utf-8"))["centres"].values() if s})
    quoted = ",".join("'" + s.replace("'", "''") + "'" for s in seats)
    layers["centre"] = ("ehak:asustusyksuste_piirid", f"asustusyksus IN ({quoted})" if seats else "EXCLUDE")
    with cf.ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda kv: wfs.fetch(kv[1][0], out / f"{kv[0]}.geojsonl", cql=kv[1][1]), layers.items()))
