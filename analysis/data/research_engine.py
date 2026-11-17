"""
Nova Research Engine

Multi-year research on the price store's panels: a monthly-rebalanced factor
backtest, daily market breadth, and a per-stock delivery profile.

Pure functions on pandas frames; no network and no file access. Analysis only:
a factor's past spread is evidence about the past, never a forecast or a signal.

What the backtest does and does not do (repeated in its payload):
- Universe at each month-end: the `top_n` stocks by median traded value over the
  prior 126 sessions that traded that day and have a year of history. Chosen with
  information available on that day only.
- Signals use data up to the rebalance day; returns run to the next month-end.
- Returns are total returns from the price store: restated for the splits,
  bonuses and rights NSE lists (each checked against the ex-date price gap), with
  cash dividends added on the ex-date. One-day moves beyond 40% that no verified
  action explains are dropped rather than counted.
- A stock that stops trading stays flat from its last trade. The store keeps
  delisted names, so there is no survivorship filter, but a delisting loss after
  the last trade is not captured.
- Long-short is a diagnostic: most NSE stocks cannot be shorted outside F&O.
  "Long-only excess" (top fifth minus the universe) is the investable reading.
"""

from __future__ import annotations

import math
import re
from typing import Optional

import numpy as np
import pandas as pd

ENGINE_NAME = "Nova Research Engine"
ENGINE_VERSION = "1.0.0"
MONTHS = 12
LOOKBACK_YEAR = 252
LIQUIDITY_LOOKBACK = 126
MIN_LIQUIDITY_OBS = 100
MIN_NAMES = 100           # stocks needed in a month for quintiles to mean anything
MIN_MONTHS = 12           # months needed before a factor is reported
DEFAULT_TOP_N = 500
DEFAULT_COST_BPS = 30     # one-way cost per rupee traded: brokerage, STT, stamp, impact (assumption, shown on screen)

FACTORS = {
    "Momentum 12-1": "Return from 12 months ago to 1 month ago.",
    "Momentum 6-1": "Return from 6 months ago to 1 month ago.",
    "Reversal 1M": "Last month's return, sign-flipped: losers rank high.",
    "Low volatility": "126-session volatility, sign-flipped: calm stocks rank high.",
    "Near 52W high": "Price as a share of its 252-session high.",
    "Trend vs 200D": "Price against its 200-session average.",
    "Delivery %": "Average delivery percentage over the last 21 sessions.",
}


def _f(v, d: int = 2) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, d) if math.isfinite(x) else None


_NOT_EQUITY = re.compile(r"-RE\d*$|ETF|BEES$|^LIQUID|GOLD|SILVER")
DELISTED_AFTER_DAYS = 30


def equity_columns(p: dict, listed: set) -> list[str]:
    """Symbols that are equities: listed in the NSE equity master, or no longer trading and not fund-like.

    The bhavcopy's EQ series also carries ETFs (NIFTYBEES, GOLDBEES, LIQUIDBEES ...) and rights entitlements
    (XYZ-RE). Liquid and gold funds would sit in the "low volatility" quintile and in the liquid 500.
    A delisted stock is not in today's master, so it is kept unless its name marks it as a fund or entitlement.
    """
    traded = p["traded"]
    last_trade = traded[::-1].idxmax()
    end = traded.index[-1]
    gone = last_trade < end - pd.Timedelta(days=DELISTED_AFTER_DAYS)
    return [s for s in traded.columns if s in listed or (bool(gone.get(s)) and not _NOT_EQUITY.search(s))]


def restrict(p: dict, columns: list[str]) -> dict:
    """The same panels with only `columns`; non-frame entries (meta) pass through."""
    return {k: (v[columns] if isinstance(v, pd.DataFrame) else v) for k, v in p.items()}


def rebalance_positions(index: pd.DatetimeIndex) -> list[int]:
    """Row number of the last session of each calendar month (the final, partial month included)."""
    s = pd.Series(np.arange(len(index)), index=index)
    return [int(v) for v in s.groupby([index.year, index.month]).last()]


def liquid_universe(turnover: pd.DataFrame, traded: pd.DataFrame, adj: pd.DataFrame, pos: int, top_n: int) -> pd.Index:
    window = turnover.iloc[max(0, pos - LIQUIDITY_LOOKBACK + 1): pos + 1]
    ok = (window.notna().sum() >= MIN_LIQUIDITY_OBS) & traded.iloc[pos] & adj.iloc[pos - LOOKBACK_YEAR].notna()
    return window.median()[ok].nlargest(top_n).index


