"""
Nova tools: actions the LLM is allowed to trigger.
Evidence-grounded market-analysis layer.

Safety rules:
- Apps: whitelist only.
- Websites: http/https only.
- Web research: local SearXNG only.
- Market data: read-only.
- Market analysis: read-only NSE scanner.
- No broker connection.
- No order placement.
- No BUY/SELL execution.
- Market claims must be grounded in returned tool data.
"""

from __future__ import annotations

import datetime
import json
import math
import subprocess
import sys
import webbrowser

from pathlib import Path
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from analysis.data.market_data import get_instrument
from analysis.data.market_scanner import scan_market


# ============================================================================
# CONFIGURATION
# ============================================================================

DEBUG = True
SEARXNG_URL = "http://localhost:8080"


# ============================================================================
# APP WHITELIST
# ============================================================================

APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "chrome": "chrome",
    "vscode": "code",
    "explorer": "explorer",
    "paint": "mspaint",
}

ALIASES = {
    "calc": "calculator",
    "googlechrome": "chrome",
    "browser": "chrome",
    "code": "vscode",
    "visualstudiocode": "vscode",
    "fileexplorer": "explorer",
    "files": "explorer",
    "mspaint": "paint",
}


# ============================================================================
# GENERIC HELPERS
# ============================================================================

def _safe_float(value, default=None):
    """Convert a value to a finite float."""
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _fmt_number(value, decimals=2, default="N/A"):
    """Safely format numeric values."""
    number = _safe_float(value)
    if number is None:
        return default
    return f"{number:.{decimals}f}"


def _fmt_percent(value, decimals=2, default="N/A"):
    """Safely format percentage values."""
    number = _safe_float(value)
    if number is None:
        return default
    return f"{number:.{decimals}f}%"


# ============================================================================
# TIME
# ============================================================================

def get_time() -> str:
    """Return the current local date and time."""
    now = datetime.datetime.now().astimezone()

    return (
        now.strftime("%A, %d %B %Y, %I:%M %p")
        + f" ({now.tzname()})"
    )


# ============================================================================
# DIRECT MARKET DATA
# ============================================================================

def get_market_data() -> str:
    """
    Get the latest available NIFTY 50 market data.

    READ-ONLY.

    Intended for direct questions about:
    - NIFTY price
    - NIFTY close
    - NIFTY high
    - NIFTY low
    """

    try:
        data = get_instrument(
            "NIFTY",
            period="5d",
            interval="1d",
        )

        if data is None or data.empty:
            return (
                "MARKET DATA ERROR | "
                "NIFTY 50 data is unavailable."
            )

        latest = data.iloc[-1]
        timestamp = data.index[-1].isoformat()

        open_price = _safe_float(latest.get("Open"))
        high_price = _safe_float(latest.get("High"))
        low_price = _safe_float(latest.get("Low"))
        close_price = _safe_float(latest.get("Close"))
        volume = _safe_float(latest.get("Volume"), 0.0)

        if close_price is None:
            return (
                "MARKET DATA ERROR | "
                "NIFTY close price is unavailable."
            )

        return (
            "VERIFIED NIFTY 50 MARKET DATA | "
            "SOURCE=Yahoo Finance | "
            f"Open={_fmt_number(open_price)} | "
            f"High={_fmt_number(high_price)} | "
            f"Low={_fmt_number(low_price)} | "
            f"Close={_fmt_number(close_price)} | "
            f"Volume={volume:,.0f} | "
            f"DATA_TIMESTAMP={timestamp}"
        )

    except Exception as e:
        return (
            "MARKET DATA ERROR | "
            f"Unable to retrieve NIFTY 50 data: {e}"
        )


# ============================================================================
# EVIDENCE-GROUNDED MARKET ANALYSIS
# ============================================================================
# CACHED MARKET LAB AVAILABILITY (NO NETWORK)
# ============================================================================

