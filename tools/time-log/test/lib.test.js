// Covers the arithmetic, the date parsing, and the roster resolution — the
// parts that can be quietly wrong without anything looking broken.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  budgetLines, dataDir, hours, loadRoster, loggedHours, money, rateFor, resolveClient,
  resolveProject, resolveWindow, roundMinutes, select, summarize, unknownClientNote,
  unknownProjectNote, versionCompare,
} from "../src/lib.js";

const WED = new Date(2026, 7, 26); // a Wednesday
const entry = (client, minutes, day, project = null) =>
  ({ client, project, start: `${day}T09:00:00-06:00`, minutes });

test("roundMinutes rounds up to the increment", () => {
  assert.equal(roundMinutes(31, 15), 45);
  assert.equal(roundMinutes(45, 15), 45);
  assert.equal(roundMinutes(0.5, 15), 15);
  assert.equal(roundMinutes(31.4, 1), 31);
});

test("resolveWindow turns phrases into inclusive day ranges", () => {
  const cases = [
    ["today", ["2026-08-26", "2026-08-26"]],
    ["yesterday", ["2026-08-25", "2026-08-25"]],
    ["this week", ["2026-08-24", "2026-08-30"]],
    ["last week", ["2026-08-17", "2026-08-23"]],
    ["this month", ["2026-08-01", "2026-08-31"]],
    ["last month", ["2026-07-01", "2026-07-31"]],
    ["2026-01-09", ["2026-01-09", "2026-01-09"]],
  ];
  for (const [phrase, expected] of cases) {
    assert.deepEqual(resolveWindow(phrase, null, WED), expected, phrase);
  }
});

test("until narrows the far end", () => {
  assert.equal(resolveWindow("this week", "2026-08-26", WED)[1], "2026-08-26");
});

test("select filters by client case-insensitively and by date", () => {
  const rows = [
    entry("Acme", 60, "2026-08-26"), entry("Other", 60, "2026-08-26"),
    entry("Acme", 60, "2026-08-01"),
  ];
  const got = select(rows, "acme", null, "2026-08-24", "2026-08-30");
  assert.equal(got.length, 1);
});

test("summarize rounds each group, not the total", () => {
  const rows = [entry("Acme", 10, "2026-08-26", "a"), entry("Acme", 10, "2026-08-26", "b")];
  const s = summarize(rows, 15);
  assert.equal(s.total, 30); // two lines at 15 each, not one 20 rounded to 30
  assert.equal(s.count, 2);
});

test("summarize keeps clients and projects apart even with spaces in names", () => {
  const rows = [entry("Beta Co", 60, "2026-08-26", "Big Redesign")];
  assert.deepEqual(summarize(rows).groups, [
    { client: "Beta Co", project: "Big Redesign", minutes: 60 },
  ]);
});

const ROSTER = {
  clients: [
    { name: "Acme Industries", aliases: ["Acme", "acme llc"], projects: [
      { name: "Redesign", budget_hours: 10 }, { name: "Retainer", budget_hours: null },
    ], rate_per_hour: 150 },
    { name: "Beta Co", aliases: [], projects: [] },
  ],
  default_round_to: 15,
};

test("resolveClient collapses spellings", () => {
  for (const [typed, expected] of [
    ["Acme Industries", "Acme Industries"], ["acme industries", "Acme Industries"],
    ["Acme", "Acme Industries"], ["ACME LLC", "Acme Industries"],
    ["  Beta Co ", "Beta Co"], ["Gamma", null],
  ]) {
    assert.equal(resolveClient(typed, ROSTER), expected, typed);
  }
});

test("resolveProject is scoped to the client", () => {
  assert.equal(resolveProject("Acme", "redesign", ROSTER), "Redesign");
  assert.equal(resolveProject("acme", "RETAINER", ROSTER), "Retainer");
  assert.equal(resolveProject("Acme", "SEO", ROSTER), null);
  assert.equal(resolveProject("Beta Co", "anything", ROSTER), null);
});

test("the unknown-name notes stay quiet when there is nothing to compare against", () => {
  assert.match(unknownClientNote("Gamma", ROSTER), /Acme Industries/);
  assert.equal(unknownClientNote("Gamma", { clients: [], default_round_to: 1 }), "");
  assert.match(unknownProjectNote("Acme", "SEO", ROSTER), /SEO/);
  assert.equal(unknownProjectNote("Beta Co", "anything", ROSTER), "");
  assert.equal(unknownProjectNote("Acme", "redesign", ROSTER), "");
});

test("rateFor follows aliases and tolerates a missing rate", () => {
  assert.equal(rateFor("acme llc", ROSTER), 150);
  assert.equal(rateFor("Beta Co", ROSTER), null);
  assert.equal(rateFor("Nobody", ROSTER), null);
});

test("money and hours format for people, not machines", () => {
  assert.equal(money(1837.5), "$1,837.50");
  assert.equal(money(0), "$0.00");
  assert.equal(hours(90), "1.50");
});

const LOGGED = [
  entry("Acme Industries", 300, "2026-09-01", "Redesign"),
  entry("Acme Industries", 240, "2026-09-01", "Redesign"),
  entry("Acme Industries", 60, "2026-09-01", "Retainer"),
  entry("Other", 600, "2026-09-01", "Redesign"),
];

test("loggedHours counts only this client and project", () => {
  assert.equal(loggedHours("Acme Industries", "Redesign", LOGGED), 9);
});

test("budgetLines skips projects with no budget and reports overruns as negative", () => {
  const rows = budgetLines(ROSTER, LOGGED);
  assert.deepEqual(rows.map((r) => r.project), ["Redesign"]);
  assert.equal(rows[0].left, 1);
  assert.equal(rows[0].fraction, 0.9);

  const over = [...LOGGED, entry("Acme Industries", 180, "2026-09-01", "Redesign")];
  assert.equal(budgetLines(ROSTER, over)[0].left, -2);
});

test("versionCompare orders releases, including double digits", () => {
  assert.equal(versionCompare("0.3.0", "v0.4.0"), -1);
  assert.equal(versionCompare("v0.9.0", "0.10.0"), -1);
  assert.equal(versionCompare("v0.4.0", "0.4.0"), 0);
});

// --- storage ---------------------------------------------------------------

let tmp;
before(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), "time-log-test-"));
  process.env.TIME_LOG_DIR = tmp;
});
after(() => fs.rmSync(tmp, { recursive: true, force: true }));

test("a roster written by an older version still loads", () => {
  fs.writeFileSync(path.join(dataDir(), "clients.json"), JSON.stringify({
    clients: [{ name: "Acme", aliases: [], projects: ["Redesign"] }],
    default_round_to: 15,
  }));
  const roster = loadRoster();
  assert.deepEqual(roster.clients[0].projects, [{ name: "Redesign", budget_hours: null }]);
  assert.equal(resolveProject("Acme", "redesign", roster), "Redesign");
});

test("an empty data dir yields an empty roster rather than throwing", () => {
  fs.rmSync(path.join(dataDir(), "clients.json"), { force: true });
  assert.deepEqual(loadRoster(), { clients: [], default_round_to: 1 });
});
