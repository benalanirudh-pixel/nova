"""
NOVA MARKET LAB
============================================================

Central analysis gateway for Nova.

CURRENT INTELLIGENCE LAYERS
---------------------------

1. NSE Market Scanner
2. Market Regime
3. Market Breadth
4. Technical Analysis
5. Volatility
6. Sector Intelligence
7. Derivatives Intelligence

DERIVATIVES
-----------

- NIFTY options
- BANK NIFTY options
- Expiry
- ATM
- OI PCR
- Volume PCR
- Max Pain
- Put OI wall
- Call OI wall
- Support / Resistance
- ATM IV
- IV skew
- Unusual activity
- Positioning interpretation

CACHE DESIGN
------------

NORMAL:

    Uses latest cached NSE equity scan.

    Does NOT perform the expensive 2,333-stock scan.

REFRESH:

    --refresh

    Forces a complete NSE equity scan.

IMPORTANT
---------

This is an analysis / research system.

It does NOT:

    - connect to brokers
    - place trades
    - execute orders
    - create automatic orders
    - authorize live trading

Technical scores, volatility and derivatives observations
are evidence for analysis, not standalone trading signals.

============================================================
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

# Make the Nova project root importable even when this file
# is launched directly from PowerShell or another working directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ANALYSIS_DIR = (
    PROJECT_ROOT
    / "analysis"
)

DATA_DIR = (
    ANALYSIS_DIR
    / "data"
)

CACHE_DIR = (
    DATA_DIR
    / "cache"
)

SECTOR_CACHE_DIR = (
    CACHE_DIR
    / "sector"
)


# ============================================================
# MARKET SCANNER
# ============================================================

try:

    from analysis.data.market_scanner import (
        scan_market,
        calculate_breadth,
        OUTPUT_DIR as SCANNER_OUTPUT_DIR,
    )

except Exception as exc:

    print(
        f"[ERROR] Could not import market scanner: {exc}"
    )

    raise


# ============================================================
# DERIVATIVES ENGINE
# ============================================================

# Ensure the Nova project root is available for local package imports.
import sys
from pathlib import Path

NOVA_PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(NOVA_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(NOVA_PROJECT_ROOT))

try:


    from analysis.data.derivatives_engine import (
        analyze_derivatives,
    )

    DERIVATIVES_IMPORT_OK = True

except Exception as exc:

    analyze_derivatives = None

    DERIVATIVES_IMPORT_OK = False

    print(
        f"[WARNING] Derivatives engine unavailable: {exc}"
    )


# ============================================================
# INSTITUTIONAL FLOW ENGINE
# ============================================================

try:
    from analysis.data.institutional_flow_engine import (
        get_institutional_flow,
    )
    INSTITUTIONAL_FLOW_IMPORT_OK = True
    INSTITUTIONAL_FLOW_IMPORT_ERROR = None
except Exception as exc:
    get_institutional_flow = None
    INSTITUTIONAL_FLOW_IMPORT_OK = False
    INSTITUTIONAL_FLOW_IMPORT_ERROR = str(exc)


def load_institutional_flow_intelligence() -> dict[str, Any]:
    """
    Retrieve validated institutional-flow metrics for Market Lab.
    This layer is analysis-only and never executes trades.
    """
    unavailable = {
        "available": False,
        "status": "NOT AVAILABLE",
        "reason": None,
        "latest_date": None,
        "latest_source": None,
        "market_scope": None,
        "history_quality": "UNKNOWN",
        "history_sessions": 0,
        "history_fresh": False,
        "data_ready_for_market_lab": False,
        "metrics": {},
        "snapshot": {},
        "source_policy": {},
        "signal_allowed": False,
        "signal_reason": None,
        "source_quality": "UNKNOWN",
    }

    if not INSTITUTIONAL_FLOW_IMPORT_OK or get_institutional_flow is None:
        unavailable["reason"] = (
            INSTITUTIONAL_FLOW_IMPORT_ERROR
            or "Institutional-flow engine import failed."
        )
        return unavailable

    try:
        # Refresh the latest observation and calculate metrics from saved
        # history. Do not trigger a full historical backfill on every run.
        result = get_institutional_flow(
            target_sessions=20,
            save=True,
            backfill=False,
        )

        if not isinstance(result, dict):
            unavailable["reason"] = "Engine returned an invalid result."
            return unavailable

        metrics = result.get("metrics") or {}
        snapshot = result.get("snapshot") or {}
        source_policy = result.get("source_policy") or {}

        if not isinstance(metrics, dict):
            metrics = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        if not isinstance(source_policy, dict):
            source_policy = {}

        scope = metrics.get("market_scope") or snapshot.get("market_scope")
        fresh = metrics.get("history_fresh") is True
        history_ready = metrics.get("data_ready_for_market_lab") is True
        scope_consistent = metrics.get("scope_consistent") is True
        correct_scope = scope == "NSE_BSE_MSEI_COMBINED"

        ready = bool(
            result.get("ok")
            and history_ready
            and fresh
            and scope_consistent
            and correct_scope
        )

        reason = None
        if not result.get("ok"):
            reason = "The engine has no usable result."
        elif not history_ready:
            reason = "The engine has not certified the history as ready."
        elif not fresh:
            reason = "The latest institutional-flow history is stale or freshness is unverified."
        elif not scope_consistent:
            reason = "The institutional-flow history has inconsistent market scope."
        elif not correct_scope:
            reason = f"Unexpected market scope: {scope!r}"

        # Data can remain available for analysis while signal eligibility
        # is blocked when the target history window is not primary-only.
        primary_history_verified = (
            metrics.get(
                "primary_source_verified_for_target_window"
            ) is True
        )

        signal_allowed = bool(
            ready
            and primary_history_verified
        )

        signal_reason = None

        if not ready:
            signal_reason = (
                reason
                or "Institutional-flow data is not ready for analysis."
            )
        elif not primary_history_verified:
            signal_reason = (
                "Signal eligibility blocked: the target history window "
                "is not entirely primary-source verified."
            )

        return {
            "available": ready,
            "status": "READY" if ready else "NOT AVAILABLE",
            "reason": reason,
            "latest_date": metrics.get("latest_date") or snapshot.get("date"),
            "latest_source": snapshot.get("source"),
            "market_scope": scope,
            "history_quality": metrics.get("history_quality", "UNKNOWN"),
            "history_sessions": metrics.get("history_sessions", 0),
            "history_fresh": fresh,
            "latest_session_age_calendar_days": metrics.get(
                "latest_session_age_calendar_days"
            ),
            "data_ready_for_market_lab": history_ready,
            "scope_consistent": scope_consistent,
            "metrics": metrics,
            "snapshot": snapshot,
            "source_policy": source_policy,
            "signal_allowed": signal_allowed,
            "signal_reason": signal_reason,
            "source_quality": metrics.get(
                "source_quality",
                "UNKNOWN",
            ),
        }

    except Exception as exc:
        unavailable["reason"] = f"{type(exc).__name__}: {exc}"
        return unavailable


# ============================================================
# RISK ENGINE
# ============================================================

try:
    from analysis.data.risk_engine import (
        build_market_risk_context,
    )

    RISK_ENGINE_IMPORT_OK = True
    RISK_ENGINE_IMPORT_ERROR = None

except Exception as exc:
    build_market_risk_context = None
    RISK_ENGINE_IMPORT_OK = False
    RISK_ENGINE_IMPORT_ERROR = str(exc)

# ============================================================
# EVENT RISK ENGINE
# ============================================================

try:
    from analysis.data.event_risk_engine import (
        build_event_risk_context,
    )

    EVENT_RISK_ENGINE_IMPORT_OK = True
    EVENT_RISK_ENGINE_IMPORT_ERROR = None

except Exception as exc:
    build_event_risk_context = None
    EVENT_RISK_ENGINE_IMPORT_OK = False
    EVENT_RISK_ENGINE_IMPORT_ERROR = str(exc)

# ============================================================
# RESEARCH FACTOR ENGINE
# ============================================================

try:
    from analysis.data.research_factor_engine import (
        build_research_factors,
    )

    RESEARCH_FACTOR_ENGINE_IMPORT_OK = True
    RESEARCH_FACTOR_ENGINE_IMPORT_ERROR = None

except Exception as exc:
    build_research_factors = None
    RESEARCH_FACTOR_ENGINE_IMPORT_OK = False
    RESEARCH_FACTOR_ENGINE_IMPORT_ERROR = str(exc)

# ============================================================
# EVENT CALENDAR INPUT
# ============================================================

# This file must be populated from a source you have actually checked.
# Missing or incomplete calendar data deliberately remains UNKNOWN.
EVENT_CALENDAR_FILE = DATA_DIR / "event_calendar.json"


def load_event_risk_context() -> dict[str, Any]:
    """Load a user-maintained, source-attributed event calendar safely."""
    unavailable = {
        "engine": "Nova Event Risk Engine",
        "status": "NOT_AVAILABLE",
        "overall_risk": "UNKNOWN",
        "overall_risk_score": None,
        "upcoming_event_count": 0,
        "upcoming_events": [],
        "warnings": [],
        "calendar_file": str(EVENT_CALENDAR_FILE),
        "decision_policy": {
            "event_risk_is_a_buy_sell_signal": False,
            "buy_sell_authorization": False,
            "trading_execution": False,
        },
    }

    if not EVENT_RISK_ENGINE_IMPORT_OK or build_event_risk_context is None:
        unavailable["warnings"].append(
            EVENT_RISK_ENGINE_IMPORT_ERROR
            or "Event risk engine import failed."
        )
        return unavailable

    if not EVENT_CALENDAR_FILE.exists():
        context = build_event_risk_context(
            events=[],
            source_checked_at=None,
            calendar_complete=False,
        )
        context["calendar_file"] = str(EVENT_CALENDAR_FILE)
        context.setdefault("warnings", []).insert(
            0,
            "Event calendar file not found; create it only after checking a reliable calendar source.",
        )
        return context

    try:
        with EVENT_CALENDAR_FILE.open("r", encoding="utf-8") as file:
            calendar = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        context = build_event_risk_context(
            events=[],
            source_checked_at=None,
            calendar_complete=False,
        )
        context["calendar_file"] = str(EVENT_CALENDAR_FILE)
        context.setdefault("warnings", []).insert(
            0,
            f"Could not read event calendar file: {type(exc).__name__}: {exc}",
        )
        return context

    if not isinstance(calendar, dict):
        calendar = {}

    events = calendar.get("events", [])
    if not isinstance(events, list):
        events = None

    context = build_event_risk_context(
        events=events,
        source_checked_at=calendar.get("source_checked_at"),
        # Never infer completeness from an empty event list.
        calendar_complete=calendar.get("calendar_complete") is True,
    )
    context["calendar_file"] = str(EVENT_CALENDAR_FILE)
    context["calendar_source_name"] = calendar.get("source_name")
    context["calendar_source_url"] = calendar.get("source_url")
    return context

# ============================================================
# EXACT SCANNER CACHE DIRECTORY
# ============================================================

SCANNER_CACHE_DIR = (
    SCANNER_OUTPUT_DIR
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_MARKET = "NSE"

TOP_TECHNICAL_STOCKS = 10

TOP_SECTORS = 5


# ============================================================
# DECISION / SAFETY POLICY
# ============================================================

TECHNICAL_SCORE_IS_SIGNAL = False

VOLATILITY_IS_SIGNAL = False

BUY_SELL_AUTHORIZATION = False

TRADING_EXECUTION = False

BROKER_CONNECTION = False

AUTOMATIC_ORDERS = False


# ============================================================
# BASIC HELPERS
# ============================================================

def now_iso() -> str:

    return (
        datetime
        .now()
        .astimezone()
        .isoformat()
    )


def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:

    try:

        if value is None:
            return default

        if isinstance(
            value,
            pd.Series,
        ):

            if value.empty:
                return default

            value = value.iloc[0]

        if isinstance(
            value,
            pd.DataFrame,
        ):

            if value.empty:
                return default

            value = value.iloc[0, 0]

        if isinstance(
            value,
            np.ndarray,
        ):

            if value.size == 0:
                return default

            value = (
                value
                .reshape(-1)[0]
            )

        if isinstance(
            value,
            str,
        ):

            value = (
                value
                .replace(",", "")
                .replace("%", "")
                .strip()
            )

            if not value:
                return default

            if value.upper() in {
                "-",
                "--",
                "NA",
                "N/A",
                "NULL",
                "NONE",
            }:

                return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except Exception:

        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:

    number = safe_float(
        value
    )

    if number is None:
        return default

    return int(number)


def clean_text(
    value: Any,
    default: str = "",
) -> str:

    if value is None:
        return default

    try:

        if pd.isna(value):
            return default

    except Exception:

        pass

    return str(value).strip()


def normalize_key(
    value: Any,
) -> str:

    text = clean_text(
        value
    ).lower()

    output = []

    for character in text:

        if character.isalnum():

            output.append(
                character
            )

        else:

            output.append("_")

    return (
        "".join(output)
        .strip("_")
    )


def find_column(
    dataframe: pd.DataFrame,
    *candidates: str,
) -> str | None:

    if (
        dataframe is None
        or dataframe.empty
    ):

        return None

    normalized = {
        normalize_key(column):
            column
        for column
        in dataframe.columns
    }

    for candidate in candidates:

        key = normalize_key(
            candidate
        )

        if key in normalized:

            return normalized[key]

    return None


def latest_file(
    directory: Path,
    prefix: str,
) -> Path | None:

    if not directory.exists():
        return None

    files = list(
        directory.glob(
            f"{prefix}_*.csv"
        )
    )

    if not files:
        return None

    files.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return files[0]


def format_number(
    value: Any,
    decimals: int = 2,
) -> str:

    number = safe_float(
        value
    )

    if number is None:
        return "N/A"

    return (
        f"{number:,.{decimals}f}"
    )


def format_percent(
    value: Any,
    decimals: int = 2,
) -> str:

    number = safe_float(
        value
    )

    if number is None:
        return "N/A"

    return (
        f"{number:.{decimals}f}%"
    )


def format_strike(
    value: Any,
) -> str:

    number = safe_float(
        value
    )

    if number is None:
        return "N/A"

    return (
        f"{number:.0f}"
    )


# ============================================================
# MARKET SCAN CACHE
# ============================================================


def load_latest_market_scan() -> tuple[
    pd.DataFrame | None,
    Path | None,
]:
    """
    Load the newest scanner CSV only when its cache is fresh.

    A cache older than 16 hours is rejected so the caller can
    run the existing full market scanner instead.

    This function does not delete old cache files or modify
    scanner calculations.
    """

    max_cache_age_hours = 16

    if not SCANNER_CACHE_DIR.exists():
        print(
            f"Scanner cache directory not found: "
            f"{SCANNER_CACHE_DIR}"
        )
        return None, None

    files = sorted(
        SCANNER_CACHE_DIR.glob("market_scan_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        print("No cached market scan found.")
        return None, None

    latest = files[0]

    print()
    print(f"Latest market scan: {latest.name}")

    # Reject stale cache rather than silently treating it as current.
    try:
        modified_at = datetime.fromtimestamp(latest.stat().st_mtime)
        age_hours = (
            datetime.now() - modified_at
        ).total_seconds() / 3600.0

    except (OSError, OverflowError, ValueError) as exc:
        print(f"Could not validate cache timestamp: {exc}")
        print("Rejecting cache; a fresh scan will be attempted.")
        return None, latest

    if age_hours < 0:
        print(
            "Cache timestamp is in the future. "
            "Rejecting cache and attempting a fresh scan."
        )
        return None, latest

    if age_hours > max_cache_age_hours:
        print(
            f"Cached market scan is stale "
            f"({age_hours:.1f} hours old; "
            f"limit is {max_cache_age_hours} hours)."
        )
        print("A fresh market scan will be attempted.")
        return None, latest

    try:
        dataframe = pd.read_csv(latest)

    except Exception as exc:
        print(f"Could not read cached market scan: {exc}")
        print("A fresh market scan will be attempted.")
        return None, latest

    if dataframe.empty:
        print("Cached market scan is empty.")
        print("A fresh market scan will be attempted.")
        return None, latest

    print(
        f"Using fresh cached market scan "
        f"({len(dataframe):,} stocks; "
        f"{age_hours:.1f} hours old)."
    )

    return dataframe, latest



def load_latest_market_scan_any_age() -> tuple[
    pd.DataFrame | None,
    Path | None,
]:
    """
    Load the newest scanner CSV regardless of age.

    Used only by live-only mode: the 16-hour freshness gate is skipped
    because the caller only wants cheap live layers (index, derivatives,
    flow, event, risk) recomputed over whatever cached universe exists.
    Scanner-derived sections are still labelled with the scan file and
    its age so staleness stays visible; nothing is presented as current
    when it is not.
    """

    if not SCANNER_CACHE_DIR.exists():
        print(
            f"Scanner cache directory not found: "
            f"{SCANNER_CACHE_DIR}"
        )
        return None, None

    files = sorted(
        SCANNER_CACHE_DIR.glob("market_scan_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        print("No cached market scan found.")
        return None, None

    latest = files[0]

    print()
    print(f"Latest market scan: {latest.name}")

    try:
        modified_at = datetime.fromtimestamp(latest.stat().st_mtime)
        age_hours = (
            datetime.now() - modified_at
        ).total_seconds() / 3600.0
    except (OSError, OverflowError, ValueError) as exc:
        print(f"Could not validate cache timestamp: {exc}")
        return None, latest

    try:
        dataframe = pd.read_csv(latest)

    except Exception as exc:
        print(f"Could not read cached market scan: {exc}")
        return None, latest

    if dataframe.empty:
        print("Cached market scan is empty.")
        return None, latest

    print(
        f"Using cached market scan for live-only mode "
        f"({len(dataframe):,} stocks; "
        f"{age_hours:.1f} hours old; "
        f"scanner sections NOT refreshed)."
    )

    return dataframe, latest



# ============================================================
# MARKET REGIME SIDECAR
# ============================================================

def regime_sidecar_path(
    scan_file: Path,
) -> Path:

    return scan_file.with_name(
        scan_file.stem
        + "_regime.json"
    )


def extract_regime_from_object(
    obj: Any,
) -> str | None:
    """
    Safely find market_regime/regime inside the scanner summary.

    Handles dict/list structures without evaluating Pandas
    Series as booleans.
    """

    if isinstance(
        obj,
        dict,
    ):

        for key, value in obj.items():

            normalized = normalize_key(
                key
            )

            if normalized in {
                "market_regime",
                "market_regime_label",
                "regime",
            }:

                result = clean_text(
                    value
                ).upper()

                if result:
                    return result

        for value in obj.values():

            result = (
                extract_regime_from_object(
                    value
                )
            )

            if result:
                return result

    elif isinstance(
        obj,
        (list, tuple),
    ):

        for value in obj:

            result = (
                extract_regime_from_object(
                    value
                )
            )

            if result:
                return result

    return None


def save_regime_sidecar(
    scan_file: Path | None,
    regime: str | None,
) -> None:

    if scan_file is None:
        return

    if not regime:
        return

    try:

        path = regime_sidecar_path(
            scan_file
        )

        payload = {

            "market":
                DEFAULT_MARKET,

            "market_regime":
                regime,

            "saved_at":
                now_iso(),

            "source_scan":
                str(
                    scan_file
                ),
        }

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                payload,
                file,
                indent=2,
            )

    except Exception as exc:

        print(
            f"[WARNING] Could not save regime sidecar: "
            f"{exc}"
        )


def load_cached_regime(
    scan_file: Path | None,
) -> str | None:

    if scan_file is None:
        return None

    path = regime_sidecar_path(
        scan_file
    )

    if not path.exists():
        return None

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            payload = json.load(
                file
            )

        regime = clean_text(
            payload.get(
                "market_regime"
            )
        ).upper()

        return regime or None

    except Exception:

        return None


# ============================================================
# BREADTH
# ============================================================

def build_market_breadth(
    dataframe: pd.DataFrame,
) -> dict[str, Any]:

    try:

        breadth = calculate_breadth(
            dataframe
        )

        if not isinstance(
            breadth,
            dict,
        ):

            breadth = {}

    except Exception as exc:

        print(
            f"[WARNING] Breadth calculation failed: "
            f"{exc}"
        )

        breadth = {}

    cleaned = {}

    for key, value in breadth.items():

        number = safe_float(
            value
        )

        if number is not None:

            cleaned[key] = number

        else:

            text = clean_text(
                value
            )

            if text:

                cleaned[key] = text

    # --------------------------------------------------------
    # Normalize key names used by Market Lab
    # --------------------------------------------------------

    if "above_ema20_pct" in cleaned:
        cleaned[
            "above_ema20_percent"
        ] = cleaned[
            "above_ema20_pct"
        ]

    if "above_ema50_pct" in cleaned:
        cleaned[
            "above_ema50_percent"
        ] = cleaned[
            "above_ema50_pct"
        ]

    if "above_ema200_pct" in cleaned:
        cleaned[
            "above_ema200_percent"
        ] = cleaned[
            "above_ema200_pct"
        ]

    if "strong_uptrend_pct" in cleaned:
        cleaned[
            "strong_uptrend_percent"
        ] = cleaned[
            "strong_uptrend_pct"
        ]

    if "strong_downtrend_pct" in cleaned:
        cleaned[
            "strong_downtrend_percent"
        ] = cleaned[
            "strong_downtrend_pct"
        ]

    # --------------------------------------------------------
    # Ensure A/D ratio is always scalar and valid
    # --------------------------------------------------------

    advancing = safe_int(
        cleaned.get(
            "advancing",
            0,
        )
    )

    declining = safe_int(
        cleaned.get(
            "declining",
            0,
        )
    )

    unchanged = safe_int(
        cleaned.get(
            "unchanged",
            0,
        )
    )

    cleaned[
        "advancing"
    ] = advancing

    cleaned[
        "declining"
    ] = declining

    cleaned[
        "unchanged"
    ] = unchanged

    if declining > 0:

        cleaned[
            "ad_ratio"
        ] = (
            advancing
            / declining
        )

    else:

        cleaned[
            "ad_ratio"
        ] = None

    return cleaned


# ============================================================
# FALLBACK REGIME
# ============================================================

def fallback_market_regime(
    breadth: dict[str, Any],
    nifty_returns: dict[str, Any],
) -> str:

    above_ema20 = safe_float(
        breadth.get(
            "above_ema20_percent"
        )
    )

    above_ema50 = safe_float(
        breadth.get(
            "above_ema50_percent"
        )
    )

    strong_up = safe_float(
        breadth.get(
            "strong_uptrend_percent"
        )
    )

    strong_down = safe_float(
        breadth.get(
            "strong_downtrend_percent"
        )
    )

    return_20d = safe_float(
        nifty_returns.get(
            "20D"
        )
    )

    return_60d = safe_float(
        nifty_returns.get(
            "60D"
        )
    )

    if (
        above_ema20 is not None
        and above_ema50 is not None
        and strong_down is not None
        and return_20d is not None
        and return_60d is not None
        and above_ema20 < 25
        and above_ema50 < 35
        and strong_down > 40
        and return_20d < 0
        and return_60d < 0
    ):

        return "BEARISH"

    if (
        above_ema20 is not None
        and strong_down is not None
        and return_20d is not None
        and above_ema20 < 40
        and strong_down > 30
        and return_20d < 0
    ):

        return "MILDLY_BEARISH"

    if (
        above_ema20 is not None
        and above_ema50 is not None
        and strong_up is not None
        and return_20d is not None
        and above_ema20 > 60
        and above_ema50 > 60
        and strong_up > 30
        and return_20d > 0
    ):

        return "BULLISH"

    if (
        above_ema20 is not None
        and strong_up is not None
        and return_20d is not None
        and above_ema20 > 50
        and strong_up > 20
        and return_20d > 0
    ):

        return "MILDLY_BULLISH"

    return "NEUTRAL"


# ============================================================
# INDEX DATA
# ============================================================

def get_index_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame | None:

    try:

        import yfinance as yf

        dataframe = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
        )

        if (
            dataframe is None
            or dataframe.empty
        ):

            return None

        if isinstance(
            dataframe.columns,
            pd.MultiIndex,
        ):

            dataframe.columns = [
                item[0]
                if isinstance(
                    item,
                    tuple,
                )
                else item
                for item
                in dataframe.columns
            ]

        dataframe.columns = [
            str(item)
            for item
            in dataframe.columns
        ]

        return dataframe

    except Exception as exc:

        print(
            f"[WARNING] Index data error for "
            f"{symbol}: {exc}"
        )

        return None


def calculate_index_returns(
    symbol: str,
) -> dict[str, float | None]:

    result = {
        "1D": None,
        "5D": None,
        "20D": None,
        "60D": None,
    }

    dataframe = get_index_history(
        symbol
    )

    if (
        dataframe is None
        or dataframe.empty
    ):

        return result

    close_column = find_column(
        dataframe,
        "Close",
    )

    if close_column is None:
        return result

    close = pd.to_numeric(
        dataframe[
            close_column
        ],
        errors="coerce",
    ).dropna()

    if close.empty:
        return result

    latest = safe_float(
        close.iloc[-1]
    )

    if latest is None:
        return result

    for label, periods in {
        "1D": 1,
        "5D": 5,
        "20D": 20,
        "60D": 60,
    }.items():

        if len(close) <= periods:
            continue

        previous = safe_float(
            close.iloc[
                -1 - periods
            ]
        )

        if (
            previous is not None
            and previous != 0
        ):

            result[label] = (
                (
                    latest
                    - previous
                )
                / previous
            ) * 100

    return result


# ============================================================
# NIFTY SNAPSHOT
# ============================================================

def _dhan_index_overrides() -> dict[str, Any]:
    """Optional live index snapshots from the Dhan adapter (read-only).

    Returns {} when Dhan is unconfigured or any call fails, so report
    generation falls back to the existing NSE/Yahoo engines unchanged.
    """
    try:
        from analysis.data.dhan_feed import (
            is_configured,
            get_report_index_snapshot,
        )

        if not is_configured():
            return {}
        snapshot = get_report_index_snapshot()
        return snapshot if isinstance(snapshot, dict) else {}
    except Exception:
        return {}


def _apply_dhan_override(nifty_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Override the NIFTY snapshot with a live Dhan quote when available.

    Analysis-only, opt-in: when Dhan is unconfigured or returns no usable NIFTY
    quote, the original snapshot is returned unchanged.
    """
    try:
        dhan_nifty = _dhan_index_overrides().get("nifty")
    except Exception:
        dhan_nifty = None
    if isinstance(dhan_nifty, dict) and dhan_nifty.get("available"):
        return dhan_nifty
    return nifty_snapshot


