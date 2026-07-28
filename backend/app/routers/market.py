"""Market metric snapshot — powers Heatmap, ETF browser and Screener (Change 17).

One endpoint returns price-derived metrics for the curated + cached universe of a market;
the three pages present the same rows differently (heatmap tiles, ETF cards, screener table).
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas import (
    Market,
    MarketSnapshotResponse,
    QuotesRequest,
    QuotesResponse,
    SnapshotRow,
)
from ..services import market_snapshot

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/snapshot", response_model=MarketSnapshotResponse)
def snapshot(market: Market = Query("KR")) -> MarketSnapshotResponse:
    rows = market_snapshot.compute_snapshot(market)
    return MarketSnapshotResponse(market=market, rows=[SnapshotRow(**r) for r in rows])


@router.post("/quotes", response_model=QuotesResponse)
def quotes(body: QuotesRequest) -> QuotesResponse:
    """Metric rows for an explicit list of tickers (the watchlist). Mixed markets allowed."""
    pairs = [(item.ticker, item.market) for item in body.items]
    rows = market_snapshot.compute_quotes(pairs)
    return QuotesResponse(rows=[SnapshotRow(**r) for r in rows])
