"""
Nova Quant Engine

Institutional-style analytics computed only from data Nova already holds:
daily OHLCV history for one stock, a benchmark close series, and the saved
NSE scan files. Pure functions: no network, no file writes, no invented
values. Anything that cannot be computed is returned as None with a reason.

Conventions (stated in every payload that uses them):
- Returns are simple daily close-to-close returns; annualisation uses 252.
- Risk-free rate is 0: Nova has no verified risk-free source, so "Sharpe"
  here is return per unit of volatility, not excess return.
- VaR/CVaR are historical (empirical quantiles), 1-day horizon.
- Factor spreads are out of sample: ranks come from an older saved scan and
  returns are measured from that scan's price to the newest scan's price.

Analysis only. Nothing here is a buy/sell signal or a forecast.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd

ENGINE_NAME = "Nova Quant Engine"
ENGINE_VERSION = "1.0.0"
TRADING_DAYS = 252
MIN_HISTORY = 60          # sessions needed for any risk statistic
FULL_YEAR_MIN = 240       # sessions that count as a full year of history
MIN_PAIRS = 60            # overlapping sessions needed for benchmark statistics
MIN_UNIVERSE = 200        # stocks needed for cross-sectional work
MIN_SECTOR = 5            # stocks needed to show a sector
PROFILE_BINS = 24
PROFILE_SESSIONS = 120
VALUE_AREA = 0.70
PARTICIPATION = 0.10      # share of average daily value assumed tradable without moving price
EXIT_NOTIONALS_CR = (10, 50, 250)  # institutional ticket sizes, Rs Cr
# forward returns outside this band between two scans are treated as corporate actions (split, bonus), not performance
FORWARD_RETURN_BAND = (-0.60, 1.50)

BUY_SELL_AUTHORIZATION = False


def _f(v: Any, d: int = 4) -> Optional[float]:
    """Finite float rounded to d places, else None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, d) if math.isfinite(x) else None


def _pct(v: Any, d: int = 2) -> Optional[float]:
    x = _f(v, 8)
    return None if x is None else round(x * 100, d)


def _date(ts: Any) -> str:
    return str(pd.Timestamp(ts).date())


