# CHANGES.md

This file tracks context, workflow, and behavior changes important for future
coding agents.

## 2026-10-09 - Agent Context Bootstrap

Added a model-agnostic context layer so Nova can be opened by another coding
agent and resumed safely.

Files added:

- `AGENTS.md`
- `README.md`
- `PROJECT_CONTEXT.md`
- `USER_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEPENDENCIES.md`
- `docs/VALIDATION.md`
- `docs/WORKFLOW.md`
- `docs/MODEL_HANDOFF.md`

Repository facts recorded:

- Actual project folder is `C:\Users\Anirudh\nova`.
- The folder is not currently a Git repository.
- No dependency manifest was found before this pass.
- Existing runtime dependencies were inspected from `venv/`.
- Main assistant entry point is `main.py`.
- Market Lab entry point is `market_lab_ui.py`.
- Market behavior is analysis-only and must remain non-executing.

Code changes:

- Added a small entry-point docstring to `main.py`.

Validation:

- Initial read-only inventory and dependency inspection completed.
- Python syntax check passed across 39 source files using BOM-aware decoding.
- Main assistant import smoke check passed.
- Market Lab import smoke check passed.

## 2026-10-09 - Git And GitHub Initialization

- Initialized a local Git repository on branch `main`.
- Confirmed the existing `.gitignore` excludes all generated state
  (`venv/`, `.venv/`, `stt_models/`, `voices/`, `analysis/data/cache/`,
  `analysis/data/data/cache/`, `*.wav`, `*.zip`, `*.log`).
- Root commit `e6ff588` contains 55 source, doc, and context files (~1.1 MB).
- Created the private GitHub repository `benalanirudh-pixel/nova` and pushed
  `main`; first push authenticated through Git Credential Manager.
- Set repo-local git identity: Anirudh <benalanirudh@gmail.com>.
- Updated stale "not a Git repository" statements in `AGENTS.md`, `README.md`,
  `PROJECT_CONTEXT.md`, and `docs/MODEL_HANDOFF.md`.


## 2026-10-09 - Market Lab UI Report Persistence

- Fixed: `market_lab_ui.py` never saved successful reports to JSON, so
  `load_latest_saved_report()` had nothing to show on the next launch and
  `analysis/data/cache/market_lab/` did not exist at all.
- `Worker.run()` now calls `save_json_report()` in the background thread for
  every successful `"report"` result; save failures print a warning but never
  fail the task.
- Verified with a cache-first engine run: 18 s end-to-end using the cached
  1,999-stock scan; first saved report written (62 KB) and loaded back
  through the UI loader with safety guardrails intact.

