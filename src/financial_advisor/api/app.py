"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import PROJECT_ROOT, Settings, load_settings
from ..portfolio.storage import PortfolioStorage
from .routes import analytics, market, portfolio


def create_app(
    settings: Optional[Settings] = None,
    db_path: Optional[Path] = None,
) -> FastAPI:
    """Create FastAPI app. If settings/db_path are None, load from config (production)."""
    if settings is None:
        settings = load_settings()
    if db_path is None:
        db_path = PROJECT_ROOT / "data" / "portfolio.db"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = PortfolioStorage(db_path)
        await storage.initialize()
        # Seed from user_profile if holdings table is empty
        profile_holdings = settings.user_profile.get("holdings", [])
        if profile_holdings:
            await storage.seed_from_profile(profile_holdings)
        app.state.storage = storage
        app.state.settings = settings
        yield
        await storage.close()

    app = FastAPI(
        title="Financial Advisor API",
        description="Portfolio analytics and market data backend",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
    app.include_router(market.router, prefix="/market", tags=["market"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
