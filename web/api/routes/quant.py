"""Quant analytics for Nova Desk: market internals, sector rotation, out-of-sample factor spreads.

Read-only and cache-only: everything is computed from scan files already on disk. Never starts a scan.
"""
import glob
import os
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

from analysis.data import fno_desk, quant_engine as qe
from market_lab import view_model as vm
from web.api import universe
from market_lab.market_lab_data import CACHE_DIR
from web.api.routes.desk import MIN_COMPLETE_ROWS

router = APIRouter()

FACTOR_TARGET_DAYS = (7, 30)   # calendar gaps aimed at: about one week and one month of trading
MIN_GAP_DAYS = 3               # a base scan closer than this measures noise
HISTORY_POINTS = 30
_BENCH_TTL = 3600
_frames: dict = {}
_payload: dict = {}
_bench: dict = {}


def _file_date(path: str) -> str:
    m = re.search(r"_(\d{8})_\d{6}\.csv$", os.path.basename(path))
    return m.group(1) if m else ""


def _data_date(frame: pd.DataFrame, fallback: str) -> str:
    """The session the scan describes: a Saturday scan holds Friday's bars."""
    try:
        return str(pd.to_datetime(frame["timestamp"].dropna().astype(str).str.slice(0, 10)).max().date())
    except Exception:
        return f"{fallback[:4]}-{fallback[4:6]}-{fallback[6:]}"


def scan_frames() -> dict:
    """{"key", "sessions": [(data_date, prepared frame)] oldest first}. One complete scan per market session."""
    root = Path(CACHE_DIR)
    paths = sorted(glob.glob(str(root / "scanner" / "market_scan_*.csv")))
    enriched = sorted(glob.glob(str(root / "sector" / "sector_enriched_stocks_*.csv")))
    key = (paths[-1] if paths else None, len(paths), enriched[-1] if enriched else None)
    if _frames.get("key") == key:
        return _frames
    sectors: dict[str, str] = {}
    if enriched:
        try:
            m = pd.read_csv(enriched[-1], usecols=["symbol", "sector"])
            sectors = dict(zip(m["symbol"].astype(str), m["sector"].fillna("").astype(str)))
        except Exception:
            sectors = {}
    by_file_date: dict[str, list[str]] = {}
    for p in paths:
        by_file_date.setdefault(_file_date(p), []).append(p)
    sessions: dict[str, pd.DataFrame] = {}
    for fd, group in by_file_date.items():
        for p in reversed(group):  # newest scan of the day first; fall back when it is partial
            try:
                raw = pd.read_csv(p)
            except Exception:
                continue
            if len(raw) < MIN_COMPLETE_ROWS:
                continue
            raw["sector"] = raw["symbol"].astype(str).map(sectors).fillna("")
            sessions[_data_date(raw, fd)] = qe.prepare(raw)  # later file dates overwrite the same session
            break
    _frames.clear()
    _frames.update(key=key, sessions=sorted(sessions.items()))
    return _frames


def latest_frame():
    s = scan_frames()["sessions"]
    return s[-1] if s else (None, None)


def _factor_windows(sessions) -> list[dict]:
    now_date, now = sessions[-1]
    today = date.fromisoformat(now_date)
    older = [(d, f, (today - date.fromisoformat(d)).days) for d, f in sessions[:-1]]
    older = [x for x in older if x[2] >= MIN_GAP_DAYS]
    out, used = [], set()
    for target in FACTOR_TARGET_DAYS:
        if not older:
            break
        d, f, gap = min(older, key=lambda x: abs(x[2] - target))
        if d in used:
            continue
        used.add(d)
        out.append({"base_date": d, "to_date": now_date, "calendar_days": gap, **qe.factor_spreads(f, now)})
    return out


@router.get("/quant/internals")
def internals():
    frames = scan_frames()
    sessions = frames["sessions"]
    if not sessions:
        return {"available": False, "reason": "No complete scan on disk. Run a refresh to build one.", "guardrails": vm.guardrails({})}
    if _payload.get("key") != frames["key"]:
        as_of, now = sessions[-1]
        m, rot = qe.market_internals(now), qe.sector_rotation(now)
        windows = _factor_windows(sessions)
        _payload.clear()
        _payload.update(key=frames["key"], body={
            "available": True, "as_of": as_of, "stocks": int(len(now)), "engine": f"{qe.ENGINE_NAME} {qe.ENGINE_VERSION}",
            "internals": m, "rotation": rot, "factor_windows": windows,
            "breadth_history": [{"date": d, **qe.breadth_point(f)} for d, f in sessions[-HISTORY_POINTS:]][::-1],
            "read": qe.internals_read(m, rot, windows[0] if windows else None),
            "sector_map": bool(frames["key"][2]),
            "guardrails": vm.guardrails({}),
        })
    return _payload["body"]


def benchmark_close():
    """Nifty 50 daily closes, cached for an hour. (series | None, error | None)."""
    hit = _bench.get("v")
    if hit and time.monotonic() - hit[0] < _BENCH_TTL:
        return hit[1]
    try:
        out = (fno_desk.fetch_spot_history("^NSEI")["Close"], None)
        if not len(out[0]):
            out = (None, "Nifty history came back empty.")
    except Exception as e:
        out = (None, f"Nifty history unavailable: {e}")
    _bench["v"] = (time.monotonic(), out)
    return out


def stock_quant(symbol: str, history: pd.DataFrame) -> dict:
    """Risk profile from the stock's own history plus its scorecard against the saved scan."""
    bench, bench_error = benchmark_close()
    risk = qe.risk_profile(history, bench)
    if bench_error and isinstance(risk.get("benchmark"), dict):
        risk["benchmark"]["reason"] = bench_error
    whole = universe.ready()
    if whole:  # every listed stock, from the local price store
        as_of, frame, source = whole["as_of"], whole["frame"], "Local price store, every listed stock"
    else:
        (as_of, frame), source = latest_frame(), "Saved scan"
    card = qe.scorecard(frame, symbol) if frame is not None else {"status": "NOT_AVAILABLE", "reason": "No complete scan on disk."}
    return {"risk": risk, "scorecard": {**card, "scan_as_of": as_of, "universe_source": source}}
