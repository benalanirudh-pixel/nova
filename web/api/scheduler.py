import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from market_lab.market_lab_data import get_market_lab_data, save_json_report

IST = "Asia/Kolkata"
SLOTS = ((9, 15), (13, 30), (15, 15), (18, 0))
REFRESH_TIMEOUT_S = 900
_running = False  # set synchronously so two quick calls can't both start
_subscribers: list[asyncio.Queue] = []
_tasks: set[asyncio.Task] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


def _broadcast(event: dict) -> None:
    for q in list(_subscribers):
        q.put_nowait(json.dumps(event))


def _refresh_and_save() -> None:
    # the dashboard reads only saved reports, so a refresh that is not saved changes nothing
    save_json_report(get_market_lab_data(force_refresh=True))


async def _run_refresh() -> None:
    global _running
    try:
        # The worker thread can't be killed, so a late-finishing scan may overlap the next one.
        await asyncio.wait_for(asyncio.to_thread(_refresh_and_save), timeout=REFRESH_TIMEOUT_S)
        _broadcast({"type": "refresh_complete", "timestamp": datetime.now().isoformat()})
    except asyncio.TimeoutError:
        _broadcast({"type": "refresh_failed", "timestamp": datetime.now().isoformat(),
                    "error": f"Refresh timed out after {REFRESH_TIMEOUT_S}s"})
    except Exception as exc:  # keep scheduler/app alive; surface via SSE
        _broadcast({"type": "refresh_failed", "timestamp": datetime.now().isoformat(), "error": str(exc)})
    finally:
        _running = False


def do_refresh() -> str:
    """Start a background refresh. Returns 'refreshing' or 'already_running'."""
    global _running
    if _running:
        return "already_running"
    _running = True
    task = asyncio.get_running_loop().create_task(_run_refresh())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return "refreshing"


async def _scheduled_refresh() -> None:
    do_refresh()


def last_slot(now: datetime) -> datetime:
    """Most recent scheduled refresh time at or before `now` (IST, Mon-Fri)."""
    now = now.astimezone(ZoneInfo(IST))
    day = now
    while True:
        if day.weekday() < 5:
            for h, m in reversed(SLOTS):
                slot = day.replace(hour=h, minute=m, second=0, microsecond=0)
                if slot <= now:
                    return slot
        day = (day - timedelta(days=1)).replace(hour=23, minute=59)


def missed_refresh(saved_at: str | None, now: datetime) -> bool:
    """True when the saved report predates the last scheduled slot (server was down or asleep then)."""
    if not saved_at:
        return True
    saved = datetime.fromisoformat(saved_at)
    saved = saved if saved.tzinfo else saved.replace(tzinfo=ZoneInfo(IST))
    return saved < last_slot(now)


def start_scheduler(app) -> None:
    sched = AsyncIOScheduler(timezone=IST)
    for hour, minute in SLOTS:
        sched.add_job(_scheduled_refresh, CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=IST))
    sched.start()
    app.state.scheduler = sched
    # cron never re-runs a slot missed while the server was off; catch up once at startup
    from web.api.report_loader import load_cached_report
    saved = load_cached_report()
    if missed_refresh(saved and saved["saved_at"], datetime.now(ZoneInfo(IST))):
        do_refresh()


def stop_scheduler(app) -> None:
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown(wait=False)
