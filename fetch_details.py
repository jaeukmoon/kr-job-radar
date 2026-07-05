#!/usr/bin/env python3
"""kr-job-radar detail enricher — mine skill/domain trends from each posting's
minimum/preferred qualifications (자격요건/우대사항).

The two fetchers (fetch_jobs.py / fetch_browser.py) only capture listing-level
title/team/tags. This stage reads the finished data/jobs.json, pulls each
posting's real JD qualifications over plain HTTP (endpoints verified per source),
extracts two axes of keywords, and writes them back:

    "domains":      specialized fields present anywhere in the JD (LLM, RL, 로보틱스 …)
    "skills":       concrete tooling present anywhere (Python, PyTorch, SQL …)
    "pref_domains": domains that appear specifically in 우대사항 (preferred)
    "pref_skills":  skills that appear specifically in 우대사항 — the trend headline

Qualification TEXT is cached in data/quals_cache.json keyed by job id, so the
daily run only fetches JDs for newly-seen postings; keyword extraction is
recomputed every run from cached text, so taxonomy edits take effect with no
refetch. Run order: fetch_browser.py -> fetch_jobs.py -> fetch_details.py.
"""
import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from fetch_jobs import http_get, get_json, post_json

ROOT = Path(__file__).parent
DATA = ROOT / "data"
JOBS = DATA / "jobs.json"
CACHE = DATA / "quals_cache.json"
FULL_CAP, PREF_CAP = 6000, 3000  # cache text caps (keyword presence needs no more)


# ------------------------------------------------------------- taxonomy ----
# Two axes. Each entry: id, display name, substring aliases, word aliases.
# "word" is boundary-matched so short/ambiguous tokens (rl, cv, java, go, rag)
# do not hit substrings of unrelated words. Lowercase everywhere.
DOMAINS = [
    {"id": "llm", "name": "LLM/생성형", "substr": [
        "llm", "대규모 언어", "large language", "언어모델", "language model",
        "sllm", "파운데이션 모델", "foundation model", "생성형", "generative ai",
        "genai", "gpt", "프롬프트", "prompt engineer", "파인튜닝", "fine-tun",
        "finetun", "instruction tun", " sft ", "지도학습 미세조정"], "word": []},
    {"id": "agent", "name": "Agent/에이전트", "substr": [
        "에이전트", "langgraph", "autogen", "crewai", "multi-agent",
        "멀티 에이전트", "agentic", "tool use", "tool-calling", "function calling",
        "model context protocol", " mcp ", "autonomous agent", "react agent"],
     "word": ["agent", "agents"]},
    {"id": "rl", "name": "강화학습", "substr": [
        "reinforcement learning", "강화학습", "rlhf", "rlaif", "policy gradient",
        "보상 모델", "reward model", "보상함수", " ppo ", " dpo ", " grpo ",
        "q-learning", "actor-critic", "actor critic"], "word": ["rl"]},
    {"id": "vision", "name": "컴퓨터비전", "substr": [
        "computer vision", "컴퓨터비전", "컴퓨터 비전", "object detection",
        "segmentation", "이미지 인식", "영상 인식", "perception", "3d vision",
        "vision-language", "vlm", "ocr", "얼굴 인식", "face recognition",
        "diffusion model", "stable diffusion", "gaussian splatting"], "word": ["cv"]},
    {"id": "nlp", "name": "자연어처리(NLP)", "substr": [
        "자연어", "natural language process", " nlp", "언어 처리", "텍스트 분석",
        "text mining", "개체명", "named entity"], "word": []},
    {"id": "speech", "name": "음성/오디오", "substr": [
        "음성", "speech", "asr", "tts", "오디오", "audio", "화자",
        "음성 인식", "음성인식", "speech recognition"], "word": []},
    {"id": "recsys", "name": "추천/랭킹", "substr": [
        "추천 시스템", "추천시스템", "recommendation", "recsys", "개인화",
        "personaliz", "ctr", "learning to rank", "검색 랭킹", "ranking model"],
     "word": []},
    {"id": "robotics", "name": "로보틱스/자율주행", "substr": [
        "로보틱스", "robotics", "로봇", "slam", "자율주행", "autonomous driving",
        "manipulation", "manipulator", "motion planning", "모션 플래닝",
        "경로 계획", "제어 알고리즘"], "word": []},
    {"id": "timeseries", "name": "시계열/예측", "substr": [
        "시계열", "time series", "time-series", "forecasting", "수요 예측",
        "수요예측", "demand forecast", "이상 탐지", "이상탐지", "anomaly detection"],
     "word": []},
    {"id": "multimodal", "name": "멀티모달", "substr": [
        "멀티모달", "multimodal", "multi-modal", "vision language", "이미지-텍스트"],
     "word": []},
    {"id": "mlops", "name": "MLOps/서빙", "substr": [
        "mlops", "ml platform", "ml 플랫폼", "모델 서빙", "model serving",
        "inference 최적화", "추론 최적화", "kubeflow", "mlflow", "kserve",
        "triton inference", "모델 배포", "model deployment", "feature store"],
     "word": []},
    {"id": "data-eng", "name": "데이터 엔지니어링", "substr": [
        "데이터 엔지니어", "data engineer", "데이터 파이프라인", "data pipeline",
        "etl", "데이터 플랫폼", "data platform", "lakehouse",
        "데이터 웨어하우스", "data warehouse", "stream processing", "실시간 처리"],
     "word": []},
    {"id": "data-analysis", "name": "데이터 분석", "substr": [
        "데이터 분석", "데이터분석", "data analysis", "data analytics",
        "비즈니스 분석", "business analy", "a/b 테스트", "ab test", "실험 설계",
        "코호트", "퍼널 분석", "product analy", "지표 설계"], "word": []},
]

