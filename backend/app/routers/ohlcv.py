from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..schemas import Candle, Market, OHLCVResponse
from ..services import data_service

router = APIRouter(prefix="/api/ohlcv", tags=["ohlcv"])


@router.get("/{market}/{ticker}", response_model=OHLCVResponse)
def get_candles(
    market: Market,
    ticker: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> OHLCVResponse:
    """Daily bars in TradingView Lightweight Charts format.

    Unadjusted `close` is returned — that is what users expect to see on a chart. The
    backtest engine reads adjusted prices straight from the Parquet cache instead.
    """
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start must not be after end")

    try:
        # Lazy loading: download+cache on first request, widening the cached window if
        # the caller asks for history older than what we already hold.
        data_service.ensure_cached(ticker, market, start=start)
        data_service.record_query(ticker, market)
        df = data_service.get_ohlcv(ticker, market, start, end)
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except data_service.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        meta = data_service.get_ticker(ticker, market)
        name = meta.name_ko or meta.name_en
        kind, is_tradable = meta.kind, meta.is_tradable
    except data_service.TickerNotFound:
        # Bars exist but the ticker predates the metadata table — still serve them.
        name, kind, is_tradable = ticker, "stock", True

    candles = [
        Candle(
            time=row.date.date(),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in df.itertuples()
    ]
    return OHLCVResponse(
        ticker=ticker,
        market=market,
        name=name,
        kind=kind,
        is_tradable=is_tradable,
        candles=candles,
    )