def _apply_dhan_volatility_overrides(volatility: dict[str, Any]) -> dict[str, Any]:
    """Optionally override BANK NIFTY price and India VIX value/change with a
    live Dhan quote. Analysis-only, opt-in.

    - BANK NIFTY: sets bank_nifty.price (+ source DHAN_LIVE); the engine's ATR /
      realized-vol / regime fields are preserved.
    - India VIX: sets india_vix.value and change_percent; the engine's
      percentile_1y / regime / direction are preserved (Dhan has none) and a
      note records the split source.
    Unconfigured / unavailable / any error returns the original unchanged.
    """
    if not isinstance(volatility, dict):
        return volatility
    try:
        overrides = _dhan_index_overrides()
    except Exception:
        overrides = {}
    if not isinstance(overrides, dict) or not overrides:
        return volatility

    bank = overrides.get("bank_nifty")
    vix = overrides.get("india_vix")
    bank_ok = isinstance(bank, dict) and bank.get("available") and bank.get("price") is not None
    vix_ok = isinstance(vix, dict) and vix.get("available") and vix.get("value") is not None
    if not bank_ok and not vix_ok:
        return volatility

    merged = dict(volatility)

    if bank_ok:
        leg = dict(merged.get("bank_nifty") or {})
        leg["price"] = bank.get("price")
        leg["source"] = "DHAN_LIVE"
        if bank.get("last_trade_time") is not None:
            leg["last_trade_time"] = bank.get("last_trade_time")
        merged["bank_nifty"] = leg

    if vix_ok:
        leg = dict(merged.get("india_vix") or {})
        leg["available"] = True
        leg["value"] = vix.get("value")
        if vix.get("change_percent") is not None:
            leg["change_percent"] = vix.get("change_percent")
        leg["source"] = "DHAN_LIVE"
        leg["note"] = (
            "value/change from Dhan; 1y percentile/regime from volatility engine"
        )
        if vix.get("last_trade_time") is not None:
            leg["last_trade_time"] = vix.get("last_trade_time")
        merged["india_vix"] = leg

    return merged


