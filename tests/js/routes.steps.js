// The routes package (lib/v1/routes.js) on small road networks as
// mapbuild/routes.py writes them, run by `make functional`. The suite's own
// steps build networks and call the package through `attempt`; pubtest's
// steps (tests/js/features/support.js) check what came back.
import { Given, Then, When, defineParameterType } from "@cucumber/cucumber";
import { mock } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { areasAround, joinNetworks, loadNetwork, nearest, route, FOOT, CAR_AB, CAR_BA } from "../../lib/v1/routes.js";

// The places of the feature's square, about 1.1 km a side.
const PLACES = { A: [26.9, 57.7], B: [26.918, 57.7], C: [26.918, 57.71], D: [26.9, 57.71] };
const OPEN = { all: FOOT | CAR_AB | CAR_BA, walkers: FOOT, "walkers, and cars along it": FOOT | CAR_AB };

// A named place, or "lng, lat".
function place(text) {
  const [lng, lat] = PLACES[text] ?? text.split(",").map(Number);
  return { lng, lat };
}

defineParameterType({ name: "travel", regexp: /on foot|by car|by bike/, transformer: (t) => t.split(" ")[1] });

// A network as mapbuild/routes.py writes it: its places in the order the
// rows first name them, and each road [from, to, metres, modes | road type << 3].
Given("a road network:", function (table) {
  const points = [];
  const index = (name) => (points.includes(name) || points.push(name), points.indexOf(name));
  const edges = table.hashes().flatMap((row) => [
    index(row.from), index(row.to), Number(row.metres), OPEN[row["open to"]] | (Number(row["road type"]) << 3),
  ]);
  const nodes = points.flatMap((name) => { const { lng, lat } = place(name); return [Math.round(lng * 1e6), Math.round(lat * 1e6)]; });
  (this.networks ??= []).push({ version: 1, nodes, edges });
});

Given("a road network of version {int}, with nothing in it", function (version) {
  (this.networks ??= []).push({ version, nodes: [], edges: [] });
});

const graph = (world) => world.graph ?? joinNetworks(world.networks ?? []);

When("I find the way {travel} from {string} to {string}", async function (travel, from, to) {
  await this.attempt(() => route(graph(this), place(from), [place(to)], travel));
});

When("I join the networks", async function () {
  await this.attempt(() => joinNetworks(this.networks));
});

When("I join the networks and list what leaves {string} by car", async function (name) {
  await this.attempt(() => {
    const g = joinNetworks(this.networks);
    const { lng, lat } = place(name);
    return g.out.car[g.lng.findIndex((x, i) => x === lng && g.lat[i] === lat)];
  });
});

When("I ask where {string} joins the network {travel}", async function (point, travel) {
  await this.attempt(() => nearest(graph(this), place(point), travel));
});

When("I pick the areas of {string} around {string} and {string}", async function (file, a, b) {
  const index = JSON.parse(fs.readFileSync(path.join(this.pubtest.directory, file), "utf8"));
  await this.attempt(() => areasAround(index, [place(a), place(b)]).map((area) => area.path));
});

When("I load the network around {string} and {string} from the files here", async function (a, b) {
  const read = [];
  const dir = this.pubtest.directory;
  const get = async (file) => (read.push(file), JSON.parse(fs.readFileSync(path.join(dir, file), "utf8")));
  await this.attempt(async () => {
    this.graph = await loadNetwork([place(a), place(b)], { read: get });
    return read;
  });
});

// fetch, stood in for: what it was asked, and the one answer it gives.
function standInFetch(world, answer) {
  world.fetched = [];
  mock.method(globalThis, "fetch", async (url) => (world.fetched.push(new URL(url).pathname), answer(world.fetched.length)));
  world.pubtest.cleanup(() => mock.restoreAll());
}

Given("every fetch answers an index of no areas", function () {
  standInFetch(this, (n) => ({ ok: true, json: async () => (n === 1 ? { version: 1, areas: [] } : null) }));
});

Given("every fetch answers {int}", function (status) {
  standInFetch(this, () => ({ ok: false, status }));
});

When("I load the network around {string}", async function (point) {
  await this.attempt(() => loadNetwork([place(point)]));
});

Then("the first address fetched has a path matching {string}", function (pattern) {
  const wanted = new RegExp(`^${pattern.split("*").map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*")}$`, "s");
  if (!wanted.test(this.fetched[0] ?? "")) throw new Error(`the first address fetched is ${this.fetched[0]}, not ${pattern}`);
});

Then("the result's {string} is within {float} of {float}", function (key, within, wanted) {
  const got = key.split(".").reduce((v, k) => v?.[k], this.pubtest.result);
  if (!(Math.abs(got - wanted) < within)) throw new Error(`the result's ${key} is ${got}, not within ${within} of ${wanted}`);
});
