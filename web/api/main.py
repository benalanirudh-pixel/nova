from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.routes.market import router as market_router
from styles.design_tokens import BUY_SELL_AUTHORIZED, GUARDRAIL_TEXT


def create_app() -> FastAPI:
    app = FastAPI(title="Nova Web API")
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
    return app
