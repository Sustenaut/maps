// cucumber-js's setup for these scenarios: pubtest's steps (GRAMMAR.md), and
// a step may take as long as a test could under node:test.
import * as cucumber from "@cucumber/cucumber";
import { register } from "@sustenaut/pubtest";

cucumber.setDefaultTimeout(60_000);
register(cucumber);
