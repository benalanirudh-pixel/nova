"""
Nova Institutional Flow Engine
===============================

Persistent, scope-aware FII/FPI and DII cash-market flow history.

Primary source:
    NSE combined FII/FPI + DII endpoint, accepted only after the latest
    observation matches the same date in the documented Groww mirror.

Historical fallback:
    Groww-labelled secondary daily-data mirror.

Quality controls:
    - Separates combined NSE+BSE+MSEI data from NSE-only data.
    - Supports flattened and category-row NSE JSON formats.
    - Validates gross buy/sell values against reported net flows.
    - Rejects incomplete and all-zero placeholder records.
    - Stores unverified NSE candidates in a quarantine file.
    - Requires sufficient valid sessions, consistent market scope and freshness.
    - Keeps the engine analysis-only: no broker connection or orders.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from io import StringIO

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

try:
    import requests
except Exception:
    requests = None


# ===========================================================================
# PATHS AND SOURCES
# ===========================================================================

BASE_DIR = Path(__file__).resolve().parent

CACHE_DIR = BASE_DIR / "cache" / "institutional_flow"

HISTORY_FILE = CACHE_DIR / "institutional_flow_history.csv"
LATEST_FILE = CACHE_DIR / "institutional_flow_latest.csv"
LATEST_JSON_FILE = CACHE_DIR / "institutional_flow_latest.json"
META_FILE = CACHE_DIR / "institutional_flow_meta.json"
QUARANTINE_FILE = CACHE_DIR / "institutional_flow_quarantine.csv"

NSE_FII_DII_PAGE = (
    "https://www.nseindia.com/reports/fii-dii"
)

# Combined-market FII/FPI + DII activity candidate.
NSE_COMBINED_ENDPOINT = (
    "https://www.nseindia.com/api/fiidiiTradeReact"
)

# NSE-only endpoint. Never label its data as combined-market data.
NSE_ONLY_ENDPOINT = (
    "https://www.nseindia.com/api/fiidiiTradeNse"
)

# Secondary historical mirror.
SECONDARY_BASE_URL = (
    "https://chirag127.github.io/fii-dii-activity-api/data"
)

SECONDARY_LATEST_URLS = [
    f"{SECONDARY_BASE_URL}/latest.json",
    (
        "https://raw.githubusercontent.com/"
        "chirag127/fii-dii-activity-api/main/data/latest.json"
    ),
]

# The fallback URL must use a single {date} placeholder.
SECONDARY_DAY_URLS = [
    f"{SECONDARY_BASE_URL}/{{date}}.json",
    (
        "https://raw.githubusercontent.com/"
        "chirag127/fii-dii-activity-api/main/data/{date}.json"
    ),
]

SECONDARY_REFERER = (
    "https://github.com/chirag127/fii-dii-activity-api"
)

GROWW_FII_DII_URL = "https://groww.in/fii-dii-data"

COMBINED_SCOPE = "NSE_BSE_MSEI_COMBINED"
NSE_ONLY_SCOPE = "NSE_ONLY"
UNKNOWN_SCOPE = "UNKNOWN"

DEFAULT_TARGET_SESSIONS = 20
DEFAULT_SCAN_CALENDAR_DAYS = 90

# Conservative calendar-day freshness guard; not an exchange-holiday calendar.
MAX_FRESHNESS_AGE_DAYS = 4

REQUEST_DELAY_SECONDS = 0.15
HTTP_TIMEOUT_SECONDS = 20
VALIDATION_TOLERANCE_CRORE = 1.5

HISTORY_COLUMNS = [
    "date",
    "fii_buy",
    "fii_sell",
    "fii_net",
    "dii_buy",
    "dii_sell",
    "dii_net",
    "combined_net",
    "source",
    "market_scope",
    "provisional",
    "fetched_at",
]

NUMERIC_COLUMNS = [
    "fii_buy",
    "fii_sell",
    "fii_net",
    "dii_buy",
    "dii_sell",
    "dii_net",
    "combined_net",
]

FLOW_FIELDS = [
    "fii_buy",
    "fii_sell",
    "fii_net",
    "dii_buy",
    "dii_sell",
    "dii_net",
]


# ===========================================================================
# DATA MODEL
# ===========================================================================

@dataclass
class FlowRow:
    date: str

    fii_buy: float
    fii_sell: float
    fii_net: float

    dii_buy: float
    dii_sell: float
    dii_net: float

    source: str

    market_scope: str = COMBINED_SCOPE
    provisional: bool = True
    fetched_at: str = ""

    @property
    def combined_net(self) -> float:
        return round(
            self.fii_net + self.dii_net,
            2,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["combined_net"] = self.combined_net
        return result


# ===========================================================================
# HTTP HELPERS
# ===========================================================================

def _build_session():
    """Create an HTTP session suitable for NSE requests."""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_FII_DII_PAGE,
        "Connection": "keep-alive",
    }

    if curl_requests is not None:
        try:
            return curl_requests.Session(
                impersonate="chrome",
                headers=headers,
            )
        except Exception:
            pass

    if requests is not None:
        session = requests.Session()
        session.headers.update(headers)
        return session

    raise RuntimeError(
        "Install HTTP dependencies with:\n"
        "pip install curl_cffi brotli requests"
    )


def _get_json(
    session,
    url: str,
    referer: Optional[str] = None,
) -> Any:
    """Request JSON and handle incorrect content-type headers."""

    headers = (
        {"Referer": referer}
        if referer
        else {}
    )

    response = session.get(
        url,
        headers=headers,
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    status = getattr(
        response,
        "status_code",
        200,
    )

    if status != 200:
        raise RuntimeError(
            f"HTTP {status} from {url}"
        )

    try:
        return response.json()

    except Exception:
        body = getattr(
            response,
            "text",
            "",
        )

        if not body:
            raise RuntimeError(
                f"Empty response from {url}"
            )

        return json.loads(body)


def _now_iso() -> str:
    return (
        datetime.now()
        .astimezone()
        .isoformat(timespec="seconds")
    )


# ===========================================================================
# VALUE AND DATE PARSING
# ===========================================================================

def _norm_key(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").strip().lower(),
    )


def _clean_number(value: Any) -> Optional[float]:
    """Parse common financial values, including accounting-style negatives."""

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)

        return (
            number
            if math.isfinite(number)
            else None
        )

    text = str(value).strip()

    if (
        not text
        or text.lower()
        in {
            "-",
            "--",
            "na",
            "n/a",
            "null",
            "none",
        }
    ):
        return None

    accounting_negative = (
        text.startswith("(")
        and text.endswith(")")
    )

    text = (
        text
        .replace(",", "")
        .replace("₹", "")
        .replace("%", "")
        .strip("() ")
    )

    match = re.search(
        r"[-+]?\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    number = float(match.group(0))

    if accounting_negative:
        number = -abs(number)

    return (
        number
        if math.isfinite(number)
        else None
    )


def _parse_date(value: Any) -> Optional[str]:
    """Normalize dates to YYYY-MM-DD."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    formats = [
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                text,
                fmt,
            ).date().isoformat()

        except ValueError:
            continue

    try:
        parsed = pd.to_datetime(
            text,
            dayfirst=True,
            errors="raise",
        )

        return parsed.date().isoformat()

    except Exception:
        return None


