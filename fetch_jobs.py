#!/usr/bin/env python3
"""kr-job-radar fetcher — Korean big-company AI/ML/Data job postings.

stdlib only (urllib/json/re). Each source returns normalized job dicts:
  {id, source, company, title, team, location, employment_type,
   career_type, deadline, url, tags}
`first_seen` is carried over from the previous data/jobs.json so the UI
can show NEW badges. Full JD text is NOT stored (copyright) — title,
metadata and the original link only.

Usage:  python fetch_jobs.py            # writes data/jobs.json + data/jobs.js
        python fetch_jobs.py --source kakao   # run one source (debug)
"""
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

# ------------------------------------------------------------ categories --
# Per-role keyword dictionaries. A posting is tagged with every category
# whose keywords hit its title/tags; postings matching none are dropped.
# "substr" = substring match, "word" = word-boundary match (short tokens
# like "ai"/"ml" would otherwise hit "mail"/"html").
CATEGORIES = [
    {"id": "ml", "name": "ML/딥러닝 엔지니어", "substr": [
        "머신러닝", "기계학습", "딥러닝", "machine learning", "deep learning",
        "인공지능", "pytorch", "tensorflow", "모델 개발", "model develop",
        "ai엔지니어", "ai 엔지니어", "ai engineer", "genai", "generative"],
     "word": ["ai", "ml"]},
    {"id": "research", "name": "AI 연구", "substr": [
        "research scientist", "research engineer", "연구원", "리서치",
        " 연구", "연구 ", "scientist"], "word": []},
    {"id": "llm", "name": "LLM/NLP", "substr": [
        "llm", "nlp", "자연어", "natural language", "언어모델", "language model",
        "챗봇", "chatbot", "rag", "sllm", "파운데이션 모델", "foundation model"],
     "word": []},
    {"id": "vision", "name": "컴퓨터비전", "substr": [
        "컴퓨터비전", "컴퓨터 비전", "computer vision", "이미지 인식", "영상 인식",
        "object detection", "segmentation", "perception", "3d vision"],
     "word": ["cv"]},
    {"id": "data-analysis", "name": "데이터 분석", "substr": [
        "데이터 분석", "데이터분석", "data analy", "analytics", "비즈니스 분석",
        "business analy", "a/b", "실험 설계", "인사이트", "통계", "statistic",
        "bi ", "tableau", "지표"], "word": ["분석"]},
    {"id": "data-eng", "name": "데이터 엔지니어링", "substr": [
        "데이터 엔지니어", "data engineer", "데이터 파이프라인", "data pipeline",
        "etl", "spark", "hadoop", "kafka", "airflow", "데이터 플랫폼",
        "data platform", "dw ", "웨어하우스", "warehouse"], "word": []},
    {"id": "mlops", "name": "MLOps/AI플랫폼", "substr": [
        "mlops", "ml platform", "ml 플랫폼", "모델 서빙", "model serving",
        "serving", "inference", "추론 최적화", "ai 플랫폼", "ai platform",
        "kubeflow", "mlflow"], "word": []},
    {"id": "recsys", "name": "추천/검색", "substr": [
        "추천", "recommendation", "recsys", "검색", "retrieval",
        "ranking", "개인화", "personaliz"], "word": ["search"]},  # "search" as word: avoid "reSEARCHer"
    {"id": "robotics", "name": "로보틱스/자율주행", "substr": [
        "로보틱스", "로봇", "robotics", "slam", "자율주행", "autonomous",
        "control engineer", "manipulator"], "word": []},  # "모빌리티"/"제어" dropped: too broad (mobility-domain false positives)
    {"id": "speech", "name": "음성/오디오", "substr": [
        "음성", "speech", "asr", "tts", "오디오", "audio"], "word": []},
]
for _c in CATEGORIES:
    _c["_word_re"] = [re.compile(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])")
                      for w in _c["word"]]


def categorize(title, tags=()):
    """Return list of category ids matching this posting (empty = drop)."""
    hay = (title + " " + " ".join(tags)).lower()
    out = []
    for c in CATEGORIES:
        if any(k in hay for k in c["substr"]) or any(r.search(hay) for r in c["_word_re"]):
            out.append(c["id"])
    return out


# ------------------------------------------------------------------ http --
def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def get_json(url, **kw):
    return json.loads(http_get(url, **kw))


def pick_name(d, *keys):
    """First non-empty value among keys of a possibly-None dict."""
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return ""


