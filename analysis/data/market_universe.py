"""
Nova Market Intelligence

NSE-first market data engine.

Primary source:
    indian-market-mcp
    -> NSE market data

Secondary fallback:
    Yahoo Finance

The fallback exists temporarily while the NSE data layer is
being validated. Nova should prefer NSE whenever available.

This module does NOT place trades.

Research principles:
    - observed market data is kept separate from analysis
    - timestamps are preserved
    - no market value is invented
    - no BUY/SELL decision is made here
    - analysis engines remain responsible for indicators,
      factors, regime, statistics, ML and risk
"""

from __future__ import annotations

import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from pathlib import Path
from typing import Iterable

import pandas as pd

from analysis.data.symbol_master import (
    load_master,
    search_symbols,
    get_security,
)

from analysis.data.nse_feed import (
    get_stock_quote as nse_get_stock_quote,
    get_stock_history as nse_get_stock_history,
)

from analysis.data.dhan_feed import (
    get_price_history_dhan,
    is_configured as dhan_configured,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CACHE_DIR = BASE_DIR / "cache"

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_PERIOD = "5d"
DEFAULT_INTERVAL = "1d"

INTRADAY_PERIOD = "1d"
INTRADAY_INTERVAL = "5m"

# Number of simultaneous NSE MCP requests during batch work.
#
# Keep this conservative. We do not want Nova hammering
# the public market-data service.
MAX_WORKERS = 5

REQUEST_DELAY = 0.10

# Temporary Yahoo fallback.
ENABLE_YAHOO_FALLBACK = True

# Optional primary historical-data source: the Dhan market-data adapter
# (analysis-only; cache-first). It is only attempted when an access token is
# configured; any Dhan failure silently falls through to the existing
# NSE MCP -> Yahoo chain, so behavior is unchanged when Dhan is disabled.
ENABLE_DHAN = True


# ============================================================
# OPTIONAL YAHOO IMPORT
# ============================================================

try:

    import yfinance as yf

    YAHOO_AVAILABLE = True

except ImportError:

    yf = None

    YAHOO_AVAILABLE = False


# ============================================================
# SYMBOL RESOLUTION
# ============================================================

def resolve_symbol(
    query: str,
) -> dict | None:
    """
    Resolve a user query into an NSE security.

    Resolution order:

        1. Exact NSE symbol
        2. Local NSE security-master search

    Market-data retrieval happens separately.
    """

    query = str(query).strip().upper()

    if not query:
        return None

    # Exact symbol first.
    security = get_security(query)

    if security:
        return security

    # Fuzzy symbol/company search.
    results = search_symbols(
        query,
        limit=1,
    )

    if results.empty:
        return None

    return results.iloc[0].to_dict()


# ============================================================
# SYMBOL NORMALIZATION
# ============================================================

def nse_symbol(
    symbol: str,
) -> str:
    """
    Normalize a symbol into an NSE symbol.

    Examples:

        RELIANCE      -> RELIANCE
        RELIANCE.NS   -> RELIANCE
    """

    symbol = str(
        symbol
    ).strip().upper()

    if symbol.endswith(".NS"):
        symbol = symbol[:-3]

    return symbol


def yahoo_symbol(
    nse_symbol_value: str,
) -> str:
    """
    Convert NSE symbol to Yahoo Finance symbol.

    Kept only for temporary fallback support.
    """

    symbol = nse_symbol(
        nse_symbol_value
    )

    return f"{symbol}.NS"


# ============================================================
# NUMERIC HELPERS
# ============================================================

def _safe_float(
    value,
):
    """
    Convert a value to float when possible.
    """

    if value is None:
        return None

    try:

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# NSE HISTORY NORMALIZATION
# ============================================================

def _history_to_dataframe(
    result,
) -> pd.DataFrame:
    """
    Convert the MCP historical-price response into a
    normalized OHLCV DataFrame.

    The MCP provider may return slightly different JSON
    structures depending on the underlying NSE response.

    We therefore normalize common field names rather than
    assuming one exact response shape.
    """

    if result is None:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Direct list
    # --------------------------------------------------------

    if isinstance(result, list):

        records = result

    # --------------------------------------------------------
    # Dictionary
    # --------------------------------------------------------

    elif isinstance(result, dict):

        records = None

        # Common containers.
        for key in (
            "data",
            "records",
            "historicalData",
            "history",
            "prices",
            "candles",
        ):

            candidate = result.get(
                key
            )

            if isinstance(
                candidate,
                list,
            ):

                records = candidate
                break

        # Sometimes data itself contains nested data.
        if records is None:

            for value in result.values():

                if isinstance(
                    value,
                    list,
                ):

                    if value and isinstance(
                        value[0],
                        dict,
                    ):

                        records = value
                        break

        if records is None:

            return pd.DataFrame()

    else:

        return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Convert records
    # --------------------------------------------------------

    rows = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        normalized = {}

        for key, value in record.items():

            normalized[
                str(key).strip().lower()
            ] = value

        # Date / timestamp
        timestamp = None

        for key in (
            "date",
            "datetime",
            "timestamp",
            "time",
            "trade_date",
        ):

            if key in normalized:

                timestamp = normalized[key]
                break

        # OHLCV
        open_value = None
        high_value = None
        low_value = None
        close_value = None
        volume_value = None

        for key in (
            "open",
            "openprice",
        ):

            if key in normalized:

                open_value = normalized[key]
                break

        for key in (
            "high",
            "highprice",
        ):

            if key in normalized:

                high_value = normalized[key]
                break

        for key in (
            "low",
            "lowprice",
        ):

            if key in normalized:

                low_value = normalized[key]
                break

        for key in (
            "close",
            "closeprice",
            "ltp",
        ):

            if key in normalized:

                close_value = normalized[key]
                break

        for key in (
            "volume",
            "totaltradedvolume",
            "total_traded_volume",
            "tradedvolume",
        ):

            if key in normalized:

                volume_value = normalized[key]
                break

        rows.append(
            {
                "Date": timestamp,
                "Open": _safe_float(
                    open_value
                ),
                "High": _safe_float(
                    high_value
                ),
                "Low": _safe_float(
                    low_value
                ),
                "Close": _safe_float(
                    close_value
                ),
                "Volume": _safe_float(
                    volume_value
                ),
            }
        )

    if not rows:
        return pd.DataFrame()

    dataframe = pd.DataFrame(
        rows
    )

    if "Date" in dataframe.columns:

        dataframe["Date"] = pd.to_datetime(
            dataframe["Date"],
            errors="coerce",
        )

        dataframe = dataframe.dropna(
            subset=["Date"]
        )

        if not dataframe.empty:

            dataframe = dataframe.set_index(
                "Date"
            )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    for column in required:

        if column not in dataframe.columns:

            dataframe[column] = None

    dataframe = dataframe[
        required
    ]

    dataframe = dataframe.dropna(
        subset=["Close"]
    )

    dataframe = dataframe.sort_index()

    return dataframe


# ============================================================
# NSE PRICE HISTORY
# ============================================================

def _get_nse_price_history(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    """
    Retrieve historical data from the NSE MCP layer.

    The MCP history interface uses explicit dates.

    For now we support the common daily-history use case
    required by Nova's analysis engines.
    """

    if interval != "1d":

        raise RuntimeError(
            "NSE history adapter currently supports "
            "daily data only. Intraday MCP support will "
            "be added after validating the provider's "
            "intraday schema."
        )

    # --------------------------------------------------------
    # Convert requested period to a reasonable date range.
    #
    # We intentionally use pandas date arithmetic here.
    # This is only a retrieval window, not market analysis.
    # --------------------------------------------------------

    today = pd.Timestamp.now(
        tz="Asia/Kolkata"
    ).normalize()

    period_days = {
        "1d": 3,
        "5d": 10,
        "1mo": 40,
        "3mo": 100,
        "6mo": 200,
        "1y": 380,
        "2y": 760,
        "5y": 1900,
    }

    days = period_days.get(
        period,
        30,
    )

    start = (
        today
        - pd.Timedelta(
            days=days
        )
    )

    from_date = start.strftime(
        "%d-%m-%Y"
    )

    to_date = today.strftime(
        "%d-%m-%Y"
    )

    result = nse_get_stock_history(
        symbol,
        from_date=from_date,
        to_date=to_date,
    )

    dataframe = _history_to_dataframe(
        result
    )

    if dataframe.empty:

        raise RuntimeError(
            f"NSE returned no usable historical "
            f"data for {symbol}"
        )

    return dataframe


# ============================================================
# YAHOO FALLBACK HISTORY
# ============================================================

def _get_yahoo_price_history(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:

    if not YAHOO_AVAILABLE:

        raise RuntimeError(
            "yfinance is not installed."
        )

    yahoo = yahoo_symbol(
        symbol
    )

    ticker = yf.Ticker(
        yahoo
    )

    data = ticker.history(
        period=period,
        interval=interval,
        auto_adjust=False,
        prepost=False,
        actions=False,
    )

    if data is None or data.empty:

        raise RuntimeError(
            f"No Yahoo Finance data returned "
            f"for {yahoo}"
        )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    available = [
        column
        for column in required
        if column in data.columns
    ]

    data = data[
        available
    ].copy()

    data = data.dropna(
        subset=["Close"]
    )

    if data.empty:

        raise RuntimeError(
            f"Price history contains no usable "
            f"data for {yahoo}"
        )

    return data


# ============================================================
# PRICE HISTORY
# ============================================================

def get_price_history(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """
    Download price history for an NSE symbol.

    NSE MCP is the primary source.

    Yahoo is only a temporary fallback.
    """

    symbol = nse_symbol(
        symbol
    )

    # Optional primary source: Dhan market-data adapter (analysis-only,
    # cache-first). Only attempted when configured; any failure falls through
    # to the existing NSE MCP -> Yahoo chain so behavior is otherwise unchanged.
    if ENABLE_DHAN and dhan_configured():
        try:
            return get_price_history_dhan(
                symbol,
                period,
            )
        except Exception as dhan_error:
            print(
                f"[DHAN FALLBACK] "
                f"{symbol}: {dhan_error}"
            )

    try:

        data = _get_nse_price_history(
            symbol,
            period,
            interval,
        )

        return data

    except Exception as nse_error:

        if not ENABLE_YAHOO_FALLBACK:

            raise RuntimeError(
                f"NSE market-data retrieval failed "
                f"for {symbol}: {nse_error}"
            ) from nse_error

        print(
            f"[NSE FALLBACK] "
            f"{symbol}: {nse_error}"
        )

        return _get_yahoo_price_history(
            symbol,
            period,
            interval,
        )


# ============================================================
# PREVIOUS CLOSE
# ============================================================

def get_previous_close(
    symbol: str,
) -> float | None:
    """
    Get the previous completed daily close.

    Uses Nova's normalized price history.
    """

    try:

        data = get_price_history(
            symbol,
            period="5d",
            interval="1d",
        )

        if len(data) < 2:

            return None

        return float(
            data.iloc[-2]["Close"]
        )

    except Exception:

        return None


# ============================================================
# SINGLE STOCK SNAPSHOT
# ============================================================

def get_stock_snapshot(
    query: str,
    intraday: bool = False,
) -> dict:
    """
    Get a complete market snapshot for one NSE stock.

    Live/current quote comes directly from NSE MCP.

    Historical fields are supplemented from the history
    layer where necessary.
    """

    security = resolve_symbol(
        query
    )

    if security is None:

        raise ValueError(
            f"Could not find NSE security: {query}"
        )

    symbol = nse_symbol(
        security["symbol"]
    )

    # --------------------------------------------------------
    # Live NSE quote
    # --------------------------------------------------------

    try:

        quote = nse_get_stock_quote(
            symbol
        )

    except Exception as exc:

        if not ENABLE_YAHOO_FALLBACK:

            raise RuntimeError(
                f"NSE quote failed for {symbol}: "
                f"{exc}"
            ) from exc

        quote = None

    # --------------------------------------------------------
    # If the NSE quote worked, normalize it.
    # --------------------------------------------------------

    if isinstance(
        quote,
        dict,
    ):

        return _normalize_nse_quote(
            security,
            quote,
            intraday,
        )

    # --------------------------------------------------------
    # Temporary fallback.
    # --------------------------------------------------------

    data = get_price_history(
        symbol,
        period=(
            INTRADAY_PERIOD
            if intraday
            else DEFAULT_PERIOD
        ),
        interval=(
            INTRADAY_INTERVAL
            if intraday
            else DEFAULT_INTERVAL
        ),
    )

    latest = data.iloc[-1]

    price = float(
        latest["Close"]
    )

    previous_close = (
        get_previous_close(
            symbol
        )
    )

    if previous_close is not None:

        change = (
            price
            - previous_close
        )

        change_percent = (
            change
            / previous_close
        ) * 100

    else:

        change = None
        change_percent = None

    timestamp = pd.Timestamp(
        data.index[-1]
    )

    if timestamp.tzinfo is None:

        timestamp = (
            timestamp.tz_localize(
                "Asia/Kolkata"
            )
        )

    else:

        timestamp = (
            timestamp.tz_convert(
                "Asia/Kolkata"
            )
        )

    return {
        "symbol": symbol,

        "company_name": security.get(
            "company_name",
            "",
        ),

        "exchange": "NSE",

        "series": security.get(
            "series",
            "",
        ),

        "isin": security.get(
            "isin",
            "",
        ),

        "price": price,

        "open": float(
            latest["Open"]
        ),

        "high": float(
            latest["High"]
        ),

        "low": float(
            latest["Low"]
        ),

        "previous_close": previous_close,

        "change": change,

        "change_percent": change_percent,

        "volume": float(
            latest["Volume"]
        ),

        "timestamp": timestamp.isoformat(),

        "interval": (
            INTRADAY_INTERVAL
            if intraday
            else DEFAULT_INTERVAL
        ),

        "source": "Yahoo Finance fallback",
    }


def _normalize_nse_quote(
    security: dict,
    quote: dict,
    intraday: bool,
) -> dict:
    """
    Normalize the MCP stock quote into Nova's
    established snapshot contract.
    """

    # The adapter normally returns the provider's
    # JSON directly. Handle both direct and nested
    # structures.

    source = quote

    if isinstance(
        quote.get("data"),
        dict,
    ):

        source = quote["data"]

    def first_value(
        *keys,
    ):

        for key in keys:

            if key in source:

                return source[key]

        return None

    symbol = nse_symbol(
        security["symbol"]
    )

    price = _safe_float(
        first_value(
            "price",
            "lastPrice",
            "last",
            "ltp",
        )
    )

    open_value = _safe_float(
        first_value(
            "open",
            "openPrice",
        )
    )

    high_value = _safe_float(
        first_value(
            "high",
            "highPrice",
        )
    )

    low_value = _safe_float(
        first_value(
            "low",
            "lowPrice",
        )
    )

    previous_close = _safe_float(
        first_value(
            "previousClose",
            "prevClose",
            "previous_close",
        )
    )

    change = _safe_float(
        first_value(
            "change",
        )
    )

    change_percent = _safe_float(
        first_value(
            "percentChange",
            "pChange",
            "changePercent",
            "change_percent",
        )
    )

    volume = _safe_float(
        first_value(
            "volume",
            "totalTradedVolume",
            "total_traded_volume",
        )
    )

    timestamp = first_value(
        "timestamp",
        "time",
        "lastUpdateTime",
        "lastUpdated",
    )

    # If provider supplies no timestamp, preserve the
    # retrieval moment rather than pretending we know
    # the exchange timestamp.
    if timestamp is None:

        timestamp = (
            pd.Timestamp.now(
                tz="Asia/Kolkata"
            ).isoformat()
        )

    return {
        "symbol": symbol,

        "company_name": security.get(
            "company_name",
            "",
        ),

        "exchange": "NSE",

        "series": security.get(
            "series",
            "",
        ),

        "isin": security.get(
            "isin",
            "",
        ),

        "price": price,

        "open": open_value,

        "high": high_value,

        "low": low_value,

        "previous_close": previous_close,

        "change": change,

        "change_percent": change_percent,

        "volume": volume,

        "timestamp": str(
            timestamp
        ),

        "interval": (
            "live"
            if not intraday
            else INTRADAY_INTERVAL
        ),

        "source": "NSE MCP",
    }


# ============================================================
# BATCH QUOTE
# ============================================================

def _fetch_one_quote(
    symbol: str,
) -> dict | None:
    """
    Retrieve one live NSE quote.

    This function is deliberately isolated so batch
    retrieval can be throttled.
    """

    try:

        result = get_stock_snapshot(
            symbol,
            intraday=False,
        )

        time.sleep(
            REQUEST_DELAY
        )

        return result

    except Exception as exc:

        print(
            f"[QUOTE FAILED] "
            f"{symbol}: {exc}"
        )

        return None


def download_market_batch(
    symbols: Iterable[str],
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """
    Download current market data for multiple NSE
    securities.

    NSE MCP is used as the primary source.

    NOTE:
        The current MCP adapter exposes single-symbol
        quote calls rather than a bulk quote endpoint.

        Therefore this function uses a conservative
        worker pool instead of making thousands of
        uncontrolled requests.
    """

    del period
    del interval

    symbols = [
        nse_symbol(symbol)
        for symbol in symbols
        if str(symbol).strip()
    ]

    symbols = list(
        dict.fromkeys(
            symbols
        )
    )

    if not symbols:

        return pd.DataFrame()

    print(
        f"Retrieving NSE market data for "
        f"{len(symbols):,} securities..."
    )

    rows = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                _fetch_one_quote,
                symbol,
            ): symbol
            for symbol in symbols
        }

        for future in as_completed(
            futures
        ):

            symbol = futures[
                future
            ]

            try:

                result = future.result()

            except Exception as exc:

                print(
                    f"[BATCH FAILED] "
                    f"{symbol}: {exc}"
                )

                continue

            if result is not None:

                rows.append(
                    {
                        "symbol": result.get(
                            "symbol",
                            symbol,
                        ),

                        "price": result.get(
                            "price"
                        ),

                        "open": result.get(
                            "open"
                        ),

                        "high": result.get(
                            "high"
                        ),

                        "low": result.get(
                            "low"
                        ),

                        "previous_close": (
                            result.get(
                                "previous_close"
                            )
                        ),

                        "change": result.get(
                            "change"
                        ),

                        "change_percent": (
                            result.get(
                                "change_percent"
                            )
                        ),

                        "volume": result.get(
                            "volume"
                        ),

                        "timestamp": result.get(
                            "timestamp"
                        ),

                        "source": result.get(
                            "source",
                            "NSE MCP",
                        ),
                    }
                )

    if not rows:

        raise RuntimeError(
            "NSE market batch returned no "
            "usable data."
        )

    dataframe = pd.DataFrame(
        rows
    )

    return dataframe.sort_values(
        "symbol"
    ).reset_index(
        drop=True
    )


# ============================================================
# NSE UNIVERSE
# ============================================================

def get_nse_symbols(
    series: str = "EQ",
) -> list[str]:
    """
    Return NSE symbols from the local
    NSE security master.
    """

    master = load_master()

    if series:

        filtered = master[
            master["series"]
            .str.upper()
            == series.upper()
        ]

    else:

        filtered = master

    symbols = (
        filtered["symbol"]
        .dropna()
        .astype(str)
        .str.upper()
        .drop_duplicates()
        .tolist()
    )

    return symbols


# ============================================================
# FULL MARKET SCAN
# ============================================================

def scan_nse_market(
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Scan the NSE equity universe.

    limit:
        Development/testing limit.

    WARNING:
        With the current public MCP interface,
        scanning the entire NSE universe is considerably
        more expensive than Yahoo's batch endpoint.

        Start with a small limit while validating the
        NSE data layer.
    """

    symbols = get_nse_symbols(
        series="EQ"
    )

    if limit is not None:

        symbols = symbols[
            :limit
        ]

    if not symbols:

        raise RuntimeError(
            "No NSE EQ securities found."
        )

    print()
    print("=" * 70)
    print("NOVA NSE MARKET SCANNER")
    print("=" * 70)

    print(
        f"Universe requested: "
        f"{len(symbols):,} securities"
    )

    print(
        "Primary source: NSE MCP"
    )

    print()

    data = download_market_batch(
        symbols,
    )

    if data.empty:

        raise RuntimeError(
            "Market scan returned no "
            "usable NSE data."
        )

    data = (
        data
        .sort_values("symbol")
        .reset_index(
            drop=True
        )
    )

    return data


# ============================================================
# MARKET LEADERS
# ============================================================

def top_gainers(
    dataframe: pd.DataFrame,
    count: int = 20,
) -> pd.DataFrame:

    if dataframe.empty:

        return dataframe

    result = dataframe.copy()

    if "change_percent" not in result.columns:

        return result.head(
            count
        )

    return (
        result
        .sort_values(
            "change_percent",
            ascending=False,
        )
        .head(count)
    )


# ============================================================
# MARKET LOSERS
# ============================================================

def top_losers(
    dataframe: pd.DataFrame,
    count: int = 20,
) -> pd.DataFrame:

    if dataframe.empty:

        return dataframe

    if "change_percent" not in dataframe.columns:

        return dataframe.head(
            count
        )

    return (
        dataframe
        .sort_values(
            "change_percent",
            ascending=True,
        )
        .head(count)
    )


# ============================================================
# SIMPLE STOCK QUERY
# ============================================================

def query_stock(
    query: str,
) -> dict:

    return get_stock_snapshot(
        query,
        intraday=False,
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("NOVA MARKET DATA ENGINE — NSE FIRST")
    print("=" * 70)

    # --------------------------------------------------------
    # Individual stock
    # --------------------------------------------------------

    print()
    print(
        "TEST 1 — NSE INDIVIDUAL STOCK"
    )

    print(
        "-" * 70
    )

    try:

        result = query_stock(
            "RELIANCE"
        )

        for key, value in result.items():

            print(
                f"{key:<20}: {value}"
            )

    except Exception as exc:

        print(
            f"Stock test failed: {exc}"
        )

    # --------------------------------------------------------
    # Small market test
    # --------------------------------------------------------

    print()
    print(
        "TEST 2 — NSE MARKET BATCH"
    )

    print(
        "-" * 70
    )

    try:

        scan = scan_nse_market(
            limit=10
        )

        print()

        print(
            scan.to_string(
                index=False
            )
        )

    except Exception as exc:

        print(
            f"Market scan failed: {exc}"
        )

    print()
    print("=" * 70)
    print(
        "MARKET DATA ENGINE TEST COMPLETE"
    )
    print("=" * 70)