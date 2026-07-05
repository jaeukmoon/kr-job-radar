/* KR Job Radar — dashboard + in-browser CV matching + BYOK Claude */
"use strict";

/* ---------------------------------------------------------- data load -- */
let DATA = window.JOBS_DATA || null;
let jobs = [];
let state = { company: "all", newOnly: false, sort: "recent", search: "",
              trendScope: "pref", trendFilter: null };
let cvSkills = [];          // extracted skill ids from CV
let matchScores = {};       // job id -> {score, hits[]}

async function init() {
  if (!DATA) {
    try { DATA = await (await fetch("data/jobs.json")).json(); }
    catch (e) {
      document.getElementById("jobList").innerHTML =
        '<div class="empty">데이터 로드 실패 — data/jobs.js 생성 후 새로고침하세요.</div>';
      return;
    }
  }
  jobs = DATA.jobs || [];
  document.getElementById("genDate").textContent = DATA.generated || "-";
  renderChips();
  restoreCv();
  render();
}

/* ------------------------------------------------------------ filters -- */
function renderChips() {
  const counts = {};
  for (const j of jobs) counts[j.company] = (counts[j.company] || 0) + 1;
  const box = document.getElementById("companyChips");
  let html = `<button class="chip active" data-c="all">전체 <span class="n">${jobs.length}</span></button>`;
  for (const [c, n] of Object.entries(counts).sort((a, b) => b[1] - a[1])) {
    html += `<button class="chip" data-c="${esc(c)}">${esc(c)} <span class="n">${n}</span></button>`;
  }
  box.innerHTML = html;
  box.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {
    state.company = b.dataset.c;
    box.querySelectorAll(".chip").forEach(x => x.classList.toggle("active", x === b));
    render();
  }));
}

/* -------------------------------------------------------- 채용 트렌드 -- */
/* Aggregates the JD-mined domain/skill fields (data/fetch_details.py) over the
   currently-scoped jobs. Two axes, two scopes: "pref" = 우대사항 only (the trend
   headline — what companies wish for), "all" = 필수+우대. Clicking a bar/tag
   filters the job list; the panel stays computed over baseJobs() so it doesn't
   collapse. Hidden gracefully if jobs.json predates enrichment. */
const TREND_TOP_DOM = 8, TREND_TOP_SK = 16;

function taxName(axis, id) {
  const t = DATA.taxonomy && DATA.taxonomy[axis];
  return (t && t[id]) || id;
}
function trendField(kind) {
  const p = state.trendScope === "pref";
  return kind === "domain" ? (p ? "pref_domains" : "domains")
                           : (p ? "pref_skills" : "skills");
}
function trendCount(list, field) {
  const c = {};
  for (const j of list) for (const id of (j[field] || [])) c[id] = (c[id] || 0) + 1;
  return Object.entries(c).sort((a, b) => b[1] - a[1]);
}
function matchesTrend(j, f) {
  const fields = f.type === "domain" ? ["domains", "pref_domains"] : ["skills", "pref_skills"];
  return fields.some(fl => (j[fl] || []).includes(f.id));
}

