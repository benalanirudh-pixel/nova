"""Nova Desk launcher (localhost only)."""
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
    frontend = Path(__file__).parent / "web" / "frontend"
    try:
        if not (frontend / "node_modules").is_dir():  # fresh clone
            subprocess.run([npm, "ci"], cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    except subprocess.CalledProcessError as e:
        print(f"error: frontend build failed (exit {e.returncode})", file=sys.stderr)
        return 1
    return 0


FRONTEND = Path(__file__).parent / "web" / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"


def needs_build() -> bool:
    """True when dist is missing or older than the frontend source, e.g. after a git pull."""
    if not DIST_INDEX.exists():
        return True
    sources = [*(FRONTEND / "src").rglob("*"), FRONTEND / "index.html", FRONTEND / "package.json"]
    built = DIST_INDEX.stat().st_mtime
    return any(f.is_file() and f.stat().st_mtime > built for f in sources)


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
    elif needs_build() and build_frontend() != 0 and not DIST_INDEX.exists():
        sys.exit(1)  # an older build still works; only stop when there is nothing to serve
    url = f"http://localhost:{5173 if a.dev else a.port}/"
    print(f"Nova Desk: {url}")
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("web.api.main:create_app", factory=True, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
