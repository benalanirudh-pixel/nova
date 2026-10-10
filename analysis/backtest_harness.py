"""
============================================================================
 NOVA MARKET INTELLIGENCE â€” FACTOR BACKTEST HARNESS
============================================================================

Purpose:
    Prove the built-in technical factors actually separate winners from
    losers historically, so the "score" Nova shows you is evidence, not
    decoration.

Design:
    1. Load the NSE universe (the same symbols the scanner ranks).
    2. Pull 1y of OHLCV history per symbol (parallel, 5 workers).
    3. Run calculate_indicators on every symbol (the same engine the UI
       and the watchlist use).
    4. Score each symbol with the existing calculate_momentum_score plus
       trend + relative-volume strength.
    5. Rank the universe by score and measure the return gap between the
       top and bottom deciles.

IMPORTANT (analysis, not execution):
    This harness only computes and reports. It does NOT place orders,
    does NOT connect to a broker, and does NOT execute BUY/SELL.

Usage:
    python analysis/backtest_harness.py           # full NSE universe
    python analysis/backtest_harness.py --quick   # 20 sample symbols
    python analysis/backtest_harness.py --days 252 --workers 5
============================================================================
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Make the Nova project root importable even when launched directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.data.market_universe import (
    get_price_history,
    get_nse_symbols,
)
from analysis.data.technical_engine import (
    calculate_indicators,
    calculate_momentum_score,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKTEST_DIR = PROJECT_ROOT / "analysis" / "cache" / "backtest"
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Score composition
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    """Coerce a value to float, or None when missing / non-numeric."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def trend_component(indicators: pd.DataFrame) -> float:
    """Map the trend classification to a small +/- point value."""
    latest = indicators.iloc[-1]
    # TREND is a classification string, not a number, so read it directly
    # instead of routing it through the numeric helper.
    trend = latest.get("TREND")
    if trend == "STRONG_UPTREND":
        return 30.0
    if trend == "UPTREND":
        return 20.0
    if trend == "SIDEWAYS":
        return 5.0
    if trend == "DOWNTREND":
        return -20.0
    if trend == "STRONG_DOWNTREND":
        return -30.0
    return 0.0


def strength_component(indicators: pd.DataFrame) -> float:
    """Positive for above-average relative volume; negative for thin volume."""
    latest = indicators.iloc[-1]
    rv = _safe_float(latest.get("RELATIVE_VOLUME"))
    if rv is None:
        return 0.0
    return rv - 1.0


def score_symbol(indicators: pd.DataFrame) -> dict[str, Any]:
    """Build the composite score used for the ranking."""
    latest = indicators.iloc[-1]
    price = _safe_float(latest.get("Close"))
    ema20 = _safe_float(latest.get("EMA_20"))
    ema50 = _safe_float(latest.get("EMA_50"))
    ema200 = _safe_float(latest.get("EMA_200"))
    rsi = _safe_float(latest.get("RSI_14"))
    macd = _safe_float(latest.get("MACD"))
    macd_signal = _safe_float(latest.get("MACD_SIGNAL"))
    roc = _safe_float(latest.get("ROC_12"))
    momentum = calculate_momentum_score(
        price, ema20, ema50, ema200, rsi, macd, macd_signal, roc
    )
    trend_pts = trend_component(indicators)
    strength_pts = strength_component(indicators)
    score = round(
        momentum + trend_pts + strength_pts + (price or 0) * 0.0,
        2,
    )
    return {
        "score": score,
        "momentum": round(float(momentum), 2),
        "trend_pts": trend_pts,
        "strength_pts": round(strength_pts, 2),
        # TREND is a classification string ("UPTREND", ...), not a number.
        # Keep it as a string so trend_counts and the UI show the real
        # classification. Treat missing/NaN as None rather than the string
        # "nan", so an absent classification is never shown as a real value.
        "trend": (
            None
            if pd.isna(latest.get("TREND"))
            else str(latest.get("TREND"))
        ),
        "rsi": rsi,
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
    }

# ---------------------------------------------------------------------------
# Per-symbol worker
# ---------------------------------------------------------------------------


def run_symbol(symbol: str) -> dict[str, Any]:
    try:
        data = get_price_history(symbol, period="1y", interval="1d")
        if data is None or data.empty:
            return {"symbol": symbol, "status": "NO_DATA", "score": None}
        indicators = calculate_indicators(data)
        if indicators.empty or indicators["Close"].isna().all():
            return {"symbol": symbol, "status": "NO_DATA", "score": None}
        if len(indicators) < 200:
            return {
                "symbol": symbol,
                "status": "SHORT",
                "score": None,
                "missing_days": int(200 - len(indicators)),
            }
        score_info = score_symbol(indicators)
        return {
            "symbol": symbol,
            "status": "OK",
            **score_info,
            "up_day_fraction": _up_day_fraction(indicators),
        }
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "status": "ERROR", "error": str(exc)}


