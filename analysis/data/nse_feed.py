"""
Nova NSE Market Data Adapter

Primary market-data source:
    indian-market-mcp

The adapter provides Nova with:
    - Live NSE stock quotes
    - NSE indices
    - Index constituents
    - Historical stock data
    - Historical index data
    - Market status
    - Advances / declines
    - Sector performance
    - FII / DII data
    - Bulk deals
    - Shareholding
    - Options
    - PCR
    - Max pain
    - Futures
    - Open interest
    - Technical provider data
    - Support / resistance

IMPORTANT
---------
This module is a DATA LAYER.

It does not:
    - generate BUY/SELL signals
    - place trades
    - make investment decisions
    - replace Nova's technical engine
    - replace Nova's statistical engine
    - replace Nova's risk engine

Raw market observations are kept separate from
Nova's higher-level analysis.

The installed MCP server is launched through the
current Python virtual environment.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================
# CONFIGURATION
# ============================================================

SERVER_NAME = "indian-market-mcp.exe"


# ============================================================
# EXCEPTION
# ============================================================

class NSEFeedError(Exception):
    """Raised when Nova cannot retrieve NSE market data."""


# ============================================================
# SERVER LOCATION
# ============================================================

def get_server_path() -> Path:
    """
    Locate indian-market-mcp.exe inside Nova's active
    virtual environment.
    """

    python_path = Path(
        sys.executable
    ).resolve()

    server_path = (
        python_path.parent
        / SERVER_NAME
    )

    if not server_path.exists():

        raise NSEFeedError(
            "indian-market-mcp.exe was not found at:\n"
            f"{server_path}"
        )

    return server_path


# ============================================================
# MCP TOOL CALL
# ============================================================

async def _call_tool_async(
    tool_name: str,
    arguments: Optional[
        Dict[str, Any]
    ] = None,
) -> Any:
    """
    Start the Indian Market MCP server, connect to it,
    execute one tool and return the result.
    """

    server_path = get_server_path()

    server_params = StdioServerParameters(
        command=str(server_path),
        args=[],
        env=None,
    )

    try:

        async with stdio_client(
            server_params
        ) as (
            read_stream,
            write_stream,
        ):

            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:

                await session.initialize()

                result = await session.call_tool(
                    tool_name,
                    arguments or {},
                )

                return _extract_result(
                    result
                )

    except Exception as exc:

        raise NSEFeedError(
            f"MCP tool '{tool_name}' failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _call_tool(
    tool_name: str,
    arguments: Optional[
        Dict[str, Any]
    ] = None,
) -> Any:
    """
    Synchronous interface used by Nova's
    current analysis modules.
    """

    try:

        return asyncio.run(
            _call_tool_async(
                tool_name,
                arguments,
            )
        )

    except RuntimeError as exc:

        raise NSEFeedError(
            "NSE feed was called while another "
            "asyncio event loop is already running. "
            "Use the async interface instead."
        ) from exc


# ============================================================
# MCP RESULT NORMALIZATION
# ============================================================

def _extract_result(
    result: Any,
) -> Any:
    """
    Convert MCP CallToolResult into normal Python data.

    JSON responses are decoded automatically.
    Plain text responses remain strings.
    """

    if result is None:
        return None

    content = getattr(
        result,
        "content",
        None,
    )

    if content is None:
        return result

    extracted = []

    for item in content:

        text = getattr(
            item,
            "text",
            None,
        )

        if text is not None:

            try:

                extracted.append(
                    json.loads(text)
                )

            except (
                TypeError,
                ValueError,
            ):

                extracted.append(
                    text
                )

        else:

            extracted.append(
                item
            )

    if len(extracted) == 1:

        return extracted[0]

    return extracted


# ============================================================
# HELPERS
# ============================================================

def _safe_float(
    value: Any,
) -> Optional[float]:
    """
    Safely convert a value to float.
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


def _first_value(
    data: dict,
    *keys: str,
) -> Any:
    """
    Return the first available value from a list of keys.
    """

    for key in keys:

        if key in data:

            return data[key]

    return None


def _unwrap_data(
    data: Any,
) -> Any:
    """
    Unwrap common MCP response containers.
    """

    if not isinstance(
        data,
        dict,
    ):

        return data

    if isinstance(
        data.get("data"),
        dict,
    ):

        return data["data"]

    return data


