// maps.sustenaut.eu map package, version 1: a MapLibre map of Estonia from
// our own tiles, for any site.
//
//   import { createMap } from "https://maps.sustenaut.eu/lib/v1/map.js";
//   const { map, maplibre } = await createMap(element, {
//     center: { lat: 57.729, lng: 26.929 },
//     radiusKm: 50,                 // which area packs to load
//     locale: { ... },              // MapLibre's own labels, translated
//     detailNote: "…",              // why it zooms no closer, translated
//   });
//
// It loads MapLibre and PMTiles from this site, reads index.json for the
// overview and the area packs that reach within radiusKm of the centre, and
// returns once the style has loaded. Where no area pack covers the view,
// the overview is all there is, so the map zooms no closer than the
// overview's own detail: the zoom-in button turns off and detailNote shows
// on the map. Any other option goes to MapLibre's Map. Layers carry metadata.group (roads, trails, buildings, borders) for
// layer switches, and metadata.mode (road, trail) for setEmphasis().
//
// addMunicipalities(map, { links }) names every municipality and marks
// the settlement each is run from.
//
// Version 1 only grows: a change that would break a site goes to /lib/v2/.

const BASE = new URL("../../", import.meta.url);
const HERE = new URL("./", import.meta.url);
const FONT = "noto-sans-regular";
// The overview's tiles stop at zoom 10; past that, only area packs draw.
const OVERVIEW_ZOOM = 10;
const DETAIL_NOTE = "There is no detailed map of this area yet, so the map zooms no closer here.";

export const COLORS = {
  land: "#F2EEDC",
  forest: "#DCE3C3",
  wet: "#E2E8D9",
  field: "#F1EBCC",
  yard: "#EAE4D3",
  water: "#AFC8CA",
  waterLabel: "#3C6E8F",
  road: "#D7A25C",
  minor: "#FFFFFF",
  path: "#A88A63",
  rail: "#7A7166",
  trail: "#3F7A3A",
  border: "#8C7B8E",
  label: "#4A3A26",
  halo: "#F7F3E3",
};

let library;
let protocol;

// MapLibre and the PMTiles protocol, loaded once per page.
export function loadLibrary() {
  library ||= (async () => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = new URL("vendor/maplibre/maplibre-gl.css", HERE).href;
    document.head.append(css);
    const [maplibre] = await Promise.all([
      import(new URL("vendor/maplibre/maplibre-gl.mjs", HERE).href),
      script(new URL("vendor/pmtiles.js", HERE).href),
    ]);
    protocol = new window.pmtiles.Protocol();
    maplibre.addProtocol("pmtiles", protocol.tile);
    return maplibre;
  })();
  return library;
}

let indexPromise;

export function loadIndex() {
  indexPromise ||= fetch(new URL("index.json", BASE)).then((r) => {
    if (!r.ok) throw new Error(`maps: index.json: ${r.status}`);
    return r.json();
  });
  return indexPromise;
}

export async function createMap(container, { center, radiusKm = 50, detailNote = DETAIL_NOTE, ...options }) {
  const [maplibre, index] = await Promise.all([loadLibrary(), loadIndex()]);
  const reach = bounds(center, radiusKm);
  const packs = index.areas.filter((a) => overlaps(a.bbox, reach)).map((a) => a.pack);
  for (const pack of [index.overview, ...packs]) {
    if (pack && !protocol.get(packUrl(pack))) protocol.add(new window.pmtiles.PMTiles(new Pieces(pack)));
  }
  const map = new maplibre.Map({
    container,
    style: style(index, packs),
    center: [center.lng, center.lat],
    zoom: 9,
    maxBounds: [[20.5, 57.0], [29.5, 60.0]],
    minZoom: 5,
    maxZoom: 17,
    cooperativeGestures: true,
    ...options,
  });
  await new Promise((resolve) => map.once("load", resolve));
  limitZoom(map, index.areas.filter((a) => packs.includes(a.pack)), detailNote);
  return { map, maplibre, index };
}

