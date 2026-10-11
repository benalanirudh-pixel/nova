
"""
Nova Market Lab Brain
Evidence-grounded interpretation of the existing Market Lab report.

READ-ONLY:
- No broker connection
- No trade execution
- No automatic orders
- No invented market data or confidence scores
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from typing import Any

import ollama

from market_lab.market_lab_data import get_market_lab_data


MODEL = "qwen3.5:4b"
KEEP_ALIVE = "30m"

OPTIONS = {
    "num_ctx": 8192,
    "temperature": 0.2,
}


SYSTEM_PROMPT = """
You are Nova Market Lab Brain, an evidence-grounded Indian market
analysis assistant.

You interpret the supplied Nova Market Lab report. You do not
replace, recalculate, or invent data from the underlying engines.

PRIMARY OBJECTIVE
Produce an integrated interpretation of the evidence, not a report
about just one instrument when multiple instruments are available.

COVERAGE REQUIREMENTS
For a broad or integrated market assessment, address each applicable
area below. If a section's data is missing, explicitly say so briefly.

1. OVERALL REGIME
   - Reported market regime and its stated basis.
   - Whether the available evidence is broadly bullish, bearish,
     mixed, or insufficient to establish a directional bias.

2. NIFTY
   - Reported returns, snapshot and relevant technical context.
   - Do not confuse NIFTY evidence with BANK NIFTY evidence.

3. BANK NIFTY
   - Reported returns, snapshot and relevant technical context.
   - Keep its conclusions separate from NIFTY conclusions.

4. MARKET BREADTH
   - Describe participation using the supplied breadth metrics.
   - Do not infer broad market strength from a small number of stocks.

5. VOLATILITY
   - Interpret only the volatility fields actually supplied.
   - Distinguish observed volatility from expectations or inference.

6. SECTORS AND TECHNICAL LEADERSHIP
   - Identify reported leadership and weakness when present.
   - Do not treat a technical ranking as a guaranteed future winner.

7. DERIVATIVES
   - Report the instrument and expiry where available.
   - Interpret PCR, open interest, volume, IV, skew, max pain, and
     support/resistance labels only when present.
   - Distinguish reported OI concentrations from confirmed support
     or resistance.
   - Max pain is not a reliable standalone spot-price target.
   - Do not infer option-writer identity or institutional intent
     solely from open interest.

8. INSTITUTIONAL FLOWS
   - State the reported source, period, values, and units when available.
   - Keep FII, DII, and combined flows distinct.
   - Do not mix daily, 5-day, 20-day, or other time windows.
   - Do not recalculate flow values unless the report explicitly
     supplies the necessary inputs and the user requests a calculation.
   - If units or period labels are unclear, say they are unclear.
   - Never silently convert crore, lakh, thousand, or other units.

9. CONFLICTING EVIDENCE
   - Identify agreement and disagreement across the available sources.
   - Explain why a mixed reading remains mixed.
   - Do not force a directional conclusion when evidence conflicts.

10. RISKS AND WHAT TO MONITOR
    - Name the material data gaps and risks.
    - State which observable changes would strengthen or weaken the
      current interpretation, without inventing thresholds or prices.

SPECIFIC QUESTIONS
If the user asks a narrow question, answer it first. Include other
sections only when relevant. For broad assessment requests, use all
applicable coverage requirements above.

SINGLE-STOCK QUESTIONS
If the user names one specific stock (the report provides a "focus_symbol"
block for it), answer about THAT stock and center the response on it.
Do NOT emit the broad multi-section market template for a single-stock
question. Use the focus_symbol data (live per-stock snapshot plus any
factor/technical membership) as the primary evidence, and add only the
minimum market/sector context that is relevant to the question. If a
per-stock field is missing or the live snapshot is unavailable, say so
explicitly and answer only with what is verifiable; never substitute
market-wide numbers for that stock, and never invent prices, levels,
targets, or probabilities. Suggested single-stock structure:

SINGLE-STOCK ANALYSIS: <SYMBOL>
1. What was asked
2. Verified per-stock facts (price, change, RSI, MACD, trend, EMAs,
   momentum, company name — only fields actually present)
3. Factor/technical context from the report (rank/composite z if present;
   state plainly if the stock is not in the stored factor extremes)
4. Brief relevant market/sector context
5. Data limitations and freshness

STRICT EVIDENCE RULES
- Use only data and labels contained in the supplied report.
- Preserve numerical values, signs, units, dates, instruments, and
  measurement periods exactly as reported.
- Do not convert units or silently reconcile conflicting figures.
- If two report fields conflict, flag the discrepancy.
- Never treat unavailable data as zero or neutral.
- A READY status does not independently prove data reliability.
- Treat stale, incomplete, inconsistent, or cached data as limitations
  where the report identifies them.
- Distinguish reported measurements from interpretation.
- Do not invent price levels, indicators, returns, flows, targets,
  probabilities, accuracy figures, or confidence scores.
- Do not claim predictive accuracy or institutional-grade performance
  without supporting validation evidence.
- Volume alone does not prove institutional activity.
- A positioning label or technical score is not a standalone signal.
- Do not describe a potential support/resistance level as guaranteed.
- Do not provide a fabricated statistical tendency or probability.

OUTPUT QUALITY
- Be specific and concise, but cover the required evidence.
- Use the report's actual values where relevant.
- Do not repeat the same analysis in multiple sections.
- Do not repeat the full report or restate the same conclusion.
- Never invent a missing field to make the report look complete.
- If the data does not support a conclusion, say so.

SAFETY
- Analysis and research only.
- No broker connection, trade execution, or automatic orders.
- Never claim an order was placed.
- Any analytical bias must be qualified and must not be represented
  as a guaranteed outcome.

For a broad assessment, use this output structure:

NOVA MARKET LAB ASSESSMENT

1. Overall regime
2. NIFTY
3. BANK NIFTY
4. Breadth and volatility
5. Sectors and technical leadership
6. Derivatives
7. Institutional flows
8. Evidence agreement and conflicts
9. Risks and data limitations
10. What to monitor next

Combine sections when that avoids repetition. Omit unavailable details
but state important data gaps. Do not force a bullish or bearish bias.

Use plain text. Never expose hidden reasoning.
""".strip()


def _json_safe(value: Any) -> Any:
    """Convert report values into strict JSON-compatible values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    # Support NumPy-like scalar values without importing NumPy.
    item_method = getattr(value, "item", None)

    if callable(item_method):
        try:
            converted = item_method()

            if converted is not value:
                return _json_safe(converted)
        except Exception:
            pass

    # Fallback for unexpected values returned by an engine.
    return str(value)


def _limit_list(value: Any, limit: int = 10) -> Any:
    """
    Limit long display-oriented lists to control prompt size.

    This changes only the AI payload, not the underlying report.
    Non-list values are returned unchanged.
    """

    if isinstance(value, list):
        return value[:limit]

    if isinstance(value, tuple):
        return list(value[:limit])

    return value


# Words that are clearly not a single stock symbol, so they never trigger a
# single-stock answer (broad market / instrument / instruction words).
_NON_SYMBOL_WORDS = {
    "NIFTY", "BANKNIFTY", "NIFTY50", "SENSEX", "BANK", "MARKET", "MARKETS",
    "STOCK", "STOCKS", "EQUITY", "EQUITIES", "INDEX", "INDICES", "INDIAN",
    "INDIA", "NSE", "BSE", "ANALYZE", "ANALYSIS", "SUMMARY", "OVERVIEW",
    "TELL", "ABOUT", "WHAT", "WHICH", "HOW", "SHOW", "GIVE", "GUIDE",
    "TREND", "TRENDS", "PRICE", "PRICES", "LEVEL", "LEVELS", "REGIME",
    "BREADTH", "SECTOR", "SECTORS", "CPI", "WPI", "PPI", "GDP", "RBI",
    "VERDICT", "OPINION", "GOOD", "BAD", "BUY", "SELL", "HOLD", "IS", "IT",
    "THE", "FOR", "AND", "WITH", "ME", "TOP", "BEST", "WORST", "TODAY",
    "NOW", "RISK", "FLOW", "FLOWS", "FII", "DII", "VIX", "TECHNICALS",
    "MOMENTUM", "MACD", "RSI", "ATR", "VOL", "VOLUME", "REPORT", "SESSION",
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&._-]{1,19}")