# --------------------------------------------------------------- sources --
def fetch_kakao():
    """careers.kakao.com public JSON API (TECHNOLOGY part)."""
    jobs, page = [], 1
    while True:
        d = get_json(f"https://careers.kakao.com/public/api/job-list"
                     f"?part=TECHNOLOGY&company=ALL&page={page}")
        for j in d.get("jobList", []):
            if j.get("closeFlag"):
                continue
            title = j.get("jobOfferTitle", "")
            tags = [s.get("skillSetName", "") for s in (j.get("skillSetList") or [])
                    if isinstance(s, dict)]
            cats = categorize(title, tags)
            if not cats:
                continue
            deadline = (j.get("resumeSubmissionEndDatetime") or j.get("endDate") or "")[:10]
            jobs.append({
                "id": f"kakao:{j.get('realId')}",
                "source": "kakao",
                "company": j.get("companyName") or "카카오",
                "title": title,
                "team": j.get("jobPartName") or "",
                "location": j.get("locationName") or "",
                "employment_type": j.get("employeeTypeName") or "",
                "career_type": j.get("workTypeName") or "",
                "deadline": deadline or "상시",
                "url": f"https://careers.kakao.com/jobs/{j.get('realId')}",
                "tags": [t for t in tags if t],
                "categories": cats,
            })
        if page >= int(d.get("totalPage") or 1):
            break
        page += 1
        time.sleep(0.5)
    return jobs


def fetch_woowahan():
    """career.woowahan.com (배달의민족/우아한형제들) JSON API."""
    jobs, page = [], 0
    while True:
        d = get_json(f"https://career.woowahan.com/w1/recruits?page={page}&size=100")
        data = d.get("data") or {}
        for j in data.get("list", []):
            title = j.get("recruitName", "")
            group = pick_name(j.get("jobGroup"), "primaryName", "recruitItemName", "name", "text")
            kw = [pick_name(k, "primaryName", "recruitItemName", "name", "text")
                  for k in (j.get("keywords") or [])]
            cats = categorize(title, [group] + kw)
            if not cats:
                continue
            end = (j.get("recruitEndDate") or "")[:10]
            jobs.append({
                "id": f"woowahan:{j.get('recruitSeq')}",
                "source": "woowahan",
                "company": "우아한형제들",
                "title": title,
                "team": group,
                "location": "서울",
                "employment_type": pick_name(j.get("employmentType"),
                                             "primaryName", "recruitItemName", "name", "text"),
                "career_type": pick_name(j.get("careerType"),
                                         "primaryName", "recruitItemName", "name", "text"),
                "deadline": "상시" if end >= "2999" else end,
                "url": f"https://career.woowahan.com/recruitment/{j.get('recruitSeq')}/detail",
                "tags": [k for k in kw if k],
                "categories": cats,
            })
        total_pages = int((data.get("totalPageNumber")) or 1)
        page += 1
        if page >= total_pages:
            break
        time.sleep(0.5)
    return jobs


def fetch_naver():
    """recruit.navercorp.com — GET works (POST is CSRF-blocked).
    Covers NAVER + affiliates (Cloud, LABS, WEBTOON, SNOW, FINANCIAL...)."""
    d = get_json("https://recruit.navercorp.com/rcrt/loadJobList.do"
                 "?firstIndex=0&recordCountPerPage=300")
    jobs = []
    for j in d.get("list", []):
        title = j.get("annoSubject", "")
        sub = j.get("subJobCdNm") or ""
        cls = j.get("classCdNm") or ""
        cats = categorize(title, [sub, cls])
        if not cats:
            continue
        end = (j.get("endYmdTime") or "").replace(".", "-")[:10]
        if end.startswith("2999"):
            deadline = "상시"
        elif end.startswith("2099"):
            deadline = "채용시 마감"
        else:
            deadline = end
        jobs.append({
            "id": f"naver:{j.get('annoId')}",
            "source": "naver",
            "company": j.get("sysCompanyCdNm") or "네이버",
            "title": title,
            "team": " · ".join(x for x in (cls, sub) if x),
            "location": "",
            "employment_type": j.get("empTypeCdNm") or "",
            "career_type": j.get("entTypeCdNm") or "",
            "deadline": deadline,
            "url": f"https://recruit.navercorp.com/rcrt/view.do?annoId={j.get('annoId')}",
            "tags": [],
            "categories": cats,
        })
    return jobs


TOSS_META = {  # Greenhouse custom-field ids used by toss.im career feed
    "category": 24623243003, "company": 4169410003, "employment": 4112432003,
    "deadline": 11431213003, "hidden": 5038345003,
}
TOSS_CAT_MAP = {"ML": "ml", "Data Engineering": "data-eng",
                "Data Analysis": "data-analysis", "R&D": "research"}


