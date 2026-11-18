"""Telegram market updates: hourly index pulse, pre-market brief, post-market wrap, rescan note.

Builders take plain data and return Telegram HTML (tested offline); `collect_*` and
`build_*` functions do the network work. Tables sit in <pre> blocks no wider than
~35 characters so they do not wrap on a phone. Missing data shows as n/a, never
invented. Analysis only: no orders, no BUY/SELL. The AI line is labelled unverified.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.data import day_movers, morning_brief, nse_feed, nse_live
from analysis.data.stock_profile import parse_news
from web.api.telegram import plain

IST = ZoneInfo("Asia/Kolkata")
DISCLAIMER = "Analysis only. Not a buy/sell signal."
ORDER = (("nifty", "NIFTY 50"), ("sensex", "SENSEX"), ("banknifty", "BANKNIFTY"), ("vix", "INDIA VIX"))
YAHOO = {"nifty": "^NSEI", "sensex": "^BSESN", "banknifty": "^NSEBANK", "vix": "^INDIAVIX"}
NEWS_FOR = 3  # headlines looked up for the top 3 gainers and top 3 losers
AI_TIMEOUT_S = 90
NA = "n/a"


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _pct(v, signed=True) -> str:
    return (f"{v:+.2f}" if signed else f"{v:.2f}") if _num(v) is not None else NA


def _money(v, dp=1) -> str:
    return f"{v:,.{dp}f}" if _num(v) is not None else NA


def _arrow(v) -> str:
    return "▲" if _num(v) and v > 0 else "▼" if _num(v) and v < 0 else "•"


def _now(now=None) -> datetime:
    return (now or datetime.now(IST)).astimezone(IST)


def esc(v) -> str:
    return html.escape(str(v), quote=False)


def header(title: str, now=None, note: str = "") -> str:
    stamp = f"{_now(now):%a %d %b %Y · %H:%M} IST"
    return f"<b>NOVA · {esc(title)}</b>\n<i>{stamp}{' · ' + esc(note) if note else ''}</i>"


def section(title: str) -> str:
    return f"\n<b>{esc(title)}</b>"


def table(rows: list[list], right: set[int] | None = None) -> str:
    """Fixed-width table: first row is the header; columns in `right` are right-aligned."""
    right = right if right is not None else set(range(1, len(rows[0])))
    cells = [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(cells[0]))]
    lines = [" ".join(c.rjust(w) if i in right else c.ljust(w) for i, (c, w) in enumerate(zip(r, widths))).rstrip()
             for r in cells]
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


def footer(sources: str) -> str:
    return f"\n<i>Src: {esc(sources)}. {DISCLAIMER}</i>"


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


def _range_pos(q: dict) -> str:
    """Where the last price sits in the day's range, 0 = low, 100 = high."""
    lo, hi, p = _num(q.get("low")), _num(q.get("high")), _num(q.get("price"))
    return f"{(p - lo) / (hi - lo) * 100:.0f}" if None not in (lo, hi, p) and hi > lo else NA


def index_table(quotes: dict, last: dict | None = None, label_last: str = "LAST") -> str:
    hourly = last is not None
    head = ["INDEX", label_last, "CHG%"] + (["1H%"] if hourly else []) + ["RNG"]
    rows = [head]
    for k, label in ORDER:
        q = quotes.get(k) or {}
        p = _num(q.get("price"))
        row = [label, _money(p, 2 if k == "vix" else 1), _pct(q.get("change_pct"))]
        if hourly:
            lp = _num((last.get(k) or {}).get("price"))
            row.append(_pct((p - lp) / lp * 100) if p and lp else NA)
        rows.append(row + [_range_pos(q) if k != "vix" else ""])
    return table(rows)


def _sources(quotes: dict, *extra: str) -> str:
    return ", ".join(sorted({q["source"] for q in quotes.values() if q.get("source")} | set(extra))) or NA


# ---------------------------------------------------------------- hourly pulse

def pulse_text(quotes: dict, last: dict | None = None, now=None) -> str:
    return "\n".join([
        header("INDEX PULSE", now),
        index_table(quotes, last or {}),
        "<i>1H% = change since the last pulse. RNG = position in day range (0 low, 100 high).</i>",
        footer(_sources(quotes)),
    ])


# ---------------------------------------------------------------- pre-market

TABLED_TOPICS = {"GIFT Nifty", "Global", "Crude", "Rupee", "Flows", "NIFTY"}  # shown in tables, not repeated as points


