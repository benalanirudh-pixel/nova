"""Nova web dashboard launcher (localhost only)."""
import argparse
import shutil
import subprocess
import sys
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dev", action="store_true", help="API only; run Vite separately")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--build", action="store_true", help="build the frontend (npm run build) and exit")
    a = p.parse_args()
    if a.build:
        sys.exit(build_frontend())
    if a.dev:
        print("Dev mode: in another shell run `cd web/frontend && npm run dev` (http://localhost:5173)")
    uvicorn.run("web.api.main:create_app", factory=True, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
