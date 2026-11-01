"""Nova web dashboard launcher (localhost only)."""
import argparse

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dev", action="store_true", help="API only; run Vite separately")
    p.add_argument("--port", type=int, default=8501)
    a = p.parse_args()
    if a.dev:
        print("Dev mode: in another shell run `cd web/frontend && npm run dev` (http://localhost:5173)")
    uvicorn.run("web.api.main:create_app", factory=True, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