def _flows_table(fii: list | None) -> str | None:
    rows = [r for r in fii or [] if _num(r.get("net_cr")) is not None]
    if not rows:
        return None
    return table([["CATEGORY", "BUY", "SELL", "NET"]] + [
        [r["category"][:8], _money(r.get("buy_cr"), 0), _money(r.get("sell_cr"), 0), f"{r['net_cr']:+,.0f}"] for r in rows])


def premarket_text(brief: dict, now=None) -> str:
    g = brief.get("global") or {}
    out = [header("PRE-MARKET BRIEF", now)]
    rows = [["MARKET", "LAST", "CHG%"]]
    gift = brief.get("gift_nifty")
    if gift:
        rows.append(["GIFT NIFTY", _money(gift.get("price")), _pct(gift.get("change_pct"))])
    rows += [[i["name"][:11], _money(i.get("last"), 0), _pct(i.get("change_pct"))] for i in g.get("indices") or []]
    rows += [[c["name"][:11], _money(c.get("price"), 2), _pct(c.get("change_pct"))]
             for c in g.get("commodities") or [] if c.get("name") in ("Crude oil", "Gold")]
    rows += [[f["pair"][:11], _money(f.get("rate"), 2), _pct(f.get("change_pct"))]
             for f in g.get("fx") or [] if str(f.get("pair", "")).upper().startswith("USD")][:1]
    out += [section("Global cues"), table(rows) if len(rows) > 1 else NA]
    flows = _flows_table(brief.get("fii_dii"))
    date = ((brief.get("fii_dii") or [{}])[0]).get("date")
    out += [section(f"Institutional flows, ₹ cr ({date or 'prev session'})"), flows or "Not yet posted"]
    po = brief.get("preopen") or {}
    if po.get("is_today") and po.get("advances") is not None:
        out += [section("Pre-open (09:08)"), f"Advances {po['advances']:.0f} · Declines {po.get('declines') or 0:.0f}"]
    points = [c for c in brief.get("morning_call") or [] if c.get("text") and c.get("topic") not in TABLED_TOPICS]
    if points:
        out.append(section("Desk view"))
        out += [f"{ {'positive': '▲', 'negative': '▼'}.get(c.get('tone'), '•') } {esc(c['text'])}" for c in points[:5]]
    r = brief.get("range")
    if r:
        out += [section("Expected NIFTY range (1-day)"),
                f"{r['low']:,.0f} – {r['high']:,.0f}  (±{r['points']:,.0f} pts, ±{_pct(r.get('pct'), False)}%)"]
    news = brief.get("news") or []
    if news:
        out.append(section("Headlines"))
        out += [f"• {esc(n['title'])} <i>({esc(n.get('source') or '?')})</i>" for n in news[:3]]
    out.append(footer("NSE, Yahoo, Indian Market MCP, Google News"))
    return "\n".join(out)


# ---------------------------------------------------------------- post-market

SECTOR_SHORT = {
    "Agricultural Food & other Products": "Agri Food", "Automobile and Auto Components": "Auto",
    "Auto Components": "Auto Comp", "Capital Goods": "Cap Goods", "Capital Markets": "Cap Markets",
    "Chemicals & Petrochemicals": "Chemicals", "Commercial Services & Supplies": "Comm Svcs",
    "Construction Materials": "Constr Matl", "Consumer Durables": "Cons Durable", "Consumer Services": "Cons Svcs",
    "Electrical Equipment": "Elec Equip", "Fast Moving Consumer Goods": "FMCG", "Fertilizers & Agrochemicals": "Agrochem",
    "Financial Services": "Fin Svcs", "Industrial Manufacturing": "Ind Mfg", "Industrial Products": "Ind Products",
    "Information Technology": "IT", "IT - Services": "IT Svcs", "Leisure Services": "Leisure",
    "Media, Entertainment & Publication": "Media", "Metals & Mining": "Metals", "Non - Ferrous Metals": "Non-Ferrous",
    "Oil, Gas & Consumable Fuels": "Oil & Gas", "Other Consumer Services": "Cons Svcs", "Aerospace & Defense": "Defence",
    "Pharmaceuticals & Biotechnology": "Pharma", "Telecom - Services": "Telecom", "Telecommunication": "Telecom",
    "Textiles & Apparels": "Textiles", "Transport Services": "Transport", "Forest Materials": "Forest Matl",
}


def short_sector(name, width: int) -> str:
    return (SECTOR_SHORT.get(name, name) if name else NA)[:width]