def _daily(series: pd.Series) -> pd.Series:
    """Index by calendar date so NSE (naive) and Yahoo (tz-aware) histories align."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


# ---------------------------------------------------------------------------
# Single-stock risk profile
# ---------------------------------------------------------------------------

def _drawdown(close: pd.Series) -> dict:
    peak = close.cummax()
    dd = close / peak - 1
    trough = dd.idxmin()
    under = (dd < 0).astype(int)
    longest = run = 0
    for flag in under:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    last_peak = close[close == peak.iloc[-1]].index[-1]
    return {
        "max_pct": _pct(dd.min()),
        "peak_date": _date(close.loc[:trough].idxmax()),
        "trough_date": _date(trough),
        "current_pct": _pct(dd.iloc[-1]),
        "sessions_underwater": int((close.index > last_peak).sum()),
        "longest_underwater": int(longest),
    }


def _benchmark(r: pd.Series, rb: pd.Series) -> dict:
    j = pd.concat([r, rb], axis=1, join="inner").dropna()
    j.columns = ["s", "b"]
    if len(j) < MIN_PAIRS or j["b"].var() == 0:
        return {"status": "NOT_AVAILABLE", "reason": f"Only {len(j)} overlapping sessions with the benchmark; {MIN_PAIRS} needed."}

    def beta(x: pd.DataFrame) -> float:
        return float(x["s"].cov(x["b"]) / x["b"].var())

    b = beta(j)
    corr = float(j["s"].corr(j["b"]))
    active = j["s"] - j["b"]
    te = float(active.std() * math.sqrt(TRADING_DAYS))
    up, dn = j[j["b"] > 0], j[j["b"] < 0]
    return {
        "status": "AVAILABLE",
        "sessions": int(len(j)),
        "beta": _f(b, 2),
        "beta_60d": _f(beta(j.tail(60)), 2),
        "correlation": _f(corr, 2),
        "r_squared": _f(corr ** 2, 2),
        "alpha_annual_pct": _pct((j["s"].mean() - b * j["b"].mean()) * TRADING_DAYS, 1),
        "tracking_error_pct": _pct(te, 1),
        "information_ratio": _f(active.mean() * TRADING_DAYS / te, 2) if te else None,
        "up_capture_pct": _pct(up["s"].mean() / up["b"].mean(), 0) if len(up) >= 20 else None,
        "down_capture_pct": _pct(dn["s"].mean() / dn["b"].mean(), 0) if len(dn) >= 20 else None,
        "excess_return_pct": _pct((1 + j["s"]).prod() - (1 + j["b"]).prod(), 1),
    }


def _trend_quality(close: pd.Series, window: int) -> Optional[dict]:
    if len(close) < window:
        return None
    y = np.log(close.tail(window).to_numpy(dtype=float))
    x = np.arange(window, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - fit) ** 2).sum()) / ss_tot if ss_tot else 0.0
    return {"sessions": window, "slope_annual_pct": _pct(math.exp(slope * TRADING_DAYS) - 1, 1), "r_squared": _f(r2, 2)}


def _volume_profile(df: pd.DataFrame) -> Optional[dict]:
    """Volume at price: each session's volume is spread evenly over its low-high range."""
    d = df.tail(PROFILE_SESSIONS)
    lo, hi = float(d["Low"].min()), float(d["High"].max())
    if not (hi > lo) or float(d["Volume"].sum()) <= 0:
        return None
    edges = np.linspace(lo, hi, PROFILE_BINS + 1)
    vol = np.zeros(PROFILE_BINS)
    for low, high, v in zip(d["Low"].to_numpy(float), d["High"].to_numpy(float), d["Volume"].to_numpy(float)):
        if not (math.isfinite(low) and math.isfinite(high) and math.isfinite(v)) or v <= 0:
            continue
        if high <= low:
            vol[min(PROFILE_BINS - 1, int((low - lo) / (hi - lo) * PROFILE_BINS))] += v
            continue
        overlap = np.clip(np.minimum(edges[1:], high) - np.maximum(edges[:-1], low), 0, None)
        vol += v * overlap / (high - low)
    total = float(vol.sum())
    if total <= 0:
        return None
    poc = int(vol.argmax())
    left = right = poc
    covered = vol[poc]
    while covered / total < VALUE_AREA and (left > 0 or right < PROFILE_BINS - 1):
        below = vol[left - 1] if left > 0 else -1.0
        above = vol[right + 1] if right < PROFILE_BINS - 1 else -1.0
        if above >= below:
            right += 1
            covered += vol[right]
        else:
            left -= 1
            covered += vol[left]
    mids = (edges[:-1] + edges[1:]) / 2
    return {
        "sessions": int(len(d)),
        "poc": _f(mids[poc], 2),
        "value_area_low": _f(edges[left], 2),
        "value_area_high": _f(edges[right + 1], 2),
        "value_area_share_pct": _pct(covered / total, 0),
        "bins": [{"price": _f(m, 2), "share_pct": _pct(v / total, 2)} for m, v in zip(mids, vol)],
    }


def _anchored_vwaps(df: pd.DataFrame) -> list[dict]:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    pv, v = tp * df["Volume"], df["Volume"]
    out = []

    def add(label: str, start) -> None:
        vol = float(v.loc[start:].sum())
        if vol > 0:
            out.append({"anchor": label, "date": _date(start), "vwap": _f(pv.loc[start:].sum() / vol, 2)})

    add("Period high", df["High"].idxmax())
    add("Period low", df["Low"].idxmin())
    this_year = df[df.index.year == df.index[-1].year]
    if len(this_year) < len(df):  # the year's first bar is inside the window
        add("Year to date", this_year.index[0])
    return out