def _walk_dicts(payload: Any) -> Iterable[Dict[str, Any]]:
    """Yield dictionaries from arbitrarily nested JSON."""

    if isinstance(payload, dict):
        yield payload

        for value in payload.values():
            yield from _walk_dicts(value)

    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_dicts(item)


def _field(
    record: Dict[str, Any],
    aliases: Sequence[str],
) -> Any:
    normalized = {
        _norm_key(key): value
        for key, value in record.items()
    }

    for alias in aliases:
        key = _norm_key(alias)

        if key in normalized:
            return normalized[key]

    return None


DATE_ALIASES = [
    "date",
    "tradeDate",
    "trade_date",
    "reportDate",
    "asOn",
    "businessDate",
]

# Flat NSE JSON schema.
DIRECT_ALIASES = {
    "fii_buy": [
        "fiibuy",
        "fii_buy",
        "fpi_buy",
        "fiiBuyValue",
        "foreignBuy",
        "fiigrosspurchase",
    ],
    "fii_sell": [
        "fiisell",
        "fii_sell",
        "fpi_sell",
        "fiiSellValue",
        "foreignSell",
        "fiigrosssales",
    ],
    "fii_net": [
        "fiinet",
        "fii_net",
        "fpi_net",
        "fiiNetValue",
        "foreignNet",
    ],
    "dii_buy": [
        "diibuy",
        "dii_buy",
        "diiBuyValue",
        "domesticBuy",
        "diigrosspurchase",
    ],
    "dii_sell": [
        "diisell",
        "dii_sell",
        "diiSellValue",
        "domesticSell",
        "diigrosssales",
    ],
    "dii_net": [
        "diinet",
        "dii_net",
        "diiNetValue",
        "domesticNet",
    ],
}

BUY_ALIASES = [
    "buyValue",
    "buy_value",
    "buy",
    "grossPurchaseCr",
    "gross_purchase_cr",
    "purchase",
    "purchaseValue",
]

SELL_ALIASES = [
    "sellValue",
    "sell_value",
    "sell",
    "grossSalesCr",
    "gross_sales_cr",
    "sales",
    "sellValueCr",
]

NET_ALIASES = [
    "netValue",
    "net_value",
    "net",
    "netInvestmentCr",
    "net_investment_cr",
    "netValueCr",
]

CATEGORY_ALIASES = [
    "category",
    "cat",
    "investorType",
    "clientType",
    "type",
]


def _category(record: Dict[str, Any]) -> Optional[str]:
    value = _field(
        record,
        CATEGORY_ALIASES,
    )

    if value is None:
        return None

    text = str(value).strip().upper()

    if (
        "FII" in text
        or "FPI" in text
        or "FOREIGN" in text
    ):
        return "FII"

    if (
        "DII" in text
        or "DOMESTIC" in text
    ):
        return "DII"

    return None


# ===========================================================================
# DATA VALIDATION
# ===========================================================================

def _validate_flow(
    values: Dict[str, float],
    tolerance: float = VALIDATION_TOLERANCE_CRORE,
) -> Tuple[bool, List[str]]:
    """Check gross buys, sells and net figures without silently correcting them."""

    errors: List[str] = []

    checks = [
        (
            "FII",
            "fii_buy",
            "fii_sell",
            "fii_net",
        ),
        (
            "DII",
            "dii_buy",
            "dii_sell",
            "dii_net",
        ),
    ]

    for label, buy_key, sell_key, net_key in checks:
        buy = values[buy_key]
        sell = values[sell_key]
        net = values[net_key]

        if not all(
            math.isfinite(float(value))
            for value in (buy, sell, net)
        ):
            errors.append(
                f"{label} contains non-finite values"
            )
            continue

        if buy < 0 or sell < 0:
            errors.append(
                f"{label} gross buy/sell contains a negative value"
            )

        expected = buy - sell

        if abs(expected - net) > tolerance:
            errors.append(
                f"{label} buy-sell mismatch: "
                f"expected {expected:.2f}, got {net:.2f}"
            )

    return not errors, errors


def _normalise_flow_values(
    values: Dict[str, Optional[float]],
) -> Optional[Dict[str, float]]:
    """Return complete validated values or None."""

    clean: Dict[str, float] = {}

    for key in FLOW_FIELDS:
        value = values.get(key)

        if value is None:
            return None

        clean[key] = float(value)

    valid, _ = _validate_flow(clean)

    if not valid:
        return None

    # The static mirror uses all-zero values as a possible placeholder.
    if all(
        abs(value) < 1e-9
        for value in clean.values()
    ):
        return None

    return {
        key: round(value, 2)
        for key, value in clean.items()
    }


def _make_row(
    row_date: str,
    values: Dict[str, float],
    source: str,
    scope: str,
) -> FlowRow:
    return FlowRow(
        date=row_date,
        fii_buy=values["fii_buy"],
        fii_sell=values["fii_sell"],
        fii_net=values["fii_net"],
        dii_buy=values["dii_buy"],
        dii_sell=values["dii_sell"],
        dii_net=values["dii_net"],
        source=source,
        market_scope=scope,
        provisional=True,
        fetched_at=_now_iso(),
    )


# ===========================================================================
# NSE PARSER
# ===========================================================================

def parse_nse_payload(
    payload: Any,
) -> List[FlowRow]:
    """
    Parse either:
      A. Flat records with fiibuy/fiisell/fiinet and dii* fields.
      B. Separate FII/FPI and DII category records.

    Returned records are candidates until cross-checked against the secondary
    source for the same date. They are deliberately not assigned combined scope
    inside this parser.
    """

    dicts = list(_walk_dicts(payload))
    found: Dict[str, FlowRow] = {}

    # Shape A: one record per date with FII and DII fields.
    for record in dicts:
        row_date = _parse_date(
            _field(
                record,
                DATE_ALIASES,
            )
        )

        if not row_date:
            continue

        raw_values = {
            key: _clean_number(
                _field(record, aliases)
            )
            for key, aliases in DIRECT_ALIASES.items()
        }

        if (
            raw_values["fii_net"] is None
            and raw_values["fii_buy"] is not None
            and raw_values["fii_sell"] is not None
        ):
            raw_values["fii_net"] = (
                raw_values["fii_buy"]
                - raw_values["fii_sell"]
            )

        if (
            raw_values["dii_net"] is None
            and raw_values["dii_buy"] is not None
            and raw_values["dii_sell"] is not None
        ):
            raw_values["dii_net"] = (
                raw_values["dii_buy"]
                - raw_values["dii_sell"]
            )

        values = _normalise_flow_values(
            raw_values
        )

        if values:
            found[row_date] = _make_row(
                row_date,
                values,
                "NSE_CANDIDATE_UNVERIFIED",
                UNKNOWN_SCOPE,
            )

    if found:
        return sorted(
            found.values(),
            key=lambda row: row.date,
        )

    # Shape B: separate FII/FPI and DII category rows.
    grouped: Dict[
        str,
        Dict[str, Dict[str, float]],
    ] = {}

    for record in dicts:
        row_date = _parse_date(
            _field(
                record,
                DATE_ALIASES,
            )
        )

        category = _category(record)

        if not row_date or not category:
            continue

        buy = _clean_number(
            _field(
                record,
                BUY_ALIASES,
            )
        )

        sell = _clean_number(
            _field(
                record,
                SELL_ALIASES,
            )
        )

        net = _clean_number(
            _field(
                record,
                NET_ALIASES,
            )
        )

        if buy is None or sell is None:
            continue

        if net is None:
            net = buy - sell

        grouped.setdefault(
            row_date,
            {},
        )[category] = {
            "buy": buy,
            "sell": sell,
            "net": net,
        }

    for row_date, pair in grouped.items():
        if "FII" not in pair or "DII" not in pair:
            continue

        raw = {
            "fii_buy": pair["FII"]["buy"],
            "fii_sell": pair["FII"]["sell"],
            "fii_net": pair["FII"]["net"],
            "dii_buy": pair["DII"]["buy"],
            "dii_sell": pair["DII"]["sell"],
            "dii_net": pair["DII"]["net"],
        }

        values = _normalise_flow_values(raw)

        if values:
            found[row_date] = _make_row(
                row_date,
                values,
                "NSE_CANDIDATE_UNVERIFIED",
                UNKNOWN_SCOPE,
            )

    if not found:
        raise RuntimeError(
            "NSE response did not contain a complete, valid "
            "FII/FPI + DII cash-flow row."
        )

    return sorted(
        found.values(),
        key=lambda row: row.date,
    )


