"""Telegram market updates: hourly index pulse, pre-market brief, post-market report.

Builders take plain data and return text (tested offline); `collect_*` functions
do the network work. Missing data shows as n/a, never invented. Analysis only:
no orders, no BUY/SELL. The AI line is labelled unverified.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.data import day_movers, morning_brief, nse_feed, nse_live
from analysis.data.stock_profile import parse_news

IST = ZoneInfo("Asia/Kolkata")
FOOTER = "Analysis only. Not a buy/sell signal."
ORDER = (("nifty", "NIFTY 50"), ("sensex", "SENSEX"), ("banknifty", "BANKNIFTY"), ("vix", "INDIA VIX"))
YAHOO = {"nifty": "^NSEI", "sensex": "^BSESN", "banknifty": "^NSEBANK", "vix": "^INDIAVIX"}
NEWS_FOR = 3  # headlines looked up for the top 3 gainers and top 3 losers
AI_TIMEOUT_S = 90


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _pct(v) -> str:
    return f"{v:+.2f}%" if _num(v) is not None else "n/a"


def _now(now=None) -> datetime:
    return (now or datetime.now(IST)).astimezone(IST)


# ---------------------------------------------------------------- index quotes

def _yahoo_quote(ticker: str) -> dict | None:
    import yfinance as yf
    # fast_info gives None for index tickers; daily history includes today's live bar
    h = yf.Ticker(ticker).history(period="5d", interval="1d").dropna(subset=["Close"])
    if h.empty:
        return None
    last = h.iloc[-1]
    prev = float(h["Close"].iloc[-2]) if len(h) > 1 else None
    return {"price": float(last["Close"]), "change_pct": (last["Close"] - prev) / prev * 100 if prev else None,
            "high": float(last["High"]), "low": float(last["Low"]), "source": "Yahoo"}


def index_quotes() -> dict:
    """NIFTY/BANKNIFTY/VIX from NSE (Yahoo fallback); SENSEX from Yahoo (no BSE source in Nova)."""
    out: dict = {}
    try:
        q = nse_live.parse_indices(nse_live.get("allIndices"))
        for k in ("nifty", "banknifty", "vix"):
            if q.get(k) and q[k]["price"] is not None:
                out[k] = {"price": q[k]["price"], "change_pct": q[k]["change_percent"],
                          "high": q[k]["high"], "low": q[k]["low"], "source": "NSE"}
    except Exception as exc:
        print(f"[UPDATES] NSE indices failed: {exc}")
    for k, t in YAHOO.items():
        if k not in out:
            try:
                if quote := _yahoo_quote(t):
                    out[k] = quote
            except Exception as exc:
                print(f"[UPDATES] Yahoo {t} failed: {exc}")
    return out


def _index_line(label: str, q: dict | None, last_price=None) -> str:
    if not q or _num(q.get("price")) is None:
        return f"{label}: n/a"
    line = f"{label} {q['price']:,.2f} ({_pct(q.get('change_pct'))})" if label == "INDIA VIX" \
        else f"{label} {q['price']:,.1f} ({_pct(q.get('change_pct'))})"
    if _num(last_price):
        line += f", 1h {_pct((q['price'] - last_price) / last_price * 100)}"
    if _num(q.get("high")) and _num(q.get("low")) and label != "INDIA VIX":
        line += f", H {q['high']:,.0f} L {q['low']:,.0f}"
    return line


# ---------------------------------------------------------------- hourly pulse

def pulse_text(quotes: dict, last: dict | None = None, now=None) -> str:
    last = last or {}
    lines = [f"NOVA hourly {_now(now):%H:%M} IST"]
    lines += [_index_line(label, quotes.get(k), (last.get(k) or {}).get("price")) for k, label in ORDER]
    sources = sorted({q["source"] for q in quotes.values() if q.get("source")})
    if sources:
        lines.append(f"Source: {', '.join(sources)}")
    lines.append(FOOTER)
    return "\n".join(lines)


# ---------------------------------------------------------------- pre-market

def premarket_text(brief: dict, now=None) -> str:
    lines = [f"NOVA pre-market {_now(now):%d %b}"]
    calls = [c["text"] for c in brief.get("morning_call") or [] if c.get("text")]
    lines += [f"- {t}" for t in calls[:6]] or ["Morning call: n/a"]
    r = brief.get("range")
    if r:
        lines.append(f"Expected NIFTY range: {r['low']:,.0f} - {r['high']:,.0f} (±{r['points']:,.0f} pts)")
    news = brief.get("news") or []
    if news:
        lines.append("News:")
        lines += [f"- {n['title']} ({n.get('source') or '?'})" for n in news[:3]]
    lines.append(FOOTER)
    return "\n".join(lines)


# ---------------------------------------------------------------- post-market

def _fii_line(fii: list | None) -> str:
    if not fii:
        return "FII/DII: not yet posted"
    parts = [f"{r['category']} {r['net_cr']:+,.0f} cr" for r in fii if _num(r.get("net_cr")) is not None]
    return f"FII/DII net ({fii[0].get('date') or '?'}): {', '.join(parts)}" if parts else "FII/DII: n/a"


def _mover_line(m: dict, headline: dict | None, looked_up: bool) -> list[str]:
    vol = f", {m['rel_volume']:.1f}x avg vol" if _num(m.get("rel_volume")) else ""
    out = [f"{m['symbol']} {_pct(m['change_pct'])} ({m.get('sector') or 'sector n/a'}{vol})"]
    if headline:
        out.append(f"   Headline: {headline['title']} ({headline.get('source') or '?'})")
    elif looked_up:
        out.append("   No news found")
    return out


def postmarket_text(report: dict, quotes: dict, movers: dict | None, sectors: dict | None,
                    headlines: dict, market_news: list, fii: list | None, ai: str | None = None, now=None) -> str:
    b = report.get("breadth") or {}
    lines = [f"NOVA post-market {_now(now):%d %b}"]
    lines += [_index_line(label, quotes.get(k)) for k, label in ORDER]
    breadth = f"{b['advancing']} up / {b['declining']} down" if b.get("advancing") is not None else "n/a"
    lines.append(f"Regime: {report.get('market_regime', 'n/a')} | Breadth: {breadth}")
    lines.append(_fii_line(fii))
    if movers is None:
        lines.append("Movers: n/a (no scan cached)")
    else:
        for key, title in (("gainers", "Top gainers"), ("losers", "Top losers")):
            lines.append(f"{title}:")
            for i, m in enumerate(movers.get(key) or []):
                lines += _mover_line(m, headlines.get(m["symbol"]), i < NEWS_FOR)
            if not movers.get(key):
                lines.append("   none")
    if sectors:
        fmt = lambda rows: ", ".join(f"{s['sector']} {_pct(s['median_pct'])}" for s in rows) or "none"
        lines.append(f"Sectors up: {fmt(sectors['up'])}")
        lines.append(f"Sectors down: {fmt(sectors['down'])}")
    if market_news:
        lines.append("Market news:")
        lines += [f"- {n['title']} ({n.get('source') or '?'})" for n in market_news[:3]]
    if ai:
        lines.append(f"AI read (unverified, {MODEL}): {ai}")
    lines.append(FOOTER)
    return "\n".join(lines)


def _clean_news(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    items = parse_news(raw, limit=80)
    return [n for n in morning_brief.fresh_news(items, max_days=2, n=40)
            if not morning_brief.JUNK_NEWS.search(n["title"])]


def collect_news(movers: dict | None) -> tuple[dict, list]:
    """One MCP session: market news plus news for the top movers. Failures give empty results."""
    picks = [m for k in ("gainers", "losers") for m in (movers or {}).get(k, [])[:NEWS_FOR]]
    calls = {"market": ("get_market_news", {"limit": 40})}
    calls.update({f"s:{m['symbol']}": ("get_stock_news", {"symbol": m["symbol"], "limit": 30}) for m in picks})
    try:
        raw = nse_feed.call_tools(calls)
    except Exception as exc:
        print(f"[UPDATES] news failed: {exc}")
        return {}, []
    headlines = {}
    for m in picks:
        hit = day_movers.match_headline(_clean_news(raw.get(f"s:{m['symbol']}")), m["symbol"], m.get("company"))
        if hit:
            headlines[m["symbol"]] = hit
    return headlines, _clean_news(raw.get("market"))


# ---------------------------------------------------------------- AI read

MODEL = "qwen3.5:4b"
AI_SYSTEM = ("You summarise one Indian stock market session for a phone notification. Use ONLY the facts given. "
             "Write at most two short sentences. Sentence 1: what the indices, breadth and sectors did. "
             "Sentence 2: which given headline most likely relates to the move, keeping the headline's own "
             "direction (if it says shares fell, they fell); if none clearly relates, say the cause is unclear. "
             "Never invent numbers, causes or directions. Never recommend buying or selling, never predict prices.")


def ai_read(facts: str) -> str | None:
    """Local Ollama summary of the report text. None on any failure: the report goes out without it."""
    try:
        import ollama
        resp = ollama.Client(timeout=AI_TIMEOUT_S).chat(
            model=MODEL, think=False, options={"temperature": 0.2},
            messages=[{"role": "system", "content": AI_SYSTEM}, {"role": "user", "content": facts}])
        text = (resp.get("message") or {}).get("content", "") if isinstance(resp, dict) else resp.message.content
        text = re.sub(r"\s+", " ", text or "").strip()
        # guardrail: drop the line rather than send trade advice
        if not text or re.search(r"\b(buy|sell|short|go long|accumulate|book profits?)\b", text, re.I):
            return None
        return text[:400]
    except Exception as exc:
        print(f"[UPDATES] AI read failed: {exc}")
        return None


def build_postmarket(report: dict) -> str:
    """Network and AI work for the evening report. Each part degrades to n/a on its own."""
    quotes = index_quotes()
    movers = sectors = None
    try:
        scan = day_movers.load_latest()
        if scan is not None:
            movers, sectors = day_movers.top_movers(scan), day_movers.sector_moves(scan)
    except Exception as exc:
        print(f"[UPDATES] movers failed: {exc}")
    headlines, market_news = collect_news(movers)
    try:
        fii = nse_live.fii_dii()
    except Exception:
        fii = None
    args = (report, quotes, movers, sectors, headlines, market_news, fii)
    return postmarket_text(*args, ai=ai_read(postmarket_text(*args)))


def build_premarket(report: dict | None) -> str:
    return premarket_text(morning_brief.build_morning_brief(report))