def get_nifty_snapshot() -> dict[str, Any]:

    dataframe = get_index_history(
        "^NSEI",
        period="1mo",
        interval="1d",
    )

    if (
        dataframe is None
        or dataframe.empty
    ):

        return {
            "available": False
        }

    close_column = find_column(
        dataframe,
        "Close",
    )

    if close_column is None:

        return {
            "available": False
        }

    close = pd.to_numeric(
        dataframe[
            close_column
        ],
        errors="coerce",
    ).dropna()

    if close.empty:

        return {
            "available": False
        }

    latest = safe_float(
        close.iloc[-1]
    )

    previous = (
        safe_float(
            close.iloc[-2]
        )
        if len(close) >= 2
        else None
    )

    result = {

        "available":
            True,

        "price":
            latest,

        "change_percent":
            (
                (
                    (
                        latest
                        - previous
                    )
                    / previous
                )
                * 100
                if (
                    latest is not None
                    and previous is not None
                    and previous != 0
                )
                else None
            ),
    }

    for label in (
        "Open",
        "High",
        "Low",
    ):

        column = find_column(
            dataframe,
            label,
        )

        if column is not None:

            result[
                label.lower()
            ] = safe_float(
                dataframe[
                    column
                ].iloc[-1]
            )

    return result


# ============================================================
# VOLATILITY
# ============================================================