# ===========================================================================
# SECONDARY SOURCE PARSER
# ===========================================================================

def _parse_secondary(
    payload: Any,
    expected_date: Optional[str] = None,
) -> Optional[FlowRow]:
    """
    Parse the static mirror's Groww-sourced equity cash-flow payload.

    Source labels such as 'placeholder' and unverified source types are rejected.
    Derivatives fields are not used here.
    """

    if not isinstance(payload, dict):
        return None

    source_label = str(
        payload.get(
            "source",
            "unknown",
        )
    ).strip().lower()

    row_date = _parse_date(
        payload.get("date")
    )

    if not row_date:
        return None

    if expected_date and row_date != expected_date:
        return None

    if source_label != "groww":
        return None

    equity = payload.get("equity")

    if not isinstance(equity, dict):
        return None

    raw_values = {
        key: _clean_number(
            equity.get(key)
        )
        for key in FLOW_FIELDS
    }

    values = _normalise_flow_values(
        raw_values
    )

    if not values:
        return None

    return _make_row(
        row_date,
        values,
        "SECONDARY_DAILY_MIRROR:groww",
        COMBINED_SCOPE,
    )


def _rows_match(
    a: FlowRow,
    b: FlowRow,
    tolerance: float = VALIDATION_TOLERANCE_CRORE,
) -> bool:
    """Require identical dates and matching gross/net amounts."""

    if a.date != b.date:
        return False

    return all(
        abs(
            float(getattr(a, key))
            - float(getattr(b, key))
        ) <= tolerance
        for key in FLOW_FIELDS
    )


# ===========================================================================
# SOURCE FETCHING
# ===========================================================================

