@routes
Feature: The routes package (lib/v1/routes.js) on small road networks as mapbuild/routes.py writes them

  Scenario: A walk takes the shortest way, and a drive the quickest
    Then a walk takes the shortest way, and a drive the quickest

  Scenario: A car keeps to a one-way road's direction; a walker does not
    Then a car keeps to a one-way road's direction; a walker does not

  Scenario: A path takes walkers only
    Then a path takes walkers only

  Scenario: The way starts and ends off the road, along a straight line to it
    Then the way starts and ends off the road, along a straight line to it

  Scenario: A place far from any road has no way to it
    Then a place far from any road has no way to it

  Scenario: Neighbouring areas' networks join where they share a node, and a shared road counts once
    Then neighbouring areas' networks join where they share a node, and a shared road counts once

  Scenario: Only the areas around the points are read
    Then only the areas around the points are read

  Scenario: loadNetwork fetches from the site the module came from by default
    Then loadNetwork fetches from the site the module came from by default

  Scenario: A failed fetch says what failed
    Then a failed fetch says what failed

  Scenario: Nearest says where a point joins the network, nearest first
    Then nearest says where a point joins the network, nearest first

  Scenario: A one-way road's far end still takes a car in
    Then a one-way road's far end still takes a car in

  Scenario: An unknown profile is refused, and a network of another version too
    Then an unknown profile is refused, and a network of another version too
