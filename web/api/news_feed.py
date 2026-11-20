"""Live Indian-market news for Nova Desk: publisher RSS feeds plus NSE filings, polled about once a minute.

`poll()` fetches every source in parallel, merges a 24 h list for the Desk and returns
only items never seen before. One story carried by several outlets counts once (same
link, or same first seven title words). Items are tagged by keyword; HIGH marks the kinds
that tend to move prices (RBI/SEBI action, results, deals, orders, material NSE filings).
Tags are a keyword heuristic, not a judgement. A source that fails is listed in `errors`,
never back-filled. Analysis only: no orders, no BUY/SELL.
"""

from __future__ import annotations

import json
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from analysis.data import nse_live
from analysis.data.morning_brief import JUNK_NEWS
from market_lab.market_lab_data import CACHE_DIR
from web.api.market_updates import FILING_HIGH, FILING_SKIP, TRUSTED_SOURCES, _clean_filing, _key

IST = ZoneInfo("Asia/Kolkata")
# (name, url); names are unique so each failed feed is listed. Market sections only; checked 2026-11-20. Moneycontrol RSS stopped in 2024, Financial Express's feed is gone (410).
FEEDS = (
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Economic Times · stocks", "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Mint", "https://www.livemint.com/rss/markets"),
    ("CNBC-TV18", "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
    ("BusinessLine", "https://www.thehindubusinessline.com/markets/feeder/default.rss"),
    # each item carries its own publisher in <source>; one request a minute stays well under Google's limits
    ("Google News", "https://news.google.com/rss/search?q=Nifty+OR+Sensex+OR+NSE+when:1d&hl=en-IN&gl=IN&ceid=IN:en"),
)
NSE_SOURCE = "NSE filings"
# a press release is HIGH only when its words say so (order, results, deal...); most are store openings and awards
FILING_ALERT = FILING_HIGH - {"Press Release"}
TIMEOUT_S = 8
KEEP_HOURS = 24  # Desk list window
KEEP_ITEMS = 300
SEEN_DAYS = 3
SEEN_PATH = Path(CACHE_DIR) / "news_seen.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NovaDesk/1.0"}

# (tag, high impact, pattern on the lowercased title); every match is kept, in this order
TAGS = (
    ("RBI", True, r"\brbi\b|repo rate|monetary policy|\bmpc\b"),
    ("SEBI", True, r"\bsebi\b"),
    ("RESULTS", True, r"\bq[1-4]\b|\bresults?\b|net profit|quarterly"),
    ("DEAL", True, r"acqui|merger|demerger|stake (?:sale|buy)|block deal|bulk deal|takeover|buyback"),
    ("ORDER", True, r"\borders?\b.{0,30}(?:worth|from|of rs|of ₹|crore)|bags .{0,40}order|contract worth"),
    ("IPO", False, r"\bipos?\b|\blisting\b"),
    ("FLOWS", False, r"\bfiis?\b|\bfpis?\b|\bdiis?\b"),
    ("MACRO", False, r"inflation|\bcpi\b|\bgdp\b|rupee|crude|\bfed\b|tariff|budget"),
    ("RATING", False, r"upgrade|downgrade|target price|\brating\b"),
    ("INDEX", False, r"nifty|sensex"),
)
_TAGS = [(t, h, re.compile(p)) for t, h, p in TAGS]

