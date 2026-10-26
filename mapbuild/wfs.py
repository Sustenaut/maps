"""Read layers from the Estonian state GeoServer WFS into GeoJSONSeq files.

All the sources (Maa- ja Ruumiamet's ETAK topography and EHAK boundaries,
the ETAK buildings joined with the Building Register's use codes, and
RMK's trails and visitor sites) are on one WFS. It returns at most 5000
features a page, and with a CQL filter its numberMatched is capped at
5000 too, so a layer is paged until a page comes back short.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = os.environ.get("MAPS_WFS", "https://gsavalik.envir.ee/geoserver/wfs")
# The server's page size; MAPS_WFS_PAGE is for tests against a small fake.
PAGE = int(os.environ.get("MAPS_WFS_PAGE", "5000"))


def page(layer: str, start: int, *, bbox: list[int] | None = None, cql: str | None = None) -> dict:
    q = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer,
        "outputFormat": "application/json", "srsName": "EPSG:4326", "count": PAGE,
        "startIndex": start, "sortBy": "fid",
    }
    if cql:
        q["CQL_FILTER"] = cql
    elif bbox:
        q["bbox"] = ",".join(map(str, bbox)) + ",EPSG:3301"
    url = URL + "?" + urllib.parse.urlencode(q)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=300) as response:
                return json.load(response)
        except (OSError, ValueError) as err:
            print(f"maps: {layer} at {start}: {err}, retrying", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise SystemExit(f"maps: could not read {url}")


def fetch(layer: str, out: Path, *, bbox: list[int] | None = None, cql: str | None = None) -> int:
    """Write every feature of `layer` (within `bbox`, in EPSG:3301, or
    matching `cql`) to `out`, one per line. A finished file is kept, so
    an interrupted download picks up where it stopped."""
    done = out.with_name(out.name + ".done")
    if done.exists():
        return int(done.read_text())
    out.parent.mkdir(parents=True, exist_ok=True)
    count, start = 0, 0
    with open(out, "w", encoding="utf-8") as f:
        while True:
            features = page(layer, start, bbox=bbox, cql=cql)["features"]
            for feature in features:
                f.write(json.dumps(feature, ensure_ascii=False) + "\n")
            count += len(features)
            start += PAGE
            if len(features) < PAGE:
                break
    done.write_text(str(count))
    print(f"maps: {layer}: {count}", file=sys.stderr)
    return count
