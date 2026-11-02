"""Nova web dashboard launcher (localhost only)."""
import argparse
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn


def build_frontend() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("error: npm not found on PATH; install Node.js first", file=sys.stderr)
        return 1
    try:
        subprocess.run([npm, "run", "build"], cwd=Path(__file__).parent / "web" / "frontend", check=True)
    except subprocess.CalledProcessError as e:
        print(f"error: frontend build failed (exit {e.returncode})", file=sys.stderr)
        return 1
    return 0


DIST_INDEX = Path(__file__).parent / "web" / "frontend" / "dist" / "index.html"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dev", action="store_true", help="API only; run Vite separately")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--build", action="store_true", help="build the frontend (npm run build) and exit")
    p.add_argument("--no-browser", action="store_true", help="don't open the dashboard in a browser")
    a = p.parse_args()
    if a.build:
        sys.exit(build_frontend())
    if a.dev:
        print("Dev mode: in another shell run `cd web/frontend && npm run dev` (http://localhost:5173)")
    elif not DIST_INDEX.exists() and build_frontend() != 0:
        sys.exit(1)
    url = f"http://localhost:{5173 if a.dev else a.port}/"
    print(f"Nova dashboard: {url}")
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("web.api.main:create_app", factory=True, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
