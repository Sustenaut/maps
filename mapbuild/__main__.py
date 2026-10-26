"""maps: download Estonia's map data and build maps.sustenaut.eu.

    maps download [--data DIR] [--areas FILE] [--centres FILE]
    maps build [--data DIR] [--out DIR] [--areas FILE] [--centres FILE]

download reads the municipality boundaries, the national overview's
layers and each area's layers from the state WFS into --data (data/ by
default); a finished layer is kept, so a second run only fetches what is
missing. build turns them into the site in --out (_site/ by default):
the packs, index.json, the map package and the Pages headers. --areas is
the list of areas to build (areas.json by default). --centres names the
settlement each municipality is run from (centres.json by default), for
municipalities.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import publish, sources

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maps", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "build"):
        p = sub.add_parser(name)
        p.add_argument("--data", type=Path, default=Path("data"))
        p.add_argument("--areas", type=Path, default=ROOT / "areas.json")
        p.add_argument("--centres", type=Path, default=ROOT / "centres.json")
        if name == "build":
            p.add_argument("--out", type=Path, default=Path("_site"))
            p.add_argument("--node-modules", type=Path, default=ROOT / "node_modules")
    args = parser.parse_args(argv)

    areas = json.loads(args.areas.read_text(encoding="utf-8"))["areas"]
    if args.command == "download":
        sources.boundaries(args.data)
        sources.national(args.data, args.centres)
        for entry in areas:
            sources.area(args.data, entry["name"], entry["path"])
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        index = publish.build(args.data, args.out, args.areas, args.node_modules, Path(tmp), args.centres)
    print(f"maps: built {args.out}: the overview and {len(index['areas'])} area pack(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