function renderTrend() {
  const panel = document.getElementById("trend");
  const enriched = DATA.taxonomy && jobs.some(j => j.domains || j.skills);
  if (!panel || !enriched) { if (panel) panel.hidden = true; return; }
  panel.hidden = false;
  panel.dataset.scope = state.trendScope;

  const list = baseJobs();
  const who = state.company === "all" ? "전체" : state.company;
  const scopeWord = state.trendScope === "pref" ? "우대사항 기준" : "전체 요구사항 기준";
  document.getElementById("domScope").textContent = scopeWord;
  document.getElementById("skScope").textContent = scopeWord;
  document.getElementById("trendSub").innerHTML =
    `<b>${esc(who)}</b> ${list.length}개 공고 · ` +
    (state.trendScope === "pref"
      ? "회사들이 <b>우대</b>하는(=지금 뜨는) 역량"
      : "공고 전체에서 요구되는 역량");

  const dom = trendCount(list, trendField("domain")).slice(0, TREND_TOP_DOM);
  const dmax = dom.length ? dom[0][1] : 1;
  document.getElementById("domBars").innerHTML = dom.map(([id, n]) => {
    const sel = state.trendFilter && state.trendFilter.type === "domain" && state.trendFilter.id === id;
    return `<button type="button" class="bar${sel ? " sel" : ""}" data-ttype="domain" data-tid="${esc(id)}">
      <span class="bar-name">${esc(taxName("domains", id))}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${Math.round(100 * n / dmax)}%"></span></span>
      <span class="bar-n">${n}</span></button>`;
  }).join("") || '<div class="empty" style="padding:14px 0">데이터 없음</div>';

  const sk = trendCount(list, trendField("skill")).slice(0, TREND_TOP_SK);
  const smax = sk.length ? sk[0][1] : 1, smin = sk.length ? sk[sk.length - 1][1] : 1;
  document.getElementById("skillTags").innerHTML = sk.map(([id, n]) => {
    const t = smax === smin ? 1 : (n - smin) / (smax - smin);
    const size = (0.8 + t * 0.42).toFixed(2);
    const sel = state.trendFilter && state.trendFilter.type === "skill" && state.trendFilter.id === id;
    return `<button type="button" class="tag${sel ? " sel" : ""}" data-ttype="skill" data-tid="${esc(id)}"` +
      ` style="font-size:${size}rem">${esc(taxName("skills", id))} <span class="tn">${n}</span></button>`;
  }).join("") || '<div class="empty" style="padding:14px 0">데이터 없음</div>';

  const foot = document.getElementById("trendFoot");
  if (state.trendFilter) {
    const nm = taxName(state.trendFilter.type === "domain" ? "domains" : "skills", state.trendFilter.id);
    foot.innerHTML = `필터: <b style="color:var(--text)">${esc(nm)}</b> 관련 공고만 표시 중 · ` +
      '<button type="button" class="clear" id="trendClear">필터 해제</button>';
    document.getElementById("trendClear").addEventListener("click", () => { state.trendFilter = null; render(); });
  } else {
    foot.textContent = state.trendScope === "pref"
      ? "🔥 우대사항 기준 = 회사들이 '있으면 좋다'고 명시한 역량. 필수요건보다 트렌드에 민감합니다."
      : "전체 요구사항(필수+우대) 기준 분포입니다.";
  }

  panel.querySelectorAll(".bar, .tag").forEach(el => el.addEventListener("click", () => {
    const f = { type: el.dataset.ttype, id: el.dataset.tid };
    state.trendFilter =
      (state.trendFilter && state.trendFilter.type === f.type && state.trendFilter.id === f.id) ? null : f;
    render();
  }));
}

// company + newOnly + search — the pool the trend panel is computed over
// (deliberately excludes trendFilter so clicking a bar doesn't collapse the chart).
function baseJobs() {
  const kw = state.search.toLowerCase();
  return jobs.filter(j =>
    (state.company === "all" || j.company === state.company) &&
    (!state.newOnly || j.first_seen === DATA.generated) &&
    (!kw || (j.title + " " + j.company + " " + (j.tags || []).join(" ")).toLowerCase().includes(kw))
  );
}

function visibleJobs() {
  let list = baseJobs();
  if (state.trendFilter) list = list.filter(j => matchesTrend(j, state.trendFilter));
  if (state.sort === "deadline") {
    list = [...list].sort((a, b) =>
      (a.deadline === "상시" ? "9999" : a.deadline).localeCompare(b.deadline === "상시" ? "9999" : b.deadline));
  } else if (state.sort === "match") {
    list = [...list].sort((a, b) => (matchScores[b.id]?.score || 0) - (matchScores[a.id]?.score || 0));
  } else {
    list = [...list].sort((a, b) => b.first_seen.localeCompare(a.first_seen));
  }
  return list;
}

