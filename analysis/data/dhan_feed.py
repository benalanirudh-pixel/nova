"""
Nova Market Intelligence
Dhan market-data adapter (READ-ONLY analysis data only)

Purpose:
    Provide historical daily candles and (optionally) live index quotes as an
    alternative/primary source for Nova's existing technical engine, which
    already computes RSI, MACD, ATR, momentum, etc. locally from candles.

Analysis-only boundary (enforced by design):
    This adapter uses ONLY Dhan market-DATA endpoints
    (POST /v2/charts/historical, and, if enabled, market-feed quote endpoints).
    It NEVER calls order, position, trade, funds, or any execution endpoint,
    places no orders, and holds no trading credentials beyond a read-only
    access token. No broker or order-placement behavior exists here.

Configuration (never committed):
    - DHAN_ACCESS_TOKEN   : Dhan access token (JWT). Without it the adapter is
                            disabled and callers fall back to existing sources.
    - DHAN_BASE_URL       : optional; defaults to https://api.dhan.co/v2
    - dhan_config.json    : git-ignored, in the project root. Maps NSE symbols
                            to Dhan security IDs, e.g.
                              { "equity": {"RELIANCE": "500285", ...} }
                            (Get IDs from Dhan's instrument/scrip master.)
    DHAN_ACCESS_TOKEN is also read from dhan_config.json {"access_token": ...}
    if present. Nothing sensitive is ever committed.

Caching / freshness:
    Daily candles are cached under analysis/data/cache/dhan (git-ignored) with a
    recorded fetch time; the cache is reused only while younger than
    MAX_AGE_HOURS (default 16h). Missing/stale cache triggers one live fetch.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

# --------------------------------------------------------------------------
# Paths / configuration
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache" / "dhan"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT = BASE_DIR.parents[1]
CONFIG_PATH = PROJECT_ROOT / "dhan_config.json"

DEFAULT_BASE_URL = "https://api.dhan.co/v2"

# Nova's existing freshness gate (scanner turns critical above 16h).
MAX_AGE_HOURS = 16

# Requested period -> how many days of history to ask Dhan for. Mirrors the
# window logic already used by the NSE adapter.
PERIOD_DAYS = {
    "1d": 3,
    "5d": 10,
    "1mo": 40,
    "3mo": 100,
    "6mo": 200,
    "1y": 380,
    "2y": 760,
    "5y": 1900,
}

# Columns Nova's technical engine expects from a price-history DataFrame.
_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _load_config() -> dict:
    """Load the git-ignored dhan_config.json if present (best effort)."""
    try:
        if CONFIG_PATH.is_file():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def get_access_token() -> str:
    """Return the Dhan access token, or '' if unset. Env wins over config."""
    token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
    if token:
        return token
    return str(_load_config().get("access_token", "")).strip()


def get_base_url() -> str:
    return os.environ.get("DHAN_BASE_URL", "").strip() or DEFAULT_BASE_URL


def is_configured() -> bool:
    """True when an access token is available (adapter can be attempted)."""
    return bool(get_access_token())


# --------------------------------------------------------------------------
# Security id resolution (no downloads; explicit mapping only)
# --------------------------------------------------------------------------

def resolve_security_id(symbol: str) -> str | None:
    """Return the Dhan securityId for an NSE equity symbol, or None.

    Priority: dhan_config.json {"equity": {...}} overrides, then the cached
    instrument-master map (analysis/data/cache/dhan/security_map.json). Never
    invents an id.
    """
    symbol_up = str(symbol).strip().upper()
    config = _load_config()
    equity = config.get("equity", {})
    if isinstance(equity, dict):
        sid = equity.get(symbol_up)
        if sid is not None and str(sid).strip():
            return str(sid).strip()
    return _load_security_map().get(symbol_up)


# --------------------------------------------------------------------------
# Instrument master (public CSV) -> cached security-id map (16h gate)
# --------------------------------------------------------------------------

INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
SECURITY_MAP_CACHE = CACHE_DIR / "security_map.json"

# Tolerant header spellings across Dhan's compact/detailed masters.
_SID_HEADERS = ("SEM_SMST_SECURITY_ID", "SECURITY_ID", "SCRIP_CODE", "SEM_SECURITY_ID")
_SYM_HEADERS = ("SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "SYMBOL", "SEM_CUSTOM_SYMBOL")
_EXCH_HEADERS = ("EXCH_ID", "EXCHANGE", "SEM_EXM_EXCH_ID")
_SEG_HEADERS = ("SEGMENT", "EXCHANGE_SEGMENT", "SEM_SEGMENT")
_INSTR_HEADERS = ("INSTRUMENT", "INSTRUMENT_TYPE", "SEM_INSTRUMENT_NAME")


def _first(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _load_security_map() -> dict:
    path = SECURITY_MAP_CACHE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(data.get("fetched_at", 0))
        mapping = data.get("mapping", {})
    except (OSError, ValueError, TypeError):
        return {}
    if (time.time() - fetched_at) / 3600.0 > MAX_AGE_HOURS:
        return {}
    if isinstance(mapping, dict):
        return {str(k).upper(): str(v) for k, v in mapping.items()}
    return {}


def _save_security_map(mapping: dict) -> None:
    try:
        SECURITY_MAP_CACHE.write_text(
            json.dumps({"fetched_at": time.time(), "mapping": mapping},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError):
        pass


def build_security_map(force: bool = False) -> dict:
    """Download Dhan's public instrument master and cache NSE EQUITY
    symbol -> securityId. Public URL (no token needed); cached 16h.

    Raises RuntimeError on network/parse failure so callers fall back.
    """
    if not force:
        cached = _load_security_map()
        if cached:
            return cached

    import csv
    import io
    import requests

    response = requests.get(INSTRUMENT_MASTER_URL, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(
            f"Dhan instrument master HTTP {response.status_code}."
        )

    text = response.content.decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(text))
    mapping: dict[str, str] = {}
    for row in reader:
        exch = (_first(row, _EXCH_HEADERS) or "").upper()
        if "NSE" not in exch:
            continue
        segment = (_first(row, _SEG_HEADERS) or "").upper()
        instrument = (_first(row, _INSTR_HEADERS) or "").upper()
        is_equity = (
            "EQ" in segment
            or instrument in ("EQUITY", "E")
        )
        if not is_equity:
            continue
        symbol = _first(row, _SYM_HEADERS)
        sid = _first(row, _SID_HEADERS)
        if symbol and sid:
            mapping[symbol.upper()] = sid

    if not mapping:
        raise RuntimeError(
            "Dhan instrument master parsed to zero NSE equity rows."
        )
    _save_security_map(mapping)
    return mapping


# --------------------------------------------------------------------------
# Live index / equity quotes (market-feed, analysis-only)
# --------------------------------------------------------------------------

# Common Dhan index security IDs; override via dhan_config.json {"index": {...}}.
DEFAULT_INDEX_SECURITY = {"NIFTY": "13", "BANKNIFTY": "25", "INDIAVIX": "26"}
_INDEX_LABELS = {"NIFTY": "NIFTY 50", "BANKNIFTY": "BANK NIFTY",
                 "INDIAVIX": "INDIA VIX"}


def _index_security_id(name: str) -> str | None:
    config = _load_config().get("index", {})
    if isinstance(config, dict):
        sid = config.get(name)
        if sid is not None and str(sid).strip():
            return str(sid).strip()
    return DEFAULT_INDEX_SECURITY.get(name)


def _coerce_ids(ids):
    out = []
    for value in ids:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            out.append(str(value))
    return out


def get_index_quote(names=("NIFTY", "BANKNIFTY", "INDIAVIX")) -> dict:
    """Live quotes for indices via POST /v2/marketfeed/quote (IDX_I segment).

    Returns {name: {label, last_price, net_change, ohlc/open/high/low/close,
    last_trade_time, available}}. Missing data is available=False (never
    invented). Requires a configured token.
    """
    if not is_configured():
        return {}

    ids = {}
    for name in names:
        sid = _index_security_id(name)
        if sid:
            ids[name] = str(sid)
    if not ids:
        return {}

    data = _post(
        "/marketfeed/quote",
        {"IDX_I": _coerce_ids(ids.values())},
    )
    block = ((data.get("data") or {}).get("IDX_I")) or {}

    result = {}
    for name, sid in ids.items():
        quote = block.get(sid) if isinstance(block, dict) else None
        entry = {"label": _INDEX_LABELS.get(name, name), "available": False}
        if isinstance(quote, dict) and quote.get("last_price") is not None:
            ohlc = quote.get("ohlc") or {}
            entry.update({
                "available": True,
                "last_price": _safe(quote.get("last_price")),
                "net_change": _safe(quote.get("net_change")),
                "open": _safe(ohlc.get("open")),
                "high": _safe(ohlc.get("high")),
                "low": _safe(ohlc.get("low")),
                "close": _safe(ohlc.get("close")),
                "last_trade_time": quote.get("last_trade_time"),
            })
        result[name] = entry
    return result


def get_last_price(symbols) -> dict:
    """LTP for NSE equities via POST /v2/marketfeed/ltp.

    symbols: iterable of NSE symbols with mapped/known security IDs.
    Returns {SYMBOL: {"last_price": float, "available": bool}}.
    """
    if not is_configured():
        return {}

    ids = {}
    for symbol in symbols:
        sid = resolve_security_id(symbol)
        if sid:
            ids[str(symbol).upper()] = str(sid)
    if not ids:
        return {}

    data = _post("/marketfeed/ltp", {"NSE_EQ": _coerce_ids(ids.values())})
    block = ((data.get("data") or {}).get("NSE_EQ")) or {}
    result = {}
    for symbol, sid in ids.items():
        entry = (block.get(sid) or {}) if isinstance(block, dict) else {}
        result[symbol] = {
            "last_price": _safe(entry.get("last_price")),
            "available": entry.get("last_price") is not None,
        }
    return result


def _safe(value):
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _index_entry_to_snapshot(entry) -> dict:
    """Convert one get_index_quote() entry into a report-compatible NIFTY
    snapshot dict. Derives change_percent/previous_close from last_price and
    net_change (arithmetic on Dhan values, labeled as source DHAN_LIVE). If the
    entry is unavailable, returns {"available": False} — never invents prices.
    """
    if not isinstance(entry, dict) or not entry.get("available"):
        return {"available": False}

    last_price = _safe(entry.get("last_price"))
    net_change = _safe(entry.get("net_change"))
    change_percent = None
    previous_close = None
    if last_price is not None and net_change is not None:
        previous_close = last_price - net_change
        if previous_close not in (None, 0):
            change_percent = (net_change / previous_close) * 100.0

    return {
        "available": True,
        "price": last_price,
        "change_percent": change_percent,
        "change_abs": net_change,
        "previous_close": previous_close,
        "open": _safe(entry.get("open")),
        "high": _safe(entry.get("high")),
        "low": _safe(entry.get("low")),
        "source": "DHAN_LIVE",
        "last_trade_time": entry.get("last_trade_time"),
    }


def get_report_index_snapshot(
    names=("NIFTY", "BANKNIFTY", "INDIAVIX"),
) -> dict:
    """Live index snapshots in a report-ish shape (keys: nifty, bank_nifty,
    india_vix). Returns {} when Dhan is unconfigured or the quote fails, so
    callers fall back to the existing NSE/Yahoo engines unchanged."""
    if not is_configured():
        return {}
    try:
        quote = get_index_quote(names)
    except Exception:
        return {}
    if not isinstance(quote, dict) or not quote:
        return {}

    key_map = {"NIFTY": "nifty", "BANKNIFTY": "bank_nifty", "INDIAVIX": "india_vix"}
    out = {}
    for name in names:
        key = key_map.get(name, name.lower())
        entry = quote.get(name, {})
        snapshot = _index_entry_to_snapshot(entry)
        if key == "india_vix" and snapshot.get("available"):
            # VIX value is the index level; keep a compact VIX shape.
            snapshot = {
                "available": True,
                "value": snapshot.get("price"),
                "change_percent": snapshot.get("change_percent"),
                "source": "DHAN_LIVE",
                "last_trade_time": snapshot.get("last_trade_time"),
            }
        out[key] = snapshot
    return out


# --------------------------------------------------------------------------
# HTTP (Dhan market-data endpoints only)
# --------------------------------------------------------------------------

def _post(path: str, body: dict[str, Any]) -> dict:
    """POST to a Dhan data endpoint and return the parsed JSON body.

    Raises RuntimeError on network failure or a Dhan error response so the
    caller can fall back to the existing NSE MCP / Yahoo sources.
    """
    import requests

    headers = {
        "access-token": get_access_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    if client_id:
        headers["client-id"] = client_id
    response = requests.post(
        f"{get_base_url()}{path}",
        json=body,
        headers=headers,
        timeout=30,
    )
    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code != 200 or (isinstance(data, dict) and data.get("errorType")):
        code = data.get("errorCode") if isinstance(data, dict) else None
        message = data.get("errorMessage") if isinstance(data, dict) else None
        raise RuntimeError(
            f"Dhan data request failed (HTTP {response.status_code}"
            + (f", {code}" if code else "")
            + f"): {message or response.text[:200]}"
            + ")"
        )

    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------
# Response -> DataFrame
# --------------------------------------------------------------------------

def _to_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert Dhan parallel-array candles into a Nova-style OHLCV DataFrame.

    Dhan returns open/high/low/close/volume as equal-length lists plus a
    timestamp list (epoch seconds). We zip them into rows indexed by IST date.
    """
    required = ("open", "high", "low", "close", "volume", "timestamp")
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(k), list) for k in required
    ):
        raise RuntimeError("Dhan returned an unexpected history payload.")

    lengths = {len(payload[k]) for k in required}
    if len(lengths) != 1:
        raise RuntimeError("Dhan history arrays have mismatched lengths.")

    rows = []
    for o, h, l, c, v, ts in zip(
        payload["open"],
        payload["high"],
        payload["low"],
        payload["close"],
        payload["volume"],
        payload["timestamp"],
    ):
        try:
            stamp = pd.to_datetime(int(ts), unit="s", utc=True).tz_convert(
                "Asia/Kolkata"
            )
        except (TypeError, ValueError):
            continue
        rows.append({
            "date": stamp.normalize(),
            "Open": float(o),
            "High": float(h),
            "Low": float(l),
            "Close": float(c),
            "Volume": int(v) if v is not None else 0,
        })

    if not rows:
        raise RuntimeError("Dhan returned no candles for the requested range.")

    frame = pd.DataFrame(rows)
    frame = frame.drop_duplicates(subset="date", keep="last").sort_values("date")
    frame = frame.set_index("date")[_COLUMNS]
    return frame