// Keep the map from zooming into blank land: past the overview's zoom,
// only the area packs draw, so where none of them has anything near the
// middle of the view, the map's max zoom drops to the overview's. A move
// the map makes itself (flyTo) can still go anywhere the max zoom allows;
// the check runs again once the map is idle.
function limitZoom(map, areas, text) {
  const top = map.getMaxZoom();
  const layers = map.getStyle().layers.filter((l) => /^p\d+$/.test(l.source)).map((l) => l.id);
  const note = document.createElement("p");
  note.className = "maps-note";
  note.setAttribute("role", "status");
  note.textContent = text;
  Object.assign(note.style, {
    position: "absolute", left: "50%", bottom: "28px", transform: "translateX(-50%)", zIndex: 2,
    maxWidth: "min(22rem, calc(100% - 24px))", margin: 0, padding: "6px 10px", borderRadius: "6px",
    background: "rgba(255,255,255,.94)", boxShadow: "0 1px 4px rgba(0,0,0,.2)",
    font: "13px/1.35 system-ui, sans-serif", color: "#333", textAlign: "center", pointerEvents: "none",
  });
  note.hidden = true;
  map.getContainer().append(note);

  const covered = () => {
    const { lng, lat } = map.getCenter();
    const inside = areas.some(({ bbox: [w, s, e, n] }) => lng >= w && lng <= e && lat >= s && lat <= n);
    // Below zoom 9 the packs hardly draw yet: their extent has to do.
    if (!inside || map.getZoom() < 9) return inside;
    const { width, height } = map.getCanvas().getBoundingClientRect();
    const box = [[width / 4, height / 4], [(width * 3) / 4, (height * 3) / 4]];
    return map.queryRenderedFeatures(box, { layers }).length > 0;
  };
  const update = () => {
    const max = covered() ? top : OVERVIEW_ZOOM;
    if (map.getMaxZoom() !== max) {
      map.setMaxZoom(max);
      // The zoom buttons look again only when the map zooms.
      map.fire("zoom");
    }
    note.hidden = !(max < top && map.getZoom() >= max - 0.01);
  };
  map.on("idle", update);
  map.on("zoomend", () => (note.hidden = !(map.getMaxZoom() < top && map.getZoom() >= map.getMaxZoom() - 0.01)));
  map.on("movestart", () => (note.hidden = true));
}

// Show or hide every layer of a group (roads, trails, buildings, borders).
export function setGroup(map, group, visible) {
  for (const layer of map.getStyle().layers) {
    if (layer.metadata?.group === group) map.setLayoutProperty(layer.id, "visibility", visible ? "visible" : "none");
  }
}

// "foot": roads step back and trails come forward. "car": roads lead.
export function setEmphasis(map, mode) {
  for (const layer of map.getStyle().layers) {
    if (layer.metadata?.mode === "road") map.setPaintProperty(layer.id, "line-opacity", mode === "foot" ? 0.45 : 1);
    if (layer.metadata?.mode === "trail") map.setPaintProperty(layer.id, "line-width", mode === "foot" ? 3 : 1.6);
  }
}

// Every municipality's name, and a dot with a name at the settlement it
// is run from (municipalities.json), all in the borders group. links maps
// a municipality's name ("Rõuge vald") to a page, and its name on the map
// then opens it.
export async function addMunicipalities(map, { links = {} } = {}) {
  const r = await fetch(new URL("municipalities.json", BASE));
  if (!r.ok) throw new Error(`maps: municipalities.json: ${r.status}`);
  const { municipalities } = await r.json();
  const point = (coordinates, properties) => ({ type: "Feature", properties, geometry: { type: "Point", coordinates } });
  const features = municipalities.flatMap((m) => [
    point(m.label, { kind: "area", name: m.name, link: links[m.name] || "" }),
    ...(m.centre ? [point([m.centre.lng, m.centre.lat], { kind: "centre", name: m.centre.name })] : []),
  ]);
  map.addSource("municipalities", { type: "geojson", data: { type: "FeatureCollection", features } });
  const group = { group: "borders" };
  const halo = { "text-halo-color": COLORS.halo, "text-halo-width": 1.6 };
  const centre = ["==", ["get", "kind"], "centre"];
  map.addLayer({
    id: "municipality-centre",
    type: "circle",
    source: "municipalities",
    filter: centre,
    metadata: group,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 2.5, 11, 4.5],
      "circle-color": COLORS.label,
      "circle-stroke-color": COLORS.halo,
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: "municipality-centre-label",
    type: "symbol",
    source: "municipalities",
    filter: centre,
    minzoom: 7,
    metadata: group,
    layout: { "text-font": [FONT], "text-size": 12, "text-field": ["get", "name"], "text-anchor": "top", "text-offset": [0, 0.5] },
    paint: { ...halo, "text-color": COLORS.label },
  });
  map.addLayer({
    id: "municipality-label",
    type: "symbol",
    source: "municipalities",
    filter: ["==", ["get", "kind"], "area"],
    minzoom: 6,
    maxzoom: 12,
    metadata: group,
    layout: {
      "text-font": [FONT],
      "text-size": ["interpolate", ["linear"], ["zoom"], 6, 10, 11, 14],
      "text-field": ["get", "name"],
      "text-transform": "uppercase",
      "text-letter-spacing": 0.1,
      "text-max-width": 7,
    },
    paint: { ...halo, "text-color": ["case", ["!=", ["get", "link"], ""], COLORS.label, COLORS.border] },
  });
  map.on("mouseenter", "municipality-label", (e) => {
    if (e.features[0]?.properties.link) map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "municipality-label", () => (map.getCanvas().style.cursor = ""));
  map.on("click", "municipality-label", (e) => {
    const link = e.features[0]?.properties.link;
    if (link) location.assign(link);
  });
  return municipalities;
}


