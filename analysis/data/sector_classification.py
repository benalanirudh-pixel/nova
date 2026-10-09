"""
Nova NSE Sector Classification
==============================

PRIMARY SOURCE
---------------
The Annexure bulk company classification directory.

FALLBACK SOURCE
---------------
PatternsRadar NSE stock pages.

WHY
---
NSE's quote-equity API is returning HTTP 403 from the
current environment.

finfetch also reaches an NSE endpoint and therefore
returns HTTP 403.

PatternsRadar exposes current NSE classification on
its NSE stock pages, including:

    Macro sector
    Sector
    Industry
    Basic industry

Nova uses it ONLY as a secondary source for securities
that cannot be matched against the primary bulk source.

MATCHING
--------
Primary:
    1. Exact symbol
    2. Exact company name
    3. Loose company name
    4. High-confidence fuzzy name

Fallback:
    Exact canonical NSE symbol on PatternsRadar page.

IMPORTANT
---------
No classification is guessed from price, trend,
company name, or sector similarity.

Unresolved securities remain unresolved.

This module does NOT:
    - place trades
    - connect to brokers
    - send orders
    - generate automatic BUY/SELL orders
"""

from __future__ import annotations

import html
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from analysis.data.symbol_master import load_master


# ============================================================
# PATHS
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

CLASSIFICATION_FILE = (
    CACHE_DIR
    / "nse_sector_classification.csv"
)

RAW_HTML_FILE = (
    CACHE_DIR
    / "annexure_companies.html"
)

META_FILE = (
    CACHE_DIR
    / "nse_sector_classification_meta.json"
)

PRIMARY_MATCH_REPORT = (
    CACHE_DIR
    / "classification_match_report.csv"
)

UNMATCHED_FILE = (
    CACHE_DIR
    / "classification_unmatched_nse.csv"
)

FALLBACK_REPORT_FILE = (
    CACHE_DIR
    / "patternsradar_fallback_report.csv"
)


# ============================================================
# SOURCES
# ============================================================

PRIMARY_SOURCE_URL = (
    "https://theannexure.com/companies"
)

PRIMARY_SOURCE_NAME = (
    "The Annexure company classification directory"
)

FALLBACK_SOURCE_URL = (
    "https://patternsradar.com/s/{symbol}"
)

FALLBACK_SOURCE_NAME = (
    "PatternsRadar NSE classification fallback"
)


# ============================================================
# HTTP
# ============================================================

TIMEOUT = 30

REQUEST_DELAY = 0.60

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/154.0.0.0 "
    "Safari/537.36"
)


# ============================================================
# OUTPUT
# ============================================================