def _date_range(period: str):
    import datetime as _dt

    days = PERIOD_DAYS.get(period, PERIOD_DAYS["5d"])
    ist = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
    today = _dt.datetime.now(ist).date()
    # Dhan toDate is exclusive; include today.
    from_date = today - _dt.timedelta(days=days)
    to_date = today + _dt.timedelta(days=1)
    return from_date.isoformat(), to_date.isoformat()


def fetch_daily_candles(symbol: str, period: str, security_id: str) -> pd.DataFrame:
    """Fetch daily candles from Dhan and return a Nova-style DataFrame."""
    from_date, to_date = _date_range(period)
    payload = _post(
        "/charts/historical",
        {
            "securityId": str(security_id),
            "exchangeSegment": "NSE_EQ",
            "instrument": "EQUITY",
            "expiryCode": 0,
            "oi": False,
            "fromDate": from_date,
            "toDate": to_date,
        },
    )
    return _to_dataframe(payload)


# --------------------------------------------------------------------------
# Cache with freshness gate
# --------------------------------------------------------------------------

def _cache_file(symbol: str, interval: str = "1d") -> Path:
    return CACHE_DIR / f"{str(symbol).strip().upper()}_{interval}.json"


def _load_cache(symbol: str, interval: str, max_age_hours: float):
    """Return a cached DataFrame if present and fresh, else None."""
    path = _cache_file(symbol, interval)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(data.get("fetched_at", 0))
        rows = data.get("rows", [])
    except (OSError, ValueError, TypeError):
        return None

    age_hours = (time.time() - fetched_at) / 3600.0
    if age_hours < 0 or age_hours > max_age_hours:
        return None  # stale (or clock skew) -> refetch

    if not rows:
        return None
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date")[_COLUMNS].sort_index()
    return frame