def signals(p: dict, pos: int, names: pd.Index) -> pd.DataFrame:
    """Factor values on rebalance day `pos`, built only from rows up to and including it. Higher = ranks higher."""
    adj, ret, dlv = p["adj"][names], p["ret"][names], p["deliv_pct"][names]
    now, m1, m6, m12 = adj.iloc[pos], adj.iloc[pos - 21], adj.iloc[pos - 126], adj.iloc[pos - LOOKBACK_YEAR]
    year = adj.iloc[pos - LOOKBACK_YEAR: pos + 1]
    return pd.DataFrame({
        "Momentum 12-1": m1 / m12 - 1,
        "Momentum 6-1": m1 / m6 - 1,
        "Reversal 1M": -(now / m1 - 1),
        "Low volatility": -ret.iloc[pos - 125: pos + 1].std(),
        "Near 52W high": now / year.max(),
        "Trend vs 200D": now / adj.iloc[pos - 199: pos + 1].mean() - 1,
        "Delivery %": dlv.iloc[pos - 20: pos + 1].mean(),
    })


def _max_drawdown(curve: np.ndarray) -> float:
    peak = np.maximum.accumulate(curve)
    return float((curve / peak - 1).min())


def _stats(rows: list[dict], cost_bps: float) -> dict:
    f = pd.DataFrame(rows)
    n = len(f)
    ls, lo, ic = f["ls"], f["lo"], f["ic"]
    turnover = float(f["turnover"].dropna().mean()) if f["turnover"].notna().any() else None
    # each replaced name is sold and its replacement bought: two one-way trades per unit of turnover
    cost_annual = None if turnover is None else turnover * 2 * cost_bps / 1e4 * MONTHS
    curve_ls, curve_lo = np.cumprod(1 + ls.to_numpy()), np.cumprod(1 + lo.to_numpy())

    def t(x: pd.Series) -> Optional[float]:
        sd = x.std()
        return _f(x.mean() / sd * math.sqrt(n)) if sd and sd > 0 else None

    return {
        "months": n, "from": str(f["date"].iloc[0])[:10], "to": str(f["end"].iloc[-1])[:10], "avg_names": _f(f["names"].mean(), 0),
        "spread_annual_pct": _f(ls.mean() * MONTHS * 100), "spread_vol_pct": _f(ls.std() * math.sqrt(MONTHS) * 100),
        "spread_ir": _f(ls.mean() / ls.std() * math.sqrt(MONTHS)) if ls.std() else None, "spread_t": t(ls),
        "hit_rate_pct": _f((ls > 0).mean() * 100, 0), "spread_max_drawdown_pct": _f(_max_drawdown(curve_ls) * 100, 1),
        "long_only_excess_pct": _f(lo.mean() * MONTHS * 100), "long_only_t": t(lo),
        "long_only_net_pct": None if cost_annual is None else _f((lo.mean() * MONTHS - cost_annual) * 100),
        "ic_mean": _f(ic.mean(), 3), "ic_t": t(ic), "turnover_pct": None if turnover is None else _f(turnover * 100, 0),
        "quintiles_annual_pct": [_f(f[f"q{i}"].mean() * MONTHS * 100, 1) for i in range(1, 6)],
        "monotonic": bool(pd.Series([f[f"q{i}"].mean() for i in range(1, 6)]).is_monotonic_increasing),
        "curve": {"dates": [str(d)[:10] for d in f["end"]], "long_short": [_f(v, 4) for v in curve_ls], "long_only_excess": [_f(v, 4) for v in curve_lo]},
    }


def factor_backtest(p: dict, top_n: int = DEFAULT_TOP_N, cost_bps: float = DEFAULT_COST_BPS) -> dict:
    """Monthly-rebalanced quintile portfolios for every factor in FACTORS."""
    if not p or "adj" not in p or len(p["adj"]) < LOOKBACK_YEAR + 60:
        return {"status": "NOT_AVAILABLE", "reason": "The price store holds less than about 15 months of sessions; a backtest needs a year of lookback plus months to test."}
    adj, index, meta = p["adj"], p["adj"].index, p.get("meta", {})
    cuts = [x for x in rebalance_positions(index) if x >= LOOKBACK_YEAR]
    rows: dict[str, list[dict]] = {k: [] for k in FACTORS}
    held: dict[str, set] = {}
    for a, b in zip(cuts[:-1], cuts[1:]):
        names = liquid_universe(p["turnover_cr"], p["traded"], adj, a, top_n)
        if len(names) < MIN_NAMES:
            continue
        fwd = adj.iloc[b][names] / adj.iloc[a][names] - 1
        sig = signals(p, a, names)
        for name in FACTORS:
            s = pd.concat([sig[name], fwd], axis=1, keys=["x", "r"]).dropna()
            if len(s) < MIN_NAMES or s["x"].nunique() < 5:
                continue
            q = pd.qcut(s["x"].rank(method="first"), 5, labels=False)
            means = s.groupby(q)["r"].mean()
            top = set(s.index[q == 4])
            prev = held.get(name)
            held[name] = top
            rows[name].append({
                "date": index[a], "end": index[b], "names": len(s), "ls": means.iloc[4] - means.iloc[0], "lo": means.iloc[4] - s["r"].mean(),
                "ic": s["x"].rank().corr(s["r"].rank()), "turnover": None if prev is None else 1 - len(top & prev) / len(top),
                **{f"q{i + 1}": means.iloc[i] for i in range(5)},
            })
    out = []
    for name, description in FACTORS.items():
        if len(rows[name]) < MIN_MONTHS:
            out.append({"factor": name, "description": description, "status": "NOT_AVAILABLE", "months": len(rows[name])})
        else:
            out.append({"factor": name, "description": description, "status": "AVAILABLE", **_stats(rows[name], cost_bps)})
    ok = [f for f in out if f["status"] == "AVAILABLE"]
    return {
        "status": "AVAILABLE" if ok else "NOT_AVAILABLE", "engine": f"{ENGINE_NAME} {ENGINE_VERSION}",
        "reason": None if ok else f"Fewer than {MIN_MONTHS} testable months in the store.",
        "sessions": int(len(index)), "store_from": str(index[0])[:10], "store_to": str(index[-1])[:10],
        "top_n": top_n, "cost_bps_one_way": cost_bps, "adjustments": meta, "rebalance": "Month-end, equal weight, quintiles",
        "factors": out,
        "caveats": [
            "Total returns: verified splits, bonuses and rights restated, cash dividends added on the ex-date. "
            f"{meta.get('unexplained_moves_dropped', 0)} one-day moves beyond 40% with no verified action were dropped, "
            f"{meta.get('splits_bonuses_rights_unverified', 0)} listed actions did not match the price gap and were not applied.",
            "A stock that stops trading stays flat from its last trade; delisting losses after that are not captured.",
            "Long-short is a diagnostic. Most NSE stocks cannot be shorted outside F&O; read long-only excess.",
            f"Costs: {cost_bps:g} bp one way on top-fifth turnover, an assumption. Past spreads are not forecasts.",
        ],
        "buy_sell_authorization": False,
    }


