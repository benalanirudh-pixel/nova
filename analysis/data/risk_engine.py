"""
NOVA RISK ENGINE
----------------
Purpose:
- Market risk context for NIFTY and BANK NIFTY.
- Risk-budget and position-risk calculations.
- ATR, volatility and risk/reward metrics.
- Explicit warnings when institutional-flow history is not
  fully verified.

Safety:
- Analysis only.
- No broker integration.
- No order placement.
- No buy/sell authorization.
"""

from __future__ import annotations

import math
from typing import Any, Optional


# ============================================================
# CONSTANTS
# ============================================================

ENGINE_NAME = "NOVA RISK ENGINE"
ENGINE_VERSION = "1.1.0"

EXECUTION_ENABLED = False
BUY_SELL_AUTHORIZATION = False


# ============================================================
# SAFE VALUE HELPERS
# ============================================================

def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to a finite float; otherwise return None."""

    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _first_number(
    source: dict[str, Any],
    *keys: str,
) -> Optional[float]:
    """Return the first valid numeric value found in the given keys."""

    for key in keys:
        value = _safe_float(source.get(key))

        if value is not None:
            return value

    return None


def _round_value(
    value: Optional[float],
    digits: int = 4,
) -> Optional[float]:
    """Round a numeric value without changing missing values."""

    if value is None:
        return None

    return round(value, digits)


# ============================================================
# POSITION RISK CALCULATOR
# ============================================================

def calculate_position_risk(
    entry_price: float,
    stop_price: float,
    target_price: float,
    account_equity: float,
    risk_pct: float = 0.5,
) -> dict[str, Any]:
    """
    Calculate a theoretical position-risk estimate.

    Parameters
    ----------
    entry_price:
        Assumed entry price per unit.

    stop_price:
        Assumed stop-loss price per unit.

    target_price:
        Assumed target price per unit.

    account_equity:
        Account equity expressed in currency units.

    risk_pct:
        Maximum theoretical account-equity risk percentage.
        For example, 0.5 means 0.5%, not 50%.

    Notes
    -----
    This function does not place orders or connect to a broker.
    It does not account automatically for brokerage, taxes,
    slippage, gaps, liquidity or contract lot sizes.
    """

    entry = _safe_float(entry_price)
    stop = _safe_float(stop_price)
    target = _safe_float(target_price)
    equity = _safe_float(account_equity)
    risk_percent = _safe_float(risk_pct)

    result: dict[str, Any] = {
        "available": False,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "risk_budget": None,
        "risk_per_unit": None,
        "reward_per_unit": None,
        "quantity": 0,
        "position_value": None,
        "estimated_stop_loss": None,
        "estimated_target_profit": None,
        "risk_reward_ratio": None,
        "risk_pct": risk_percent,
        "warnings": [],
        "execution_enabled": False,
        "buy_sell_authorization": False,
    }

    # --------------------------------------------------------
    # INPUT VALIDATION
    # --------------------------------------------------------

    if entry is None or entry <= 0:
        result["reason"] = "Entry price must be greater than zero."
        return result

    if stop is None or stop <= 0:
        result["reason"] = "Stop price must be greater than zero."
        return result

    if target is None or target <= 0:
        result["reason"] = "Target price must be greater than zero."
        return result

    if equity is None or equity <= 0:
        result["reason"] = "Account equity must be greater than zero."
        return result

    if risk_percent is None or not 0 < risk_percent <= 100:
        result["reason"] = (
            "Risk percentage must be greater than 0 and at most 100."
        )
        return result

    # --------------------------------------------------------
    # RISK AND REWARD
    # --------------------------------------------------------

    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(target - entry)

    if risk_per_unit <= 0:
        result["reason"] = (
            "Entry and stop prices must be different."
        )
        return result

    if reward_per_unit <= 0:
        result["reason"] = (
            "Entry and target prices must be different."
        )
        return result

    # --------------------------------------------------------
    # POSITION SIZE
    # --------------------------------------------------------

    risk_budget = equity * (risk_percent / 100.0)

    # Whole units only. Derivative lot-size rules must be
    # applied separately before using this estimate.
    quantity = int(risk_budget // risk_per_unit)

    position_value = entry * quantity
    estimated_stop_loss = risk_per_unit * quantity
    estimated_target_profit = reward_per_unit * quantity
    risk_reward_ratio = reward_per_unit / risk_per_unit

    result.update(
        {
            "available": True,
            "reason": "Risk calculation completed.",
            "entry_price": _round_value(entry, 4),
            "stop_price": _round_value(stop, 4),
            "target_price": _round_value(target, 4),
            "account_equity": _round_value(equity, 2),
            "risk_budget": _round_value(risk_budget, 2),
            "risk_per_unit": _round_value(risk_per_unit, 4),
            "reward_per_unit": _round_value(reward_per_unit, 4),
            "quantity": quantity,
            "position_value": _round_value(position_value, 2),
            "estimated_stop_loss": _round_value(
                estimated_stop_loss, 2
            ),
            "estimated_target_profit": _round_value(
                estimated_target_profit, 2
            ),
            "risk_reward_ratio": _round_value(
                risk_reward_ratio, 4
            ),
        }
    )

    # --------------------------------------------------------
    # WARNINGS
    # --------------------------------------------------------

    warnings: list[str] = []

    if quantity == 0:
        warnings.append(
            "Risk budget is smaller than the risk per unit."
        )

    if quantity > 0 and position_value > equity:
        warnings.append(
            "Estimated position value exceeds account equity; "
            "leverage or additional capital may be required."
        )

    if (entry > stop and target < entry) or (
        entry < stop and target > entry
    ):
        warnings.append(
            "Stop and target appear to be on the same side of entry. "
            "Verify whether the intended scenario is long or short."
        )

    warnings.append(
        "Theoretical estimate only. Costs, slippage, gaps and "
        "instrument lot sizes are not included."
    )

    result["warnings"] = warnings

    return result


# ============================================================
# MARKET VOLATILITY NORMALIZATION
# ============================================================

def _build_instrument_context(
    source: Any,
    instrument_name: str,
) -> dict[str, Any]:
    """
    Normalize a Market Lab volatility block.

    The Market Lab source uses keys such as:
        atr14
        atr_percent
        realized_volatility_20d
        realized_volatility_60d
        expected_daily_move_percent
    """

    if not isinstance(source, dict):
        source = {}

    source_available = bool(source.get("available", False))

    # Important fix:
    # The source field is atr14, not just atr.
    atr = _first_number(
        source,
        "atr14",
        "atr",
        "atr_14",
        "ATR",
    )

    atr_percent = _first_number(
        source,
        "atr_percent",
        "atr_pct",
        "atr_percentage",
    )

    realized_vol_20d = _first_number(
        source,
        "realized_volatility_20d",
        "realized_vol_20d",
        "rv20",
    )

    realized_vol_60d = _first_number(
        source,
        "realized_volatility_60d",
        "realized_vol_60d",
        "rv60",
    )

    expected_daily_move = _first_number(
        source,
        "expected_daily_move_percent",
        "expected_daily_move",
    )

    volatility_percentile = _first_number(
        source,
        "volatility_percentile",
        "vol_percentile",
    )

    expected_daily_range = _first_number(
        source,
        "expected_daily_range",
    )

    price = _first_number(
        source,
        "price",
        "last_price",
        "close",
    )

    volatility_regime = str(
        source.get("volatility_regime") or "UNKNOWN"
    ).upper()

    volatility_direction = str(
        source.get("volatility_direction") or "UNKNOWN"
    ).upper()

    available = (
        source_available
        and any(
            value is not None
            for value in (
                atr,
                atr_percent,
                realized_vol_20d,
                realized_vol_60d,
                expected_daily_move,
            )
        )
    )

    return {
        "name": instrument_name,
        "available": available,
        "price": _round_value(price, 4),
        "atr": _round_value(atr, 4),
        "atr_pct": _round_value(atr_percent, 4),
        "expected_daily_move_percent": _round_value(
            expected_daily_move, 4
        ),
        "expected_daily_range": _round_value(
            expected_daily_range, 4
        ),
        "realized_volatility_20d": _round_value(
            realized_vol_20d, 4
        ),
        "realized_volatility_60d": _round_value(
            realized_vol_60d, 4
        ),
        "volatility_percentile": _round_value(
            volatility_percentile, 4
        ),
        "volatility_regime": volatility_regime,
        "volatility_direction": volatility_direction,
    }


# ============================================================
# MARKET RISK CONTEXT
# ============================================================

def build_market_risk_context(
    volatility: dict[str, Any],
    market_regime: Optional[str],
    institutional_flow: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build a risk-only context from Nova Market Lab data.

    Expected volatility structure:
        {
            "nifty": {...},
            "bank_nifty": {...},
            "india_vix": {...}
        }

    Institutional flow is used only to add data-quality warnings.
    It does not authorize or generate buy/sell instructions.
    """

    if not isinstance(volatility, dict):
        volatility = {}

    if not isinstance(institutional_flow, dict):
        institutional_flow = {}

    # --------------------------------------------------------
    # INSTRUMENT CONTEXT
    # --------------------------------------------------------

    nifty = _build_instrument_context(
        volatility.get("nifty"),
        "NIFTY",
    )

    bank_nifty = _build_instrument_context(
        volatility.get("bank_nifty"),
        "BANK NIFTY",
    )

    instruments = {
        "nifty": nifty,
        "bank_nifty": bank_nifty,
    }

    available = any(
        item.get("available", False)
        for item in instruments.values()
    )

    # --------------------------------------------------------
    # WARNINGS
    # --------------------------------------------------------

    warnings: list[str] = []

    if not nifty["available"]:
        warnings.append(
            "NIFTY volatility metrics are unavailable or incomplete."
        )

    if not bank_nifty["available"]:
        warnings.append(
            "BANK NIFTY volatility metrics are unavailable or incomplete."
        )

    # Institutional-flow source-quality safeguard.
    primary_history_verified = institutional_flow.get(
        "primary_only_history_verified"
    )

    signal_eligible = institutional_flow.get(
        "decision_support_eligible"
    )

    if primary_history_verified is False:
        warnings.append(
            "Institutional-flow history is not fully "
            "primary-source verified."
        )

    if signal_eligible is False:
        note = institutional_flow.get(
            "signal_eligibility_note"
        )

        if note:
            note = str(note).strip()

            if note and note not in warnings:
                warnings.append(note)

    # --------------------------------------------------------
    # FINAL CONTEXT
    # --------------------------------------------------------

    return {
        "available": available,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "purpose": "MARKET_RISK_CONTEXT_ONLY",
        "market_regime": (
            str(market_regime).upper()
            if market_regime
            else "UNKNOWN"
        ),
        "instruments": instruments,
        "warnings": warnings,
        "execution_enabled": False,
        "buy_sell_authorization": False,
    }


