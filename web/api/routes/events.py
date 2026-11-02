from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from web.api import scheduler

router = APIRouter()


ALLOWED_ORIGINS = {"http://localhost:8501", "http://127.0.0.1:8501",
                   "http://localhost:5173", "http://127.0.0.1:5173"}


@router.post("/refresh")
async def refresh(request: Request):
    # Absent headers (curl/scripts) pass; a browser page on another site cannot.
    origin = request.headers.get("origin")
    site = request.headers.get("sec-fetch-site")
    if (origin is not None and origin not in ALLOWED_ORIGINS) or (
            site is not None and site not in {"same-origin", "none"}):
        return JSONResponse({"error": "Cross-origin refresh rejected"}, status_code=403)
    status = scheduler.do_refresh()
    return {"status": status, "triggered_at": datetime.now().isoformat()}


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
