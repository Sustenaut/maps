Feature: Downloading the data
  `maps download` reads the boundaries, the overview's layers and each
  area's layers from the state WFS, page by page, into data/. A finished
  layer is kept, so a second run only fetches what is missing. The areas
  are the ones areas.json lists and each municipality a site's place is
  in; an area's layers are fetched again when its places change, and not
  otherwise.

  Background:
    Given a WFS with two neighbouring municipalities

  Scenario: A layer is read page by page until a short page
    Given the WFS returns 2 features a page
    When I download the area "Alfa vald" at "louna/alfa"
    Then it succeeds
    And the data has every municipality's boundary
    And the data has every layer of the area "louna/alfa" and of the overview
    And the area "louna/alfa"'s roads have all 5 features, read in 3 pages

  Scenario: A second download fetches nothing it already has
    When I download the area "Alfa vald" at "louna/alfa"
    And I download the area "Alfa vald" at "louna/alfa" again
    Then it succeeds
    And the second download made no requests

  Scenario: An area that is not a municipality stops the download
    When I download the area "Gamma vald" at "louna/gamma"
    Then it fails
    And stderr mentions "Gamma vald"

  Scenario: Each municipality a place is in gets an area, at its region's path
    Given a site has the place "torn" at 57.72, 26.95
    And a site has the place "jarv" at 57.73, 26.96
    When I download the areas the places are in
    Then it succeeds
    And the planned areas are "louna/beeta"
    And the area "louna/beeta" has the places "jarv, torn"
    And the data has every layer of the area "louna/beeta" and of the overview

  Scenario: An area's layers are fetched again only when its places change
    Given a site has the place "torn" at 57.72, 26.95
    When I download the areas the places are in
    And I download the areas the places are in
    Then the download fetched no area's layers
    When a site adds the place "jarv" at 57.73, 26.96
    And I download the areas the places are in
    Then it succeeds
    And the download fetched the layers of "louna/beeta" again

  Scenario: A place in no municipality gets no area, and is named
    Given a site has the place "laht" at 59.0, 24.0
    When I download the areas the places are in
    Then it succeeds
    And no area is planned
    And stderr mentions "laht"