def calculate_atr(
    dataframe: pd.DataFrame,
    window: int = 14,
) -> tuple[
    float | None,
    float | None,
]:

    high_column = find_column(
        dataframe,
        "High",
    )

    low_column = find_column(
        dataframe,
        "Low",
    )

    close_column = find_column(
        dataframe,
        "Close",
    )

    if (
        high_column is None
        or low_column is None
        or close_column is None
    ):

        return None, None

    high = pd.to_numeric(
        dataframe[
            high_column
        ],
        errors="coerce",
    )

    low = pd.to_numeric(
        dataframe[
            low_column
        ],
        errors="coerce",
    )

    close = pd.to_numeric(
        dataframe[
            close_column
        ],
        errors="coerce",
    )

    previous_close = (
        close.shift(1)
    )

    true_range = pd.concat(
        [
            high - low,

            (
                high
                - previous_close
            ).abs(),

            (
                low
                - previous_close
            ).abs(),
        ],
        axis=1,
    ).max(
        axis=1
    )

    atr = (
        true_range
        .rolling(window)
        .mean()
        .iloc[-1]
    )

    atr_value = safe_float(
        atr
    )

    close_value = safe_float(
        close.iloc[-1]
    )

    if (
        atr_value is None
        or close_value in (
            None,
            0,
        )
    ):

        return (
            atr_value,
            None,
        )

    atr_percent = (
        atr_value
        / close_value
    ) * 100

    return (
        atr_value,
        safe_float(
            atr_percent
        ),
    )


def calculate_realized_volatility(
    close: pd.Series,
    window: int,
) -> float | None:

    close = pd.to_numeric(
        close,
        errors="coerce",
    ).dropna()

    if len(close) < window + 1:
        return None

    returns = np.log(
        close
        / close.shift(1)
    ).dropna()

    if len(returns) < window:
        return None

    value = (
        returns
        .rolling(window)
        .std()
        .iloc[-1]
        * np.sqrt(252)
        * 100
    )

    return safe_float(
        value
    )


def calculate_vix_snapshot() -> dict[str, Any]:

    dataframe = get_index_history(
        "^INDIAVIX",
        period="1y",
        interval="1d",
    )

    if (
        dataframe is None
        or dataframe.empty
    ):

        return {
            "available": False
        }

    close_column = find_column(
        dataframe,
        "Close",
    )

    if close_column is None:

        return {
            "available": False
        }

    close = pd.to_numeric(
        dataframe[
            close_column
        ],
        errors="coerce",
    ).dropna()

    if close.empty:

        return {
            "available": False
        }

    current = safe_float(
        close.iloc[-1]
    )

    previous = (
        safe_float(
            close.iloc[-2]
        )
        if len(close) >= 2
        else None
    )

    if current is None:

        return {
            "available": False
        }

    if current < 13:

        regime = "LOW"

    elif current < 18:

        regime = "MODERATE"

    elif current < 25:

        regime = "HIGH"

    else:

        regime = "EXTREME"

    if previous is None:

        direction = "UNKNOWN"

    elif current > previous:

        direction = "RISING"

    elif current < previous:

        direction = "FALLING"

    else:

        direction = "FLAT"

    percentile = None

    if len(close) >= 20:

        percentile = safe_float(
            (
                close
                <= current
            ).mean()
            * 100
        )

    return {

        "available":
            True,

        "value":
            current,

        "change_percent":
            (
                (
                    (
                        current
                        - previous
                    )
                    / previous
                )
                * 100
                if (
                    previous is not None
                    and previous != 0
                )
                else None
            ),

        "percentile_1y":
            percentile,

        "regime":
            regime,

        "direction":
            direction,
    }


def build_volatility_block(
    dataframe: pd.DataFrame | None,
) -> dict[str, Any]:

    if (
        dataframe is None
        or dataframe.empty
    ):

        return {
            "available": False
        }

    close_column = find_column(
        dataframe,
        "Close",
    )

    if close_column is None:

        return {
            "available": False
        }

    close = pd.to_numeric(
        dataframe[
            close_column
        ],
        errors="coerce",
    ).dropna()

    if close.empty:

        return {
            "available": False
        }

    price = safe_float(
        close.iloc[-1]
    )

    atr14, atr_percent = (
        calculate_atr(
            dataframe
        )
    )

    rv20 = (
        calculate_realized_volatility(
            close,
            20,
        )
    )

    rv60 = (
        calculate_realized_volatility(
            close,
            60,
        )
    )

    volatility_percentile = None

    if len(close) >= 70:

        daily_returns = (
            close
            .pct_change()
            .dropna()
        )

        rolling_vol = (
            daily_returns
            .rolling(20)
            .std()
            * np.sqrt(252)
            * 100
        ).dropna()

        if not rolling_vol.empty:

            current_vol = safe_float(
                rolling_vol.iloc[-1]
            )

            if current_vol is not None:

                volatility_percentile = (
                    (
                        rolling_vol
                        <= current_vol
                    ).mean()
                    * 100
                )

    expected_daily_move = None

    expected_daily_range = None

    if rv20 is not None:

        expected_daily_move = (
            rv20
            / np.sqrt(252)
        )

        if price is not None:

            expected_daily_range = (
                price
                * expected_daily_move
                / 100
            )

    if atr_percent is None:

        volatility_regime = (
            "UNKNOWN"
        )

    elif atr_percent < 0.8:

        volatility_regime = "LOW"

    elif atr_percent < 1.5:

        volatility_regime = (
            "MODERATE"
        )

    elif atr_percent < 2.5:

        volatility_regime = "HIGH"

    else:

        volatility_regime = (
            "EXTREME"
        )

    direction = "UNKNOWN"

    if len(close) >= 70:

        returns = (
            close
            .pct_change()
            .dropna()
        )

        short_vol = safe_float(
            returns
            .rolling(20)
            .std()
            .iloc[-1]
        )

        long_vol = safe_float(
            returns
            .rolling(60)
            .std()
            .iloc[-1]
        )

        if (
            short_vol is not None
            and long_vol is not None
        ):

            if (
                short_vol
                > long_vol * 1.10
            ):

                direction = (
                    "EXPANDING"
                )

            elif (
                short_vol
                < long_vol * 0.90
            ):

                direction = (
                    "CONTRACTING"
                )

            else:

                direction = (
                    "STABLE"
                )

    return {

        "available":
            True,

        "price":
            price,

        "atr14":
            atr14,

        "atr_percent":
            atr_percent,

        "realized_volatility_20d":
            rv20,

        "realized_volatility_60d":
            rv60,

        "volatility_percentile":
            safe_float(
                volatility_percentile
            ),

        "expected_daily_move_percent":
            safe_float(
                expected_daily_move
            ),

        "expected_daily_range":
            safe_float(
                expected_daily_range
            ),

        "volatility_regime":
            volatility_regime,

        "volatility_direction":
            direction,
    }


def load_volatility_snapshot() -> dict[str, Any]:

    print(
        "Refreshing NIFTY volatility..."
    )

    nifty = get_index_history(
        "^NSEI",
        period="1y",
        interval="1d",
    )

    print(
        "Refreshing BANK NIFTY volatility..."
    )

    bank_nifty = get_index_history(
        "^NSEBANK",
        period="1y",
        interval="1d",
    )

    return {

        "india_vix":
            calculate_vix_snapshot(),

        "nifty":
            build_volatility_block(
                nifty
            ),

        "bank_nifty":
            build_volatility_block(
                bank_nifty
            ),
    }


# ============================================================
# TECHNICAL RANKINGS
# ============================================================

