"""Extract explicit graduate-degree mentions without inferring eligibility.

Section labels describe where a degree is mentioned. Alternatives such as a
degree OR equivalent experience are preserved verbatim, not treated as mandatory.
Unrecognized sections remain unclassified; missing text is never degree-free.
"""
import html
import re

DEGREES = {
    "masters": re.compile(r"석\s*(?:[·/ㆍ・]?\s*박\s*)?사|(?<![a-z])master(?:['’]s|s)\b|\bmaster\s+(?:of\s+(?:science|arts|engineering)|degree)\b|(?<![a-z])(?:m\.\s*s\.|m\.?\s*(?:sc|eng)\.?|ms(?=\s+(?:degree|in|or)\b|[/,]))(?![a-z])", re.I),
    "phd": re.compile(r"박\s*사|(?<![a-z])ph\.?\s*d\.?(?![a-z])|\bdoctor(?:al|ate)\b|\bd\.?\s*phil\.?(?![a-z])", re.I),
}
HEADINGS = {
    "preferred": r"우대\s*(?:사항|조건|요건)|preferred qualifications?|preferred requirements?|nice[- ]to[- ]have(?:s)?|ways to stand out|이런 (?:분이면|경험이 있으면|경험이 있다면|경험을 가진 분이면|경험도 있다면) (?:더 )?(?:좋아요|잘 맞아요)|이런 분을 우대해요|있으면 좋아요|bonus (?:points|qualifications)",
    "required": r"(?:기본|최소|필수)\s*(?:자격|요건|사항)(?:\s*요건)?|자격\s*요건|지원\s*자격|필요\s*역량|학력\s*(?:사항|요건)|minimum qualifications?|basic qualifications?|required qualifications?|qualifications?|requirements|what (?:we need to see|you bring|we look for)|who (?:you are|we['’]re looking for)|이런 분(?:과|을) (?:함께하고 싶어요|찾고 있어요|찾아요)|이런 경험을 가진 분을 찾고 있어요",
    "stop": r"(?:주요|담당)\s*업무|업무\s*내용|전형\s*절차|채용\s*절차|지원\s*방법|유의\s*사항|복리\s*후생|혜택|benefits|responsibilities|what you['’]ll do|about (?:us|the team|the role)|compensation|equal (?:employment )?opportunity|합류하면 (?:함께|이런)",
}
HEADER = re.compile(r"(?:^|\n)\s*[#*■✦•\[\] :\-]*(?P<label>" + "|".join(
    f"(?P<{key}>{value})" for key, value in HEADINGS.items()) + r")[ \t*:\]—-]*(?=\n|$|[^a-zA-Z가-힣])", re.I)


def clean(text):
    text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6])>", "\n", text or "")
    return html.unescape(re.sub(r"<[^>]*>", " ", text)).replace("\r", "")


def sections(text):
    result = {"required": [], "preferred": []}
    marks = list(HEADER.finditer(text))
    for index, mark in enumerate(marks):
        kind = next(key for key in HEADINGS if mark.group(key))
        if kind == "stop":
            continue
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        result[kind].append(text[mark.end():end].strip())
    return {key: "\n".join(values) for key, values in result.items()}


def mentions(text):
    found = []
    for line in text.splitlines():
        line = " ".join(line.split()).strip("#*•- ")
        for degree, pattern in DEGREES.items():
            match = pattern.search(line)
            if not match:
                continue
            # Preserve the clause around the match, including OR/experience
            # alternatives, even when a source provides one very long line.
            start = max(0, match.start() - 140)
            end = min(len(line), max(match.end() + 220, start + 360))
            evidence = ("…" if start else "") + line[start:end] + ("…" if end < len(line) else "")
            item = {"degree": degree, "text": evidence}
            if item not in found:
                found.append(item)
    return found


def extract_degrees(full, required=None, preferred=None):
    full = clean(full)
    parsed = sections(full)
    required = clean(required) if required is not None else parsed["required"]
    preferred = parsed["preferred"] or (clean(preferred) if preferred is not None else "")
    result = {"required": mentions(required), "preferred": mentions(preferred), "unclassified": []}
    # Classify only evidence explicitly located in a known section. Body/title
    # mentions must not leak into either qualifications filter.
    covered = " ".join((required + " " + preferred).split())
    for item in mentions(full):
        if item["text"].strip("…") not in covered and not any(
                item["degree"] == hit["degree"] and item["text"] in hit["text"]
                for key in ("required", "preferred") for hit in result[key]):
            result["unclassified"].append(item)
    result["available"] = bool(full.strip() or required.strip() or preferred.strip())
    return result


def attach_degrees(job):
    source = job.get("scoring_input") or {}
    full = source.get("description") or job.get("scoring_description") or job.get("description") or ""
    quals = source.get("quals") or job.get("quals") or {}
    parsed = sections(clean(full))
    # Heading-aware full inputs avoid the historical qualification storage cap.
    job["degree_requirements"] = extract_degrees(full,
        required=parsed["required"] or quals.get("required") or None,
        preferred=parsed["preferred"] or quals.get("preferred") or None)
    return job
