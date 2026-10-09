
from pathlib import Path
import py_compile
import shutil
import sys


# ============================================================
# NOVA INSTITUTIONAL FLOW SOURCE-QUALITY PATCH
# ============================================================

ROOT = Path(__file__).resolve().parent

ENGINE_PATH = (
    ROOT
    / "analysis"
    / "data"
    / "institutional_flow_engine.py"
)

MARKET_LAB_PATH = (
    ROOT
    / "market_lab"
    / "market_lab_data.py"
)

ENGINE_BACKUP = ENGINE_PATH.with_name(
    "institutional_flow_engine.before_source_quality.py"
)

MARKET_LAB_BACKUP = MARKET_LAB_PATH.with_name(
    "market_lab_data.before_source_quality.py"
)


def replace_once(
    source: str,
    old: str,
    new: str,
    label: str,
) -> str:
    """Replace one exact source block or stop without writing."""

    count = source.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected one matching block, "
            f"found {count}. No changes have been written."
        )

    return source.replace(old, new, 1)


def make_backup(
    original_path: Path,
    backup_path: Path,
) -> None:
    """Create a backup without overwriting an existing backup."""

    if backup_path.exists():
        print(f"Backup already exists: {backup_path.name}")
        return

    shutil.copy2(
        original_path,
        backup_path,
    )

    print(f"Backup created: {backup_path.name}")