def risk_profile(history: pd.DataFrame, benchmark_close: Optional[pd.Series] = None, benchmark_name: str = "Nifty 50") -> dict:
    """Risk, benchmark, liquidity and structure statistics for one stock from daily OHLCV."""
    need = ["Open", "High", "Low", "Close", "Volume"]
    if history is None or not set(need).issubset(getattr(history, "columns", [])):
        return {"status": "NOT_AVAILABLE", "reason": "Daily OHLCV history is missing."}
    df = history[need].apply(pd.to_numeric, errors="coerce").dropna(subset=["Close"])
    idx = pd.DatetimeIndex(df.index)
    df.index = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if len(df) < MIN_HISTORY:
        return {"status": "NOT_AVAILABLE", "reason": f"Only {len(df)} sessions of history; {MIN_HISTORY} needed."}

    close = df["Close"]
    r = close.pct_change().dropna()
    n = len(close)
    last = float(close.iloc[-1])

    def ret(k: int) -> Optional[float]:
        if k == TRADING_DAYS and FULL_YEAR_MIN <= n <= k:
            k = n - 1  # a "1y" download holds 245-252 sessions; use the whole window
        return _pct(last / float(close.iloc[-1 - k]) - 1) if n > k else None

    def vol(k: int) -> Optional[float]:
        return _pct(r.tail(k).std() * math.sqrt(TRADING_DAYS), 1) if len(r) >= k else None

    rolling = (r.rolling(20).std() * math.sqrt(TRADING_DAYS)).dropna()
    downside = math.sqrt(float((r.clip(upper=0) ** 2).mean())) * math.sqrt(TRADING_DAYS)
    ann_ret = float(r.mean()) * TRADING_DAYS
    ann_vol = float(r.std()) * math.sqrt(TRADING_DAYS)
    q05 = float(r.quantile(0.05))
    dd = _drawdown(close)
    years = len(r) / TRADING_DAYS
    cagr = (last / float(close.iloc[0])) ** (1 / years) - 1 if years > 0 else None

    value_cr = (close * df["Volume"]).dropna() / 1e7
    adv20, adv60 = float(value_cr.tail(20).mean()), float(value_cr.tail(60).mean())
    amihud = (r.abs() / value_cr.reindex(r.index)).replace([np.inf, -np.inf], np.nan).tail(60).mean()
    path = float(close.diff().abs().tail(20).sum())

    out = {
        "status": "AVAILABLE",
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "as_of": _date(close.index[-1]),
        "sessions": int(n),
        "from": _date(close.index[0]),
        "conventions": "Simple daily returns, 252-day annualisation, risk-free rate 0, historical VaR.",
        "returns_pct": {"1m": ret(21), "3m": ret(63), "6m": ret(126), "12m": ret(252),
                        "12m_ex_1m": _pct(float(close.iloc[-22]) / float(close.iloc[-253]) - 1) if n > 252 else None},
        "volatility": {
            "vol_20d_pct": vol(20), "vol_60d_pct": vol(60), "vol_full_pct": _pct(ann_vol, 1),
            "vol_20d_percentile": _pct((rolling <= rolling.iloc[-1]).mean(), 0) if len(rolling) >= 40 else None,
            "downside_dev_pct": _pct(downside, 1),
        },
        "tail": {
            "var_95_pct": _pct(-q05), "cvar_95_pct": _pct(-float(r[r <= q05].mean())),
            "var_99_pct": _pct(-float(r.quantile(0.01))) if len(r) >= 100 else None,
            "worst_day_pct": _pct(r.min()), "worst_day_date": _date(r.idxmin()),
            "best_day_pct": _pct(r.max()), "best_day_date": _date(r.idxmax()),
            "skew": _f(r.skew(), 2), "excess_kurtosis": _f(r.kurt(), 2),
        },
        "drawdown": dd,
        "ratios": {
            "return_annual_pct": _pct(ann_ret, 1),
            "sharpe_rf0": _f(ann_ret / ann_vol, 2) if ann_vol else None,
            "sortino_rf0": _f(ann_ret / downside, 2) if downside else None,
            "calmar": _f(cagr / abs(dd["max_pct"] / 100), 2) if cagr is not None and dd["max_pct"] else None,
        },
        "benchmark": {"name": benchmark_name, **(_benchmark(r, _daily(benchmark_close).pct_change().dropna())
                                                 if benchmark_close is not None and len(benchmark_close) else
                                                 {"status": "NOT_AVAILABLE", "reason": "Benchmark history unavailable."})},
        "liquidity": {
            "adv_20d_cr": _f(adv20, 2), "adv_60d_cr": _f(adv60, 2), "median_60d_cr": _f(value_cr.tail(60).median(), 2),
            "adv_20d_vs_60d": _f(adv20 / adv60, 2) if adv60 else None,
            # average absolute daily move, in basis points, per Rs 1 Cr traded (Amihud illiquidity, 60 sessions)
            "amihud_bps_per_cr": _f(amihud * 10000, 3),
            "participation_pct": PARTICIPATION * 100,
            "days_to_exit": [{"notional_cr": c, "days": _f(c / (PARTICIPATION * adv20), 1) if adv20 > 0 else None} for c in EXIT_NOTIONALS_CR],
        },
        "trend_quality": {
            "fit_60d": _trend_quality(close, 60), "fit_120d": _trend_quality(close, 120),
            # Kaufman efficiency ratio: net move / path length over 20 sessions (1 = straight line, 0 = noise)
            "efficiency_20d": _f(abs(last - float(close.iloc[-21])) / path, 2) if n > 20 and path else None,
        },
        "volume_profile": _volume_profile(df),
        "anchored_vwap": _anchored_vwaps(df),
        "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
    }
    return out