def _save_cache(symbol: str, frame: pd.DataFrame, interval: str = "1d") -> None:
    try:
        payload = {
            "fetched_at": time.time(),
            "security_id": resolve_security_id(symbol),
            "rows": [
                {"date": idx.isoformat(), **{c: float(r[c]) for c in _COLUMNS}}
                for idx, r in frame.iterrows()
            ],
        }
        _cache_file(symbol, interval).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError, TypeError):
        pass  # cache write failure must never break analysis


# --------------------------------------------------------------------------
# Cache-first entry point used by the market-data layer
# --------------------------------------------------------------------------

def get_price_history_dhan(symbol: str, period: str = "5d") -> pd.DataFrame:
    """Cache-first daily history from Dhan.

    Returns a Nova-style DataFrame, or raises RuntimeError (always) so the
    caller can fall back to the existing NSE MCP / Yahoo chain. It raises when:
    Dhan is unconfigured, the symbol has no mapped security id, the cache is
    missing/stale and the live fetch fails, or the fetch yields no candles.
    """
    symbol = str(symbol).strip().upper()
    if not is_configured():
        raise RuntimeError("Dhan adapter is not configured (no access token).")

    fresh = _load_cache(symbol, "1d", MAX_AGE_HOURS)
    if fresh is not None:
        return fresh

    security_id = resolve_security_id(symbol)
    if not security_id:
        # Best-effort: build/lookup the public instrument-master map (cached
        # 16h) so symbols don't need manual mapping. Never invents an id.
        try:
            build_security_map()
            security_id = resolve_security_id(symbol)
        except Exception:
            security_id = None
    if not security_id:
        raise RuntimeError(
            f"No Dhan security id resolvable for {symbol}."
        )

    frame = fetch_daily_candles(symbol, period, security_id)
    _save_cache(symbol, frame)
    return frame