/* ------------------------------------------------------------- render -- */
function render() {
  renderTrend();
  const list = visibleJobs();
  const out = [];
  const today = DATA.generated;
  for (const j of list) {
    const isNew = j.first_seen === today;
    const dueSoon = j.deadline !== "상시" && j.deadline && daysTo(j.deadline) <= 7 && daysTo(j.deadline) >= 0;
    const m = matchScores[j.id];
    const doms = (j.domains || []).map(id => `<span class="jd">${esc(taxName("domains", id))}</span>`).join("");
    const pset = new Set(j.pref_skills || []);
    const sks = (j.skills || []).slice(0, 6).map(id =>
      `<span class="js${pset.has(id) ? " jp" : ""}">${esc(taxName("skills", id))}</span>`).join("");
    out.push(`<div class="job">
      <div class="row1">
        <span class="company">${esc(j.company)}</span>
        ${isNew ? '<span class="badge new">NEW</span>' : ""}
        ${dueSoon ? `<span class="badge due">마감 D-${daysTo(j.deadline)}</span>` : ""}
        ${m && m.score > 0 ? `<span class="badge match">매칭 ${m.score}%</span>` : ""}
      </div>
      <h3><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></h3>
      <div class="meta">
        ${j.team ? `<span>${esc(j.team)}</span>` : ""}
        ${j.location ? `<span>📍 ${esc(j.location)}</span>` : ""}
        ${j.employment_type ? `<span>${esc(j.employment_type)}</span>` : ""}
        <span>마감 ${esc(j.deadline)}</span>
        <span>등록확인 ${esc(j.first_seen)}</span>
      </div>
      ${m && m.hits.length ? `<div class="mk">${m.hits.map(h => `<span>${esc(h)}</span>`).join("")}</div>` : ""}
      ${(doms || sks) ? `<div class="jtags">${doms}${sks}</div>` : ""}
      <div class="actions">
        <button class="iconbtn" onclick="aiAnalyze('${esc(j.id)}')">AI 적합도 분석</button>
        <button class="iconbtn" onclick="aiTailor('${esc(j.id)}')">CV 맞춤 제안</button>
      </div>
    </div>`);
  }
  document.getElementById("jobList").innerHTML =
    out.join("") || '<div class="empty">조건에 맞는 공고가 없습니다.</div>';
}

function daysTo(d) { return Math.floor((new Date(d) - new Date(DATA.generated)) / 86400000); }
function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* -------------------------------------------------- CV skill matching -- */
/* Skill dictionary: id, display, aliases (lowercase substring match). */
const SKILLS = [
  ["python", "Python", ["python", "파이썬"]],
  ["cpp", "C++", ["c++"]],
  ["java", "Java", ["java ", "java,", "java/", "자바"]],
  ["javascript", "JS/TS", ["javascript", "typescript", "node.js"]],
  ["pytorch", "PyTorch", ["pytorch", "torch"]],
  ["tensorflow", "TensorFlow", ["tensorflow", "keras"]],
  ["ml", "머신러닝", ["machine learning", "머신러닝", "기계학습", " ml "]],
  ["dl", "딥러닝", ["deep learning", "딥러닝", "neural network", "신경망"]],
  ["llm", "LLM", ["llm", "large language", "gpt", "claude", "언어모델", "sllm", "rag", "파인튜닝", "fine-tun", "finetun"]],
  ["nlp", "NLP", ["nlp", "자연어", "natural language"]],
  ["cv", "Computer Vision", ["computer vision", "컴퓨터비전", "컴퓨터 비전", "vision", "이미지 인식", "object detection", "segmentation"]],
  ["rl", "강화학습", ["reinforcement learning", "강화학습", " rl ", "rlhf"]],
  ["timeseries", "시계열", ["time series", "time-series", "시계열", "forecasting", "예측 모델"]],
  ["recsys", "추천시스템", ["recommendation", "recsys", "추천"]],
  ["search", "검색", ["search", "검색", "retrieval", "ranking"]],
  ["speech", "음성", ["speech", "음성", "asr", "tts", "audio"]],
  ["robotics", "로보틱스", ["robotics", "로보틱스", "로봇", "slam", "자율주행", "autonomous"]],
  ["mlops", "MLOps", ["mlops", "kubeflow", "mlflow", "model serving", "모델 서빙", "sagemaker", "vertex"]],
  ["data-eng", "데이터 엔지니어링", ["data engineer", "데이터 엔지니어", "etl", "airflow", "spark", "hadoop", "kafka", "데이터 파이프라인", "data pipeline"]],
  ["data-analysis", "데이터 분석", ["data analy", "데이터 분석", "데이터분석", "a/b test", "ab test", "통계", "statistics", "bi ", "tableau", "looker"]],
  ["sql", "SQL/DB", ["sql", "database", "bigquery", "redshift", "snowflake"]],
  ["cloud", "클라우드", ["aws", "gcp", "azure", "cloud", "클라우드"]],
  ["k8s", "Docker/K8s", ["kubernetes", "k8s", "docker", "컨테이너"]],
  ["distributed", "분산학습", ["distributed", "분산", "multi-gpu", "deepspeed", "fsdp", "megatron", "slurm"]],
  ["research", "연구/논문", ["research", "논문", "paper", "publication", "phd", "박사", "석사", "neurips", "icml", "cvpr", "acl", "aaai"]],
  ["backend", "백엔드", ["backend", "백엔드", "server", "서버 개발", "api 개발", "spring", "django", "fastapi"]],
  ["frontend", "프론트엔드", ["frontend", "프론트엔드", "react", "vue"]],
];