# ---------------------------------------------------------------------------
# Cross-sectional frame
# ---------------------------------------------------------------------------

NUMERIC = ("price", "return_1d", "return_5d", "return_20d", "return_60d", "relative_strength_20d", "relative_strength_60d",
           "ema_20", "ema_50", "ema_200", "rsi_14", "atr_percent", "volume", "volume_average_20", "relative_volume",
           "distance_52w_high", "distance_52w_low", "score")


def prepare(scan: pd.DataFrame) -> pd.DataFrame:
    """Typed copy of a scan with the derived columns every cross-sectional function uses."""
    d = scan.copy()
    for c in NUMERIC:
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    d = d[d["price"] > 0].drop_duplicates("symbol").reset_index(drop=True)
    d["value_cr"] = d["price"] * d["volume"].fillna(0) / 1e7
    d["avg_value_cr"] = d["price"] * d["volume_average_20"] / 1e7
    for k in (20, 50, 200):
        d[f"vs_ema{k}"] = (d["price"] / d[f"ema_{k}"] - 1) * 100
    # the scanner stores both 52-week distances as positive magnitudes (percent away from the extreme)
    d["below_high"] = d["distance_52w_high"].abs()
    d["above_low"] = d["distance_52w_low"].abs()
    if "sector" not in d.columns:
        d["sector"] = ""
    d["sector"] = d["sector"].fillna("").astype(str)
    return d


def _share(mask: pd.Series) -> Optional[float]:
    m = mask.dropna()
    return _pct(m.mean(), 1) if len(m) else None


def _breadth(d: pd.DataFrame) -> dict:
    adv, dec = int((d["return_1d"] > 0).sum()), int((d["return_1d"] < 0).sum())
    up_val = float(d.loc[d["return_1d"] > 0, "value_cr"].sum())
    dn_val = float(d.loc[d["return_1d"] < 0, "value_cr"].sum())
    return {
        "stocks": int(len(d)), "advancing": adv, "declining": dec, "unchanged": int(len(d) - adv - dec),
        "ad_ratio": _f(adv / dec, 2) if dec else None,
        "up_value_share_pct": _pct(up_val / (up_val + dn_val), 1) if up_val + dn_val else None,
        "above_ema20_pct": _share(d["vs_ema20"].dropna() > 0), "above_ema50_pct": _share(d["vs_ema50"].dropna() > 0),
        "above_ema200_pct": _share(d["vs_ema200"].dropna() > 0),
        "new_highs": int((d["below_high"] == 0).sum()), "new_lows": int((d["above_low"] == 0).sum()),
        "within_5pct_of_high_pct": _share(d["below_high"].dropna() <= 5),
        "rsi_over_70_pct": _share(d["rsi_14"].dropna() >= 70), "rsi_under_30_pct": _share(d["rsi_14"].dropna() <= 30),
        "median_1d_pct": _f(d["return_1d"].median(), 2), "median_5d_pct": _f(d["return_5d"].median(), 2),
        "median_20d_pct": _f(d["return_20d"].median(), 2), "median_60d_pct": _f(d["return_60d"].median(), 2),
        "dispersion_1d_pct": _f(d["return_1d"].std(), 2), "dispersion_20d_pct": _f(d["return_20d"].std(), 2),
    }