def build_top_technical_stocks(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:

    if (
        dataframe is None
        or dataframe.empty
    ):

        return []

    score_column = find_column(
        dataframe,
        "technical_score",
        "score",
    )

    symbol_column = find_column(
        dataframe,
        "symbol",
        "nse_symbol",
        "ticker",
    )

    company_column = find_column(
        dataframe,
        "company_name",
        "company",
        "name",
    )

    trend_column = find_column(
        dataframe,
        "trend",
        "trend_state",
    )

    if score_column is None:
        return []

    working = dataframe.copy()

    working["_score_numeric"] = (
        pd.to_numeric(
            working[
                score_column
            ],
            errors="coerce",
        )
    )

    working = (
        working
        .dropna(
            subset=[
                "_score_numeric"
            ]
        )
        .sort_values(
            "_score_numeric",
            ascending=False,
        )
        .head(
            TOP_TECHNICAL_STOCKS
        )
    )

    result = []

    for _, row in (
        working.iterrows()
    ):

        result.append(
            {

                "symbol":
                    clean_text(
                        row.get(
                            symbol_column
                        )
                        if symbol_column
                        else ""
                    ),

                "company_name":
                    clean_text(
                        row.get(
                            company_column
                        )
                        if company_column
                        else ""
                    ),

                "technical_score":
                    safe_float(
                        row.get(
                            score_column
                        )
                    ),

                "trend":
                    clean_text(
                        row.get(
                            trend_column
                        )
                        if trend_column
                        else ""
                    ),
            }
        )

    return result


# ============================================================
# SECTOR INTELLIGENCE
# ============================================================

def load_latest_sector_report() -> tuple[
    pd.DataFrame | None,
    Path | None,
]:

    if not SECTOR_CACHE_DIR.exists():

        return None, None

    files = sorted(
        SECTOR_CACHE_DIR.glob(
            "sector_scan_*.csv"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:

        return None, None

    latest = files[0]

    try:

        dataframe = pd.read_csv(
            latest
        )

    except Exception as exc:

        print(
            f"[WARNING] Could not load sector report: "
            f"{exc}"
        )

        return None, latest

    if dataframe.empty:

        return None, latest

    return (
        dataframe,
        latest,
    )


def build_sector_intelligence(
    dataframe: pd.DataFrame | None,
) -> dict[str, Any]:

    if (
        dataframe is None
        or dataframe.empty
    ):

        return {

            "available":
                False,

            "count":
                0,

            "top_sectors":
                [],
        }

    sector_column = find_column(
        dataframe,
        "sector",
        "sector_name",
    )

    return_column = find_column(
        dataframe,
        "return_20d",
        "r20",
        "sector_return_20d",
    )

    rs_column = find_column(
        dataframe,
        "relative_strength_20d",
        "rs20",
        "sector_relative_strength_20d",
    )

    regime_column = find_column(
        dataframe,
        "regime",
        "sector_regime",
    )

    if sector_column is None:

        return {

            "available":
                False,

            "count":
                0,

            "top_sectors":
                [],
        }

    rows = []

    for _, row in (
        dataframe.iterrows()
    ):

        sector = clean_text(
            row.get(
                sector_column
            )
        )

        if not sector:
            continue

        rows.append(
            {

                "sector":
                    sector,

                "return_20d":
                    (
                        safe_float(
                            row.get(
                                return_column
                            )
                        )
                        if return_column
                        else None
                    ),

                "relative_strength_20d":
                    (
                        safe_float(
                            row.get(
                                rs_column
                            )
                        )
                        if rs_column
                        else None
                    ),

                "regime":
                    (
                        clean_text(
                            row.get(
                                regime_column
                            )
                        )
                        if regime_column
                        else ""
                    ),
            }
        )

    if not rows:

        return {

            "available":
                False,

            "count":
                0,

            "top_sectors":
                [],
        }

    sectors = pd.DataFrame(
        rows
    )

    sectors = (
        sectors
        .sort_values(
            by=[
                "relative_strength_20d",
                "return_20d",
            ],
            ascending=False,
            na_position="last",
        )
        .drop_duplicates(
            subset=[
                "sector"
            ]
        )
    )

    return {

        "available":
            True,

        "count":
            int(
                len(
                    sectors
                )
            ),

        "top_sectors":
            (
                sectors
                .head(
                    TOP_SECTORS
                )
                .to_dict(
                    orient="records"
                )
            ),
    }


# ============================================================
# DERIVATIVES
# ============================================================

def load_derivatives_intelligence() -> dict[str, Any]:
    """
    Run live derivatives analysis for NIFTY and BANKNIFTY.

    This does NOT run the expensive equity scanner.

    Both standalone derivatives reports have already been
    validated before integration.
    """

    result = {

        "available":
            False,

        "nifty":
            {
                "available":
                    False
            },

        "bank_nifty":
            {
                "available":
                    False
            },
    }

    if not DERIVATIVES_IMPORT_OK:

        return result

    # --------------------------------------------------------
    # NIFTY
    # --------------------------------------------------------

    try:

        print()
        print(
            "Refreshing NIFTY derivatives..."
        )

        nifty = analyze_derivatives(
            symbol="NIFTY",
            strike_window=20,
        )

        if isinstance(
            nifty,
            dict,
        ):

            nifty[
                "available"
            ] = True

            result[
                "nifty"
            ] = nifty

    except Exception as exc:

        print(
            f"[WARNING] NIFTY derivatives failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # BANK NIFTY
    # --------------------------------------------------------

    try:

        print()
        print(
            "Refreshing BANK NIFTY derivatives..."
        )

        bank_nifty = analyze_derivatives(
            symbol="BANKNIFTY",
            strike_window=20,
        )

        if isinstance(
            bank_nifty,
            dict,
        ):

            bank_nifty[
                "available"
            ] = True

            result[
                "bank_nifty"
            ] = bank_nifty

    except Exception as exc:

        print(
            f"[WARNING] BANK NIFTY derivatives failed: "
            f"{exc}"
        )

    result[
        "available"
    ] = (
        result[
            "nifty"
        ].get(
            "available",
            False,
        )
        or
        result[
            "bank_nifty"
        ].get(
            "available",
            False,
        )
    )

    return result


# ============================================================
# DATA AVAILABILITY
# ============================================================

def build_data_availability(
    market_dataframe: pd.DataFrame,
    sector_dataframe: pd.DataFrame | None,
    volatility: dict[str, Any],
    derivatives: dict[str, Any],
) -> dict[str, str]:

    market_available = (
        market_dataframe is not None
        and not market_dataframe.empty
    )

    sector_available = (
        sector_dataframe is not None
        and not sector_dataframe.empty
    )

    nifty_vol_available = (
        volatility
        .get(
            "nifty",
            {}
        )
        .get(
            "available",
            False,
        )
    )

    vix_available = (
        volatility
        .get(
            "india_vix",
            {}
        )
        .get(
            "available",
            False,
        )
    )

    nifty_options_available = (
        derivatives
        .get(
            "nifty",
            {}
        )
        .get(
            "available",
            False,
        )
    )

    bank_options_available = (
        derivatives
        .get(
            "bank_nifty",
            {}
        )
        .get(
            "available",
            False,
        )
    )

    return {

        "market_scanner":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "market_regime":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "nifty_returns":
            "AVAILABLE",

        "breadth":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "technical_analysis":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "momentum":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "volume":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "relative_strength":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "price_structure":
            (
                "AVAILABLE"
                if market_available
                else "NOT AVAILABLE"
            ),

        "volatility_engine":
            (
                "AVAILABLE"
                if nifty_vol_available
                else "NOT AVAILABLE"
            ),

        "india_vix":
            (
                "AVAILABLE"
                if vix_available
                else "NOT AVAILABLE"
            ),

        "realized_volatility":
            (
                "AVAILABLE"
                if volatility
                .get(
                    "nifty",
                    {}
                )
                .get(
                    "realized_volatility_20d"
                )
                is not None
                else "NOT AVAILABLE"
            ),

        "atr":
            (
                "AVAILABLE"
                if volatility
                .get(
                    "nifty",
                    {}
                )
                .get(
                    "atr14"
                )
                is not None
                else "NOT AVAILABLE"
            ),

        "volatility_percentile":
            (
                "AVAILABLE"
                if volatility
                .get(
                    "nifty",
                    {}
                )
                .get(
                    "volatility_percentile"
                )
                is not None
                else "NOT AVAILABLE"
            ),

        "expected_daily_move":
            (
                "AVAILABLE"
                if volatility
                .get(
                    "nifty",
                    {}
                )
                .get(
                    "expected_daily_move_percent"
                )
                is not None
                else "NOT AVAILABLE"
            ),

        "sector_engine":
            (
                "AVAILABLE"
                if sector_available
                else "NOT AVAILABLE"
            ),

        "sector_relative_strength":
            (
                "AVAILABLE"
                if sector_available
                else "NOT AVAILABLE"
            ),

        "sector_breadth":
            (
                "AVAILABLE"
                if sector_available
                else "NOT AVAILABLE"
            ),

        "sector_volume":
            (
                "AVAILABLE"
                if sector_available
                else "NOT AVAILABLE"
            ),

        "derivatives_engine":
            (
                "AVAILABLE"
                if derivatives.get(
                    "available",
                    False,
                )
                else "NOT AVAILABLE"
            ),

        "nifty_options":
            (
                "AVAILABLE"
                if nifty_options_available
                else "NOT AVAILABLE"
            ),

        "bank_nifty_options":
            (
                "AVAILABLE"
                if bank_options_available
                else "NOT AVAILABLE"
            ),

        "event_risk_engine":
            "NOT AVAILABLE",

        "risk_engine":
            "NOT AVAILABLE",

        "research_factor_engine":
            "NOT BUILT",
    }


# ============================================================
# MAIN MARKET LAB DATA
# ============================================================

def get_market_lab_data(
    force_refresh: bool = False,
    live_only: bool = False,
) -> dict[str, Any]:

    print()
    print("=" * 66)
    print("NOVA MARKET LAB")
    print("=" * 66)
    print()

    if live_only and force_refresh:
        raise ValueError(
            "live_only and force_refresh are mutually exclusive: "
            "live_only never runs the full NSE scan."
        )

    if live_only:
        print(
            "LIVE-ONLY MODE: cached equity scan is reused as-is; "
            "only index, derivatives, flow, event, and risk layers "
            "are refreshed."
        )
        print()

    market_dataframe = None

    market_file = None

    scanner_summary = None

    scanner_regime = None

    # --------------------------------------------------------
    # NORMAL MODE = CACHE FIRST
    # --------------------------------------------------------

    if live_only:

        (
            market_dataframe,
            market_file,
        ) = load_latest_market_scan_any_age()

        if (
            market_dataframe is None
            or market_dataframe.empty
        ):
            raise RuntimeError(
                "Live-only mode needs a cached market scan, "
                "but none was usable. Run a normal report first "
                "or use --refresh to build one."
            )

    elif not force_refresh:

        (
            market_dataframe,
            market_file,
        ) = load_latest_market_scan()

    # --------------------------------------------------------
    # FULL MARKET SCAN
    # --------------------------------------------------------

    if (
        market_dataframe is None
        or market_dataframe.empty
    ):

        if force_refresh:

            print(
                "FORCED REFRESH ENABLED."
            )

        else:

            print(
                "No cached market scan available."
            )

        print(
            "Running full NSE market scanner..."
        )

        print()

        (
            market_dataframe,
            scanner_summary,
        ) = scan_market()

        if (
            market_dataframe is None
            or market_dataframe.empty
        ):

            raise RuntimeError(
                "NSE market scanner returned no usable data."
            )

        market_file = latest_file(
            SCANNER_CACHE_DIR,
            "market_scan",
        )

        # ----------------------------------------------------
        # Use scanner's actual regime.
        # Do NOT call determine_market_regime() again.
        # ----------------------------------------------------

        scanner_regime = (
            extract_regime_from_object(
                scanner_summary
            )
        )

        if scanner_regime:

            save_regime_sidecar(
                market_file,
                scanner_regime,
            )

    # --------------------------------------------------------
    # BREADTH
    # --------------------------------------------------------

    breadth = build_market_breadth(
        market_dataframe
    )

    # --------------------------------------------------------
    # NIFTY RETURNS
    # --------------------------------------------------------

    print(
        "Refreshing lightweight index data..."
    )

    nifty_returns = (
        calculate_index_returns(
            "^NSEI"
        )
    )

    bank_nifty_returns = (
        calculate_index_returns(
            "^NSEBANK"
        )
    )

    # --------------------------------------------------------
    # REGIME
    # --------------------------------------------------------

    if scanner_regime:

        market_regime = (
            scanner_regime
        )

    else:

        cached_regime = (
            load_cached_regime(
                market_file
            )
        )

        if cached_regime:

            market_regime = (
                cached_regime
            )

        else:

            market_regime = (
                fallback_market_regime(
                    breadth,
                    nifty_returns,
                )
            )

            save_regime_sidecar(
                market_file,
                market_regime,
            )

    # --------------------------------------------------------
    # SNAPSHOT
    # --------------------------------------------------------

    print(
        "Refreshing NIFTY snapshot..."
    )

    nifty_snapshot = (
        _apply_dhan_override(
            get_nifty_snapshot()
        )
    )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    volatility = (
        _apply_dhan_volatility_overrides(
            load_volatility_snapshot()
        )
    )

    # --------------------------------------------------------
    # SECTOR
    # --------------------------------------------------------

    (
        sector_dataframe,
        sector_file,
    ) = load_latest_sector_report()

    sector_intelligence = (
        build_sector_intelligence(
            sector_dataframe
        )
    )

    # --------------------------------------------------------
    # TECHNICAL RANKING
    # --------------------------------------------------------

    top_technical_stocks = (
        build_top_technical_stocks(
            market_dataframe
        )
    )

    # --------------------------------------------------------
    # RESEARCH FACTORS
    # --------------------------------------------------------

    try:
        if not RESEARCH_FACTOR_ENGINE_IMPORT_OK:
            raise RuntimeError(
                RESEARCH_FACTOR_ENGINE_IMPORT_ERROR
                or "Research factor engine import failed."
            )

        research_factors = build_research_factors(market_dataframe)
    except Exception as exc:
        research_factors = {
            "engine": "Nova Research Factor Engine",
            "status": "NOT_AVAILABLE",
            "reason": f"{type(exc).__name__}: {exc}",
            "warnings": [],
            "decision_policy": {
                "factor_rank_is_a_buy_sell_signal": False,
                "buy_sell_authorization": False,
                "trading_execution": False,
            },
        }

    # --------------------------------------------------------
    # DERIVATIVES
    # --------------------------------------------------------

    derivatives = (
        load_derivatives_intelligence()
    )

    # --------------------------------------------------------
    # AVAILABILITY
    # --------------------------------------------------------

    # --------------------------------------------------------
    # INSTITUTIONAL FLOW
    # --------------------------------------------------------

    institutional_flow = load_institutional_flow_intelligence()

    # --------------------------------------------------------
    # RISK CONTEXT
    # --------------------------------------------------------

    if RISK_ENGINE_IMPORT_OK and build_market_risk_context:
        try:
            risk_context = build_market_risk_context(
                volatility=volatility,
                market_regime=market_regime,
                institutional_flow=institutional_flow,
            )
        except Exception as exc:
            risk_context = {
                "available": False,
                "reason": f"Risk context calculation failed: {exc}",
                "execution_enabled": False,
                "buy_sell_authorization": False,
            }
    else:
        risk_context = {
            "available": False,
            "reason": (
                RISK_ENGINE_IMPORT_ERROR
                or "Risk engine import failed."
            ),
            "execution_enabled": False,
            "buy_sell_authorization": False,
        }
    
    # --------------------------------------------------------
    # EVENT RISK CONTEXT
    # --------------------------------------------------------

    try:
        event_risk_context = load_event_risk_context()
    except Exception as exc:
        event_risk_context = {
            "engine": "Nova Event Risk Engine",
            "status": "ERROR",
            "overall_risk": "UNKNOWN",
            "upcoming_event_count": 0,
            "upcoming_events": [],
            "warnings": [
                f"Event risk integration failed: {type(exc).__name__}: {exc}"
            ],
            "decision_policy": {
                "event_risk_is_a_buy_sell_signal": False,
                "buy_sell_authorization": False,
                "trading_execution": False,
            },
        }

    # --------------------------------------------------------
    # AVAILABILITY
    # --------------------------------------------------------

    data_availability = (
        build_data_availability(
            market_dataframe,
            sector_dataframe,
            volatility,
            derivatives,
        )
    )

    data_availability["institutional_flow"] = (
        "READY"
        if institutional_flow.get("available")
        else "NOT AVAILABLE"
    )
    data_availability["risk_engine"] = (
        "AVAILABLE"
        if risk_context.get("available")
        else "NOT AVAILABLE"
    )
    data_availability["event_risk_engine"] = (
        "AVAILABLE"
        if (
            event_risk_context.get("available") is True
            or str(event_risk_context.get("status", "")).upper()
            in {"AVAILABLE", "READY", "OK", "SUCCESS"}
        )
        else "NOT AVAILABLE"
    )
    data_availability["research_factor_engine"] = (
        "AVAILABLE"
        if research_factors.get("status") == "AVAILABLE"
        else "NOT AVAILABLE"
    )

    # --------------------------------------------------------
    # DECISION POLICY
    # --------------------------------------------------------

    decision_policy = {

        "TECHNICAL_SCORE_IS_SIGNAL":
            TECHNICAL_SCORE_IS_SIGNAL,

        "VOLATILITY_IS_SIGNAL":
            VOLATILITY_IS_SIGNAL,

        "BUY_SELL_AUTHORIZATION":
            BUY_SELL_AUTHORIZATION,

        "TRADING_EXECUTION":
            TRADING_EXECUTION,

        "BROKER_CONNECTION":
            BROKER_CONNECTION,

        "AUTOMATIC_ORDERS":
            AUTOMATIC_ORDERS,
    }

    # --------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------

    report = {

        "system":
            "NOVA MARKET LAB",

        "generated":
            now_iso(),

        "market":
            DEFAULT_MARKET,

        "stocks_analyzed":
            int(
                len(
                    market_dataframe
                )
            ),

        "market_regime":
            market_regime,

        "mode":
            (
                "FORCED_REFRESH"
                if force_refresh
                else "LIVE_ONLY"
                if live_only
                else "CACHED_OR_REFRESH"
            ),

        "scanner_file":
            (
                str(
                    market_file
                )
                if market_file
                else None
            ),

        "sector_file":
            (
                str(
                    sector_file
                )
                if sector_file
                else None
            ),

        "nifty_returns":
            nifty_returns,

        "bank_nifty_returns":
            bank_nifty_returns,

        "nifty_snapshot":
            nifty_snapshot,

        "breadth":
            breadth,

        "volatility":
            volatility,

        "sector_intelligence":
            sector_intelligence,

        "top_technical_stocks":
            top_technical_stocks,

        "derivatives":
            derivatives,


        "institutional_flow":
            institutional_flow,

        "risk_context":
            risk_context,

        "event_risk_context":
            event_risk_context,

        "research_factors":
            research_factors,

        "data_availability":
            data_availability,

        "decision_policy":
            decision_policy,

        # ----------------------------------------------------
        # AI CONTEXT
        # ----------------------------------------------------

        "ai_context":
            {

                "system":
                    "NOVA MARKET LAB",

                "purpose":
                    (
                        "Evidence-grounded market "
                        "research and analysis."
                    ),

                "market":
                    DEFAULT_MARKET,

                "market_regime":
                    market_regime,

                "nifty_returns":
                    nifty_returns,

                "bank_nifty_returns":
                    bank_nifty_returns,

                "nifty_snapshot":
                    nifty_snapshot,

                "breadth":
                    breadth,

                "volatility":
                    volatility,

                "sector_intelligence":
                    sector_intelligence,

                "top_technical_stocks":
                    top_technical_stocks,

                "derivatives":
                    derivatives,


                "institutional_flow":
                    institutional_flow,

                "risk_context":
                    risk_context,

                "event_risk_context":
                    event_risk_context,

                "research_factors":
                    research_factors,

                "decision_policy":
                    decision_policy,

                "data_availability":
                    data_availability,

                "guardrails":
                    {

                        "analysis_only":
                            True,

                        "no_broker":
                            True,

                        "no_trade_execution":
                            True,

                        "no_automatic_orders":
                            True,

                        "buy_sell_authorized":
                            False,
                    },
            },
    }

    return report


# ============================================================
# TERMINAL OUTPUT
# ============================================================

def print_market_lab(
    report: dict[str, Any],
) -> None:

    print()
    print("=" * 66)
    print("NOVA MARKET LAB")
    print("=" * 66)

    print(
        f"Generated: "
        f"{report.get(
            'generated',
            'N/A'
        )}"
    )

    print(
        f"Market: "
        f"{report.get(
            'market',
            DEFAULT_MARKET
        )}"
    )

    print(
        f"Stocks analyzed: "
        f"{safe_int(
            report.get(
                'stocks_analyzed'
            )
        ):,}"
    )

    print(
        f"Market regime: "
        f"{report.get(
            'market_regime',
            'UNKNOWN'
        )}"
    )

    # ========================================================
    # INSTITUTIONAL FLOW
    # ========================================================

    print()
    print("INSTITUTIONAL FLOW")
    print("-" * 70)

    flow = report.get("institutional_flow") or {}
    flow_metrics = flow.get("metrics") or {}
    flow_snapshot = flow.get("snapshot") or {}

    print(f"Status: {flow.get('status', 'NOT AVAILABLE')}")
    print(f"Latest session: {flow.get('latest_date') or 'N/A'}")
    print(f"Source: {flow.get('latest_source') or 'N/A'}")
    print(f"Market scope: {flow.get('market_scope') or 'N/A'}")
    print(
        "History: "
        f"{flow.get('history_sessions', 0)} sessions | "
        f"{flow.get('history_quality', 'UNKNOWN')}"
    )
    print(f"Fresh: {flow.get('history_fresh', False)}")

    print(
        "Source quality: "
        f"{flow.get('source_quality', 'UNKNOWN')}"
    )

    print(
        "Primary sessions in target window: "
        f"{flow_metrics.get('primary_source_sessions_in_target_window', 0)}"
        f"/{flow_metrics.get('target_sessions', 20)}"
    )

    print(
        "Primary-only history verified: "
        f"{flow_metrics.get('primary_source_verified_for_target_window', False)}"
    )

    print(
        "Flow unit: "
        f"{flow_metrics.get('flow_unit', 'INR crore')}"
    )

    for window in (5, 10, 20):
        print(
            f"{window:>2}D | "
            f"FII net: {flow_metrics.get(f'fii_{window}d', 'N/A')} Cr | "
            f"DII net: {flow_metrics.get(f'dii_{window}d', 'N/A')} Cr | "
            f"Combined: {flow_metrics.get(f'combined_{window}d', 'N/A')} Cr"
        )

    print(
        "Flow regime: "
        f"{flow_metrics.get('flow_regime', 'INSUFFICIENT_HISTORY')}"
    )

    if flow.get("reason"):
        print(f"Readiness note: {flow['reason']}")

    if flow.get("signal_reason"):
        print(f"Signal eligibility note: {flow['signal_reason']}")

    print(
        "Decision-support eligible: "
        f"{flow.get('signal_allowed', False)}"
    )

    # ========================================================
    # RISK CONTEXT
    # ========================================================

    print()
    print("RISK CONTEXT")
    print("-" * 70)

    risk = report.get("risk_context") or {}

    print(
        f"Status: "
        f"{'AVAILABLE' if risk.get('available') else 'NOT AVAILABLE'}"
    )
    print(f"Purpose: {risk.get('purpose', 'N/A')}")
    print(f"Market regime: {risk.get('market_regime', 'UNKNOWN')}")

    instruments = risk.get("instruments") or {}

    for key in ("nifty", "bank_nifty"):
        item = instruments.get(key) or {}

        if not item.get("available"):
            print(f"{item.get('name', key.upper())}: Metrics unavailable")
            continue

        print(f"\n{item.get('name', key.upper())}")
        print(f"ATR: {item.get('atr', 'N/A')}")
        print(f"ATR %: {item.get('atr_pct', 'N/A')}")
        print(
            "Expected daily move: "
            f"{item.get('expected_daily_move_percent', 'N/A')}%"
        )
        print(
            "Realized volatility 20D: "
            f"{item.get('realized_volatility_20d', 'N/A')}%"
        )
        print(
            "Realized volatility 60D: "
            f"{item.get('realized_volatility_60d', 'N/A')}%"
        )

    for warning in risk.get("warnings") or []:
        print(f"Warning: {warning}")

    print(f"Execution enabled: {risk.get('execution_enabled', False)}")
    print(
        "Buy/sell authorization: "
        f"{risk.get('buy_sell_authorization', False)}"
    )

    # ========================================================
    # EVENT RISK CONTEXT
    # ========================================================

    print()
    print("EVENT RISK CONTEXT")
    print("-" * 70)

    event_risk = report.get("event_risk_context") or {}
    print(f"Engine: {event_risk.get('engine', 'Nova Event Risk Engine')}")
    print(f"Status: {event_risk.get('status', 'NOT AVAILABLE')}")
    print(f"Overall event risk: {event_risk.get('overall_risk', 'UNKNOWN')}")
    print(f"Upcoming events: {event_risk.get('upcoming_event_count', 0)}")

    upcoming_events = event_risk.get("upcoming_events") or []
    if upcoming_events:
        for event in upcoming_events[:10]:
            if isinstance(event, dict):
                name = event.get("name") or event.get("title") or "Unnamed event"
                date = (
                    event.get("datetime_utc")
                    or event.get("datetime")
                    or event.get("date")
                    or event.get("event_date")
                    or "Date unknown"
                )
                impact = (
                    event.get("risk_level")
                    or event.get("severity")
                    or event.get("impact")
                    or "UNCLASSIFIED"
                )
                print(f"- {date} | {name} | Impact: {impact}")
            else:
                print(f"- {event}")
    else:
        print("No upcoming events were returned by the event-risk engine.")

    for warning in event_risk.get("warnings") or []:
        print(f"Warning: {warning}")

    event_policy = event_risk.get("decision_policy") or {}
    print(
        "Event risk is a buy/sell signal: "
        f"{event_policy.get('event_risk_is_a_buy_sell_signal', False)}"
    )
    print(
        "Buy/sell authorization: "
        f"{event_policy.get('buy_sell_authorization', False)}"
    )
    print(
        "Trading execution: "
        f"{event_policy.get('trading_execution', False)}"
    )

    # ========================================================
    # NIFTY
    # ========================================================

    print()
    print("NIFTY BENCHMARK")
    print("-" * 70)

    nifty = report.get(
        "nifty_returns",
        {},
    )

    print(
        f"1D : "
        f"{safe_float(
            nifty.get('1D')
        )}"
    )

    print(
        f"5D : "
        f"{safe_float(
            nifty.get('5D')
        )}"
    )

    print(
        f"20D: "
        f"{safe_float(
            nifty.get('20D')
        )}"
    )

    print(
        f"60D: "
        f"{safe_float(
            nifty.get('60D')
        )}"
    )

    # ========================================================
    # BREADTH
    # ========================================================

    print()
    print("MARKET BREADTH")
    print("-" * 70)

    breadth = report.get(
        "breadth",
        {},
    )

    print(
        f"Advancing: "
        f"{safe_int(
            breadth.get(
                'advancing'
            )
        ):,}"
    )

    print(
        f"Declining: "
        f"{safe_int(
            breadth.get(
                'declining'
            )
        ):,}"
    )

    print(
        f"Unchanged: "
        f"{safe_int(
            breadth.get(
                'unchanged'
            )
        ):,}"
    )

    print(
        f"Advance/Decline Ratio: "
        f"{format_number(
            breadth.get(
                'ad_ratio'
            ),
            3,
        )}"
    )

    print(
        f"Above EMA20: "
        f"{format_percent(
            breadth.get(
                'above_ema20_percent'
            )
        )}"
    )

    print(
        f"Above EMA50: "
        f"{format_percent(
            breadth.get(
                'above_ema50_percent'
            )
        )}"
    )

    print(
        f"Above EMA200: "
        f"{format_percent(
            breadth.get(
                'above_ema200_percent'
            )
        )}"
    )

    print(
        f"Strong uptrend: "
        f"{format_percent(
            breadth.get(
                'strong_uptrend_percent'
            )
        )}"
    )

    print(
        f"Strong downtrend: "
        f"{format_percent(
            breadth.get(
                'strong_downtrend_percent'
            )
        )}"
    )

    # ========================================================
    # VOLATILITY
    # ========================================================

    print()
    print("VOLATILITY")
    print("-" * 70)

    volatility = report.get(
        "volatility",
        {},
    )

    vix = volatility.get(
        "india_vix",
        {},
    )

    if vix.get(
        "available",
        False,
    ):

        print(
            f"India VIX: "
            f"{format_number(
                vix.get(
                    'value'
                )
            )}"
        )

        print(
            f"VIX Change: "
            f"{format_percent(
                vix.get(
                    'change_percent'
                )
            )}"
        )

        print(
            f"VIX 1Y Percentile: "
            f"{format_percent(
                vix.get(
                    'percentile_1y'
                )
            )}"
        )

        print(
            f"VIX Absolute Regime: "
            f"{vix.get(
                'regime',
                'UNKNOWN'
            )}"
        )

        print(
            f"VIX Direction: "
            f"{vix.get(
                'direction',
                'UNKNOWN'
            )}"
        )

    nifty_vol = volatility.get(
        "nifty",
        {},
    )

    if nifty_vol.get(
        "available",
        False,
    ):

        print()
        print("NIFTY VOLATILITY")
        print("-" * 70)

        print(
            f"Price: "
            f"{format_number(
                nifty_vol.get(
                    'price'
                )
            )}"
        )

        print(
            f"ATR(14): "
            f"{format_number(
                nifty_vol.get(
                    'atr14'
                )
            )}"
        )

        print(
            f"ATR %: "
            f"{format_percent(
                nifty_vol.get(
                    'atr_percent'
                )
            )}"
        )

        print(
            f"Realized Vol 20D: "
            f"{format_percent(
                nifty_vol.get(
                    'realized_volatility_20d'
                )
            )}"
        )

        print(
            f"Realized Vol 60D: "
            f"{format_percent(
                nifty_vol.get(
                    'realized_volatility_60d'
                )
            )}"
        )

        print(
            f"Volatility Percentile: "
            f"{format_percent(
                nifty_vol.get(
                    'volatility_percentile'
                )
            )}"
        )

        print(
            f"Expected Daily Move: "
            f"{format_percent(
                nifty_vol.get(
                    'expected_daily_move_percent'
                )
            )}"
        )

        print(
            f"Expected Daily Range: "
            f"{format_number(
                nifty_vol.get(
                    'expected_daily_range'
                )
            )}"
        )

        print(
            f"Volatility Regime: "
            f"{nifty_vol.get(
                'volatility_regime',
                'UNKNOWN'
            )}"
        )

        print(
            f"Volatility Direction: "
            f"{nifty_vol.get(
                'volatility_direction',
                'UNKNOWN'
            )}"
        )

    bank_vol = volatility.get(
        "bank_nifty",
        {},
    )

    if bank_vol.get(
        "available",
        False,
    ):

        print()
        print("BANK NIFTY VOLATILITY")
        print("-" * 70)

        print(
            f"Price: "
            f"{format_number(
                bank_vol.get(
                    'price'
                )
            )}"
        )

        print(
            f"ATR(14): "
            f"{format_number(
                bank_vol.get(
                    'atr14'
                )
            )}"
        )

        print(
            f"ATR %: "
            f"{format_percent(
                bank_vol.get(
                    'atr_percent'
                )
            )}"
        )

        print(
            f"Realized Vol 20D: "
            f"{format_percent(
                bank_vol.get(
                    'realized_volatility_20d'
                )
            )}"
        )

        print(
            f"Realized Vol 60D: "
            f"{format_percent(
                bank_vol.get(
                    'realized_volatility_60d'
                )
            )}"
        )

        print(
            f"Volatility Percentile: "
            f"{format_percent(
                bank_vol.get(
                    'volatility_percentile'
                )
            )}"
        )

        print(
            f"Expected Daily Move: "
            f"{format_percent(
                bank_vol.get(
                    'expected_daily_move_percent'
                )
            )}"
        )

        print(
            f"Expected Daily Range: "
            f"{format_number(
                bank_vol.get(
                    'expected_daily_range'
                )
            )}"
        )

        print(
            f"Volatility Regime: "
            f"{bank_vol.get(
                'volatility_regime',
                'UNKNOWN'
            )}"
        )

        print(
            f"Volatility Direction: "
            f"{bank_vol.get(
                'volatility_direction',
                'UNKNOWN'
            )}"
        )

    # ========================================================
    # TECHNICAL
    # ========================================================

    print()
    print("TOP TECHNICAL RANKINGS")
    print("-" * 70)

    stocks = report.get(
        "top_technical_stocks",
        [],
    )

    if not stocks:

        print(
            "No technical rankings available."
        )

    else:

        for index, stock in enumerate(
            stocks,
            start=1,
        ):

            print(
                f"{index}. "
                f"{stock.get(
                    'symbol',
                    'UNKNOWN'
                )} "
                f"| Score: "
                f"{format_number(
                    stock.get(
                        'technical_score'
                    )
                )} "
                f"| Trend: "
                f"{stock.get(
                    'trend',
                    'UNKNOWN'
                )}"
            )

    # ========================================================
    # SECTOR INTELLIGENCE
    # ========================================================

    print()
    print("SECTOR INTELLIGENCE")
    print("-" * 70)

    sectors = report.get(
        "sector_intelligence",
        {},
    )

    print(
        f"Sectors loaded: "
        f"{sectors.get(
            'count',
            0
        )}+"
    )

    top_sectors = (
        sectors.get(
            "top_sectors",
            [],
        )
    )

    for index, sector in enumerate(
        top_sectors,
        start=1,
    ):

        print(
            f"{index}. "
            f"{sector.get(
                'sector',
                'UNKNOWN'
            )} "
            f"| R20: "
            f"{safe_float(
                sector.get(
                    'return_20d'
                )
            )} "
            f"| RS20: "
            f"{safe_float(
                sector.get(
                    'relative_strength_20d'
                )
            )} "
            f"| Regime: "
            f"{sector.get(
                'regime',
                'UNKNOWN'
            )}"
        )

    # ========================================================
    # DERIVATIVES INTELLIGENCE
    # ========================================================

    print()
    print("DERIVATIVES INTELLIGENCE")
    print("-" * 70)

    derivatives = report.get(
        "derivatives",
        {},
    )

    for label, key in (
        (
            "NIFTY",
            "nifty",
        ),
        (
            "BANK NIFTY",
            "bank_nifty",
        ),
    ):

        data = derivatives.get(
            key,
            {},
        )

        if not data.get(
            "available",
            False,
        ):

            print(
                f"{label}: "
                f"NOT AVAILABLE"
            )

            continue

        underlying = data.get(
            "underlying",
            {},
        )

        expiry = data.get(
            "expiry",
            {},
        )

        atm = data.get(
            "atm",
            {},
        )

        pcr = data.get(
            "pcr",
            {},
        )

        max_pain = data.get(
            "max_pain",
            {},
        )

        walls = data.get(
            "oi_walls",
            {},
        )

        sr = data.get(
            "support_resistance",
            {},
        )

        iv = data.get(
            "iv_structure",
            {},
        )

        positioning = data.get(
            "positioning_interpretation",
            {},
        )

        put_wall = (
            walls.get(
                "put_wall"
            )
            or {}
        )

        call_wall = (
            walls.get(
                "call_wall"
            )
            or {}
        )

        support = (
            sr.get(
                "support"
            )
            or {}
        )

        resistance = (
            sr.get(
                "resistance"
            )
            or {}
        )

        print()
        print(
            label
        )

        print(
            f"Spot: "
            f"{format_number(
                underlying.get(
                    'spot'
                )
            )}"
        )

        print(
            f"Expiry: "
            f"{expiry.get(
                'selected',
                'N/A'
            )}"
        )

        print(
            f"ATM: "
            f"{format_strike(
                atm.get(
                    'strike'
                )
            )}"
        )

        print(
            f"OI PCR: "
            f"{format_number(
                pcr.get(
                    'oi_pcr'
                ),
                3,
            )}"
        )

        print(
            f"Volume PCR: "
            f"{format_number(
                pcr.get(
                    'volume_pcr'
                ),
                3,
            )}"
        )

        print(
            f"Max Pain: "
            f"{format_strike(
                max_pain.get(
                    'strike'
                )
            )}"
        )

        print(
            f"Put Wall: "
            f"{format_strike(
                put_wall.get(
                    'strike'
                )
            )}"
        )

        print(
            f"Call Wall: "
            f"{format_strike(
                call_wall.get(
                    'strike'
                )
            )}"
        )

        print(
            f"Support: "
            f"{format_strike(
                support.get(
                    'strike'
                )
            )}"
        )

        print(
            f"Resistance: "
            f"{format_strike(
                resistance.get(
                    'strike'
                )
            )}"
        )

        print(
            f"ATM Call IV: "
            f"{format_number(
                iv.get(
                    'atm_call_iv'
                )
            )}"
        )

        print(
            f"ATM Put IV: "
            f"{format_number(
                iv.get(
                    'atm_put_iv'
                )
            )}"
        )

        print(
            f"ATM IV: "
            f"{format_number(
                iv.get(
                    'atm_iv'
                )
            )}"
        )

        print(
            f"IV Skew: "
            f"{format_number(
                iv.get(
                    'put_minus_call_iv_skew'
                )
            )}"
        )

        print(
            f"Positioning: "
            f"{positioning.get(
                'classification',
                'UNKNOWN'
            )}"
        )

    # ========================================================
    # DATA AVAILABILITY
    # ========================================================

    print()
    print("DATA AVAILABILITY")
    print("-" * 70)

    for key, value in report.get(
        "data_availability",
        {},
    ).items():

        print(
            f"{key:<36} "
            f"{value}"
        )

    # ========================================================
    # DECISION POLICY
    # ========================================================

    print()
    print("DECISION POLICY")
    print("-" * 70)

    for key, value in report.get(
        "decision_policy",
        {},
    ).items():

        print(
            f"{key}: "
            f"{value}"
        )

    # ========================================================
    # CACHE
    # ========================================================

    print()
    print("CACHE MODE")
    print("-" * 70)

    print(
        f"Market scan: "
        f"{report.get(
            'scanner_file',
            'N/A'
        )}"
    )

    print(
        f"Sector scan: "
        f"{report.get(
            'sector_file',
            'N/A'
        )}"
    )

    print(
        f"Mode: "
        f"{report.get(
            'mode',
            'UNKNOWN'
        )}"
    )

    print()
    print("=" * 66)


