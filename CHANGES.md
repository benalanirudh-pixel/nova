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