SKILLS = [
    {"id": "python", "name": "Python", "substr": ["python", "파이썬"], "word": []},
    {"id": "cpp", "name": "C++", "substr": ["c++"], "word": []},
    {"id": "java", "name": "Java", "substr": ["자바"], "word": ["java"]},
    {"id": "javascript", "name": "JS/TS", "substr": [
        "javascript", "typescript", "node.js", "react", "vue"], "word": []},
    {"id": "scala", "name": "Scala", "substr": [], "word": ["scala"]},
    {"id": "go", "name": "Go", "substr": ["golang"], "word": ["go"]},
    {"id": "sql", "name": "SQL", "substr": ["sql"], "word": []},
    {"id": "pytorch", "name": "PyTorch", "substr": ["pytorch", "torch"], "word": []},
    {"id": "tensorflow", "name": "TF/JAX", "substr": ["tensorflow", "keras", "jax"], "word": []},
    {"id": "spark", "name": "Spark", "substr": ["spark"], "word": []},
    {"id": "hadoop", "name": "Hadoop", "substr": ["hadoop", "hdfs", "mapreduce"], "word": []},
    {"id": "kafka", "name": "Kafka", "substr": ["kafka"], "word": []},
    {"id": "airflow", "name": "Airflow", "substr": ["airflow"], "word": []},
    {"id": "flink", "name": "Flink", "substr": ["flink"], "word": []},
    {"id": "k8s", "name": "K8s/Docker", "substr": [
        "kubernetes", "k8s", "docker", "컨테이너", "쿠버네티스"], "word": []},
    {"id": "aws", "name": "AWS", "substr": ["aws", "amazon web"], "word": []},
    {"id": "gcp", "name": "GCP", "substr": ["gcp", "google cloud", "bigquery", "vertex ai"], "word": []},
    {"id": "azure", "name": "Azure", "substr": ["azure"], "word": []},
    {"id": "cuda", "name": "CUDA", "substr": ["cuda"], "word": []},
    {"id": "distributed", "name": "분산학습", "substr": [
        "deepspeed", "fsdp", "megatron", "horovod", "분산 학습",
        "distributed training", "multi-gpu", "멀티 gpu"], "word": []},
    {"id": "vllm", "name": "vLLM/추론엔진", "substr": ["vllm", "tensorrt", "sglang", " tgi "], "word": []},
    {"id": "langchain", "name": "LangChain", "substr": [
        "langchain", "langgraph", "llamaindex", "llama-index"], "word": []},
    {"id": "rag", "name": "RAG", "substr": [
        "retrieval augmented", "검색 증강", "벡터 db", "vector db", "벡터db",
        "embedding search"], "word": ["rag"]},
    {"id": "huggingface", "name": "HuggingFace", "substr": ["huggingface", "hugging face"], "word": []},
    {"id": "tableau", "name": "Tableau", "substr": ["tableau", "태블로"], "word": []},
    {"id": "powerbi", "name": "Power BI", "substr": ["power bi", "powerbi", "파워bi"], "word": []},
    {"id": "spring", "name": "Spring", "substr": ["spring boot", "스프링"], "word": []},
    {"id": "fastapi", "name": "FastAPI/Django", "substr": ["fastapi", "django", "flask"], "word": []},
    {"id": "git", "name": "Git", "substr": ["github", "gitlab", "형상관리", "버전 관리"], "word": ["git"]},
    {"id": "linux", "name": "Linux", "substr": ["linux", "리눅스", "unix"], "word": []},
]