// the names stay on top.
export function firstLabel(map) {
  return map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
}

// A circle of r km around { lat, lng }, as [lng, lat] points.
export function circle(center, r, n = 128) {
  const points = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    const dLat = ((r / 6371) * Math.cos(a) * 180) / Math.PI;
    const dLng = ((r / 6371) * Math.sin(a) * 180) / Math.PI / Math.cos((center.lat * Math.PI) / 180);
    points.push([center.lng + dLng, center.lat + dLat]);
  }
  return points;
}

// The box around a circle of r km: [[west, south], [east, north]].
export function bounds(center, r) {
  const ring = circle(center, r, 8);
  const lngs = ring.map((c) => c[0]);
  const lats = ring.map((c) => c[1]);
  return [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]];
}

// Cloudflare Pages answers no range request, so a pack is served as
// numbered pieces of pack.chunk bytes (packs/<path>/<hash>/<n>.bin), and
// this reads the bytes a PMTiles request needs from the pieces they fall in.
const pieces = new Map();

function packUrl(pack) {
  return new URL(pack.dir, BASE).href;
}

class Pieces {
  constructor(pack) {
    this.pack = pack;
    this.url = packUrl(pack);
  }

  getKey() {
    return this.url;
  }

  async getBytes(offset, length) {
    const { chunk, size } = this.pack;
    const end = Math.min(offset + length, size);
    const first = Math.floor(offset / chunk);
    const last = Math.floor((end - 1) / chunk);
    const parts = [];
    for (let n = first; n <= last; n++) parts.push(this.piece(n));
    const buffers = await Promise.all(parts);
    const out = new Uint8Array(end - offset);
    let at = 0;
    buffers.forEach((buffer, i) => {
      const start = i === 0 ? offset - first * chunk : 0;
      const bytes = new Uint8Array(buffer, start, Math.min(buffer.byteLength - start, out.length - at));
      out.set(bytes, at);
      at += bytes.length;
    });
    return { data: out.buffer };
  }

  // Each piece is fetched once per page; the browser caches it for good.
  piece(n) {
    const url = `${this.url}/${n}.bin`;
    if (!pieces.has(url)) {
      const load = fetch(url).then((r) => {
        if (!r.ok) throw new Error(`maps: ${url}: ${r.status}`);
        return r.arrayBuffer();
      });
      load.catch(() => pieces.delete(url));
      pieces.set(url, load);
    }
    return pieces.get(url);
  }
}

function overlaps([w, s, e, n], [[west, south], [east, north]]) {
  return w <= east && e >= west && s <= north && n >= south;
}

function script(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`maps: could not load ${src}`));
    document.head.append(s);
  });
}

