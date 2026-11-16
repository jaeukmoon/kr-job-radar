/* Explicit mentions, not minimum-degree or hiring-eligibility inference. */
(function (root) {
  "use strict";
  const sections = {required: "기본 자격", preferred: "우대사항", unclassified: "본문·구분 미확인"};
  const degrees = {masters: "석사", phd: "박사"};
  function entries(job, section = "all") {
    const data = job.degree_requirements || {};
    return Object.keys(sections).filter(key => section === "all" || key === section)
      .flatMap(key => (data[key] || []).map(hit => ({...hit, section: key})));
  }
  function matches(job, degree = "all", section = "all") {
    if (degree === "all" && section === "all") return true;
    return entries(job, section).some(hit => degree === "all" || degree === "graduate" || hit.degree === degree);
  }
  function markup(job, escape) {
    const hits = entries(job);
    if (!hits.length) return '<div class="degree-note">학위: ' +
      (job.degree_requirements?.available ? "확보한 원문에서 석사·박사 언급 미검출" : "원문 미확보") + '</div>';
    return '<details class="degree-evidence"><summary>' + [...new Set(hits.map(hit =>
      `${sections[hit.section]} ${degrees[hit.degree]}`))].map(escape).join(" · ") + '</summary>' +
      hits.map(hit => `<p><b>${sections[hit.section]} · ${degrees[hit.degree]}</b> ${escape(hit.text)}</p>`).join("") + '</details>';
  }
  const api = {entries, matches, markup};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.DegreeFilters = api;
})(typeof window !== "undefined" ? window : globalThis);
