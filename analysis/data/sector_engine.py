"""
Nova Sector Intelligence Engine
===============================

Sector-level market intelligence for Nova.

Data architecture
-----------------
1. Nova NSE Security Master
2. Nova sector classification engine/cache
3. Nova Market Scanner output

The sector engine is analysis-only:
- no broker connection
- no order placement
- no automatic trading
- no BUY/SELL authorization

Classification provenance is preserved in `classification_source`.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from analysis.data.market_scanner import scan_market
from analysis.data.symbol_master import load_master

# Current API exposed by sector_classification.py
from analysis.data.sector_classification import (
    CLASSIFICATION_FILE,
    RAW_HTML_FILE,
    parse_primary_html,
    normalize_company_name,
    loose_company_name,
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CACHE_DIR = (
    BASE_DIR
    / "cache"
    / "sector"
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

SECTOR_OUTPUT_PREFIX = "sector_scan"
MACRO_OUTPUT_PREFIX = "macro_sector_scan"
ENRICHED_OUTPUT_PREFIX = "sector_enriched_stocks"

UNRESOLVED_FILE = (
    CACHE_DIR
    / "sector_unresolved_stocks.csv"
)

PRIMARY_SOURCE_URL = (
    "https://theannexure.com/companies"
)

REQUEST_TIMEOUT = 30

CLASSIFICATION_COLUMNS = [
    "symbol",
    "company_name",
    "macro_sector",
    "sector",
    "industry",
    "basic_industry",
    "classification_source",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def safe_float(
    value: Any,
) -> float | None:
    try:
        if value is None:
            return None

        if pd.isna(value):
            return None

        result = float(value)

        if not math.isfinite(result):
            return None

        return result

    except (
        TypeError,
        ValueError,
    ):
        return None


def pct_mean(
    series: pd.Series,
) -> float | None:
    numeric = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return None

    return safe_float(
        numeric.mean()
    )


def safe_ratio(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator <= 0:
        return None

    return safe_float(
        numerator / denominator
    )


def own_loose_name(
    value: Any,
) -> str:
    """
    Internal fallback name normalizer.
    Used only if classifier helpers fail.
    """
    text = clean_text(value).upper()

    text = re.sub(
        r"&",
        " AND ",
        text,
    )

    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text,
    )

    stopwords = {
        "LIMITED",
        "LTD",
        "PRIVATE",
        "PVT",
        "INC",
        "PLC",
        "CORPORATION",
        "CORP",
        "COMPANY",
        "CO",
        "LLP",
        "HOLDINGS",
        "HOLDING",
    }

    tokens = [
        token
        for token in text.split()
        if token not in stopwords
    ]

    return "".join(tokens)


def normalized_name(
    value: Any,
) -> str:
    try:
        result = normalize_company_name(
            value
        )

        result = clean_text(
            result
        )

        if result:
            return result.upper()

    except Exception:
        pass

    return own_loose_name(value)


def loose_name(
    value: Any,
) -> str:
    try:
        result = loose_company_name(
            value
        )

        result = clean_text(
            result
        )

        if result:
            return result.upper()

    except Exception:
        pass

    return own_loose_name(value)


def choose_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    lower_map = {
        str(column).strip().lower(): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        found = lower_map.get(
            candidate.lower()
        )

        if found is not None:
            return found

    return None


# ============================================================
# CLASSIFICATION CACHE
# ============================================================

def empty_classification_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=CLASSIFICATION_COLUMNS
    )


def load_classification_cache() -> pd.DataFrame:
    """
    Load canonical classification cache.

    Supports:
    - current `classification_source`
    - legacy `source`
    """

    if not CLASSIFICATION_FILE.exists():
        return empty_classification_frame()

    try:
        dataframe = pd.read_csv(
            CLASSIFICATION_FILE,
            dtype=str,
        )

    except Exception as exc:
        print(
            "WARNING: Could not read "
            f"classification cache: {exc}"
        )

        return empty_classification_frame()

    dataframe = dataframe.fillna("")

    # Legacy compatibility.
    if (
        "classification_source"
        not in dataframe.columns
        and "source"
        in dataframe.columns
    ):
        dataframe[
            "classification_source"
        ] = dataframe["source"]

    if "company_name" not in dataframe.columns:
        dataframe["company_name"] = ""

    for column in CLASSIFICATION_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    dataframe = dataframe[
        CLASSIFICATION_COLUMNS
    ].copy()

    dataframe["symbol"] = (
        dataframe["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    for column in CLASSIFICATION_COLUMNS:
        dataframe[column] = (
            dataframe[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    dataframe = dataframe[
        dataframe["symbol"].ne("")
    ].copy()

    if not dataframe.empty:
        dataframe = (
            dataframe
            .drop_duplicates(
                subset=["symbol"],
                keep="last",
            )
            .sort_values("symbol")
            .reset_index(drop=True)
        )

    return dataframe


def save_classification_cache(
    dataframe: pd.DataFrame,
) -> None:
    """
    Save canonical classification cache.
    """

    dataframe = dataframe.copy()

    if (
        "classification_source"
        not in dataframe.columns
        and "source"
        in dataframe.columns
    ):
        dataframe[
            "classification_source"
        ] = dataframe["source"]

    if "company_name" not in dataframe.columns:
        dataframe["company_name"] = ""

    for column in CLASSIFICATION_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    dataframe = dataframe[
        CLASSIFICATION_COLUMNS
    ].copy()

    dataframe["symbol"] = (
        dataframe["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    for column in CLASSIFICATION_COLUMNS:
        dataframe[column] = (
            dataframe[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    dataframe = (
        dataframe[
            dataframe["symbol"].ne("")
        ]
        .drop_duplicates(
            subset=["symbol"],
            keep="last",
        )
        .sort_values("symbol")
        .reset_index(drop=True)
    )

    dataframe.to_csv(
        CLASSIFICATION_FILE,
        index=False,
        encoding="utf-8",
    )


# ============================================================
# PRIMARY CLASSIFICATION
# ============================================================

def download_primary_html() -> str:
    """
    Download primary classification directory
    only if cached HTML is unavailable.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/154.0.0.0 "
            "Safari/537.36"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml"
        ),
        "Accept-Language": (
            "en-US,en;q=0.9"
        ),
    }

    response = requests.get(
        PRIMARY_SOURCE_URL,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    html = response.text

    if len(html) < 10000:
        raise RuntimeError(
            "Primary classification page "
            "returned unexpectedly little HTML."
        )

    RAW_HTML_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_HTML_FILE.write_text(
        html,
        encoding="utf-8",
    )

    return html


def load_primary_rows() -> pd.DataFrame:
    """
    Parse primary classification HTML
    using sector_classification.py.
    """

    if RAW_HTML_FILE.exists():
        html = RAW_HTML_FILE.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    else:
        html = download_primary_html()

    parsed = parse_primary_html(
        html
    )

    if parsed is None:
        return pd.DataFrame()

    if isinstance(
        parsed,
        pd.DataFrame,
    ):
        dataframe = parsed.copy()

    elif isinstance(
        parsed,
        list,
    ):
        dataframe = pd.DataFrame(
            parsed
        )

    elif isinstance(
        parsed,
        dict,
    ):
        dataframe = pd.DataFrame(
            [parsed]
        )

    else:
        raise RuntimeError(
            "parse_primary_html() returned "
            "unsupported type: "
            f"{type(parsed).__name__}"
        )

    if dataframe.empty:
        return dataframe

    return dataframe.fillna("")


def canonicalize_primary_rows(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize parser output into canonical
    classification columns.
    """

    if dataframe.empty:
        return empty_classification_frame()

    symbol_column = choose_column(
        dataframe,
        [
            "symbol",
            "ticker",
            "yahoo_symbol",
            "scrip",
        ],
    )

    company_column = choose_column(
        dataframe,
        [
            "company_name",
            "name",
            "company",
        ],
    )

    macro_column = choose_column(
        dataframe,
        [
            "macro_sector",
            "macro",
            "macro_sector_name",
        ],
    )

    sector_column = choose_column(
        dataframe,
        [
            "sector",
            "sector_name",
        ],
    )

    industry_column = choose_column(
        dataframe,
        [
            "industry",
            "industry_name",
        ],
    )

    basic_column = choose_column(
        dataframe,
        [
            "basic_industry",
            "basic",
            "basicIndustry",
        ],
    )

    if company_column is None:
        raise RuntimeError(
            "Primary classifier output does not "
            "contain a company-name column."
        )

    result = pd.DataFrame()

    if symbol_column is not None:
        result["symbol"] = (
            dataframe[
                symbol_column
            ].astype(str)
        )
    else:
        result["symbol"] = ""

    result["company_name"] = (
        dataframe[
            company_column
        ].astype(str)
    )

    if macro_column is not None:
        result["macro_sector"] = (
            dataframe[
                macro_column
            ].astype(str)
        )
    else:
        result["macro_sector"] = ""

    if sector_column is not None:
        result["sector"] = (
            dataframe[
                sector_column
            ].astype(str)
        )
    else:
        result["sector"] = ""

    if industry_column is not None:
        result["industry"] = (
            dataframe[
                industry_column
            ].astype(str)
        )
    else:
        result["industry"] = ""

    if basic_column is not None:
        result["basic_industry"] = (
            dataframe[
                basic_column
            ].astype(str)
        )
    else:
        result["basic_industry"] = ""

    result[
        "classification_source"
    ] = (
        "The Annexure primary classification"
    )

    for column in CLASSIFICATION_COLUMNS:
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    result["symbol"] = (
        result["symbol"]
        .str.upper()
        .str.strip()
    )

    return result


def build_master_lookup(
    master: pd.DataFrame,
) -> pd.DataFrame:
    result = master.copy()

    required = [
        "symbol",
        "company_name",
    ]

    for column in required:
        if column not in result.columns:
            raise RuntimeError(
                "NSE security master is missing "
                f"'{column}'."
            )

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["company_name"] = (
        result["company_name"]
        .astype(str)
        .str.strip()
    )

    result[
        "name_normalized"
    ] = (
        result["company_name"]
        .map(normalized_name)
    )

    result[
        "name_loose"
    ] = (
        result["company_name"]
        .map(loose_name)
    )

    result = (
        result[
            result["symbol"].ne("")
            & result["company_name"].ne("")
        ]
        .drop_duplicates(
            subset=["symbol"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return result


# ============================================================
# RECONCILIATION
# ============================================================

def reconcile_missing_classifications(
    scanner_dataframe: pd.DataFrame,
    classification: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Recover scanner symbols missing from the
    canonical classification cache.

    Matching order:
    1. exact symbol
    2. normalized company name
    3. loose company name

    Unmatched symbols are NOT guessed.
    """

    if scanner_dataframe.empty:
        return (
            classification.copy(),
            pd.DataFrame(),
        )

    master = load_master()

    if master.empty:
        raise RuntimeError(
            "NSE security master is empty; "
            "cannot reconcile classifications."
        )

    master_lookup = build_master_lookup(
        master
    )

    scanner_symbols = {
        clean_text(symbol).upper()
        for symbol
        in scanner_dataframe["symbol"].tolist()
    }

    cache_symbols: set[str] = set()

    if (
        not classification.empty
        and "symbol"
        in classification.columns
    ):
        cache_symbols = {
            clean_text(symbol).upper()
            for symbol
            in classification["symbol"].tolist()
            if clean_text(symbol)
        }

    missing_symbols = sorted(
        scanner_symbols - cache_symbols
    )

    if not missing_symbols:
        return (
            classification.copy(),
            pd.DataFrame(),
        )

    print()
    print(
        "CLASSIFICATION RECONCILIATION"
    )
    print("-" * 80)

    print(
        "Scanner symbols missing "
        f"from cache: {len(missing_symbols):,}"
    )

    primary_rows = load_primary_rows()

    if primary_rows.empty:
        print(
            "Primary directory produced "
            "no usable rows."
        )

        unresolved = master_lookup[
            master_lookup["symbol"].isin(
                missing_symbols
            )
        ][
            [
                "symbol",
                "company_name",
            ]
        ].copy()

        unresolved["reason"] = (
            "primary_source_empty"
        )

        return (
            classification.copy(),
            unresolved,
        )

    primary = canonicalize_primary_rows(
        primary_rows
    )

    # --------------------------------------------------------
    # Exact symbol lookup
    # --------------------------------------------------------

    exact_symbol_map: dict[
        str,
        dict[str, Any],
    ] = {}

    for _, row in primary.iterrows():
        symbol = clean_text(
            row["symbol"]
        ).upper()

        if symbol:
            exact_symbol_map[
                symbol
            ] = row.to_dict()

    # --------------------------------------------------------
    # Name lookups
    # --------------------------------------------------------

    primary[
        "name_normalized"
    ] = (
        primary["company_name"]
        .map(normalized_name)
    )

    primary[
        "name_loose"
    ] = (
        primary["company_name"]
        .map(loose_name)
    )

    normalized_map: dict[
        str,
        dict[str, Any],
    ] = {}

    loose_map: dict[
        str,
        dict[str, Any],
    ] = {}

    for _, row in primary.iterrows():
        data = row.to_dict()

        name_key = clean_text(
            data.get(
                "name_normalized"
            )
        )

        loose_key = clean_text(
            data.get(
                "name_loose"
            )
        )

        if (
            name_key
            and name_key not in normalized_map
        ):
            normalized_map[
                name_key
            ] = data

        if (
            loose_key
            and loose_key not in loose_map
        ):
            loose_map[
                loose_key
            ] = data

    # --------------------------------------------------------
    # Master lookup
    # --------------------------------------------------------

    master_by_symbol = (
        master_lookup.set_index(
            "symbol",
            drop=False,
        )
    )

    recovered: list[
        dict[str, Any]
    ] = []

    unresolved_rows: list[
        dict[str, Any]
    ] = []

    for index, symbol in enumerate(
        missing_symbols,
        start=1,
    ):
        symbol = (
            clean_text(symbol)
            .upper()
        )

        if (
            symbol
            not in master_by_symbol.index
        ):
            unresolved_rows.append(
                {
                    "symbol": symbol,
                    "company_name": "",
                    "reason": (
                        "symbol_not_in_master"
                    ),
                }
            )

            continue

        master_row = (
            master_by_symbol.loc[symbol]
        )

        if isinstance(
            master_row,
            pd.DataFrame,
        ):
            master_row = (
                master_row.iloc[0]
            )

        company_name = clean_text(
            master_row[
                "company_name"
            ]
        )

        match: (
            dict[str, Any] | None
        ) = None

        # 1. Exact source ticker.
        source_row = (
            exact_symbol_map.get(
                symbol
            )
        )

        if source_row:
            match = source_row

        # 2. Normalized company name.
        if match is None:
            normalized_key = (
                normalized_name(
                    company_name
                )
            )

            match = (
                normalized_map.get(
                    normalized_key
                )
            )

        # 3. Loose company name.
        if match is None:
            loose_key = (
                loose_name(
                    company_name
                )
            )

            match = (
                loose_map.get(
                    loose_key
                )
            )

        # ----------------------------------------------------
        # No reliable match
        # ----------------------------------------------------

        if match is None:
            unresolved_rows.append(
                {
                    "symbol": symbol,
                    "company_name": (
                        company_name
                    ),
                    "reason": (
                        "no_reliable_primary_match"
                    ),
                }
            )

            continue

        sector = clean_text(
            match.get("sector")
        )

        # Require an actual sector.
        if not sector:
            unresolved_rows.append(
                {
                    "symbol": symbol,
                    "company_name": (
                        company_name
                    ),
                    "reason": (
                        "matched_row_has_no_sector"
                    ),
                }
            )

            continue

        recovered.append(
            {
                "symbol": symbol,
                "company_name": company_name,
                "macro_sector": clean_text(
                    match.get(
                        "macro_sector"
                    )
                ),
                "sector": sector,
                "industry": clean_text(
                    match.get(
                        "industry"
                    )
                ),
                "basic_industry": clean_text(
                    match.get(
                        "basic_industry"
                    )
                ),
                "classification_source": (
                    "The Annexure "
                    "primary classification"
                ),
            }
        )

        if (
            index == 1
            or index % 25 == 0
            or index == len(
                missing_symbols
            )
        ):
            print(
                f"[{index:,}/"
                f"{len(missing_symbols):,}] "
                f"Recovered: "
                f"{len(recovered):,}"
            )

    recovered_dataframe = pd.DataFrame(
        recovered,
        columns=CLASSIFICATION_COLUMNS,
    )

    unresolved_dataframe = pd.DataFrame(
        unresolved_rows,
        columns=[
            "symbol",
            "company_name",
            "reason",
        ],
    )

    # --------------------------------------------------------
    # Combine and persist
    # --------------------------------------------------------

    if recovered_dataframe.empty:
        combined = (
            classification.copy()
        )

    elif classification.empty:
        combined = (
            recovered_dataframe
        )

    else:
        combined = pd.concat(
            [
                classification,
                recovered_dataframe,
            ],
            ignore_index=True,
        )

    combined = combined[
        CLASSIFICATION_COLUMNS
    ].copy()

    combined = (
        combined
        .drop_duplicates(
            subset=["symbol"],
            keep="last",
        )
        .sort_values("symbol")
        .reset_index(drop=True)
    )

    save_classification_cache(
        combined
    )

    print()
    print(
        "Recovered from primary directory: "
        f"{len(recovered_dataframe):,}"
    )

    print(
        "Still unresolved: "
        f"{len(unresolved_dataframe):,}"
    )

    if not unresolved_dataframe.empty:
        unresolved_dataframe.to_csv(
            UNRESOLVED_FILE,
            index=False,
            encoding="utf-8",
        )

    return (
        combined,
        unresolved_dataframe,
    )


# ============================================================
# MERGE CLASSIFICATION
# ============================================================

def merge_sector_classification(
    dataframe: pd.DataFrame,
    classification: pd.DataFrame,
) -> pd.DataFrame:

    if dataframe.empty:
        return dataframe.copy()

    result = dataframe.copy()

    # --------------------------------------------------------
    # Empty classification
    # --------------------------------------------------------

    if classification.empty:
        for column in [
            "company_name",
            "macro_sector",
            "sector",
            "industry",
            "basic_industry",
            "classification_source",
        ]:
            if column not in result.columns:
                result[column] = ""

        return result

    mapping = classification.copy()

    mapping["symbol"] = (
        mapping["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    for column in [
        "company_name",
        "macro_sector",
        "sector",
        "industry",
        "basic_industry",
        "classification_source",
    ]:
        if column not in mapping.columns:
            mapping[column] = ""

    mapping = mapping[
        [
            "symbol",
            "company_name",
            "macro_sector",
            "sector",
            "industry",
            "basic_industry",
            "classification_source",
        ]
    ].drop_duplicates(
        subset=["symbol"],
        keep="last",
    )

    if "symbol" not in result.columns:
        raise RuntimeError(
            "Scanner dataframe is missing "
            "'symbol'."
        )

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Prevent company_name duplication.
    mapping = mapping.rename(
        columns={
            "company_name":
            "classified_company_name"
        }
    )

    result = result.merge(
        mapping,
        on="symbol",
        how="left",
    )

    if "company_name" not in result.columns:
        result["company_name"] = ""

    empty_company = (
        result[
            "company_name"
        ]
        .astype(str)
        .str.strip()
        .eq("")
    )

    result.loc[
        empty_company,
        "company_name",
    ] = result.loc[
        empty_company,
        "classified_company_name",
    ]

    result.drop(
        columns=[
            "classified_company_name",
        ],
        inplace=True,
        errors="ignore",
    )

    for column in [
        "company_name",
        "macro_sector",
        "sector",
        "industry",
        "basic_industry",
        "classification_source",
    ]:
        if column not in result.columns:
            result[column] = ""

        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return result


# ============================================================
# SECTOR REGIME
# ============================================================

def determine_sector_regime(
    average_return_20d: float | None,
    relative_strength_20d: float | None,
    above_ema50_percent: float | None,
) -> str:
    """
    Descriptive sector regime only.

    Not a trading signal.
    """

    score = 0
    evidence = 0

    # --------------------------------------------------------
    # 20D return
    # --------------------------------------------------------

    if average_return_20d is not None:
        evidence += 1

        if average_return_20d > 5:
            score += 2

        elif average_return_20d > 0:
            score += 1

        elif average_return_20d < -5:
            score -= 2

        else:
            score -= 1

    # --------------------------------------------------------
    # Relative strength
    # --------------------------------------------------------

    if relative_strength_20d is not None:
        evidence += 1

        if relative_strength_20d > 5:
            score += 2

        elif relative_strength_20d > 0:
            score += 1

        elif relative_strength_20d < -5:
            score -= 2

        else:
            score -= 1

    # --------------------------------------------------------
    # EMA50 breadth
    # --------------------------------------------------------

    if above_ema50_percent is not None:
        evidence += 1

        if above_ema50_percent >= 60:
            score += 2

        elif above_ema50_percent >= 50:
            score += 1

        elif above_ema50_percent < 40:
            score -= 2

        else:
            score -= 1

    if evidence == 0:
        return "INSUFFICIENT_DATA"

    if score >= 5:
        return "STRONG"

    if score >= 2:
        return "POSITIVE"

    if score <= -5:
        return "WEAK"

    if score <= -2:
        return "NEGATIVE"

    return "NEUTRAL"


# ============================================================
# SECTOR ANALYSIS
# ============================================================

def analyze_sector(
    group: pd.DataFrame,
    nifty_returns: dict[str, Any],
) -> dict[str, Any]:

    if group.empty:
        return {}

    sector_name = clean_text(
        group[
            "sector"
        ].iloc[0]
    )

    macro_sector = clean_text(
        group[
            "macro_sector"
        ].iloc[0]
    )

    stock_count = len(group)

    # --------------------------------------------------------
    # RETURNS
    # --------------------------------------------------------

    average_return_1d = pct_mean(
        group["return_1d"]
    )

    average_return_5d = pct_mean(
        group["return_5d"]
    )

    average_return_20d = pct_mean(
        group["return_20d"]
    )

    average_return_60d = pct_mean(
        group["return_60d"]
    )

    # --------------------------------------------------------
    # NIFTY
    # --------------------------------------------------------

    nifty_20d = safe_float(
        nifty_returns.get(
            "return_20d"
        )
    )

    nifty_60d = safe_float(
        nifty_returns.get(
            "return_60d"
        )
    )

    relative_strength_20d = None
    relative_strength_60d = None

    if (
        average_return_20d is not None
        and nifty_20d is not None
    ):
        relative_strength_20d = (
            average_return_20d
            - nifty_20d
        )

    if (
        average_return_60d is not None
        and nifty_60d is not None
    ):
        relative_strength_60d = (
            average_return_60d
            - nifty_60d
        )

    # --------------------------------------------------------
    # DAILY BREADTH
    # --------------------------------------------------------

    return_1d_numeric = pd.to_numeric(
        group["return_1d"],
        errors="coerce",
    )

    advancing = int(
        (
            return_1d_numeric > 0
        ).sum()
    )

    declining = int(
        (
            return_1d_numeric < 0
        ).sum()
    )

    unchanged = (
        stock_count
        - advancing
        - declining
    )

    advance_decline_ratio = safe_ratio(
        advancing,
        declining,
    )

    # --------------------------------------------------------
    # EMA BREADTH
    # --------------------------------------------------------

    price = pd.to_numeric(
        group["price"],
        errors="coerce",
    )

    ema20 = pd.to_numeric(
        group["ema_20"],
        errors="coerce",
    )

    ema50 = pd.to_numeric(
        group["ema_50"],
        errors="coerce",
    )

    ema200 = pd.to_numeric(
        group["ema_200"],
        errors="coerce",
    )

    above_ema20_percent = safe_float(
        (
            price > ema20
        ).mean()
        * 100
    )

    above_ema50_percent = safe_float(
        (
            price > ema50
        ).mean()
        * 100
    )

    above_ema200_percent = safe_float(
        (
            price > ema200
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # TREND BREADTH
    # --------------------------------------------------------

    trend = (
        group["trend"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    strong_uptrend_percent = safe_float(
        (
            trend
            == "STRONG_UPTREND"
        ).mean()
        * 100
    )

    strong_downtrend_percent = safe_float(
        (
            trend
            == "STRONG_DOWNTREND"
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    rsi = pd.to_numeric(
        group["rsi_14"],
        errors="coerce",
    )

    rsi_clean = rsi.dropna()

    average_rsi = (
        safe_float(
            rsi_clean.mean()
        )
        if not rsi_clean.empty
        else None
    )

    macd_condition = (
        group[
            "macd_condition"
        ]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    bullish_macd_percent = safe_float(
        (
            macd_condition
            == "BULLISH"
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    relative_volume = pd.to_numeric(
        group[
            "relative_volume"
        ],
        errors="coerce",
    )

    rv_clean = (
        relative_volume.dropna()
    )

    average_relative_volume = (
        safe_float(
            rv_clean.mean()
        )
        if not rv_clean.empty
        else None
    )

    high_volume_percent = safe_float(
        (
            relative_volume >= 1.5
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    atr_percent = pd.to_numeric(
        group["atr_percent"],
        errors="coerce",
    )

    atr_clean = (
        atr_percent.dropna()
    )

    average_atr_percent = (
        safe_float(
            atr_clean.mean()
        )
        if not atr_clean.empty
        else None
    )

    # --------------------------------------------------------
    # TECHNICAL SCORE
    # --------------------------------------------------------

    score = pd.to_numeric(
        group["score"],
        errors="coerce",
    )

    score_clean = score.dropna()

    average_score = (
        safe_float(
            score_clean.mean()
        )
        if not score_clean.empty
        else None
    )

    median_score = (
        safe_float(
            score_clean.median()
        )
        if not score_clean.empty
        else None
    )

    # --------------------------------------------------------
    # RELATIVE STRENGTH BREADTH
    # --------------------------------------------------------

    rs20 = pd.to_numeric(
        group[
            "relative_strength_20d"
        ],
        errors="coerce",
    )

    rs60 = pd.to_numeric(
        group[
            "relative_strength_60d"
        ],
        errors="coerce",
    )

    positive_rs20_percent = safe_float(
        (
            rs20 > 0
        ).mean()
        * 100
    )

    positive_rs60_percent = safe_float(
        (
            rs60 > 0
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # REGIME
    # --------------------------------------------------------

    regime = determine_sector_regime(
        average_return_20d,
        relative_strength_20d,
        above_ema50_percent,
    )

    return {
        "macro_sector": macro_sector,
        "sector": sector_name,
        "stocks": stock_count,
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "advance_decline_ratio": (
            advance_decline_ratio
        ),
        "return_1d": (
            average_return_1d
        ),
        "return_5d": (
            average_return_5d
        ),
        "return_20d": (
            average_return_20d
        ),
        "return_60d": (
            average_return_60d
        ),
        "nifty_return_20d": (
            nifty_20d
        ),
        "nifty_return_60d": (
            nifty_60d
        ),
        "relative_strength_20d": (
            relative_strength_20d
        ),
        "relative_strength_60d": (
            relative_strength_60d
        ),
        "above_ema20_percent": (
            above_ema20_percent
        ),
        "above_ema50_percent": (
            above_ema50_percent
        ),
        "above_ema200_percent": (
            above_ema200_percent
        ),
        "strong_uptrend_percent": (
            strong_uptrend_percent
        ),
        "strong_downtrend_percent": (
            strong_downtrend_percent
        ),
        "average_rsi": (
            average_rsi
        ),
        "bullish_macd_percent": (
            bullish_macd_percent
        ),
        "average_relative_volume": (
            average_relative_volume
        ),
        "high_volume_percent": (
            high_volume_percent
        ),
        "average_atr_percent": (
            average_atr_percent
        ),
        "average_score": (
            average_score
        ),
        "median_score": (
            median_score
        ),
        "positive_rs20_percent": (
            positive_rs20_percent
        ),
        "positive_rs60_percent": (
            positive_rs60_percent
        ),
        "sector_regime": regime,
    }


# ============================================================
# MACRO SECTOR ANALYSIS
# ============================================================

def analyze_macro_sector(
    group: pd.DataFrame,
    nifty_returns: dict[str, Any],
) -> dict[str, Any]:

    macro_name = clean_text(
        group[
            "macro_sector"
        ].iloc[0]
    )

    average_return_20d = pct_mean(
        group["return_20d"]
    )

    average_return_60d = pct_mean(
        group["return_60d"]
    )

    nifty_20d = safe_float(
        nifty_returns.get(
            "return_20d"
        )
    )

    relative_strength_20d = None

    if (
        average_return_20d is not None
        and nifty_20d is not None
    ):
        relative_strength_20d = (
            average_return_20d
            - nifty_20d
        )

    price = pd.to_numeric(
        group["price"],
        errors="coerce",
    )

    ema50 = pd.to_numeric(
        group["ema_50"],
        errors="coerce",
    )

    above_ema50_percent = safe_float(
        (
            price > ema50
        ).mean()
        * 100
    )

    return {
        "macro_sector": macro_name,
        "stocks": len(group),
        "return_20d": (
            average_return_20d
        ),
        "return_60d": (
            average_return_60d
        ),
        "relative_strength_20d": (
            relative_strength_20d
        ),
        "above_ema50_percent": (
            above_ema50_percent
        ),
    }


# ============================================================
# FULL SECTOR SCAN
# ============================================================

def scan_sectors(
    update_classification: bool = True,
    force_classification: bool = False,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
    """
    Run complete Nova Sector Intelligence.

    Arguments retained for compatibility.
    The dedicated sector_classification.py engine
    owns classification updates.
    """

    print()
    print("=" * 80)
    print("NOVA SECTOR INTELLIGENCE")
    print("=" * 80)

    # --------------------------------------------------------
    # MARKET SCANNER
    # --------------------------------------------------------

    print()
    print(
        "Loading Nova market scanner..."
    )

    scanner_dataframe, scanner_summary = (
        scan_market()
    )

    if scanner_dataframe.empty:
        raise RuntimeError(
            "Market scanner returned "
            "no usable stocks."
        )

    nifty_returns = (
        scanner_summary.get(
            "nifty_returns",
            {},
        )
    )

    # --------------------------------------------------------
    # CLASSIFICATION CACHE
    # --------------------------------------------------------

    print()
    print(
        "Loading canonical sector "
        "classification cache..."
    )

    classification = (
        load_classification_cache()
    )

    print(
        "Classification cache records: "
        f"{len(classification):,}"
    )

    # --------------------------------------------------------
    # RECONCILE MISSING STOCKS
    # --------------------------------------------------------

    (
        classification,
        unresolved,
    ) = reconcile_missing_classifications(
        scanner_dataframe,
        classification,
    )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    enriched = (
        merge_sector_classification(
            scanner_dataframe,
            classification,
        )
    )

    # --------------------------------------------------------
    # COVERAGE
    # --------------------------------------------------------

    classified_mask = (
        enriched["sector"]
        .astype(str)
        .str.strip()
        .ne("")
    )

    total_count = len(
        enriched
    )

    classified_count = int(
        classified_mask.sum()
    )

    classification_coverage = (
        classified_count
        / total_count
        * 100
        if total_count > 0
        else 0.0
    )

    print()
    print(
        f"Stocks analyzed        : "
        f"{total_count:,}"
    )

    print(
        f"Stocks classified      : "
        f"{classified_count:,}"
    )

    print(
        f"Classification coverage: "
        f"{classification_coverage:.2f}%"
    )

    # --------------------------------------------------------
    # UNRESOLVED REPORT
    # --------------------------------------------------------

    if not unresolved.empty:
        unresolved.to_csv(
            UNRESOLVED_FILE,
            index=False,
            encoding="utf-8",
        )

    else:
        pd.DataFrame(
            columns=[
                "symbol",
                "company_name",
                "reason",
            ]
        ).to_csv(
            UNRESOLVED_FILE,
            index=False,
            encoding="utf-8",
        )

    # --------------------------------------------------------
    # CLASSIFIED DATA
    # --------------------------------------------------------

    classified = enriched[
        classified_mask
    ].copy()

    if classified.empty:
        raise RuntimeError(
            "No stocks have usable "
            "sector classification."
        )

    # --------------------------------------------------------
    # NUMERIC NORMALIZATION
    # --------------------------------------------------------

    numeric_columns = [
        "price",
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
        "relative_strength_20d",
        "relative_strength_60d",
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "relative_volume",
        "atr_percent",
        "score",
    ]

    for column in numeric_columns:
        if column in classified.columns:
            classified[column] = (
                pd.to_numeric(
                    classified[column],
                    errors="coerce",
                )
            )

    # --------------------------------------------------------
    # SECTOR ANALYSIS
    # --------------------------------------------------------

    sector_records: list[
        dict[str, Any]
    ] = []

    for (
        sector_name,
        group,
    ) in classified.groupby(
        "sector",
        sort=False,
        dropna=True,
    ):

        sector_name = clean_text(
            sector_name
        )

        if not sector_name:
            continue

        record = analyze_sector(
            group,
            nifty_returns,
        )

        if record:
            sector_records.append(
                record
            )

    sector_dataframe = pd.DataFrame(
        sector_records
    )

    if sector_dataframe.empty:
        raise RuntimeError(
            "Sector analysis returned "
            "no sectors."
        )

    # --------------------------------------------------------
    # SECTOR NUMERIC CLEANUP
    # --------------------------------------------------------

    sector_numeric_columns = [
        "stocks",
        "advancing",
        "declining",
        "unchanged",
        "advance_decline_ratio",
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
        "nifty_return_20d",
        "nifty_return_60d",
        "relative_strength_20d",
        "relative_strength_60d",
        "above_ema20_percent",
        "above_ema50_percent",
        "above_ema200_percent",
        "strong_uptrend_percent",
        "strong_downtrend_percent",
        "average_rsi",
        "bullish_macd_percent",
        "average_relative_volume",
        "high_volume_percent",
        "average_atr_percent",
        "average_score",
        "median_score",
        "positive_rs20_percent",
        "positive_rs60_percent",
    ]

    for column in sector_numeric_columns:
        if column in sector_dataframe.columns:
            sector_dataframe[column] = (
                pd.to_numeric(
                    sector_dataframe[column],
                    errors="coerce",
                )
            )

    # --------------------------------------------------------
    # LEADERSHIP RANKING
    # --------------------------------------------------------

    sector_dataframe = (
        sector_dataframe
        .sort_values(
            [
                "relative_strength_20d",
                "average_score",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    sector_dataframe[
        "leadership_rank"
    ] = (
        sector_dataframe.index
        + 1
    )

    # --------------------------------------------------------
    # LEADERS
    # --------------------------------------------------------

    leaders = (
        sector_dataframe
        .sort_values(
            [
                "relative_strength_20d",
                "relative_strength_60d",
                "average_score",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum = (
        sector_dataframe
        .sort_values(
            [
                "return_20d",
                "return_60d",
                "average_score",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # BREADTH
    # --------------------------------------------------------

    breadth = (
        sector_dataframe
        .sort_values(
            [
                "above_ema50_percent",
                "above_ema20_percent",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume = (
        sector_dataframe
        .sort_values(
            [
                "average_relative_volume",
                "average_score",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # LAGGARDS
    # --------------------------------------------------------

    laggards = (
        sector_dataframe
        .sort_values(
            [
                "relative_strength_20d",
                "relative_strength_60d",
                "average_score",
            ],
            ascending=True,
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # REGIME COUNTS
    # --------------------------------------------------------

    regime_counts = (
        sector_dataframe[
            "sector_regime"
        ]
        .value_counts()
        .to_dict()
    )

    # --------------------------------------------------------
    # MACRO SECTORS
    # --------------------------------------------------------

    macro_records: list[
        dict[str, Any]
    ] = []

    for (
        macro_name,
        group,
    ) in classified.groupby(
        "macro_sector",
        sort=False,
        dropna=True,
    ):

        macro_name = clean_text(
            macro_name
        )

        if not macro_name:
            continue

        macro_records.append(
            analyze_macro_sector(
                group,
                nifty_returns,
            )
        )

    macro_dataframe = pd.DataFrame(
        macro_records
    )

    if not macro_dataframe.empty:
        macro_dataframe = (
            macro_dataframe
            .sort_values(
                "relative_strength_20d",
                ascending=False,
                na_position="last",
            )
            .reset_index(
                drop=True
            )
        )

    # --------------------------------------------------------
    # SAVE REPORTS
    # --------------------------------------------------------

    timestamp = (
        pd.Timestamp.now(
            tz="Asia/Kolkata"
        )
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    sector_output = (
        CACHE_DIR
        / (
            f"{SECTOR_OUTPUT_PREFIX}_"
            f"{timestamp}.csv"
        )
    )

    macro_output = (
        CACHE_DIR
        / (
            f"{MACRO_OUTPUT_PREFIX}_"
            f"{timestamp}.csv"
        )
    )

    enriched_output = (
        CACHE_DIR
        / (
            f"{ENRICHED_OUTPUT_PREFIX}_"
            f"{timestamp}.csv"
        )
    )

    sector_dataframe.to_csv(
        sector_output,
        index=False,
        encoding="utf-8",
    )

    if not macro_dataframe.empty:
        macro_dataframe.to_csv(
            macro_output,
            index=False,
            encoding="utf-8",
        )

    classified.to_csv(
        enriched_output,
        index=False,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    result_summary = {
        "market_regime": (
            scanner_summary.get(
                "market_regime",
                "UNKNOWN",
            )
        ),
        "nifty_returns": (
            nifty_returns
        ),
        "stocks_analyzed": (
            total_count
        ),
        "stocks_classified": (
            classified_count
        ),
        "stocks_unclassified": (
            total_count
            - classified_count
        ),
        "classification_coverage_percent": (
            classification_coverage
        ),
        "sectors_found": (
            len(sector_dataframe)
        ),
        "macro_sectors_found": (
            len(macro_dataframe)
        ),
        "sector_regime_counts": (
            regime_counts
        ),
        "classification_cache": (
            str(CLASSIFICATION_FILE)
        ),
        "sector_report": (
            str(sector_output)
        ),
        "macro_report": (
            str(macro_output)
            if not macro_dataframe.empty
            else ""
        ),
        "enriched_stock_report": (
            str(enriched_output)
        ),
        "unresolved_report": (
            str(UNRESOLVED_FILE)
        ),
        "generated_at": (
            pd.Timestamp.now(
                tz="Asia/Kolkata"
            ).isoformat()
        ),
        "analysis_only": True,
        "sector_is_buy_sell_signal": False,
        "buy_sell_authorization": False,
        "trading_execution": False,
        "broker_connection": False,
        "automatic_orders": False,
    }

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "SECTOR INTELLIGENCE COMPLETE"
    )
    print("=" * 80)

    print()
    print(
        f"Stocks analyzed        : "
        f"{total_count:,}"
    )

    print(
        f"Stocks classified      : "
        f"{classified_count:,}"
    )

    print(
        f"Classification coverage: "
        f"{classification_coverage:.2f}%"
    )

    print(
        f"Sectors found          : "
        f"{len(sector_dataframe):,}"
    )

    print(
        f"Macro sectors found    : "
        f"{len(macro_dataframe):,}"
    )

    print(
        f"Still unclassified     : "
        f"{len(unresolved):,}"
    )

    # --------------------------------------------------------
    # LEADERS
    # --------------------------------------------------------

    print()
    print("SECTOR LEADERS")
    print("-" * 80)

    print(
        leaders[
            [
                "sector",
                "stocks",
                "return_1d",
                "return_5d",
                "return_20d",
                "relative_strength_20d",
                "above_ema50_percent",
                "average_score",
                "sector_regime",
            ]
        ]
        .head(10)
        .to_string(
            index=False,
            float_format=(
                lambda value:
                f"{value:.2f}"
            ),
        )
    )

    # --------------------------------------------------------
    # LAGGARDS
    # --------------------------------------------------------

    print()
    print("SECTOR LAGGARDS")
    print("-" * 80)

    print(
        laggards[
            [
                "sector",
                "stocks",
                "return_1d",
                "return_5d",
                "return_20d",
                "relative_strength_20d",
                "above_ema50_percent",
                "average_score",
                "sector_regime",
            ]
        ]
        .head(10)
        .to_string(
            index=False,
            float_format=(
                lambda value:
                f"{value:.2f}"
            ),
        )
    )

    # --------------------------------------------------------
    # BREADTH
    # --------------------------------------------------------

    print()
    print("SECTOR BREADTH")
    print("-" * 80)

    print(
        breadth[
            [
                "sector",
                "stocks",
                "advancing",
                "declining",
                "advance_decline_ratio",
                "above_ema20_percent",
                "above_ema50_percent",
                "above_ema200_percent",
            ]
        ]
        .head(10)
        .to_string(
            index=False,
            float_format=(
                lambda value:
                f"{value:.2f}"
            ),
        )
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    print()
    print(
        "SECTOR VOLUME EXPANSION"
    )
    print("-" * 80)

    print(
        volume[
            [
                "sector",
                "stocks",
                "average_relative_volume",
                "high_volume_percent",
                "average_atr_percent",
                "average_score",
            ]
        ]
        .head(10)
        .to_string(
            index=False,
            float_format=(
                lambda value:
                f"{value:.2f}"
            ),
        )
    )

    # --------------------------------------------------------
    # DATA AVAILABILITY
    # --------------------------------------------------------

    print()
    print("DATA AVAILABILITY")
    print("-" * 80)

    print(
        "Sector returns            AVAILABLE"
    )

    print(
        "Sector breadth            AVAILABLE"
    )

    print(
        "Sector relative strength  AVAILABLE"
    )

    print(
        "Sector momentum            AVAILABLE"
    )

    print(
        "Sector volume              AVAILABLE"
    )

    print(
        "Sector volatility          AVAILABLE"
    )

    print(
        "Industry classification    AVAILABLE"
    )

    print(
        "Basic industry             AVAILABLE"
    )

    print(
        "Unresolved classifications "
        f"{len(unresolved):,}"
    )

    # --------------------------------------------------------
    # DECISION POLICY
    # --------------------------------------------------------

    print()
    print("DECISION POLICY")
    print("-" * 80)

    print(
        "SECTOR_IS_BUY_SELL_SIGNAL=FALSE"
    )

    print(
        "BUY_SELL_AUTHORIZATION=FALSE"
    )

    print(
        "TRADING_EXECUTION=FALSE"
    )

    print(
        "BROKER_CONNECTION=FALSE"
    )

    print(
        "AUTOMATIC_ORDERS=FALSE"
    )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    print()
    print(
        f"Sector report: "
        f"{sector_output}"
    )

    print(
        f"Macro report: "
        f"{macro_output}"
    )

    print(
        f"Enriched stock report: "
        f"{enriched_output}"
    )

    print(
        f"Unresolved report: "
        f"{UNRESOLVED_FILE}"
    )

    print("=" * 80)

    return (
        sector_dataframe,
        result_summary,
    )


# ============================================================
# COMMAND LINE
# ============================================================

def main() -> None:
    dataframe, summary = (
        scan_sectors(
            update_classification=True,
            force_classification=False,
        )
    )

    print()
    print(
        "NOVA SECTOR ENGINE TEST COMPLETE"
    )

    print(
        f"Sectors analyzed: "
        f"{len(dataframe):,}"
    )

    print(
        "Stocks classified: "
        f"{summary['stocks_classified']:,}"
    )

    print(
        "Coverage: "
        f"{summary['classification_coverage_percent']:.2f}%"
    )

    print(
        "Still unclassified: "
        f"{summary['stocks_unclassified']:,}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print()
        print(
            "Sector Intelligence "
            "interrupted by user."
        )
        raise SystemExit(1)

    except Exception as exc:
        print()
        print(
            "SECTOR ENGINE ERROR"
        )
        print(str(exc))
        raise SystemExit(1)