def _movers_table(rows: list[dict]) -> str:
    return table([["SYMBOL", "CHG%", "RVOL", "SECTOR"]] + [
        [m["symbol"][:10], _pct(m["change_pct"]),
         f"{m['rel_volume']:.1f}x" if _num(m.get("rel_volume")) else NA, short_sector(m.get("sector"), 12)]
        for m in rows], right={1, 2})


def postmarket_text(report: dict, quotes: dict, movers: dict | None, sectors: dict | None,
                    headlines: dict, market_news: list, fii: list | None, ai: str | None = None, now=None) -> str:
    b = report.get("breadth") or {}
    out = [header("POST-MARKET WRAP", now), section("Indices"), index_table(quotes, label_last="CLOSE")]

    adv, dec = b.get("advancing"), b.get("declining")
    ad = f"{adv:,} / {dec:,} (A/D {adv / dec:.2f})" if _num(adv) is not None and dec else NA
    out += [section("Market internals"), f"Regime: <b>{esc(report.get('market_regime', NA))}</b>",
            f"Advances / declines: {ad}"]
    if _num(b.get("above_ema50_percent")) is not None:
        out.append(f"Stocks above 50-DMA: {b['above_ema50_percent']:.0f}% · 200-DMA: "
                   + (f"{b['above_ema200_percent']:.0f}%" if _num(b.get("above_ema200_percent")) is not None else NA))

    date = ((fii or [{}])[0]).get("date")
    out += [section(f"Institutional flows, ₹ cr ({date or 'today'})"), _flows_table(fii) or "Not yet posted"]

    if movers is None:
        out += [section("Movers"), "n/a (no scan cached)"]
    else:
        out += [section("Top gainers"), _movers_table(movers.get("gainers") or []) if movers.get("gainers") else "None",
                section("Top losers"), _movers_table(movers.get("losers") or []) if movers.get("losers") else "None"]
        looked = [m for k in ("gainers", "losers") for m in (movers.get(k) or [])[:NEWS_FOR]]
        if looked:
            out.append(section("Mover headlines (context, not confirmed cause)"))
            for m in looked:
                h = headlines.get(m["symbol"])
                out.append(f"{_arrow(m['change_pct'])} <b>{esc(m['symbol'])}</b>: "
                           + (f"{esc(h['title'])} <i>({esc(h.get('source') or '?')})</i>" if h else "<i>no news found</i>"))

    if sectors and (sectors.get("up") or sectors.get("down")):
        rows = [["SECTOR (MEDIAN)", "1D%", "N"]] + [[short_sector(s["sector"], 16), _pct(s["median_pct"]), s["stocks"]]
                                                    for s in (sectors.get("up") or []) + (sectors.get("down") or [])]
        out += [section("Sector moves"), table(rows)]

    if market_news:
        out.append(section("Market headlines"))
        out += [f"• {esc(n['title'])} <i>({esc(n.get('source') or '?')})</i>" for n in market_news[:3]]
    if ai:
        out += [section("AI read"), f"<i>Unverified, {esc(MODEL)}:</i> {esc(ai)}"]
    out.append(footer(_sources(quotes, "Nova scan", "Google News")))
    return "\n".join(out)


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


# ---------------------------------------------------------------- rescan / alerts

def rescan_text(report: dict, now=None) -> str:
    """After a rescan: how many stocks carry today's prices, so stale data is visible."""
    total, fresh = report.get("stocks_analyzed"), None
    try:
        import pandas as pd
        stamps = pd.read_csv(report["scanner_file"], usecols=["timestamp"])["timestamp"].astype(str).str[:10]
        total, fresh = len(stamps), int((stamps == _now(now).date().isoformat()).sum())
    except Exception as exc:
        print(f"[UPDATES] rescan count failed: {exc}")
    if fresh is not None and total:
        cover = f"{fresh:,} / {total:,} stocks on today's prices ({fresh / total * 100:.1f}%)"
        if fresh < total:
            cover += f" · {total - fresh} stale"
    else:
        cover = f"{total:,} stocks scanned" if isinstance(total, int) else "Stock count n/a"
    return "\n".join([header("FULL-MARKET RESCAN", now), cover,
                      f"Regime: <b>{esc(report.get('market_regime', NA))}</b>", footer("Nova scan")])


def failure_text(reason: str, now=None) -> str:
    return "\n".join([header("SCAN FAILED", now), esc(reason), "<i>The desk keeps the last good report.</i>"])


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
    return postmarket_text(*args, ai=ai_read(plain(postmarket_text(*args))))


def build_premarket(report: dict | None) -> str:
    return premarket_text(morning_brief.build_morning_brief(report))
