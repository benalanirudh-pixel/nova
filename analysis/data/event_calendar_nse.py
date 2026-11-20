"""
Machine-checked part of the event calendar: NSE trading holidays and NIFTY F&O
expiries, straight from NSE's own APIs. Refreshed daily by the Nova Desk
scheduler into a git-ignored cache; the event risk engine treats these as fresh
for 24 hours after `checked_at`.

Scheduled macro releases (RBI, Fed, CPI, GDP...) stay in the hand-verified
analysis/data/event_calendar.json. Nothing here is invented: an NSE failure
leaves the previous cache in place, and the engine then reports it as stale.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CACHE_FILE = Path(__file__).resolve().parent / "cache" / "event_calendar_nse.json"
HORIZON_DAYS = 60
NSE_CATEGORIES = {"MARKET_HOLIDAY", "DERIVATIVES_EXPIRY"}  # owned by this feed once its cache exists
IN3 = ["INDIAN_MARKET", "NIFTY", "BANK_NIFTY"]


def _day(text: str) -> Optional[date]:
    try:
        return datetime.strptime(str(text), "%d-%b-%Y").date()
    except ValueError:
        return None


def build_events(holidays: dict, nifty_expiries: list, banknifty_expiries: list, now: datetime,
                 horizon_days: int = HORIZON_DAYS) -> list[dict]:
    """Events for [today, today + horizon]. Weekend holidays are skipped: the market is shut anyway."""
    today = now.astimezone(IST).date()
    end = today + timedelta(days=horizon_days)
    stamp = f"checked {now.astimezone(IST):%Y-%m-%d %H:%M} IST"
    out = []
    for h in holidays.get("CM") or []:
        d = _day(h.get("tradingDate"))
        if d and today <= d <= end and d.weekday() < 5:
            out.append({"name": f"NSE/BSE trading holiday - {str(h.get('description') or '').strip(' *')}",
                        "datetime": f"{d.isoformat()}T09:15:00+05:30", "category": "MARKET_HOLIDAY",
                        "severity": "LOW", "instruments": IN3, "verified": True,
                        "source": f"NSE holiday-master API ({stamp})",
                        "impact_note": "Exchange closed; no cash or derivatives trading."})
    monthly = {d for d in map(_day, banknifty_expiries) if d}  # BANKNIFTY lists monthly contracts only
    for d in sorted({d for d in map(_day, nifty_expiries) if d}):
        if not today <= d <= end:
            continue
        is_monthly = d in monthly
        out.append({"name": f"NIFTY {'monthly' if is_monthly else 'weekly'} expiry"
                            + (" (also BANKNIFTY monthly)" if is_monthly else ""),
                    "datetime": f"{d.isoformat()}T15:30:00+05:30", "category": "DERIVATIVES_EXPIRY",
                    "severity": "MODERATE" if is_monthly else "LOW",
                    "instruments": IN3 if is_monthly else ["NIFTY", "INDIAN_MARKET"], "verified": True,
                    "source": f"NSE option-chain-contract-info ({stamp})",
                    "impact_note": "Monthly F&O expiry and rollover." if is_monthly else "Weekly options expiry."})
    return sorted(out, key=lambda e: e["datetime"])


def refresh(path: Path = CACHE_FILE, now: Optional[datetime] = None) -> int:
    """Fetch from NSE and rewrite the cache. Raises on failure so the old cache stays untouched."""
    from analysis.data import nse_live
    now = now or datetime.now(IST)
    holidays = nse_live.get("holiday-master", {"type": "trading"})
    nifty = nse_live.get("option-chain-contract-info", {"symbol": "NIFTY"}).get("expiryDates") or []
    bank = nse_live.get("option-chain-contract-info", {"symbol": "BANKNIFTY"}).get("expiryDates") or []
    if not holidays.get("CM") or not nifty:
        raise ValueError("NSE returned no holidays or no NIFTY expiries")
    events = build_events(holidays, nifty, bank, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"checked_at": now.isoformat(), "source": "NSE APIs", "events": events}, indent=2),
                   encoding="utf-8")
    tmp.replace(path)  # atomic: a reader never sees half a file
    return len(events)


def load(path: Path = CACHE_FILE) -> tuple[Optional[str], list[dict]]:
    """(checked_at, events), or (None, []) when the cache is missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("checked_at"), list(data.get("events") or [])
    except (OSError, ValueError):
        return None, []


if __name__ == "__main__":
    print(f"{refresh()} NSE events written to {CACHE_FILE}")
