"""
Nova Market Intelligence
Indian Equity Security Master

Source:
    NSE India official securities-available-for-trading CSV.

Purpose:
    Maintain a local searchable universe of NSE securities.

This file does NOT provide prices.
It provides the universe of securities that Nova can scan.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

CACHE_DIR = DATA_DIR / "cache"

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

MASTER_FILE = CACHE_DIR / "nse_equity_master.csv"

META_FILE = CACHE_DIR / "nse_equity_master_meta.json"


# ============================================================
# NSE SOURCE
# ============================================================

NSE_EQUITY_URL = (
    "https://nsearchives.nseindia.com/"
    "content/equities/EQUITY_L.csv"
)


NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/csv,application/csv,"
        "application/octet-stream,*/*"
    ),
    "Referer": (
        "https://www.nseindia.com/"
        "static/market-data/"
        "securities-available-for-trading"
    ),
}


# ============================================================
# DOWNLOAD
# ============================================================

def download_nse_equity_master() -> pd.DataFrame:
    """
    Download the current official NSE Equity security list.
    """

    response = requests.get(
        NSE_EQUITY_URL,
        headers=NSE_HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.content

    if not data:
        raise RuntimeError(
            "NSE returned an empty security master."
        )

    dataframe = pd.read_csv(
        io.BytesIO(data)
    )

    if dataframe.empty:
        raise RuntimeError(
            "NSE security master contains no records."
        )

    return dataframe


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize_columns(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = dataframe.copy()

    dataframe.columns = [
        str(column)
        .strip()
        .upper()
        .replace(" ", "_")
        for column in dataframe.columns
    ]

    return dataframe


def _find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
) -> str | None:

    for candidate in candidates:

        if candidate in dataframe.columns:
            return candidate

    return None


def normalize_master(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = _normalize_columns(dataframe)

    symbol_column = _find_column(
        dataframe,
        [
            "SYMBOL",
            "SYMBOL_NAME",
            "SECURITY_SYMBOL",
        ],
    )

    company_column = _find_column(
        dataframe,
        [
            "NAME_OF_COMPANY",
            "COMPANY_NAME",
            "NAME",
            "SECURITY_NAME",
        ],
    )

    series_column = _find_column(
        dataframe,
        [
            "SERIES",
            "SERIES_CODE",
        ],
    )

    isin_column = _find_column(
        dataframe,
        [
            "ISIN_NUMBER",
            "ISIN",
            "ISIN_CODE",
        ],
    )

    if symbol_column is None:
        raise RuntimeError(
            "Could not identify SYMBOL column "
            "in NSE security master."
        )

    result = pd.DataFrame()

    result["symbol"] = (
        dataframe[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    if company_column:
        result["company_name"] = (
            dataframe[company_column]
            .astype(str)
            .str.strip()
        )
    else:
        result["company_name"] = ""

    if series_column:
        result["series"] = (
            dataframe[series_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    else:
        result["series"] = ""

    if isin_column:
        result["isin"] = (
            dataframe[isin_column]
            .astype(str)
            .str.strip()
            .str.upper()
        )
    else:
        result["isin"] = ""

    result["exchange"] = "NSE"

    result["yahoo_symbol"] = (
        result["symbol"] + ".NS"
    )

    # Remove invalid rows.
    result = result[
        result["symbol"].notna()
    ]

    result = result[
        result["symbol"] != ""
    ]

    result = result[
        result["symbol"] != "NAN"
    ]

    # Keep unique symbol + series combinations.
    result = result.drop_duplicates(
        subset=["symbol", "series"],
        keep="first",
    )

    result = result.sort_values(
        ["symbol", "series"]
    ).reset_index(drop=True)

    return result


# ============================================================
# SAVE
# ============================================================

def save_master(
    dataframe: pd.DataFrame,
) -> None:

    dataframe.to_csv(
        MASTER_FILE,
        index=False,
        encoding="utf-8",
    )

    metadata = {
        "exchange": "NSE",
        "source": NSE_EQUITY_URL,
        "updated_at": time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "records": int(len(dataframe)),
    }

    META_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# UPDATE MASTER
# ============================================================

def update_master() -> pd.DataFrame:

    print()
    print("=" * 70)
    print("NOVA NSE SECURITY MASTER")
    print("=" * 70)

    print()
    print("Downloading official NSE equity universe...")

    raw = download_nse_equity_master()

    master = normalize_master(raw)

    save_master(master)

    print(
        f"Loaded {len(master):,} "
        "NSE symbol/series records."
    )

    print()
    print(
        f"Saved: {MASTER_FILE}"
    )

    print()
    print("NSE security master updated.")

    return master


# ============================================================
# LOAD LOCAL MASTER
# ============================================================

def load_master(
    auto_update: bool = False,
) -> pd.DataFrame:

    if auto_update or not MASTER_FILE.exists():

        return update_master()

    return pd.read_csv(
        MASTER_FILE,
        dtype=str,
    ).fillna("")


# ============================================================
# SEARCH SYMBOL
# ============================================================

def search_symbols(
    query: str,
    limit: int = 20,
) -> pd.DataFrame:

    query = str(query).strip().upper()

    if not query:
        return pd.DataFrame()

    master = load_master()

    exact = master[
        master["symbol"] == query
    ]

    if not exact.empty:
        return exact.head(limit)

    contains_symbol = master[
        master["symbol"]
        .str.contains(
            query,
            case=False,
            regex=False,
        )
    ]

    contains_company = master[
        master["company_name"]
        .str.contains(
            query,
            case=False,
            regex=False,
        )
    ]

    result = pd.concat(
        [
            contains_symbol,
            contains_company,
        ],
        ignore_index=True,
    )

    result = result.drop_duplicates(
        subset=["symbol", "series"]
    )

    return result.head(limit)


# ============================================================
# LOOKUP EXACT SYMBOL
# ============================================================

def get_security(
    symbol: str,
) -> dict | None:

    symbol = str(symbol).strip().upper()

    master = load_master()

    result = master[
        master["symbol"] == symbol
    ]

    if result.empty:
        return None

    row = result.iloc[0]

    return row.to_dict()


# ============================================================
# UNIVERSE STATISTICS
# ============================================================

def get_universe_stats() -> dict:

    master = load_master()

    symbols = (
        master["symbol"]
        .drop_duplicates()
    )

    series_counts = (
        master["series"]
        .value_counts()
        .to_dict()
    )

    return {
        "exchange": "NSE",
        "records": len(master),
        "unique_symbols": len(symbols),
        "series": series_counts,
        "master_file": str(MASTER_FILE),
    }


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    try:

        master = update_master()

        stats = get_universe_stats()

        print()
        print("UNIVERSE STATISTICS")
        print("-" * 70)
        print(
            f"Records        : "
            f"{stats['records']:,}"
        )
        print(
            f"Unique symbols : "
            f"{stats['unique_symbols']:,}"
        )

        print()
        print("SERIES")
        print("-" * 70)

        for series, count in stats["series"].items():

            print(
                f"{series:<10} {count:,}"
            )

        print()
        print("SAMPLE")
        print("-" * 70)

        print(
            master[
                [
                    "symbol",
                    "company_name",
                    "series",
                    "isin",
                    "yahoo_symbol",
                ]
            ].head(15).to_string(
                index=False
            )
        )

        print()
        print("Security master test completed.")

    except Exception as exc:

        print()
        print("SECURITY MASTER ERROR")
        print(exc)