def breadth_regime(b: dict) -> dict:
    """Rule-based label; the rule is returned so the reader can check it."""
    a200, a50 = b.get("above_ema200_pct"), b.get("above_ema50_pct")
    if a200 is None or a50 is None:
        return {"label": "Unknown", "rule": "Breadth inputs missing."}
    if a200 >= 60 and a50 >= 60:
        label = "Broad uptrend"
    elif a200 >= 60:
        label = "Uptrend, short-term pullback"
    elif a200 <= 40 and a50 <= 40:
        label = "Broad downtrend"
    elif a200 <= 40:
        label = "Downtrend, short-term rebound"
    else:
        label = "Mixed"
    return {"label": label, "rule": f"{a200:.0f}% above the 200-day average and {a50:.0f}% above the 50-day (60 / 40 thresholds)."}


def market_internals(d: pd.DataFrame) -> dict:
    """Breadth, participation by liquidity tier and concentration of traded value."""
    if len(d) < MIN_UNIVERSE:
        return {"status": "NOT_AVAILABLE", "reason": f"Scan holds {len(d)} stocks; {MIN_UNIVERSE} needed."}
    ranked = d.sort_values("avg_value_cr", ascending=False, na_position="last").reset_index(drop=True)
    tiers = []
    for name, part in (("Top 100 by value", ranked.iloc[:100]), ("Next 400", ranked.iloc[100:500]), ("Rest", ranked.iloc[500:])):
        if len(part):
            tiers.append({"tier": name, **_breadth(part), "value_cr": _f(part["value_cr"].sum(), 0)})
    total = float(d["value_cr"].sum())
    shares = d["value_cr"] / total if total else d["value_cr"] * 0
    top = d.nlargest(10, "value_cr")
    b = _breadth(d)
    return {
        "status": "AVAILABLE", "breadth": b, "regime": breadth_regime(b), "tiers": tiers,
        "concentration": {
            "total_value_cr": _f(total, 0), "top10_share_pct": _pct(shares.nlargest(10).sum(), 1),
            "top50_share_pct": _pct(shares.nlargest(50).sum(), 1),
            # Herfindahl index of traded value: 10,000 = one stock holds all turnover
            "hhi": _f(float((shares ** 2).sum()) * 10000, 0),
            "top10": [{"symbol": s, "value_cr": _f(v, 0), "return_1d": _f(r1, 2)} for s, v, r1 in zip(top["symbol"], top["value_cr"], top["return_1d"])],
        },
    }