# ============================================================
# SYMBOL NORMALIZATION
# ============================================================

def normalize_symbol(
    symbol: str,
) -> str:
    """
    Normalize an NSE symbol.

    Examples:

        RELIANCE
        RELIANCE.NS

    both become:

        RELIANCE
    """

    symbol = str(
        symbol
    ).strip().upper()

    if symbol.endswith(".NS"):

        symbol = symbol[:-3]

    return symbol


# ============================================================
# STOCK QUOTE
# ============================================================

def get_stock_quote(
    symbol: str,
) -> Any:
    """
    Get the raw live NSE stock quote.

    Example:

        get_stock_quote("RELIANCE")
    """

    symbol = normalize_symbol(
        symbol
    )

    if not symbol:

        raise ValueError(
            "Stock symbol cannot be empty."
        )

    return _call_tool(
        "get_stock_quote",
        {
            "symbol": symbol,
        },
    )


# ============================================================
# NORMALIZED STOCK QUOTE
# ============================================================

def normalize_stock_quote(
    symbol: str,
    quote: dict,
) -> dict:
    """
    Normalize the actual indian-market-mcp stock quote.

    Observed MCP schema:

        symbol
        company
        industry
        price
        change
        change_percent
        open
        close
        day_high
        day_low
        week_52_high
        week_52_low
        total_traded_volume

    IMPORTANT:

    The provider's 'close' field represents the previous
    completed close in the live quote response.

    Example observed response:

        price  = 1207.7
        change = -10.300049
        close  = 1218.0

    Therefore:

        previous_close = close

    is preferred over reconstructing it from price/change.
    """

    source = _unwrap_data(
        quote
    )

    if not isinstance(
        source,
        dict,
    ):

        raise NSEFeedError(
            "Unexpected stock quote response format."
        )

    symbol = normalize_symbol(
        symbol
    )

    # --------------------------------------------------------
    # Actual MCP fields
    # --------------------------------------------------------

    price = _safe_float(
        _first_value(
            source,
            "price",
        )
    )

    change = _safe_float(
        _first_value(
            source,
            "change",
        )
    )

    change_percent = _safe_float(
        _first_value(
            source,
            "change_percent",
            "changePercent",
            "percentChange",
            "pChange",
        )
    )

    open_value = _safe_float(
        _first_value(
            source,
            "open",
        )
    )

    # MCP's live quote "close" is the previous
    # completed close.
    previous_close = _safe_float(
        _first_value(
            source,
            "close",
        )
    )

    high_value = _safe_float(
        _first_value(
            source,
            "day_high",
            "dayHigh",
            "high",
        )
    )

    low_value = _safe_float(
        _first_value(
            source,
            "day_low",
            "dayLow",
            "low",
        )
    )

    week_52_high = _safe_float(
        _first_value(
            source,
            "week_52_high",
            "week52High",
            "52_week_high",
        )
    )

    week_52_low = _safe_float(
        _first_value(
            source,
            "week_52_low",
            "week52Low",
            "52_week_low",
        )
    )

    volume = _safe_float(
        _first_value(
            source,
            "total_traded_volume",
            "totalTradedVolume",
            "volume",
        )
    )

    company = _first_value(
        source,
        "company",
        "company_name",
        "name",
    )

    industry = _first_value(
        source,
        "industry",
    )

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------
    #
    # The observed get_stock_quote response does not expose
    # an exchange timestamp.
    #
    # Therefore this is explicitly marked as the local
    # retrieval time.
    # --------------------------------------------------------

    timestamp = pd.Timestamp.now(
        tz="Asia/Kolkata"
    ).isoformat()

    return {
        "symbol": symbol,

        "company_name": (
            str(company)
            if company is not None
            else ""
        ),

        "industry": (
            str(industry)
            if industry is not None
            else ""
        ),

        "exchange": "NSE",

        "price": price,

        "open": open_value,

        "high": high_value,

        "low": low_value,

        "close": previous_close,

        "previous_close": previous_close,

        "change": change,

        "change_percent": change_percent,

        "volume": volume,

        "week_52_high": week_52_high,

        "week_52_low": week_52_low,

        "timestamp": timestamp,

        "timestamp_type": (
            "local_retrieval_time"
        ),

        "source": "NSE MCP",
    }