# ============================================================
# JSON SAVE
# ============================================================

def save_json_report(
    report: dict[str, Any],
) -> Path:

    output_directory = (
        CACHE_DIR
        / "market_lab"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    path = (
        output_directory
        / (
            f"market_lab_"
            f"{timestamp}.json"
        )
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return path


# ============================================================
# CLI
# ============================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Nova Market Lab"
        )
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Force a complete NSE equity scan."
        ),
    )

    parser.add_argument(
        "--live-only",
        action="store_true",
        help=(
            "Refresh only live layers (index, derivatives, flow, "
            "event, risk) over the cached equity scan. Never runs "
            "the full NSE scan; refuses to combine with --refresh."
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Save complete Market Lab report "
            "to JSON."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    args = parse_arguments()

    if args.live_only and args.refresh:
        print()
        print("=" * 66)
        print("NOVA MARKET LAB ERROR")
        print("=" * 66)
        print()
        print(
            "--live-only and --refresh are mutually exclusive: "
            "live-only mode never runs the full NSE scan."
        )
        print()

        return 2

    try:

        report = get_market_lab_data(
            force_refresh=args.refresh,
            live_only=args.live_only,
        )

        print_market_lab(
            report
        )

        if args.json:

            path = save_json_report(
                report
            )

            print()
            print(
                f"JSON report saved: "
                f"{path}"
            )

        print()
        print(
            "NOVA MARKET LAB TEST COMPLETE"
        )

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Market Lab stopped by user."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 66)
        print("NOVA MARKET LAB ERROR")
        print("=" * 66)
        print()
        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )
        print()

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )