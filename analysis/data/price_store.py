"""
Nova Price Store

A local daily price database for every NSE equity, built from two NSE sources:

- "security-wise bhavcopy with delivery": one CSV per session with OHLC, volume,
  turnover and delivery quantity for every traded security.
- the corporate-actions feed: ex-dates and the exchange's own description of each
  split, bonus, rights issue and dividend.

Why it exists:
- History no longer depends on a per-symbol Yahoo download.
- Survivorship-free: a stock that was later delisted is still in the days it traded.
- Corporate actions are applied from NSE's record, and each one is checked against
  the price gap actually observed on the ex-date. An action whose stated ratio does
  not match the gap is kept on file as unverified and is NOT applied.
- Bhavcopy PREV_CLOSE is the raw previous close: NSE does not restate it on
  ex-dates, so it cannot be used to adjust. (Verified: Nestle's 1:10 split on
  2024-01-05 shows prev_close 27116.40, close 2666.40.)
- A one-day move beyond +/-40% that no verified action explains (a demerger, a
  relisting, a scheme of arrangement) is treated as unknown, not as performance.

Read-only market data. No orders, no broker. SQLite from the standard library.

CLI:
    python -m analysis.data.price_store --update            # fetch sessions missing since the last one stored
    python -m analysis.data.price_store --backfill 2021-01-01
    python -m analysis.data.price_store --status
"""

from __future__ import annotations

import argparse
import io
import re
import sqlite3
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from analysis.data import derivatives_engine as de

DB_PATH = Path(__file__).resolve().parent / "cache" / "prices" / "prices.sqlite"
ARCHIVE = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{:%d%m%Y}.csv"
SYMBOL_CHANGES = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
ACTIONS_API = "https://www.nseindia.com/api/corporates-corporateActions"
# rolling-settlement equity series; EQ wins when a symbol shows up in two on one day
SERIES = ("EQ", "BE", "BZ")
PAUSE_S = 0.35            # gap between archive requests: this is NSE's server, not ours
RECENT_DAYS = 4           # a missing file this recent may simply not be published yet
TIMEOUT_S = 25
VERIFY_BAND = (0.70, 1.40)   # observed ex-date gap / stated factor must fall here for an action to be applied
MAX_DIVIDEND_YIELD = 0.30    # a single cash dividend above this share of price is a parsing error, not a payout
UNEXPLAINED_MOVE = 0.40      # NSE price bands cap ordinary one-day moves well inside this

_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL, date TEXT NOT NULL, series TEXT, prev_close REAL, open REAL, high REAL, low REAL, close REAL,
    volume REAL, turnover_lacs REAL, trades INTEGER, deliv_qty REAL, deliv_pct REAL,
    PRIMARY KEY (symbol, date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS bars_date ON bars (date);
CREATE TABLE IF NOT EXISTS days (date TEXT PRIMARY KEY, rows INTEGER NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS symbol_changes (old TEXT NOT NULL, new TEXT NOT NULL, date TEXT NOT NULL, PRIMARY KEY (old, new, date));
CREATE TABLE IF NOT EXISTS actions (
    symbol TEXT NOT NULL, ex_date TEXT NOT NULL, kind TEXT NOT NULL, a REAL, b REAL, c REAL, subject TEXT NOT NULL,
    PRIMARY KEY (symbol, ex_date, kind, subject)
);
CREATE TABLE IF NOT EXISTS action_years (year INTEGER PRIMARY KEY, fetched TEXT NOT NULL);
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    con.executescript(SCHEMA)
    return con


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_bhavcopy(raw: bytes) -> pd.DataFrame:
    """One day's archive CSV -> rows for `bars`. Raises ValueError when the file is not a bhavcopy."""
    df = pd.read_csv(io.BytesIO(raw), skipinitialspace=True, na_values=["-", " -", ""])
    df.columns = [c.strip().upper() for c in df.columns]
    need = {"SYMBOL", "SERIES", "DATE1", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"}
    if not need.issubset(df.columns):
        raise ValueError(f"Not a bhavcopy: columns {list(df.columns)[:6]}")
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df = df[df["SERIES"].isin(SERIES)].copy()
    df["_rank"] = df["SERIES"].map({s: i for i, s in enumerate(SERIES)})
    df = df.sort_values("_rank").drop_duplicates("SYMBOL", keep="first")
    out = pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip(),
        "date": pd.to_datetime(df["DATE1"].astype(str).str.strip(), format="%d-%b-%Y").dt.strftime("%Y-%m-%d"),
        "series": df["SERIES"],
    })
    for col, src in (("prev_close", "PREV_CLOSE"), ("open", "OPEN_PRICE"), ("high", "HIGH_PRICE"), ("low", "LOW_PRICE"), ("close", "CLOSE_PRICE"),
                     ("volume", "TTL_TRD_QNTY"), ("turnover_lacs", "TURNOVER_LACS"), ("trades", "NO_OF_TRADES"), ("deliv_qty", "DELIV_QTY"), ("deliv_pct", "DELIV_PER")):
        out[col] = pd.to_numeric(df[src], errors="coerce") if src in df.columns else np.nan
    return out[out["close"] > 0].reset_index(drop=True)


def parse_symbol_changes(raw: bytes) -> list[tuple[str, str, str]]:
    df = pd.read_csv(io.BytesIO(raw), skipinitialspace=True)
    df.columns = [c.strip().upper() for c in df.columns]
    out = []
    for old, new, when in zip(df["OLD SYMBOL"], df["NEW SYMBOL"], df["EFFECTIVE DATE"]):
        d = pd.to_datetime(str(when).strip(), format="%d-%b-%Y", errors="coerce")
        if pd.notna(d) and str(old).strip() and str(new).strip():
            out.append((str(old).strip(), str(new).strip(), d.strftime("%Y-%m-%d")))
    return out


_RUPEES = r"r[se]\.?\s*([0-9]+(?:\.[0-9]+)?)"
_SPLIT = re.compile(rf"(?:split|sub-?\s*division|consolidation).*?from\s+{_RUPEES}.*?to\s+{_RUPEES}", re.I | re.S)
_BONUS = re.compile(r"bonus\s+(\d+)\s*:\s*(\d+)", re.I)
_RIGHTS = re.compile(rf"rights\s+(\d+)\s*:\s*(\d+)(?:.*?premium\s+{_RUPEES})?", re.I | re.S)
_PER_SHARE = re.compile(rf"{_RUPEES}\s*(?:/-)?\s*per\s+sh", re.I)


def parse_action(subject: str, face_value: Optional[float] = None) -> list[tuple[str, float, Optional[float], Optional[float]]]:
    """NSE's free-text subject -> [(kind, a, b, c)].

    split:    a = old face value, b = new face value          price factor b / a
    bonus:    a new shares for every b held                    price factor b / (a + b)
    rights:   a new shares for every b held, c = issue price   price factor from the theoretical ex-rights price
    dividend: a = rupees per share (every amount in the subject, summed)
    """
    s, out = str(subject or ""), []
    m = _SPLIT.search(s)
    if m and float(m.group(1)) > 0 and float(m.group(2)) > 0:
        out.append(("split", float(m.group(1)), float(m.group(2)), None))
    m = _BONUS.search(s)
    if m and int(m.group(1)) > 0 and int(m.group(2)) > 0:
        out.append(("bonus", float(m.group(1)), float(m.group(2)), None))
    m = _RIGHTS.search(s)
    if m and int(m.group(1)) > 0 and int(m.group(2)) > 0:
        premium = float(m.group(3)) if m.group(3) else None
        out.append(("rights", float(m.group(1)), float(m.group(2)), None if premium is None else premium + (face_value or 0)))
    if "dividend" in s.lower():
        total = sum(float(x) for x in _PER_SHARE.findall(s))
        if total > 0:
            out.append(("dividend", total, None, None))
    return out


def parse_actions(payload) -> list[tuple]:
    """Corporate-actions API rows -> rows for `actions`."""
    out = []
    for row in payload if isinstance(payload, list) else []:
        if str(row.get("series", "")).strip() not in SERIES:
            continue
        ex = pd.to_datetime(str(row.get("exDate", "")).strip(), format="%d-%b-%Y", errors="coerce")
        symbol, subject = str(row.get("symbol", "")).strip(), " ".join(str(row.get("subject", "")).split())
        if pd.isna(ex) or not symbol:
            continue
        try:
            face = float(row.get("faceVal"))
        except (TypeError, ValueError):
            face = None
        for kind, a, b, c in parse_action(subject, face):
            out.append((symbol, ex.strftime("%Y-%m-%d"), kind, a, b, c, subject))
    return out


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _store_day(con: sqlite3.Connection, day: date, frame: Optional[pd.DataFrame]) -> int:
    rows = 0 if frame is None else len(frame)
    with _write_lock, con:
        if rows:
            con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            frame.astype(object).where(frame.notna(), None).itertuples(index=False, name=None))
        con.execute("INSERT OR REPLACE INTO days VALUES (?,?,?)", (day.isoformat(), rows, "ok" if rows else "none"))
    return rows