def sector_rotation(d: pd.DataFrame) -> dict:
    """Relative-strength rotation by sector.

    Strength is measured against the median stock, not the cap-weighted Nifty: when a few
    large caps carry the index, every equal-weight sector "lags" it and the map says nothing.
    x = sector median 60-day return minus the universe median (strength).
    y = sector median 20-day return minus the universe median, minus one third of x
        (is the last month running ahead of the 60-day pace?).
    """
    rows = []
    total = float(d["value_cr"].sum())
    base60, base20 = d["return_60d"].median(), d["return_20d"].median()
    for name, g in d[d["sector"] != ""].groupby("sector"):
        if len(g) < MIN_SECTOR:
            continue
        x, rs20 = g["return_60d"].median() - base60, g["return_20d"].median() - base20
        if pd.isna(x) or pd.isna(rs20):
            continue
        y = rs20 - x / 3
        quadrant = "Leading" if x >= 0 and y >= 0 else "Weakening" if x >= 0 else "Improving" if y >= 0 else "Lagging"
        leader = g.loc[g["return_60d"].idxmax()] if g["return_60d"].notna().any() else None
        rows.append({
            "sector": name, "stocks": int(len(g)), "quadrant": quadrant, "rs_60d": _f(x, 2), "rs_20d": _f(rs20, 2), "rs_momentum": _f(y, 2),
            "median_1d": _f(g["return_1d"].median(), 2), "median_5d": _f(g["return_5d"].median(), 2), "median_20d": _f(g["return_20d"].median(), 2),
            "above_ema50_pct": _share(g["vs_ema50"].dropna() > 0), "above_ema200_pct": _share(g["vs_ema200"].dropna() > 0),
            "value_share_pct": _pct(g["value_cr"].sum() / total, 1) if total else None,
            "leader": None if leader is None else str(leader["symbol"]),
        })
    order = {"Leading": 0, "Improving": 1, "Weakening": 2, "Lagging": 3}
    rows.sort(key=lambda r: (order[r["quadrant"]], -(r["rs_60d"] or 0)))
    counts = {q: sum(1 for r in rows if r["quadrant"] == q) for q in order}
    return {"status": "AVAILABLE" if rows else "NOT_AVAILABLE", "sectors": rows, "counts": counts,
            "universe_median_60d": _f(base60, 2), "universe_median_20d": _f(base20, 2),
            "method": "x: sector median 60D return minus the median stock's. y: the same for 20D, minus x/3. Sectors with 5+ stocks."}


# ---------------------------------------------------------------------------
# Out-of-sample factor spreads
# ---------------------------------------------------------------------------

FACTORS = {
    # relative strength vs Nifty ranks stocks exactly as raw return does, so it is not listed twice
    "Momentum 60D": ("return_60d", 1),
    "Momentum 5D": ("return_5d", 1),
    "Near 52W high": ("below_high", -1),
    "Trend vs 200D": ("vs_ema200", 1),
    "Low volatility": ("atr_percent", -1),
    "Liquidity": ("avg_value_cr", 1),
    "Relative volume": ("relative_volume", 1),
    "Scanner score": ("score", 1),
}
MIN_FACTOR_NAMES = 100


def factor_spreads(base: pd.DataFrame, now: pd.DataFrame) -> dict:
    """Quintile spreads: rank on the older scan, measure return to the newer scan."""
    j = base.merge(now[["symbol", "price"]].rename(columns={"price": "price_now"}), on="symbol", how="inner")
    j["fwd"] = j["price_now"] / j["price"] - 1
    lo, hi = FORWARD_RETURN_BAND
    kept = j[(j["fwd"] >= lo) & (j["fwd"] <= hi)]
    dropped = int(len(j) - len(kept))
    rows = []
    for name, (col, sign) in FACTORS.items():
        s = kept[[col, "fwd"]].dropna()
        if len(s) < MIN_FACTOR_NAMES or s[col].nunique() < 5:
            rows.append({"factor": name, "status": "NOT_AVAILABLE", "names": int(len(s))})
            continue
        q = pd.qcut((s[col] * sign).rank(method="first"), 5, labels=False)
        means = s.groupby(q)["fwd"].mean()
        # rank correlation of factor value with forward return: the information coefficient
        ic = (s[col] * sign).rank().corr(s["fwd"].rank())
        rows.append({
            "factor": name, "status": "AVAILABLE", "names": int(len(s)),
            "top_pct": _pct(means.iloc[-1]), "bottom_pct": _pct(means.iloc[0]), "spread_pct": _pct(means.iloc[-1] - means.iloc[0]),
            "ic": _f(ic, 3), "monotonic": bool(means.is_monotonic_increasing),
            "quintiles_pct": [_pct(v) for v in means],
        })
    return {"names": int(len(kept)), "dropped_corporate_action_suspects": dropped, "universe_median_pct": _pct(kept["fwd"].median()), "factors": rows}


def breadth_point(d: pd.DataFrame) -> dict:
    b = _breadth(d)
    return {k: b[k] for k in ("stocks", "advancing", "declining", "above_ema20_pct", "above_ema50_pct", "above_ema200_pct",
                              "new_highs", "new_lows", "median_20d_pct", "rsi_over_70_pct", "rsi_under_30_pct")}


