"""AI interpretation of the saved report (Market Lab brain, local Ollama) for Nova Desk.

Read-only: the brain only reads the saved report and live quotes. Guarded like
/refresh because each call ties up the local model for a while.
"""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from market_lab import market_lab_brain as brain
from market_lab import view_model as vm
from web.api import ttl_cache
from web.api.report_loader import load_cached_report
from web.api.routes import stock as stock_route
from web.api.routes.events import forbidden

router = APIRouter()

_TTL = 900  # same question on the same report is answered once
_cache: dict = {}
MAX_QUESTION = 500


def _stock_report(symbol: str, question: str, report: dict | None) -> str:
    # reuse the Stock page's cached sheet: a rebuild costs ~15 s on top of the model call
    built = ttl_cache.get(stock_route._stock_cache, symbol, stock_route._STOCK_TTL) or stock_route._build(symbol)
    candles = [{"t": c["time"]} for c in built["chart"]["candles"]]
    return brain.analyze_stock_report(symbol, built["analysis"], candles, report,
                                      mode="quick" if "quick" in question.lower() else "full")


@router.post("/interpret")
async def interpret(request: Request):
    if reason := forbidden(request, "interpret"):
        return JSONResponse({"error": reason}, status_code=403)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    question = str(body.get("q") or "").strip()[:MAX_QUESTION]
    symbol = str(body.get("symbol") or "").strip().upper()
    if symbol and stock_route._bad_symbol(symbol):
        return JSONResponse({"error": f"Invalid symbol: {symbol}"}, status_code=400)
    saved = load_cached_report()
    report = saved["report"] if saved else None
    if report is None and not symbol:
        return JSONResponse({"error": "No saved report yet. Run a refresh first."}, status_code=503)
    key = (symbol, question, saved["saved_at"] if saved else None)
    if hit := ttl_cache.get(_cache, key, _TTL):
        return hit
    try:
        # the saved report is passed in, so the brain never waits on the data engine (or a running scan)
        if symbol:
            text = await asyncio.to_thread(_stock_report, symbol, question, report)
        else:
            text = await asyncio.to_thread(brain.analyze_market_lab, question, report=report)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": f"Interpretation failed: {e}"}, status_code=502)
    data = {"text": text, "model": f"Ollama {brain.MODEL}", "report_saved_at": saved["saved_at"] if saved else None,
            "guardrails": vm.guardrails(report or {})}
    if not text.startswith(("MARKET LAB", "STOCK ANALYSIS")):  # engine error strings are not worth caching
        ttl_cache.put(_cache, key, data, _TTL)
    return data