# ============================================================
# MODULE SELF-TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 64)
    print(ENGINE_NAME)
    print(f"Version: {ENGINE_VERSION}")
    print("=" * 64)

    sample_volatility = {
        "nifty": {
            "available": True,
            "price": 22520.45,
            "atr14": 263.48,
            "atr_percent": 1.17,
            "realized_volatility_20d": 13.7443,
            "realized_volatility_60d": 10.5428,
            "volatility_percentile": 74.01,
            "expected_daily_move_percent": 0.8658,
            "expected_daily_range": 194.98,
            "volatility_regime": "MODERATE",
            "volatility_direction": "EXPANDING",
        },
        "bank_nifty": {
            "available": True,
            "price": 55256.65,
            "atr14": 741.31,
            "atr_percent": 1.3416,
            "realized_volatility_20d": 14.7161,
            "realized_volatility_60d": 11.9669,
            "volatility_percentile": 48.90,
            "expected_daily_move_percent": 0.927,
            "expected_daily_range": 512.24,
            "volatility_regime": "MODERATE",
            "volatility_direction": "EXPANDING",
        },
    }

    sample_flow = {
        "primary_only_history_verified": False,
        "decision_support_eligible": False,
        "signal_eligibility_note": (
            "Signal eligibility blocked: the target history "
            "window is not entirely primary-source verified."
        ),
    }

    context = build_market_risk_context(
        volatility=sample_volatility,
        market_regime="BEARISH",
        institutional_flow=sample_flow,
    )

    for key, item in context["instruments"].items():
        print(
            f"{item['name']}: "
            f"available={item['available']}, "
            f"ATR={item['atr']}, "
            f"ATR%={item['atr_pct']}"
        )

    risk = calculate_position_risk(
        entry_price=100,
        stop_price=95,
        target_price=110,
        account_equity=100000,
        risk_pct=0.5,
    )

    print()
    print("Position risk self-test:")
    print(risk)

    assert context["instruments"]["nifty"]["atr"] == 263.48
    assert context["instruments"]["bank_nifty"]["atr"] == 741.31
    assert context["execution_enabled"] is False
    assert context["buy_sell_authorization"] is False

    assert risk["available"] is True
    assert risk["risk_budget"] == 500.0
    assert risk["risk_per_unit"] == 5.0
    assert risk["quantity"] == 100
    assert risk["estimated_stop_loss"] == 500.0
    assert risk["estimated_target_profit"] == 1000.0
    assert risk["risk_reward_ratio"] == 2.0

    print()
    print("SELF-TEST PASSED")