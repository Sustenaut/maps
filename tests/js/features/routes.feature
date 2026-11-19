@routes
Feature: The routes package (lib/v1/routes.js) on small road networks as mapbuild/routes.py writes them
  The places are a square about 1.1 km a side: A (26.9, 57.7, south-west),
  B (26.918, 57.7, south-east), C (26.918, 57.71, north-east) and D (26.9,
  57.71, north-west). A road is open to all both ways, to walkers only, or
  to walkers and to cars along its line (from its first place to its second).

  Scenario Outline: A walk takes the shortest way, and a drive the quickest
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 1         |
      | B    | C  | 1100   | all     | 1         |
      | A    | D  | 1000   | all     | 6         |
      | D    | C  | 1000   | all     | 6         |
    When I find the way <travel> from "A" to "C"
    Then the result is "<metres>"

    Examples: East then north on a main road, or north then east on a forest road
      | travel  | metres |
      | on foot | [2000] |
      | by car  | [2200] |

  Scenario Outline: A car keeps to a one-way road's direction; a walker does not
    Given a road network:
      | from | to | metres | open to                    | road type |
      | B    | A  | 1100   | walkers, and cars along it | 3         |
      | A    | D  | 1100   | all                        | 3         |
      | D    | C  | 1100   | all                        | 3         |
      | C    | B  | 1100   | all                        | 3         |
    When I find the way <travel> from "<from>" to "<to>"
    Then the result is "<metres>"

    Examples:
      | travel  | from | to | metres |
      | on foot | A    | B  | [1100] |
      | by car  | A    | B  | [3300] |
      | by car  | B    | A  | [1100] |

  Scenario Outline: A path takes walkers only
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | walkers | 7         |
    When I find the way <travel> from "A" to "B"
    Then the result is "<metres>"

    Examples:
      | travel  | metres |
      | on foot | [1100] |
      | by car  | [null] |

  Scenario: The way starts and ends off the road, along a straight line to it
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I find the way on foot from "26.9, 57.701" to "26.918, 57.701"
    Then the result's "0" is within 2 of 1322

  Scenario: A place far from any road has no way to it
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I find the way on foot from "A" to "27.2, 57.9"
    Then the result is "[null]"

  Scenario: Neighbouring areas' networks join where they share a node
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    And a road network:
      | from | to | metres | open to | road type |
      | B    | C  | 1100   | all     | 3         |
    And a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I find the way by car from "A" to "C"
    Then the result is "[2200]"

  Scenario: A road two neighbouring areas share counts once
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    And a road network:
      | from | to | metres | open to | road type |
      | B    | C  | 1100   | all     | 3         |
    And a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I join the networks and list what leaves "A" by car
    Then the result has 3 numbers

  Scenario: Only the areas around the points are picked
    Given a scratch directory
    And a file "index.json" holding:
      """
      {"areas": [
        {"path": "near", "bbox": [26.8, 57.6, 27.0, 57.8], "routes": {"file": "routes/near.json"}},
        {"path": "far", "bbox": [24.5, 59.3, 24.9, 59.5], "routes": {"file": "routes/far.json"}},
        {"path": "no-routes", "bbox": [26.8, 57.6, 27.0, 57.8]}
      ]}
      """
    When I pick the areas of "index.json" around "A" and "C"
    Then the result is:
      """
      ["near"]
      """

  Scenario: Only the networks of the areas around the points are read
    Given a scratch directory
    And a file "index.json" holding:
      """
      {"areas": [
        {"path": "near", "bbox": [26.8, 57.6, 27.0, 57.8], "routes": {"file": "routes/near.json"}},
        {"path": "far", "bbox": [24.5, 59.3, 24.9, 59.5], "routes": {"file": "routes/far.json"}},
        {"path": "no-routes", "bbox": [26.8, 57.6, 27.0, 57.8]}
      ]}
      """
    And a file "routes/near.json" holding:
      """
      {"version": 1, "nodes": [26900000, 57700000, 26918000, 57700000], "edges": [0, 1, 1100, 31]}
      """
    When I load the network around "A" and "C" from the files here
    Then the result is:
      """
      ["index.json", "routes/near.json"]
      """

  Scenario: The network read is the one routed on
    Given a scratch directory
    And a file "index.json" holding:
      """
      {"areas": [{"path": "near", "bbox": [26.8, 57.6, 27.0, 57.8], "routes": {"file": "routes/near.json"}}]}
      """
    And a file "routes/near.json" holding:
      """
      {"version": 1, "nodes": [26900000, 57700000, 26918000, 57700000], "edges": [0, 1, 1100, 31]}
      """
    When I load the network around "A" and "C" from the files here
    And I find the way by car from "A" to "B"
    Then the result is "[1100]"

  Scenario: loadNetwork fetches from the site the module came from by default
    Given every fetch answers an index of no areas
    When I load the network around "A"
    Then it is not refused
    And the first address fetched has a path matching "*/index.json"

  Scenario: A failed fetch says what failed
    Given every fetch answers 404
    When I load the network around "A"
    Then it is refused, saying "index.json: 404"

  Scenario: Nearest says where a point joins the network, nearest first
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I ask where "26.9, 57.701" joins the network on foot
    Then the result has 1 join
    And the result's "0.0" is "0"
    And the result's "0.1" is within 0.01 of 111.19508023327376

  Scenario: A one-way road's far end still takes a car in
    Given a road network:
      | from | to | metres | open to                    | road type |
      | A    | B  | 1100   | walkers, and cars along it | 3         |
    When I find the way by car from "A" to "B"
    Then the result is "[1100]"

  Scenario: An unknown profile is refused
    Given a road network:
      | from | to | metres | open to | road type |
      | A    | B  | 1100   | all     | 3         |
    When I find the way by bike from "A" to "B"
    Then it is refused, saying 'no route profile "bike"'

  Scenario: A network of another version is refused
    Given a road network of version 2, with nothing in it
    When I join the networks
    Then it is refused, saying "version 2"
