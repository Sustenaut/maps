# maps.sustenaut.eu

Maps of Estonia from the state's open data, built weekly and served from
Cloudflare Pages, for any sustenaut.eu site (visit.ee first).

The data is Maa- ja Ruumiamet's topographic database (ETAK), its
administrative boundaries (EHAK) and the Building Register's use codes
(EHR), and RMK's trails and visitor sites, all read from the state WFS at
gsavalik.envir.ee. There is no OpenStreetMap data in the maps.

## Using a map on a site

```html
<div id="map" style="height: 400px"></div>
<script type="module">
  import { createMap, setGroup, setEmphasis, circle } from "https://maps.sustenaut.eu/lib/v1/map.js";
  const { map, maplibre } = await createMap(document.getElementById("map"), {
    center: { lat: 57.729, lng: 26.929 },
    radiusKm: 25,   // load the area packs within 25 km
    zoom: 11,       // anything else goes to MapLibre's Map
  });
  new maplibre.Marker().setLngLat([26.929, 57.729]).addTo(map);
  setEmphasis(map, "foot");          // trails forward, roads back
  setGroup(map, "buildings", false); // groups: roads, trails, buildings, borders
</script>
```

The package loads MapLibre GL and PMTiles from this site, so a site needs
nothing else.

Where no area pack covers the view, only the overview (zoom 5 to 10)
draws, so the map stops zooming in there: the zoom-in button turns off and
a note says why. Pass `detailNote` to `createMap` to translate it. `/lib/v1/` only grows; a change that would break a site goes
to `/lib/v2/`. `lib/v1/map.js` documents every export.

## What the site serves

| Path | What |
| --- | --- |
| `index.json` | the overview and every area pack (where its pieces are), each area's name, EHAK code, extent and neighbours |
| `municipalities.json` | every municipality: where to write its name, its extent, and the settlement it is run from (`centres.json`), for `addMunicipalities()` |
| `packs/eesti/<hash>/<n>.bin` | all of Estonia, zoom 5 to 10 |
| `packs/<path>/<hash>/<n>.bin` | one municipality, zoom 8 to 15, at the path `areas.json` gives it |
| `lib/v1/` | the map package, its fonts and the map library |

Each pack is a PMTiles archive cut into numbered 128 KiB pieces. A PMTiles
reader asks for a few kilobytes at a time with range requests, and
Cloudflare Pages answers none: it always sends the whole file. So the
package reads the pieces a request falls in instead. The folder is named
by the pack's content, so pieces are cached for good and a changed pack
gets new names; `index.json` is cached for five minutes. Any origin may
read them.

To add an area, add its EHAK name and path to `areas.json`. When a
municipality moves its seat or two merge, change `centres.json`; the build
names any seat it cannot find.

## Building

You need Python 3, Node and tippecanoe (`apt install tippecanoe`).

```sh
make venv node
bin/maps download   # into data/; a finished layer is kept
bin/maps build      # into _site/
make functional     # the Gherkin suite, on small made-up data
```

`.github/workflows/deploy.yml` downloads, builds and publishes on every
push to main and every Monday. It keeps the downloaded data for the ISO
week, so only the first run of a week fetches it (run it by hand with
`fresh` to fetch it anyway), and keeps the built packs: `bin/maps build
--cache` makes each pack through pubkit's `pubkit cache run`, by the rules
in pubkit.json's `cache` block, so a pack whose inputs (its data, the
boundaries, mapbuild's code and tippecanoe's version) have not changed is
copied, and a deploy that changes only `lib/` or `site/` builds nothing
again. pubkit's `actions/cache` restores and saves both. It runs once the repository variable
`MAPS_DEPLOY` is `on`, with the Actions secret `CLOUDFLARE_GITHUB_API_TOKEN`
and variable `CLOUDFLARE_ACCOUNT_ID`. The Pages project `sustenaut-maps`
and the DNS name come from schryer/business-plan's infrastructure.

`pr.yml` and `main.yml` are written by `pubkit sync` from `pubkit.json`.

## Licences

The map data: © Maa- ja Ruumiamet (ETAK, EHAK, EHR), under its open data
licence, and © RMK. The fonts: Noto Sans, SIL Open Font License
(`lib/v1/fonts/OFL.txt`). MapLibre GL JS: BSD-3-Clause. PMTiles: BSD-3-Clause.