# ---------------------------------------------------------------------------
# Daily breadth
# ---------------------------------------------------------------------------

def breadth_series(p: dict, top_n: Optional[int] = None) -> pd.DataFrame:
    """Per session: share of traded stocks above their 50 and 200-session averages, advancers, decliners, 252-session highs and lows.

    `top_n` restricts each day to the stocks that were most liquid over the trailing 126 sessions (rank known on that day).
    """
    adj, ret, traded = p["adj"], p["ret"], p["traded"]
    live = traded
    if top_n:
        med = p["turnover_cr"].rolling(LIQUIDITY_LOOKBACK, min_periods=MIN_LIQUIDITY_OBS).median()
        live = traded & (med.rank(axis=1, ascending=False) <= top_n)

    def share(mask: pd.DataFrame, base: pd.DataFrame) -> pd.Series:
        d = base.sum(axis=1)
        return (mask & base).sum(axis=1) / d.where(d > 0) * 100

    sma50, sma200 = adj.rolling(50, min_periods=50).mean(), adj.rolling(200, min_periods=200).mean()
    hi, lo = adj.rolling(LOOKBACK_YEAR, min_periods=200).max(), adj.rolling(LOOKBACK_YEAR, min_periods=200).min()
    out = pd.DataFrame({
        "stocks": live.sum(axis=1),
        "above_50_pct": share(adj > sma50, live & sma50.notna()),
        "above_200_pct": share(adj > sma200, live & sma200.notna()),
        "advancing": ((ret > 0) & live).sum(axis=1), "declining": ((ret < 0) & live).sum(axis=1),
        "new_highs": ((adj >= hi) & live & hi.notna()).sum(axis=1), "new_lows": ((adj <= lo) & live & lo.notna()).sum(axis=1),
    })
    out["ad_line"] = (out["advancing"] - out["declining"]).cumsum()
    return out.iloc[200:] if len(out) > 260 else out.iloc[0:0]


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def delivery_profile(history: pd.DataFrame) -> dict:
    """How much of a stock's volume is taken into delivery, and whether that share is rising."""
    if history is None or "DelivPct" not in getattr(history, "columns", []) or history["DelivPct"].notna().sum() < 60:
        return {"status": "NOT_AVAILABLE", "reason": "Fewer than 60 sessions of delivery data in the price store."}
    d = history["DelivPct"].dropna()
    value = (history["TurnoverCr"] * history["DelivPct"] / 100).dropna()
    a5, a20, a60 = d.tail(5).mean(), d.tail(20).mean(), d.tail(60).mean()
    roll = d.rolling(20).mean().dropna().tail(LOOKBACK_YEAR)
    gap = a5 - a60
    return {
        "status": "AVAILABLE", "as_of": str(d.index[-1].date()), "sessions": int(len(d)),
        "last_pct": _f(d.iloc[-1], 1), "avg_5d_pct": _f(a5, 1), "avg_20d_pct": _f(a20, 1), "avg_60d_pct": _f(a60, 1),
        "avg_20d_percentile": _f((roll <= roll.iloc[-1]).mean() * 100, 0) if len(roll) >= 60 else None,
        "delivered_value_20d_cr": _f(value.tail(20).mean(), 2), "delivered_value_60d_cr": _f(value.tail(60).mean(), 2),
        "trend": "Rising" if gap >= 5 else "Falling" if gap <= -5 else "Stable",
        "trend_rule": f"5-session average {a5:.1f}% against 60-session {a60:.1f}% (5-point threshold).",
    }
