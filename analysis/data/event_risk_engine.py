"""

Nova Event Risk Engine

Version: 1.0.0



Purpose:

- Assess upcoming, verified market events.

- Calculate time until each event.

- Identify relevant instruments.

- Flag stale or incomplete calendar data.



This module does not fetch events from the internet, predict market

moves, authorize buy/sell signals, or execute trades.



Timestamps must include a timezone, for example:

2026-10-12T10:00:00+05:30

"""



from __future__ import annotations



from datetime import datetime, timezone

from typing import Any





ENGINE_NAME = "Nova Event Risk Engine"

ENGINE_VERSION = "1.0.0"



DEFAULT_LOOKAHEAD_DAYS = 7

MAX_SOURCE_AGE_HOURS = 24



EXECUTION_ENABLED = False

BUY_SELL_AUTHORIZATION = False



SEVERITY_SCORES = {

    "LOW": 1,

    "MODERATE": 2,

    "HIGH": 3,

    "CRITICAL": 4,

}



SUPPORTED_INSTRUMENTS = {

    "NIFTY",

    "BANK_NIFTY",

    "INDIAN_MARKET",

    "GLOBAL_MARKET",

}





def _parse_timestamp(value: Any) -> datetime | None:

    """Parse a timezone-aware datetime or ISO-8601 timestamp."""

    if isinstance(value, datetime):

        parsed = value

    elif isinstance(value, str) and value.strip():

        try:

            parsed = datetime.fromisoformat(

                value.strip().replace("Z", "+00:00")

            )

        except ValueError:

            return None

    else:

        return None



    # Naive timestamps are rejected to prevent timezone assumptions.

    if parsed.tzinfo is None or parsed.utcoffset() is None:

        return None



    return parsed.astimezone(timezone.utc)





def _normalise_severity(value: Any) -> str | None:

    if not isinstance(value, str):

        return None



    severity = value.strip().upper()

    return severity if severity in SEVERITY_SCORES else None





def _normalise_instruments(value: Any) -> list[str]:

    if isinstance(value, str):

        value = [value]



    if not isinstance(value, (list, tuple, set)):

        return []



    instruments = []

    for item in value:

        if isinstance(item, str):

            instrument = item.strip().upper()

            if instrument in SUPPORTED_INSTRUMENTS:

                instruments.append(instrument)



    return sorted(set(instruments))





def _event_risk_score(

    severity: str,

    hours_until_event: float,

) -> int:

    """

    Apply a transparent rule-based score.

    This is a risk-priority score, not a probability of a market move.

    """

    score = SEVERITY_SCORES[severity]



    if hours_until_event <= 6:

        score += 2

    elif hours_until_event <= 24:

        score += 1



    return min(score, 6)





def _risk_label(score: int) -> str:

    if score >= 5:

        return "CRITICAL"

    if score >= 4:

        return "HIGH"

    if score >= 3:

        return "MODERATE"

    return "LOW"





