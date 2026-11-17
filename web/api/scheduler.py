import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from analysis.data import nse_live, price_store
from web.api import universe
from market_lab.market_lab_data import get_market_lab_data, save_json_report

IST = "Asia/Kolkata"
SLOTS = ((9, 15), (13, 30), (15, 15), (18, 0))
REFRESH_TIMEOUT_S = 900
_running = False  # set synchronously so two quick calls can't both start
_subscribers: list[asyncio.Queue] = []
_tasks: set[asyncio.Task] = set()


MAX_QUEUE = 200  # a stalled SSE client must not grow memory; it drops ticks and catches up on reconnect


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


def _broadcast(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(json.dumps(event))
        except asyncio.QueueFull:
            pass


KEEP_REPORTS = 40  # ~2 weeks at 4 scans a day; older saved reports are deleted after each new save


def prune_reports(report_dir: Path, keep: int = KEEP_REPORTS) -> int:
    files = sorted(report_dir.glob("market_lab_*.json"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep] if keep else files:
        p.unlink(missing_ok=True)
    return max(0, len(files) - keep)


def _refresh_and_save() -> None:
    # the dashboard reads only saved reports, so a refresh that is not saved changes nothing
    path = save_json_report(get_market_lab_data(force_refresh=True))
    prune_reports(Path(path).parent)


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
    try:
        if datetime.now(ZoneInfo(IST)).date().isoformat() in await asyncio.to_thread(nse_live.trading_holidays):
            return  # NSE is shut: a scan would only re-save the last session
    except Exception:
        pass  # holiday list unavailable: refresh as scheduled
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


PRICE_SLOT = (19, 30)  # NSE publishes the day's bhavcopy in the evening
_prices_running = False


async def update_prices() -> None:
    """Fetch the sessions the price store is missing. Cheap: one small file per missing day."""
    global _prices_running
    if _prices_running:
        return
    _prices_running = True
    try:
        await asyncio.to_thread(price_store.update)
        try:
            await asyncio.to_thread(universe.refresh_master)
        except Exception as exc:  # the cached master still works; new listings just wait for the next try
            print(f"[MASTER] refresh failed: {exc}")
        # rebuild the whole-market cross-section for the store as it now stands (a no-op when nothing changed)
        if await asyncio.to_thread(universe.build):
            _broadcast({"type": "universe_ready", "timestamp": datetime.now().isoformat()})
    except Exception as exc:  # the desk works without the store; say so and carry on
        print(f"[PRICE STORE] update failed: {exc}")
    finally:
        _prices_running = False


def catch_up_prices() -> None:
    """At startup: pick up any sessions published while the server was off. Needs a running loop."""
    task = asyncio.get_running_loop().create_task(update_prices())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def start_scheduler(app) -> None:
    sched = AsyncIOScheduler(timezone=IST)
    sched.add_job(update_prices, CronTrigger(day_of_week="mon-fri", hour=PRICE_SLOT[0], minute=PRICE_SLOT[1], timezone=IST),
                  misfire_grace_time=None, coalesce=True)
    for hour, minute in SLOTS:
        # PC sleep makes the timer fire late; APScheduler's 1 s default grace would silently skip the slot
        sched.add_job(_scheduled_refresh, CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=IST),
                      misfire_grace_time=None, coalesce=True)
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