OUTPUT_COLUMNS = [
    "symbol",
    "company_name",
    "macro_sector",
    "sector",
    "industry",
    "basic_industry",
    "classification_source",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(
    value: Any,
) -> str:
    """
    Clean text / HTML entities.
    """

    if value is None:
        return ""

    text = str(value)

    text = html.unescape(
        text
    )

    text = (
        text
        .replace(
            "\u00a0",
            " ",
        )
        .replace(
            "\r",
            " ",
        )
        .replace(
            "\t",
            " ",
        )
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_symbol(
    value: Any,
) -> str:
    """
    Normalize NSE symbol.
    """

    return (
        clean_text(value)
        .upper()
        .replace(
            ".NS",
            "",
        )
    )


def normalize_company_name(
    value: Any,
) -> str:
    """
    Conservative company-name normalization.
    """

    text = (
        clean_text(value)
        .lower()
    )

    text = html.unescape(
        text
    )

    text = (
        text
        .replace(
            "&",
            " and ",
        )
        .replace(
            "/",
            " ",
        )
        .replace(
            "-",
            " ",
        )
        .replace(
            ".",
            " ",
        )
        .replace(
            ",",
            " ",
        )
        .replace(
            "'",
            "",
        )
    )

    tokens = re.findall(
        r"[a-z0-9]+",
        text,
    )

    legal_suffixes = {
        "ltd",
        "limited",
        "private",
        "pvt",
        "plc",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
    }

    tokens = [
        token
        for token in tokens
        if token not in legal_suffixes
    ]

    return " ".join(tokens)


def loose_company_name(
    value: Any,
) -> str:
    """
    Secondary normalization.
    """

    text = normalize_company_name(
        value
    )

    generic_words = {
        "the",
        "company",
        "industries",
        "industrial",
        "group",
        "india",
    }

    return " ".join(
        token
        for token in text.split()
        if token not in generic_words
    )


# ============================================================
# HTML ATTRIBUTE
# ============================================================

def extract_attribute(
    tag: str,
    attribute: str,
) -> str:
    """
    Extract one HTML attribute.
    """

    pattern = re.compile(
        rf'\b{re.escape(attribute)}\s*=\s*'
        r'(["\'])(.*?)\1',
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(
        tag
    )

    if not match:
        return ""

    return clean_text(
        match.group(2)
    )


# ============================================================
# PRIMARY HTML PARSER
# ============================================================

ROW_PATTERN = re.compile(
    r'<tr\b'
    r'[^>]*'
    r'class\s*=\s*'
    r'(["\'])'
    r'[^"\']*\bco-row\b[^"\']*'
    r'\1'
    r'[^>]*>'
    r'.*?'
    r'</tr>',
    re.IGNORECASE | re.DOTALL,
)


def extract_primary_ticker(
    row: str,
) -> str:
    """
    Extract source ticker.
    """

    pattern = re.compile(
        r'<td\b[^>]*class=["\'][^"\']*'
        r'\bco-col-ticker\b[^"\']*["\'][^>]*>'
        r'(.*?)'
        r'</td>',
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(
        row
    )

    if not match:
        return ""

    value = re.sub(
        r"<[^>]+>",
        "",
        match.group(1),
    )

    return normalize_symbol(
        value
    )


def parse_primary_html(
    source_html: str,
) -> pd.DataFrame:
    """
    Parse The Annexure's company rows.

    The classification values are taken directly from:

        data-macro
        data-sector
        data-industry
        data-basic
    """

    matches = list(
        ROW_PATTERN.finditer(
            source_html
        )
    )

    print()
    print(
        f"Primary company rows: "
        f"{len(matches):,}"
    )

    records = []

    for match in matches:

        row = match.group(0)

        opening_match = re.search(
            r"<tr\b[^>]*>",
            row,
            re.IGNORECASE | re.DOTALL,
        )

        if not opening_match:
            continue

        opening_tag = (
            opening_match.group(0)
        )

        source_symbol = (
            extract_primary_ticker(
                row
            )
        )

        if not source_symbol:
            continue

        company_name = (
            extract_attribute(
                opening_tag,
                "data-name",
            )
        )

        macro_sector = (
            extract_attribute(
                opening_tag,
                "data-macro",
            )
        )

        sector = (
            extract_attribute(
                opening_tag,
                "data-sector",
            )
        )

        industry = (
            extract_attribute(
                opening_tag,
                "data-industry",
            )
        )

        basic_industry = (
            extract_attribute(
                opening_tag,
                "data-basic",
            )
        )

        if not sector:
            continue

        records.append(
            {
                "source_symbol":
                    normalize_symbol(
                        source_symbol
                    ),

                "source_company_name":
                    clean_text(
                        company_name
                    ),

                "macro_sector":
                    clean_text(
                        macro_sector
                    ),

                "sector":
                    clean_text(
                        sector
                    ),

                "industry":
                    clean_text(
                        industry
                    ),

                "basic_industry":
                    clean_text(
                        basic_industry
                    ),
            }
        )

    dataframe = pd.DataFrame(
        records
    )

    if dataframe.empty:

        raise RuntimeError(
            "Primary classification source "
            "returned zero usable rows."
        )

    dataframe = (
        dataframe
        .drop_duplicates(
            subset=[
                "source_symbol",
                "source_company_name",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    print(
        f"Primary classifications: "
        f"{len(dataframe):,}"
    )

    return dataframe


# ============================================================
# SOURCE HTML
# ============================================================

def load_primary_html(
    force_download: bool = False,
) -> str:
    """
    Load cached primary HTML or download it.
    """

    if (
        RAW_HTML_FILE.exists()
        and not force_download
    ):

        content = (
            RAW_HTML_FILE.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        )

        if content.strip():

            print()
            print(
                "Using existing primary HTML:"
            )

            print(
                RAW_HTML_FILE
            )

            print(
                f"Cached characters: "
                f"{len(content):,}"
            )

            return content

    headers = {
        "User-Agent":
            USER_AGENT,

        "Accept":
            (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),

        "Accept-Language":
            "en-US,en;q=0.9,en-IN;q=0.8",

        "Connection":
            "keep-alive",
    }

    print()
    print(
        f"Downloading primary source:"
    )

    print(
        PRIMARY_SOURCE_URL
    )

    response = requests.get(
        PRIMARY_SOURCE_URL,
        headers=headers,
        timeout=TIMEOUT,
    )

    print(
        f"HTTP status: "
        f"{response.status_code}"
    )

    response.raise_for_status()

    content = response.text

    RAW_HTML_FILE.write_text(
        content,
        encoding="utf-8",
    )

    print(
        f"Downloaded characters: "
        f"{len(content):,}"
    )

    return content


# ============================================================
# PRIMARY NAME INDEX
# ============================================================

def build_primary_indexes(
    source: pd.DataFrame,
) -> tuple[
    dict[str, list[int]],
    dict[str, list[int]],
]:
    """
    Build exact and loose company-name indexes.
    """

    exact = {}
    loose = {}

    for index, row in (
        source.iterrows()
    ):

        name = str(
            row[
                "source_company_name"
            ]
        )

        exact_name = (
            normalize_company_name(
                name
            )
        )

        loose_name = (
            loose_company_name(
                name
            )
        )

        if exact_name:

            exact.setdefault(
                exact_name,
                [],
            ).append(index)

        if loose_name:

            loose.setdefault(
                loose_name,
                [],
            ).append(index)

    return exact, loose


# ============================================================
# PRIMARY MATCH
# ============================================================

def primary_match(
    nse_symbol: str,
    company_name: str,
    source: pd.DataFrame,
    exact_index: dict[str, list[int]],
    loose_index: dict[str, list[int]],
) -> tuple[
    int | None,
    str,
    float,
]:
    """
    Match NSE master security to primary source.
    """

    # --------------------------------------------------------
    # 1. Exact symbol
    # --------------------------------------------------------

    candidates = source[
        source["source_symbol"]
        .map(normalize_symbol)
        .eq(nse_symbol)
    ]

    if len(candidates) == 1:

        return (
            candidates.index[0],
            "EXACT_SYMBOL",
            1.0,
        )

    # --------------------------------------------------------
    # 2. Exact normalized name
    # --------------------------------------------------------

    normalized = (
        normalize_company_name(
            company_name
        )
    )

    candidates = exact_index.get(
        normalized,
        [],
    )

    if len(candidates) == 1:

        return (
            candidates[0],
            "EXACT_NAME",
            1.0,
        )

    # --------------------------------------------------------
    # 3. Loose exact name
    # --------------------------------------------------------

    loose = (
        loose_company_name(
            company_name
        )
    )

    candidates = loose_index.get(
        loose,
        [],
    )

    if len(candidates) == 1:

        return (
            candidates[0],
            "LOOSE_NAME",
            0.98,
        )

    # --------------------------------------------------------
    # 4. High-confidence fuzzy
    # --------------------------------------------------------

    best_index = None

    best_score = 0.0

    second_score = 0.0

    for index, row in (
        source.iterrows()
    ):

        candidate_name = str(
            row[
                "source_company_name"
            ]
        )

        score = SequenceMatcher(
            None,
            normalize_company_name(
                company_name
            ),
            normalize_company_name(
                candidate_name
            ),
        ).ratio()

        if score > best_score:

            second_score = best_score

            best_score = score

            best_index = index

        elif score > second_score:

            second_score = score

    margin = (
        best_score
        - second_score
    )

    if (
        best_index is not None
        and best_score >= 0.93
        and margin >= 0.04
    ):

        return (
            best_index,
            "FUZZY_HIGH_CONFIDENCE",
            best_score,
        )

    return (
        None,
        "UNMATCHED",
        best_score,
    )


# ============================================================
# BUILD PRIMARY CACHE
# ============================================================

def build_primary_cache(
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Build canonical cache from primary source.
    """

    html_source = load_primary_html(
        force_download=force_download
    )

    source = parse_primary_html(
        html_source
    )

    master = load_master()

    if master.empty:

        raise RuntimeError(
            "NSE security master is empty."
        )

    if (
        "symbol"
        not in master.columns
    ):

        raise RuntimeError(
            "NSE master has no symbol column."
        )

    if (
        "company_name"
        not in master.columns
    ):

        master["company_name"] = ""

    master = master.copy()

    master["symbol"] = (
        master["symbol"]
        .map(normalize_symbol)
    )

    master = (
        master
        .drop_duplicates(
            subset=["symbol"],
            keep="first",
        )
    )

    (
        exact_index,
        loose_index,
    ) = build_primary_indexes(
        source
    )

    records = []

    match_report = []

    unresolved = []

    for _, row in master.iterrows():

        symbol = normalize_symbol(
            row["symbol"]
        )

        company_name = clean_text(
            row["company_name"]
        )

        (
            source_index,
            method,
            confidence,
        ) = primary_match(
            symbol,
            company_name,
            source,
            exact_index,
            loose_index,
        )

        if source_index is not None:

            source_row = source.loc[
                source_index
            ]

            records.append(
                {
                    "symbol":
                        symbol,

                    "company_name":
                        company_name,

                    "macro_sector":
                        clean_text(
                            source_row[
                                "macro_sector"
                            ]
                        ),

                    "sector":
                        clean_text(
                            source_row[
                                "sector"
                            ]
                        ),

                    "industry":
                        clean_text(
                            source_row[
                                "industry"
                            ]
                        ),

                    "basic_industry":
                        clean_text(
                            source_row[
                                "basic_industry"
                            ]
                        ),

                    "classification_source":
                        PRIMARY_SOURCE_NAME,
                }
            )

            match_report.append(
                {
                    "symbol":
                        symbol,

                    "company_name":
                        company_name,

                    "source_symbol":
                        source_row[
                            "source_symbol"
                        ],

                    "source_company_name":
                        source_row[
                            "source_company_name"
                        ],

                    "match_method":
                        method,

                    "confidence":
                        confidence,
                }
            )

        else:

            unresolved.append(
                {
                    "symbol":
                        symbol,

                    "company_name":
                        company_name,

                    "reason":
                        "PRIMARY_SOURCE_NO_MATCH",

                    "best_similarity":
                        confidence,
                }
            )

    classification = pd.DataFrame(
        records,
        columns=OUTPUT_COLUMNS,
    )

    pd.DataFrame(
        match_report
    ).to_csv(
        PRIMARY_MATCH_REPORT,
        index=False,
        encoding="utf-8",
    )

    pd.DataFrame(
        unresolved
    ).to_csv(
        UNMATCHED_FILE,
        index=False,
        encoding="utf-8",
    )

    save_cache(
        classification
    )

    print()
    print(
        f"Primary classifications: "
        f"{len(classification):,}"
    )

    print(
        f"Primary unresolved: "
        f"{len(unresolved):,}"
    )

    return classification


# ============================================================
# PATTERNSRADAR PAGE
# ============================================================

def fetch_patternsradar_page(
    symbol: str,
) -> str:
    """
    Download one current NSE stock page from PatternsRadar.
    """

    url = (
        FALLBACK_SOURCE_URL.format(
            symbol=symbol
        )
    )

    headers = {
        "User-Agent":
            USER_AGENT,

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",

        "Accept-Language":
            "en-US,en;q=0.9,en-IN;q=0.8",

        "Connection":
            "keep-alive",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
    )

    if response.status_code != 200:

        raise RuntimeError(
            f"HTTP {response.status_code}"
        )

    if not response.text.strip():

        raise RuntimeError(
            "EMPTY_RESPONSE"
        )

    return response.text


# ============================================================
# HTML → TEXT
# ============================================================

def html_to_lines(
    source_html: str,
) -> list[str]:
    """
    Convert page HTML to reasonably clean text lines.

    Uses BeautifulSoup when installed.
    Falls back to a standard-library HTML parser.
    """

    try:

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            source_html,
            "html.parser",
        )

        text = soup.get_text(
            "\n",
            strip=True,
        )

    except ImportError:

        from html.parser import HTMLParser

        class TextExtractor(
            HTMLParser
        ):

            def __init__(self):

                super().__init__()

                self.parts = []

            def handle_data(
                self,
                data: str,
            ):

                data = clean_text(
                    data
                )

                if data:
                    self.parts.append(
                        data
                    )

        parser = TextExtractor()

        parser.feed(
            source_html
        )

        text = "\n".join(
            parser.parts
        )

    lines = []

    for line in text.splitlines():

        value = clean_text(
            line
        )

        if value:
            lines.append(
                value
            )

    return lines


# ============================================================
# PATTERNSRADAR CLASSIFICATION PARSER
# ============================================================

LABELS = [
    "Macro sector",
    "Macro Sector",
    "Sector",
    "Industry",
    "Basic industry",
    "Basic Industry",
]


def find_label_value(
    lines: list[str],
    label_variants: list[str],
    start: int,
) -> tuple[str, int]:
    """
    Find value following an exact label.

    Supports:
        Label
        Value

    and:
        Label: Value
    """

    normalized_labels = {
        label.lower()
        for label in label_variants
    }

    for index in range(
        start,
        len(lines),
    ):

        line = lines[index].strip()

        lower = line.lower()

        # Label: Value
        for label in normalized_labels:

            prefix = (
                label
                + ":"
            )

            if lower.startswith(
                prefix
            ):

                value = (
                    line[
                        len(prefix):
                    ].strip()
                )

                if value:
                    return (
                        value,
                        index,
                    )

        # Label on one line, value below
        if lower in normalized_labels:

            for next_index in range(
                index + 1,
                min(
                    index + 4,
                    len(lines),
                ),
            ):

                candidate = (
                    lines[
                        next_index
                    ].strip()
                )

                if not candidate:
                    continue

                if (
                    candidate.lower()
                    in normalized_labels
                ):
                    continue

                return (
                    candidate,
                    next_index,
                )

    return (
        "",
        start,
    )


def parse_patternsradar_classification(
    source_html: str,
) -> dict[str, str]:
    """
    Extract:

        Macro sector
        Sector
        Industry
        Basic industry
    """

    lines = html_to_lines(
        source_html
    )

    if not lines:

        return {}

    # --------------------------------------------------------
    # Locate Classification section.
    # --------------------------------------------------------

    classification_start = 0

    for index, line in enumerate(
        lines
    ):

        if (
            line.strip().lower()
            == "classification"
        ):

            classification_start = index

            break

    macro_sector, _ = (
        find_label_value(
            lines,
            [
                "Macro sector",
                "Macro Sector",
            ],
            classification_start,
        )
    )

    sector, _ = (
        find_label_value(
            lines,
            [
                "Sector",
            ],
            classification_start,
        )
    )

    industry, _ = (
        find_label_value(
            lines,
            [
                "Industry",
            ],
            classification_start,
        )
    )

    basic_industry, _ = (
        find_label_value(
            lines,
            [
                "Basic industry",
                "Basic Industry",
            ],
            classification_start,
        )
    )

    # --------------------------------------------------------
    # Sanity checks
    # --------------------------------------------------------

    def invalid(
        value: str,
    ) -> bool:

        if not value:
            return True

        lowered = value.lower()

        blocked = {
            "classification",
            "overview",
            "fundamentals",
            "about",
            "peers",
            "csv",
            "button",
        }

        return (
            lowered in blocked
        )

    if invalid(
        sector
    ):

        sector = ""

    if invalid(
        industry
    ):

        industry = ""

    if invalid(
        basic_industry
    ):

        basic_industry = ""

    if invalid(
        macro_sector
    ):

        macro_sector = ""

    return {
        "macro_sector":
            macro_sector,

        "sector":
            sector,

        "industry":
            industry,

        "basic_industry":
            basic_industry,
    }


# ============================================================
# FALLBACK
# ============================================================

def repair_missing_with_patternsradar(
    classification: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Use PatternsRadar for securities absent from
    the primary classification cache.

    Only canonical NSE master symbols are queried.
    """

    master = load_master()

    if master.empty:

        raise RuntimeError(
            "NSE security master is empty."
        )

    if "symbol" not in master.columns:

        raise RuntimeError(
            "NSE security master has no symbol column."
        )

    if "company_name" not in master.columns:

        master["company_name"] = ""

    master = master.copy()

    master["symbol"] = (
        master["symbol"]
        .map(normalize_symbol)
    )

    master = (
        master
        .drop_duplicates(
            subset=["symbol"],
            keep="first",
        )
    )

    classified_symbols = set(
        classification[
            "symbol"
        ]
        .map(normalize_symbol)
    )

    missing = master[
        ~master["symbol"].isin(
            classified_symbols
        )
    ].copy()

    if missing.empty:

        print()
        print(
            "No PatternsRadar fallback "
            "classification is required."
        )

        return (
            classification,
            pd.DataFrame(),
        )

    print()
    print("=" * 80)
    print(
        "PATTERNSRADAR FALLBACK"
    )
    print("=" * 80)

    print()
    print(
        f"Unresolved NSE symbols: "
        f"{len(missing):,}"
    )

    recovered_records = []

    diagnostics = []

    for position, (_, row) in enumerate(
        missing.iterrows(),
        start=1,
    ):

        symbol = normalize_symbol(
            row["symbol"]
        )

        company_name = clean_text(
            row["company_name"]
        )

        status = ""

        result = {}

        try:

            source_html = (
                fetch_patternsradar_page(
                    symbol
                )
            )

            result = (
                parse_patternsradar_classification(
                    source_html
                )
            )

            if not result.get(
                "sector"
            ):

                status = (
                    "NO_SECTOR_IN_PAGE"
                )

            else:

                status = (
                    "SUCCESS"
                )

                recovered_records.append(
                    {
                        "symbol":
                            symbol,

                        "company_name":
                            company_name,

                        "macro_sector":
                            clean_text(
                                result.get(
                                    "macro_sector",
                                    "",
                                )
                            ),

                        "sector":
                            clean_text(
                                result.get(
                                    "sector",
                                    "",
                                )
                            ),

                        "industry":
                            clean_text(
                                result.get(
                                    "industry",
                                    "",
                                )
                            ),

                        "basic_industry":
                            clean_text(
                                result.get(
                                    "basic_industry",
                                    "",
                                )
                            ),

                        "classification_source":
                            FALLBACK_SOURCE_NAME,
                    }
                )

        except Exception as exc:

            status = (
                f"ERROR_{type(exc).__name__}"
            )

            result = {
                "error":
                    str(exc)
            }

        diagnostics.append(
            {
                "symbol":
                    symbol,

                "company_name":
                    company_name,

                "status":
                    status,

                "macro_sector":
                    result.get(
                        "macro_sector",
                        "",
                    ),

                "sector":
                    result.get(
                        "sector",
                        "",
                    ),

                "industry":
                    result.get(
                        "industry",
                        "",
                    ),

                "basic_industry":
                    result.get(
                        "basic_industry",
                        "",
                    ),
            }
        )

        if (
            position == 1
            or position % 10 == 0
            or position == len(missing)
        ):

            print(
                f"[{position:,}/"
                f"{len(missing):,}] "
                f"Recovered: "
                f"{len(recovered_records):,}"
            )

        time.sleep(
            REQUEST_DELAY
        )

    # --------------------------------------------------------
    # Merge recovered
    # --------------------------------------------------------

    recovered = pd.DataFrame(
        recovered_records,
        columns=OUTPUT_COLUMNS,
    )

    diagnostic_df = pd.DataFrame(
        diagnostics
    )

    if not recovered.empty:

        classification = pd.concat(
            [
                classification,
                recovered,
            ],
            ignore_index=True,
        )

        classification = (
            classification
            .drop_duplicates(
                subset=["symbol"],
                keep="last",
            )
            .reset_index(
                drop=True
            )
        )

        save_cache(
            classification
        )

    diagnostic_df.to_csv(
        FALLBACK_REPORT_FILE,
        index=False,
        encoding="utf-8",
    )

    print()
    print(
        "PATTERNSRADAR FALLBACK RESULT"
    )

    print("-" * 80)

    print(
        f"Missing before fallback : "
        f"{len(missing):,}"
    )

    print(
        f"Recovered               : "
        f"{len(recovered):,}"
    )

    print(
        f"Still unresolved        : "
        f"{len(missing) - len(recovered):,}"
    )

    print()
    print(
        f"Fallback report:"
    )

    print(
        FALLBACK_REPORT_FILE
    )

    return (
        classification,
        diagnostic_df,
    )


# ============================================================
# CACHE SAVE
# ============================================================

def save_cache(
    dataframe: pd.DataFrame,
) -> None:
    """
    Save canonical classification cache.
    """

    dataframe = dataframe.copy()

    for column in OUTPUT_COLUMNS:

        if column not in dataframe.columns:

            dataframe[column] = ""

    dataframe = dataframe[
        OUTPUT_COLUMNS
    ]

    dataframe["symbol"] = (
        dataframe["symbol"]
        .map(normalize_symbol)
    )

    dataframe = (
        dataframe
        .drop_duplicates(
            subset=["symbol"],
            keep="last",
        )
        .sort_values(
            "symbol"
        )
        .reset_index(
            drop=True
        )
    )

    dataframe.to_csv(
        CLASSIFICATION_FILE,
        index=False,
        encoding="utf-8",
    )

    metadata = {
        "primary_source":
            PRIMARY_SOURCE_NAME,

        "primary_source_url":
            PRIMARY_SOURCE_URL,

        "fallback_source":
            FALLBACK_SOURCE_NAME,

        "fallback_source_url":
            (
                "https://patternsradar.com/"
                "s/{symbol}"
            ),

        "records":
            int(len(dataframe)),

        "updated_at":
            pd.Timestamp.now(
                tz="Asia/Kolkata"
            ).isoformat(),

        "canonical_key":
            "NSE security master symbol",

        "unresolved_are_not_guessed":
            True,
    }

    META_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# FINAL COVERAGE
# ============================================================

def print_final_coverage() -> pd.DataFrame:
    """
    Print coverage against NSE master.
    """

    classification = load_cache()

    master = load_master()

    master_symbols = set(
        master[
            "symbol"
        ]
        .map(normalize_symbol)
    )

    classified_symbols = set(
        classification[
            "symbol"
        ]
        .map(normalize_symbol)
    )

    matched = (
        master_symbols
        & classified_symbols
    )

    unresolved = (
        master_symbols
        - classified_symbols
    )

    coverage = (
        len(matched)
        / len(master_symbols)
        * 100
        if master_symbols
        else 0
    )

    print()
    print("=" * 80)
    print(
        "FINAL NSE CLASSIFICATION COVERAGE"
    )
    print("=" * 80)

    print()
    print(
        f"NSE master symbols : "
        f"{len(master_symbols):,}"
    )

    print(
        f"Classified          : "
        f"{len(matched):,}"
    )

    print(
        f"Unresolved          : "
        f"{len(unresolved):,}"
    )

    print(
        f"Coverage            : "
        f"{coverage:.2f}%"
    )

    if unresolved:

        unresolved_rows = master[
            master["symbol"]
            .map(normalize_symbol)
            .isin(unresolved)
        ][
            [
                "symbol",
                "company_name",
            ]
        ].copy()

        unresolved_rows.to_csv(
            UNMATCHED_FILE,
            index=False,
            encoding="utf-8",
        )

        print()
        print(
            f"Unresolved report:"
        )

        print(
            UNMATCHED_FILE
        )

    else:

        print()
        print(
            "100% NSE master classification "
            "coverage achieved."
        )

    return classification


# ============================================================
# LOAD CACHE
# ============================================================

def load_cache() -> pd.DataFrame:
    """
    Load canonical classification cache.
    """

    if not CLASSIFICATION_FILE.exists():

        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )

    dataframe = pd.read_csv(
        CLASSIFICATION_FILE,
        dtype=str,
    ).fillna("")

    for column in OUTPUT_COLUMNS:

        if column not in dataframe.columns:

            dataframe[column] = ""

    dataframe["symbol"] = (
        dataframe["symbol"]
        .map(normalize_symbol)
    )

    return (
        dataframe[
            OUTPUT_COLUMNS
        ]
        .drop_duplicates(
            subset=["symbol"],
            keep="last",
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 80)
    print(
        "NOVA NSE CLASSIFICATION ENGINE"
    )
    print("=" * 80)

    # --------------------------------------------------------
    # Primary build
    # --------------------------------------------------------

    classification = (
        build_primary_cache(
            force_download=False
        )
    )

    # --------------------------------------------------------
    # Secondary repair
    # --------------------------------------------------------

    (
        classification,
        fallback_report,
    ) = (
        repair_missing_with_patternsradar(
            classification
        )
    )

    # --------------------------------------------------------
    # Final coverage
    # --------------------------------------------------------

    classification = (
        print_final_coverage()
    )

    print()
    print(
        "NOVA CLASSIFICATION ENGINE COMPLETE"
    )

    print()
    print(
        f"Final cache records: "
        f"{len(classification):,}"
    )

    print()
    print(
        f"Cache:"
    )

    print(
        CLASSIFICATION_FILE
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
            "Classification engine interrupted."
        )

        raise SystemExit(1)

    except Exception as exc:

        print()
        print(
            "CLASSIFICATION ENGINE ERROR"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        raise SystemExit(1)