for _tax in (DOMAINS, SKILLS):
    for _c in _tax:
        _c["_re"] = [re.compile(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])")
                     for w in _c["word"]]


def extract(text, tax):
    """Return list of taxonomy ids whose aliases hit the text (lowercased)."""
    hay = " " + text.lower().replace("\n", " ") + " "
    out = []
    for c in tax:
        if any(k in hay for k in c["substr"]) or any(r.search(hay) for r in c["_re"]):
            out.append(c["id"])
    return out


# ----------------------------------------------------------- text utils ----
def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ﻿]+", " ", s)
    s = re.sub(r"\n[ \t]*\n+", "\n", s)
    return s.strip()


PREF_MARKERS = ["우대사항", "우대 사항", "우대조건", "우대 조건", "preferred qualification",
                "이런 분이면 더 좋아요", "이런 분이면 좋아요", "있으면 좋아요"]


def split_min_pref(text):
    """(everything up to the preferred section, preferred section) — best-effort."""
    low = text.lower()
    idx = min((low.find(m) for m in (m.lower() for m in PREF_MARKERS) if low.find(m) != -1),
              default=-1)
    if idx == -1:
        return text, ""
    return text[:idx], text[idx:]


def slice_region(text, starts, ends):
    """Trim page chrome: keep from the first start marker to the first end marker."""
    low = text.lower()
    s = min((low.find(m.lower()) for m in starts if low.find(m.lower()) != -1), default=-1)
    if s == -1:
        return text
    e = min((low.find(m.lower(), s) for m in ends if low.find(m.lower(), s) != -1), default=len(text))
    return text[s:e]


# --------------------------------------------------------- source pulls ----
# Each returns {job_id: (full_text, pref_text)} for bulk sources, or
# (full_text, pref_text) for one posting.
def bulk_kakao(_need):
    out, page = {}, 1
    while True:
        d = get_json("https://careers.kakao.com/public/api/job-list"
                     f"?part=TECHNOLOGY&company=ALL&page={page}")
        for j in d.get("jobList", []):
            jid = f"kakao:{j.get('realId')}"
            if j.get("freeTextFlag"):
                full = strip_html(j.get("introduction") or "")
                pref = split_min_pref(full)[1]
            else:
                qual = strip_html(j.get("qualification") or "")
                duties = strip_html(j.get("workContentDesc") or "")
                full = f"{duties}\n{qual}"
                pref = split_min_pref(qual)[1]
            out[jid] = (full, pref)
        if page >= int(d.get("totalPage") or 1):
            break
        page += 1
        time.sleep(0.4)
    return out


