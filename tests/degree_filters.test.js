"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const degrees = require("../degree_filters.js");
const job = {degree_requirements: {available: true,
  required: [{degree:"masters",text:"Master’s or equivalent experience"}],
  preferred: [{degree:"phd",text:"PhD preferred"}],
  unclassified: [{degree:"phd",text:"<script>PhD</script>"}]}};
test("degree and section must match the same mention", () => {
  assert.equal(degrees.matches(job,"masters","required"),true);
  assert.equal(degrees.matches(job,"phd","preferred"),true);
  assert.equal(degrees.matches(job,"phd","required"),false);
  assert.equal(degrees.matches(job,"masters","preferred"),false);
});
test("graduate OR and section-only filters", () => {
  assert.equal(degrees.matches(job,"graduate","required"),true);
  assert.equal(degrees.matches(job,"graduate","preferred"),true);
  assert.equal(degrees.matches(job,"all","preferred"),true);
});
test("missing and body-only text never pass qualification filters", () => {
  assert.equal(degrees.matches({},"all","all"),true);
  assert.equal(degrees.matches({},"phd","all"),false);
  assert.equal(degrees.matches({degree_requirements:{unclassified:[{degree:"phd",text:"team"}]}},"phd","required"),false);
});
test("evidence is escaped and unavailable data stays visible", () => {
  const esc = s => s.replaceAll('<','&lt;').replaceAll('>','&gt;');
  assert(!degrees.markup(job,esc).includes('<script>'));
  assert(degrees.markup(job,esc).includes('or equivalent experience'));
  assert(degrees.markup({},esc).includes('원문 미확보'));
  assert(degrees.markup({degree_requirements:{available:true}},esc).includes('언급 미검출'));
});
