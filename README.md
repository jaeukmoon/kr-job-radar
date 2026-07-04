# KR Job Radar

국내 대기업 **AI / ML / 데이터** 직군 채용 공고를 매일 모아 보여주는 정적 사이트.
누구나 자기 CV를 붙여넣어 **브라우저 안에서** 공고별 매칭 점수를 확인할 수 있고,
본인 Claude API 키(BYOK)를 넣으면 AI 적합도 분석·CV 맞춤 제안까지 받을 수 있습니다.

**모든 개인 데이터(CV, API 키)는 브라우저 localStorage에만 저장됩니다.**
서버가 없으며(GitHub Pages 정적 호스팅), AI 기능 사용 시에만 사용자의 브라우저에서
Anthropic API로 직접 요청이 나갑니다. 사이트 운영자는 CV·키에 접근할 수 없습니다.

## 기능

- 공고 대시보드: 회사 필터 · 검색 · NEW 배지(신규 등록) · 마감임박(D-7) 배지 · 다크모드
- CV 매칭: 이력서 텍스트/파일(.txt/.md/.pdf) → 기술 키워드 추출 → 공고별 매칭 % + 매칭순 정렬
- BYOK Claude: 공고별 **AI 적합도 분석**, **CV 맞춤 제안** (키 발급: [console.anthropic.com](https://console.anthropic.com/settings/keys))

## 데이터 소스

**정적 소스** — `fetch_jobs.py` (stdlib만, 공개 JSON API)

| 소스 | 방식 | 커버리지 |
|---|---|---|
| 네이버 (계열사 포함) | recruit.navercorp.com loadJobList.do (GET) | 전체 중 AI/ML/데이터 (Cloud·WEBTOON·SNOW 등 포함) |
| 카카오 (공동체 포함) | careers.kakao.com public JSON API | TECHNOLOGY 직군 중 AI/ML/데이터 |
| 우아한형제들 | career.woowahan.com JSON API | 전체 중 AI/ML/데이터 |
| 토스 (계열사 포함) | api-public.toss.im (Greenhouse 백엔드) | 전체 중 AI/ML/데이터 (토스뱅크·증권 등 포함) |
| LG AI연구원 | Greenhouse boards API | 전체 |
| 쿠팡 | Greenhouse boards API | 한국 근무지 중 AI/ML/데이터 |

**브라우저 소스** — `fetch_browser.py` (Playwright 헤드리스 크롬)

자사 채용 시스템이 비-브라우저 접근을 막아(SK는 AJAX 라우트 WAF, 현대는 NetFunnel 가상대기열,
삼성은 SPA 렌더) 실제 브라우저를 구동해 사이트와 동일한 JSON/DOM을 읽습니다.

| 소스 | 방식 | 커버리지 |
|---|---|---|
| 삼성 (관계사) | samsungcareers.com/hr/ DOM 파싱 | 진행중 공고 중 AI/ML/데이터 (전자·SDS·E&A 등 관계사) |
| 현대자동차 | talent.hyundai.com `/api/rec` (NetFunnel 통과 후) | 전체 중 AI/ML/데이터 (로보틱스랩·반도체 등) |
| SK (계열사) | skcareers.com `/Recruit/GetRecruitList` | 전체 중 AI/ML/데이터 (하이닉스·텔레콤·이노베이션 등) |

갱신: GitHub Actions가 매일 09:00 KST에 `fetch_browser.py`(Playwright) → `fetch_jobs.py`(정적+병합)
순으로 실행 → `data/` 커밋. 브라우저 소스는 `continue-on-error`라 차단돼도 정적 6소스는 계속 갱신되며,
`data/jobs_browser.json`에 마지막 정상 데이터가 유지됩니다.
공고 저장 항목은 제목·회사·근무지·마감일·원문 링크 등 메타데이터만이며(전문 미저장),
상세 내용과 지원은 반드시 원문 링크에서 확인하세요.

### v2 확장 후보 (막힌 지점 메모)

- **카카오뱅크**: Next.js, 목록은 클라이언트 fetch (`__NEXT_DATA__`에 없음)
- **LINE**: Gatsby 정적 쿼리(sq/d/*.json) 해시 추적 필요; greenhouse 보드 없음
- **LG전자·KT**: 자사 채용 시스템(JSP/SPA) — 소스별 리버스엔지니어링 필요

## 로컬 실행

```bash
pip install playwright && python -m playwright install chromium   # 브라우저 소스용 (1회)
python fetch_browser.py       # data/jobs_browser.json (삼성/현대/SK) — 생략 가능
python fetch_jobs.py          # data/jobs.json + data/jobs.js (정적 6소스 + 브라우저 병합)
python -m http.server 8788    # http://localhost:8788
```

`fetch_browser.py`는 생략해도 됩니다(그러면 정적 6소스만). `index.html`을 더블클릭해도
동작합니다(`data/jobs.js`가 JS 전역이라 file://에서도 로드).

## 구조

```
fetch_jobs.py       # stdlib-only 정적 fetcher (6소스 + AI/ML 필터 + first_seen 원장 + 브라우저 병합)
fetch_browser.py    # Playwright fetcher (삼성/현대/SK) -> data/jobs_browser.json
data/jobs.json      # 최종 정규화 공고 데이터 (Actions가 매일 갱신)
data/jobs.js        # 같은 데이터의 JS 전역 버전 (file:// 대응)
data/jobs_browser.json  # 브라우저 소스 중간 산출물 + 마지막 정상 데이터 원장
index.html / app.js / style.css   # 대시보드 + CV 매칭 + BYOK Claude
.github/workflows/fetch.yml       # 일일 자동 갱신 (Playwright 설치 → 브라우저 → 정적+병합)
```

## Disclaimer

본 사이트는 개인 프로젝트이며 각 회사와 무관합니다. 공고 정보의 정확성·최신성은
보장되지 않으니 지원 전 반드시 원문을 확인하세요. AI 분석 결과는 참고용입니다.
