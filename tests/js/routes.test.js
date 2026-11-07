// The routes package (lib/v1/routes.js) on small road networks as
// mapbuild/routes.py writes them, run by `make functional`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { areasAround, joinNetworks, loadNetwork, nearest, route, crowMetres, FOOT, CAR_AB, CAR_BA } from "../../lib/v1/routes.js";

// A network as mapbuild/routes.py writes it, from points in degrees and
// edges [a, b, metres, modes, road type].
function network(points, edges) {
  return {
    version: 1,
    nodes: points.flatMap(([lng, lat]) => [Math.round(lng * 1e6), Math.round(lat * 1e6)]),
    edges: edges.flatMap(([a, b, m, modes, kind]) => [a, b, m, modes | (kind << 3)]),
  };
}
const BOTH = FOOT | CAR_AB | CAR_BA;
const at = ([lng, lat]) => ({ lng, lat });
// A square of four roads, about 1.1 km a side: A (south-west), B (south-east),
// C (north-east), D (north-west).
const A = [26.9, 57.7];
const B = [26.918, 57.7];
const C = [26.918, 57.71];
const D = [26.9, 57.71];

test("a walk takes the shortest way, and a drive the quickest", () => {
  // A to C: east then north on a main road (2.2 km), or north then east on a
  // forest road (2 km).
  const g = joinNetworks([network([A, B, C, D], [[0, 1, 1100, BOTH, 1], [1, 2, 1100, BOTH, 1], [0, 3, 1000, BOTH, 6], [3, 2, 1000, BOTH, 6]])]);
  assert.deepEqual(route(g, at(A), [at(C)], "foot"), [2000]);
  assert.deepEqual(route(g, at(A), [at(C)], "car"), [2200]);
});

test("a car keeps to a one-way road's direction; a walker does not", () => {
  // A to B one way only (along the line), and the long way round both ways.
  const g = joinNetworks([network([A, B, C, D], [[1, 0, 1100, FOOT | CAR_AB, 3], [0, 3, 1100, BOTH, 3], [3, 2, 1100, BOTH, 3], [2, 1, 1100, BOTH, 3]])]);
  assert.deepEqual(route(g, at(A), [at(B)], "foot"), [1100]);
  assert.deepEqual(route(g, at(A), [at(B)], "car"), [3300]);
  assert.deepEqual(route(g, at(B), [at(A)], "car"), [1100]);
});

test("a path takes walkers only", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, FOOT, 7]])]);
  assert.deepEqual(route(g, at(A), [at(B)], "foot"), [1100]);
  assert.deepEqual(route(g, at(A), [at(B)], "car"), [null]);
});

test("the way starts and ends off the road, along a straight line to it", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, BOTH, 3]])]);
  // About 111 m north of A, and of B.
  const [walk] = route(g, { lng: A[0], lat: A[1] + 0.001 }, [{ lng: B[0], lat: B[1] + 0.001 }], "foot");
  assert.ok(Math.abs(walk - (1100 + 2 * 111)) < 2, walk);
});

test("a place far from any road has no way to it", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, BOTH, 3]])]);
  assert.deepEqual(route(g, at(A), [{ lng: 27.2, lat: 57.9 }], "foot"), [null]);
});

test("neighbouring areas' networks join where they share a node, and a shared road counts once", () => {
  const west = network([A, B], [[0, 1, 1100, BOTH, 3]]);
  const east = network([B, C], [[0, 1, 1100, BOTH, 3]]);
  const both = network([A, B], [[0, 1, 1100, BOTH, 3]]);
  const g = joinNetworks([west, east, both]);
  assert.deepEqual(route(g, at(A), [at(C)], "car"), [2200]);
  assert.equal(g.out.car[0].length, 3);
});

test("only the areas around the points are read", async () => {
  const index = {
    areas: [
      { path: "near", bbox: [26.8, 57.6, 27.0, 57.8], routes: { file: "routes/near.json" } },
      { path: "far", bbox: [24.5, 59.3, 24.9, 59.5], routes: { file: "routes/far.json" } },
      { path: "no-routes", bbox: [26.8, 57.6, 27.0, 57.8] },
    ],
  };
  assert.deepEqual(areasAround(index, [at(A), at(C)]).map((a) => a.path), ["near"]);
  const read = [];
  const get = async (file) => (read.push(file), file === "index.json" ? index : network([A, B], [[0, 1, 1100, BOTH, 3]]));
  const g = await loadNetwork([at(A), at(C)], { read: get });
  assert.deepEqual(read, ["index.json", "routes/near.json"]);
  assert.deepEqual(route(g, at(A), [at(B)], "car"), [1100]);
});

test("loadNetwork fetches from the site the module came from by default", async (t) => {
  const asked = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    asked.push(new URL(url).pathname);
    const body = asked.length === 1 ? { version: 1, areas: [] } : null;
    return { ok: true, json: async () => body };
  });
  await loadNetwork([at(A)]);
  assert.match(asked[0], /\/index\.json$/);
});

test("a failed fetch says what failed", async (t) => {
  t.mock.method(globalThis, "fetch", async () => ({ ok: false, status: 404 }));
  await assert.rejects(loadNetwork([at(A)]), /index\.json: 404/);
});

test("nearest says where a point joins the network, nearest first", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, BOTH, 3]])]);
  const joins = nearest(g, { lng: A[0], lat: A[1] + 0.001 }, "foot");
  assert.equal(joins.length, 1);
  assert.equal(joins[0][0], 0);
  assert.ok(Math.abs(joins[0][1] - crowMetres(at(A), { lng: A[0], lat: A[1] + 0.001 })) < 0.01);
});

test("a one-way road's far end still takes a car in", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, FOOT | CAR_AB, 3]])]);
  assert.deepEqual(route(g, at(A), [at(B)], "car"), [1100]);
});

test("an unknown profile is refused, and a network of another version too", () => {
  const g = joinNetworks([network([A, B], [[0, 1, 1100, BOTH, 3]])]);
  assert.throws(() => route(g, at(A), [at(B)], "bike"), /no route profile "bike"/);
  assert.throws(() => joinNetworks([{ version: 2, nodes: [], edges: [] }]), /version 2/);
});
