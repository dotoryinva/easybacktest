from fastapi import APIRouter, HTTPException, Query

from ..schemas import Market, Ticker
from ..services import data_service

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("/search", response_model=list[Ticker])
def search(
    q: str = Query(min_length=1, max_length=64),
    market: Market | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cached_only: bool = Query(
        default=False,
        description="Only return tickers that already have local OHLCV data. Default "
        "false: the whole universe is searchable and OHLCV is fetched on first open.",
    ),
) -> list[Ticker]:
    return data_service.search_tickers(q, market, limit, cached_only=cached_only)


@router.get("/{market}/{ticker}", response_model=Ticker)
def get_one(market: Market, ticker: str) -> Ticker:
    try:
        return data_service.get_ticker(ticker, market)
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except data_service.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