def _session():
    s = de.create_nse_session()
    de.warm_nse_session(s)
    return s


def _get(session, url: str, params: Optional[dict] = None):
    return session.get(url, params=params, timeout=TIMEOUT_S, headers={**de.HEADERS, "Referer": "https://www.nseindia.com/"})


def missing_days(con: sqlite3.Connection, start: date, end: date) -> list[date]:
    """Every calendar day not yet recorded. Weekends are asked too: NSE holds special sessions on them
    (budget Saturdays, Diwali muhurat Sundays); an empty weekend is remembered like any holiday."""
    known = {r[0] for r in con.execute("SELECT date FROM days WHERE date BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))}
    out, d = [], start
    while d <= end:
        if d.isoformat() not in known:
            out.append(d)
        d += timedelta(days=1)
    return out


def update_actions(con: sqlite3.Connection, session, first_year: int, last_year: int, log=print) -> int:
    """Corporate actions, one request per calendar year. Past years are fetched once; the current year every time."""
    done = {r[0] for r in con.execute("SELECT year FROM action_years")}
    stored = 0
    for year in range(first_year, last_year + 1):
        if year in done and year < date.today().year:
            continue
        try:
            r = _get(session, ACTIONS_API, {"index": "equities", "from_date": f"01-01-{year}", "to_date": f"31-12-{year}"})
            rows = parse_actions(r.json())
        except Exception as exc:
            log(f"[PRICE STORE] corporate actions {year} unavailable: {type(exc).__name__}: {exc}")
            continue
        with _write_lock, con:
            con.executemany("INSERT OR REPLACE INTO actions VALUES (?,?,?,?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO action_years VALUES (?,?)", (year, date.today().isoformat()))
        stored += len(rows)
    return stored


def update(start: Optional[date] = None, end: Optional[date] = None, con: Optional[sqlite3.Connection] = None,
           session=None, log=print, pause: float = PAUSE_S) -> dict:
    """Fetch every day not yet recorded between start and end, then refresh corporate actions.
    Days without a file are remembered so they are asked for once."""
    own = con is None
    con = con or connect()
    try:
        end = end or date.today()
        if start is None:
            last = con.execute("SELECT MAX(date) FROM days WHERE status='ok'").fetchone()[0]
            start = date.fromisoformat(last) + timedelta(days=1) if last else end - timedelta(days=400)
        todo = missing_days(con, start, end)
        got = empty = failed = 0
        if todo:
            session = session or _session()
            try:
                with _write_lock, con:
                    con.executemany("INSERT OR REPLACE INTO symbol_changes VALUES (?,?,?)", parse_symbol_changes(_get(session, SYMBOL_CHANGES).content))
            except Exception as exc:  # renames are a refinement; prices still load without them
                log(f"[PRICE STORE] symbol changes unavailable: {exc}")
        for i, day in enumerate(todo):
            try:
                r = _get(session, ARCHIVE.format(day))
                frame = parse_bhavcopy(r.content) if r.status_code == 200 and r.content[:6] == b"SYMBOL" else None
                if frame is not None and len(frame) and (frame["date"] == day.isoformat()).all():
                    got += 1 if _store_day(con, day, frame) else 0
                elif frame is not None:
                    # the archive answers some non-trading dates with another session's file (seen on 2021-22 Sundays)
                    _store_day(con, day, None)
                    empty += 1
                elif r.status_code == 404 or r.status_code == 200:
                    if (end - day).days > RECENT_DAYS:  # old and absent: no session. Recent and absent: maybe not published yet
                        _store_day(con, day, None)
                    empty += 1
                else:
                    failed += 1
                    log(f"[PRICE STORE] {day}: HTTP {r.status_code}")
            except Exception as exc:
                failed += 1
                log(f"[PRICE STORE] {day}: {type(exc).__name__}: {exc}")
                try:
                    session = _session()
                except Exception:
                    break  # NSE is refusing us; stop rather than hammer it
            if (i + 1) % 100 == 0:
                log(f"[PRICE STORE] {i + 1}/{len(todo)} days, {got} stored")
            if pause and i + 1 < len(todo):
                time.sleep(pause)
        first = con.execute("SELECT MIN(date) FROM days WHERE status='ok'").fetchone()[0]
        actions = 0
        if first and (todo or not con.execute("SELECT 1 FROM action_years LIMIT 1").fetchone()):
            actions = update_actions(con, session or _session(), int(first[:4]), end.year, log)
        return {"requested": len(todo), "stored": got, "no_file": empty, "failed": failed, "actions_loaded": actions, **status(con)}
    finally:
        if own:
            con.close()


def version(con: Optional[sqlite3.Connection] = None) -> tuple:
    """(last session, sessions, actions): changes whenever the store does. Milliseconds, unlike `status`."""
    own = con is None
    con = con or connect()
    try:
        last, sessions = con.execute("SELECT MAX(date), COUNT(*) FROM days WHERE status='ok'").fetchone()
        return last, sessions, con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    finally:
        if own:
            con.close()


def status(con: Optional[sqlite3.Connection] = None) -> dict:
    own = con is None
    con = con or connect()
    try:
        first, last, sessions = con.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM days WHERE status='ok'").fetchone()
        rows, symbols = con.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM bars").fetchone()
        actions = con.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        return {"available": bool(sessions), "first": first, "last": last, "sessions": sessions, "rows": rows, "symbols": symbols, "actions": actions}
    finally:
        if own:
            con.close()


# ---------------------------------------------------------------------------
# Corporate-action factors
# ---------------------------------------------------------------------------

def price_factor(kind: str, a: float, b: Optional[float], c: Optional[float], prev_close: float) -> Optional[float]:
    """Multiplier that restates a pre-action price in post-action terms (0.5 for a 1:1 bonus). None when it cannot be computed."""
    if kind == "split":
        return b / a
    if kind == "bonus":
        return b / (a + b)
    if kind == "rights":
        if c is None or not prev_close or prev_close <= 0:
            return None
        return min(1.0, (b * prev_close + a * c) / ((a + b) * prev_close))  # rights priced above market carry no discount
    return None


def evaluate_actions(actions: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Attach each action to the first bar on or after its ex-date and decide whether it can be applied.

    actions: symbol, ex_date, kind, a, b, c, subject.   bars: symbol, date, close (ascending by date within a symbol).
    Returns: symbol, date (the bar it lands on), kind, subject, factor, dividend, verified, note.
    """
    cols = ["symbol", "date", "kind", "subject", "factor", "dividend", "verified", "note"]

    def frame(rows: list) -> pd.DataFrame:
        # typed even when empty: an object-dtype "verified" column cannot be used as a boolean mask
        return pd.DataFrame(rows, columns=cols).astype({"factor": float, "dividend": float, "verified": bool})

    if actions.empty or bars.empty:
        return frame([])
    by_symbol = {s: g for s, g in bars.groupby("symbol", sort=False)}
    out = []
    for symbol, group in actions.groupby("symbol", sort=False):
        g = by_symbol.get(symbol)
        if g is None:
            continue
        dates, close = g["date"].to_numpy(), g["close"].to_numpy(dtype=float)
        for ex_date, day in group.groupby("ex_date"):
            i = int(np.searchsorted(dates, ex_date))
            if i == 0 or i >= len(dates):
                continue  # before the first stored bar or after the last: nothing to restate
            prev, now = close[i - 1], close[i]
            observed = now / prev if prev > 0 else np.nan
            combined, parts = 1.0, []
            for row in day.itertuples():
                if row.kind == "dividend":
                    ok = prev > 0 and row.a / prev <= MAX_DIVIDEND_YIELD
                    out.append((symbol, dates[i], "dividend", row.subject, 1.0, row.a if ok else 0.0, ok, "" if ok else "Amount is implausible against the price; ignored."))
                    continue
                f = price_factor(row.kind, row.a, row.b, row.c, prev)
                if f is None or not np.isfinite(f) or f <= 0:
                    out.append((symbol, dates[i], row.kind, row.subject, 1.0, 0.0, False, "Terms could not be turned into a ratio."))
                    continue
                combined *= f
                parts.append((row.kind, row.subject, f))
            if parts:
                # judge the day's price-changing actions together: a bonus and a split can share an ex-date
                ok = np.isfinite(observed) and VERIFY_BAND[0] <= observed / combined <= VERIFY_BAND[1]
                note = "" if ok else f"Stated ratio {combined:.4f} does not match the observed ex-date gap {observed:.4f}; not applied."
                for kind, subject, f in parts:
                    out.append((symbol, dates[i], kind, subject, f if ok else 1.0, 0.0, bool(ok), note))
    return frame(out)


def _load_actions(con: sqlite3.Connection, symbols: Optional[list[str]] = None) -> pd.DataFrame:
    q = "SELECT symbol, ex_date, kind, a, b, c, subject FROM actions"
    if symbols:
        return pd.read_sql_query(q + f" WHERE symbol IN ({','.join('?' * len(symbols))})", con, params=symbols)
    return pd.read_sql_query(q, con)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def rename_map(con: sqlite3.Connection) -> dict[str, str]:
    """old symbol -> the symbol it trades under today (follows chains A -> B -> C)."""
    step = {}
    for old, new, _ in con.execute("SELECT old, new, date FROM symbol_changes ORDER BY date"):
        if old != new:
            step[old] = new
    out = {}
    for old in step:
        cur, seen = old, set()
        while cur in step and cur not in seen:
            seen.add(cur)
            cur = step[cur]
        out[old] = cur
    return out


def _aliases(con: sqlite3.Connection, symbol: str) -> list[str]:
    final = rename_map(con)
    target = final.get(symbol, symbol)
    return [target] + [old for old, new in final.items() if new == target]


EMPTY_HISTORY = ["Open", "High", "Low", "Close", "Volume", "RawClose", "DelivPct", "DelivQty", "TurnoverCr", "Factor", "Dividend"]


def history(symbol: str, sessions: Optional[int] = None, con: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """Daily history for one symbol in today's share terms, including bars under its earlier names.

    Open/High/Low/Close/Volume are adjusted for verified splits, bonuses and rights (not for dividends, as on any
    price chart). RawClose is as traded. Factor and Dividend mark the bars where an action landed.
    """
    own = con is None
    con = con or connect()
    try:
        names = _aliases(con, str(symbol).upper())
        marks = ",".join("?" * len(names))
        f = pd.read_sql_query(f"SELECT * FROM bars WHERE symbol IN ({marks}) ORDER BY date", con, params=names)
        acts = _load_actions(con, names)
    finally:
        if own:
            con.close()
    if f.empty:
        return pd.DataFrame(columns=EMPTY_HISTORY)
    f = f.drop_duplicates("date", keep="last").reset_index(drop=True)
    one = f.assign(symbol=names[0])
    ev = evaluate_actions(acts.assign(symbol=names[0]), one[["symbol", "date", "close"]])
    factor = pd.Series(1.0, index=f["date"])
    dividend = pd.Series(0.0, index=f["date"])
    for row in ev[ev["verified"]].itertuples():
        factor[row.date] *= row.factor
        dividend[row.date] += row.dividend
    # every earlier bar is multiplied by the product of all later factors
    cum = pd.Series(factor.to_numpy()[::-1].cumprod()[::-1], index=f.index).shift(-1).fillna(1.0)
    out = pd.DataFrame({
        "Open": f["open"] * cum, "High": f["high"] * cum, "Low": f["low"] * cum, "Close": f["close"] * cum, "Volume": f["volume"] / cum,
        "RawClose": f["close"], "DelivPct": f["deliv_pct"], "DelivQty": f["deliv_qty"], "TurnoverCr": f["turnover_lacs"] / 100,
        "Factor": factor.to_numpy(), "Dividend": dividend.to_numpy(),
    })
    out.index = pd.DatetimeIndex(pd.to_datetime(f["date"]), name="Date")
    return out.tail(sessions) if sessions else out


def recent_histories(sessions: int = 300, con: Optional[sqlite3.Connection] = None) -> tuple[Optional[str], dict[str, pd.DataFrame]]:
    """(last session, {symbol: adjusted daily OHLCV}) for every symbol over the last `sessions` stored sessions.

    One bulk read instead of one query per stock. Same adjustment as `history`: verified splits, bonuses and
    rights restate earlier bars; dividends do not. Old symbols are folded into the name they trade under today.
    """
    own = con is None
    con = con or connect()
    try:
        dates = [r[0] for r in con.execute("SELECT date FROM days WHERE status='ok' ORDER BY date DESC LIMIT ?", (sessions,))]
        if not dates:
            return None, {}
        start = dates[-1]
        f = pd.read_sql_query("SELECT symbol, date, open, high, low, close, volume FROM bars WHERE date >= ?", con, params=[start])
        acts = pd.read_sql_query("SELECT symbol, ex_date, kind, a, b, c, subject FROM actions WHERE ex_date >= ?", con, params=[start])
        final = rename_map(con)
    finally:
        if own:
            con.close()
    f["symbol"] = f["symbol"].map(lambda s: final.get(s, s))
    acts["symbol"] = acts["symbol"].map(lambda s: final.get(s, s))
    f = f.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"]).reset_index(drop=True)
    ev = evaluate_actions(acts, f[["symbol", "date", "close"]])
    on_day = ev[ev["verified"]].groupby(["symbol", "date"])["factor"].prod().rename("factor").reset_index()
    f = f.merge(on_day, on=["symbol", "date"], how="left")
    f["factor"] = f["factor"].fillna(1.0)
    # product of all later factors within the symbol, so every bar is in today's share terms
    rev = f.iloc[::-1]
    f["cum"] = rev.groupby("symbol", sort=False)["factor"].cumprod().iloc[::-1] / f["factor"]
    out = {}
    for symbol, g in f.groupby("symbol", sort=False):
        frame = pd.DataFrame({"Open": g["open"] * g["cum"], "High": g["high"] * g["cum"], "Low": g["low"] * g["cum"],
                              "Close": g["close"] * g["cum"], "Volume": g["volume"] / g["cum"]}).set_axis(pd.DatetimeIndex(pd.to_datetime(g["date"]), name="Date"))
        out[symbol] = frame
    return dates[0], out


def corporate_actions(symbol: str, con: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Every action NSE lists for the symbol inside the stored window, with whether the store applied it."""
    own = con is None
    con = con or connect()
    try:
        names = _aliases(con, str(symbol).upper())
        marks = ",".join("?" * len(names))
        bars = pd.read_sql_query(f"SELECT date, close FROM bars WHERE symbol IN ({marks}) ORDER BY date", con, params=names)
        acts = _load_actions(con, names)
    finally:
        if own:
            con.close()
    ev = evaluate_actions(acts.assign(symbol=names[0]), bars.drop_duplicates("date", keep="last").assign(symbol=names[0]))
    return [{"date": r.date, "kind": r.kind, "subject": r.subject, "factor": round(float(r.factor), 4), "dividend": round(float(r.dividend), 2),
             "applied": bool(r.verified), "note": r.note} for r in ev.sort_values("date").itertuples()]


def panels(start: Optional[str] = None, con: Optional[sqlite3.Connection] = None) -> dict:
    """Wide date x symbol frames for cross-sectional research.

    ret:  total return per session: close-to-close across stored bars, restated for verified splits, bonuses and
          rights, with cash dividends added on the ex-date. A move beyond +/-40% that no verified action explains is NaN.
    adj:  total-return index chained from ret (1.0 on the first traded day, flat through gaps).
    turnover_cr, deliv_pct: as traded.   meta: what was applied and what was dropped.
    Old symbols are folded into the name they trade under today.
    """
    own = con is None
    con = con or connect()
    try:
        q = "SELECT symbol, date, close, turnover_lacs, deliv_pct FROM bars" + (" WHERE date >= ?" if start else "")
        f = pd.read_sql_query(q, con, params=[start] if start else None)
        acts = _load_actions(con)
        final = rename_map(con)
    finally:
        if own:
            con.close()
    if f.empty:
        return {}
    f["symbol"] = f["symbol"].map(lambda s: final.get(s, s))
    acts["symbol"] = acts["symbol"].map(lambda s: final.get(s, s))
    f = f.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"]).reset_index(drop=True)
    ev = evaluate_actions(acts, f[["symbol", "date", "close"]])
    ok = ev[ev["verified"]]
    on_day = ok.groupby(["symbol", "date"]).agg(factor=("factor", "prod"), dividend=("dividend", "sum")).reset_index()
    f = f.merge(on_day, on=["symbol", "date"], how="left")
    f["factor"], f["dividend"] = f["factor"].fillna(1.0), f["dividend"].fillna(0.0)
    prev = f.groupby("symbol", sort=False)["close"].shift(1)
    f["ret"] = (f["close"] + f["dividend"]) / (prev * f["factor"]) - 1
    explained = f["factor"] != 1.0
    wild = (f["ret"].abs() > UNEXPLAINED_MOVE) & ~explained
    f.loc[wild, "ret"] = np.nan
    idx = pd.DatetimeIndex(pd.to_datetime(sorted(f["date"].unique())))
    f["date"] = pd.to_datetime(f["date"])

    def wide(col: str) -> pd.DataFrame:
        return f.pivot(index="date", columns="symbol", values=col).reindex(idx)

    ret = wide("ret")
    traded = wide("close").notna()
    adj = (1 + ret.fillna(0)).cumprod().where(traded.cummax())  # NaN before the first trade, flat through gaps
    price_changing = ev[ev["kind"] != "dividend"]
    return {
        "ret": ret, "adj": adj, "traded": traded, "turnover_cr": wide("turnover_lacs") / 100, "deliv_pct": wide("deliv_pct"),
        "meta": {
            "splits_bonuses_rights_applied": int(price_changing["verified"].sum()),
            "splits_bonuses_rights_unverified": int((~price_changing["verified"]).sum()),
            "dividends_applied": int(((ev["kind"] == "dividend") & ev["verified"]).sum()),
            "unexplained_moves_dropped": int(wild.sum()),
        },
    }


# ---------------------------------------------------------------------------

def main(argv: Optional[Iterable[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Nova price store (NSE bhavcopy archive). Read-only market data.")
    p.add_argument("--update", action="store_true", help="fetch sessions missing since the last stored one")
    p.add_argument("--backfill", metavar="YYYY-MM-DD", help="fetch every missing session from this date")
    p.add_argument("--status", action="store_true")
    a = p.parse_args(argv)
    if a.backfill:
        print(update(start=date.fromisoformat(a.backfill)))
    elif a.update:
        print(update())
    print(status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
