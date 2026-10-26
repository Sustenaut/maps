Feature: Building the site
  `maps build` turns the downloaded data into what maps.sustenaut.eu
  serves: one pack per area at the area's path, the national overview,
  index.json that lists them, the map package and the Pages headers.

  Background:
    Given sample data for two neighbouring municipalities

  Scenario: Each area gets a pack under a content-hashed name
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And index.json lists the areas "louna/alfa, louna/beeta"
    And every file index.json names exists and is named by its content
    And index.json lists the overview "eesti/overview.<hash>.pmtiles"

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

  Scenario: Every map names the data's sources
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And index.json's attribution names "Maa- ja Ruumiamet, ETAK, EHAK, EHR, RMK"
    And every pack carries the same attribution as index.json

  Scenario: Any site may read the tiles
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And _headers lets any origin make range requests
    And _headers caches packs for good and index.json for 5 minutes

  Scenario: The map package and its library ship with the site
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it succeeds
    And the site has "lib/v1/map.js, lib/v1/vendor/maplibre/maplibre-gl.mjs, lib/v1/vendor/maplibre/maplibre-gl-worker.mjs, lib/v1/vendor/maplibre/maplibre-gl.css, lib/v1/vendor/pmtiles.js, lib/v1/fonts/noto-sans-regular/0-255.pbf, index.html"

  Scenario: An area that is not a municipality stops the build
    When I build the areas "Alfa vald" at "louna/alfa" and "Gamma vald" at "louna/gamma"
    Then it fails
    And stderr mentions "Gamma vald"

  Scenario: A pack too big for Pages stops the build
    Given packs may be at most 1000 bytes
    When I build the areas "Alfa vald" at "louna/alfa" and "Beeta vald" at "louna/beeta"
    Then it fails
    And stderr mentions "over the Pages limit"