def main() -> int:
    if not ENGINE_PATH.is_file():
        print(f"ERROR: Missing file: {ENGINE_PATH}")
        return 1

    if not MARKET_LAB_PATH.is_file():
        print(f"ERROR: Missing file: {MARKET_LAB_PATH}")
        return 1

    engine_original = ENGINE_PATH.read_text(
        encoding="utf-8"
    )

    market_lab_original = MARKET_LAB_PATH.read_text(
        encoding="utf-8"
    )

    engine_updated = engine_original
    market_lab_updated = market_lab_original

    # ========================================================
    # 1. INSTITUTIONAL FLOW ENGINE
    # ========================================================

    # Add explicit metadata to the empty-history result.
    engine_updated = replace_once(
        engine_updated,
        '''        "invalid_rows": 0,
        "data_ready_for_market_lab": False,
        "flow_regime": "INSUFFICIENT_HISTORY",
''',
        '''        "invalid_rows": 0,
        "data_ready_for_market_lab": False,
        "flow_unit": "INR crore",
        "source_quality": "NO_HISTORY",
        "primary_source_sessions_in_target_window": 0,
        "non_primary_sessions_in_target_window": 0,
        "primary_source_verified_for_target_window": False,
        "flow_regime": "INSUFFICIENT_HISTORY",
''',
        "Engine empty metrics",
    )

    # Calculate provenance for the exact target window.
    # This does not change the existing 5D/10D/20D totals.
    engine_updated = replace_once(
        engine_updated,
        '''    metrics["secondary_sessions"] = int(
        valid_df["source"]
        .astype(str)
        .str.startswith((
            "SECONDARY_DAILY_MIRROR:",
            "GROWW_HTML:",
        ))
        .sum()
    )

    metrics["history_complete_for_5d"] = (
''',
        '''    metrics["secondary_sessions"] = int(
        valid_df["source"]
        .astype(str)
        .str.startswith((
            "SECONDARY_DAILY_MIRROR:",
            "GROWW_HTML:",
        ))
        .sum()
    )

    # --------------------------------------------------------
    # SOURCE QUALITY FOR THE TARGET HISTORY WINDOW
    # --------------------------------------------------------

    target_window = valid_df.tail(
        target_sessions
    ).copy()

    target_sources = (
        target_window["source"]
        .fillna("")
        .astype(str)
    )

    primary_mask = target_sources.eq(
        "NSE_PRIMARY_COMBINED_VERIFIED"
    )

    primary_count = int(
        primary_mask.sum()
    )

    non_primary_count = int(
        (~primary_mask).sum()
    )

    primary_window_verified = bool(
        len(target_window) >= target_sessions
        and len(target_window) > 0
        and primary_mask.all()
    )

    if len(target_window) < target_sessions:
        source_quality = "INSUFFICIENT_TARGET_WINDOW"

    elif primary_window_verified:
        source_quality = "PRIMARY_ONLY_TARGET_WINDOW"

    elif primary_count > 0:
        source_quality = "MIXED_SOURCE_TARGET_WINDOW"

    else:
        source_quality = "SECONDARY_ONLY_TARGET_WINDOW"

    metrics["flow_unit"] = "INR crore"

    metrics["primary_source_sessions_in_target_window"] = (
        primary_count
    )

    metrics["non_primary_sessions_in_target_window"] = (
        non_primary_count
    )

    metrics["primary_source_verified_for_target_window"] = (
        primary_window_verified
    )

    metrics["source_quality"] = source_quality

    metrics["history_complete_for_5d"] = (
''',
        "Engine target-window provenance",
    )

    # ========================================================
    # 2. MARKET LAB INTEGRATION
    # ========================================================

    # Add default fields for unavailable institutional data.
    market_lab_updated = replace_once(
        market_lab_updated,
        '''        "source_policy": {},
        "signal_allowed": False,
    }
''',
        '''        "source_policy": {},
        "signal_allowed": False,
        "signal_reason": None,
        "source_quality": "UNKNOWN",
    }
''',
        "Market Lab unavailable defaults",
    )

    # Keep data availability separate from signal eligibility.
    market_lab_updated = replace_once(
        market_lab_updated,
        '''        elif not correct_scope:
            reason = f"Unexpected market scope: {scope!r}"

        return {
            "available": ready,
''',
        '''        elif not correct_scope:
            reason = f"Unexpected market scope: {scope!r}"

        # Data can remain available for analysis while signal eligibility
        # is blocked when the target history window is not primary-only.
        primary_history_verified = (
            metrics.get(
                "primary_source_verified_for_target_window"
            ) is True
        )

        signal_allowed = bool(
            ready
            and primary_history_verified
        )

        signal_reason = None

        if not ready:
            signal_reason = (
                reason
                or "Institutional-flow data is not ready for analysis."
            )
        elif not primary_history_verified:
            signal_reason = (
                "Signal eligibility blocked: the target history window "
                "is not entirely primary-source verified."
            )

        return {
            "available": ready,
''',
        "Market Lab signal eligibility",
    )

    # Update the returned result without changing the existing
    # readiness or market-scope checks.
    market_lab_updated = replace_once(
        market_lab_updated,
        '''            "source_policy": source_policy,
            "signal_allowed": ready,
        }
''',
        '''            "source_policy": source_policy,
            "signal_allowed": signal_allowed,
            "signal_reason": signal_reason,
            "source_quality": metrics.get(
                "source_quality",
                "UNKNOWN",
            ),
        }
''',
        "Market Lab returned signal fields",
    )

    # ========================================================
    # 3. TERMINAL REPORT
    # ========================================================

    market_lab_updated = replace_once(
        market_lab_updated,
        '''    print(f"Fresh: {flow.get('history_fresh', False)}")

    for window in (5, 10, 20):
''',
        '''    print(f"Fresh: {flow.get('history_fresh', False)}")

    print(
        "Source quality: "
        f"{flow.get('source_quality', 'UNKNOWN')}"
    )

    print(
        "Primary sessions in target window: "
        f"{flow_metrics.get('primary_source_sessions_in_target_window', 0)}"
        f"/{flow_metrics.get('target_sessions', 20)}"
    )

    print(
        "Primary-only history verified: "
        f"{flow_metrics.get('primary_source_verified_for_target_window', False)}"
    )

    print(
        "Flow unit: "
        f"{flow_metrics.get('flow_unit', 'INR crore')}"
    )

    for window in (5, 10, 20):
''',
        "Market Lab source-quality display",
    )

    market_lab_updated = replace_once(
        market_lab_updated,
        '''    if flow.get("reason"):
        print(f"Readiness note: {flow['reason']}")

    print(
        "Decision-support eligible: "
        f"{flow.get('signal_allowed', False)}"
    )
''',
        '''    if flow.get("reason"):
        print(f"Readiness note: {flow['reason']}")

    if flow.get("signal_reason"):
        print(f"Signal eligibility note: {flow['signal_reason']}")

    print(
        "Decision-support eligible: "
        f"{flow.get('signal_allowed', False)}"
    )
''',
        "Market Lab signal warning",
    )

    # ========================================================
    # 4. CREATE BACKUPS AND WRITE
    # ========================================================

    make_backup(
        ENGINE_PATH,
        ENGINE_BACKUP,
    )

    make_backup(
        MARKET_LAB_PATH,
        MARKET_LAB_BACKUP,
    )

    try:
        ENGINE_PATH.write_text(
            engine_updated,
            encoding="utf-8",
        )

        MARKET_LAB_PATH.write_text(
            market_lab_updated,
            encoding="utf-8",
        )

        py_compile.compile(
            str(ENGINE_PATH),
            doraise=True,
        )

        py_compile.compile(
            str(MARKET_LAB_PATH),
            doraise=True,
        )

    except Exception as exc:
        # Restore the exact pre-patch contents if anything fails.
        ENGINE_PATH.write_text(
            engine_original,
            encoding="utf-8",
        )

        MARKET_LAB_PATH.write_text(
            market_lab_original,
            encoding="utf-8",
        )

        print()
        print("PATCH FAILED. Original files restored.")
        print(f"Reason: {type(exc).__name__}: {exc}")
        return 1

    print()
    print("=" * 64)
    print("NOVA INSTITUTIONAL FLOW PATCH SUCCESSFUL")
    print("=" * 64)
    print(f"Updated: {ENGINE_PATH.relative_to(ROOT)}")
    print(f"Updated: {MARKET_LAB_PATH.relative_to(ROOT)}")
    print("Engine syntax check: PASSED")
    print("Market Lab syntax check: PASSED")
    print()
    print("Existing flow totals and regime calculations preserved.")
    print("Analysis availability remains separate from signal eligibility.")
    print("Signal eligibility requires a fully primary-source target window.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
