"""
Parser for the AI stock research report text.

Pure, dependency-free (stdlib `re`). Turns the model's structured Markdown-ish
report into sections + a bias + any key price levels, so the Stock Analysis
page can render a structured interface. **Never invents content**: if parsing
finds nothing structured, the caller keeps the original raw text and the raw
text is always preserved in the returned dict.

This only reformats the AI's own words for display; it does not compute or
infer any market facts.
"""

from __future__ import annotations

import re

_HEADING_HASH = re.compile(r"^\s*#{1,6}\s*(.+?)\s*:?\s*$")
_HEADING_NUM = re.compile(r"^\s*\d+[).]\s*(.+?)\s*:?\s*$")
_TITLE_COLON = re.compile(r"^\s*([A-Za-z][A-Za-z /&-]{2,40}):\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[).])\s+")
_DISCLAIMER = "AI-generated analysis based on available market data"
_PREAMBLE = ("NOVA STOCK ANALYSIS", "Mode:")
_BIAS_MARKERS = (
    "INSUFFICIENT EVIDENCE",
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "MIXED",
)
_LEVEL_PATTERNS = {
    "r2": re.compile(r"(?:resistance\s*2|r2)\D{0,4}([\d,]+(?:\.\d+)?)", re.I),
    "r1": re.compile(r"(?:resistance\s*1|r1)\D{0,4}([\d,]+(?:\.\d+)?)", re.I),
    "p": re.compile(r"(?:current(?:\s*price)?|spot)\D{0,4}([\d,]+(?:\.\d+)?)", re.I),
    "s1": re.compile(r"(?:support\s*1|s1)\D{0,4}([\d,]+(?:\.\d+)?)", re.I),
    "s2": re.compile(r"(?:support\s*2|s2)\D{0,4}([\d,]+(?:\.\d+)?)", re.I),
}


def _clean(text):
    text = text.strip()
    text = text.strip("*_`").strip()
    return text


def detect_bias(text, sections=None):
    """Classify the overall bias from the report's own wording.

    Returns one of BULLISH / BEARISH / NEUTRAL / MIXED / INSUFFICIENT EVIDENCE
    / UNAVAILABLE. INSUFFICIENT EVIDENCE (an explicit refusal to conclude)
    wins; otherwise an explicitly stated stance in the conclusion/summary
    wins; if none is stated, section-title mentions are counted (tie -> MIXED);
    nothing found -> UNAVAILABLE. Never guesses toward bullish/bearish.
    """
    if not text or not text.strip():
        return "UNAVAILABLE"
    if "INSUFFICIENT EVIDENCE" in text.upper():
        return "INSUFFICIENT EVIDENCE"

    sections = sections or {}
    priority_blob = ""
    for title, items in sections.items():
        lowered = title.lower()
        if any(k in lowered for k in ("conclusion", "summary", "executive", "overall")):
            priority_blob += " " + " ".join(items)
    if priority_blob.strip():
        upper = priority_blob.upper()
        for token in ("BULLISH", "BEARISH", "NEUTRAL", "MIXED"):
            if re.search(r"\b" + token + r"\b", upper):
                return token

    counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0, "MIXED": 0}
    for title in sections:
        upper_title = title.upper()
        for key in counts:
            if key in upper_title:
                counts[key] += 1
    best = max(counts, key=lambda k: counts[k])
    if counts[best] == 0:
        return "UNAVAILABLE"
    ordered = sorted(counts.values(), reverse=True)
    if ordered[0] == ordered[1]:
        return "MIXED"
    return best


def _extract_levels(sections):
    for title, items in sections.items():
        blob = " ".join([title] + items)
        found = {}
        for key, pattern in _LEVEL_PATTERNS.items():
            m = pattern.search(blob)
            if m:
                try:
                    found[key] = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        if found:
            return found
    return {}


def parse_report(text):
    """Return {"bias", "sections", "order", "levels", "raw"}.

    `sections` maps a heading to its cleaned bullet/paragraph lines; `raw`
    always keeps the original text for a scrollable fallback.
    """
    raw = text if isinstance(text, str) else ""
    result = {"bias": "UNAVAILABLE", "sections": {}, "order": [],
              "levels": {}, "raw": raw}
    if not raw.strip():
        return result

    sections = {}
    order = []
    current = None
    for line in raw.splitlines():
        if _DISCLAIMER in line:
            continue
        if any(line.strip().startswith(p) for p in _PREAMBLE):
            continue

        match = _HEADING_HASH.match(line) or _HEADING_NUM.match(line) or _TITLE_COLON.match(line)
        if match:
            title = _clean(match.group(1))
            title = re.sub(r"^\s*\d+[).]\s*", "", title).strip()  # drop "1) "
            if title and len(title) <= 60 and not _is_bullet(title):
                current = title
                if title not in sections:
                    sections[title] = []
                    order.append(title)
                continue

        content = line.strip()
        if not content:
            continue
        content = _BULLET.sub("", content)
        content = _clean(content)
        if not content:
            continue
        if current is None:
            current = "Report"
            sections.setdefault("Report", [])
            if "Report" not in order:
                order.append("Report")
        sections[current].append(content)

    result["sections"] = sections
    result["order"] = order
    result["bias"] = detect_bias(raw, sections)
    result["levels"] = _extract_levels(sections)
    return result


def _is_bullet(value):
    return bool(_BULLET.match(value))


def sections_matching(parsed, *keywords):
    """Return {title: items} for section titles containing any keyword."""
    keys = tuple(k.lower() for k in keywords)
    return {
        title: items
        for title, items in parsed.get("sections", {}).items()
        if any(k in title.lower() for k in keys)
    }


def collect_bullets(sections_dict):
    """Flatten several sections into one ordered bullet list."""
    bullets = []
    for items in sections_dict.values():
        for item in items:
            if item not in bullets:
                bullets.append(item)
    return bullets
