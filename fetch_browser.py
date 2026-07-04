#!/usr/bin/env python3
"""kr-job-radar browser fetcher — Samsung / Hyundai / SK (headless Playwright).

These three run their career sites behind bot-protection that blocks plain
HTTP clients: SK's AJAX routes are WAF-gated, Hyundai sits behind a NetFunnel
virtual-waiting-room queue, and Samsung renders postings only after its SPA
runs. A real browser passes all three, so we drive one with Playwright and read
the same JSON/DOM the site shows a visitor. Output schema matches fetch_jobs.py.

Writes data/jobs_browser.json (its own ledger of the 3 sources). fetch_jobs.py
merges this file into the final data/jobs.json, so if this fetcher is blocked or
absent the static 6-source feed still updates. Each source is isolated: one
failing does not drop the others, and on a source error the previous file's
entries for that source are carried over so a transient block does not wipe data.

Usage:  python fetch_browser.py            # writes data/jobs_browser.json
        python fetch_browser.py --debug    # + dumps raw samples for tuning
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

# reuse the same AI/ML/Data category filter as the static fetcher
from fetch_jobs import categorize

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "jobs_browser.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DEBUG = "--debug" in sys.argv


def to_iso(s):
    """'2026년 07월 05일(일)' / '20260706' / '2026.07.15' -> '2026-07-05'."""
    if not s:
        return ""
    nums = re.findall(r"\d+", str(s))
    if len(nums) >= 3:
        y, m, d = nums[0], nums[1], nums[2]
        if len(y) == 4:
            return f"{y}-{int(m):02d}-{int(d):02d}"
    if len(nums) == 1 and len(nums[0]) == 8:  # 20260706
        v = nums[0]
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return ""


# --------------------------------------------------------------- SK --------
def fetch_sk(ctx):
    """skcareers.com Recruit/GetRecruitList — fires on page load; capture it."""
    page = ctx.new_page()
    captured = {}
    page.on("response", lambda r: captured.__setitem__(
        "list", r) if "GetRecruitList" in r.url else None)
    page.goto("https://www.skcareers.com/Recruit/", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3500)
    resp = captured.get("list")
    data = json.loads(resp.text()) if resp else {}
    page.close()
    out = []
    for j in data.get("list", []):
        title = j.get("title", "")
        role = j.get("jobRole", "")
        cats = categorize(title, [role])
        if not cats:
            continue
        nid = j.get("noticeID")
        out.append({
            "id": f"sk:{nid}",
            "source": "sk",
            "company": j.get("corpName") or "SK",
            "title": title,
            "team": role,
            "location": j.get("workingArea") or "",
            "employment_type": j.get("workingType") or "",
            "career_type": j.get("recruitType") or "",
            "deadline": to_iso(j.get("end")) or "상시",
            "url": f"https://www.skcareers.com/Recruit/Detail/{nid}",
            "tags": [],
            "categories": cats,
        })
    return out


# ------------------------------------------------------------ HYUNDAI ------
HY_LIST = ("https://talent.hyundai.com/api/rec/AP-HM-FO-02700"
           "?hgrCd=1&lang=ko&page=1&pageblock=300"
           "&searchType=&searchText=&searchFieldList=&searchOccupList="
           "&searchSecList=&searchPlaceList=&searchBrandList=&sortDataTagArray=")


def fetch_hyundai(ctx):
    """talent.hyundai.com — pass NetFunnel via the Jobs page, then fetch list API."""
    page = ctx.new_page()
    page.goto("https://talent.hyundai.com/", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    try:
        page.click("text=Jobs", timeout=6000)   # navigates to applyList.hc (netfunnel token)
        page.wait_for_timeout(5000)
    except Exception:
        pass
    # fetch the full paginated list from within the page (cookies/netfunnel apply)
    data = page.evaluate(
        """async (u) => { const r = await fetch(u, {headers:{'Accept':'application/json'}});
                          return await r.json(); }""", HY_LIST)
    page.close()
    rows = ((data or {}).get("data") or {}).get("list") or []
    out = []
    for j in rows:
        title = j.get("recuNoticeNm") or ""
        fld = j.get("fldCodeNm") or ""
        cate = j.get("jdRecuCateNm") or ""
        htag = j.get("hashTag") or ""
        cats = categorize(title, [fld, cate, htag])
        if not cats:
            continue
        ry, rt, rc = j.get("recuYy"), j.get("recuType"), j.get("recuCls")
        sec = j.get("secCodeNm") or ""  # job sector (IT/생산·제조/…), not the company
        out.append({
            "id": f"hyundai:{ry}-{rt}-{rc}",
            "source": "hyundai",
            "company": "현대자동차",
            "title": title,
            "team": " · ".join(x for x in (sec, fld) if x),
            "location": j.get("workPlaceCodeNm") or "",
            "employment_type": j.get("codeKnm") or "",
            "career_type": "",
            "deadline": to_iso(j.get("applyEndDt")) or "상시",
            "url": (f"https://talent.hyundai.com/apply/applyView.hc"
                    f"?recuYy={ry}&recuType={rt}&recuCls={rc}"),
            "tags": [t for t in [htag] if t],
            "categories": cats,
        })
    return out


# ------------------------------------------------------------- SAMSUNG -----
def fetch_samsung(ctx):
    """samsungcareers.com/hr/ — postings are SPA-rendered into the DOM; parse cards.

    Each posting card is an <a data-value="{seqno}"> holding .company/.title/.period.
    Titles are batch postings (e.g. "경력사원 채용(설계, Data분석, AI/Data Governance...)")
    so the category filter matches on the whole title. Detail links are JS-routed
    (href="/#none"); the site opens them from the /hr/ list, so that is the link.
    """
    page = ctx.new_page()
    page.goto("https://www.samsungcareers.com/hr/", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)
    page.mouse.wheel(0, 2000)
    page.wait_for_timeout(2500)
    cards = page.evaluate(r"""() => {
        const out = [], seen = new Set();
        for (const a of document.querySelectorAll('a[data-value]')) {
            const comp = a.querySelector('.company'), title = a.querySelector('.title');
            if (!comp || !title) continue;
            const period = a.querySelector('.period');
            const seq = (a.getAttribute('data-value') || '').replace(/[^0-9]/g, '');
            const key = seq + '|' + title.innerText.trim();
            if (seen.has(key)) continue; seen.add(key);
            out.push({company: comp.innerText.trim(), title: title.innerText.trim(),
                      period: period ? period.innerText.trim() : '', seq});
        }
        return out;
    }""")
    if DEBUG:
        print("  [samsung debug] raw cards:", json.dumps(cards, ensure_ascii=False)[:1500])
    page.close()
    out = []
    for c in cards:
        title = c["title"]
        cats = categorize(title)
        if not cats:
            continue
        mend = re.search(r"~\s*(\d{4}[.\-]\d{2}[.\-]\d{2})", c["period"])
        out.append({
            "id": f"samsung:{c['seq']}",
            "source": "samsung",
            "company": c["company"] or "삼성",
            "title": title,
            "team": "",
            "location": "",
            "employment_type": "",
            "career_type": "",
            "deadline": to_iso(mend.group(1)) if mend else "상시",
            "url": "https://www.samsungcareers.com/hr/",
            "tags": [],
            "categories": cats,
        })
    return out


SOURCES = {"sk": fetch_sk, "hyundai": fetch_hyundai, "samsung": fetch_samsung}


def main():
    only = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else None
    today = date.today().isoformat()
    # carry-over previous entries per source (so a transient block keeps last-good)
    prev_by_source = {}
    if OUT.exists():
        try:
            for j in json.loads(OUT.read_text(encoding="utf-8")).get("jobs", []):
                prev_by_source.setdefault(j["source"], []).append(j)
        except Exception:
            pass

    all_jobs, errors, ok = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="ko-KR",
                                  viewport={"width": 1366, "height": 900})
        for name, fn in SOURCES.items():
            if only and name != only:
                continue
            try:
                js = fn(ctx)
                if not js and prev_by_source.get(name):
                    raise RuntimeError("0 jobs returned")
                all_jobs.extend(js)
                ok.append(name)
                print(f"[{name}] {len(js)} jobs")
            except Exception as e:
                errors.append(f"{name}: {e}")
                print(f"[{name}] ERROR: {e}", file=sys.stderr)
                all_jobs.extend(prev_by_source.get(name, []))  # keep last-good
        browser.close()

    out = {"generated": today, "sources_ok": ok, "errors": errors, "jobs": all_jobs}
    DATA.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"total {len(all_jobs)} jobs -> {OUT.name}  (ok={ok}, errors={len(errors)})")


if __name__ == "__main__":
    main()
