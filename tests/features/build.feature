Feature: Building the site
  `maps build` turns the downloaded data into what maps.sustenaut.eu
  serves: one pack per area, the national overview, index.json that lists
  them, the map package and the Pages headers. Pages answers no range
  request, so each pack is served in numbered pieces the package joins.

  Background:
    Given sample data for two neighbouring municipalities

  Scenario: Each area gets a pack in a folder named by its content
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And index.json lists the areas "louna/alfa, louna/beeta"
    And the pack of "louna/alfa" is in "packs/louna/alfa/<hash>"
    And the overview is in "packs/eesti/<hash>"
    And every pack's pieces join into a PMTiles archive named by its content

  Scenario: An area knows its neighbours and its extent
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And the area "louna/alfa" has the neighbours "Beeta vald"
    And the area "louna/alfa" lies within its municipality's tiles

  Scenario: A pack has the layers the map package draws
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And the pack of "louna/alfa" has the layers "road, water, landcover, building, place_label, trail, poi, boundary"
    And the pack of "louna/alfa" spans zoom 8 to 15
    And the overview has the layers "road, water, boundary, place_label, area_label"

  Scenario: Every municipality is listed, with the settlement it is run from
    Given "Alfa vald" is run from "Alfa küla"
    And "Beeta vald" is run from "Gamma küla"
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And municipalities.json labels "Alfa vald" inside it
    And municipalities.json has "Alfa vald" run from "Alfa"
    And municipalities.json has "Beeta vald" with no centre
    And stderr mentions "Gamma küla"

  Scenario: Every map names the data's sources
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And index.json's attribution names "Maa- ja Ruumiamet, ETAK, EHAK, EHR, RMK"
    And every pack carries the same attribution as index.json

  Scenario: Any site may read the tiles
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And _headers lets any site read the maps
    And _headers caches packs for good and index.json for 5 minutes

  Scenario: The map package and its library ship with the site
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And the site has "lib/v1/map.js, lib/v1/vendor/maplibre/maplibre-gl.mjs, lib/v1/vendor/maplibre/maplibre-gl-worker.mjs, lib/v1/vendor/maplibre/maplibre-gl.css, lib/v1/vendor/pmtiles.js, lib/v1/fonts/noto-sans-regular/0-255.pbf, index.html"

  Scenario: An area that is not a municipality stops the build
    When I build the areas "Alfa vald" at "louna/alfa" and "Gamma vald" at "louna/gamma"
    Then it fails
    And stderr mentions "Gamma vald"

  Scenario: A pack is split into pieces of the same size
    Given pieces of 4096 bytes
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And the pack of "louna/alfa" is in more than one piece of 4096 bytes
    And every pack's pieces join into a PMTiles archive named by its content

  Scenario: With a pack cache, a pack whose inputs have not changed is not built again
    Given a pack cache
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And it prints "maps: reused 0 of 3 pack(s)"
    When I note index.json
    And I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And it prints "maps: reused 3 of 3 pack(s)"
    And index.json is as noted
    When the data of "louna/beeta" changes
    And I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And it prints "maps: reused 2 of 3 pack(s)"
    And only the pack of "louna/beeta" is new since noted
    And the pack cache holds 3 packs
