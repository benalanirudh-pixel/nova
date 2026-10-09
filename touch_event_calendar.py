"""
Confirm a real event-calendar re-check for Nova Market Lab.

The event risk engine accepts `source_checked_at` as fresh only after a
real source check, so this script never touches the network and never
edits event entries. After you have actually re-checked the sources it
prints, answer yes and it stamps `source_checked_at` with the current
local time. Answer anything else and the file is left untouched.

Usage:
    .\\venv\\Scripts\\python.exe touch_event_calendar.py

Exit codes: 0 = stamped (or already fresh), 1 = declined, missing, or invalid.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CALENDAR_FILE = (
    Path(__file__).resolve().parent
    / "analysis"
    / "data"
    / "event_calendar.json"
)

SOURCES = [
    "NSE 2026 trading holidays (Zerodha/Livemint or nseindia.com)",
    "MoSPI + DPIIT advance release calendars (CPI/WPI dates)",
    "US BLS schedule (bls.gov/schedule) for CPI/PPI in window",
    "RBI MPC schedule (rbi.org.in) for policy decisions",
]


def parse_timestamp(value):
    """Return a timezone-aware datetime, or None (same rules as the engine)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def main() -> int:
    print("=" * 66)
    print("NOVA EVENT CALENDAR RE-CHECK CONFIRMATION")
    print("=" * 66)
    print(f"File: {CALENDAR_FILE}")

    if not CALENDAR_FILE.exists():
        print("\nMISSING: calendar file not found.")
        return 1

    try:
        with CALENDAR_FILE.open("r", encoding="utf-8") as handle:
            calendar = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"\nERROR: could not read calendar: {exc}")
        return 1

    if not isinstance(calendar, dict) or not isinstance(
        calendar.get("events"), list
    ):
        print("\nERROR: calendar is not a valid object with an events list.")
        print("Fix it before stamping a check time.")
        return 1

    checked_at = parse_timestamp(calendar.get("source_checked_at"))
    if checked_at is not None:
        age_hours = (
            datetime.now(timezone.utc) - checked_at
        ).total_seconds() / 3600
        print(
            f"\nLast checked: {checked_at.isoformat()} "
            f"({age_hours:.1f} h ago)"
        )

    print("\nConfirm you have JUST re-checked each source:")
    for number, source in enumerate(SOURCES, start=1):
        print(f"  {number}. {source}")
    print("  5. Event entries (names, datetimes, severities) still match.")

    answer = input(
        "\nHave you completed all 5 checks just now? (yes/no): "
    ).strip().lower()
    if answer not in {"yes", "y"}:
        print("Declined: calendar left untouched.")
        return 1

    calendar["source_checked_at"] = datetime.now().astimezone().isoformat()
    with CALENDAR_FILE.open("w", encoding="utf-8") as handle:
        json.dump(calendar, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(
        f"\nStamped source_checked_at = {calendar['source_checked_at']}"
    )
    print("Run check_event_calendar.py to confirm RESULT: OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
