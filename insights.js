/* Pure aggregation shared by the dashboard and regression tests. */
"use strict";
const JobInsights = (() => {
  function today(date = new Date()) {
    return new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Seoul",
      year: "numeric", month: "2-digit", day: "2-digit"}).format(date);
  }
  function day(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
    const result = Date.parse(value + "T00:00:00Z");
    return Number.isFinite(result) ? result / 86400000 : null;
  }
  function daysTo(value, now = today()) {
    const target = day(value), current = day(now);
    return target === null || current === null ? null : target - current;
  }
  function recent(job, count, now = today()) {
    const delta = daysTo(job.first_seen, now);
    return delta !== null && delta <= 0 && delta > -count;
  }
  function field(type, scope) {
    return (scope === "pref" ? "pref_" : "") + (type === "domain" ? "domains" : "skills");
  }
  function matches(job, filter, scope) {
    return (job[field(filter.type, scope)] || []).includes(filter.id);
  }
  function rows(jobs, key) {
    const entries = new Map();
    for (const job of jobs) for (const id of new Set(job[key] || [])) {
      if (!entries.has(id)) entries.set(id, {id, count: 0, companies: new Set()});
      const item = entries.get(id);
      item.count++;
      item.companies.add(job.company);
    }
    return [...entries.values()].map(item => ({id: item.id, count: item.count,
      companies: item.companies.size, percent: jobs.length ? Math.round(100 * item.count / jobs.length) : 0}))
      .sort((a, b) => b.count - a.count || a.id.localeCompare(b.id));
  }
  return {today, day, daysTo, recent, field, matches, rows};
})();
if (typeof module !== "undefined") module.exports = JobInsights;
