"""
F&O desk for the three index option markets: NIFTY, BANKNIFTY (NSE) and
SENSEX (BSE).

Live option chains:
- NSE via derivatives_engine (NSE option chain v3, curl_cffi session).
- BSE via its public BseIndiaAPI (DerivOptionChain_IV); normalized to the
  same columns as the NSE rows.
Spot technicals and realized volatility come from Yahoo daily history.

All numbers are computed from the chain/history; missing inputs stay None.
The "desk read" is a plain description of positioning, never a trade call.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

INSTRUMENTS = {
    "NIFTY": {"name": "NIFTY 50", "exchange": "NSE", "yahoo": "^NSEI"},
    "BANKNIFTY": {"name": "BANK NIFTY", "exchange": "NSE", "yahoo": "^NSEBANK"},
    "SENSEX": {"name": "SENSEX", "exchange": "BSE", "yahoo": "^BSESN"},
}
IST = timezone(timedelta(hours=5, minutes=30))
CHAIN_COLS = ["strike", "call_oi", "call_change_oi", "call_volume", "call_iv", "call_ltp",
              "put_oi", "put_change_oi", "put_volume", "put_iv", "put_ltp"]
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_HEADERS = {"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com", "Accept": "application/json"}


def _num(v: Any) -> Optional[float]:
    if isinstance(v, str):
        v = v.replace(",", "").strip()
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ---------------------------------------------------------------- chain fetchers

def fetch_nse_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    from analysis.data import derivatives_engine as de
    payload, selected = de.fetch_option_chain_json(symbol, requested_expiry=expiry)
    spot = de.get_underlying_value(payload)
    df = de.extract_option_rows(payload, selected)
    return {"spot": spot, "expiry": selected, "expiries": de.extract_expiry_dates(payload)[:8],
            "rows": df[[c for c in CHAIN_COLS if c in df.columns]], "source": "NSE option chain"}


def parse_bse_chain(table: list[dict]) -> pd.DataFrame:
    """BSE rows: C_* fields are the call leg, unprefixed fields the put leg."""
    rows = [{
        "strike": _num(r.get("Strike_Price1") or r.get("Strike_Price")),
        "call_oi": _num(r.get("C_Open_Interest")), "call_change_oi": _num(r.get("C_Absolute_Change_OI")),
        "call_volume": _num(r.get("C_Vol_Traded")), "call_iv": _num(r.get("C_IV")), "call_ltp": _num(r.get("C_Last_Trd_Price")),
        "put_oi": _num(r.get("Open_Interest")), "put_change_oi": _num(r.get("Absolute_Change_OI")),
        "put_volume": _num(r.get("Vol_Traded")), "put_iv": _num(r.get("IV")), "put_ltp": _num(r.get("Last_Trd_Price")),
    } for r in table if isinstance(r, dict)]
    df = pd.DataFrame([r for r in rows if r["strike"] is not None], columns=CHAIN_COLS)
    return df.sort_values("strike").reset_index(drop=True)


def fetch_bse_chain(expiry: Optional[str] = None) -> dict:
    from curl_cffi import requests
    s = requests.Session(impersonate="chrome")
    meta = s.get(f"{BSE_API}/ddlExpiry_IV/w?ProductType=IO&scrip_cd=1", headers=BSE_HEADERS, timeout=20).json()
    expiries = [e["ExpiryDate"] for e in meta.get("Table1", []) if e.get("ExpiryDate")]
    if not expiries:
        raise RuntimeError("BSE returned no SENSEX expiries")
    chosen = expiry if expiry in expiries else expiries[0]
    j = s.get(f"{BSE_API}/DerivOptionChain_IV/w", params={"Expiry": chosen, "scrip_cd": 1, "strprice": 0},
              headers=BSE_HEADERS, timeout=20).json()
    table = j.get("Table") or []
    if not table:
        raise RuntimeError(f"BSE returned an empty SENSEX chain for {chosen}")
    spot = _num(table[0].get("UlaValue")) or _num((meta.get("Table2") or [{}])[0].get("UlaValue"))
    return {"spot": spot, "expiry": chosen, "expiries": expiries[:8], "rows": parse_bse_chain(table),
            "source": f"BSE option chain ({(j.get('ASON') or {}).get('DT_TM', '').strip()})"}


# ---------------------------------------------------------------- chain analytics

def _expiry_date(s: str) -> Optional[date]:
    for fmt in ("%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def max_pain(df: pd.DataFrame) -> Optional[float]:
    """Settlement strike that minimizes total intrinsic value paid to option holders."""
    k = df["strike"].to_numpy(float)
    c = df["call_oi"].fillna(0).to_numpy(float)
    p = df["put_oi"].fillna(0).to_numpy(float)
    if len(k) == 0 or (c.sum() + p.sum()) == 0:
        return None
    s = k[:, None]  # candidate settlements x strikes
    pain = (c * np.maximum(s - k, 0) + p * np.maximum(k - s, 0)).sum(axis=1)
    return float(k[int(pain.argmin())])


def _iv(v: Any) -> Optional[float]:
    v = _num(v)
    return v if v and v > 0 else None  # exchanges send 0 for "no IV"


def chain_metrics(df: pd.DataFrame, spot: float, expiry: str, today: Optional[date] = None, window: int = 15) -> dict:
    df = df.dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True)
    if df.empty or not spot:
        raise ValueError("empty chain or no spot")
    today = today or date.today()
    i_atm = int((df["strike"] - spot).abs().idxmin())
    atm = df.loc[i_atm]
    tot = lambda col: float(df[col].fillna(0).sum())  # noqa: E731

    call_oi, put_oi = tot("call_oi"), tot("put_oi")
    d_call, d_put = tot("call_change_oi"), tot("put_change_oi")
    straddle = (_num(atm["call_ltp"]) or 0) + (_num(atm["put_ltp"]) or 0) if _num(atm["call_ltp"]) and _num(atm["put_ltp"]) else None
    ivs = [x for x in (_iv(atm["call_iv"]), _iv(atm["put_iv"])) if x]

    def nearest(target, col):
        sub = df[df[col].map(_iv).notna()]
        return None if sub.empty else sub.loc[(sub["strike"] - target).abs().idxmin()]

    otm_put, otm_call = nearest(spot * 0.97, "put_iv"), nearest(spot * 1.03, "call_iv")
    skew = _iv(otm_put["put_iv"]) - _iv(otm_call["call_iv"]) if otm_put is not None and otm_call is not None else None

    above, below = df[df["strike"] > spot], df[df["strike"] < spot]
    def top(frame, col, n=3):
        leg = col.split("_")[0]  # "call" / "put"
        return [{"strike": float(r["strike"]), "oi": _num(r[f"{leg}_oi"]), "change_oi": _num(r[f"{leg}_change_oi"])}
                for _, r in frame.nlargest(n, col).iterrows() if _num(r[col])]
    exp_d = _expiry_date(expiry)
    win = df.iloc[max(0, i_atm - window): i_atm + window + 1]

    return {
        "atm": float(atm["strike"]),
        "days_to_expiry": (exp_d - today).days if exp_d else None,
        "pcr_oi": put_oi / call_oi if call_oi else None,
        "pcr_volume": tot("put_volume") / tot("call_volume") if tot("call_volume") else None,
        "pcr_change_oi": d_put / d_call if d_call > 0 and d_put >= 0 else None,
        "call_oi": call_oi, "put_oi": put_oi, "call_change_oi": d_call, "put_change_oi": d_put,
        "max_pain": max_pain(df),
        "atm_iv": sum(ivs) / len(ivs) if ivs else None,
        "atm_call_iv": _iv(atm["call_iv"]), "atm_put_iv": _iv(atm["put_iv"]),
        "skew": skew,
        "straddle": straddle,
        "expected_move_pct": straddle / spot * 100 if straddle else None,
        "breakeven_low": float(atm["strike"]) - straddle if straddle else None,
        "breakeven_high": float(atm["strike"]) + straddle if straddle else None,
        "resistance": top(above, "call_oi"),
        "support": top(below, "put_oi"),
        "fresh_call_writing": top(df, "call_change_oi", 1),
        "fresh_put_writing": top(df, "put_change_oi", 1),
        "profile": [{k: (None if (isinstance(v, float) and not math.isfinite(v)) else v) for k, v in r.items()}
                    for r in win[CHAIN_COLS].to_dict("records")],
    }


# ---------------------------------------------------------------- spot technicals

def spot_technicals(closes: pd.DataFrame, now: Optional[datetime] = None) -> dict:
    """closes: daily OHLC (High, Low, Close) oldest first."""
    c, h, l = closes["Close"], closes["High"], closes["Low"]
    if len(c) < 30:
        raise ValueError("not enough history")
    prev_c, prev_h, prev_l = float(c.iloc[-2]), float(h.iloc[-2]), float(l.iloc[-2])
    last = float(c.iloc[-1])
    ema = {n: float(c.ewm(span=n, adjust=False).mean().iloc[-1]) for n in (20, 50, 200) if len(c) >= n}
    delta = c.diff()
    gain, loss = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1])) if loss.iloc[-1] else 100.0
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    rv20 = float(np.log(c).diff().tail(20).std() * math.sqrt(252) * 100)
    # classic floor pivots from the last completed session: today's bar is partial until 15:30 IST
    ist = (now or datetime.now(timezone.utc)).astimezone(IST)
    live = str(c.index[-1])[:10] == ist.date().isoformat() and (ist.hour, ist.minute) < (15, 30)
    j = -2 if live else -1
    ph, pl, pc = float(h.iloc[j]), float(l.iloc[j]), float(c.iloc[j])
    pp = (ph + pl + pc) / 3
    hi52, lo52 = float(h.tail(252).max()), float(l.tail(252).min())
    ret = lambda n: (last / float(c.iloc[-1 - n]) - 1) * 100 if len(c) > n else None  # noqa: E731
    return {
        "last": last, "prev_close": prev_c, "change": last - prev_c, "change_pct": (last / prev_c - 1) * 100,
        "day_high": float(h.iloc[-1]), "day_low": float(l.iloc[-1]), "prev_high": prev_h, "prev_low": prev_l,
        "as_of": str(c.index[-1])[:10],
        "ema": ema, "rsi": rsi, "atr": atr, "atr_pct": atr / last * 100, "rv20": rv20,
        "pivots": {"r2": pp + (ph - pl), "r1": 2 * pp - pl, "pp": pp, "s1": 2 * pp - ph, "s2": pp - (ph - pl),
                   "from": str(c.index[j])[:10]},
        "high_52w": hi52, "low_52w": lo52,
        "returns": {"5d": ret(5), "20d": ret(20), "60d": ret(60)},
    }


def daily_candles(hist: pd.DataFrame, n: int = 180) -> list[dict]:
    """Last n daily bars for the desk chart; rows with any missing OHLC are dropped, not filled."""
    cols = ["Open", "High", "Low", "Close"]
    if not set(cols) <= set(hist.columns):
        return []
    tail = hist[cols].dropna().tail(n)
    return [{"t": str(i)[:10], "o": float(r.Open), "h": float(r.High), "l": float(r.Low), "c": float(r.Close)}
            for i, r in tail.iterrows()]


def fetch_spot_history(yahoo: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.Ticker(yahoo).history(period="2y", interval="1d", auto_adjust=False)
    return df.dropna(subset=["Close"])


# ---------------------------------------------------------------- desk read

def desk_read(spot: float, m: Optional[dict], t: Optional[dict]) -> list[dict]:
    """Plain lines describing positioning. tone: positive | negative | neutral. Never a trade call."""
    out: list[dict] = []

    def add(tone, topic, text):
        out.append({"tone": tone, "topic": topic, "text": text})

    if m:
        pcr = m.get("pcr_oi")
        if pcr is not None:
            if pcr >= 1.2:
                add("positive", "PCR", f"OI PCR {pcr:.2f}: put-heavy, writers are defending lower strikes")
            elif pcr <= 0.7:
                add("negative", "PCR", f"OI PCR {pcr:.2f}: call-heavy, writers are capping upside")
            else:
                add("neutral", "PCR", f"OI PCR {pcr:.2f}: balanced positioning")
        dc, dp = m.get("call_change_oi") or 0, m.get("put_change_oi") or 0
        if dc or dp:
            if dp > dc * 1.3:
                add("positive", "Fresh OI", f"Put OI added faster than calls today (+{dp:,.0f} vs +{dc:,.0f})")
            elif dc > dp * 1.3:
                add("negative", "Fresh OI", f"Call OI added faster than puts today (+{dc:,.0f} vs +{dp:,.0f})")
            else:
                add("neutral", "Fresh OI", f"Call and put OI added at a similar pace (+{dc:,.0f} / +{dp:,.0f})")
        res, sup = (m.get("resistance") or [None])[0], (m.get("support") or [None])[0]
        if res and sup:
            add("neutral", "OI range", f"Heaviest call OI at {res['strike']:,.0f} ({(res['strike'] / spot - 1) * 100:+.1f}%), "
                                       f"heaviest put OI at {sup['strike']:,.0f} ({(sup['strike'] / spot - 1) * 100:+.1f}%)")
        mp = m.get("max_pain")
        if mp:
            gap = (mp / spot - 1) * 100
            add("neutral", "Max pain", f"Max pain {mp:,.0f}, {abs(gap):.1f}% {'above' if gap > 0 else 'below'} spot"
                + (f" with {m['days_to_expiry']} day(s) to expiry" if m.get("days_to_expiry") is not None else ""))
        if m.get("straddle"):
            add("neutral", "Expected move", f"ATM straddle {m['straddle']:,.0f} prices a ±{m['expected_move_pct']:.2f}% move by expiry "
                                            f"({m['breakeven_low']:,.0f} to {m['breakeven_high']:,.0f})")
        if m.get("skew") is not None:
            sk = m["skew"]
            add("negative" if sk > 2 else "neutral", "Skew",
                f"3% OTM put IV is {abs(sk):.1f} vol pts {'above' if sk >= 0 else 'below'} the 3% OTM call"
                + (": demand for downside protection" if sk > 2 else ""))
    if m and t and m.get("atm_iv") and t.get("rv20"):
        prem = m["atm_iv"] - t["rv20"]
        add("negative" if prem < -2 else "neutral", "Vol",
            f"ATM IV {m['atm_iv']:.1f}% vs 20-day realized {t['rv20']:.1f}%: options {'rich' if prem > 2 else 'cheap' if prem < -2 else 'fairly priced'} to recent movement")
    if t:
        e = t.get("ema", {})
        above = [n for n, v in e.items() if spot > v]
        if e:
            tone = "positive" if len(above) == len(e) else "negative" if not above else "neutral"
            add(tone, "Trend", f"Spot above {len(above)} of {len(e)} EMAs ({', '.join(f'{n}' for n in sorted(e))}); RSI {t['rsi']:.0f}")
    return out


# ---------------------------------------------------------------- assembly

def build_fno(instrument: str, expiry: Optional[str] = None, today: Optional[date] = None) -> dict:
    key = re.sub(r"[^A-Z]", "", instrument.upper())
    if key not in INSTRUMENTS:
        raise ValueError(f"Unsupported instrument: {instrument}")
    meta = INSTRUMENTS[key]
    errors: dict = {}

    chain = metrics = tech = None
    try:
        chain = fetch_bse_chain(expiry) if key == "SENSEX" else fetch_nse_chain(key, expiry)
    except Exception as exc:
        errors["chain"] = f"{meta['exchange']} option chain unavailable: {exc}"
    try:
        hist = fetch_spot_history(meta["yahoo"])
        tech = spot_technicals(hist)
        tech["candles"] = daily_candles(hist)
    except Exception as exc:
        errors["technicals"] = f"Spot history unavailable: {exc}"

    spot = (chain or {}).get("spot") or (tech or {}).get("last")
    if chain and spot:
        try:
            metrics = chain_metrics(chain["rows"], spot, chain["expiry"], today=today)
        except Exception as exc:
            errors["chain"] = f"Could not analyze chain: {exc}"

    return {
        "instrument": key, "name": meta["name"], "exchange": meta["exchange"],
        "spot": spot,
        "expiry": (chain or {}).get("expiry"), "expiries": (chain or {}).get("expiries", []),
        "source": (chain or {}).get("source"),
        "metrics": metrics, "technicals": tech,
        "read": desk_read(spot, metrics, tech) if spot else [],
        "errors": errors,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
