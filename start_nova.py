"""
Nova launcher + preflight health check.

Usage:
    python start_nova.py               # launch Nova Desk, the main terminal (web_main.py)
    python start_nova.py main          # launch the voice assistant (main.py)
    python start_nova.py market        # launch Nova Market Lab (market_lab_ui.py)
    python start_nova.py --check       # check services only, launch nothing

Before launching, it verifies the two local services Nova depends on and
reports clearly what is or isn't running:

- Ollama   http://localhost:11434  (both brains / AI analysis)
- SearXNG  http://localhost:8080   (web_research tool)

The check is read-only and never blocks the UI launch; it only warns. Nova
itself is analysis-only: this launcher starts the same two existing entry
points and adds no broker, order, or trading behavior.

Run from the project root:
    .\\venv\\Scripts\\python.exe start_nova.py --check
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request

# Discovered once so a failed probe costs little; re-checked per call.
SERVICES = [
    {
        "name": "Ollama",
        "url": "http://localhost:11434/api/tags",
        "why": "Nova's brain + Market Lab analysis (model qwen3.5:4b)",
    },
    {
        "name": "SearXNG",
        "url": "http://localhost:8080",
        "why": "the web_research tool",
    },
]

APPS = {
    "desk": "web_main.py",
    "main": "main.py",
    "market": "market_lab_ui.py",
}

CHECK_TIMEOUT_S = 3


def check_service(url, timeout=CHECK_TIMEOUT_S):
    """Return (ok, detail) for one local service. Never raises."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
        return True, f"HTTP {status}"
    except Exception as exc:  # connection refused, timeout, 404, ...
        return False, f"{type(exc).__name__}: {exc}"


def check_all(services=None, timeout=CHECK_TIMEOUT_S):
    """Probe every service; returns a list of result dicts."""
    services = SERVICES if services is None else services
    results = []
    for service in services:
        ok, detail = check_service(service["url"], timeout=timeout)
        results.append(
            {
                "name": service["name"],
                "url": service["url"],
                "why": service["why"],
                "ok": ok,
                "detail": detail,
            }
        )
    return results


def print_report(results):
    print("=" * 60)
    print("NOVA PREFLIGHT CHECK")
    print("=" * 60)
    all_ok = True
    for r in results:
        mark = "UP  " if r["ok"] else "DOWN"
        print(f"[{mark}] {r['name']:9} {r['url']}  ({r['detail']})")
        print(f"         used by: {r['why']}")
        if not r["ok"]:
            all_ok = False
    print("-" * 60)
    if all_ok:
        print("All services are up.")
    else:
        print("Some services are DOWN. Nova will still launch, but the")
        print("features that need them will report errors when used.")
    print("=" * 60)
    return all_ok


def launch(app_key):
    """Start the requested entry point in a new process and return its pid."""
    target = APPS.get(app_key)
    if target is None:
        raise ValueError(
            f"Unknown app '{app_key}'. Choose: {', '.join(APPS)}"
        )
    proc = subprocess.Popen([sys.executable, target])
    return proc.pid


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Nova launcher and local-service health check."
    )
    parser.add_argument(
        "app",
        nargs="?",
        choices=list(APPS.keys()),
        help="which app to launch (default: desk)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only run the preflight check, do not launch anything",
    )
    args = parser.parse_args(argv)

    all_ok = print_report(check_all())

    if args.check:
        return 0 if all_ok else 1

    app_key = args.app or "desk"

    pid = launch(app_key)
    print(f"\nLaunched {APPS[app_key]} (pid {pid}).")
    if not all_ok:
        print("Note: some services were down, so parts of Nova may not work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
