# Model Handoff Guide

This guide is for moving Nova work between Codex, Claude, Gemini, Cursor, or
another coding assistant.

## First Prompt To A New Model

Use something like:

```text
You are working in C:\Users\Anirudh\nova. Read AGENTS.md first, then README.md,
PROJECT_CONTEXT.md, USER_CONTEXT.md, docs/ARCHITECTURE.md,
docs/VALIDATION.md, docs/WORKFLOW.md, docs/DEPENDENCIES.md, and CHANGES.md.
After that, inspect the files relevant to my request before editing. Preserve
the analysis-only market safety boundary and avoid broad rewrites.
```

Then give the specific task.

## What A New Model Should Know Immediately

- This is a Windows local Python app.
- Use `.\venv\Scripts\python.exe`.
- The app is in Git: branch `main`, private GitHub remote `origin`
  (`benalanirudh-pixel/nova`).
- There are large generated folders that should be ignored unless relevant.
- The main assistant starts with `main.py`.
- Market Lab starts with `market_lab_ui.py`.
- Ollama model config is in `brain.py` and `market_lab/market_lab_brain.py`.
- Market Lab is cache-first by default.
- Full market refresh can be expensive.
- No code path should place trades or connect to brokers.

## Switching Model Providers

If changing Nova's own runtime LLM provider or model, inspect first:

- `brain.py`
- `market_lab/market_lab_brain.py`
- `tools.py`

Current model string:

```text
qwen3.5:4b
```

Do not only change the string if the provider changes. The current code expects
Ollama's Python client response shape and tool-call format.

## Switching Coding Agents

No special migration is needed if the next agent follows this order:

1. Read the context files.
2. Inspect current source files.
3. Make narrow edits.
4. Run targeted checks.
5. Update `CHANGES.md` and validation notes.

## Minimum Handoff Summary After Each Work Session

Each agent should leave:

- Exact files changed.
- Commands/checks run.
- Any failed checks.
- Any unresolved risks.
- The next recommended task.
