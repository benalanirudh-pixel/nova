from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from web.api import live_feed, scheduler

router = APIRouter()


ALLOWED_ORIGINS = {"http://localhost:8501", "http://127.0.0.1:8501",
                   "http://localhost:5173", "http://127.0.0.1:5173"}


def _cross_origin(request: Request) -> bool:
    # Absent headers (curl/scripts) pass; a browser page on another site cannot.
    origin = request.headers.get("origin")
    site = request.headers.get("sec-fetch-site")
    same = f"{request.url.scheme}://{request.headers.get('host')}"  # covers web_main.py --port
    return (origin is not None and origin not in ALLOWED_ORIGINS and origin != same) or (
        site is not None and site not in {"same-origin", "none"})


@router.post("/refresh")
async def refresh(request: Request):
    if _cross_origin(request):
        return JSONResponse({"error": "Cross-origin refresh rejected"}, status_code=403)
    status = scheduler.do_refresh()
    return {"status": status, "triggered_at": datetime.now().isoformat()}


@router.post("/live/watch")
async def live_watch(request: Request):
    if _cross_origin(request):
        return JSONResponse({"error": "Cross-origin watch rejected"}, status_code=403)
    try:
        body = await request.json()
    except ValueError:
        body = None
    symbols = body.get("symbols") if isinstance(body, dict) else None
    if not isinstance(symbols, list):
        return JSONResponse({"error": "Body must be {\"symbols\": [...]}"}, status_code=422)
    return live_feed.watch(symbols)


@router.get("/live/snapshot")
def live_snapshot():
    return live_feed.snapshot()


@router.get("/events")
async def events():
    async def gen():
        q = scheduler.subscribe()
        try:
            while True:
                yield {"data": await q.get()}
        finally:
            scheduler.unsubscribe(q)

    return EventSourceResponse(gen())