def get_normalized_stock_quote(
    symbol: str,
) -> dict:
    """
    Get and normalize a live NSE stock quote.
    """

    symbol = normalize_symbol(
        symbol
    )

    raw = get_stock_quote(
        symbol
    )

    return normalize_stock_quote(
        symbol,
        raw,
    )


# ============================================================
# STOCK HISTORY
# ============================================================

def get_stock_history(
    symbol: str,
    from_date: str = "",
    to_date: str = "",
) -> Any:
    """
    Get historical NSE stock OHLC data.

    Date format:

        DD-MM-YYYY
    """

    symbol = normalize_symbol(
        symbol
    )

    arguments = {
        "symbol": symbol,
    }

    if from_date:

        arguments[
            "from_date"
        ] = from_date

    if to_date:

        arguments[
            "to_date"
        ] = to_date

    return _call_tool(
        "get_stock_history",
        arguments,
    )


# ============================================================
# HISTORY -> DATAFRAME
# ============================================================

def history_to_dataframe(
    result: Any,
) -> pd.DataFrame:
    """
    Convert the actual NSE MCP historical response
    into Nova's standard OHLCV DataFrame.

    Actual observed NSE fields:

        CH_TIMESTAMP
        CH_OPENING_PRICE
        CH_TRADE_HIGH_PRICE
        CH_TRADE_LOW_PRICE
        CH_CLOSING_PRICE
        CH_TOT_TRADED_QTY
    """

    if result is None:
        return pd.DataFrame()

    # --------------------------------------------------------
    # The MCP returns the historical records directly as a
    # list in the observed response.
    #
    # Also support a few common wrapper formats so the
    # adapter remains robust.
    # --------------------------------------------------------

    if isinstance(result, list):

        records = result

    elif isinstance(result, dict):

        records = None

        for key in (
            "data",
            "records",
            "history",
            "historicalData",
            "prices",
            "candles",
        ):

            candidate = result.get(key)

            if isinstance(
                candidate,
                list,
            ):

                records = candidate
                break

        if records is None:

            return pd.DataFrame()

    else:

        return pd.DataFrame()

    if not records:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Parse NSE records
    # --------------------------------------------------------

    rows = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        date_value = record.get(
            "CH_TIMESTAMP"
        )

        open_value = record.get(
            "CH_OPENING_PRICE"
        )

        high_value = record.get(
            "CH_TRADE_HIGH_PRICE"
        )

        low_value = record.get(
            "CH_TRADE_LOW_PRICE"
        )

        close_value = record.get(
            "CH_CLOSING_PRICE"
        )

        volume_value = record.get(
            "CH_TOT_TRADED_QTY"
        )

        rows.append(
            {
                "Date": date_value,

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

    # --------------------------------------------------------
    # Parse dates
    # --------------------------------------------------------

    dataframe["Date"] = pd.to_datetime(
        dataframe["Date"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Remove unusable rows
    # --------------------------------------------------------

    dataframe = dataframe.dropna(
        subset=[
            "Date",
            "Close",
        ]
    )

    if dataframe.empty:

        return pd.DataFrame()

    # --------------------------------------------------------
    # Standard datetime index
    # --------------------------------------------------------

    dataframe = dataframe.set_index(
        "Date"
    )

    # --------------------------------------------------------
    # Ensure numeric OHLCV
    # --------------------------------------------------------

    for column in (
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ):

        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    # --------------------------------------------------------
    # Sort chronologically
    # --------------------------------------------------------

    dataframe = (
        dataframe
        .sort_index()
        .copy()
    )

    # --------------------------------------------------------
    # Remove duplicate dates
    # --------------------------------------------------------

    dataframe = dataframe[
        ~dataframe.index.duplicated(
            keep="last"
        )
    ]

    # --------------------------------------------------------
    # Final column order
    # --------------------------------------------------------

    dataframe = dataframe[
        [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    ]

    return dataframe
    # --------------------------------------------------------
    # Datetime index
    # --------------------------------------------------------

    dataframe["Date"] = pd.to_datetime(
        dataframe["Date"],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=[
            "Date",
            "Close",
        ]
    )

    if dataframe.empty:

        return pd.DataFrame()

    dataframe = dataframe.set_index(
        "Date"
    )

    # --------------------------------------------------------
    # Ensure standard OHLCV columns
    # --------------------------------------------------------

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

    dataframe = dataframe.sort_index()

    return dataframe


def get_stock_history_dataframe(
    symbol: str,
    from_date: str = "",
    to_date: str = "",
) -> pd.DataFrame:
    """
    Retrieve historical stock data and return a DataFrame.
    """

    result = get_stock_history(
        symbol,
        from_date=from_date,
        to_date=to_date,
    )

    dataframe = history_to_dataframe(
        result
    )

    if dataframe.empty:

        raise NSEFeedError(
            f"No usable historical data returned "
            f"for {symbol}."
        )

    return dataframe


# ============================================================
# INDICES
# ============================================================

def get_index(
    name: str,
) -> Any:
    """
    Get live NSE index data.

    Examples:

        NIFTY 50
        NIFTY BANK
        NIFTY IT
        NIFTY FINANCIAL SERVICES
    """

    name = str(
        name
    ).strip()

    if not name:

        raise ValueError(
            "Index name cannot be empty."
        )

    return _call_tool(
        "get_index",
        {
            "name": name,
        },
    )


def get_all_indices() -> Any:
    """
    Get all available NSE indices.
    """

    return _call_tool(
        "get_all_indices"
    )


def get_index_constituents(
    name: str,
) -> Any:
    """
    Get index constituents.
    """

    return _call_tool(
        "get_index_constituents",
        {
            "name": str(
                name
            ).strip(),
        },
    )


def get_index_history(
    index: str,
    from_date: str = "",
    to_date: str = "",
) -> Any:
    """
    Get historical NSE index data.
    """

    arguments = {
        "index": str(
            index
        ).strip(),
    }

    if from_date:

        arguments[
            "from_date"
        ] = from_date

    if to_date:

        arguments[
            "to_date"
        ] = to_date

    return _call_tool(
        "get_index_history",
        arguments,
    )


# ============================================================
# MARKET STATUS
# ============================================================

def get_market_status() -> Any:
    """
    Get the current Indian market status.
    """

    return _call_tool(
        "get_market_status"
    )


# ============================================================
# MARKET BREADTH
# ============================================================

def get_advances_declines() -> Any:
    """
    Get NSE market advances and declines.
    """

    return _call_tool(
        "get_advances_declines"
    )


# ============================================================
# SECTOR DATA
# ============================================================

def get_sector_performance() -> Any:
    """
    Get current NSE sector performance.
    """

    return _call_tool(
        "get_sector_performance"
    )


# ============================================================
# MARKET LEADERS
# ============================================================

def get_top_gainers() -> Any:
    """
    Get top NSE gainers.
    """

    return _call_tool(
        "get_top_gainers"
    )


def get_top_losers() -> Any:
    """
    Get top NSE losers.
    """

    return _call_tool(
        "get_top_losers"
    )


def get_most_active_stocks(
    by: str = "volume",
) -> Any:
    """
    Get most-active NSE stocks.

    by:
        volume
        value
    """

    by = str(
        by
    ).strip().lower()

    if by not in {
        "volume",
        "value",
    }:

        raise ValueError(
            "by must be 'volume' or 'value'."
        )

    return _call_tool(
        "get_most_active_stocks",
        {
            "by": by,
        },
    )


# ============================================================
# INSTITUTIONAL FLOW
# ============================================================

def get_fii_dii_data() -> Any:
    """
    Get reported FII/DII activity.
    """

    return _call_tool(
        "get_fii_dii_data"
    )


def get_bulk_deals() -> Any:
    """
    Get NSE bulk/block deals.
    """

    return _call_tool(
        "get_bulk_deals"
    )


def get_shareholding_pattern(
    symbol: str,
) -> Any:
    """
    Get promoter/FII/DII/public ownership data.

    IMPORTANT:

    Shareholding is ownership information.

    It is not equivalent to daily FII/DII trading flow.
    """

    return _call_tool(
        "get_shareholding_pattern",
        {
            "symbol": normalize_symbol(
                symbol
            ),
        },
    )


# ============================================================
# DERIVATIVES
# ============================================================

def get_option_chain(
    symbol: str,
    is_index: bool = True,
) -> Any:
    """
    Get option-chain data.

    Examples:

        NIFTY
        BANKNIFTY
        FINNIFTY
        RELIANCE
    """

    return _call_tool(
        "get_option_chain",
        {
            "symbol": normalize_symbol(
                symbol
            ),
            "is_index": bool(
                is_index
            ),
        },
    )


def get_pcr(
    symbol: str,
) -> Any:
    """
    Get Put-Call Ratio.
    """

    return _call_tool(
        "get_pcr",
        {
            "symbol": normalize_symbol(
                symbol
            ),
        },
    )


def get_max_pain(
    symbol: str,
) -> Any:
    """
    Get maximum-pain strike.
    """

    return _call_tool(
        "get_max_pain",
        {
            "symbol": normalize_symbol(
                symbol
            ),
        },
    )


def get_futures_data(
    symbol: str,
) -> Any:
    """
    Get futures data.
    """

    return _call_tool(
        "get_futures_data",
        {
            "symbol": normalize_symbol(
                symbol
            ),
        },
    )


def get_oi_data(
    symbol: str,
) -> Any:
    """
    Get derivative open-interest data.
    """

    return _call_tool(
        "get_oi_data",
        {
            "symbol": normalize_symbol(
                symbol
            ),
        },
    )


# ============================================================
# TECHNICAL PROVIDER DATA
# ============================================================

def get_technical_indicators(
    symbol: str,
    period: str = "6mo",
) -> Any:
    """
    Retrieve provider-side technical indicators.

    Nova's own technical_engine.py remains the authoritative
    calculation layer for Nova's technical analysis.
    """

    return _call_tool(
        "get_technical_indicators",
        {
            "symbol": normalize_symbol(
                symbol
            ),
            "period": period,
        },
    )


def get_support_resistance(
    symbol: str,
    period: str = "3mo",
) -> Any:
    """
    Retrieve provider-side support/resistance levels.
    """

    return _call_tool(
        "get_support_resistance",
        {
            "symbol": normalize_symbol(
                symbol
            ),
            "period": period,
        },
    )


# ============================================================
# COMPLETE MARKET SNAPSHOT
# ============================================================

def get_market_snapshot() -> Dict[str, Any]:
    """
    Retrieve the core market environment.

    Includes:

        Market status
        NIFTY 50
        BANK NIFTY
        Market breadth
        Sector performance
        FII/DII
    """

    return {
        "source": "indian-market-mcp",

        "retrieved_at": (
            pd.Timestamp.now(
                tz="Asia/Kolkata"
            ).isoformat()
        ),

        "market_status": (
            get_market_status()
        ),

        "nifty_50": (
            get_index(
                "NIFTY 50"
            )
        ),

        "bank_nifty": (
            get_index(
                "NIFTY BANK"
            )
        ),

        "breadth": (
            get_advances_declines()
        ),

        "sector_performance": (
            get_sector_performance()
        ),

        "fii_dii": (
            get_fii_dii_data()
        ),
    }


# ============================================================
# BASIC TEST
# ============================================================

def main() -> None:

    print()
    print("=" * 80)
    print("NOVA NSE MARKET DATA ADAPTER")
    print("=" * 80)

    print()
    print(
        "MCP SERVER:"
    )

    print(
        get_server_path()
    )

    # --------------------------------------------------------
    # MARKET STATUS
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("1. MARKET STATUS")
    print("=" * 80)

    try:

        result = get_market_status()

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # NIFTY
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("2. NIFTY 50")
    print("=" * 80)

    try:

        result = get_index(
            "NIFTY 50"
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # BANK NIFTY
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("3. BANK NIFTY")
    print("=" * 80)

    try:

        result = get_index(
            "NIFTY BANK"
        )

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # RELIANCE
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("4. RELIANCE")
    print("=" * 80)

    try:

        raw = get_stock_quote(
            "RELIANCE"
        )

        normalized = normalize_stock_quote(
            "RELIANCE",
            raw,
        )

        print(
            json.dumps(
                normalized,
                indent=2,
                default=str,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # BREADTH
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("5. MARKET BREADTH")
    print("=" * 80)

    try:

        result = get_advances_declines()

        print(
            json.dumps(
                result,
                indent=2,
                default=str,
            )
        )

    except Exception as exc:

        print(
            f"ERROR: {exc}"
        )

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("NSE MARKET DATA ADAPTER TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":

    main()