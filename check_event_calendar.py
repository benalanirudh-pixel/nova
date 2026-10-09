"""
Offline checker for analysis/data/event_calendar.json.

Validates the calendar against the Event Risk Engine's rules and reports
freshness. Never modifies the file and never touches the network: the engine
accepts source_checked_at as fresh only after a real source check, so this
script tells you WHEN a re-check is due - it never fakes one.

Usage:
    .\\venv\\Scripts\\python.exe check_event_calendar.py

Exit codes: 0 = valid and fresh, 1 = stale, invalid, or missing.
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

SEVERITIES = {"LOW", "MODERATE", "HIGH", "CRITICAL"}
INSTRUMENTS = {"NIFTY", "BANK_NIFTY", "INDIAN_MARKET", "GLOBAL_MARKET"}
MAX_SOURCE_AGE_HOURS = 24
LOOKAHEAD_DAYS = 7


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


def check_event(index, event):
    """Return a list of problems for one event (empty list = valid)."""
    if not isinstance(event, dict):
        return ["not an object"]

    problems = []

    name = event.get("name")
    if not (isinstance(name, str) and name.strip()):
        problems.append("name missing")

    if parse_timestamp(event.get("datetime")) is None:
        problems.append("datetime missing or not ISO-8601 with timezone")

    severity = str(event.get("severity", "")).strip().upper()
    if severity not in SEVERITIES:
        problems.append(f"severity '{severity}' not in {sorted(SEVERITIES)}")

    source = event.get("source")
    if not (isinstance(source, str) and source.strip()):
        problems.append("source missing")

    if event.get("verified") is not True:
        problems.append("verified must be true")

    instruments = event.get("instruments", [])
    if isinstance(instruments, str):
        instruments = [instruments]
    if not instruments:
        problems.append("instruments empty")
    else:
        bad = [
            str(item)
            for item in instruments
            if str(item).strip().upper() not in INSTRUMENTS
        ]
        if bad:
            problems.append(f"instruments unsupported: {bad}")

    return problems


def main() -> int:
    print("=" * 66)
    print("NOVA EVENT CALENDAR CHECK")
    print("=" * 66)
    print(f"File: {CALENDAR_FILE}")

    if not CALENDAR_FILE.exists():
        print("\nMISSING: calendar file not found.")
        print(
            "The event risk engine will report NOT_AVAILABLE / UNKNOWN "
            "until it exists. Create it only after checking a reliable "
            "calendar source, then run this script again."
        )
        return 1

    try:
        with CALENDAR_FILE.open("r", encoding="utf-8") as handle:
            calendar = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"\nINVALID JSON: {type(exc).__name__}: {exc}")
        return 1

    if not isinstance(calendar, dict):
        print("\nINVALID: top level must be a JSON object.")
        return 1

    errors = []
    warnings = []

    # ------------------------------------------------------------------
    # FRESHNESS
    # ------------------------------------------------------------------

    now = datetime.now(timezone.utc)
    checked_at = parse_timestamp(calendar.get("source_checked_at"))
    age_hours = None

    if checked_at is None:
        errors.append(
            "source_checked_at missing or not timezone-aware "
            "(example: 2026-10-10T00:11:37+05:30)"
        )
    else:
        age_hours = (now - checked_at).total_seconds() / 3600
        if age_hours < 0:
            warnings.append("source_checked_at is in the future.")
        elif age_hours > MAX_SOURCE_AGE_HOURS:
            errors.append(
                f"source_checked_at is {age_hours:.1f} h old "
                f"(limit {MAX_SOURCE_AGE_HOURS} h): the engine will "
                "report NOT_AVAILABLE / UNKNOWN until a real re-check "
                "is recorded."
            )

    if calendar.get("calendar_complete") is not True:
        errors.append(
            "calendar_complete is not true: the engine refuses an "
            "all-clear without an explicitly complete calendar."
        )

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------

    events = calendar.get("events", [])
    if not isinstance(events, list):
        errors.append("events must be a list")
        events = []

    invalid = []
    valid = []

    for index, event in enumerate(events):
        problems = check_event(index, event)
        if problems:
            label = (
                event.get("name", "?")
                if isinstance(event, dict)
                else "?"
            )
            invalid.append(
                f"event #{index} '{label}': {'; '.join(problems)}"
            )
        else:
            valid.append((event, parse_timestamp(event.get("datetime"))))

    horizon = datetime.fromtimestamp(
        now.timestamp() + LOOKAHEAD_DAYS * 86400,
        timezone.utc,
    )
    upcoming = sorted(
        [
            (event, when)
            for event, when in valid
            if now < when <= horizon
        ],
        key=lambda pair: pair[1],
    )

    # ------------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------------

    print("\n--- SOURCE ---")
    print(f"Name: {calendar.get('source_name')}")
    print(f"URL : {calendar.get('source_url')}")
    if checked_at is not None and age_hours is not None:
        state = "FRESH" if age_hours <= MAX_SOURCE_AGE_HOURS else "STALE"
        print(
            f"Checked at: {checked_at.isoformat()} "
            f"({age_hours:.1f} h ago) -> {state}"
        )

    print("\n--- EVENTS ---")
    print(
        f"Total: {len(events)} | valid: {len(valid)} | "
        f"invalid: {len(invalid)} | next {LOOKAHEAD_DAYS} days: "
        f"{len(upcoming)}"
    )
    for event, when in upcoming:
        print(
            f"  - {when.astimezone().strftime('%Y-%m-%d %H:%M %Z')} | "
            f"{event['severity']} | {event['name']}"
        )

    if invalid:
        print("\nINVALID EVENTS (the engine will silently drop these):")
        for line in invalid:
            print(f"  - {line}")

    # ------------------------------------------------------------------
    # RE-CHECK CHECKLIST (only a real check may update source_checked_at)
    # ------------------------------------------------------------------

    print("\n--- RE-CHECK CHECKLIST (before updating source_checked_at) ---")
    print("1. NSE 2026 trading holidays (Zerodha/Livemint or nseindia.com)")
    print("2. MoSPI + DPIIT advance release calendars (CPI/WPI dates)")
    print("3. US BLS schedule (bls.gov/schedule) for CPI/PPI in window")
    print("4. RBI MPC schedule (rbi.org.in) for policy decisions")
    print("5. Adjust events with sources, then set source_checked_at")
    print("   to the actual time of this check.")

    # ------------------------------------------------------------------
    # RESULT
    # ------------------------------------------------------------------

    ok = not errors and not invalid

    if warnings:
        print("\nWarnings:")
        for line in warnings:
            print(f"  - {line}")

    if errors:
        print("\nErrors:")
        for line in errors:
            print(f"  - {line}")

    print()
    if ok and age_hours is not None and age_hours <= MAX_SOURCE_AGE_HOURS:
        print("RESULT: OK - calendar is valid and fresh.")
        return 0

    print("RESULT: NOT OK - fix the issues above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