def _known_symbols() -> set | None:
    """Return the cached NSE symbol universe (upper), or None if unavailable.
    Offline: reads the cached equity master; never triggers a download."""
    try:
        from analysis.data.symbol_master import load_master

        master = load_master()
        if master is None or "symbol" not in master:
            return None
        return set(master["symbol"].astype(str).str.upper())
    except Exception:
        return None


def _extract_focus_symbol(query: str) -> str:
    """Detect the single NSE stock the user is asking about, or ''.

    Deterministic and offline: a candidate token is accepted only when it is
    a real symbol in the cached equity master. Benchmarks/instruments and
    instruction words never trigger it (that stays a broad assessment). If
    the master cache is unavailable, fall back to an explicitly UPPERCASE
    ticker-shaped token so the feature still works without inventing data.
    """
    if not isinstance(query, str) or not query.strip():
        return ""

    tokens = _TOKEN_RE.findall(query)
    candidates = []
    for tok in tokens:
        upper = tok.upper()
        if upper in _NON_SYMBOL_WORDS:
            continue
        candidates.append((tok, upper))

    if not candidates:
        return ""

    known = _known_symbols()
    if known:
        for _, upper in candidates:
            if upper in known:
                return upper
        return ""  # no real symbol named -> stay broad

    # Fallback (no master cache): accept an explicitly uppercase token.
    for tok, upper in candidates:
        if tok.isupper() and len(upper) >= 2:
            return upper
    return ""


def _focus_payload(symbol: str, report: dict[str, Any]) -> dict[str, Any]:
    """Assemble verifiable per-stock evidence for the requested symbol.

    Live per-stock snapshot comes from the existing watchlist engine (which
    returns status UNAVAILABLE with a reason on any failure instead of demo
    values). Factor/technical membership is read from the report itself. No
    values are fabricated anywhere.
    """
    focus: dict[str, Any] = {"requested_symbol": symbol}

    try:
        from analysis.data.watchlist_engine import refresh_watch_symbol

        live = refresh_watch_symbol(symbol)
    except Exception as exc:
        live = {
            "status": "UNAVAILABLE",
            "reason": f"{type(exc).__name__}: {exc}",
            "symbol": symbol,
        }
    focus["live_snapshot"] = _json_safe(live)

    try:
        from analysis.data.symbol_master import get_security

        security = get_security(symbol)
        if security:
            focus["company_name"] = str(
                security.get("company_name")
                or security.get("name")
                or ""
            ).strip()
    except Exception:
        pass

    symbol_upper = symbol.upper()

    membership = {"in_stored_extremes": False}
    factors = report.get("research_factors")
    if isinstance(factors, dict):
        for side, key in (("top", "top_ranked"), ("bottom", "bottom_ranked")):
            for item in factors.get(key, []) or []:
                if isinstance(item, dict) and str(
                    item.get("symbol", "")
                ).upper() == symbol_upper:
                    membership = {
                        "in_stored_extremes": True,
                        "side": side,
                        "rank": item.get("rank"),
                        "composite_z": item.get("composite_z"),
                    }
                    break
            if membership["in_stored_extremes"]:
                break
    focus["factor_membership"] = membership

    technical = {"in_top_technical": False}
    for item in report.get("top_technical_stocks", []) or []:
        if isinstance(item, dict) and str(
            item.get("symbol", "")
        ).upper() == symbol_upper:
            technical = {
                "in_top_technical": True,
                "technical_score": item.get("technical_score"),
                "trend": item.get("trend"),
            }
            break
    focus["technical_membership"] = technical

    return _json_safe(focus)


