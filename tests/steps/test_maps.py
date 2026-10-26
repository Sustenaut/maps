"""Steps for `maps download` and `maps build`, on small made-up data around
two neighbouring municipalities, Alfa vald and Beeta vald."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("build.feature", "download.feature")

# Each area layer and overview layer `maps download` writes.
AREA_LAYERS = ["road", "rail", "cutline", "sea", "lake", "river_a", "river_l", "wood", "wetland", "field",
               "open", "yard", "peat", "other_lc", "building", "settlement", "rmk_hike", "rmk_bike",
               "rmk_route", "rmk_poi"]
NATIONAL_LAYERS = ["sea", "lake", "road", "rail", "river", "county", "town", "wood", "wetland"]

# Alfa vald and Beeta vald share the meridian 26.9.
ALFA = (26.80, 57.70, 26.90, 57.75)
BEETA = (26.90, 57.70, 27.00, 57.75)


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def line(*points):
    return {"type": "LineString", "coordinates": [list(p) for p in points]}


def feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def municipalities():
    return [feature(rect(*ALFA), omavalitsus="Alfa vald", ehak_kood="0001"),
            feature(rect(*BEETA), omavalitsus="Beeta vald", ehak_kood="0002")]


def area_layers(w, s, e, n, name):
    """A little of everything a pack shows, inside the box."""
    cx, cy = (w + e) / 2, (s + n) / 2
    return {
        "road": [feature(line((w, cy), (e, cy)), tyyp=10, nimetus="Tee 1"),
                 feature(line((cx, s), (cx, n)), tyyp=60)],
        "lake": [feature(rect(cx + 0.01, cy + 0.01, cx + 0.02, cy + 0.015), nimetus=f"{name} järv")],
        "river_l": [feature(line((w, s + 0.005), (e, s + 0.01)), tyyp=30, nimetus=f"{name} oja")],
        "wood": [feature(rect(w, s, cx, cy), tyyp=10)],
        "building": [feature(rect(cx + 0.001, cy + 0.001, cx + 0.0015, cy + 0.0013), tyyp=10, kaos_kood="12111"),
                     feature(rect(cx - 0.002, cy + 0.001, cx - 0.0015, cy + 0.0013), tyyp=10, kaos_kood="11100")],
        "settlement": [feature(rect(cx - 0.01, cy - 0.01, cx + 0.01, cy + 0.01), asustusyksus=f"{name} küla", tyyp="küla")],
        "rmk_hike": [feature(line((w + 0.01, s + 0.01), (cx, n - 0.01)), nimi=f"{name} matkarada")],
        "rmk_poi": [feature({"type": "Point", "coordinates": [cx + 0.005, cy - 0.005]},
                            tyypnimi="RMK külastustaristu lõkkekoht", nimi=f"{name} lõkkekoht")],
    }


def national_layers():
    return {
        "sea": [feature(rect(26.0, 57.6, 26.3, 57.8))],
        "lake": [feature(rect(26.85, 57.72, 26.95, 57.74), nimetus="Suurjärv")],
        "road": [feature(line((26.5, 57.72), (27.2, 57.72)), tyyp=10)],
        "rail": [feature(line((26.5, 57.71), (27.2, 57.71)), tyyp=10)],
        "river": [feature(line((26.5, 57.705), (27.2, 57.705)), tyyp=10, nimetus="Jõgi")],
        "county": [feature(rect(26.5, 57.5, 27.5, 58.0), maakond="Näidis maakond")],
        "town": [feature(rect(26.94, 57.73, 26.96, 57.74), asustusyksus="Beeta alevik", tyyp="alevik")],
        "wood": [feature(rect(26.8, 57.7, 26.85, 57.72), tyyp=10)],
        "wetland": [feature(rect(26.95, 57.7, 27.0, 57.72), tyyp=20)],
    }


def write(path: Path, features) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in features), encoding="utf-8")


def joined(site: Path, pack: dict) -> bytes:
    """A pack's pieces, joined in order."""
    count = -(-pack["size"] // pack["chunk"])
    pieces = [site / pack["dir"] / f"{n}.bin" for n in range(count)]
    assert sorted(p.name for p in (site / pack["dir"]).iterdir()) == sorted(p.name for p in pieces)
    return b"".join(p.read_bytes() for p in pieces)


def pmtiles(site: Path, pack: dict) -> dict:
    """A PMTiles v3 pack's zoom range and metadata."""
    data = joined(site, pack)
    assert data[:7] == b"PMTiles" and data[7] == 3, pack["dir"]
    meta_offset, meta_length = struct.unpack_from("<QQ", data, 24)
    meta = data[meta_offset:meta_offset + meta_length]
    if data[97] == 2:
        meta = gzip.decompress(meta)
    return {"minzoom": data[100], "maxzoom": data[101], "metadata": json.loads(meta)}


# Building

@given("sample data for two neighbouring municipalities", target_fixture="data")
def sample_data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    write(data / "boundaries.geojsonl", municipalities())
    for path, box, name in (("louna/alfa", ALFA, "Alfa"), ("louna/beeta", BEETA, "Beeta")):
        for layer, features in area_layers(*box, name).items():
            write(data / "areas" / path / f"{layer}.geojsonl", features)
    for layer, features in national_layers().items():
        write(data / "national" / f"{layer}.geojsonl", features)
    return data


@pytest.fixture
def env() -> dict:
    return {}


@given(parsers.parse("pieces of {size:d} bytes"))
def pieces_of(env: dict, size: int) -> None:
    env["MAPS_CHUNK"] = str(size)


@when(parsers.parse('I build the areas "{a}" at "{a_path}" and "{b}" at "{b_path}"'), target_fixture="result")
def build(run, binary, tmp_path: Path, data: Path, env: dict, a, a_path, b, b_path):
    areas = tmp_path / "areas.json"
    areas.write_text(json.dumps({"areas": [{"name": a, "path": a_path}, {"name": b, "path": b_path}]}))
    return run(binary("maps"), "build", "--data", data, "--areas", areas, "--out", tmp_path / "_site",
               env=env, timeout=600)


@pytest.fixture
def site(tmp_path: Path) -> Path:
    return tmp_path / "_site"


def index(site: Path) -> dict:
    return json.loads((site / "index.json").read_text(encoding="utf-8"))


def area(site: Path, path: str) -> dict:
    return next(a for a in index(site)["areas"] if a["path"] == path)


@then(parsers.parse('index.json lists the areas "{paths}"'))
def lists_areas(site: Path, paths: str) -> None:
    assert [a["path"] for a in index(site)["areas"]] == paths.split(", ")


def packs(site: Path) -> list[dict]:
    i = index(site)
    return [i["overview"]] + [a["pack"] for a in i["areas"]]


def matches(pattern: str, value: str) -> bool:
    return re.fullmatch(re.escape(pattern).replace(re.escape("<hash>"), "[0-9a-f]{12}"), value) is not None


@then(parsers.parse('the pack of "{path}" is in "{pattern}"'))
def pack_in(site: Path, path: str, pattern: str) -> None:
    assert matches(pattern, area(site, path)["pack"]["dir"]), area(site, path)["pack"]


@then(parsers.parse('the overview is in "{pattern}"'))
def overview_in(site: Path, pattern: str) -> None:
    assert matches(pattern, index(site)["overview"]["dir"]), index(site)["overview"]


@then("every pack's pieces join into a PMTiles archive named by its content")
def pieces_join(site: Path) -> None:
    for pack in packs(site):
        data = joined(site, pack)
        assert len(data) == pack["size"] and data[:7] == b"PMTiles", pack
        assert pack["dir"].rsplit("/", 1)[1] == hashlib.sha256(data).hexdigest()[:12], pack


@then(parsers.parse('the pack of "{path}" is in more than one piece of {size:d} bytes'))
def several_pieces(site: Path, path: str, size: int) -> None:
    pack = area(site, path)["pack"]
    files = sorted((site / pack["dir"]).iterdir(), key=lambda p: int(p.stem))
    assert pack["chunk"] == size and len(files) > 1, pack
    assert all(f.stat().st_size == size for f in files[:-1]) and 0 < files[-1].stat().st_size <= size


@then(parsers.parse('the area "{path}" has the neighbours "{names}"'))
def has_neighbours(site: Path, path: str, names: str) -> None:
    assert area(site, path)["neighbours"] == names.split(", ")


@then(parsers.parse('the area "{path}" lies within its municipality\'s tiles'))
def within_tiles(site: Path, path: str) -> None:
    # The pack covers the zoom-13 tiles it owns: about its municipality,
    # never more than a tile (0.044° of longitude) beyond it.
    w, s, e, n = area(site, path)["bbox"]
    assert ALFA[0] - 0.044 <= w <= ALFA[0] + 0.044 and ALFA[2] - 0.044 <= e <= ALFA[2] + 0.044, (w, e)
    assert ALFA[1] - 0.03 <= s and n <= ALFA[3] + 0.03, (s, n)
    assert area(site, path)["tiles"] > 0


@then(parsers.parse('index.json\'s attribution names "{names}"'))
def attribution_names(site: Path, names: str) -> None:
    text = index(site)["attribution"]
    missing = [n for n in names.split(", ") if n not in text]
    assert not missing, (missing, text)


@then("every pack carries the same attribution as index.json")
def packs_attributed(site: Path) -> None:
    i = index(site)
    for pack in packs(site):
        assert pmtiles(site, pack)["metadata"]["attribution"] == i["attribution"], pack["dir"]


def layers(site: Path, pack: dict) -> set[str]:
    return {layer["id"] for layer in pmtiles(site, pack)["metadata"]["vector_layers"]}


@then(parsers.parse('the pack of "{path}" has the layers "{names}"'))
def pack_layers(site: Path, path: str, names: str) -> None:
    missing = set(names.split(", ")) - layers(site, area(site, path)["pack"])
    assert not missing, missing


@then(parsers.parse('the pack of "{path}" spans zoom {low:d} to {high:d}'))
def pack_zooms(site: Path, path: str, low: int, high: int) -> None:
    p = pmtiles(site, area(site, path)["pack"])
    assert (p["minzoom"], p["maxzoom"]) == (low, high)


@then(parsers.parse('the overview has the layers "{names}"'))
def overview_layers(site: Path, names: str) -> None:
    missing = set(names.split(", ")) - layers(site, index(site)["overview"])
    assert not missing, missing


def headers(site: Path) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    current = None
    for raw in (site / "_headers").read_text().splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        if raw[0].isspace():
            rules[current].append(raw.strip())
        else:
            current = raw.strip()
            rules[current] = []
    return rules


@then("_headers lets any site read the maps")
def cors(site: Path) -> None:
    assert "Access-Control-Allow-Origin: *" in headers(site)["/*"]


@then("_headers caches packs for good and index.json for 5 minutes")
def caching(site: Path) -> None:
    h = headers(site)
    assert "Cache-Control: public, max-age=31536000, immutable" in h["/packs/*"]
    assert "Cache-Control: public, max-age=300" in h["/index.json"]


@then(parsers.parse('the site has "{files}"'))
def site_has(site: Path, files: str) -> None:
    missing = [f for f in files.split(", ") if not (site / f).is_file()]
    assert not missing, missing


# Downloading

class WFS:
    """A fake of the state WFS: the boundaries, five roads, and nothing
    else, served in pages of the size the client asks for."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.layers = {
            "ehak:omavalitsuste_piirid": municipalities(),
            "etak:e_501_tee_j": [feature(line((26.81 + i * 0.01, 57.71), (26.81 + i * 0.01, 57.74)), tyyp=60)
                                 for i in range(5)],
        }
        wfs = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                wfs.requests.append(q)
                start, count = int(q["startIndex"]), int(q["count"])
                features = wfs.layers.get(q["typeNames"], [])[start:start + count]
                body = json.dumps({"type": "FeatureCollection", "features": features}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/wfs"


@given("a WFS with two neighbouring municipalities", target_fixture="wfs")
def a_wfs(env: dict):
    wfs = WFS()
    env.update({"MAPS_WFS": wfs.url, "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
    yield wfs
    wfs.server.shutdown()


@given(parsers.parse("the WFS returns {count:d} features a page"))
def page_size(env: dict, count: int) -> None:
    env["MAPS_WFS_PAGE"] = str(count)


def download(run, binary, tmp_path: Path, env: dict, name: str, path: str):
    areas = tmp_path / "areas.json"
    areas.write_text(json.dumps({"areas": [{"name": name, "path": path}]}))
    return run(binary("maps"), "download", "--data", tmp_path / "data", "--areas", areas, env=env)


@when(parsers.parse('I download the area "{name}" at "{path}"'), target_fixture="result")
def i_download(run, binary, tmp_path: Path, env: dict, name: str, path: str):
    return download(run, binary, tmp_path, env, name, path)


@when(parsers.parse('I download the area "{name}" at "{path}" again'), target_fixture="result")
def i_download_again(run, binary, tmp_path: Path, env: dict, wfs: WFS, name: str, path: str):
    wfs.before_second = len(wfs.requests)
    return download(run, binary, tmp_path, env, name, path)


@then("the data has every municipality's boundary")
def has_boundaries(tmp_path: Path) -> None:
    lines = (tmp_path / "data" / "boundaries.geojsonl").read_text(encoding="utf-8").splitlines()
    assert sorted(json.loads(x)["properties"]["omavalitsus"] for x in lines) == ["Alfa vald", "Beeta vald"]


@then(parsers.parse('the data has every layer of the area "{path}" and of the overview'))
def has_layers(tmp_path: Path, path: str) -> None:
    data = tmp_path / "data"
    files = [data / "areas" / path / f"{name}.geojsonl" for name in AREA_LAYERS]
    files += [data / "national" / f"{name}.geojsonl" for name in NATIONAL_LAYERS]
    missing = [str(f.relative_to(data)) for f in files if not f.is_file()]
    assert not missing, missing


@then(parsers.parse('the area "{path}"\'s roads have all {count:d} features, read in {pages:d} pages'))
def roads_paged(tmp_path: Path, wfs: WFS, path: str, count: int, pages: int) -> None:
    roads = (tmp_path / "data" / "areas" / path / "road.geojsonl").read_text(encoding="utf-8").splitlines()
    assert len(roads) == count
    # The area's own requests have a bbox; the overview's have a CQL filter.
    asked = [q for q in wfs.requests if q["typeNames"] == "etak:e_501_tee_j" and "bbox" in q]
    assert len(asked) == pages, asked


@then("the second download made no requests")
def no_requests(wfs: WFS) -> None:
    assert len(wfs.requests) == wfs.before_second, wfs.requests[wfs.before_second:]