_lock = threading.Lock()
_recent: list[dict] = []
_errors: dict[str, str] = {}
_polled_at: str | None = None
_seen: dict[str, str] | None = None  # key -> first-seen UTC iso; loaded lazily


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _date(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    try:
        return _utc(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        pass
    try:  # Atom / ISO 8601
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _utc(dt if dt.tzinfo else dt.replace(tzinfo=IST))
    except ValueError:
        return None


def tag(item: dict) -> dict:
    title = item["title"].lower()
    tags = [t for t, _, rx in _TAGS if rx.search(title)]
    item["tags"] = tags
    item["high"] = item.get("high", False) or any(h for t, h, _ in _TAGS if t in tags)
    return item


def parse_feed(content: bytes, source: str) -> list[dict]:
    """RSS <item> or Atom <entry> to {title, link, source, published}. Links must be https (they go into the page)."""
    root = ET.fromstring(content)
    out = []
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1]
        if name not in ("item", "entry"):
            continue
        f = {c.tag.rsplit("}", 1)[-1]: c for c in node}
        title = re.sub(r"\s+", " ", (f["title"].text or "") if "title" in f else "").strip()
        link_el = f.get("link")
        link = ((link_el.text or link_el.get("href") or "") if link_el is not None else "").strip()
        src = source
        if source == "Google News" and "source" in f and (f["source"].text or "").strip():
            src = f["source"].text.strip()
            if title.endswith(f" - {src}"):
                title = title[: -len(src) - 3]
            if not any(t in src.lower() for t in TRUSTED_SOURCES):
                continue  # Google mixes in blogs and broker landing pages; keep established publishers
        if not title or not link.startswith("https://") or JUNK_NEWS.search(title):
            continue
        when = next((f[k].text for k in ("pubDate", "published", "updated", "date") if k in f and f[k].text), None)
        out.append(tag({"title": title, "link": link, "source": src, "published": _date(when)}))
    return out


def parse_filings(rows) -> list[dict]:
    """NSE corporate announcements (newest ~20, all companies). Routine categories are dropped."""
    out = []
    for a in rows if isinstance(rows, list) else []:
        desc = str(a.get("desc") or "").strip()
        link = str(a.get("attchmntFile") or "")
        if not desc or desc in FILING_SKIP or not link.startswith("https://"):
            continue
        try:
            when = _utc(datetime.strptime(str(a.get("an_dt")), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST))
        except ValueError:
            when = None
        text = str(a.get("attchmntText") or "")
        titled = re.search(r'titled\s+"([^"]+)"', text)
        body = f"{desc}: {titled.group(1)}"[:160] if titled else _clean_filing(desc, text)
        out.append(tag({"title": f"{a.get('symbol')}: {body}", "link": link, "source": NSE_SOURCE,
                        "published": when, "high": desc in FILING_ALERT}))
    return out


class _IPv4(requests.adapters.HTTPAdapter):
    """Bind to an IPv4 source. On this PC IPv6 has no route and urllib3 tries addresses one by one,
    so each IPv6 address cost a full timeout (16 s for ET, Mint) before IPv4 answered in 0.1 s."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = ("0.0.0.0", 0)
        super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", _IPv4())


def _fetch_feed(source: str, url: str) -> list[dict]:
    r = _session.get(url, headers=UA, timeout=TIMEOUT_S)
    r.raise_for_status()
    return parse_feed(r.content, source)


def fetch_all() -> tuple[list[dict], dict[str, str]]:
    """Every source in parallel. Returns (items, errors by source)."""
    jobs = [(name, lambda name=name, u=u: _fetch_feed(name.split(" · ")[0], u)) for name, u in FEEDS]
    jobs.append((NSE_SOURCE, lambda: parse_filings(nse_live.get("corporate-announcements", {"index": "equities"}))))
    items, errors = [], {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [(name, pool.submit(fn)) for name, fn in jobs]
        for name, fut in futures:
            try:
                items += fut.result()
            except Exception as exc:  # one dead feed must not stop the rest
                errors[name] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return items, errors


def _ids(item: dict) -> list[str]:
    return [i for i in (item["link"], _key(item["title"])) if i]


def _load_seen() -> dict[str, str]:
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_seen(seen: dict[str, str]) -> None:
    try:
        SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SEEN_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        tmp.replace(SEEN_PATH)
    except OSError as exc:
        print(f"[NEWS] could not save seen list: {exc}")


def merge(items: list[dict], recent: list[dict], seen: dict[str, str], now: datetime) -> tuple[list[dict], list[dict]]:
    """Pure merge step: returns (new items, updated Desk list). Mutates `seen` (adds new ids, drops old ones)."""
    now_s = _utc(now)
    keep_after = _utc(now - timedelta(hours=KEEP_HOURS))
    new = []
    for it in sorted(items, key=lambda i: i["published"] or "", reverse=True):
        it.setdefault("seen_at", now_s)
        ids = _ids(it)
        if any(i in seen for i in ids):
            continue
        for i in ids:
            seen[i] = now_s
        new.append(it)
    drop_before = _utc(now - timedelta(days=SEEN_DAYS))
    for k in [k for k, v in seen.items() if v < drop_before]:
        del seen[k]
    # the Desk list holds everything fetched, not only new items, so a restart still shows the full 24 h
    merged, listed = [], set()
    for it in sorted(recent + items, key=lambda i: i["published"] or i["seen_at"], reverse=True):
        ids = _ids(it)
        if (it["published"] or it["seen_at"]) < keep_after or any(i in listed for i in ids):
            continue
        listed.update(ids)
        merged.append(it)
    return new, merged[:KEEP_ITEMS]


def poll(now: datetime | None = None) -> dict:
    """Fetch all sources once. Returns {"new": [...], "errors": {...}}."""
    global _seen, _recent, _errors, _polled_at
    now = now or datetime.now(timezone.utc)
    items, errors = fetch_all()
    with _lock:
        if _seen is None:
            _seen = _load_seen()
        new, _recent = merge(items, _recent, _seen, now)
        _errors, _polled_at = errors, _utc(now)
        if new:
            _save_seen(_seen)
    if errors:
        print(f"[NEWS] {len(errors)} source(s) failed: {', '.join(errors)}")
    return {"new": new, "errors": errors}


def snapshot() -> dict:
    with _lock:
        return {"items": list(_recent), "errors": dict(_errors), "polled_at": _polled_at,
                "sources": len(FEEDS) + 1, "note": "Tags are keyword-based. Analysis only, not a buy/sell signal."}


ALERT_FRESH_MIN = 30  # a story older than this when first seen (e.g. overnight, server was off) is not pushed
ALERT_MAX = 8


def alerts(new: list[dict], now: datetime | None = None) -> list[dict]:
    """High-impact, freshly published items worth a Telegram push."""
    cutoff = _utc((now or datetime.now(timezone.utc)) - timedelta(minutes=ALERT_FRESH_MIN))
    return [i for i in new if i["high"] and i["published"] and i["published"] >= cutoff][:ALERT_MAX]
