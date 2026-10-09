"""
NOVA DERIVATIVES INTELLIGENCE ENGINE
====================================

NSE index options analysis engine for Nova Market Lab.

Supported:
    - NIFTY
    - BANKNIFTY

Current NSE API flow:
    1. Warm NSE website/session
    2. option-chain-contract-info
    3. option-chain-v3

Derived intelligence:
    - Spot
    - Expiry
    - ATM
    - Call OI
    - Put OI
    - Change in OI
    - Call / Put volume
    - Call / Put IV
    - LTP
    - Premium change
    - OI PCR
    - Volume PCR
    - Max Pain
    - Call OI wall
    - Put OI wall
    - Support / resistance
    - ATM IV
    - IV skew
    - OI concentration
    - Unusual activity
    - Positioning interpretation

IMPORTANT:
    ANALYSIS ONLY.

    No broker.
    No orders.
    No execution.
    No automatic trading.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# OPTIONAL HTTP CLIENTS
# ============================================================

try:
    from curl_cffi import requests as curl_requests

    CURL_CFFI_AVAILABLE = True

except Exception:

    curl_requests = None
    CURL_CFFI_AVAILABLE = False


try:
    import requests

except Exception as exc:

    print(
        "[ERROR] requests is required."
    )

    raise exc


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CACHE_DIR = (
    BASE_DIR
    / "cache"
    / "derivatives"
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# NSE ENDPOINTS
# ============================================================

NSE_HOME_URL = (
    "https://www.nseindia.com/"
)

NSE_OPTION_CHAIN_PAGE = (
    "https://www.nseindia.com/option-chain"
)

NSE_CONTRACT_INFO_URL = (
    "https://www.nseindia.com/api/"
    "option-chain-contract-info"
)

NSE_OPTION_CHAIN_V3_URL = (
    "https://www.nseindia.com/api/"
    "option-chain-v3"
)


# ============================================================
# SUPPORTED INSTRUMENTS
# ============================================================

SUPPORTED_SYMBOLS = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}


# ============================================================
# CONFIG
# ============================================================

REQUEST_TIMEOUT = 25

MAX_RETRIES = 3

REQUEST_DELAY = 1.0

STRIKE_WINDOW = 20

TOP_OI_COUNT = 10

TOP_ACTIVITY_COUNT = 10

UNUSUAL_VOLUME_OI_RATIO = 2.0

UNUSUAL_OI_CHANGE_RATIO = 0.10


# ============================================================
# BROWSER HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),

    "Accept": (
        "application/json,text/plain,*/*"
    ),

    "Accept-Language": (
        "en-US,en;q=0.9"
    ),

    # Do NOT advertise Brotli here for the requests fallback.
    # curl_cffi handles browser-style compression itself.
    "Accept-Encoding": (
        "gzip, deflate"
    ),

    "Referer":
        NSE_OPTION_CHAIN_PAGE,

    "Connection":
        "keep-alive",

    "Cache-Control":
        "no-cache",

    "Pragma":
        "no-cache",

    "X-Requested-With":
        "XMLHttpRequest",

    "sec-fetch-dest":
        "empty",

    "sec-fetch-mode":
        "cors",

    "sec-fetch-site":
        "same-origin",
}


# ============================================================
# GENERIC HELPERS
# ============================================================

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

            value = value.reshape(-1)[0]

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


def now_iso() -> str:

    return (
        datetime
        .now()
        .astimezone()
        .isoformat()
    )


def normalize_symbol(
    symbol: str,
) -> str:

    symbol = (
        str(symbol)
        .strip()
        .upper()
    )

    aliases = {
        "NIFTY50":
            "NIFTY",

        "NIFTY 50":
            "NIFTY",

        "NIFTY_50":
            "NIFTY",

        "BANK NIFTY":
            "BANKNIFTY",

        "BANK_NIFTY":
            "BANKNIFTY",

        "BANK-NIFTY":
            "BANKNIFTY",
    }

    return aliases.get(
        symbol,
        symbol,
    )


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
# SESSION CREATION
# ============================================================

def create_nse_session():

    """
    Prefer curl_cffi Chrome impersonation because NSE/Akamai
    can reject plain Python requests based on TLS fingerprint.

    Falls back to requests if curl_cffi is unavailable.
    """

    if CURL_CFFI_AVAILABLE:

        session = curl_requests.Session(
            impersonate="chrome"
        )

        session.headers.update(
            HEADERS
        )

        return session

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    return session


# ============================================================
# SESSION WARMUP
# ============================================================

def warm_nse_session(
    session,
) -> None:

    """
    Warm the NSE session using the real option-chain page.

    This establishes cookies before API calls.
    """

    response = session.get(
        NSE_OPTION_CHAIN_PAGE,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        headers={
            **HEADERS,
            "Referer":
                NSE_HOME_URL,
        },
    )

    if response.status_code >= 400:

        raise RuntimeError(
            f"NSE warmup HTTP "
            f"{response.status_code}"
        )


# ============================================================
# RESPONSE DECOMPRESSION
# ============================================================

def decompress_response(
    response,
) -> bytes:

    """
    Defensive decompression for the requests fallback.

    curl_cffi generally handles browser compression correctly.

    requests may receive:
        gzip
        deflate
        br

    automatically or as raw bytes depending on environment.
    """

    raw = response.content

    encoding = clean_text(
        response.headers.get(
            "Content-Encoding"
        )
    ).lower()

    # Requests/curl_cffi has already decoded it.
    if not encoding:
        return raw

    try:

        if "gzip" in encoding:

            return gzip.decompress(
                raw
            )

        if "deflate" in encoding:

            try:

                return zlib.decompress(
                    raw
                )

            except zlib.error:

                return zlib.decompress(
                    raw,
                    -zlib.MAX_WBITS,
                )

        if "br" in encoding:

            try:

                import brotli

            except ImportError as exc:

                raise RuntimeError(
                    "NSE returned Brotli-compressed "
                    "data but brotli is not installed. "
                    "Run: "
                    "python -m pip install brotli"
                ) from exc

            return brotli.decompress(
                raw
            )

    except Exception:

        # Return raw data so the JSON parser below
        # can provide the final diagnostic.
        return raw

    return raw


# ============================================================
# NSE JSON REQUEST
# ============================================================

def fetch_nse_json(
    session,
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:

    response = session.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        headers={
            **HEADERS,
            "Referer":
                NSE_OPTION_CHAIN_PAGE,
        },
    )

    if response.status_code != 200:

        body = ""

        try:

            body = response.text[:500]

        except Exception:

            pass

        raise RuntimeError(
            f"NSE HTTP "
            f"{response.status_code} "
            f"for {response.url}\n"
            f"Response: {body}"
        )

    # --------------------------------------------------------
    # First try native JSON handling.
    # --------------------------------------------------------

    try:

        payload = response.json()

        if isinstance(
            payload,
            dict,
        ):

            return payload

    except Exception:

        pass

    # --------------------------------------------------------
    # Defensive raw-byte decoding.
    # --------------------------------------------------------

    raw = decompress_response(
        response
    )

    # UTF-8
    try:

        text = raw.decode(
            "utf-8"
        )

        payload = json.loads(
            text
        )

        if isinstance(
            payload,
            dict,
        ):

            return payload

    except Exception:

        pass

    # UTF-8 with BOM
    try:

        text = raw.decode(
            "utf-8-sig"
        )

        payload = json.loads(
            text
        )

        if isinstance(
            payload,
            dict,
        ):

            return payload

    except Exception:

        pass

    content_type = clean_text(
        response.headers.get(
            "Content-Type"
        )
    )

    content_encoding = clean_text(
        response.headers.get(
            "Content-Encoding"
        )
    )

    sample = raw[:120]

    raise RuntimeError(
        "NSE returned a response that could "
        "not be decoded as JSON.\n"
        f"Content-Type: {content_type}\n"
        f"Content-Encoding: {content_encoding}\n"
        f"First bytes: {sample!r}"
    )


# ============================================================
# EXPIRY DATE
# ============================================================

def parse_expiry_date(
    value: str,
) -> datetime | None:

    value = clean_text(
        value
    )

    if not value:
        return None

    formats = [
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%Y-%m-%d",
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                value,
                fmt,
            )

        except ValueError:

            continue

    return None


def extract_expiry_dates(
    payload: dict[str, Any],
) -> list[str]:

    direct = payload.get(
        "expiryDates"
    )

    if isinstance(
        direct,
        list,
    ):

        return [
            clean_text(item)
            for item in direct
            if clean_text(item)
        ]

    records = payload.get(
        "records",
        {}
    )

    if isinstance(
        records,
        dict,
    ):

        nested = records.get(
            "expiryDates"
        )

        if isinstance(
            nested,
            list,
        ):

            return [
                clean_text(item)
                for item in nested
                if clean_text(item)
            ]

    return []


def select_expiry(
    expiry_dates: list[str],
    requested_expiry: str | None = None,
) -> str:

    if not expiry_dates:

        raise RuntimeError(
            "No NSE expiry dates available."
        )

    if requested_expiry:

        requested = clean_text(
            requested_expiry
        )

        for expiry in expiry_dates:

            if (
                expiry.upper()
                == requested.upper()
            ):

                return expiry

        raise ValueError(
            f"Requested expiry "
            f"'{requested_expiry}' "
            f"was not returned by NSE."
        )

    today = datetime.now().date()

    future = []

    for expiry in expiry_dates:

        parsed = parse_expiry_date(
            expiry
        )

        if parsed is None:
            continue

        if parsed.date() >= today:

            future.append(
                (
                    parsed,
                    expiry,
                )
            )

    if future:

        future.sort(
            key=lambda x: x[0]
        )

        return future[0][1]

    return expiry_dates[0]


# ============================================================
# OPTION CHAIN FETCH
# ============================================================

def fetch_option_chain_json(
    symbol: str,
    requested_expiry: str | None = None,
) -> tuple[
    dict[str, Any],
    str,
]:

    symbol = normalize_symbol(
        symbol
    )

    if symbol not in SUPPORTED_SYMBOLS:

        raise ValueError(
            f"Unsupported instrument: "
            f"{symbol}"
        )

    last_error: Exception | None = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        session = create_nse_session()

        try:

            client_name = (
                "curl_cffi / Chrome"
                if CURL_CFFI_AVAILABLE
                else "requests"
            )

            print(
                f"HTTP client: {client_name}"
            )

            print(
                f"Connecting to NSE "
                f"(attempt "
                f"{attempt}/{MAX_RETRIES})..."
            )

            # ------------------------------------------------
            # Warmup
            # ------------------------------------------------

            warm_nse_session(
                session
            )

            time.sleep(
                REQUEST_DELAY
            )

            # ------------------------------------------------
            # Contract info
            # ------------------------------------------------

            print(
                "Fetching NSE contract information..."
            )

            contract_info = fetch_nse_json(
                session,
                NSE_CONTRACT_INFO_URL,
                params={
                    "symbol":
                        symbol,
                },
            )

            expiry_dates = (
                extract_expiry_dates(
                    contract_info
                )
            )

            if not expiry_dates:

                raise RuntimeError(
                    f"NSE returned no expiry dates "
                    f"for {symbol}."
                )

            selected_expiry = select_expiry(
                expiry_dates,
                requested_expiry,
            )

            print(
                f"Selected expiry: "
                f"{selected_expiry}"
            )

            time.sleep(
                REQUEST_DELAY
            )

            # ------------------------------------------------
            # Current v3 option chain
            # ------------------------------------------------

            print(
                "Fetching NSE v3 option chain..."
            )

            payload = fetch_nse_json(
                session,
                NSE_OPTION_CHAIN_V3_URL,
                params={
                    "type":
                        "Indices",

                    "symbol":
                        symbol,

                    "expiry":
                        selected_expiry,
                },
            )

            records = payload.get(
                "records"
            )

            if not isinstance(
                records,
                dict,
            ):

                raise RuntimeError(
                    "NSE v3 option chain "
                    "returned no records."
                )

            rows = records.get(
                "data"
            )

            if not isinstance(
                rows,
                list,
            ) or not rows:

                raise RuntimeError(
                    "NSE v3 option chain "
                    "returned no option rows."
                )

            print(
                f"Raw option rows: "
                f"{len(rows):,}"
            )

            return (
                payload,
                selected_expiry,
            )

        except Exception as exc:

            last_error = exc

            print(
                f"[Attempt "
                f"{attempt}/{MAX_RETRIES}] "
                f"{exc}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    REQUEST_DELAY * attempt
                )

    raise RuntimeError(
        "Unable to fetch NSE option-chain "
        f"for {symbol}: {last_error}"
    )


# ============================================================
# UNDERLYING
# ============================================================

def get_underlying_value(
    payload: dict[str, Any],
) -> float | None:

    records = payload.get(
        "records",
        {}
    )

    value = safe_float(
        records.get(
            "underlyingValue"
        )
    )

    if value is not None:
        return value

    filtered = payload.get(
        "filtered",
        {}
    )

    return safe_float(
        filtered.get(
            "underlyingValue"
        )
    )


# ============================================================
# NORMALIZE OPTION CHAIN
# ============================================================

def extract_option_rows(
    payload: dict[str, Any],
    expiry: str,
) -> pd.DataFrame:

    records = payload.get(
        "records",
        {}
    )

    rows = records.get(
        "data",
        []
    )

    normalized = []

    for row in rows:

        if not isinstance(
            row,
            dict,
        ):
            continue

        row_expiry = clean_text(
            row.get(
                "expiryDate"
            )
        )

        if (
            row_expiry
            and row_expiry != expiry
        ):

            continue

        strike = safe_float(
            row.get(
                "strikePrice"
            )
        )

        if strike is None:
            continue

        ce = row.get(
            "CE"
        ) or {}

        pe = row.get(
            "PE"
        ) or {}

        normalized.append(
            {

                "strike":
                    strike,

                # ------------------------------
                # CALL
                # ------------------------------

                "call_oi":
                    safe_float(
                        ce.get(
                            "openInterest"
                        ),
                        0.0,
                    ),

                "call_change_oi":
                    safe_float(
                        ce.get(
                            "changeinOpenInterest"
                        ),
                        0.0,
                    ),

                "call_volume":
                    safe_float(
                        ce.get(
                            "totalTradedVolume"
                        ),
                        0.0,
                    ),

                "call_iv":
                    safe_float(
                        ce.get(
                            "impliedVolatility"
                        )
                    ),

                "call_ltp":
                    safe_float(
                        ce.get(
                            "lastPrice"
                        )
                    ),

                "call_change":
                    safe_float(
                        ce.get(
                            "change"
                        )
                    ),

                "call_bid_qty":
                    safe_float(
                        ce.get(
                            "bidQty"
                        ),
                        0.0,
                    ),

                "call_bid":
                    safe_float(
                        ce.get(
                            "bidprice"
                        )
                    ),

                "call_ask":
                    safe_float(
                        ce.get(
                            "askPrice"
                        )
                    ),

                "call_ask_qty":
                    safe_float(
                        ce.get(
                            "askQty"
                        ),
                        0.0,
                    ),

                # ------------------------------
                # PUT
                # ------------------------------

                "put_oi":
                    safe_float(
                        pe.get(
                            "openInterest"
                        ),
                        0.0,
                    ),

                "put_change_oi":
                    safe_float(
                        pe.get(
                            "changeinOpenInterest"
                        ),
                        0.0,
                    ),

                "put_volume":
                    safe_float(
                        pe.get(
                            "totalTradedVolume"
                        ),
                        0.0,
                    ),

                "put_iv":
                    safe_float(
                        pe.get(
                            "impliedVolatility"
                        )
                    ),

                "put_ltp":
                    safe_float(
                        pe.get(
                            "lastPrice"
                        )
                    ),

                "put_change":
                    safe_float(
                        pe.get(
                            "change"
                        )
                    ),

                "put_bid_qty":
                    safe_float(
                        pe.get(
                            "bidQty"
                        ),
                        0.0,
                    ),

                "put_bid":
                    safe_float(
                        pe.get(
                            "bidprice"
                        )
                    ),

                "put_ask":
                    safe_float(
                        pe.get(
                            "askPrice"
                        )
                    ),

                "put_ask_qty":
                    safe_float(
                        pe.get(
                            "askQty"
                        ),
                        0.0,
                    ),
            }
        )

    dataframe = pd.DataFrame(
        normalized
    )

    if dataframe.empty:

        raise RuntimeError(
            "No usable option rows after normalization."
        )

    numeric_columns = [
        column
        for column in dataframe.columns
        if column != "strike"
    ]

    for column in numeric_columns:

        dataframe[column] = (
            pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )
            .fillna(0.0)
        )

    dataframe["strike"] = pd.to_numeric(
        dataframe["strike"],
        errors="coerce",
    )

    dataframe = (
        dataframe
        .dropna(
            subset=[
                "strike"
            ]
        )
        .sort_values(
            "strike"
        )
        .reset_index(
            drop=True
        )
    )

    return dataframe


# ============================================================
# ATM
# ============================================================

def get_atm_strike(
    dataframe: pd.DataFrame,
    spot: float,
) -> float:

    distances = (
        dataframe["strike"]
        - spot
    ).abs()

    index = distances.idxmin()

    value = safe_float(
        dataframe.loc[
            index,
            "strike",
        ]
    )

    if value is None:

        raise RuntimeError(
            "Unable to determine ATM strike."
        )

    return value


def filter_strike_window(
    dataframe: pd.DataFrame,
    atm: float,
    window: int,
) -> pd.DataFrame:

    working = dataframe.copy()

    working["_distance"] = (
        (
            working["strike"]
            - atm
        )
        .abs()
    )

    return (
        working
        .sort_values(
            "_distance"
        )
        .head(
            window * 2 + 1
        )
        .sort_values(
            "strike"
        )
        .drop(
            columns=[
                "_distance"
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# PCR
# ============================================================

def calculate_pcr(
    dataframe: pd.DataFrame,
) -> dict[str, Any]:

    call_oi = safe_float(
        dataframe[
            "call_oi"
        ].sum(),
        0.0,
    )

    put_oi = safe_float(
        dataframe[
            "put_oi"
        ].sum(),
        0.0,
    )

    call_volume = safe_float(
        dataframe[
            "call_volume"
        ].sum(),
        0.0,
    )

    put_volume = safe_float(
        dataframe[
            "put_volume"
        ].sum(),
        0.0,
    )

    oi_pcr = (
        put_oi / call_oi
        if call_oi
        and call_oi > 0
        else None
    )

    volume_pcr = (
        put_volume / call_volume
        if call_volume
        and call_volume > 0
        else None
    )

    return {

        "call_oi":
            call_oi,

        "put_oi":
            put_oi,

        "oi_pcr":
            safe_float(
                oi_pcr
            ),

        "call_volume":
            call_volume,

        "put_volume":
            put_volume,

        "volume_pcr":
            safe_float(
                volume_pcr
            ),
    }


# ============================================================
# MAX PAIN
# ============================================================

def calculate_max_pain(
    dataframe: pd.DataFrame,
) -> tuple[
    float | None,
    pd.DataFrame,
]:

    strikes = (
        pd.to_numeric(
            dataframe[
                "strike"
            ],
            errors="coerce",
        )
        .dropna()
        .unique()
    )

    if len(strikes) == 0:

        return (
            None,
            pd.DataFrame(),
        )

    results = []

    for settlement in strikes:

        call_pain = (
            np.maximum(
                settlement
                - dataframe["strike"],
                0,
            )
            * dataframe["call_oi"]
        ).sum()

        put_pain = (
            np.maximum(
                dataframe["strike"]
                - settlement,
                0,
            )
            * dataframe["put_oi"]
        ).sum()

        total = (
            call_pain
            + put_pain
        )

        results.append(
            {
                "strike":
                    float(
                        settlement
                    ),

                "call_pain":
                    safe_float(
                        call_pain
                    ),

                "put_pain":
                    safe_float(
                        put_pain
                    ),

                "total_pain":
                    safe_float(
                        total
                    ),
            }
        )

    curve = (
        pd.DataFrame(
            results
        )
        .sort_values(
            "strike"
        )
        .reset_index(
            drop=True
        )
    )

    if curve.empty:
        return None, curve

    index = (
        curve[
            "total_pain"
        ]
        .idxmin()
    )

    max_pain = safe_float(
        curve.loc[
            index,
            "strike",
        ]
    )

    return (
        max_pain,
        curve,
    )


# ============================================================
# OI WALLS
# ============================================================

def find_oi_walls(
    dataframe: pd.DataFrame,
    spot: float,
) -> dict[str, Any]:

    calls_above = dataframe[
        dataframe["strike"]
        >= spot
    ]

    puts_below = dataframe[
        dataframe["strike"]
        <= spot
    ]

    call_wall = None

    if not calls_above.empty:

        index = (
            calls_above[
                "call_oi"
            ]
            .idxmax()
        )

        row = calls_above.loc[
            index
        ]

        call_wall = {
            "strike":
                safe_float(
                    row[
                        "strike"
                    ]
                ),

            "oi":
                safe_float(
                    row[
                        "call_oi"
                    ]
                ),

            "change_oi":
                safe_float(
                    row[
                        "call_change_oi"
                    ]
                ),
        }

    put_wall = None

    if not puts_below.empty:

        index = (
            puts_below[
                "put_oi"
            ]
            .idxmax()
        )

        row = puts_below.loc[
            index
        ]

        put_wall = {
            "strike":
                safe_float(
                    row[
                        "strike"
                    ]
                ),

            "oi":
                safe_float(
                    row[
                        "put_oi"
                    ]
                ),

            "change_oi":
                safe_float(
                    row[
                        "put_change_oi"
                    ]
                ),
        }

    return {
        "call_wall":
            call_wall,

        "put_wall":
            put_wall,
    }


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def derive_support_resistance(
    dataframe: pd.DataFrame,
    spot: float,
) -> dict[str, Any]:

    puts = dataframe[
        dataframe["strike"]
        <= spot
    ]

    calls = dataframe[
        dataframe["strike"]
        >= spot
    ]

    support = None

    if not puts.empty:

        index = (
            puts[
                "put_oi"
            ]
            .idxmax()
        )

        row = puts.loc[
            index
        ]

        support = {
            "strike":
                safe_float(
                    row[
                        "strike"
                    ]
                ),

            "oi":
                safe_float(
                    row[
                        "put_oi"
                    ]
                ),

            "change_oi":
                safe_float(
                    row[
                        "put_change_oi"
                    ]
                ),
        }

    resistance = None

    if not calls.empty:

        index = (
            calls[
                "call_oi"
            ]
            .idxmax()
        )

        row = calls.loc[
            index
        ]

        resistance = {
            "strike":
                safe_float(
                    row[
                        "strike"
                    ]
                ),

            "oi":
                safe_float(
                    row[
                        "call_oi"
                    ]
                ),

            "change_oi":
                safe_float(
                    row[
                        "call_change_oi"
                    ]
                ),
        }

    return {
        "support":
            support,

        "resistance":
            resistance,
    }


# ============================================================
# IV STRUCTURE
# ============================================================

def calculate_iv_structure(
    dataframe: pd.DataFrame,
    atm: float,
) -> dict[str, Any]:

    distances = (
        dataframe["strike"]
        - atm
    ).abs()

    index = distances.idxmin()

    row = dataframe.loc[
        index
    ]

    call_iv = safe_float(
        row[
            "call_iv"
        ]
    )

    put_iv = safe_float(
        row[
            "put_iv"
        ]
    )

    values = [
        value
        for value in (
            call_iv,
            put_iv,
        )
        if value is not None
    ]

    atm_iv = (
        sum(values)
        / len(values)
        if values
        else None
    )

    skew = None

    if (
        call_iv is not None
        and put_iv is not None
    ):

        skew = (
            put_iv
            - call_iv
        )

    return {

        "atm_call_iv":
            call_iv,

        "atm_put_iv":
            put_iv,

        "atm_iv":
            safe_float(
                atm_iv
            ),

        "put_minus_call_iv_skew":
            safe_float(
                skew
            ),
    }


# ============================================================
# ACTIVITY CLASSIFICATION
# ============================================================

def classify_oi_activity(
    change_oi: float | None,
) -> str:

    value = safe_float(
        change_oi
    )

    if value is None:
        return "UNKNOWN"

    if value > 0:
        return "OI BUILDUP"

    if value < 0:
        return "OI UNWINDING"

    return "OI FLAT"


def classify_premium(
    change: float | None,
) -> str:

    value = safe_float(
        change
    )

    if value is None:
        return "UNKNOWN"

    if value > 0:
        return "PREMIUM STRENGTHENING"

    if value < 0:
        return "PREMIUM WEAKENING"

    return "PREMIUM FLAT"


def build_activity_table(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for _, row in dataframe.iterrows():

        strike = safe_float(
            row[
                "strike"
            ]
        )

        # CALL
        call_oi = safe_float(
            row[
                "call_oi"
            ],
            0.0,
        )

        call_change_oi = safe_float(
            row[
                "call_change_oi"
            ],
            0.0,
        )

        call_volume = safe_float(
            row[
                "call_volume"
            ],
            0.0,
        )

        call_change = safe_float(
            row[
                "call_change"
            ]
        )

        call_ratio = (
            call_volume
            / call_oi
            if call_oi
            and call_oi > 0
            else None
        )

        rows.append(
            {
                "option_type":
                    "CALL",

                "strike":
                    strike,

                "oi":
                    call_oi,

                "change_oi":
                    call_change_oi,

                "volume":
                    call_volume,

                "volume_oi_ratio":
                    call_ratio,

                "premium_change":
                    call_change,

                "oi_activity":
                    classify_oi_activity(
                        call_change_oi
                    ),

                "premium_state":
                    classify_premium(
                        call_change
                    ),
            }
        )

        # PUT
        put_oi = safe_float(
            row[
                "put_oi"
            ],
            0.0,
        )

        put_change_oi = safe_float(
            row[
                "put_change_oi"
            ],
            0.0,
        )

        put_volume = safe_float(
            row[
                "put_volume"
            ],
            0.0,
        )

        put_change = safe_float(
            row[
                "put_change"
            ]
        )

        put_ratio = (
            put_volume
            / put_oi
            if put_oi
            and put_oi > 0
            else None
        )

        rows.append(
            {
                "option_type":
                    "PUT",

                "strike":
                    strike,

                "oi":
                    put_oi,

                "change_oi":
                    put_change_oi,

                "volume":
                    put_volume,

                "volume_oi_ratio":
                    put_ratio,

                "premium_change":
                    put_change,

                "oi_activity":
                    classify_oi_activity(
                        put_change_oi
                    ),

                "premium_state":
                    classify_premium(
                        put_change
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# UNUSUAL ACTIVITY
# ============================================================

def find_unusual_activity(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:

    if dataframe.empty:
        return []

    result = dataframe.copy()

    result[
        "unusual_score"
    ] = 0

    volume_ratio = pd.to_numeric(
        result[
            "volume_oi_ratio"
        ],
        errors="coerce",
    )

    oi = pd.to_numeric(
        result[
            "oi"
        ],
        errors="coerce",
    )

    change_oi = pd.to_numeric(
        result[
            "change_oi"
        ],
        errors="coerce",
    )

    volume_mask = (
        volume_ratio
        >= UNUSUAL_VOLUME_OI_RATIO
    )

    result.loc[
        volume_mask,
        "unusual_score",
    ] += 1

    oi_safe = oi.replace(
        0,
        np.nan,
    )

    change_ratio = (
        change_oi.abs()
        / oi_safe
    )

    oi_mask = (
        change_ratio
        >= UNUSUAL_OI_CHANGE_RATIO
    )

    result.loc[
        oi_mask,
        "unusual_score",
    ] += 1

    result = result[
        result[
            "unusual_score"
        ]
        > 0
    ]

    if result.empty:
        return []

    result = (
        result
        .sort_values(
            [
                "unusual_score",
                "volume",
            ],
            ascending=False,
        )
        .head(
            TOP_ACTIVITY_COUNT
        )
    )

    rows = []

    for _, row in result.iterrows():

        rows.append(
            {
                "option_type":
                    clean_text(
                        row[
                            "option_type"
                        ]
                    ),

                "strike":
                    safe_float(
                        row[
                            "strike"
                        ]
                    ),

                "oi":
                    safe_float(
                        row[
                            "oi"
                        ]
                    ),

                "change_oi":
                    safe_float(
                        row[
                            "change_oi"
                        ]
                    ),

                "volume":
                    safe_float(
                        row[
                            "volume"
                        ]
                    ),

                "volume_oi_ratio":
                    safe_float(
                        row[
                            "volume_oi_ratio"
                        ]
                    ),

                "premium_change":
                    safe_float(
                        row[
                            "premium_change"
                        ]
                    ),

                "oi_activity":
                    clean_text(
                        row[
                            "oi_activity"
                        ]
                    ),

                "premium_state":
                    clean_text(
                        row[
                            "premium_state"
                        ]
                    ),

                "unusual_score":
                    safe_int(
                        row[
                            "unusual_score"
                        ]
                    ),
            }
        )

    return rows


# ============================================================
# TOP OI
# ============================================================

def top_oi_levels(
    dataframe: pd.DataFrame,
    count: int = TOP_OI_COUNT,
) -> dict[str, Any]:

    call_top = (
        dataframe[
            [
                "strike",
                "call_oi",
                "call_change_oi",
            ]
        ]
        .sort_values(
            "call_oi",
            ascending=False,
        )
        .head(
            count
        )
    )

    put_top = (
        dataframe[
            [
                "strike",
                "put_oi",
                "put_change_oi",
            ]
        ]
        .sort_values(
            "put_oi",
            ascending=False,
        )
        .head(
            count
        )
    )

    calls = []

    for _, row in call_top.iterrows():

        calls.append(
            {
                "strike":
                    safe_float(
                        row[
                            "strike"
                        ]
                    ),

                "oi":
                    safe_float(
                        row[
                            "call_oi"
                        ]
                    ),

                "change_oi":
                    safe_float(
                        row[
                            "call_change_oi"
                        ]
                    ),
            }
        )

    puts = []

    for _, row in put_top.iterrows():

        puts.append(
            {
                "strike":
                    safe_float(
                        row[
                            "strike"
                        ]
                    ),

                "oi":
                    safe_float(
                        row[
                            "put_oi"
                        ]
                    ),

                "change_oi":
                    safe_float(
                        row[
                            "put_change_oi"
                        ]
                    ),
            }
        )

    return {
        "top_call_oi":
            calls,

        "top_put_oi":
            puts,
    }


# ============================================================
# POSITIONING INTERPRETATION
# ============================================================

def derive_positioning_interpretation(
    spot: float,
    pcr: dict[str, Any],
    walls: dict[str, Any],
    max_pain: float | None,
) -> dict[str, Any]:

    oi_pcr = safe_float(
        pcr.get(
            "oi_pcr"
        )
    )

    observations = []

    if oi_pcr is not None:

        if oi_pcr >= 1.20:

            observations.append(
                "PUT OI dominates CALL OI."
            )

        elif oi_pcr <= 0.80:

            observations.append(
                "CALL OI dominates PUT OI."
            )

        else:

            observations.append(
                "CALL and PUT OI are relatively balanced."
            )

    put_wall = walls.get(
        "put_wall"
    )

    if put_wall:

        strike = safe_float(
            put_wall.get(
                "strike"
            )
        )

        if strike is not None:

            observations.append(
                "Largest put-OI concentration "
                f"is around {strike:.0f}."
            )

    call_wall = walls.get(
        "call_wall"
    )

    if call_wall:

        strike = safe_float(
            call_wall.get(
                "strike"
            )
        )

        if strike is not None:

            observations.append(
                "Largest call-OI concentration "
                f"is around {strike:.0f}."
            )

    max_pain_distance = None

    if (
        max_pain is not None
        and spot > 0
    ):

        max_pain_distance = (
            (
                max_pain
                - spot
            )
            / spot
        ) * 100

        observations.append(
            "Max-pain reference is "
            f"{max_pain_distance:+.2f}% "
            "from spot."
        )

    if (
        oi_pcr is not None
        and oi_pcr >= 1.20
    ):

        classification = (
            "PUT-OI-DOMINANT"
        )

    elif (
        oi_pcr is not None
        and oi_pcr <= 0.80
    ):

        classification = (
            "CALL-OI-DOMINANT"
        )

    else:

        classification = (
            "BALANCED / MIXED"
        )

    return {

        "classification":
            classification,

        "observations":
            observations,

        "max_pain_distance_percent":
            safe_float(
                max_pain_distance
            ),

        "warning":
            (
                "Options positioning is evidence "
                "for analysis, not an automatic "
                "directional trading signal."
            ),
    }


# ============================================================
# FULL ANALYSIS
# ============================================================

def analyze_derivatives(
    symbol: str = "NIFTY",
    expiry: str | None = None,
    strike_window: int = STRIKE_WINDOW,
) -> dict[str, Any]:

    symbol = normalize_symbol(
        symbol
    )

    if symbol not in SUPPORTED_SYMBOLS:

        raise ValueError(
            f"Unsupported instrument: {symbol}"
        )

    if strike_window < 1:

        raise ValueError(
            "Strike window must be >= 1."
        )

    print()
    print("=" * 70)
    print("NOVA DERIVATIVES INTELLIGENCE")
    print("=" * 70)
    print()

    print(
        f"Instrument: {symbol}"
    )

    print(
        "Fetching NSE option-chain data..."
    )

    payload, selected_expiry = (
        fetch_option_chain_json(
            symbol,
            requested_expiry=expiry,
        )
    )

    # --------------------------------------------------------
    # SPOT
    # --------------------------------------------------------

    spot = get_underlying_value(
        payload
    )

    if spot is None:

        raise RuntimeError(
            "NSE did not return the "
            "underlying value."
        )

    print(
        f"Underlying spot: "
        f"{spot:.2f}"
    )

    # --------------------------------------------------------
    # RAW CHAIN
    # --------------------------------------------------------

    option_data = extract_option_rows(
        payload,
        selected_expiry,
    )

    print(
        f"Normalized option rows: "
        f"{len(option_data):,}"
    )

    # --------------------------------------------------------
    # ATM
    # --------------------------------------------------------

    atm = get_atm_strike(
        option_data,
        spot,
    )

    analysis_data = (
        filter_strike_window(
            option_data,
            atm,
            strike_window,
        )
    )

    # --------------------------------------------------------
    # DERIVATIVES METRICS
    # --------------------------------------------------------

    pcr = calculate_pcr(
        analysis_data
    )

    max_pain, pain_curve = (
        calculate_max_pain(
            option_data
        )
    )

    walls = find_oi_walls(
        option_data,
        spot,
    )

    support_resistance = (
        derive_support_resistance(
            option_data,
            spot,
        )
    )

    iv_structure = (
        calculate_iv_structure(
            analysis_data,
            atm,
        )
    )

    activity_table = (
        build_activity_table(
            analysis_data
        )
    )

    unusual_activity = (
        find_unusual_activity(
            activity_table
        )
    )

    positioning = (
        derive_positioning_interpretation(
            spot,
            pcr,
            walls,
            max_pain,
        )
    )

    oi_levels = top_oi_levels(
        option_data
    )

    records = payload.get(
        "records",
        {}
    )

    expiry_dates = (
        records.get(
            "expiryDates",
            []
        )
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    report = {

        "system":
            "NOVA DERIVATIVES INTELLIGENCE",

        "timestamp":
            now_iso(),

        "source":
            "NSE Option Chain v3",

        "instrument":
            symbol,

        "underlying":
            {
                "spot":
                    spot,
            },

        "expiry":
            {
                "selected":
                    selected_expiry,

                "available":
                    expiry_dates,
            },

        "atm":
            {
                "strike":
                    atm,
            },

        "option_chain":
            {
                "full_rows":
                    int(
                        len(
                            option_data
                        )
                    ),

                "analysis_rows":
                    int(
                        len(
                            analysis_data
                        )
                    ),

                "strike_window":
                    strike_window,
            },

        "pcr":
            pcr,

        "max_pain":
            {
                "strike":
                    max_pain,
            },

        "oi_walls":
            walls,

        "support_resistance":
            support_resistance,

        "iv_structure":
            iv_structure,

        "top_oi_levels":
            oi_levels,

        "unusual_activity":
            unusual_activity,

        "positioning_interpretation":
            positioning,

        "policy":
            {
                "analysis_only":
                    True,

                "buy_sell_authorized":
                    False,

                "broker_connection":
                    False,

                "trade_execution":
                    False,

                "automatic_orders":
                    False,
            },
    }

    # --------------------------------------------------------
    # TERMINAL OUTPUT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("DERIVATIVES SUMMARY")
    print("=" * 70)

    print(
        f"Spot: "
        f"{format_number(spot)}"
    )

    print(
        f"Expiry: "
        f"{selected_expiry}"
    )

    print(
        f"ATM: "
        f"{format_strike(atm)}"
    )

    print()

    print(
        f"OI PCR: "
        f"{format_number(
            pcr.get(
                'oi_pcr'
            )
        )}"
    )

    print(
        f"Volume PCR: "
        f"{format_number(
            pcr.get(
                'volume_pcr'
            )
        )}"
    )

    print(
        f"Max Pain: "
        f"{format_strike(
            max_pain
        )}"
    )

    print()

    put_wall = walls.get(
        "put_wall"
    )

    call_wall = walls.get(
        "call_wall"
    )

    print(
        f"Put Wall: "
        f"{format_strike(
            put_wall.get('strike')
            if put_wall
            else None
        )}"
    )

    print(
        f"Call Wall: "
        f"{format_strike(
            call_wall.get('strike')
            if call_wall
            else None
        )}"
    )

    support = (
        support_resistance
        .get(
            "support"
        )
    )

    resistance = (
        support_resistance
        .get(
            "resistance"
        )
    )

    print(
        f"Support: "
        f"{format_strike(
            support.get('strike')
            if support
            else None
        )}"
    )

    print(
        f"Resistance: "
        f"{format_strike(
            resistance.get('strike')
            if resistance
            else None
        )}"
    )

    print()

    print(
        f"ATM Call IV: "
        f"{format_number(
            iv_structure.get(
                'atm_call_iv'
            )
        )}"
    )

    print(
        f"ATM Put IV: "
        f"{format_number(
            iv_structure.get(
                'atm_put_iv'
            )
        )}"
    )

    print(
        f"ATM IV: "
        f"{format_number(
            iv_structure.get(
                'atm_iv'
            )
        )}"
    )

    print(
        f"Put-Call IV Skew: "
        f"{format_number(
            iv_structure.get(
                'put_minus_call_iv_skew'
            )
        )}"
    )

    print()
    print(
        "POSITIONING INTERPRETATION"
    )
    print("-" * 70)

    print(
        f"Classification: "
        f"{positioning.get(
            'classification',
            'UNKNOWN'
        )}"
    )

    for observation in (
        positioning.get(
            "observations",
            [],
        )
    ):

        print(
            f"  - {observation}"
        )

    print()
    print(
        "TOP UNUSUAL ACTIVITY"
    )
    print("-" * 70)

    if not unusual_activity:

        print(
            "No unusual activity detected "
            "under current thresholds."
        )

    else:

        for item in unusual_activity:

            print(
                f"{item['option_type']} "
                f"{format_strike(
                    item['strike']
                )} "
                f"| OI "
                f"{format_number(
                    item['oi'],
                    0,
                )} "
                f"| ChgOI "
                f"{format_number(
                    item['change_oi'],
                    0,
                )} "
                f"| Vol "
                f"{format_number(
                    item['volume'],
                    0,
                )} "
                f"| "
                f"{item['oi_activity']}"
            )

    print()

    return report


# ============================================================
# SAVE REPORT
# ============================================================

def save_report(
    report: dict[str, Any],
) -> tuple[Path, Path]:

    symbol = normalize_symbol(
        report.get(
            "instrument",
            "UNKNOWN",
        )
    )

    expiry = clean_text(
        report
        .get(
            "expiry",
            {}
        )
        .get(
            "selected",
            "UNKNOWN",
        )
    )

    safe_expiry = (
        expiry
        .replace(
            "-",
            "",
        )
        .replace(
            " ",
            "",
        )
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    # --------------------------------------------------------
    # COMPLETE JSON
    # --------------------------------------------------------

    json_path = (
        CACHE_DIR
        / (
            f"derivatives_"
            f"{symbol}_"
            f"{safe_expiry}_"
            f"{timestamp}.json"
        )
    )

    with json_path.open(
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

    # --------------------------------------------------------
    # LATEST METRICS CSV
    # --------------------------------------------------------

    pcr = report.get(
        "pcr",
        {}
    )

    iv = report.get(
        "iv_structure",
        {}
    )

    walls = report.get(
        "oi_walls",
        {}
    )

    sr = report.get(
        "support_resistance",
        {}
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

    csv_row = {

        "timestamp":
            report.get(
                "timestamp"
            ),

        "instrument":
            symbol,

        "expiry":
            expiry,

        "spot":
            report
            .get(
                "underlying",
                {}
            )
            .get(
                "spot"
            ),

        "atm":
            report
            .get(
                "atm",
                {}
            )
            .get(
                "strike"
            ),

        "oi_pcr":
            pcr.get(
                "oi_pcr"
            ),

        "volume_pcr":
            pcr.get(
                "volume_pcr"
            ),

        "max_pain":
            report
            .get(
                "max_pain",
                {}
            )
            .get(
                "strike"
            ),

        "put_wall":
            put_wall.get(
                "strike"
            ),

        "put_wall_oi":
            put_wall.get(
                "oi"
            ),

        "call_wall":
            call_wall.get(
                "strike"
            ),

        "call_wall_oi":
            call_wall.get(
                "oi"
            ),

        "support":
            support.get(
                "strike"
            ),

        "resistance":
            resistance.get(
                "strike"
            ),

        "atm_call_iv":
            iv.get(
                "atm_call_iv"
            ),

        "atm_put_iv":
            iv.get(
                "atm_put_iv"
            ),

        "atm_iv":
            iv.get(
                "atm_iv"
            ),

        "iv_skew":
            iv.get(
                "put_minus_call_iv_skew"
            ),

        "positioning":
            report
            .get(
                "positioning_interpretation",
                {}
            )
            .get(
                "classification"
            ),
    }

    csv_path = (
        CACHE_DIR
        / (
            f"derivatives_latest_"
            f"{symbol}.csv"
        )
    )

    pd.DataFrame(
        [csv_row]
    ).to_csv(
        csv_path,
        index=False,
    )

    return (
        json_path,
        csv_path,
    )


# ============================================================
# CLI
# ============================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Nova NSE Derivatives Intelligence"
        )
    )

    parser.add_argument(
        "--symbol",
        default="NIFTY",
        choices=[
            "NIFTY",
            "BANKNIFTY",
        ],
        help=(
            "Index to analyze."
        ),
    )

    parser.add_argument(
        "--expiry",
        default=None,
        help=(
            "Exact NSE expiry, e.g. "
            "15-Oct-2026."
        ),
    )

    parser.add_argument(
        "--window",
        type=int,
        default=STRIKE_WINDOW,
        help=(
            "ATM strikes on each side."
        ),
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "Save complete JSON and "
            "latest metrics CSV."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    args = parse_arguments()

    try:

        report = analyze_derivatives(
            symbol=args.symbol,
            expiry=args.expiry,
            strike_window=args.window,
        )

        if args.save:

            json_path, csv_path = (
                save_report(
                    report
                )
            )

            print()
            print(
                "REPORTS SAVED"
            )

            print(
                f"JSON: {json_path}"
            )

            print(
                f"CSV : {csv_path}"
            )

        print()
        print("=" * 70)
        print(
            "NOVA DERIVATIVES TEST COMPLETE"
        )
        print("=" * 70)
        print()

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Derivatives engine stopped."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 70)
        print(
            "NOVA DERIVATIVES ENGINE ERROR"
        )
        print("=" * 70)
        print()

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())