def _compact_factors(report: dict[str, Any]) -> dict[str, Any] | None:
    """A small, JSON-safe factor summary (top/bottom 5) for prompt context."""
    factors = report.get("research_factors")
    if not isinstance(factors, dict):
        return None

    def rows(key):
        out = []
        for item in (factors.get(key) or [])[:5]:
            if isinstance(item, dict):
                out.append({
                    "rank": item.get("rank"),
                    "symbol": item.get("symbol"),
                    "composite_z": item.get("composite_z"),
                })
        return out

    return {
        "status": factors.get("status"),
        "method": factors.get("method"),
        "universe_size": factors.get("universe_size"),
        "top_ranked": rows("top_ranked"),
        "bottom_ranked": rows("bottom_ranked"),
    }


def _build_analysis_payload(
    report: dict[str, Any],
    focus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a structured AI payload from the existing report.

    Preserve the original engine's values and labels. Only the
    display-oriented technical-stock list is capped. When the user asks
    about a specific stock, `focus` carries that symbol's verified evidence.
    """
    ai_context = report.get("ai_context")

    if not isinstance(ai_context, dict):
        ai_context = {}

    payload = {
        "system": report.get("system", "NOVA MARKET LAB"),
        "generated": report.get("generated"),
        "market": report.get("market"),
        "mode": report.get("mode"),
        "stocks_analyzed": report.get("stocks_analyzed"),

        # Overall regime and benchmark context
        "market_regime": report.get("market_regime"),
        "nifty_returns": report.get("nifty_returns"),
        "bank_nifty_returns": report.get("bank_nifty_returns"),
        "nifty_snapshot": report.get("nifty_snapshot"),

        # Participation and leadership
        "breadth": report.get("breadth"),
        "volatility": report.get("volatility"),
        "sector_intelligence": report.get("sector_intelligence"),
        "top_technical_stocks": _limit_list(
            report.get("top_technical_stocks"),
            limit=10,
        ),

        # Positioning and flows
        "derivatives": report.get("derivatives"),
        "institutional_flow": report.get("institutional_flow"),

        # Data-quality and policy context
        "data_availability": report.get("data_availability"),
        "decision_policy": report.get("decision_policy"),
        "ai_context": ai_context,
    }

    # Compact factor summary so the model can place a single stock in the
    # cross-sectional ranking without expanding the whole report.
    compact_factors = _compact_factors(report)
    if compact_factors is not None:
        payload["research_factors"] = compact_factors

    # Single-stock focus (only when the user named a real stock).
    if focus is not None:
        payload["focus_symbol"] = focus

    return payload


def _extract_response_content(response: Any) -> str:
    """Read Ollama response content from object or dict responses."""

    if isinstance(response, dict):
        message = response.get("message", {})

        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = getattr(message, "content", "")
    else:
        message = getattr(response, "message", None)
        content = getattr(message, "content", "")

    if not isinstance(content, str):
        return ""

    return content.strip()


def analyze_market_lab(
    query: str = "",
    force_refresh: bool = False,
) -> str:
    """
    Retrieve the existing Market Lab report and ask Ollama to interpret it.

    Cache-first behavior is preserved unless force_refresh=True.
    This function never executes or submits trades.
    """

    # Step 1: Retrieve the report from the existing data engine.
    try:
        report = get_market_lab_data(
            force_refresh=force_refresh,
        )

        if not isinstance(report, dict) or not report:
            return (
                "MARKET LAB ERROR: The data engine did not return "
                "a usable report. No analysis was generated."
            )

    except Exception as exc:
        return (
            "MARKET LAB DATA ERROR: "
            f"{type(exc).__name__}: {exc}. "
            "The analysis was not completed."
        )

    # Step 2: Resolve the user's request.
    user_question = (
        query.strip()
        if isinstance(query, str)
        else ""
    )

    default_question = (
        "Provide an integrated assessment of the available "
        "market evidence. Cover NIFTY and BANK NIFTY separately, "
        "then breadth, volatility, sectors, derivatives, "
        "institutional flows, conflicts, and data limitations."
    )

    # Step 2a: If a specific stock was named, gather verified per-stock
    # evidence so the answer is about that stock, not the whole market.
    focus_symbol = _extract_focus_symbol(user_question) if user_question else ""
    focus = None
    if focus_symbol:
        try:
            focus = _focus_payload(focus_symbol, report)
        except Exception as exc:
            focus = {
                "requested_symbol": focus_symbol,
                "reason": f"focus lookup failed: {type(exc).__name__}: {exc}",
            }

    try:
        payload = _json_safe(
            _build_analysis_payload(report, focus=focus)
        )

        report_json = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except Exception as exc:
        return (
            "MARKET LAB DATA ERROR: "
            f"{type(exc).__name__}: {exc}. "
            "The analysis was not completed."
        )

    if not user_question:
        user_question = default_question

    focus_json = None
    if focus is not None:
        focus_json = json.dumps(
            focus,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )

    # Step 3: Keep the source report explicit in the prompt.
    if focus_json:
        # Single-stock question: answer about that stock; do not dump the
        # broad market template.
        user_message = (
            "USER QUESTION:\n"
            f"{user_question}\n\n"
            "Answer about the requested stock using the FOCUS STOCK JSON "
            "below as the primary evidence. Do NOT emit the broad "
            "multi-section market template for this single-stock question. "
            "Add only brief, relevant market/sector context. If a per-stock "
            "field is missing or the live snapshot is UNAVAILABLE, say so "
            "explicitly; never substitute market-wide numbers for this "
            "stock and never invent prices, levels, targets or "
            "probabilities. Preserve values, units and dates exactly.\n\n"
            "FOCUS STOCK JSON:\n"
            f"{focus_json}\n\n"
            "MARKET LAB REPORT JSON:\n"
            f"{report_json}"
        )
    else:
        user_message = (
            "USER QUESTION:\n"
            f"{user_question}\n\n"
            "IMPORTANT DATA RULES:\n"
            "- The JSON below is the source of truth.\n"
            "- Preserve values, signs, units, dates, and periods exactly.\n"
            "- Do not silently convert or recalculate reported values.\n"
            "- Cover both benchmarks for a broad market assessment.\n"
            "- Do not repeat the same analysis in multiple sections.\n"
            "- Flag conflicts and missing fields instead of guessing.\n\n"
            "MARKET LAB REPORT JSON:\n"
            f"{report_json}"
        )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    # Step 4: Generate the interpretation.
    try:
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            think=False,
            options=OPTIONS,
            keep_alive=KEEP_ALIVE,
        )

        content = _extract_response_content(response)

        if not content:
            return (
                "MARKET LAB AI ERROR: The model returned an empty "
                "interpretation. The report was retrieved, but no "
                "market conclusion was generated."
            )

        generated = report.get("generated", "Not reported")
        market = report.get("market", "Not reported")

        focus_line = (
            f"Focus: {focus_symbol}\n" if focus_symbol else ""
        )

        return (
            "NOVA MARKET LAB ANALYSIS\n"
            f"Report generated: {generated}\n"
            f"{focus_line}"
            f"Market: {market}\n\n"
            f"{content}\n\n"
            "LIMITATION: This is an interpretation of the supplied "
            "market report, not a validated prediction, a guarantee "
            "of market direction, or an instruction to execute a trade."
        )

    except ollama.ResponseError as exc:
        if getattr(exc, "status_code", None) == 404:
            return (
                f"MARKET LAB AI ERROR: Ollama model '{MODEL}' was not "
                f"found. Install it with: ollama pull {MODEL}"
            )

        return (
            "MARKET LAB AI ERROR: Ollama rejected the request. "
            f"{getattr(exc, 'error', str(exc))}"
        )

    except Exception as exc:
        return (
            "MARKET LAB AI ERROR: The report was retrieved, but "
            f"interpretation failed ({type(exc).__name__}: {exc}). "
            "No market conclusion was generated."
        )
