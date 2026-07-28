"""FastAPI entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db
from .routers import (
    ai,
    allocation,
    backtest,
    correlation,
    market,
    ohlcv,
    report,
    retirement,
    seasonality,
    strategies,
    tickers,
)
from .services import data_service

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

scheduler: BackgroundScheduler | None = None


def _nightly_refresh() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.nightly_refresh import refresh  # noqa: PLC0415 - imported lazily

    try:
        refresh(lookback_days=5)
    except Exception:  # noqa: BLE001 - a failed refresh must not kill the scheduler
        logger.exception("nightly refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler

    init_db()
    settings.ohlcv_path.mkdir(parents=True, exist_ok=True)
    settings.tickers_path.mkdir(parents=True, exist_ok=True)
    for market in ("KR", "US"):
        logger.info("cached %s tickers: %d", market, len(data_service.list_cached(market)))

    if settings.enable_scheduler:
        scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        scheduler.add_job(
            _nightly_refresh,
            CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
            id="nightly_refresh",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        logger.info("scheduler started — nightly refresh at 07:00 KST")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="EasyBacktest API",
    version="0.1.0",
    description="AI-native stock backtesting for the KR and US markets.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort safety net: log the full trace, return a typed 500 with a detail.

    Deliberate HTTPExceptions raised by routers are handled by FastAPI's own handler and
    never reach here; this only catches genuinely unexpected errors so the frontend gets
    `{detail, type}` instead of an opaque crash.
    """
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or exc.__class__.__name__, "type": type(exc).__name__},
    )


app.include_router(tickers.router)
app.include_router(ohlcv.router)
app.include_router(ai.router)
app.include_router(backtest.router)
app.include_router(strategies.router)
app.include_router(correlation.router)
app.include_router(seasonality.router)
app.include_router(allocation.router)
app.include_router(report.router)
app.include_router(market.router)
app.include_router(retirement.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "ai_enabled": bool(settings.gemini_api_key),
        "model": settings.active_model,
        "cached_tickers": {
            market: len(data_service.list_cached(market)) for market in ("KR", "US")
        },
    }
