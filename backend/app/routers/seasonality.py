"""Seasonality statistics for one ticker (Change 14, Tier 2 계절성).

All figures are derived from the cached adjusted closes (lazy-loaded, and widened when
`since` reaches further back than the cache holds). Monthly returns come from month-end
closes; weekday and turn-of-month figures come from daily returns.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    Market,
    MonthlyCell,
    MonthStat,
    SeasonalityResponse,
    TurnOfMonthStat,
    WeekdayStat,
)
from ..services import data_service

router = APIRouter(prefix="/api/seasonality", tags=["seasonality"])

# Trading days at the end of a month that make up the "turn of month" window.
TURN_WINDOW = 3


@router.get("/{market}/{ticker}", response_model=SeasonalityResponse)
def seasonality(
    market: Market,
    ticker: str,
    since: int | None = Query(default=None, ge=1970, le=2100),
) -> SeasonalityResponse:
    start = date(since, 1, 1) if since else None
    try:
        data_service.ensure_cached(ticker, market, start=start)
        df = data_service.get_ohlcv(ticker, market, start, None)
    except data_service.InvalidTicker as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except data_service.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    s = df.set_index(pd.to_datetime(df["date"]))["adj_close"].sort_index()
    if len(s) < 40:
        raise HTTPException(
            status_code=422, detail="not enough history to compute seasonality"
        )

    # --- Monthly returns (month-end close to month-end close) ------------------
    monthly_close = s.resample("ME").last()
    monthly_ret = monthly_close.pct_change().dropna()

    monthly = [
        MonthlyCell(year=int(idx.year), month=int(idx.month), return_pct=round(float(v), 6))
        for idx, v in monthly_ret.items()
    ]

    month_stats: list[MonthStat] = []
    for m in range(1, 13):
        vals = monthly_ret[monthly_ret.index.month == m]
        if vals.empty:
            continue
        month_stats.append(
            MonthStat(
                month=m,
                mean=round(float(vals.mean()), 6),
                positive_rate=round(float((vals > 0).mean()), 6),
                best=round(float(vals.max()), 6),
                worst=round(float(vals.min()), 6),
                count=int(vals.size),
            )
        )

    # --- Daily returns: weekday + turn-of-month -------------------------------
    daily = s.pct_change().dropna()

    weekday_stats: list[WeekdayStat] = []
    for wd in range(5):  # Mon..Fri
        vals = daily[daily.index.weekday == wd]
        if vals.empty:
            continue
        weekday_stats.append(
            WeekdayStat(
                weekday=wd,
                mean=round(float(vals.mean()), 8),
                positive_rate=round(float((vals > 0).mean()), 6),
                count=int(vals.size),
            )
        )

    # Rank each trading day from the end of its month; the last TURN_WINDOW are "turn".
    frame = daily.to_frame("ret")
    frame["period"] = frame.index.to_period("M")
    frame["from_end"] = frame.groupby("period").cumcount(ascending=False)
    turn = frame.loc[frame["from_end"] < TURN_WINDOW, "ret"]
    rest = frame.loc[frame["from_end"] >= TURN_WINDOW, "ret"]

    turn_of_month = TurnOfMonthStat(
        turn_mean=round(float(turn.mean()), 8) if not turn.empty else 0.0,
        rest_mean=round(float(rest.mean()), 8) if not rest.empty else 0.0,
        turn_count=int(turn.size),
        rest_count=int(rest.size),
    )

    try:
        meta = data_service.get_ticker(ticker, market)
        name = meta.name_ko or meta.name_en
    except data_service.TickerNotFound:
        name = ticker

    return SeasonalityResponse(
        ticker=ticker,
        market=market,
        name=name,
        start_year=int(s.index[0].year),
        end_year=int(s.index[-1].year),
        monthly=monthly,
        month_stats=month_stats,
        weekday_stats=weekday_stats,
        turn_of_month=turn_of_month,
    )