def build_event_risk_context(

    events: list[dict[str, Any]] | None = None,

    source_checked_at: str | datetime | None = None,

    calendar_complete: bool = False,

    now: str | datetime | None = None,

    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,

) -> dict[str, Any]:

    """

    Build a JSON-serializable event-risk report.



    Each event should contain:

        name: str

        datetime: timezone-aware ISO-8601 string

        category: str

        severity: LOW | MODERATE | HIGH | CRITICAL

        instruments: list[str]

        source: str

        verified: bool

        impact_note: optional str



    source_checked_at must identify when the calendar source was

    last checked. Set calendar_complete=True only when the source

    has been checked and its coverage is considered complete.

    """

    current_time = _parse_timestamp(now) if now is not None else (

        datetime.now(timezone.utc)

    )

    source_time = _parse_timestamp(source_checked_at)



    warnings: list[str] = []

    valid_events: list[dict[str, Any]] = []

    rejected_events = 0



    if not isinstance(lookahead_days, int) or not 1 <= lookahead_days <= 90:

        lookahead_days = DEFAULT_LOOKAHEAD_DAYS

        warnings.append(

            "Invalid lookahead_days; default lookahead of 7 days used."

        )



    if not isinstance(events, list):

        events = []

        warnings.append("Events input was invalid; treated as empty.")



    if source_time is None:

        warnings.append(

            "Calendar source check time is missing or timezone-invalid."

        )

        source_fresh = False

    else:

        source_age_hours = (

            current_time - source_time

        ).total_seconds() / 3600



        source_fresh = (

            0 <= source_age_hours <= MAX_SOURCE_AGE_HOURS

        )



        if source_age_hours < 0:

            warnings.append(

                "Calendar source check time is in the future."

            )

        elif not source_fresh:

            warnings.append(

                "Calendar source is stale or older than 24 hours."

            )



    horizon_end = current_time.timestamp() + lookahead_days * 86400



    for raw_event in events:

        if not isinstance(raw_event, dict):

            rejected_events += 1

            continue



        name = raw_event.get("name")

        event_time = _parse_timestamp(raw_event.get("datetime"))

        severity = _normalise_severity(raw_event.get("severity"))

        instruments = _normalise_instruments(

            raw_event.get("instruments", [])

        )

        source = raw_event.get("source")

        verified = raw_event.get("verified") is True



        if not (

            isinstance(name, str)

            and name.strip()

            and event_time is not None

            and severity is not None

            and isinstance(source, str)

            and source.strip()

            and verified

            and instruments

        ):

            rejected_events += 1

            continue



        if event_time <= current_time:

            continue



        if event_time.timestamp() > horizon_end:

            continue



        hours_until = (

            event_time - current_time

        ).total_seconds() / 3600



        score = _event_risk_score(severity, hours_until)



        valid_events.append({

            "name": name.strip(),

            "datetime_utc": event_time.isoformat(),

            "category": str(

                raw_event.get("category", "UNSPECIFIED")

            ).strip().upper(),

            "severity": severity,

            "instruments": instruments,

            "source": source.strip(),

            "verified": True,

            "impact_note": str(

                raw_event.get("impact_note", "")

            ).strip(),

            "hours_until": round(hours_until, 2),

            "risk_score": score,

            "risk_level": _risk_label(score),

        })



    valid_events.sort(key=lambda event: event["datetime_utc"])



    if rejected_events:

        warnings.append(

            f"{rejected_events} event record(s) were rejected "

            "because required fields were invalid or unverified."

        )



    if source_fresh and calendar_complete:

        status = "AVAILABLE"

    else:

        status = "NOT_AVAILABLE"



    if status != "AVAILABLE":

        overall_risk = "UNKNOWN"

        overall_score = None

        warnings.append(

            "No reliable all-clear is possible until a fresh, "

            "complete calendar check is confirmed."

        )

    elif valid_events:

        overall_score = max(

            event["risk_score"] for event in valid_events

        )

        overall_risk = _risk_label(overall_score)

    else:

        # Only a fresh and explicitly complete calendar can establish

        # that no qualifying events were found in the requested window.

        overall_score = 0

        overall_risk = "LOW"



    by_instrument = {}

    for instrument in sorted(SUPPORTED_INSTRUMENTS):

        matching = [

            event for event in valid_events

            if instrument in event["instruments"]

            or (

                instrument in {"NIFTY", "BANK_NIFTY"}

                and "INDIAN_MARKET" in event["instruments"]

            )

            or "GLOBAL_MARKET" in event["instruments"]

        ]



        by_instrument[instrument] = {

            "event_count": len(matching),

            "highest_risk": (

                _risk_label(

                    max(event["risk_score"] for event in matching)

                )

                if matching and status == "AVAILABLE"

                else (

                    "LOW"

                    if status == "AVAILABLE"

                    else "UNKNOWN"

                )

            ),

            "events": matching,

        }



    return {

        "engine": ENGINE_NAME,

        "version": ENGINE_VERSION,

        "status": status,

        "generated_at_utc": current_time.isoformat(),

        "source_checked_at_utc": (

            source_time.isoformat() if source_time else None

        ),

        "source_fresh": source_fresh,

        "calendar_complete": bool(calendar_complete),

        "lookahead_days": lookahead_days,

        "overall_risk": overall_risk,

        "overall_risk_score": overall_score,

        "upcoming_event_count": len(valid_events),

        "upcoming_events": valid_events,

        "instrument_context": by_instrument,

        "warnings": warnings,

        "decision_policy": {

            "event_risk_is_a_buy_sell_signal": False,

            "buy_sell_authorization": BUY_SELL_AUTHORIZATION,

            "trading_execution": EXECUTION_ENABLED,

        },

    }





if __name__ == "__main__":

    # Demonstration only. This is fictional test data, not a real

    # market announcement. It is never used by the engine by default.

    from datetime import timedelta



    test_now = datetime.now(timezone.utc)

    test_events = [{

        "name": "Example policy announcement (TEST ONLY)",

        "datetime": (test_now + timedelta(hours=12)).isoformat(),

        "category": "CENTRAL_BANK",

        "severity": "HIGH",

        "instruments": ["NIFTY", "BANK_NIFTY"],

        "source": "SELF_TEST_FIXTURE",

        "verified": True,

        "impact_note": "Fictional event used only to test the engine.",

    }]



    result = build_event_risk_context(

        events=test_events,

        source_checked_at=test_now.isoformat(),

        calendar_complete=True,

        now=test_now.isoformat(),

    )



    assert result["status"] == "AVAILABLE"

    assert result["upcoming_event_count"] == 1

    assert result["decision_policy"]["trading_execution"] is False



    print("NOVA EVENT RISK ENGINE SELF-TEST")

    print("Status:", result["status"])

    print("Overall risk:", result["overall_risk"])

    print("Upcoming test events:", result["upcoming_event_count"])

    print("Execution enabled:", result["decision_policy"]["trading_execution"])

    print("Self-test passed.")