def fetch_toss():
    """api-public.toss.im career job-groups (Greenhouse-backed, no auth)."""
    d = get_json("https://api-public.toss.im/api/v3/ipd-eggnog/career/job-groups")
    jobs = []
    for g in d.get("success") or []:
        pj = g.get("primary_job") or {}
        if pj.get("internal_job_id") is None:  # 인재풀/prospect
            continue
        meta = {m.get("id"): m.get("value") for m in (pj.get("metadata") or [])}
        if meta.get(TOSS_META["hidden"]) is True:
            continue
        company = str(meta.get(TOSS_META["company"]) or "토스")
        if company.upper() == "ETC":
            continue
        title = g.get("title") or pj.get("title") or ""
        toss_cat = str(meta.get(TOSS_META["category"]) or "")
        cats = sorted(set(categorize(title, [toss_cat])) |
                      ({TOSS_CAT_MAP[toss_cat]} if toss_cat in TOSS_CAT_MAP else set()))
        if not cats:
            continue
        deadline = str(meta.get(TOSS_META["deadline"]) or "")[:10]
        jobs.append({
            "id": f"toss:{g.get('id')}",
            "source": "toss",
            "company": company,
            "title": title,
            "team": toss_cat,
            "location": ((pj.get("location") or {}).get("name") or ""),
            "employment_type": str(meta.get(TOSS_META["employment"]) or ""),
            "career_type": "",
            "deadline": deadline or "상시",
            "url": pj.get("absolute_url") or f"https://toss.im/career/job-detail?gh_jid={g.get('id')}",
            "tags": [],
            "categories": cats,
        })
    return jobs


def fetch_greenhouse(board, company, korea_only=False):
    """Greenhouse boards API (LG AI연구원, 쿠팡)."""
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
    jobs = []
    for j in d.get("jobs", []):
        title = j.get("title", "")
        loc = (j.get("location") or {}).get("name", "")
        if korea_only and not re.search(r"korea|seoul|korean", loc, re.I):
            continue
        cats = categorize(title)
        if not cats:
            continue
        deadline = (j.get("application_deadline") or "")[:10]
        jobs.append({
            "id": f"{board}:{j.get('id')}",
            "source": board,
            "company": j.get("company_name") or company,
            "title": title,
            "team": "",
            "location": loc,
            "employment_type": "",
            "career_type": "",
            "deadline": deadline or "상시",
            "url": j.get("absolute_url", ""),
            "tags": [],
            "categories": cats,
        })
    return jobs


SOURCES = {
    "naver": fetch_naver,
    "kakao": fetch_kakao,
    "woowahan": fetch_woowahan,
    "toss": fetch_toss,
    "lgairesearch": lambda: fetch_greenhouse("lgairesearch", "LG AI연구원"),
    "coupang": lambda: fetch_greenhouse("coupang", "쿠팡", korea_only=True),
}

# v2 candidates (blocked or needs deeper reverse-engineering; see README):
#   samsung, sk(hynix), lg-electronics, hyundai, kt, line, kakaobank


# ------------------------------------------------------------------ main --
def main():
    only = None
    if "--source" in sys.argv:
        only = sys.argv[sys.argv.index("--source") + 1]

    prev = {}
    prev_path = DATA / "jobs.json"
    if prev_path.exists():
        try:
            for j in json.loads(prev_path.read_text(encoding="utf-8")).get("jobs", []):
                prev[j["id"]] = j.get("first_seen")
        except (json.JSONDecodeError, KeyError):
            pass

    today = date.today().isoformat()
    all_jobs, errors = [], []
    for name, fn in SOURCES.items():
        if only and name != only:
            continue
        try:
            js = fn()
            for j in js:
                j["first_seen"] = prev.get(j["id"]) or today
            all_jobs.extend(js)
            print(f"[{name}] {len(js)} jobs")
        except Exception as e:  # keep other sources alive on one failure
            errors.append(f"{name}: {e}")
            print(f"[{name}] ERROR: {e}", file=sys.stderr)

    # merge browser-fetched sources (Samsung/Hyundai/SK via Playwright), if present.
    # fetch_browser.py writes data/jobs_browser.json in a prior workflow step; if it is
    # absent or blocked this contributes nothing and the static feed stands on its own.
    browser_ok = []
    bpath = DATA / "jobs_browser.json"
    if not only and bpath.exists():
        try:
            bdata = json.loads(bpath.read_text(encoding="utf-8"))
            for j in bdata.get("jobs", []):
                j["first_seen"] = prev.get(j["id"]) or today
                all_jobs.append(j)
            browser_ok = bdata.get("sources_ok", [])
            print(f"[browser] merged {len(bdata.get('jobs', []))} jobs from {browser_ok}")
        except Exception as e:
            print(f"[browser] merge skipped: {e}", file=sys.stderr)

    all_jobs.sort(key=lambda j: (j["first_seen"], j["company"], j["title"]), reverse=True)
    out = {
        "generated": today,
        "sources_ok": [n for n in SOURCES if not only or n == only] + browser_ok,
        "errors": errors,
        "jobs": all_jobs,
    }
    DATA.mkdir(exist_ok=True)
    prev_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "jobs.js").write_text(
        "window.JOBS_DATA = " + json.dumps(out, ensure_ascii=False) + ";",
        encoding="utf-8")
    print(f"total {len(all_jobs)} jobs -> data/jobs.json, data/jobs.js")
    if errors:
        print("errors:", errors, file=sys.stderr)


if __name__ == "__main__":
    main()
