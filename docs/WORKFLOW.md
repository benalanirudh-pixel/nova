# Safe Change Workflow

Use this workflow for Codex or any other coding model.

## 1. Start With Context

Read:

```text
AGENTS.md
README.md
PROJECT_CONTEXT.md
USER_CONTEXT.md
docs/ARCHITECTURE.md
docs/VALIDATION.md
docs/DEPENDENCIES.md
CHANGES.md
```

Then inspect the specific files related to the requested change.

## 2. Classify The Change

Use the smallest safe category:

- Documentation/context only.
- UI-only.
- LLM prompt/tool behavior.
- Voice/TTS/audio.
- Market-data adapter.
- Market analysis engine.
- Cache/data migration.
- Dependency/environment change.

The higher the category risk, the more targeted validation is needed.

## 3. Protect Generated State

Do not edit or delete these during normal coding work:

```text
venv/
.venv/
__pycache__/
stt_models/
voices/
analysis/data/cache/
*.wav
*.zip
market_lab_debug.log
```

If cleanup is requested, list exactly what will be removed before doing it.

## 4. Make Narrow Edits

- Prefer small patches over broad rewrites.
- Keep behavior-compatible names and interfaces unless the user asks for a
  redesign.
- Preserve analysis-only market safety.
- Preserve cache-first behavior in Market Lab unless the task is specifically
  about refresh behavior.
- Do not silently introduce a new model, API provider, trading connector, or
  network dependency.

## 5. Verify

For docs-only changes:

- Confirm files exist and are readable.

For Python edits:

- Run a syntax check that excludes virtual environments.
- Run import smoke checks for touched surfaces.
- Run targeted scripts only when they match the change.

For market-data changes:

- Prefer cached/local checks first.
- Run live endpoint checks only when the change needs them.
- Clearly report whether data was cached, live, stale, or unavailable.

## 6. Update Handoff Files

Update these when relevant:

- `CHANGES.md` for human-readable change history.
- `docs/VALIDATION.md` for checks actually run.
- `docs/ARCHITECTURE.md` if module boundaries or data flow changed.
- `docs/DEPENDENCIES.md` if imports, services, or environment expectations
  changed.

## 7. Final Response Template

Give the user:

- Changed files.
- What was verified.
- What was not run and why.
- Next safest step.

Keep it practical and specific.
