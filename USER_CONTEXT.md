# User Context

This file records user preferences that matter for coding-agent handoff.

## User

- Name in code context: Anirudh / Ani.
- Project: Nova.
- Environment: Windows, PowerShell, local Python virtual environment.
- Timezone for user-facing notes: Asia/Calcutta.

## What The User Wants

The user has been building Nova with generated code and copy-paste edits. They
want to move to a coding-agent workflow where different models can open the
folder, read context, and resume work safely.

The requested outcome is not a rewrite. The requested outcome is a reliable
project context layer plus cautious edits that preserve working behavior.

## Working Preferences

- Inspect the actual project before editing.
- Prefer practical CLI-based work.
- Provide complete code when code is requested.
- Do not make broad speculative rewrites.
- Do not silently clean up or delete generated files.
- Keep final summaries exact: changed files, checks run, and next steps.
- Make the project model-agnostic so Codex, Claude, Gemini, Cursor, or another
  coding agent can continue from the same files.

## Domain Preferences

- Market analysis must be evidence-grounded.
- Current market values must come from tools/data sources, not memory.
- Missing or stale data should be called out plainly.
- Technical scores, derivatives context, and institutional-flow readings are
  analysis inputs, not trade execution signals.

## Agent Interaction Pattern

When another model resumes:

1. Read `AGENTS.md`.
2. Read the context files listed there.
3. Inspect relevant source files directly.
4. State what will be changed before editing if the task is broad.
5. Keep changes narrow.
6. Verify with non-destructive checks.
7. Update `CHANGES.md` and `docs/VALIDATION.md` when project context changes.