function extractSkills(text) {
  const hay = " " + text.toLowerCase().replace(/\s+/g, " ") + " ";
  return SKILLS.filter(([, , aliases]) => aliases.some(a => hay.includes(a))).map(([id]) => id);
}

function scoreJobs() {
  matchScores = {};
  if (!cvSkills.length) return;
  for (const j of jobs) {
    const jobText = (j.title + " " + (j.tags || []).join(" ") + " " + j.team).toLowerCase();
    const jobSkills = SKILLS.filter(([, , aliases]) => aliases.some(a => jobText.includes(a)));
    if (!jobSkills.length) { matchScores[j.id] = { score: 0, hits: [] }; continue; }
    const hits = jobSkills.filter(([id]) => cvSkills.includes(id));
    matchScores[j.id] = {
      score: Math.round(100 * hits.length / jobSkills.length),
      hits: hits.map(([, name]) => name),
    };
  }
}

function applyCv() {
  const text = document.getElementById("cvText").value.trim();
  if (!text) { alert("이력서 텍스트를 먼저 입력하세요."); return; }
  localStorage.setItem("kjr_cv", text);
  cvSkills = extractSkills(text);
  document.getElementById("cvSkills").innerHTML =
    cvSkills.length
      ? cvSkills.map(id => `<span>${esc(SKILLS.find(s => s[0] === id)[1])}</span>`).join("")
      : '<span style="background:none;color:var(--muted)">인식된 기술 키워드 없음 — 기술 스택을 CV에 명시해보세요</span>';
  scoreJobs();
  document.getElementById("sortMatch").style.display = "";
  setSort("match");
}

function restoreCv() {
  const saved = localStorage.getItem("kjr_cv");
  if (saved) {
    document.getElementById("cvText").value = saved;
    cvSkills = extractSkills(saved);
    if (cvSkills.length) {
      document.getElementById("cvSkills").innerHTML =
        cvSkills.map(id => `<span>${esc(SKILLS.find(s => s[0] === id)[1])}</span>`).join("");
      scoreJobs();
      document.getElementById("sortMatch").style.display = "";
    }
  }
}

/* ------------------------------------------------------- file upload -- */
async function readCvFile(file) {
  if (file.name.toLowerCase().endsWith(".pdf")) {
    try {
      if (!window.pdfjsLib) await loadPdfJs();
      const buf = await file.arrayBuffer();
      const pdf = await window.pdfjsLib.getDocument({ data: buf }).promise;
      let text = "";
      for (let p = 1; p <= pdf.numPages; p++) {
        const content = await (await pdf.getPage(p)).getTextContent();
        text += content.items.map(i => i.str).join(" ") + "\n";
      }
      return text;
    } catch (e) {
      alert("PDF 파싱 실패 (오프라인이거나 스캔본일 수 있음). 텍스트를 직접 붙여넣어주세요.");
      throw e;
    }
  }
  return file.text();
}

function loadPdfJs() {
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
    s.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
      res();
    };
    s.onerror = rej;
    document.head.appendChild(s);
  });
}

/* ------------------------------------------------------- BYOK Claude -- */
function apiConfig() {
  return {
    key: localStorage.getItem("kjr_api_key") || "",
    model: localStorage.getItem("kjr_api_model") || "claude-sonnet-4-6",
  };
}

async function callClaude(system, user) {
  const { key, model } = apiConfig();
  if (!key) {
    openModal("settingsModal");
    throw new Error("no-key");
  }
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model, max_tokens: 1500, system,
      messages: [{ role: "user", content: user }],
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`API ${res.status}: ${t.slice(0, 300)}`);
  }
  const d = await res.json();
  return d.content.map(c => c.text || "").join("");
}

function jobById(id) { return jobs.find(j => j.id === id); }

function jobBrief(j) {
  return `회사: ${j.company}\n공고 제목: ${j.title}\n` +
    (j.team ? `조직: ${j.team}\n` : "") +
    (j.location ? `근무지: ${j.location}\n` : "") +
    `마감: ${j.deadline}\n원문: ${j.url}`;
}