// The style: the overview under the area packs. Each layer is written
// once per source.
export function style(index, packs) {
  // Every map names the data's sources, as their licences ask.
  const source = (pack) => ({ type: "vector", url: `pmtiles://${packUrl(pack)}`, attribution: index.attribution });
  const sources = {};
  if (index.overview) sources.ov = source(index.overview);
  const packIds = packs.map((pack, i) => {
    sources["p" + i] = source(pack);
    return "p" + i;
  });

  const layers = [{ id: "land", type: "background", paint: { "background-color": COLORS.land } }];
  const each = (id, def, { overview = true, overviewMax = 11 } = {}) => {
    if (overview && sources.ov) layers.push({ ...def, id: `ov-${id}`, source: "ov", maxzoom: overviewMax });
    for (const src of packIds) layers.push({ ...def, id: `${src}-${id}`, source: src });
  };
  const is = (values) => ["in", ["get", "class"], ["literal", values]];
  const roads = { group: "roads", mode: "road" };

  each("forest", { type: "fill", "source-layer": "landcover", filter: is(["forest", "scrub"]), paint: { "fill-color": COLORS.forest } });
  each("wet", { type: "fill", "source-layer": "landcover", filter: is(["fen", "bog", "wet_meadow", "peat"]), paint: { "fill-color": COLORS.wet } });
  each("field", { type: "fill", "source-layer": "landcover", filter: is(["farmland"]), paint: { "fill-color": COLORS.field } }, { overview: false });
  each("yard", { type: "fill", "source-layer": "landcover", filter: is(["yard"]), paint: { "fill-color": COLORS.yard } }, { overview: false });
  each("water", { type: "fill", "source-layer": "water", paint: { "fill-color": COLORS.water } });
  each("waterway", {
    type: "line",
    "source-layer": "waterway",
    paint: { "line-color": COLORS.water, "line-width": ["match", ["get", "class"], "river", 1.8, "stream", 1, 0.6] },
  });
  each("road-path", {
    type: "line",
    "source-layer": "road",
    filter: is(["path", "cycleway", "track"]),
    metadata: roads,
    paint: { "line-color": COLORS.path, "line-width": 1, "line-dasharray": [2, 2] },
  }, { overview: false });
  each("road-minor", {
    type: "line",
    "source-layer": "road",
    filter: is(["minor", "street", "link"]),
    metadata: roads,
    paint: { "line-color": COLORS.minor, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 16, 5] },
  }, { overview: false });
  each("road-main", {
    type: "line",
    "source-layer": "road",
    filter: is(["primary", "secondary", "tertiary"]),
    metadata: roads,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": COLORS.road,
      "line-width": ["interpolate", ["linear"], ["zoom"], 7, ["match", ["get", "class"], "primary", 1.4, 0.6], 15, ["match", ["get", "class"], "primary", 7, "secondary", 5.5, 4]],
    },
  });
  each("rail", { type: "line", "source-layer": "rail", paint: { "line-color": COLORS.rail, "line-width": 1.2, "line-dasharray": [3, 2] } });
  each("building", {
    type: "fill",
    "source-layer": "building",
    minzoom: 14,
    metadata: { group: "buildings" },
    paint: {
      "fill-color": ["match", ["get", "use"],
        "lodging", "#E4B2A6", "shop", "#EBC99A", "culture", "#CDBFDD", "religious", "#CDBFDD",
        "education", "#BFD3E2", "health", "#BFD3E2", "sport", "#BFD3E2", "#D9D1C3"],
    },
  }, { overview: false });
  each("trail", {
    type: "line",
    "source-layer": "trail",
    metadata: { group: "trails", mode: "trail" },
    paint: { "line-color": COLORS.trail, "line-width": 1.6, "line-dasharray": [1.5, 1] },
  }, { overview: false });
  each("boundary", {
    type: "line",
    "source-layer": "boundary",
    metadata: { group: "borders" },
    paint: { "line-color": COLORS.border, "line-width": 1, "line-dasharray": [4, 2], "line-opacity": 0.8 },
  });

  const text = (size) => ({ "text-font": [FONT], "text-size": size, "text-max-width": 8 });
  const halo = { "text-color": COLORS.label, "text-halo-color": COLORS.halo, "text-halo-width": 1.4 };
  each("water-label", {
    type: "symbol",
    "source-layer": "water",
    minzoom: 12,
    filter: ["has", "name"],
    layout: { ...text(12), "text-field": ["get", "name"] },
    paint: { ...halo, "text-color": COLORS.waterLabel },
  }, { overview: false });
  each("road-label", {
    type: "symbol",
    "source-layer": "road",
    minzoom: 14,
    filter: ["has", "name"],
    layout: { ...text(11), "text-field": ["get", "name"], "symbol-placement": "line" },
    paint: halo,
  }, { overview: false });
  each("place-label", {
    type: "symbol",
    "source-layer": "place_label",
    layout: { ...text(["interpolate", ["linear"], ["zoom"], 8, 11, 14, 14]), "text-field": ["get", "name"] },
    paint: halo,
    // On to just past OVERVIEW_ZOOM, where a map with no area pack stops.
  }, { overviewMax: OVERVIEW_ZOOM + 0.5 });

  return {
    version: 8,
    glyphs: new URL("fonts/{fontstack}/{range}.pbf", HERE).href.replace("%7Bfontstack%7D", "{fontstack}").replace("%7Brange%7D", "{range}"),
    sources,
    layers,
  };
}