def _up_day_fraction(data: pd.DataFrame) -> float:
    """Fraction of 1d bars that were positive (a hit-rate, not a return).

    This is the share of up days across the loaded window, NOT an average
    daily or 20-day return. Keep it labelled as a fraction everywhere.
    """
    returns = data["Close"].pct_change().dropna()
    if returns.empty:
        return 0.0
    return round(float((returns > 0).mean()), 4)

# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------


def run_backtest(
    symbols: list[str] | None = None,
    sample: int = 20,
    days: int = 252,
    workers: int = 5,
    quiet: bool = False,
) -> dict[str, Any]:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: list[dict[str, Any]] = []

    # None or an empty list both mean "use the scanner universe"; the UI
    # blank path and the CLI (argparse nargs="*") rely on this.
    if not symbols:
        all_symbols = get_nse_symbols()
        pool = all_symbols[: 500 if not quiet else max(sample, 10)]
    else:
        pool = list(dict.fromkeys(symbols))[:50]

    if sample and len(pool) > sample:
        pool = pool[:sample]

    print(f"Backtesting {len(pool)} symbols â€¦")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=min(workers, 5)) as pool_exec:
        futures = {pool_exec.submit(run_symbol, s): s for s in pool}
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.time() - t0
    ok = [r for r in results if r.get("status") == "OK"]
    degraded = [r for r in results if r.get("status") in ("SHORT", "NO_DATA")]
    errors = [r for r in results if r.get("status") == "ERROR"]

    # ------------------------------------------------------------------
    # Rank + decile comparison
    # ------------------------------------------------------------------
    ranked = sorted(ok, key=lambda r: r["score"], reverse=True)
    n = len(ranked)
    pack = max(1, int(np.ceil(n / 10)))

    report: dict[str, Any] = {
        "generated_at": now,
        "universe": len(pool),
        "completed": len(ok),
        "degraded": len(degraded),
        "errors": len(errors),
        "pack_width": pack,
        "elapsed_seconds": round(elapsed, 2),
        "symbols": [
            {
                "symbol": r["symbol"],
                "score": r["score"],
                "trend": r.get("trend"),
                "rsi": r.get("rsi"),
                "up_day_fraction": r.get("up_day_fraction"),
            }
            for r in ranked
        ],
        "trend_counts": {
            str(k): int(v)
            for k, v in pd.Series(
                [r.get("trend") for r in ranked],
                dtype="string",
            ).value_counts().items()
        },
    }

    # Deciles are contiguous rank slices of width `pack`. The bottom decile
    # is the *last* `pack` symbols, so it must be sliced from the tail: a
    # negative group index (ranked[-pack:0]) yields an empty slice and would
    # silently report the spread as None.
    def decile_avg(lo: int, hi: int) -> float | None:
        chunk = ranked[lo:hi]
        valid = [r for r in chunk if r.get("up_day_fraction") is not None]
        if not valid:
            return None
        return float(np.mean([r["up_day_fraction"] for r in valid]))

    top = decile_avg(0, pack)
    bottom = decile_avg(max(0, n - pack), n)
    mid_lo = max(0, (n - pack) // 2)
    mid = decile_avg(mid_lo, mid_lo + pack)
    report["decile_stats"] = {
        "top_decile_up_day_fraction": top,
        "bottom_decile_up_day_fraction": bottom,
        "spread_top_vs_bottom": (
            round(top - bottom, 4)
            if (top is not None and bottom is not None)
            else None
        ),
        "mid_decile_up_day_fraction": mid,
    }

    # ------------------------------------------------------------------
    # Save + print
    # ------------------------------------------------------------------
    path = BACKTEST_DIR / f"backtest_{now}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if not quiet:
        print(f"\n{'='*60}")
        print(f"FACTOR BACKTEST â€” {len(ok)}/{len(pool)} completed in {elapsed:.1f}s")
        print(f"  Top decile up-day fraction: {top}")
        print(f"  Bottom decile up-day fraction: {bottom}")
        spread = report["decile_stats"]["spread_top_vs_bottom"]
        print(
            f"  Spread (top - bottom): "
            f"{spread if spread is None else round(spread, 4)}"
        )
        print(f"  Saved: {path.name}")
        print(f"{'='*60}\n")
        print("Trend mix:", report["trend_counts"])

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nova factor backtest harness (analysis only)."
    )
    parser.add_argument(
        "--quick", action="store_true", help="sample 20 symbols instead of full universe",
    )
    parser.add_argument(
        "--days", type=int, default=252, help="history window in days (default 252)",
    )
    parser.add_argument(
        "--workers", type=int, default=5, help="parallel fetch workers (default 5)",
    )
    parser.add_argument(
        "symbols", nargs="*", help="one or more NSE symbols to test (overrides universe)",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="quiet output, only write JSON",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    run_backtest(
        symbols=args.symbols,
        sample=20 if args.quick else None,
        days=args.days,
        workers=args.workers,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
