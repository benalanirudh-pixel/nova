# CLAUDE.md — Nova

Nova is a local Windows Python assistant and Indian-market analysis workbench.
Analysis only — no broker, no orders, no BUY/SELL. Read `AGENTS.md` first for
full agent rules; this file is the quick-start.

## Entry Points

| Command | Surface |
|---------|---------|
| `.\venv\Scripts\python.exe web_main.py` | **Nova Desk, the main terminal** (web, live data) |
| `.\venv\Scripts\python.exe main.py` | Nova Assistant (personal AI desktop) |
| `.\venv\Scripts\python.exe market_lab_ui.py` | Market Lab (standalone) |
| `.\venv\Scripts\python.exe terminal_main.py` | Nova Terminal (unified) |
| `.\venv\Scripts\python.exe start_nova.py [desk\|main\|market\|--check]` | Launcher with preflight; opens Nova Desk by default |

## Architecture (summary)

See `docs/ARCHITECTURE.md` for full map.

- **Nova Desk path:** `web_main.py` → `web/api/main.py` (routes in `web/api/routes/`) → React app in `web/frontend/src/desk/`
- **Assistant path:** `main.py` → `ui.py` → `brain.py` (Ollama `qwen3.5:4b`) → `tools.py` → `analysis/data/*`
- **Market Lab path:** `market_lab_ui.py` → `market_lab/market_lab_data.py` (cache-first report) → `analysis/data/*`; `market_lab/market_lab_brain.py` (AI interpretation)
- **Terminal path:** `terminal_main.py` → `terminal/main_window.py` → pages in `terminal/pages/` (wires both paths above)
- **Design system:** `styles/design_tokens.py` (tokens), `styles/nova_theme.qss` (QSS), loaders in `market_lab/theme.py` and `ui/theme.py`
- **Analysis engines:** all under `analysis/data/` — technical, volatility, derivatives, institutional flow, sector, risk, event risk, research factors, scanner
- **Optional Dhan adapter:** `analysis/data/dhan_feed.py` — read-only market data, off by default, git-ignored config

## Key Commands

```powershell
# Run tests (394+ offline, stdlib unittest)
.\venv\Scripts\python.exe -m unittest discover -s tests -v

# Cache-first Market Lab report (terminal)
.\venv\Scripts\python.exe market_lab\market_lab_data.py

# JSON report
.\venv\Scripts\python.exe market_lab\market_lab_data.py --json

# Full NSE scan (expensive, ~2-3 min, 2333 stocks)
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh

# Service health check
.\venv\Scripts\python.exe start_nova.py --check

# Event calendar check
.\venv\Scripts\python.exe check_event_calendar.py
```

## Safety Rules (non-negotiable)

1. **Analysis only.** Never add trading execution, broker integration, order
   placement, or automatic BUY/SELL.
2. **No invented data.** Missing, stale, or conflicting data must be flagged,
   never fabricated.
3. **Cache-first.** Do not run the full NSE equity scan unless `--refresh` is
   used or no cache exists.
4. **Preserve guardrails.** The `GuardrailsBar` and `buy_sell_authorized: False`
   must survive every change.

## Do Not Touch (unless explicitly asked)

- `venv/`, `.venv/`, `__pycache__/`, `stt_models/`, `voices/`
- `analysis/data/cache/` — working market data caches
- `*.wav`, `*.zip`, `market_lab_debug.log`
- Backup files (`*.before_*.py`)

## External Services

| Service | URL | Used by |
|---------|-----|---------|
| Ollama | `http://localhost:11434` | `brain.py`, `market_lab_brain.py` |
| SearXNG | `http://localhost:8080` | `tools.py` web research |
| Indian Market MCP | `indian-market-mcp.exe` (stdio) | `nse_feed.py` |

Current LLM model: `qwen3.5:4b` (both brains).

## Agent Workflow

1. Read `AGENTS.md` → context files listed there → inspect relevant sources.
2. Keep edits small, reversible, tied to the task.
3. Verify with tests matching the risk: syntax check, import smoke, targeted
   unit tests.
4. Update `CHANGES.md` and `docs/VALIDATION.md` when behavior changes.

## Manifests

- `requirements.txt` — locked runtime (Python 3.14 venv, 109 packages)
- `pyproject.toml` — mirrors it as metadata; `tests/test_packaging.py` keeps sync
- `.github/workflows/ci.yml` — dependency-free gate (ast parse + stdlib tests)
- Full test suite runs locally only (heavy Windows stack)