# ---------------------------------------------------------------------------
# Single-stock scorecard (percentile ranks against the scan universe)
# ---------------------------------------------------------------------------

PILLARS = {
    "Trend": (("vs_ema200", 1), ("vs_ema50", 1)),
    "Momentum": (("return_60d", 1), ("return_20d", 1)),
    "52W position": (("below_high", -1),),
    "Low volatility": (("atr_percent", -1),),
}
MIN_SECTOR_RANK = 8


def _percentile(col: pd.Series, value: float, sign: int) -> Optional[float]:
    s = col.dropna()
    if not len(s) or pd.isna(value):
        return None
    below = (s < value).mean() if sign > 0 else (s > value).mean()
    return round(float(below) * 100, 0)


def _pillar(frame: pd.DataFrame, row: pd.Series, inputs) -> Optional[float]:
    p = [x for x in (_percentile(frame[c], row[c], s) for c, s in inputs) if x is not None]
    return round(sum(p) / len(p), 0) if p else None


def _conflicts(row: pd.Series, pillars: dict) -> list[str]:
    out = []
    g = lambda k: row.get(k)
    mom, trend, vol = pillars.get("Momentum"), pillars.get("Trend"), pillars.get("Low volatility")
    if pd.notna(g("rsi_14")) and g("rsi_14") >= 75 and (mom or 0) >= 70:
        out.append(f"Momentum is top-tier but RSI {g('rsi_14'):.0f} is stretched.")
    if pd.notna(g("rsi_14")) and g("rsi_14") <= 30 and (trend or 100) <= 30:
        out.append(f"Trend is weak and RSI {g('rsi_14'):.0f} is washed out: weakness is established, not new.")
    if (mom or 0) >= 70 and (vol or 100) <= 20:
        out.append("Strong momentum comes with bottom-quintile volatility rank: moves are large in both directions.")
    if pd.notna(g("return_60d")) and pd.notna(g("return_5d")) and g("return_60d") > 15 and g("return_5d") < -5:
        out.append(f"60-day gain of {g('return_60d'):.0f}% against a 5-day loss of {abs(g('return_5d')):.0f}%.")
    if pd.notna(g("vs_ema200")) and pd.notna(g("vs_ema20")) and g("vs_ema200") > 0 > g("vs_ema20") and (trend or 0) >= 50:
        out.append("Above the 200-day average but below the 20-day: long trend intact, short trend broken.")
    if pd.notna(g("relative_volume")) and g("relative_volume") >= 2 and pd.notna(g("return_1d")) and g("return_1d") < -2:
        out.append(f"Fell {abs(g('return_1d')):.1f}% on {g('relative_volume'):.1f}x normal volume.")
    if pd.notna(g("avg_value_cr")) and g("avg_value_cr") < 1:
        out.append(f"Average traded value is Rs {g('avg_value_cr'):.2f} Cr a day: prices here are easy to move.")
    return out


