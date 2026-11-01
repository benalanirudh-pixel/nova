from datetime import datetime

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from web.api import scheduler

router = APIRouter()


@router.get("/refresh")
async def refresh():
    status = scheduler.do_refresh()
    return {"status": status, "triggered_at": datetime.now().isoformat()}


@router.get("/events")
async def events():
    q = scheduler.subscribe()

    async def gen():
        try:
            while True:
                yield {"data": await q.get()}
        finally:
            scheduler.unsubscribe(q)

    return EventSourceResponse(gen())
