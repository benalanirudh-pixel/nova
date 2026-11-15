"""
Nova Store Scan

The market scan, rebuilt from the local price store for every listed NSE equity.

The saved scanner run covers about 2,000 stocks: it downloads each one and drops
anything with under 210 sessions. Here every symbol in the NSE equity master that
traded in the last week gets a row:
- 210+ stored sessions: the scanner's own `analyze_stock_dataframe`, so trend,
  score and every indicator mean exactly what they mean in the saved scan.
- fewer sessions (recent listings): the fields that history can support, the rest
  left empty, and `short_history` set. Nothing is filled with a default.

No network. Analysis only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from analysis.data import market_scanner as ms

MIN_SESSIONS = 20          # below this a stock gets no row: too little to say anything
FULL_SESSIONS = 210        # the scanner's own minimum
MAX_STALE_DAYS = 7         # last bar older than this before the store's last session: suspended or delisted


def _ret(close: pd.Series, k: int) -> Optional[float]:
    return float((close.iloc[-1] / close.iloc[-1 - k] - 1) * 100) if len(close) > k and close.iloc[-1 - k] > 0 else None


def nifty_returns(close: Optional[pd.Series], as_of: str) -> dict:
    """Nifty returns over the same window as the store, ending on the store's last session (not on a later feed date)."""
    empty = {"return_1d": None, "return_5d": None, "return_20d": None, "return_60d": None}
    if close is None or not len(close):
        return empty
    s = pd.to_numeric(close, errors="coerce").dropna()
    idx = pd.DatetimeIndex(s.index)
    s.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    s = s[s.index <= pd.Timestamp(as_of)]
    return ms.calculate_nifty_returns(pd.DataFrame({"Close": s})) if len(s) > 60 else empty


def short_row(symbol: str, df: pd.DataFrame, nifty: dict) -> dict:
    """Scanner columns for a stock with fewer than 210 sessions: only what its history supports."""
    close, vol = df["Close"], df["Volume"]
    n, price = len(close), float(close.iloc[-1])
    r = {k: _ret(close, d) for k, d in (("return_1d", 1), ("return_5d", 5), ("return_20d", 20), ("return_60d", 60))}
    ema = {k: (float(close.ewm(span=k, adjust=False).mean().iloc[-1]) if n >= k else None) for k in (20, 50)}
    delta = close.diff()
    gain, loss = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1])) if n > 15 and loss.iloc[-1] > 0 else None
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - close.shift()).abs(), (df["Low"] - close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(14).mean()) if n > 15 else None
    hi, lo = float(df["High"].max()), float(df["Low"].min())
    avg20 = float(vol.tail(20).mean()) if n >= 20 else None
    rel = lambda k: None if r[k] is None or nifty.get(k) is None else r[k] - nifty[k]
    return {
        "symbol": symbol, "price": price, **r,
        "nifty_return_20d": nifty.get("return_20d"), "nifty_return_60d": nifty.get("return_60d"),
        "relative_strength_20d": rel("return_20d"), "relative_strength_60d": rel("return_60d"),
        "ema_20": ema[20], "ema_50": ema[50], "ema_200": None, "rsi_14": rsi,
        "atr_14": atr, "atr_percent": atr / price * 100 if atr else None,
        "volume": float(vol.iloc[-1]), "volume_average_20": avg20, "relative_volume": float(vol.iloc[-1]) / avg20 if avg20 else None,
        # under a year of history has no 52-week high or low; a high since listing would pass for one in every screen
        "high_52w": None, "low_52w": None, "distance_52w_high": None, "distance_52w_low": None,
        "high_since_listing": hi, "low_since_listing": lo,
        "trend": None, "score": None,
    }


def build(histories: dict[str, pd.DataFrame], as_of: str, symbols: set[str], nifty_close: Optional[pd.Series] = None,
          sectors: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """One scanner-style row per listed symbol that is still trading. `sectors`: symbol, sector, industry, company_name."""
    nifty = nifty_returns(nifty_close, as_of)
    cutoff = pd.Timestamp(as_of) - pd.Timedelta(days=MAX_STALE_DAYS)
    rows = []
    for symbol in sorted(symbols):
        df = histories.get(symbol)
        if df is None or len(df) < MIN_SESSIONS or df.index[-1] < cutoff:
            continue
        df = df.dropna(subset=["Close"])
        row = ms.analyze_stock_dataframe(symbol, df, nifty) if len(df) >= FULL_SESSIONS else None
        short = row is None
        row = row or short_row(symbol, df, nifty)
        row.update(symbol=symbol, timestamp=str(df.index[-1].date()), history_sessions=int(len(df)), short_history=short,
                   last_session=str(df.index[-1].date()))
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["rank"] = out["score"].rank(ascending=False, method="min")
    if sectors is not None and len(sectors):
        keep = [c for c in ("symbol", "macro_sector", "sector", "industry", "basic_industry", "company_name") if c in sectors.columns]
        out = out.merge(sectors[keep].drop_duplicates("symbol"), on="symbol", how="left")
    return out.replace([np.inf, -np.inf], np.nan)


def built_at() -> str:
    return datetime.now().isoformat(timespec="seconds")