def fetch_nse_rows() -> List[FlowRow]:
    """Fetch and parse NSE's combined-market endpoint candidate."""

    session = _build_session()

    # Prime cookies before querying the NSE JSON endpoint.
    try:
        session.get(
            NSE_FII_DII_PAGE,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except Exception:
        pass

    payload = _get_json(
        session,
        NSE_COMBINED_ENDPOINT,
        referer=NSE_FII_DII_PAGE,
    )

    return parse_nse_payload(
        payload
    )


def _fetch_secondary_url_list(
    urls: Sequence[str],
    referer: str,
) -> Any:
    session = _build_session()
    last_error: Optional[Exception] = None

    for url in urls:
        try:
            return _get_json(
                session,
                url,
                referer=referer,
            )

        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error

    raise RuntimeError(
        "No secondary URLs were configured."
    )



def fetch_groww_html_rows() -> List[FlowRow]:
    """
    Fetch Groww's dated FII/DII table once and validate every extracted row.
    The page's published dates are used as-is; missing dates are not invented.
    """
    session = _build_session()
    response = session.get(
        GROWW_FII_DII_URL,
        headers={
            "Referer": GROWW_FII_DII_URL,
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    status = getattr(response, "status_code", 200)
    if status != 200:
        raise RuntimeError(f"HTTP {status} from Groww FII/DII page")

    html = getattr(response, "text", "")
    if not html or len(html) < 1000:
        raise RuntimeError("Groww returned an empty or incomplete HTML page")

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError("No HTML tables found on Groww's FII/DII page")

    rows_by_date: Dict[str, FlowRow] = {}

    for table in tables:
        if table.empty:
            continue

        columns: Dict[str, Any] = {}

        for column in table.columns:
            parts = tuple(column) if isinstance(column, tuple) else (column,)
            normalized = [_norm_key(part) for part in parts]
            group = normalized[0] if normalized else ""
            label = normalized[-1] if normalized else ""

            if "date" in normalized:
                columns["date"] = column
                continue

            if "fii" in group or "fpi" in group:
                prefix = "fii"
            elif "dii" in group:
                prefix = "dii"
            else:
                continue

            if "grossbuy" in label:
                field = f"{prefix}_buy"
            elif "grosssell" in label:
                field = f"{prefix}_sell"
            elif "netbuysell" in label or "net" in label:
                field = f"{prefix}_net"
            else:
                continue

            columns[field] = column

        required = {
            "date", "fii_buy", "fii_sell", "fii_net",
            "dii_buy", "dii_sell", "dii_net",
        }
        if not required.issubset(columns):
            continue

        for _, record in table.iterrows():
            row_date = _parse_date(record[columns["date"]])
            if not row_date:
                continue

            try:
                parsed_date = date.fromisoformat(row_date)
            except ValueError:
                continue

            if parsed_date > date.today():
                continue

            raw_values = {
                field: _clean_number(record[columns[field]])
                for field in FLOW_FIELDS
            }
            values = _normalise_flow_values(raw_values)
            if not values:
                continue

            row = _make_row(
                row_date,
                values,
                "GROWW_HTML:groww",
                COMBINED_SCOPE,
            )

            existing = rows_by_date.get(row_date)
            if existing is not None and not _rows_match(existing, row):
                # Conflicting duplicate records must not be silently accepted.
                rows_by_date.pop(row_date, None)
                continue

            rows_by_date[row_date] = row

    if not rows_by_date:
        raise RuntimeError(
            "Groww HTML loaded, but no complete, valid FII/DII rows were extracted"
        )

    return sorted(rows_by_date.values(), key=lambda row: row.date)


def fetch_secondary_archive_day(day: date) -> Optional[FlowRow]:
    """Fetch one dated JSON archive row without refetching the Groww HTML page."""
    urls = [
        url.format(date=day.isoformat())
        for url in SECONDARY_DAY_URLS
    ]

    try:
        payload = _fetch_secondary_url_list(urls, SECONDARY_REFERER)
        return _parse_secondary(payload, expected_date=day.isoformat())
    except Exception:
        return None


def fetch_secondary_latest() -> Optional[FlowRow]:
    """Choose the newest valid row from the mirror and Groww HTML."""
    candidates: List[FlowRow] = []

    try:
        payload = _fetch_secondary_url_list(
            SECONDARY_LATEST_URLS,
            SECONDARY_REFERER,
        )
        row = _parse_secondary(payload)
        if row:
            candidates.append(row)
    except Exception:
        pass

    try:
        candidates.extend(fetch_groww_html_rows())
    except Exception:
        pass

    if not candidates:
        return None

    # For duplicate dates, prefer the direct Groww HTML row.
    candidates.sort(
        key=lambda row: (
            row.date,
            row.source == "GROWW_HTML:groww",
        )
    )
    return candidates[-1]


def fetch_secondary_day(day: date) -> Optional[FlowRow]:
    """Cross-check a date against Groww HTML, then the dated JSON archive."""
    expected_date = day.isoformat()

    try:
        for row in fetch_groww_html_rows():
            if row.date == expected_date:
                return row
    except Exception:
        pass

    return fetch_secondary_archive_day(day)


# ===========================================================================
# PERSISTENCE AND MIGRATION
# ===========================================================================

def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        columns=HISTORY_COLUMNS
    )


def load_history() -> pd.DataFrame:
    """
    Load previous history and quarantine legacy NSE-only records.

    Old NSE_PRIMARY rows are not relabelled as combined-market figures.
    """

    ensure_cache_dir()

    if not HISTORY_FILE.exists():
        return _empty_history()

    try:
        df = pd.read_csv(
            HISTORY_FILE
        )

    except Exception as exc:
        raise RuntimeError(
            f"Cannot read {HISTORY_FILE}. "
            "The source file was preserved. Inspect or repair it before "
            f"rerunning. Details: {exc}"
        ) from exc

    for col in HISTORY_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[
        HISTORY_COLUMNS
    ].copy()

    df["date"] = (
        pd.to_datetime(
            df["date"],
            errors="coerce",
        )
        .dt.date
        .astype("string")
    )

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    old_sources = (
        df["source"]
        .fillna("")
        .astype(str)
    )

    legacy = old_sources.isin(
        {
            "NSE_PRIMARY",
            "NSE_PRIMARY_UNVERIFIED",
            "NSE_PRIMARY_COMBINED",
        }
    )

    df.loc[
        legacy,
        "source",
    ] = "LEGACY_NSE_ONLY_QUARANTINED"

    df.loc[
        legacy,
        "market_scope",
    ] = NSE_ONLY_SCOPE

    missing_scope = (
        df["market_scope"].isna()
        | df["market_scope"]
        .astype(str)
        .str.strip()
        .eq("")
    )

    is_groww = old_sources.str.startswith((
        "SECONDARY_DAILY_MIRROR:groww",
        "GROWW_HTML:groww",
    ))

    df.loc[
        missing_scope & is_groww,
        "market_scope",
    ] = COMBINED_SCOPE

    df.loc[
        missing_scope & ~is_groww,
        "market_scope",
    ] = UNKNOWN_SCOPE

    df["combined_net"] = (
        df["fii_net"] + df["dii_net"]
    ).round(2)

    df["provisional"] = df["provisional"].map(
        lambda value: (
            True
            if pd.isna(value)
            else str(value).strip().lower()
            in {"true", "1", "yes", "y"}
        )
    )

    df = df.dropna(
        subset=["date"]
    )

    df = df.drop_duplicates(
        subset=["date", "market_scope"],
        keep="last",
    )

    return (
        df.sort_values(
            ["date", "market_scope"]
        )
        .reset_index(drop=True)
    )


def _source_priority(source: Any) -> int:
    value = str(source or "")

    if value == "NSE_PRIMARY_COMBINED_VERIFIED":
        return 3

    if value.startswith((
        "SECONDARY_DAILY_MIRROR:groww",
        "GROWW_HTML:groww",
    )):
        return 2

    return 0


def upsert_rows(
    history: pd.DataFrame,
    rows: Sequence[FlowRow],
) -> pd.DataFrame:
    """Insert/update rows while retaining one row per date and market scope."""

    incoming = pd.DataFrame(
        [
            row.to_dict()
            for row in rows
        ]
    )

    if incoming.empty:
        return history

    for col in HISTORY_COLUMNS:
        if col not in incoming.columns:
            incoming[col] = None

    incoming = incoming[
        HISTORY_COLUMNS
    ]

    combined = pd.concat(
        [
            history,
            incoming,
        ],
        ignore_index=True,
    )

    combined["date"] = (
        pd.to_datetime(
            combined["date"],
            errors="coerce",
        )
        .dt.date
        .astype("string")
    )

    for col in NUMERIC_COLUMNS:
        combined[col] = pd.to_numeric(
            combined[col],
            errors="coerce",
        )

    combined["combined_net"] = (
        combined["fii_net"] + combined["dii_net"]
    ).round(2)

    combined["_priority"] = combined[
        "source"
    ].map(_source_priority)

    combined["_order"] = range(
        len(combined)
    )

    combined = (
        combined.sort_values(
            [
                "date",
                "market_scope",
                "_priority",
                "_order",
            ],
            kind="mergesort",
        )
        .drop_duplicates(
            subset=[
                "date",
                "market_scope",
            ],
            keep="last",
        )
        .drop(
            columns=[
                "_priority",
                "_order",
            ]
        )
        .dropna(
            subset=["date"]
        )
        .sort_values(
            ["date", "market_scope"]
        )
        .reset_index(drop=True)
    )

    return combined


def save_history(
    history: pd.DataFrame,
) -> None:
    ensure_cache_dir()

    history[
        HISTORY_COLUMNS
    ].to_csv(
        HISTORY_FILE,
        index=False,
    )


def save_latest(
    row: FlowRow,
) -> None:
    ensure_cache_dir()

    pd.DataFrame(
        [
            row.to_dict()
        ]
    )[HISTORY_COLUMNS].to_csv(
        LATEST_FILE,
        index=False,
    )

    LATEST_JSON_FILE.write_text(
        json.dumps(
            row.to_dict(),
            indent=2,
        ),
        encoding="utf-8",
    )


def save_quarantine(
    rows: Sequence[FlowRow],
    reason: str,
) -> None:
    """Persist unverified NSE candidates separately from usable history."""

    if not rows:
        return

    ensure_cache_dir()
    items = []

    for row in rows:
        item = row.to_dict()

        item["source"] = (
            "NSE_CANDIDATE_QUARANTINED"
        )

        item["market_scope"] = UNKNOWN_SCOPE
        item["quarantine_reason"] = reason

        items.append(item)

    new_df = pd.DataFrame(items)

    if QUARANTINE_FILE.exists():
        try:
            old_df = pd.read_csv(
                QUARANTINE_FILE
            )

        except Exception:
            old_df = pd.DataFrame()

        combined = pd.concat(
            [
                old_df,
                new_df,
            ],
            ignore_index=True,
        )

        if "date" in combined.columns:
            combined = combined.drop_duplicates(
                subset=[
                    "date",
                    "source",
                ],
                keep="last",
            )

    else:
        combined = new_df

    combined.to_csv(
        QUARANTINE_FILE,
        index=False,
    )


# ===========================================================================
# METRICS
# ===========================================================================

def _sign_streak(
    values_newest_first: Sequence[float],
) -> Tuple[str, int]:
    if not values_newest_first:
        return "UNKNOWN", 0

    first = float(
        values_newest_first[0]
    )

    target = (
        "BUYING"
        if first > 0
        else "SELLING"
        if first < 0
        else "FLAT"
    )

    count = 0

    for value in values_newest_first:
        direction = (
            "BUYING"
            if value > 0
            else "SELLING"
            if value < 0
            else "FLAT"
        )

        if direction != target:
            break

        count += 1

    return target, count


def _sum_last(
    df: pd.DataFrame,
    column: str,
    n: int,
) -> Optional[float]:
    if len(df) < n:
        return None

    return round(
        float(
            df[column].tail(n).sum()
        ),
        2,
    )


def _mean_last(
    df: pd.DataFrame,
    column: str,
    n: int,
) -> Optional[float]:
    if len(df) < n:
        return None

    return round(
        float(
            df[column].tail(n).mean()
        ),
        2,
    )


def _primary_coverage_summary(
    primary_count: Any,
    target_sessions: Any,
) -> Dict[str, Any]:
    """Turn the measured NSE-primary session count into an honest
    coverage ratio and a clearly-labelled runway estimate.

    NSE serves only the latest session per call, so full primary
    verification is reached at roughly one promoted session per trading
    day. The estimate below assumes that cadence; it is an estimate, not
    a measured value, and is labelled as such in the note.
    """
    try:
        primary = int(primary_count)
    except (TypeError, ValueError):
        primary = 0

    try:
        target = int(target_sessions)
    except (TypeError, ValueError):
        target = 0

    if target <= 0:
        return {
            "primary_coverage_ratio": None,
            "trading_days_to_full_primary_estimate": 0,
            "primary_coverage_note": (
                "NSE-primary coverage unknown (no target window)."
            ),
        }

    primary = max(0, primary)
    primary = min(primary, target)

    ratio = round(primary / target, 4)
    remaining = target - primary

    if remaining == 0:
        note = (
            f"Target window is fully NSE-primary verified "
            f"({primary}/{target})."
        )
    elif primary == 0:
        note = (
            f"No NSE-primary sessions verified yet; {remaining} more "
            f"trading day(s) estimated to reach full primary."
        )
    else:
        note = (
            f"{primary}/{target} target sessions are NSE-primary; "
            f"{remaining} more trading day(s) estimated to reach full "
            f"primary (assumes ~1 primary session promoted per day)."
        )

    return {
        "primary_coverage_ratio": ratio,
        "trading_days_to_full_primary_estimate": remaining,
        "primary_coverage_note": note,
    }



def calculate_metrics(
    history: pd.DataFrame,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
) -> Dict[str, Any]:
    """Calculate metrics from the combined-market history only."""

    empty = {
        "history_quality": "NO_HISTORY",
        "history_sessions": 0,
        "target_sessions": target_sessions,
        "latest_date": None,
        "oldest_date": None,
        "market_scope": COMBINED_SCOPE,
        "scope_consistent": False,
        "invalid_rows": 0,
        "data_ready_for_market_lab": False,
        "flow_unit": "INR crore",
        "source_quality": "NO_HISTORY",
        "primary_source_sessions_in_target_window": 0,
        "non_primary_sessions_in_target_window": 0,
        "primary_source_verified_for_target_window": False,
        "flow_regime": "INSUFFICIENT_HISTORY",
    }

    if history.empty:
        return empty

    all_rows = history.copy()

    all_rows["market_scope"] = (
        all_rows["market_scope"]
        .fillna(UNKNOWN_SCOPE)
        .astype(str)
    )

    scopes_in_store = sorted(
        set(all_rows["market_scope"].tolist())
    )

    scope_df = all_rows[
        all_rows["market_scope"] == COMBINED_SCOPE
    ].copy()

    if scope_df.empty:
        result = dict(empty)

        result.update(
            {
                "history_quality": (
                    "NO_COMBINED_SCOPE_HISTORY"
                ),
                "scopes_in_store": scopes_in_store,
                "rows_outside_target_scope": int(
                    len(all_rows)
                ),
            }
        )

        return result

    scope_df["date"] = (
        scope_df["date"].astype(str)
    )

    scope_df = (
        scope_df.sort_values("date")
        .drop_duplicates(
            subset=["date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    bad_indexes: List[int] = []

    for index, row in scope_df.iterrows():
        try:
            values = {
                key: float(row[key])
                for key in FLOW_FIELDS
            }

            valid = (
                all(
                    math.isfinite(value)
                    for value in values.values()
                )
                and _validate_flow(values)[0]
                and not all(
                    abs(value) < 1e-9
                    for value in values.values()
                )
            )

        except (
            TypeError,
            ValueError,
            KeyError,
        ):
            valid = False

        if not valid:
            bad_indexes.append(index)

    valid_df = (
        scope_df.drop(
            index=bad_indexes
        )
        .copy()
        .reset_index(drop=True)
    )

    sessions = len(valid_df)

    if valid_df.empty:
        result = dict(empty)

        result.update(
            {
                "history_quality": (
                    "INVALID_COMBINED_SCOPE_ROWS"
                ),
                "scopes_in_store": scopes_in_store,
                "rows_outside_target_scope": int(
                    len(all_rows) - len(scope_df)
                ),
                "invalid_rows": len(bad_indexes),
            }
        )

        return result

    valid_df["combined_net"] = (
        valid_df["fii_net"] + valid_df["dii_net"]
    ).round(2)

    fii_direction, fii_streak = _sign_streak(
        list(
            reversed(
                valid_df["fii_net"]
                .astype(float)
                .tolist()
            )
        )
    )

    dii_direction, dii_streak = _sign_streak(
        list(
            reversed(
                valid_df["dii_net"]
                .astype(float)
                .tolist()
            )
        )
    )

    metrics: Dict[str, Any] = {
        "history_quality": (
            "COMPLETE"
            if sessions >= target_sessions and not bad_indexes
            else "INSUFFICIENT_HISTORY"
        ),

        "history_sessions": sessions,
        "target_sessions": target_sessions,

        "latest_date": str(
            valid_df["date"].iloc[-1]
        ),

        "oldest_date": str(
            valid_df["date"].iloc[0]
        ),

        "latest_source": str(
            valid_df["source"].iloc[-1]
        ),

        "market_scope": COMBINED_SCOPE,

        "scope_consistent": bool(
            (
                valid_df["market_scope"]
                == COMBINED_SCOPE
            ).all()
        ),

        "scopes_in_store": scopes_in_store,

        "rows_outside_target_scope": int(
            len(all_rows) - len(scope_df)
        ),

        "invalid_rows": len(bad_indexes),

        "fii_streak_direction": fii_direction,
        "fii_streak_days": fii_streak,

        "dii_streak_direction": dii_direction,
        "dii_streak_days": dii_streak,
    }

    for n in (5, 10, 20):
        fii_total = _sum_last(
            valid_df,
            "fii_net",
            n,
        )

        dii_total = _sum_last(
            valid_df,
            "dii_net",
            n,
        )

        metrics[f"fii_{n}d"] = fii_total
        metrics[f"dii_{n}d"] = dii_total

        metrics[f"combined_{n}d"] = _sum_last(
            valid_df,
            "combined_net",
            n,
        )

        metrics[f"fii_avg_{n}d"] = _mean_last(
            valid_df,
            "fii_net",
            n,
        )

        metrics[f"dii_avg_{n}d"] = _mean_last(
            valid_df,
            "dii_net",
            n,
        )

        metrics[f"flow_divergence_{n}d"] = (
            round(
                fii_total - dii_total,
                2,
            )
            if fii_total is not None
            and dii_total is not None
            else None
        )

    fii20 = metrics.get("fii_20d")
    dii20 = metrics.get("dii_20d")

    if fii20 is None or dii20 is None:
        regime = "INSUFFICIENT_HISTORY"

    elif fii20 < 0 < dii20:
        regime = (
            "FII_SELLING_DII_ABSORPTION"
            if abs(dii20) >= abs(fii20)
            else "FII_SELLING_DII_SUPPORT_WEAK"
        )

    elif fii20 > 0 > dii20:
        regime = "FII_BUYING_DII_DISTRIBUTION"

    elif fii20 > 0 and dii20 > 0:
        regime = "BROAD_INSTITUTIONAL_BUYING"

    elif fii20 < 0 and dii20 < 0:
        regime = "BROAD_INSTITUTIONAL_SELLING"

    else:
        regime = "MIXED_FLAT"

    metrics["flow_regime"] = regime

    metrics["source_counts"] = {
        str(key): int(value)
        for key, value in (
            valid_df["source"]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    metrics["primary_combined_sessions"] = int(
        valid_df["source"]
        .eq("NSE_PRIMARY_COMBINED_VERIFIED")
        .sum()
    )

    metrics["secondary_sessions"] = int(
        valid_df["source"]
        .astype(str)
        .str.startswith((
            "SECONDARY_DAILY_MIRROR:",
            "GROWW_HTML:",
        ))
        .sum()
    )

    # --------------------------------------------------------
    # SOURCE QUALITY FOR THE TARGET HISTORY WINDOW
    # --------------------------------------------------------

    target_window = valid_df.tail(
        target_sessions
    ).copy()

    target_sources = (
        target_window["source"]
        .fillna("")
        .astype(str)
    )

    primary_mask = target_sources.eq(
        "NSE_PRIMARY_COMBINED_VERIFIED"
    )

    primary_count = int(
        primary_mask.sum()
    )

    non_primary_count = int(
        (~primary_mask).sum()
    )

    primary_window_verified = bool(
        len(target_window) >= target_sessions
        and len(target_window) > 0
        and primary_mask.all()
    )

    if len(target_window) < target_sessions:
        source_quality = "INSUFFICIENT_TARGET_WINDOW"

    elif primary_window_verified:
        source_quality = "PRIMARY_ONLY_TARGET_WINDOW"

    elif primary_count > 0:
        source_quality = "MIXED_SOURCE_TARGET_WINDOW"

    else:
        source_quality = "SECONDARY_ONLY_TARGET_WINDOW"

    metrics["flow_unit"] = "INR crore"

    metrics["primary_source_sessions_in_target_window"] = (
        primary_count
    )

    metrics["non_primary_sessions_in_target_window"] = (
        non_primary_count
    )

    metrics["primary_source_verified_for_target_window"] = (
        primary_window_verified
    )

    metrics["source_quality"] = source_quality

    metrics.update(
        _primary_coverage_summary(
            primary_count,
            target_sessions,
        )
    )

    metrics["history_complete_for_5d"] = (
        sessions >= 5 and not bad_indexes
    )

    metrics["history_complete_for_10d"] = (
        sessions >= 10 and not bad_indexes
    )

    metrics["history_complete_for_20d"] = (
        sessions >= 20 and not bad_indexes
    )

    # Freshness is based on the newest valid accepted combined-scope session.
    latest_session_age_days = None

    try:
        latest_session = date.fromisoformat(
            str(valid_df["date"].iloc[-1])
        )
        latest_session_age_days = (
            date.today() - latest_session
        ).days

    except (TypeError, ValueError, IndexError):
        latest_session_age_days = None

    history_fresh = bool(
        latest_session_age_days is not None
        and 0 <= latest_session_age_days <= MAX_FRESHNESS_AGE_DAYS
    )

    metrics["latest_session_age_calendar_days"] = (
        latest_session_age_days
    )
    metrics["freshness_max_calendar_days"] = (
        MAX_FRESHNESS_AGE_DAYS
    )
    metrics["history_fresh"] = history_fresh

    # Fail closed: enough sessions, no invalid rows, consistent scope,
    # unique dates, and fresh latest accepted session are all required.
    metrics["data_ready_for_market_lab"] = bool(
        sessions >= target_sessions
        and not bad_indexes
        and metrics["scope_consistent"]
        and valid_df["date"].nunique() == len(valid_df)
        and history_fresh
    )

    if not history_fresh:
        metrics["history_quality"] = "STALE_DATA"

    elif metrics["data_ready_for_market_lab"]:
        metrics["history_quality"] = "COMPLETE"

    elif bad_indexes:
        metrics["history_quality"] = "INVALID_ROWS"

    else:
        metrics["history_quality"] = "INSUFFICIENT_HISTORY"

    return metrics


# ===========================================================================
# HISTORICAL BACKFILL
# ===========================================================================


def backfill_history(
    history: pd.DataFrame,
    *,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
    scan_calendar_days: int = DEFAULT_SCAN_CALENDAR_DAYS,
    latest_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Refresh recent sessions from Groww HTML, then the dated JSON archive."""
    del latest_date

    if not history.empty:
        combined = history[
            history["market_scope"].astype(str) == COMBINED_SCOPE
        ].copy()
    else:
        combined = pd.DataFrame()

    valid_dates = set()
    if not combined.empty:
        for _, stored in combined.iterrows():
            try:
                values = {key: float(stored[key]) for key in FLOW_FIELDS}
                valid = (
                    all(math.isfinite(value) for value in values.values())
                    and _validate_flow(values)[0]
                    and not all(abs(value) < 1e-9 for value in values.values())
                )
                parsed_day = date.fromisoformat(str(stored["date"]))
                if valid and parsed_day <= date.today():
                    valid_dates.add(parsed_day.isoformat())
            except (TypeError, ValueError, KeyError):
                continue

    today = date.today()
    attempted = 0
    added = 0
    skipped = 0

    # One page request supplies all available Groww table sessions.
    groww_rows: Dict[str, FlowRow] = {}
    groww_error = None
    try:
        groww_rows = {
            row.date: row for row in fetch_groww_html_rows()
        }
    except Exception as exc:
        groww_error = f"{type(exc).__name__}: {exc}"

    for offset in range(scan_calendar_days + 1):
        latest_valid_date = max(valid_dates) if valid_dates else None
        latest_age = (
            (today - date.fromisoformat(latest_valid_date)).days
            if latest_valid_date else None
        )
        fresh_enough = (
            latest_age is not None
            and 0 <= latest_age <= MAX_FRESHNESS_AGE_DAYS
        )

        if len(valid_dates) >= target_sessions and fresh_enough:
            break

        day = today - timedelta(days=offset)
        day_text = day.isoformat()

        if day_text in valid_dates:
            skipped += 1
            continue

        attempted += 1
        row = groww_rows.get(day_text)

        if row is None:
            row = fetch_secondary_archive_day(day)

        if row is None:
            continue

        history = upsert_rows(history, [row])
        valid_dates.add(row.date)
        added += 1

        if REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    latest_valid_date = max(valid_dates) if valid_dates else None
    latest_age = (
        (today - date.fromisoformat(latest_valid_date)).days
        if latest_valid_date else None
    )
    fresh_enough = (
        latest_age is not None
        and 0 <= latest_age <= MAX_FRESHNESS_AGE_DAYS
    )

    return history, {
        "target_sessions": target_sessions,
        "attempted_calendar_days": attempted,
        "added_sessions": added,
        "skipped_existing": skipped,
        "latest_valid_date": latest_valid_date,
        "latest_age_calendar_days": latest_age,
        "freshness_max_calendar_days": MAX_FRESHNESS_AGE_DAYS,
        "freshness_satisfied": fresh_enough,
        "groww_html_rows": len(groww_rows),
        "groww_html_error": groww_error,
    }


# ===========================================================================
# MAIN ENGINE
# ===========================================================================

def get_institutional_flow(
    *,
    target_sessions: int = DEFAULT_TARGET_SESSIONS,
    save: bool = True,
    backfill: bool = True,
    scan_calendar_days: int = DEFAULT_SCAN_CALENDAR_DAYS,
) -> Dict[str, Any]:
    """Fetch, validate, persist and summarize institutional cash flows."""

    history = load_history()

    primary_rows: List[FlowRow] = []
    primary_error: Optional[str] = None
    secondary_latest: Optional[FlowRow] = None
    latest_row: Optional[FlowRow] = None
    primary_verified = False

    # 1. Fetch the official NSE combined-endpoint candidate history.
    try:
        primary_rows = fetch_nse_rows()

    except Exception as exc:
        primary_error = (
            f"NSE combined endpoint fetch/parse failed: {exc}"
        )

    # 2. Fetch same-source-family secondary cross-check.
    secondary_latest = fetch_secondary_latest()

    primary_latest = (
        primary_rows[-1]
        if primary_rows
        else None
    )

    crosscheck_row = secondary_latest

    # Require the same trade date for comparison.
    if primary_latest and (
        crosscheck_row is None
        or crosscheck_row.date != primary_latest.date
    ):
        crosscheck_row = fetch_secondary_day(
            date.fromisoformat(
                primary_latest.date
            )
        )

    verified_rows: List[FlowRow] = []

    if (
        primary_latest
        and crosscheck_row
        and _rows_match(
            primary_latest,
            crosscheck_row,
        )
    ):
        primary_verified = True

        # The source is accepted for combined scope only after the same-day
        # cross-check matches its gross and net FII/DII figures.
        for row in primary_rows:
            verified_rows.append(
                FlowRow(
                    date=row.date,
                    fii_buy=row.fii_buy,
                    fii_sell=row.fii_sell,
                    fii_net=row.fii_net,
                    dii_buy=row.dii_buy,
                    dii_sell=row.dii_sell,
                    dii_net=row.dii_net,
                    source="NSE_PRIMARY_COMBINED_VERIFIED",
                    market_scope=COMBINED_SCOPE,
                    provisional=True,
                    fetched_at=row.fetched_at,
                )
            )

        history = upsert_rows(
            history,
            verified_rows,
        )

        latest_row = verified_rows[-1]

    else:
        if primary_rows:
            reason = (
                "NSE candidate could not be cross-checked against Groww "
                "on the same date; the data was not assigned combined-market scope."
            )

            save_quarantine(
                primary_rows,
                reason,
            )

            primary_error = (
                reason
                if not primary_error
                else f"{primary_error}; {reason}"
            )

        # The secondary row is explicitly labelled. An unverified NSE
        # candidate is never silently accepted as combined-market data.
        if secondary_latest:
            latest_row = secondary_latest

            history = upsert_rows(
                history,
                [secondary_latest],
            )

    backfill_info = {
        "target_sessions": target_sessions,
        "attempted_calendar_days": 0,
        "added_sessions": 0,
        "skipped_existing": 0,
        "valid_sessions_seen_newest_first": 0,
        "scan_complete": False,
        "source_errors": [],
    }

    if backfill:
        history, backfill_info = backfill_history(
            history,
            target_sessions=target_sessions,
            scan_calendar_days=scan_calendar_days,
            latest_date=(
                latest_row.date
                if latest_row is not None
                else None
            ),
        )

    metrics = calculate_metrics(
        history,
        target_sessions=target_sessions,
    )

    # Refresh the output snapshot after backfill from the newest valid accepted
    # combined-scope row, not from a potentially stale pre-backfill candidate.
    metrics_latest_date = metrics.get("latest_date")

    if metrics_latest_date and not history.empty:
        latest_candidates = history[
            (
                history["market_scope"].astype(str)
                == COMBINED_SCOPE
            )
            & (
                history["date"].astype(str)
                == str(metrics_latest_date)
            )
        ].copy()

        if not latest_candidates.empty:
            latest_record = latest_candidates.iloc[-1]

            provisional_value = latest_record.get(
                "provisional",
                True,
            )

            if pd.isna(provisional_value):
                provisional = True
            elif isinstance(provisional_value, bool):
                provisional = provisional_value
            else:
                provisional = (
                    str(provisional_value).strip().lower()
                    in {"true", "1", "yes", "y"}
                )

            latest_row = FlowRow(
                date=str(latest_record["date"]),
                fii_buy=float(latest_record["fii_buy"]),
                fii_sell=float(latest_record["fii_sell"]),
                fii_net=float(latest_record["fii_net"]),
                dii_buy=float(latest_record["dii_buy"]),
                dii_sell=float(latest_record["dii_sell"]),
                dii_net=float(latest_record["dii_net"]),
                source=str(latest_record["source"]),
                market_scope=str(
                    latest_record["market_scope"]
                ),
                provisional=provisional,
                fetched_at=str(
                    latest_record.get("fetched_at", "")
                ),
            )

    if save:
        save_history(history)

        if latest_row is not None:
            save_latest(latest_row)

    result = {
        "ok": (
            latest_row is not None
            or not history.empty
        ),

        "primary_candidate_fetch_ok": bool(
            primary_rows
        ),

        "primary_fetch_ok": primary_verified,
        "primary_scope_match": primary_verified,
        "primary_error": primary_error,

        "snapshot": (
            latest_row.to_dict()
            if latest_row
            else None
        ),

        "history": history.to_dict(
            orient="records"
        ),

        "metrics": metrics,
        "backfill": backfill_info,

        "source_policy": {
            "target_scope": COMBINED_SCOPE,
            "primary_endpoint": NSE_COMBINED_ENDPOINT,
            "primary_requires_same_date_crosscheck": True,
            "nse_only_endpoint_quarantined": NSE_ONLY_ENDPOINT,
            "historical_backfill": (
                "Groww HTML table plus Groww-labelled dated JSON archive"
            ),
            "provisional_data": True,
        },
    }

    if save:
        ensure_cache_dir()

        metadata = {
            "generated_at": _now_iso(),
            "primary_endpoint": NSE_COMBINED_ENDPOINT,
            "nse_only_endpoint_quarantined": NSE_ONLY_ENDPOINT,
            "primary_page": NSE_FII_DII_PAGE,
            "secondary_endpoint": SECONDARY_BASE_URL,
            "target_market_scope": COMBINED_SCOPE,
            "primary_scope_match": primary_verified,
            "metrics": metrics,
            "backfill": backfill_info,
            "primary_fetch_error": primary_error,
        }

        META_FILE.write_text(
            json.dumps(
                metadata,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    return result


# Backwards-compatible aliases for later Market Lab integration.
get_flow_snapshot = get_institutional_flow
run_institutional_flow_analysis = get_institutional_flow


# ===========================================================================
# COMMAND-LINE REPORT
# ===========================================================================

def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"

    if isinstance(value, (float, int)):
        return f"{value:,.2f}"

    return str(value)


def print_report(
    result: Dict[str, Any],
) -> None:
    metrics = result.get(
        "metrics",
        {},
    )

    snapshot = (
        result.get("snapshot")
        or {}
    )

    backfill = result.get(
        "backfill",
        {},
    )

    print("\n" + "=" * 72)
    print("NOVA INSTITUTIONAL FLOW ENGINE")
    print("=" * 72)

    print(
        "Primary candidate fetch : "
        f"{'OK' if result.get('primary_candidate_fetch_ok') else 'FAILED'}"
    )

    print(
        "Primary scope verified  : "
        f"{'YES' if result.get('primary_scope_match') else 'NO'}"
    )

    if result.get("primary_error"):
        print(
            "Primary note            : "
            f"{result['primary_error']}"
        )

    if snapshot:
        print(
            f"Latest session           : {snapshot.get('date')}"
        )

        print(
            f"FII net                  : {_fmt(snapshot.get('fii_net'))} Cr"
        )

        print(
            f"DII net                  : {_fmt(snapshot.get('dii_net'))} Cr"
        )

        print(
            f"Combined                 : {_fmt(snapshot.get('combined_net'))} Cr"
        )

        print(
            f"Latest source            : {snapshot.get('source')}"
        )

        print(
            f"Market scope             : {snapshot.get('market_scope')}"
        )

    print("\nHISTORY")

    print(
        "Observed sessions        : "
        f"{metrics.get('history_sessions', 0)} / "
        f"{metrics.get('target_sessions', DEFAULT_TARGET_SESSIONS)}"
    )

    print(
        "Coverage                 : "
        f"{metrics.get('oldest_date')} -> "
        f"{metrics.get('latest_date')}"
    )

    print(
        f"Quality                  : {metrics.get('history_quality')}"
    )

    print(
        f"History fresh            : {metrics.get('history_fresh', False)}"
    )

    print(
        "Latest session age       : "
        f"{metrics.get('latest_session_age_calendar_days', 'N/A')} "
        "calendar days"
    )

    print(
        "Freshness limit          : "
        f"{metrics.get('freshness_max_calendar_days', MAX_FRESHNESS_AGE_DAYS)} "
        "calendar days"
    )

    print(
        f"Scope consistent         : {metrics.get('scope_consistent')}"
    )

    print(
        f"Scope                    : {metrics.get('market_scope', COMBINED_SCOPE)}"
    )

    print(
        f"Invalid rows             : {metrics.get('invalid_rows', 0)}"
    )

    print(
        "Rows outside scope       : "
        f"{metrics.get('rows_outside_target_scope', 0)}"
    )

    print(
        "Market Lab ready         : "
        f"{metrics.get('data_ready_for_market_lab')}"
    )

    print(
        "Primary sessions         : "
        f"{metrics.get('primary_combined_sessions', 0)}"
    )

    print(
        "Secondary sessions       : "
        f"{metrics.get('secondary_sessions', 0)}"
    )

    if metrics.get("primary_coverage_note"):
        print(
            "Primary coverage note    : "
            f"{metrics.get('primary_coverage_note')}"
        )

    print(
        "Backfill added           : "
        f"{backfill.get('added_sessions', 0)} sessions"
    )

    print(
        "Backfill scan complete   : "
        f"{backfill.get('scan_complete', False)}"
    )

    if backfill.get("source_errors"):
        print(
            "Backfill source errors   : "
            f"{backfill.get('source_errors')}"
        )

    print("\nFLOW METRICS")

    for n in (5, 10, 20):
        print(
            f"{n:>2}D | "
            f"FII {_fmt(metrics.get(f'fii_{n}d')):>12} Cr | "
            f"DII {_fmt(metrics.get(f'dii_{n}d')):>12} Cr | "
            f"Combined {_fmt(metrics.get(f'combined_{n}d')):>12} Cr | "
            f"Divergence {_fmt(metrics.get(f'flow_divergence_{n}d')):>12} Cr"
        )

    print(
        "\nFII streak               : "
        f"{metrics.get('fii_streak_direction', 'UNKNOWN')} "
        f"{metrics.get('fii_streak_days', 0)}D"
    )

    print(
        "DII streak               : "
        f"{metrics.get('dii_streak_direction', 'UNKNOWN')} "
        f"{metrics.get('dii_streak_days', 0)}D"
    )

    print(
        f"Flow regime              : {metrics.get('flow_regime')}"
    )

    print(
        f"Source counts            : {metrics.get('source_counts', {})}"
    )

    print("=" * 72 + "\n")


def main(
    argv: Optional[Sequence[str]] = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Nova scope-validated institutional flow history builder"
        )
    )

    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_TARGET_SESSIONS,
        help=(
            "Target number of actual sessions; default 20"
        ),
    )

    parser.add_argument(
        "--scan-days",
        type=int,
        default=DEFAULT_SCAN_CALENDAR_DAYS,
        help=(
            "Calendar days to search for historical sessions; default 90"
        ),
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=(
            "Persist history, latest row and metadata"
        ),
    )

    parser.add_argument(
        "--no-backfill",
        action="store_true",
        help=(
            "Do not fetch missing historical sessions"
        ),
    )

    args = parser.parse_args(argv)

    if args.days < 1:
        parser.error(
            "--days must be >= 1"
        )

    if args.scan_days < 1:
        parser.error(
            "--scan-days must be >= 1"
        )

    try:
        result = get_institutional_flow(
            target_sessions=args.days,
            save=args.save,
            backfill=not args.no_backfill,
            scan_calendar_days=args.scan_days,
        )

        print_report(result)

    except Exception as exc:
        print(
            "\nINSTITUTIONAL FLOW ENGINE FAILED: "
            f"{exc}\n"
        )

        return 1

    ready = bool(
        result
        .get("metrics", {})
        .get(
            "data_ready_for_market_lab",
            False,
        )
    )

    if args.days >= 20 and not ready:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())