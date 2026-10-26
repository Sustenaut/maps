"""municipalities.json: every municipality, for maps that name them all.

    {"version": 1, "municipalities": [
      {"name": "Rõuge vald", "ehak": "0698", "county": "Võru maakond",
       "label": [lng, lat], "bbox": [w, s, e, n],
       "centre": {"name": "Rõuge", "lng": ..., "lat": ...}}, ...]}

label is a point inside the municipality to write its name at. centre is
the settlement it is run from (centres.json), named without its type
("Rõuge alevik" is "Rõuge"); a city district stands for its city
("Kesklinna linnaosa" is "Tallinn"). A municipality whose seat is not
found has no centre, and the build says which.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from shapely import make_valid
from shapely.geometry import shape

from .sources import municipalities, read

SUFFIX = re.compile(r" (linn|alev|alevik|küla)$")


def build(data: Path, centres_file: Path) -> dict:
    seats = json.loads(centres_file.read_text(encoding="utf-8"))["centres"] if centres_file.exists() else {}
    boundaries = {name: make_valid(shape(f["geometry"])) for name, f in municipalities(data).items()}
    settlements: dict[str, list] = {}
    centre_file = data / "national" / "centre.geojsonl"
    if centre_file.exists():
        for f in read(centre_file):
            p = f["properties"]
            settlements.setdefault(p["asustusyksus"], []).append((p.get("omavalitsus"), make_valid(shape(f["geometry"]))))

    def centre(name: str) -> dict | None:
        seat = seats.get(name)
        if not seat:
            return None
        found = settlements.get(seat, [])
        # A village name can repeat across Estonia: take the one in this
        # municipality, else the only one there is.
        here = [g for owner, g in found if owner == name] or ([found[0][1]] if len(found) == 1 else [])
        if here:
            label = name if seat.endswith(" linnaosa") else SUFFIX.sub("", seat)
            point = here[0].representative_point()
        elif seat in boundaries:
            label, point = SUFFIX.sub("", seat), boundaries[seat].representative_point()
        else:
            return None
        return {"name": label, "lng": round(point.x, 5), "lat": round(point.y, 5)}

    listed, missing = [], []
    for name, f in sorted(municipalities(data).items()):
        g = boundaries[name]
        p = f["properties"]
        point = g.representative_point()
        entry = {
            "name": name,
            "ehak": p.get("ehak_kood"),
            "county": p.get("maakond"),
            "label": [round(point.x, 5), round(point.y, 5)],
            "bbox": [round(v, 5) for v in g.bounds],
            "centre": centre(name),
        }
        if entry["centre"] is None and seats.get(name):
            missing.append(f"{name} ({seats[name]})")
        listed.append(entry)
    if missing:
        print(f"maps: no centre found for {', '.join(missing)}", file=sys.stderr)
    return {"version": 1, "municipalities": listed}