def _load_latest_market_lab_report():
    """Return the newest saved Market Lab report, or None. Cache-first only."""
    try:
        from market_lab.market_lab_data import CACHE_DIR

        report_dir = Path(CACHE_DIR) / "market_lab"
        files = sorted(
            report_dir.glob("market_lab_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        for path in files:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    report = json.load(handle)
            except (OSError, ValueError):
                continue

            if isinstance(report, dict) and report:
                return report
    except Exception:
        return None

    return None


# Saved-report flags that back the scanner-unavailable matrix rows.
LAB_AVAILABILITY_MAP = {
    "INDIA_VIX": "india_vix",
    "MARKET_WIDE_VOLATILITY_REGIME": "volatility_engine",
    "SECTOR_STRENGTH": "sector_engine",
    "DERIVATIVES_OI": "derivatives_engine",
    "OPTIONS_IV": "nifty_options",
    "PUT_CALL_RATIO": "nifty_options",
    "MAX_PAIN": "nifty_options",
    "INSTITUTIONAL_FLOW": "institutional_flow",
    "EVENT_RISK": "event_risk_engine",
}

LAB_REPORT_LIVE_FLAGS = {"AVAILABLE", "READY"}


def _merge_lab_availability(availability, lab_report):
    """
    Fill scanner-unavailable rows from the latest saved Market Lab report.

    A row only flips to AVAILABLE when the report itself confirms it; the
    report timestamp is printed alongside so staleness stays visible.
    """
    if not lab_report:
        return availability

    lab_flags = lab_report.get("data_availability") or {}

    for key, flag_key in LAB_AVAILABILITY_MAP.items():
        if key in availability and str(
            lab_flags.get(flag_key, "")
        ).upper() in LAB_REPORT_LIVE_FLAGS:
            availability[key] = "AVAILABLE"

    return availability


# ============================================================================
# CACHE-FIRST MARKET ANALYSIS (report-backed and scanner-backed)
# ============================================================================

def _report_return(returns, key):
    """Read a NIFTY/BANKNIFTY return from a saved report.

    Saved Market Lab reports use 1D/5D/20D/60D keys; the scanner summary uses
    return_1d/return_5d/... keys. This supports both without inventing values.
    """
    if not isinstance(returns, dict):
        return None
    short = key.split("_")[-1]  # return_20d -> 20d
    for candidate in (key, short, short.upper()):
        if candidate in returns:
            return returns.get(candidate)
    return None


def _build_market_analysis_from_report(lab_report):
    """Build the market-analysis snapshot from a SAVED Market Lab report.

    Cache-first and offline: never runs a scan or fetches live prices. The
    report already integrated the scanner plus VIX, sector, derivatives,
    institutional-flow and event-risk layers, so this reuses that measured
    output. Rankings that depend on the full per-stock scanner dataframe
    (momentum / relative-strength / volume-expansion) are not stored in the
    saved report and are honestly reported as NOT_AVAILABLE here.
    """
    if not isinstance(lab_report, dict) or not lab_report:
        return (
            "MARKET ANALYSIS ERROR | "
            "the saved Market Lab report is not a valid object."
        )

    generated = lab_report.get("generated", "UNKNOWN")
    market_regime = lab_report.get("market_regime", "UNKNOWN")
    nifty_returns = lab_report.get("nifty_returns", {}) or {}
    bank_nifty_returns = lab_report.get("bank_nifty_returns", {}) or {}
    breadth = lab_report.get("breadth", {}) or {}
    stocks_analyzed = lab_report.get("stocks_analyzed")
    mode = lab_report.get("mode", "")
    scanner_file = lab_report.get("scanner_file", "")
    lab_flags = lab_report.get("data_availability", {}) or {}

    output = []
    output.append("=" * 60)
    output.append("NOVA EVIDENCE-GROUNDED NSE MARKET ANALYSIS")
    output.append("=" * 60)
    output.append("ANALYSIS_STATUS=SUCCESS")
    output.append("DATA_TYPE=READ_ONLY_QUANTITATIVE_MARKET_ANALYSIS")
    output.append(
        "DATA_SOURCE=LATEST_SAVED_MARKET_LAB_REPORT (CACHE-FIRST, NO SCAN)"
    )
    output.append(f"DATA_TIMESTAMP={generated}")
    if stocks_analyzed is not None:
        output.append(f"STOCKS_ANALYZED={stocks_analyzed}")
    if mode:
        output.append(f"MODE={mode}")
    if scanner_file:
        output.append(f"SCANNER_FILE={scanner_file}")

    # EVIDENCE CONTRACT
    output.append("")
    output.append("EVIDENCE CONTRACT")
    output.append("[VERIFIED DATA]")
    output.append(
        "Values come straight from the latest saved Market Lab report, "
        "which is composed of scanner output plus measured VIX, sector, "
        "derivatives, institutional-flow and event-risk engine results."
    )
    output.append("[CALCULATED DATA]")
    output.append(
        "Technical scores, returns, breadth, volatility regime, sector "
        "strength, options context and institutional-flow metrics are the "
        "report's existing calculated values."
    )
    output.append("[INFERENCE BOUNDARY]")
    output.append(
        "Interpretations must be distinguished from measured and "
        "calculated values."
    )
    output.append("[NOT AVAILABLE]")
    output.append(
        "Full-dataframe rankings (momentum, relative strength, volume "
        "expansion) are not stored in a saved report and are reported as "
        "NOT_AVAILABLE below. Transaction-cost modeling and portfolio "
        "covariance analysis are not available anywhere in Nova."
    )
    output.append(
        "The report may be stale; the DATA_TIMESTAMP above shows its age. "
        "For a fresh scan open Market Lab and use FULL REFRESH."
    )
    output.append("Unavailable fields must not be inferred or invented.")

    # MARKET REGIME
    output.append("")
    output.append("MARKET REGIME")
    output.append(f"[CALCULATED DATA] MARKET_REGIME={market_regime}")

    # NIFTY BENCHMARK
    output.append("")
    output.append("NIFTY BENCHMARK")
    output.append("[VERIFIED/CALCULATED DATA]")
    for horizon in ("return_1d", "return_5d", "return_20d", "return_60d"):
        output.append(
            f"NIFTY_{horizon.upper()}="
            + _fmt_percent(_report_return(nifty_returns, horizon))
        )

    output.append("")
    output.append("BANK NIFTY BENCHMARK")
    output.append("[VERIFIED/CALCULATED DATA]")
    for horizon in ("return_1d", "return_5d", "return_20d", "return_60d"):
        output.append(
            f"BANKNIFTY_{horizon.upper()}="
            + _fmt_percent(_report_return(bank_nifty_returns, horizon))
        )

    # MARKET BREADTH
    output.append("")
    output.append("MARKET BREADTH")
    output.append("[CALCULATED DATA]")
    output.append(f"TOTAL_STOCKS={breadth.get('total', 'N/A')}")
    output.append(f"ADVANCING={breadth.get('advancing', 'N/A')}")
    output.append(f"DECLINING={breadth.get('declining', 'N/A')}")
    output.append(f"UNCHANGED={breadth.get('unchanged', 'N/A')}")
    output.append(
        "ADVANCE_DECLINE_RATIO="
        + _fmt_number(breadth.get("advance_decline_ratio"))
    )
    output.append(
        "ABOVE_EMA20=" + _fmt_percent(breadth.get("above_ema20_percent"))
    )
    output.append(
        "ABOVE_EMA50=" + _fmt_percent(breadth.get("above_ema50_percent"))
    )
    output.append(
        "ABOVE_EMA200=" + _fmt_percent(breadth.get("above_ema200_percent"))
    )
    output.append(
        "STRONG_UPTREND_PERCENT="
        + _fmt_percent(breadth.get("strong_uptrend_percent"))
    )
    output.append(
        "STRONG_DOWNTREND_PERCENT="
        + _fmt_percent(breadth.get("strong_downtrend_percent"))
    )

    # INDIA VIX
    vix = (lab_report.get("volatility", {}) or {}).get("india_vix", {}) or {}
    if vix:
        output.append("")
        output.append("INDIA VIX")
        if vix.get("available"):
            output.append(f"INDIA_VIX={_fmt_number(vix.get('value'))}")
            output.append(f"VIX_DIRECTION={vix.get('direction', 'N/A')}")
            output.append(
                "VIX_CHANGE_PERCENT=" + _fmt_percent(vix.get("change_percent"))
            )
            output.append(
                "VIX_PERCENTILE_1Y="
                + _fmt_number(vix.get("percentile_1y"), 0)
            )
            output.append(f"VOLATILITY_REGIME={vix.get('regime', 'N/A')}")
        else:
            output.append("INDIA_VIX=NOT_AVAILABLE")

    # DERIVATIVES CONTEXT
    derivatives = lab_report.get("derivatives", {}) or {}
    if derivatives.get("available"):
        output.append("")
        output.append("DERIVATIVES CONTEXT")
        for leg_key, label in (("nifty", "NIFTY"), ("bank_nifty", "BANKNIFTY")):
            leg = derivatives.get(leg_key, {}) or {}
            if not isinstance(leg, dict):
                continue
            pcr = leg.get("pcr", {}) or {}
            max_pain = leg.get("max_pain", {}) or {}
            underlying = leg.get("underlying", {}) or {}
            if not isinstance(pcr, dict):
                pcr = {}
            if not isinstance(max_pain, dict):
                max_pain = {}
            if not isinstance(underlying, dict):
                underlying = {}
            output.append(
                f"{label}_SPOT={_fmt_number(underlying.get('spot'))}"
                f" | {label}_OI_PCR={_fmt_number(pcr.get('oi_pcr'))}"
                f" | {label}_VOLUME_PCR={_fmt_number(pcr.get('volume_pcr'))}"
                f" | {label}_MAX_PAIN_STRIKE="
                f"{_fmt_number(max_pain.get('strike'), 0)}"
            )

    # INSTITUTIONAL FLOW (FII/DII)
    flow = lab_report.get("institutional_flow", {}) or {}
    if flow:
        output.append("")
        output.append("INSTITUTIONAL FLOW (FII/DII, INR crore)")
        if flow.get("available"):
            metrics = flow.get("metrics", {}) or {}
            output.append(
                f"FLOW_REGIME={metrics.get('flow_regime', 'N/A')}"
                f" | LATEST_DATE={metrics.get('latest_date', 'N/A')}"
            )
            for horizon in ("5d", "10d", "20d"):
                output.append(
                    f"FII_{horizon.upper()}="
                    + _fmt_number(metrics.get(f"fii_{horizon}"))
                    + f" | DII_{horizon.upper()}="
                    + _fmt_number(metrics.get(f"dii_{horizon}"))
                )
            output.append(
                "PRIMARY_VERIFIED_SESSIONS="
                + str(
                    metrics.get(
                        "primary_source_sessions_in_target_window", 0
                    )
                )
                + "/"
                + str(metrics.get("target_sessions", "?"))
            )
            if flow.get("signal_allowed", False):
                output.append("SIGNAL_ELIGIBLE=YES")
            else:
                output.append(
                    "SIGNAL_ELIGIBLE=NO ("
                    + str(flow.get("signal_reason", "not fully primary-verified"))
                    + ")"
                )
        else:
            output.append(
                "INSTITUTIONAL_FLOW=NOT_AVAILABLE ("
                + str(flow.get("reason", ""))
                + ")"
            )

    # EVENT RISK
    event = lab_report.get("event_risk_context", {}) or {}
    if event:
        output.append("")
        output.append("EVENT RISK")
        output.append(f"OVERALL_RISK={event.get('overall_risk', 'N/A')}")
        output.append(
            f"UPCOMING_EVENTS={event.get('upcoming_event_count', 0)}"
            f" | SOURCE_FRESH={event.get('source_fresh', 'N/A')}"
        )

    # TOP TECHNICAL STOCKS (from the saved report's limited list)
    output.append("")
    output.append("TOP TECHNICAL STOCKS (composite score, NOT a signal)")
    top_tech = lab_report.get("top_technical_stocks", []) or []
    if top_tech:
        for rank, stock in enumerate(top_tech[:10], start=1):
            output.append(
                f"{rank}. {stock.get('symbol', '?')} | "
                f"SCORE={_fmt_number(stock.get('technical_score'))} | "
                f"TREND={stock.get('trend', 'N/A')}"
            )
    else:
        output.append("No top technical stocks stored in the saved report.")

    # TOP FACTOR-RANKED (when the report includes the research factor layer)
    factors = lab_report.get("research_factors", {}) or {}
    ranked = factors.get("top_ranked", []) or []
    if ranked and factors.get("status") == "AVAILABLE":
        output.append("")
        output.append("TOP FACTOR-RANKED (cross-sectional z, NOT a signal)")
        for entry in ranked[:10]:
            output.append(
                f"{entry.get('rank', '?')}. {entry.get('symbol', '?')}"
                f" | composite_z={_fmt_number(entry.get('composite_z'), 3)}"
            )

    # DATA AVAILABILITY MATRIX
    output.append("")
    output.append("DATA AVAILABILITY MATRIX")
    availability = {
        "MARKET_REGIME": "AVAILABLE" if market_regime else "NOT_AVAILABLE",
        "NIFTY_RETURNS": "AVAILABLE" if nifty_returns else "NOT_AVAILABLE",
        "MARKET_BREADTH": "AVAILABLE" if breadth else "NOT_AVAILABLE",
        "TECHNICAL_RANKING": "AVAILABLE" if top_tech else "NOT_AVAILABLE",
        "MOMENTUM_RANKING": "NOT_AVAILABLE",
        "RELATIVE_STRENGTH": "NOT_AVAILABLE",
        "RELATIVE_VOLUME": "NOT_AVAILABLE",
        "TREND_CLASSIFICATION": "AVAILABLE" if top_tech else "NOT_AVAILABLE",
        "INDIA_VIX": "NOT_AVAILABLE",
        "MARKET_WIDE_VOLATILITY_REGIME": "NOT_AVAILABLE",
        "SECTOR_STRENGTH": "NOT_AVAILABLE",
        "DERIVATIVES_OI": "NOT_AVAILABLE",
        "OPTIONS_IV": "NOT_AVAILABLE",
        "PUT_CALL_RATIO": "NOT_AVAILABLE",
        "MAX_PAIN": "NOT_AVAILABLE",
        "INSTITUTIONAL_FLOW": "NOT_AVAILABLE",
        "EVENT_RISK": "NOT_AVAILABLE",
        "TRANSACTION_COST_MODEL": "NOT_AVAILABLE",
        "COVARIANCE_PORTFOLIO_MODEL": "NOT_AVAILABLE",
    }
    availability = _merge_lab_availability(availability, lab_report)
    for key, value in availability.items():
        output.append(f"{key}={value}")
    output.append("AVAILABILITY_SOURCE=LATEST_SAVED_MARKET_LAB_REPORT")
    output.append(
        "Cached Market Lab values may be stale; check DATA_TIMESTAMP above."
    )
    output.append(
        "Momentum/relative-strength/volume rankings need a full scan: open "
        "Market Lab and use FULL REFRESH for those."
    )

    # REASONING GUARDRAILS
    output.append("")
    output.append("REASONING GUARDRAILS")
    rules = [
        "Never claim data marked NOT_AVAILABLE.",
        "High relative volume does NOT prove institutional buying.",
        "A high technical score does NOT equal a BUY signal.",
        "A low technical score does NOT equal a SELL signal.",
        "Do not claim volatility conditions without measured data.",
        "Do not claim sector leadership without sector data.",
        "Do not claim derivatives positioning without OI/options data.",
        "Do not claim institutional flows without actual flow data.",
        "Distinguish measured data from analytical inference.",
        "If critical evidence is missing, say NO SETUP or "
        "INSUFFICIENT EVIDENCE.",
    ]
    for index, rule in enumerate(rules, start=1):
        output.append(f"RULE_{index}={rule}")

    # FINAL DECISION BOUNDARY
    output.append("")
    output.append("FINAL DECISION BOUNDARY")
    output.append("CURRENT_STATUS=ANALYSIS_ONLY")
    output.append("BUY_SELL_AUTHORIZATION=DISABLED")
    output.append("TRADING_EXECUTION=DISABLED")
    output.append("BROKER_CONNECTION=DISABLED")
    output.append("TECHNICAL_SCORE_IS_SIGNAL=FALSE")
    missing_layers = []
    if availability.get("INDIA_VIX") != "AVAILABLE":
        missing_layers.append("VOLATILITY")
    if availability.get("SECTOR_STRENGTH") != "AVAILABLE":
        missing_layers.append("SECTOR")
    if availability.get("DERIVATIVES_OI") != "AVAILABLE":
        missing_layers.append("DERIVATIVES")
    if availability.get("EVENT_RISK") != "AVAILABLE":
        missing_layers.append("EVENT_RISK")
    if lab_flags.get("risk_engine") != "AVAILABLE":
        missing_layers.append("RISK_MODEL")
    missing_layers.extend(
        ["TRANSACTION_COST_MODEL", "COVARIANCE_PORTFOLIO_MODEL"]
    )
    output.append("MISSING_CRITICAL_LAYERS=" + ", ".join(missing_layers))
    output.append(
        "FINAL_DECISION_RULE="
        "Do not issue a BUY or SELL solely from this report."
    )
    output.append(
        "If the requested conclusion requires unavailable data, "
        "state that the evidence is insufficient."
    )
    output.append("=" * 60)

    return "\n".join(output)


def _build_market_analysis_from_scanner(dataframe, summary, lab_report=None):
    """Build the market-analysis snapshot from a live NSE scanner run.

    This is the original scanner path, kept for when no saved report exists
    (or when a full scan is explicitly required). It still merges the
    latest saved Market Lab report into the availability matrix.
    """
    market_regime = summary.get("market_regime", "UNKNOWN")
    nifty_returns = summary.get("nifty_returns", {}) or {}
    breadth = summary.get("breadth", {}) or {}
    stocks_in_universe = summary.get("stocks_in_universe", 0)
    stocks_analyzed = summary.get("stocks_analyzed", len(dataframe))
    timestamp = summary.get("timestamp", "UNKNOWN")

    if lab_report is None:
        lab_report = _load_latest_market_lab_report()
    lab_flags = (lab_report or {}).get("data_availability") or {}

    output = []
    output.append("=" * 60)
    output.append("NOVA EVIDENCE-GROUNDED NSE MARKET ANALYSIS")
    output.append("=" * 60)
    output.append("ANALYSIS_STATUS=SUCCESS")
    output.append("DATA_TYPE=READ_ONLY_QUANTITATIVE_MARKET_ANALYSIS")
    output.append(f"DATA_TIMESTAMP={timestamp}")
    output.append(f"STOCKS_IN_UNIVERSE={stocks_in_universe}")
    output.append(f"STOCKS_ANALYZED={stocks_analyzed}")

    output.append("")
    output.append("EVIDENCE CONTRACT")
    output.append("[VERIFIED DATA]")
    output.append("Values obtained directly from the NSE scanner output.")
    output.append("[CALCULATED DATA]")
    output.append(
        "The scanner calculates technical scores, returns, breadth, "
        "momentum rankings, relative strength, volume metrics and trend "
        "classifications."
    )
    output.append("[INFERENCE BOUNDARY]")
    output.append(
        "Interpretations must be distinguished from measured and "
        "calculated values."
    )
    output.append("[NOT AVAILABLE]")
    output.append(
        "The scanner alone does not provide India VIX, sector breadth, "
        "derivatives/OI, institutional flow or event risk. The "
        "availability matrix below is filled from the latest saved Market "
        "Lab report when one exists."
    )
    output.append(
        "Transaction-cost modeling and portfolio covariance analysis are "
        "not available anywhere in Nova."
    )
    output.append("Unavailable fields must not be inferred or invented.")

    output.append("")
    output.append("MARKET REGIME")
    output.append(f"[CALCULATED DATA] MARKET_REGIME={market_regime}")
    output.append(
        "Regime is generated using the scanner's existing NIFTY-return "
        "and breadth methodology."
    )

    output.append("")
    output.append("NIFTY BENCHMARK")
    output.append("[VERIFIED/CALCULATED DATA]")
    output.append("NIFTY_RETURN_1D=" + _fmt_percent(nifty_returns.get("return_1d")))
    output.append("NIFTY_RETURN_5D=" + _fmt_percent(nifty_returns.get("return_5d")))
    output.append("NIFTY_RETURN_20D=" + _fmt_percent(nifty_returns.get("return_20d")))
    output.append("NIFTY_RETURN_60D=" + _fmt_percent(nifty_returns.get("return_60d")))

    output.append("")
    output.append("MARKET BREADTH")
    output.append("[CALCULATED DATA]")
    output.append(f"TOTAL_STOCKS={breadth.get('total', 'N/A')}")
    output.append(f"ADVANCING={breadth.get('advancing', 'N/A')}")
    output.append(f"DECLINING={breadth.get('declining', 'N/A')}")
    output.append(f"UNCHANGED={breadth.get('unchanged', 'N/A')}")
    output.append(
        "ADVANCE_DECLINE_RATIO="
        + _fmt_number(breadth.get("advance_decline_ratio"))
    )
    output.append("ABOVE_EMA20=" + _fmt_percent(breadth.get("above_ema20_percent")))
    output.append("ABOVE_EMA50=" + _fmt_percent(breadth.get("above_ema50_percent")))
    output.append("ABOVE_EMA200=" + _fmt_percent(breadth.get("above_ema200_percent")))
    output.append(
        "STRONG_UPTREND_PERCENT=" + _fmt_percent(breadth.get("strong_uptrend_percent"))
    )
    output.append(
        "STRONG_DOWNTREND_PERCENT="
        + _fmt_percent(breadth.get("strong_downtrend_percent"))
    )

    output.append("")
    output.append("DATA AVAILABILITY MATRIX")
    availability = {
        "MARKET_REGIME": "AVAILABLE",
        "NIFTY_RETURNS": "AVAILABLE",
        "MARKET_BREADTH": "AVAILABLE",
        "TECHNICAL_RANKING": "AVAILABLE",
        "MOMENTUM_RANKING": "AVAILABLE",
        "RELATIVE_STRENGTH": "AVAILABLE",
        "RELATIVE_VOLUME": "AVAILABLE",
        "TREND_CLASSIFICATION": "AVAILABLE",
        "INDIA_VIX": "NOT_AVAILABLE",
        "MARKET_WIDE_VOLATILITY_REGIME": "NOT_AVAILABLE",
        "SECTOR_STRENGTH": "NOT_AVAILABLE",
        "DERIVATIVES_OI": "NOT_AVAILABLE",
        "OPTIONS_IV": "NOT_AVAILABLE",
        "PUT_CALL_RATIO": "NOT_AVAILABLE",
        "MAX_PAIN": "NOT_AVAILABLE",
        "INSTITUTIONAL_FLOW": "NOT_AVAILABLE",
        "EVENT_RISK": "NOT_AVAILABLE",
        "TRANSACTION_COST_MODEL": "NOT_AVAILABLE",
        "COVARIANCE_PORTFOLIO_MODEL": "NOT_AVAILABLE",
    }
    availability = _merge_lab_availability(availability, lab_report)
    for key, value in availability.items():
        output.append(f"{key}={value}")
    if lab_report:
        output.append(
            "AVAILABILITY_SOURCE=SCANNER+LATEST_SAVED_MARKET_LAB_REPORT"
        )
        output.append(
            "MARKET_LAB_REPORT_TIMESTAMP="
            + str(lab_report.get("generated", "UNKNOWN"))
        )
        output.append(
            "Cached Market Lab values may be stale; check the timestamp "
            "above before relying on them."
        )
    else:
        output.append(
            "AVAILABILITY_SOURCE=SCANNER_ONLY(NO_SAVED_MARKET_LAB_REPORT_FOUND)"
        )

    output.append("")
    output.append("TOP TECHNICAL RANKINGS")
    output.append("[CALCULATED DATA]")
    technical = dataframe.sort_values("score", ascending=False).head(10)
    for rank, (_, row) in enumerate(technical.iterrows(), start=1):
        output.append(
            f"{rank}. {row['symbol']} | "
            f"PRICE={_fmt_number(row['price'])} | "
            f"SCORE={_fmt_number(row['score'])} | "
            f"TREND={row['trend']} | "
            f"RSI14={_fmt_number(row['rsi_14'])} | "
            f"RVOL={_fmt_number(row['relative_volume'])} | "
            f"RETURN20D={_fmt_percent(row['return_20d'])} | "
            f"RETURN60D={_fmt_percent(row['return_60d'])} | "
            f"RS20={_fmt_percent(row['relative_strength_20d'])}"
        )

    output.append("")
    output.append("TOP MOMENTUM")
    output.append("[CALCULATED DATA]")
    momentum = dataframe.sort_values(
        ["return_20d", "return_60d", "score"], ascending=False
    ).head(10)
    for rank, (_, row) in enumerate(momentum.iterrows(), start=1):
        output.append(
            f"{rank}. {row['symbol']} | "
            f"RETURN20D={_fmt_percent(row['return_20d'])} | "
            f"RETURN60D={_fmt_percent(row['return_60d'])} | "
            f"RSI14={_fmt_number(row['rsi_14'])} | "
            f"MACD={row['macd_condition']} | "
            f"TREND={row['trend']} | "
            f"SCORE={_fmt_number(row['score'])}"
        )

    output.append("")
    output.append("TOP RELATIVE STRENGTH")
    output.append("[CALCULATED DATA]")
    relative_strength = dataframe.sort_values(
        ["relative_strength_20d", "relative_strength_60d"], ascending=False
    ).head(10)
    for rank, (_, row) in enumerate(relative_strength.iterrows(), start=1):
        output.append(
            f"{rank}. {row['symbol']} | "
            f"RS20={_fmt_percent(row['relative_strength_20d'])} | "
            f"RS60={_fmt_percent(row['relative_strength_60d'])} | "
            f"RETURN20D={_fmt_percent(row['return_20d'])} | "
            f"RETURN60D={_fmt_percent(row['return_60d'])} | "
            f"TREND={row['trend']}"
        )

    output.append("")
    output.append("TOP VOLUME EXPANSION")
    output.append("[CALCULATED DATA]")
    volume = dataframe.sort_values(
        ["relative_volume", "score"], ascending=False
    ).head(10)
    for rank, (_, row) in enumerate(volume.iterrows(), start=1):
        output.append(
            f"{rank}. {row['symbol']} | "
            f"RVOL={_fmt_number(row['relative_volume'])} | "
            f"VOLUME_CONDITION={row['volume_condition']} | "
            f"RETURN1D={_fmt_percent(row['return_1d'])} | "
            f"RSI14={_fmt_number(row['rsi_14'])} | "
            f"TREND={row['trend']}"
        )

    output.append("")
    output.append("STRONG UPTRENDS")
    output.append("[CALCULATED DATA]")
    uptrends = dataframe[dataframe["trend"] == "STRONG_UPTREND"].sort_values(
        "score", ascending=False
    ).head(10)
    for rank, (_, row) in enumerate(uptrends.iterrows(), start=1):
        output.append(
            f"{rank}. {row['symbol']} | "
            f"PRICE={_fmt_number(row['price'])} | "
            f"SCORE={_fmt_number(row['score'])} | "
            f"RSI14={_fmt_number(row['rsi_14'])} | "
            f"RVOL={_fmt_number(row['relative_volume'])} | "
            f"RETURN20D={_fmt_percent(row['return_20d'])} | "
            f"RS20={_fmt_percent(row['relative_strength_20d'])}"
        )

    output.append("")
    output.append("REASONING GUARDRAILS")
    rules = [
        "Never claim data marked NOT_AVAILABLE.",
        "High relative volume does NOT prove institutional buying.",
        "A high technical score does NOT equal a BUY signal.",
        "A low technical score does NOT equal a SELL signal.",
        "Do not claim volatility conditions without measured data.",
        "Do not claim sector leadership without sector data.",
        "Do not claim derivatives positioning without OI/options data.",
        "Do not claim institutional flows without actual flow data.",
        "Distinguish measured data from analytical inference.",
        "If critical evidence is missing, say NO SETUP or "
        "INSUFFICIENT EVIDENCE.",
    ]
    for index, rule in enumerate(rules, start=1):
        output.append(f"RULE_{index}={rule}")

    output.append("")
    output.append("FINAL DECISION BOUNDARY")
    output.append("CURRENT_STATUS=ANALYSIS_ONLY")
    output.append("BUY_SELL_AUTHORIZATION=DISABLED")
    output.append("TRADING_EXECUTION=DISABLED")
    output.append("BROKER_CONNECTION=DISABLED")
    output.append("TECHNICAL_SCORE_IS_SIGNAL=FALSE")
    missing_layers = []
    if availability.get("INDIA_VIX") != "AVAILABLE":
        missing_layers.append("VOLATILITY")
    if availability.get("SECTOR_STRENGTH") != "AVAILABLE":
        missing_layers.append("SECTOR")
    if availability.get("DERIVATIVES_OI") != "AVAILABLE":
        missing_layers.append("DERIVATIVES")
    if availability.get("EVENT_RISK") != "AVAILABLE":
        missing_layers.append("EVENT_RISK")
    if lab_flags.get("risk_engine") != "AVAILABLE":
        missing_layers.append("RISK_MODEL")
    missing_layers.extend(
        ["TRANSACTION_COST_MODEL", "COVARIANCE_PORTFOLIO_MODEL"]
    )
    output.append("MISSING_CRITICAL_LAYERS=" + ", ".join(missing_layers))
    output.append(
        "FINAL_DECISION_RULE="
        "Do not issue a BUY or SELL solely from this scanner."
    )
    output.append(
        "If the requested conclusion requires unavailable data, "
        "state that the evidence is insufficient."
    )
    output.append("=" * 60)

    return "\n".join(output)


# ============================================================================

def get_market_analysis() -> str:
    """
    Run the NSE market scanner and return an evidence-grounded
    market-intelligence snapshot.

    READ-ONLY.

    This tool does NOT:
    - Place trades.
    - Connect to a broker.
    - Generate orders.
    - Prove institutional activity.
    - Provide derivatives positioning unless explicitly available.
    - Invent sector or volatility data.

    The output separates verified data, calculated data,
    inference boundaries and unavailable data.

    CACHE-FIRST BEHAVIOUR:
    - Tries to use the latest saved Market Lab report first.
    - Only runs the expensive NSE scanner if no saved report exists.
    - Merges scanner-computed data with report-available layers
      (India VIX, volatility regime, sector strength, derivatives,
       institutional flow, event risk).
    """

    try:
        # --------------------------------------------------------------------
        # TRY CACHE-FIRST: load latest saved Market Lab report
        # --------------------------------------------------------------------

        lab_report = _load_latest_market_lab_report()

        if lab_report is not None:
            # Use report data as the primary source (cache-first)
            return _build_market_analysis_from_report(lab_report)

        # --------------------------------------------------------------------
        # FALL BACK: run full NSE scanner (expensive, no cache)
        # --------------------------------------------------------------------

        dataframe, summary = scan_market()

        if dataframe is None or dataframe.empty:
            return (
                "MARKET ANALYSIS ERROR | "
                "The NSE scanner returned no usable stock data."
            )

        # Build analysis from scanner data (original behavior). Pass the
        # (already-loaded None) report so the helper does not reload the cache.
        return _build_market_analysis_from_scanner(dataframe, summary, lab_report)

    except Exception as e:
        return (
            "MARKET ANALYSIS ERROR | "
            f"Unable to run the NSE analysis engine: {e}"
        )


# ============================================================================
# NOVA MARKET LAB INTEGRATION
# ============================================================================

def get_market_lab_analysis(query: str = "") -> str:
    """
    Run Nova's integrated, evidence-grounded Market Lab analysis.

    READ-ONLY:
    - No broker connection.
    - No trade execution.
    - No automatic orders.
    """

    try:
        from market_lab.market_lab_brain import analyze_market_lab

        return analyze_market_lab(query=query)

    except Exception as exc:
        return (
            "MARKET LAB TOOL ERROR | "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================================
# URL VALIDATION
# ============================================================================

def _normalize_url(url: str) -> str:
    url = str(url).strip().strip("\"'")

    if not url:
        raise ValueError("empty address")

    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http and https links are allowed")

    host = parsed.hostname or ""

    if "." not in host or " " in url:
        raise ValueError("give a full domain like youtube.com")

    return url


# ============================================================================
# OPEN WEBSITE
# ============================================================================

def open_website(url: str) -> str:
    try:
        clean = _normalize_url(url)

    except ValueError as e:
        return f"Could not open website: {e}."

    try:
        if webbrowser.open(clean):
            return f"Opened {clean}."

    except Exception as e:
        return f"Could not open website: {e}"

    return "Could not open the browser."


# ============================================================================
# OPEN APP
# ============================================================================

def open_app(name: str) -> str:
    key = (
        str(name)
        .lower()
        .replace(" ", "")
        .strip()
    )

    key = ALIASES.get(key, key)

    if key not in APPS:
        return (
            f"I can't open '{name}'. "
            f"Available apps: {', '.join(APPS)}."
        )

    if sys.platform != "win32":
        return "App launching is only set up for Windows."

    try:
        result = subprocess.run(
            [
                "cmd",
                "/c",
                "start",
                "",
                APPS[key],
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    except Exception as e:
        return f"Could not open {key}: {e}"

    if result.returncode != 0:
        return f"Could not open {key}. Is it installed?"

    return f"Opened {key}."


# ============================================================================
# GOOGLE SEARCH
# ============================================================================

def search_web(query: str) -> str:
    query = str(query).strip()

    if not query:
        return "Please provide a search query."

    search_url = (
        "https://www.google.com/search?q="
        + quote(query, safe="")
    )

    try:
        if webbrowser.open(search_url):
            return f"Opened web search results for {query}."

        return "Could not open the browser."

    except Exception as e:
        return f"Could not open web search: {e}"


# ============================================================================
# YOUTUBE SEARCH
# ============================================================================

def search_youtube(query: str) -> str:
    query = str(query).strip()

    if not query:
        return "Please provide a YouTube search query."

    search_url = (
        "https://www.youtube.com/results?search_query="
        + quote(query, safe="")
    )

    try:
        if webbrowser.open(search_url):
            return f"Opened YouTube search results for {query}."

        return "Could not open the browser."

    except Exception as e:
        return f"Could not open YouTube search: {e}"


# ============================================================================
# SEARXNG WEB RESEARCH
# ============================================================================

def web_research(query: str) -> str:
    """Search through the local SearXNG instance."""

    query = str(query).strip()

    if not query:
        return "Please provide a research query."

    try:
        url = (
            f"{SEARXNG_URL}/search"
            f"?q={quote(query)}"
            f"&format=json"
            f"&language=en"
        )

        request = Request(
            url,
            headers={
                "User-Agent": "Nova/1.0 Local AI Assistant"
            },
        )

        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")

        data = json.loads(raw)

    except HTTPError as e:
        return f"SearXNG returned HTTP {e.code}."

    except URLError:
        return (
            "I can't reach local SearXNG. "
            "Make sure the SearXNG Docker container is running."
        )

    except json.JSONDecodeError:
        return "SearXNG returned invalid JSON."

    except Exception as e:
        return f"Web research failed: {e}"

    results = data.get("results", [])

    if not results:
        return f"No useful web results were found for: {query}"

    max_results = 6
    max_content = 500

    output = [
        f"Web research results for: {query}",
        "",
    ]

    for index, result in enumerate(
        results[:max_results],
        start=1,
    ):
        title = str(
            result.get("title", "Untitled") or "Untitled"
        ).strip()

        url = str(
            result.get("url", "") or ""
        ).strip()

        content = str(
            result.get("content", "") or ""
        ).strip()

        if len(content) > max_content:
            content = content[:max_content].rstrip() + "..."

        output.append(f"{index}. {title}")

        if url:
            output.append(f"URL: {url}")

        if content:
            output.append(f"Summary: {content}")

        output.append("")

    return "\n".join(output).strip()


# ============================================================================
# MORNING MARKET BRIEF (cache-first, read-only)
# ============================================================================

def _brief_age_hours(generated):
    """Hours since the saved report was generated, or None if unknown."""
    if not generated:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(str(generated))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - stamp).total_seconds() / 3600.0
    return age if age >= 0 else None


def _brief_crore(value):
    """Signed crore string; preserves None as N/A (never invents a number)."""
    number = _safe_float(value)
    if number is None:
        return "N/A"
    return f"{number:+,.2f}"


def _build_market_brief(report: dict) -> str:
    """Compose a measured-only morning brief from a saved Market Lab report.

    Pure: takes a report dict and returns text. Never fetches data, never
    scores or advises trades. Missing values stay 'N/A'; interpretation is
    labelled separately from measured values.
    """
    if not isinstance(report, dict):
        return "MARKET BRIEF ERROR | the saved report is not a valid object."

    generated = report.get("generated")
    age = _brief_age_hours(generated)
    market = report.get("market", "NSE")
    analyzed = report.get("stocks_analyzed")
    mode = report.get("mode", "")

    lines = [
        "NOVA MORNING MARKET BRIEF",
        f"Source report generated: {generated or 'unknown'}"
        + (f" (about {age:.1f}h old)" if age is not None else " (age unknown)"),
        f"Market: {market}"
        + (f" | Stocks analyzed: {analyzed}" if analyzed is not None else "")
        + (f" | Mode: {mode}" if mode else ""),
    ]

    # Staleness is a measured concern: a brief from a stale report must say
    # so instead of being presented as current.
    if age is not None and age > 24:
        lines.append(
            f"WARNING: the saved report is about {age:.1f}h old. "
            "Open Market Lab to refresh before relying on this brief."
        )
    lines.append("")

    # ---- Market regime (plain string) ----
    regime = report.get("market_regime")
    lines.append("MARKET REGIME")
    lines.append(f"  Regime: {regime if regime else 'N/A'}")
    lines.append("")

    # ---- Breadth ----
    breadth = report.get("breadth") or {}
    if breadth:
        lines.append("BREADTH")
        lines.append(
            f"  Advancing: {breadth.get('advancing', 'N/A')}"
            f" | Declining: {breadth.get('declining', 'N/A')}"
            f" | A/D ratio: {_fmt_number(breadth.get('advance_decline_ratio'))}"
        )
        lines.append(
            f"  Above EMA20: {_fmt_percent(breadth.get('above_ema20_percent'))}"
            f" | EMA50: {_fmt_percent(breadth.get('above_ema50_percent'))}"
            f" | EMA200: {_fmt_percent(breadth.get('above_ema200_percent'))}"
        )
        lines.append("")

    # ---- Volatility / India VIX ----
    vol = report.get("volatility") or {}
    vix = vol.get("india_vix") or {}
    if vix:
        lines.append("VOLATILITY")
        if vix.get("available"):
            lines.append(
                f"  India VIX: {_fmt_number(vix.get('value'))}"
                f" | {vix.get('direction', 'N/A')}"
                f" ({_fmt_percent(vix.get('change_percent'))})"
                f" | 1y percentile: {_fmt_number(vix.get('percentile_1y'), 0)}"
                f" | Regime: {vix.get('regime', 'N/A')}"
            )
        else:
            lines.append("  India VIX: not available")
        lines.append("")

    # ---- Institutional flow (FII/DII) ----
    flow = report.get("institutional_flow") or {}
    metrics = flow.get("metrics") or {}
    if flow:
        lines.append("INSTITUTIONAL FLOW (FII/DII, INR crore)")
        if flow.get("available") and metrics:
            lines.append(
                f"  Regime: {metrics.get('flow_regime', 'N/A')}"
                f" | Latest session: {metrics.get('latest_date', 'N/A')}"
                f" (age {metrics.get('latest_session_age_calendar_days', '?')}d)"
            )
            lines.append(
                f"  5D  | FII {_brief_crore(metrics.get('fii_5d'))}"
                f" | DII {_brief_crore(metrics.get('dii_5d'))}"
                f" | Combined {_brief_crore(metrics.get('combined_5d'))}"
            )
            lines.append(
                f"  10D | FII {_brief_crore(metrics.get('fii_10d'))}"
                f" | DII {_brief_crore(metrics.get('dii_10d'))}"
                f" | Combined {_brief_crore(metrics.get('combined_10d'))}"
            )
            lines.append(
                f"  20D | FII {_brief_crore(metrics.get('fii_20d'))}"
                f" | DII {_brief_crore(metrics.get('dii_20d'))}"
                f" | Combined {_brief_crore(metrics.get('combined_20d'))}"
            )
            primary = metrics.get("primary_source_sessions_in_target_window", 0)
            target = metrics.get("target_sessions", "?")
            lines.append(
                f"  Primary-verified sessions: {primary}/{target}"
                f" | Source quality: {metrics.get('source_quality', 'N/A')}"
            )
            coverage_note = metrics.get("primary_coverage_note")
            if coverage_note and not metrics.get(
                "primary_source_verified_for_target_window", False
            ):
                lines.append(f"  Coverage: {coverage_note}")
            if not flow.get("signal_allowed", False):
                reason = flow.get("signal_reason", "not fully primary-verified")
                lines.append(f"  Signal-eligible: NO ({reason})")
        else:
            reason = flow.get("reason")
            lines.append("  Not available" + (f": {reason}" if reason else ""))
        lines.append("")

    # ---- Event risk ----
    event = report.get("event_risk_context") or {}
    if event:
        lines.append("EVENT RISK")
        lines.append(
            f"  Overall: {event.get('overall_risk', 'N/A')}"
            f" | Upcoming events: {event.get('upcoming_event_count', 0)}"
            f" | Source fresh: {event.get('source_fresh', 'N/A')}"
        )
        events = event.get("upcoming_events") or []
        for item in events[:3]:
            hours = item.get("hours_until")
            when = f" in {_fmt_number(hours, 0)}h" if hours is not None else ""
            lines.append(
                f"  - {item.get('name', 'event')}"
                f" ({item.get('severity', 'N/A')}{when})"
            )
        lines.append("")

    # ---- Top technical stocks (score, explicitly NOT a signal) ----
    tech = report.get("top_technical_stocks") or []
    if tech:
        lines.append("TOP TECHNICAL STOCKS (composite score, NOT a signal)")
        for index, stock in enumerate(tech[:5], start=1):
            lines.append(
                f"  {index}. {stock.get('symbol', '?')}"
                f" | score {_fmt_number(stock.get('technical_score'), 1)}"
                f" | {stock.get('trend', 'N/A')}"
            )
        lines.append("")

    # ---- Top factor-ranked (cross-sectional z, explicitly NOT a signal) ----
    factors = report.get("research_factors") or {}
    ranked = factors.get("top_ranked") or []
    if ranked and factors.get("status") == "AVAILABLE":
        lines.append("TOP FACTOR-RANKED (cross-sectional z, NOT a signal)")
        for entry in ranked[:5]:
            lines.append(
                f"  {entry.get('rank', '?')}. {entry.get('symbol', '?')}"
                f" @ {_fmt_number(entry.get('price'))}"
                f" | composite z {_fmt_number(entry.get('composite_z'), 3)}"
            )
        lines.append("")

    # ---- Data availability gaps ----
    availability = report.get("data_availability") or {}
    gaps = [
        name for name, status in availability.items()
        if str(status).upper() not in {"AVAILABLE", "READY", "OK", "SUCCESS"}
    ]
    lines.append("DATA GAPS")
    lines.append("  " + (", ".join(sorted(gaps)) if gaps else "None reported"))
    lines.append("")

    lines.append(
        "GUARDRAILS: Analysis-only. Measured values above come straight from "
        "the saved report; any interpretation is separate. This is NOT a "
        "buy/sell signal. No broker, no orders, no execution."
    )

    return "\n".join(lines)


def get_market_brief() -> str:
    """Build the morning brief from the latest SAVED Market Lab report.

    Cache-first and read-only: never runs a scan or fetches live prices.
    """
    cache_dir = (
        Path(__file__).resolve().parent
        / "analysis"
        / "data"
        / "cache"
        / "market_lab"
    )
    try:
        files = list(cache_dir.glob("market_lab_*.json"))
    except OSError:
        files = []

    if not files:
        return (
            "No saved Market Lab report found. Open Nova Market Lab "
            "(market_lab_ui.py) once to generate a report, then ask again."
        )

    latest = max(files, key=lambda p: p.stat().st_mtime)
    try:
        with latest.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return f"MARKET BRIEF ERROR | could not read {latest.name}: {exc}"

    return _build_market_brief(report)


# ============================================================================
# TOOL REGISTRY
# ============================================================================

TOOLS = {
    "get_time": get_time,
    "get_market_data": get_market_data,
    "get_market_analysis": get_market_analysis,
    "get_market_lab_analysis": get_market_lab_analysis,
    "get_market_brief": get_market_brief,
    "open_website": open_website,
    "open_app": open_app,
    "search_web": search_web,
    "search_youtube": search_youtube,
    "web_research": web_research,
}


# ============================================================================
# TOOL SCHEMA
# ============================================================================

TOOL_SCHEMA = [
    # ------------------------------------------------------------------------
    # TIME
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": (
                "Get the current local date and time. "
                "Always use this for any time or date question."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # ------------------------------------------------------------------------
    # DIRECT MARKET DATA
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_market_data",
            "description": (
                "Get the latest available NIFTY 50 market data "
                "from Yahoo Finance. "
                "MANDATORY for direct NIFTY 50 price, open, high, "
                "low, close or volume questions. "
                "Never guess or invent a market number. "
                "Use the exact returned value."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # ------------------------------------------------------------------------
    # FULL MARKET ANALYSIS
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_market_analysis",
            "description": (
                "Run the read-only NSE market intelligence snapshot. "
                "MANDATORY for broad current Indian market analysis, "
                "including market regime, breadth, technical rankings, "
                "relative strength, strongest stocks and NSE-wide "
                "conditions. CACHE-FIRST: it reads the latest saved Market "
                "Lab report (regime, breadth, India VIX, sector strength, "
                "derivatives OI/PCR/max-pain, institutional FII/DII flow, "
                "event risk, factor-ranked names) and only runs the "
                "expensive full NSE scanner when no saved report exists; "
                "full-dataframe momentum/relative-strength/volume rankings "
                "require that scan and are otherwise reported as not "
                "available. The tool returns an evidence contract "
                "identifying verified data, calculated data and "
                "unavailable data. Never infer unavailable market "
                "information. High volume does not prove institutional "
                "activity. Technical score is NOT a BUY/SELL signal. Do not "
                "claim volatility, sector leadership, derivatives "
                "positioning, institutional flows or event risk unless the "
                "tool explicitly provides that data. This tool is "
                "read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # ------------------------------------------------------------------------
    # INTEGRATED MARKET LAB ANALYSIS
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_market_lab_analysis",
            "description": (
                "Run Nova's integrated Market Lab analysis. "
                "MANDATORY for comprehensive current Indian market "
                "interpretation involving market regime, NIFTY and "
                "BANK NIFTY returns, breadth, volatility, sectors, "
                "technical rankings, derivatives and institutional flow "
                "when available. Distinguish measured data from inference, "
                "identify conflicting evidence, and report missing or "
                "stale data. Do not invent values or claim unvalidated "
                "accuracy. Read-only: never executes trades or places orders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The specific integrated market-analysis "
                            "question. For a general assessment, ask for "
                            "the integrated Market Lab outlook."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },

    # ------------------------------------------------------------------------
    # MORNING MARKET BRIEF (CACHE-FIRST)
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_market_brief",
            "description": (
                "Build Nova's morning market brief from the latest SAVED "
                "Market Lab report. MANDATORY for a quick pre-market or "
                "start-of-day summary (regime, breadth, volatility, "
                "FII/DII institutional flow, event risk, top technical and "
                "factor-ranked stocks). Fast and cache-first: it reads an "
                "existing report and never runs a scan or fetches live "
                "prices. It reports measured values only and flags stale or "
                "missing data. It is NOT a trading signal and never gives "
                "BUY/SELL advice. If no saved report exists, say the user "
                "must open Market Lab first."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },

    # ------------------------------------------------------------------------
    # OPEN WEBSITE
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": (
                "Open a website in the browser. "
                "Use only when the user explicitly asks "
                "to open a website."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full domain, e.g. youtube.com",
                    },
                },
                "required": ["url"],
            },
        },
    },

    # ------------------------------------------------------------------------
    # OPEN APP
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Open a desktop application. Supported apps: "
                + ", ".join(APPS)
                + "."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Application name",
                    },
                },
                "required": ["name"],
            },
        },
    },

    # ------------------------------------------------------------------------
    # GOOGLE SEARCH
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Open Google search results in the browser. "
                "Use when the user explicitly wants browser search results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    },

    # ------------------------------------------------------------------------
    # YOUTUBE SEARCH
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "search_youtube",
            "description": "Search YouTube in the browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "YouTube search query",
                    },
                },
                "required": ["query"],
            },
        },
    },

    # ------------------------------------------------------------------------
    # WEB RESEARCH
    # ------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "web_research",
            "description": (
                "Search the live web through the local SearXNG "
                "search engine and return actual search results "
                "for analysis. "
                "Use this for current information, news, facts, "
                "companies, products, events and research. "
                "For direct NIFTY price questions use get_market_data. "
                "For broad quantitative Indian market analysis use "
                "get_market_analysis. "
                "For comprehensive integrated analysis use "
                "get_market_lab_analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Exact topic or question to research."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ============================================================================
# TOOL EXECUTION
# ============================================================================

def run_tool(
    name: str,
    args,
) -> str:
    """
    Safely execute a tool requested by the model.

    Tool failures are returned as text rather than raised,
    so Nova can explain the problem to the user.
    """

    fn = TOOLS.get(name)

    if fn is None:
        result = f"Unknown tool '{name}'."

    else:
        # --------------------------------------------------------------------
        # NORMALIZE ARGUMENTS
        # --------------------------------------------------------------------

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if not isinstance(args, dict):
            args = {}

        # --------------------------------------------------------------------
        # EXECUTE
        # --------------------------------------------------------------------

        try:
            result = str(fn(**args))

        except TypeError:
            result = f"Bad arguments for {name}."

        except Exception as e:
            result = f"Tool error: {e}"

    # ------------------------------------------------------------------------
    # DEBUG OUTPUT
    # ------------------------------------------------------------------------

    if DEBUG:
        print(f"[tool] {name}({args}) -> {result}")

    return result