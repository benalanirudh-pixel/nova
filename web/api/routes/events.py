import hmac
import os
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
    # host only, not scheme: behind a TLS proxy the page is https but uvicorn sees http
    same_host = (origin or "").split("://", 1)[-1] == request.headers.get("host")
    return (origin is not None and origin not in ALLOWED_ORIGINS and not same_host) or (
        site is not None and site not in {"same-origin", "none"})


def forbidden(request: Request, action: str = "refresh") -> str | None:
    """Why a costly POST must be rejected, or None. Shared by /refresh and /interpret."""
    if _cross_origin(request):
        return f"Cross-origin {action} rejected"
    # a full NSE scan takes minutes and an AI call costs money; on a public host,
    # NOVA_REFRESH_TOKEN keeps strangers from triggering either
    token = os.getenv("NOVA_REFRESH_TOKEN")
    if token and not hmac.compare_digest(request.headers.get("x-nova-token", ""), token):
        return f"{action.capitalize()} token missing or wrong"
    return None


@router.post("/refresh")
async def refresh(request: Request):
    if reason := forbidden(request):
        return JSONResponse({"error": reason}, status_code=403)
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
