"""An area's road network, for working out walking and driving distances.

ETAK's roads (etak:e_501_tee_j) meet at the ends of their segments, so
the ends are the network's nodes and each segment is an edge, as long as
its line. A site measures the way from itself to its places through the
networks of the areas around it (visit.ee's `make distances`).

    {"version": 1,
     "nodes": [lng, lat, lng, lat, ...],     in millionths of a degree
     "edges": [a, b, metres, modes, ...]}    a and b index nodes

An edge's modes are bits: FOOT (1), CAR from a to b (2), CAR from b to a
(4), and above them (modes >> 3) ETAK's road type over ten (1 a main road,
2 a secondary one, 3 a local one, 4 a ramp, 5 a street, 6 any other road, 7 a
path, 8 a cycle and foot path), so a car's way can prefer the faster
roads. Neighbouring areas' data overlap by 1 km and hold the same
segments with the same coordinates, so their networks join where their
nodes do.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .sources import read

FOOT, CAR_AB, CAR_BA = 1, 2, 4

# ETAK's road types (tyyp): who may use each.
MAIN, SECONDARY, LOCAL, RAMP, STREET, OTHER, PATH, CYCLE_FOOT = 10, 20, 30, 40, 50, 60, 70, 80
CAR_TYPES = {MAIN, SECONDARY, LOCAL, RAMP, STREET, OTHER}
FOOT_TYPES = {MAIN, SECONDARY, LOCAL, STREET, OTHER, PATH, CYCLE_FOOT}
# ETAK's traffic direction (liiklus): both ways, along the line, against it.
BOTH, ALONG, AGAINST = 10, 20, 30

R = 6371008.8


def metres(line: list[list[float]]) -> float:
    total = 0.0
    for (x1, y1, *_), (x2, y2, *_) in zip(line, line[1:]):
        p1, p2 = math.radians(y1), math.radians(y2)
        h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(x2 - x1) / 2) ** 2
        total += 2 * R * math.asin(math.sqrt(h))
    return total


def modes(props: dict) -> int:
    kind = props.get("tyyp")
    bits = FOOT if kind in FOOT_TYPES else 0
    if kind in CAR_TYPES:
        way = props.get("liiklus")
        bits |= {ALONG: CAR_AB, AGAINST: CAR_BA}.get(way, CAR_AB | CAR_BA)
    if bits:
        bits |= (kind // 10) << 3
    return bits


def network(roads: Path) -> dict:
    nodes: dict[tuple[int, int], int] = {}
    flat_nodes: list[int] = []
    edges: list[int] = []

    def node(point: list[float]) -> int:
        key = (round(point[0] * 1e6), round(point[1] * 1e6))
        if key not in nodes:
            nodes[key] = len(nodes)
            flat_nodes.extend(key)
        return nodes[key]

    for feature in read(roads):
        bits = modes(feature.get("properties") or {})
        geometry = feature["geometry"]
        lines = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
        for line in lines:
            if not bits or len(line) < 2:
                continue
            a, b = node(line[0]), node(line[-1])
            if a != b:
                edges.extend((a, b, max(1, round(metres(line))), bits))
    return {"version": 1, "nodes": flat_nodes, "edges": edges}


def write(roads: Path, out: Path, path: str) -> dict:
    """Write an area's network to out/routes/<path>/<hash>.json, named by
    its content so it can be cached for good, and say where it is."""
    text = json.dumps(network(roads), separators=(",", ":"))
    data = text.encode("utf-8")
    file = Path("routes") / path / f"{hashlib.sha256(data).hexdigest()[:12]}.json"
    (out / file).parent.mkdir(parents=True, exist_ok=True)
    (out / file).write_bytes(data)
    return {"file": file.as_posix(), "size": len(data)}
