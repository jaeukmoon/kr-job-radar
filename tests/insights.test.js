"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const insights = require("../insights.js");
test("Korean deadline dates use today, including month boundaries", () => {
  assert.equal(insights.today(new Date("2026-10-14T16:00:00Z")), "2026-10-15");
  assert.equal(insights.daysTo("2026-10-14", "2026-10-15"), -1);
  assert.equal(insights.daysTo("2026-11-01", "2026-10-31"), 1);
  assert.equal(insights.daysTo("상시", "2026-10-15"), null);
});
test("preferred filters do not admit required-only matches", () => {
  const job = {domains: ["llm"], pref_domains: ["robotics"]};
  assert.equal(insights.matches(job, {type: "domain", id: "llm"}, "pref"), false);
  assert.equal(insights.matches(job, {type: "domain", id: "llm"}, "all"), true);
});
test("one posting is counted once per keyword with distinct companies", () => {
  const rows = insights.rows([{company: "A", skills: ["python", "python"]},
    {company: "A", skills: ["python"]}, {company: "B", skills: ["python"]},
    {company: "C", skills: []}], "skills");
  assert.deepEqual(rows, [{id: "python", count: 3, companies: 2, percent: 75}]);
});
test("recent windows exclude future and eighth-day postings", () => {
  assert.equal(insights.recent({first_seen: "2026-10-09"}, 7, "2026-10-15"), true);
  assert.equal(insights.recent({first_seen: "2026-10-08"}, 7, "2026-10-15"), false);
  assert.equal(insights.recent({first_seen: "2026-10-16"}, 7, "2026-10-15"), false);
});