def scorecard(d: pd.DataFrame, symbol: str) -> dict:
    """Where one stock sits in the scan universe and in its sector, pillar by pillar."""
    hit = d[d["symbol"] == str(symbol).upper()]
    if hit.empty:
        return {"status": "NOT_AVAILABLE", "reason": f"{symbol} is not in the saved scan."}
    if len(d) < MIN_UNIVERSE:
        return {"status": "NOT_AVAILABLE", "reason": f"Scan holds {len(d)} stocks; {MIN_UNIVERSE} needed."}
    row = hit.iloc[0]
    sector = row["sector"]
    peers = d[d["sector"] == sector] if sector else d.iloc[0:0]
    pillars = {name: _pillar(d, row, inputs) for name, inputs in PILLARS.items()}
    in_sector = {name: _pillar(peers, row, inputs) for name, inputs in PILLARS.items()} if len(peers) >= MIN_SECTOR_RANK else {}
    scored = [v for v in pillars.values() if v is not None]
    composite = round(sum(scored) / len(scored), 0) if len(scored) >= 3 else None
    # a rank against other stocks, never a view on direction: a top-quartile stock can still be falling
    stance = ("Not rated" if composite is None else "Top quartile" if composite >= 75 else "Above median" if composite >= 55
              else "Mid-pack" if composite >= 45 else "Below median" if composite >= 25 else "Bottom quartile")
    return {
        "status": "AVAILABLE", "symbol": str(row["symbol"]), "sector": sector or None, "universe": int(len(d)),
        "sector_peers": int(len(peers)) if len(peers) >= MIN_SECTOR_RANK else None,
        "composite": composite, "stance": stance,
        "pillars": [{"pillar": k, "universe_pct": v, "sector_pct": in_sector.get(k)} for k, v in pillars.items()],
        # capacity, not evidence: reported beside the composite, never inside it
        "liquidity_pct": _percentile(d["avg_value_cr"], row["avg_value_cr"], 1),
        "conflicts": _conflicts(row, pillars),
        "method": "Percentile rank against every stock in the universe; composite is the plain average of the four pillars.",
        "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
    }


# ---------------------------------------------------------------------------
# Plain-language read of the internals
# ---------------------------------------------------------------------------

def internals_read(internals: dict, rotation: dict, spreads: Optional[dict]) -> list[dict]:
    """Short factual lines. tone: positive | negative | neutral. Never a trade call."""
    out: list[dict] = []
    if internals.get("status") != "AVAILABLE":
        return out
    b, tiers = internals["breadth"], internals["tiers"]

    def add(tone: str, topic: str, text: str) -> None:
        out.append({"tone": tone, "topic": topic, "text": text})

    a200 = b["above_ema200_pct"]
    add("positive" if a200 >= 60 else "negative" if a200 <= 40 else "neutral", "Regime", f"{internals['regime']['label']}. {internals['regime']['rule']}")
    if len(tiers) >= 2 and tiers[0]["above_ema50_pct"] is not None and tiers[-1]["above_ema50_pct"] is not None:
        gap = tiers[0]["above_ema50_pct"] - tiers[-1]["above_ema50_pct"]
        if abs(gap) >= 10:
            add("neutral", "Participation", f"{tiers[0]['above_ema50_pct']:.0f}% of the 100 most traded stocks sit above their 50-day average "
                f"against {tiers[-1]['above_ema50_pct']:.0f}% of the least traded: {'large caps lead' if gap > 0 else 'the broad market leads'}.")
    hi, lo = b["new_highs"], b["new_lows"]
    add("positive" if hi > lo else "negative" if lo > hi else "neutral", "Highs and lows", f"{hi} stocks at a 52-week high against {lo} at a low.")
    if b["up_value_share_pct"] is not None:
        u = b["up_value_share_pct"]
        add("positive" if u >= 60 else "negative" if u <= 40 else "neutral", "Money flow", f"{u:.0f}% of traded value was in advancing stocks.")
    c = rotation.get("counts") or {}
    if rotation.get("sectors"):
        lead = [r["sector"] for r in rotation["sectors"] if r["quadrant"] == "Leading"][:3]
        lag = [r["sector"] for r in rotation["sectors"] if r["quadrant"] == "Lagging"][:3]
        add("neutral", "Rotation", f"{c.get('Leading', 0)} sectors leading, {c.get('Improving', 0)} improving, {c.get('Weakening', 0)} weakening, "
            f"{c.get('Lagging', 0)} lagging." + (f" Leading: {', '.join(lead)}." if lead else "") + (f" Lagging: {', '.join(lag)}." if lag else ""))
    if spreads:
        ok = [f for f in spreads["factors"] if f["status"] == "AVAILABLE"]
        if ok:
            best, worst = max(ok, key=lambda f: f["spread_pct"]), min(ok, key=lambda f: f["spread_pct"])
            add("neutral", "Factors", f"Since {spreads['base_date']}: {best['factor']} paid most ({best['spread_pct']:+.2f} pts top minus bottom quintile), "
                f"{worst['factor']} least ({worst['spread_pct']:+.2f} pts).")
    return out
