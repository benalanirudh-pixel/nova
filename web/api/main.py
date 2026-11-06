from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.api.routes.analysis import router as analysis_router
from web.api.routes.desk import router as desk_router
from web.api import live_feed, scheduler
from web.api.routes.events import router as events_router
from web.api.routes.market import router as market_router
from web.api.routes.stock import router as stock_router
from styles.design_tokens import BUY_SELL_AUTHORIZED, GUARDRAIL_TEXT


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start_scheduler(app)
    live_feed.start(app)
    yield
    live_feed.stop(app)
    scheduler.stop_scheduler(app)


DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app(dist: Path | None = None) -> FastAPI:
    dist = (DIST_DIR if dist is None else Path(dist)).resolve()
    app = FastAPI(title="Nova Web API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8501"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "buy_sell_authorized": BUY_SELL_AUTHORIZED,
            "guardrail": GUARDRAIL_TEXT,
        }

    app.include_router(market_router, prefix="/api")
    app.include_router(analysis_router, prefix="/api")
    app.include_router(desk_router, prefix="/api")
    app.include_router(stock_router, prefix="/api")
    app.include_router(events_router, prefix="/api")

    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            f = (dist / path).resolve()
            if f.is_file() and f.is_relative_to(dist):
                return FileResponse(f)
            # no-cache: a browser must never keep showing a previous build's page
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})  # SPA deep-link fallback

    return app
