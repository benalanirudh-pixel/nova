"""Multi-year research from the local price store: factor backtest and daily breadth. Read-only; never downloads."""
import asyncio
import threading

from fastapi import APIRouter

from analysis.data import price_store, research_engine as rs
from market_lab import view_model as vm

router = APIRouter()

LIQUID_N = 500
_lock = threading.Lock()   # the first build reads millions of rows; concurrent callers wait for one build
_cache: dict = {}


def _series(frame) -> dict:
    return {"dates": [str(d.date()) for d in frame.index],
            **{c: [None if v != v else round(float(v), 2) for v in frame[c]] for c in frame.columns}}


def build() -> dict:
    st = price_store.status()
    if not st["available"]:
        return {"available": False, "reason": "The price store is empty. Run: python -m analysis.data.price_store --backfill 2021-01-01", "store": st}
    key = (st["last"], st["sessions"])
    with _lock:
        if _cache.get("key") != key:
            panels = price_store.panels()
            _cache.clear()
            _cache.update(key=key, body={
                "available": True, "store": st,
                "backtest": rs.factor_backtest(panels, top_n=LIQUID_N),
                "breadth": {"all": _series(rs.breadth_series(panels)), "liquid": _series(rs.breadth_series(panels, top_n=LIQUID_N)), "liquid_n": LIQUID_N},
            })
        return _cache["body"]


@router.get("/research/overview")
async def overview():
    body = await asyncio.to_thread(build)
    return {**body, "guardrails": vm.guardrails({})}


@router.get("/research/status")
def store_status():
    return {"store": price_store.status(), "guardrails": vm.guardrails({})}
