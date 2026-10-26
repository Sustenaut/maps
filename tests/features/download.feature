Feature: Downloading the data
  `maps download` reads the boundaries, the overview's layers and each
  area's layers from the state WFS, page by page, into data/. A finished
  layer is kept, so a second run only fetches what is missing.

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