async function aiRun(title, system, user) {
  document.getElementById("aiTitle").textContent = title;
  document.getElementById("aiOut").innerHTML = '<span class="spin">◌</span> 분석 중...';
  openModal("aiModal");
  try {
    const out = await callClaude(system, user);
    document.getElementById("aiOut").textContent = out;
  } catch (e) {
    if (e.message === "no-key") { closeModal("aiModal"); return; }
    document.getElementById("aiOut").textContent = "오류: " + e.message;
  }
}

window.aiAnalyze = function (id) {
  const j = jobById(id);
  const cv = document.getElementById("cvText").value.trim();
  if (!cv) { alert("좌측 CV 패널에 이력서를 먼저 입력하세요."); return; }
  aiRun(`AI 적합도 분석 — ${j.company}`,
    "당신은 한국 대기업 채용 전문 커리어 코치입니다. 지원자의 CV와 공고 정보를 보고 적합도를 냉정하게 평가하세요. 공고 제목/회사에서 유추되는 요구역량 기준으로 (1) 적합도 점수(0~100)와 근거, (2) 강점 3개, (3) 부족한 부분과 보완 방법, (4) 서류 통과 확률을 높일 핵심 어필 포인트를 한국어로 간결히 답하세요.",
    `[공고]\n${jobBrief(j)}\n\n[지원자 CV]\n${cv.slice(0, 8000)}`);
};

window.aiTailor = function (id) {
  const j = jobById(id);
  const cv = document.getElementById("cvText").value.trim();
  if (!cv) { alert("좌측 CV 패널에 이력서를 먼저 입력하세요."); return; }
  aiRun(`CV 맞춤 제안 — ${j.company}`,
    "당신은 한국 대기업 서류전형에 정통한 이력서 컨설턴트입니다. 아래 공고에 맞춰 CV를 어떻게 수정할지 제안하세요: (1) 이 공고에 맞게 강조 순서를 바꿀 항목, (2) 문장 단위 수정 제안 3~5개 (원문 → 수정문 형식), (3) 추가하면 좋을 키워드, (4) 삭제/축소할 항목. 사실을 지어내지 말고 CV에 있는 내용만 재구성하세요. 한국어로 답하세요.",
    `[공고]\n${jobBrief(j)}\n\n[현재 CV]\n${cv.slice(0, 8000)}`);
};

/* -------------------------------------------------------------- modal -- */
function openModal(id) { document.getElementById(id).classList.add("open"); }
function closeModal(id) { document.getElementById(id).classList.remove("open"); }

/* --------------------------------------------------------- listeners -- */
function setSort(mode) {
  state.sort = mode;
  document.getElementById("sortDeadline").classList.toggle("active", mode === "deadline");
  document.getElementById("sortMatch").classList.toggle("active", mode === "match");
  render();
}

document.getElementById("search").addEventListener("input", e => { state.search = e.target.value; render(); });
document.getElementById("newOnly").addEventListener("click", e => {
  state.newOnly = !state.newOnly; e.target.classList.toggle("active", state.newOnly); render();
});
document.getElementById("sortDeadline").addEventListener("click", () =>
  setSort(state.sort === "deadline" ? "recent" : "deadline"));
document.getElementById("sortMatch").addEventListener("click", () =>
  setSort(state.sort === "match" ? "recent" : "match"));

document.querySelectorAll("#trend .seg button").forEach(b => b.addEventListener("click", () => {
  state.trendScope = b.dataset.scope;
  state.trendFilter = null;
  document.querySelectorAll("#trend .seg button").forEach(x => x.classList.toggle("active", x === b));
  render();
}));

document.getElementById("cvApply").addEventListener("click", applyCv);
document.getElementById("cvClear").addEventListener("click", () => {
  document.getElementById("cvText").value = "";
  document.getElementById("cvSkills").innerHTML = "";
  localStorage.removeItem("kjr_cv");
  cvSkills = []; matchScores = {};
  document.getElementById("sortMatch").style.display = "none";
  setSort("recent");
});
document.getElementById("cvFileBtn").addEventListener("click", () => document.getElementById("cvFile").click());
document.getElementById("cvFile").addEventListener("change", async e => {
  if (!e.target.files[0]) return;
  try {
    document.getElementById("cvText").value = await readCvFile(e.target.files[0]);
    applyCv();
  } catch (err) { /* alert shown in readCvFile */ }
});