def bulk_kt(_need):
    d = get_json("https://recruit.kt.com/api/recruit"
                 "?isPost=1&isInprogress=1&isContainsContents=1")
    out = {}
    for j in d.get("data", []):
        jid = f"kt:{j.get('recruitNoticeSn')}"
        c = j.get("contents") or ""
        if "<img" in c.lower() and "자격" not in c:  # image-only JD (needs OCR) — skip
            continue
        t = strip_html(c)
        out[jid] = (t, split_min_pref(t)[1])
    return out


def _bulk_greenhouse(board, double):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
    out = {}
    for j in d.get("jobs", []):
        c = html.unescape(j.get("content") or "")
        if double:
            c = html.unescape(c)
        t = strip_html(c)
        out[f"{board}:{j.get('id')}"] = (t, split_min_pref(t)[1])
    return out


def bulk_lgairesearch(_need):
    return _bulk_greenhouse("lgairesearch", double=False)


def bulk_coupang(_need):
    return _bulk_greenhouse("coupang", double=True)  # coupang content is double-escaped


def one_toss(job):
    page = http_get(f"https://toss.im/career/job-detail?job_id={job['id'].split(':', 1)[1]}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    data = json.loads(m.group(1))
    queries = data["props"]["pageProps"]["prefetchResult"]["dehydratedState"]["queries"]
    for q in queries:
        key = q.get("queryKey")
        if isinstance(key, list) and "job-detail" in key:
            state = q.get("state", {}).get("data")
            if isinstance(state, str):
                state = json.loads(state)
            jb = (state or {}).get("job") or {}
            desc = jb.get("description") or ""
            kws = " ".join(jb.get("searchKeywords") or []) + " " + " ".join(jb.get("keywords") or [])
            return (f"{desc} {kws}", split_min_pref(desc)[1])
    return None


def one_hyundai(job):
    ry, rt, rc = job["id"].split(":", 1)[1].split("-")
    d = get_json("https://talent.hyundai.com/api/rec/AP-HM-FO-02800"
                 f"?hgrCd=1&lang=ko&recuYy={ry}&recuType={rt}&recuCls={rc}",
                 headers={"X-HKMC-SERVICE": "HM", "X-HKMC-TOKEN": "null"})
    ai = (d.get("data") or {}).get("applyInfo") or {}
    mn, pr, du = ai.get("privMustReq") or "", ai.get("prefReq") or "", ai.get("privJdDtl") or ""
    return (f"{du}\n{mn}\n{pr}", pr)


def one_samsung(job):
    seq = job["id"].split(":", 1)[1]
    d = get_json(f"https://www.samsungcareers.com/recruit/detail.data?seqno={seq}&strCode=")
    items = (d.get("data") or {}).get("items") or []
    mins = [it.get("qlfctKr") or "" for it in items]
    prefs = [it.get("favorKr") or "" for it in items]
    duties = [it.get("taskKr") or "" for it in items]
    return ("\n".join(duties + mins + prefs), "\n".join(prefs))


def one_woowahan(job):
    seq = job["id"].split(":", 1)[1]
    d = get_json(f"https://career.woowahan.com/w1/recruits/{seq}/info")
    if str(d.get("code")) != "2000":
        return None
    t = strip_html((d.get("data") or {}).get("recruitContents") or "")
    return (t, split_min_pref(t)[1])


def one_naver(job):
    aid = job["id"].split(":", 1)[1]
    t = strip_html(http_get(f"https://recruit.navercorp.com/rcrt/view.do?annoId={aid}"))
    t = slice_region(t, ["필요 역량", "담당 업무", "주요 업무", "역할 및 책임", "자격 요건"],
                     ["전형 절차", "채용 절차", "지원 방법", "기타 사항", "유의 사항"])
    return (t, split_min_pref(t)[1])


def one_lg(job):
    nid = job["id"].split(":", 1)[1]
    d = post_json("https://api.careers.lg.com/rmk/job/retrieveJobNoticesDetail",
                  {"jobNoticeId": nid},
                  headers={"Origin": "https://careers.lg.com", "Referer": "https://careers.lg.com/"})
    recs = ((d.get("data") or {}).get("jobNoticesDetail") or {}).get("recList") or []
    mins = [strip_html(r.get("requiredItem") or "") for r in recs]
    prefs = [strip_html(r.get("preferredItem") or "") for r in recs]
    duties = [strip_html(r.get("detailContext") or "") for r in recs]
    return ("\n".join(duties + mins + prefs), "\n".join(prefs))


def one_sk(job):
    nid = job["id"].split(":", 1)[1]
    t = strip_html(http_get(f"https://www.skcareers.com/Recruit/Detail/{nid}"))
    t = slice_region(t, ["who we're looking for", "지원자격", "자격요건", "담당업무", "what you"],
                     ["how to apply", "전형 절차", "전형절차", "지원 방법", "복리후생", "recruitment process"])
    return (t, split_min_pref(t)[1])


BULK = {"kakao": bulk_kakao, "kt": bulk_kt,
        "lgairesearch": bulk_lgairesearch, "coupang": bulk_coupang}
PER = {"toss": one_toss, "hyundai": one_hyundai, "samsung": one_samsung,
       "woowahan": one_woowahan, "naver": one_naver, "lg": one_lg, "sk": one_sk}


# ---------------------------------------------------------------- main -----
def main():
    if not JOBS.exists():
        print("data/jobs.json not found — run fetch_jobs.py first", file=sys.stderr)
        sys.exit(1)
    doc = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = doc.get("jobs", [])
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    today = date.today().isoformat()
    need_by_source = {}
    for j in jobs:
        if j["id"] not in cache:
            need_by_source.setdefault(j["source"], []).append(j)

    # bulk sources: one (or few) calls cover all their postings
    for src, fn in BULK.items():
        if src not in need_by_source:
            continue
        try:
            idx = fn(need_by_source[src])
            for j in need_by_source[src]:
                full, pref = idx.get(j["id"], ("", ""))
                cache[j["id"]] = {"full": full[:FULL_CAP], "pref": pref[:PREF_CAP], "d": today}
            print(f"[{src}] bulk quals for {len(need_by_source[src])} postings")
        except Exception as e:
            print(f"[{src}] bulk quals ERROR: {e}", file=sys.stderr)

    # per-posting sources: fetch each uncached posting (polite throttle)
    for src, fn in PER.items():
        for j in need_by_source.get(src, []):
            try:
                res = fn(j)
                full, pref = res if res else ("", "")
                cache[j["id"]] = {"full": full[:FULL_CAP], "pref": pref[:PREF_CAP], "d": today}
            except Exception as e:
                print(f"[{src}] {j['id']} quals ERROR: {e}", file=sys.stderr)
            time.sleep(0.3)
        if need_by_source.get(src):
            print(f"[{src}] fetched quals for {len(need_by_source[src])} postings")

    # (re)extract keywords for every job from cached text
    enriched = 0
    for j in jobs:
        c = cache.get(j["id"])
        if not c:
            continue
        full, pref = c.get("full", ""), c.get("pref", "")
        j["domains"] = extract(full, DOMAINS)
        j["skills"] = extract(full, SKILLS)
        j["pref_domains"] = extract(pref, DOMAINS)
        j["pref_skills"] = extract(pref, SKILLS)
        if full:
            enriched += 1

    doc["taxonomy"] = {
        "domains": {c["id"]: c["name"] for c in DOMAINS},
        "skills": {c["id"]: c["name"] for c in SKILLS},
    }
    live = {j["id"] for j in jobs}  # drop cached text for postings that closed
    cache = {k: v for k, v in cache.items() if k in live}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    JOBS.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "jobs.js").write_text(
        "window.JOBS_DATA = " + json.dumps(doc, ensure_ascii=False) + ";", encoding="utf-8")
    print(f"enriched {enriched}/{len(jobs)} jobs with qual keywords -> data/jobs.json, data/jobs.js")


if __name__ == "__main__":
    main()
