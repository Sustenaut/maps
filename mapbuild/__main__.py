"""maps: download Estonia's map data and build maps.sustenaut.eu.

    maps download [--data DIR] [--areas FILE] [--centres FILE]
    maps build [--data DIR] [--out DIR] [--areas FILE] [--centres FILE] [--cache]
    maps build-area NAME PATH --data DIR --pack FILE --meta FILE
    maps build-overview --data DIR --pack FILE

download reads the municipality boundaries, the national overview's
layers and each area's layers from the state WFS into --data (data/ by
default); a finished layer is kept, so a second run only fetches what is
missing. --areas (areas.json by default) says which areas: the ones it
lists, and each municipality a site's place is in (mapbuild/places.py).
download writes them, with their places, to DIR/areas.json, and fetches
an area's layers again when its places change. build turns them into the
site in --out (_site/ by default): the packs, index.json, the map package
and the Pages headers, for the areas in --areas (DIR/areas.json, as
download left it, by default). --centres names the settlement each
municipality is run from (centres.json by default), for
municipalities.json. --cache makes each pack through `pubkit cache run`,
by the entries of pubkit.json's cache block, so a pack whose inputs have
not changed is copied instead of made again (mapbuild/publish.py).
build-area and build-overview make one pack each, as pubkit cache run
calls them.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import places, publish, sources

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maps", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "build"):
        p = sub.add_parser(name)
        p.add_argument("--data", type=Path, default=Path("data"))
        p.add_argument("--areas", type=Path, default=None)
        p.add_argument("--centres", type=Path, default=ROOT / "centres.json")
        if name == "build":
            p.add_argument("--out", type=Path, default=Path("_site"))
            p.add_argument("--node-modules", type=Path, default=ROOT / "node_modules")
            p.add_argument("--cache", action="store_true",
                           help="make packs through pubkit cache run, by pubkit.json's cache entries")
            p.add_argument("--cache-root", type=Path, default=ROOT,
                           help="where pubkit.json's cache entries are (the repository, unless testing)")
    # One pack at a time, as pubkit cache run calls them.
    p = sub.add_parser("build-area", help="make one area's pack and what the index says of it")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--pack", type=Path, required=True)
    p.add_argument("--meta", type=Path, required=True)
    p = sub.add_parser("build-overview", help="make the national overview's pack")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--pack", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in ("build-area", "build-overview"):
        from . import area, overview
        args.pack.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            if args.command == "build-overview":
                overview.build(args.data, args.pack, Path(tmp))
                return 0
            meta = area.build(args.data, args.name, args.path, args.pack, Path(tmp))
        args.meta.write_text(json.dumps(meta), encoding="utf-8")
        return 0

    if args.command == "download":
        sources.boundaries(args.data)
        areas = places.plan(args.data, args.areas or ROOT / "areas.json")
        places.write_plan(args.data, areas)
        sources.national(args.data, args.centres)
        for entry in areas:
            if places.keep(args.data, entry):
                print(f"maps: the places in {entry['path']} changed, so its data is fetched again", file=sys.stderr)
            sources.area(args.data, entry["name"], entry["path"])
        return 0

    if args.areas is None:
        planned = args.data / places.PLAN
        args.areas = planned if planned.is_file() else ROOT / "areas.json"

    with tempfile.TemporaryDirectory() as tmp:
        index = publish.build(args.data, args.out, args.areas, args.node_modules, Path(tmp), args.centres,
                              cache=args.cache_root if args.cache else None)
    print(f"maps: built {args.out}: the overview and {len(index['areas'])} area pack(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