document.getElementById("settingsBtn").addEventListener("click", () => {
  document.getElementById("apiKey").value = apiConfig().key;
  document.getElementById("apiModel").value = apiConfig().model;
  openModal("settingsModal");
});
document.getElementById("settingsSave").addEventListener("click", () => {
  localStorage.setItem("kjr_api_key", document.getElementById("apiKey").value.trim());
  localStorage.setItem("kjr_api_model", document.getElementById("apiModel").value);
  closeModal("settingsModal");
});
document.getElementById("settingsClose").addEventListener("click", () => closeModal("settingsModal"));
document.getElementById("aiClose").addEventListener("click", () => closeModal("aiModal"));
document.getElementById("aiCopy").addEventListener("click", () =>
  navigator.clipboard.writeText(document.getElementById("aiOut").textContent));
document.querySelectorAll(".modal-back").forEach(m =>
  m.addEventListener("click", e => { if (e.target === m) m.classList.remove("open"); }));

document.getElementById("themeToggle").addEventListener("click", () => {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "" : "dark";
  if (next) root.dataset.theme = next; else delete root.dataset.theme;
  localStorage.setItem("kjr_theme", next);
});
if (localStorage.getItem("kjr_theme") === "dark") document.documentElement.dataset.theme = "dark";

/* -------------------------------------------------------- issues tab -- */
/* Backend-free reporting: a submission opens a prefilled GitHub "new issue"
   page (uses the visitor's own GitHub session, no token needed); the list is
   read back from the public GitHub REST API and filtered by the [제보] title. */
const REPO = "jaeukmoon/kr-job-radar";
let issuesLoaded = false;

function switchView(view) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.view === view));
  document.getElementById("jobsView").hidden = view !== "jobs";
  document.getElementById("issuesView").hidden = view !== "issues";
  if (view === "issues" && !issuesLoaded) loadIssues();
}

function submitIssue() {
  const type = document.getElementById("issueType").value;
  const title = document.getElementById("issueTitle").value.trim();
  const ref = document.getElementById("issueRef").value.trim();
  const body = document.getElementById("issueBody").value.trim();
  if (!title) { alert("제목을 입력하세요."); return; }
  const fullTitle = `[제보] [${type}] ${title}`;
  const fullBody =
    `**유형**: ${type}\n` +
    (ref ? `**관련 회사/링크**: ${ref}\n` : "") +
    `\n${body || "(내용 없음)"}\n\n---\nKR Job Radar 제보 폼에서 작성됨`;
  const url = `https://github.com/${REPO}/issues/new` +
    `?title=${encodeURIComponent(fullTitle)}` +
    `&body=${encodeURIComponent(fullBody)}`;
  window.open(url, "_blank", "noopener");
}

async function loadIssues() {
  const box = document.getElementById("issueList");
  box.innerHTML = '<div class="empty">불러오는 중...</div>';
  try {
    const res = await fetch(
      `https://api.github.com/repos/${REPO}/issues?state=all&per_page=50&sort=created&direction=desc`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) throw new Error(`GitHub API ${res.status}`);
    const all = await res.json();
    const reports = all.filter(i => !i.pull_request && (i.title || "").startsWith("[제보]"));
    issuesLoaded = true;
    if (!reports.length) {
      box.innerHTML = '<div class="empty">아직 접수된 제보가 없습니다. 첫 제보를 남겨주세요.</div>';
      return;
    }
    box.innerHTML = reports.map(i => {
      const open = i.state === "open";
      const date = (i.created_at || "").slice(0, 10);
      const title = i.title.replace(/^\[제보\]\s*/, "");
      return `<div class="issue">
        <div class="row1">
          <span class="badge ${open ? "st-open" : "st-closed"}">${open ? "접수" : "처리완료"}</span>
          <span class="issue-date">${esc(date)}</span>
          ${i.comments ? `<span class="issue-cmt">💬 ${i.comments}</span>` : ""}
        </div>
        <h3><a href="${esc(i.html_url)}" target="_blank" rel="noopener">${esc(title)}</a></h3>
        <div class="meta">by ${esc(i.user && i.user.login || "?")}</div>
      </div>`;
    }).join("");
  } catch (e) {
    box.innerHTML =
      `<div class="empty">제보 목록을 불러오지 못했습니다 (${esc(e.message)}).<br>` +
      `GitHub API 시간당 요청 한도(60회)일 수 있습니다. 잠시 후 새로고침하세요.</div>`;
  }
}

document.querySelectorAll(".tab").forEach(t =>
  t.addEventListener("click", () => switchView(t.dataset.view)));
document.getElementById("issueSubmit").addEventListener("click", submitIssue);
document.getElementById("issueRefresh").addEventListener("click", () => { issuesLoaded = false; loadIssues(); });

init();
