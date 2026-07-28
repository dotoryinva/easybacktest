"""Correlation matrix across a small basket of tickers (Change 14, Tier 2).

Returns are computed from cached adjusted closes (lazy-loaded on first use), resampled to
the requested frequency and inner-joined on common dates before correlating.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..schemas import CorrelationRequest, CorrelationResponse, TickerStat
from ..services import data_service

router = APIRouter(prefix="/api/correlation", tags=["correlation"])

_PERIODS_PER_YEAR = {"daily": 252, "weekly": 52, "monthly": 12}
_RESAMPLE_RULE = {"weekly": "W-FRI", "monthly": "ME"}
# Approximate market close time in ET hours. KR closes ~01:30 ET (same calendar date),
# US at 16:00 ET — so a US close on date D is only reflected in a KR-listed asset the NEXT
# day. Matching cross-market returns by naive calendar date therefore compares offset
# periods and collapses the correlation toward zero; we align by close timestamp instead.
_CLOSE_HOUR_ET = {"KR": 1.5, "US": 16.0}


def _price_series(ticker: str, market: str, start, end) -> pd.Series | None:
    try:
        data_service.ensure_cached(ticker, market)
        df = data_service.get_ohlcv(ticker, market, start, end)
    except (data_service.TickerNotFound, data_service.InvalidTicker):
        return None
    s = df.set_index(pd.to_datetime(df["date"]))["adj_close"].sort_index()
    return s if len(s) >= 4 else None


def _period_returns(prices: pd.Series, frequency: str) -> pd.Series | None:
    s = prices.sort_index()
    if frequency in _RESAMPLE_RULE:
        s = s.resample(_RESAMPLE_RULE[frequency]).last()
    returns = s.pct_change().dropna()
    return returns if len(returns) >= 3 else None


def _cross_market_returns(
    entries: list[tuple[str, str, pd.Series]], frequency: str
) -> pd.DataFrame | None:
    """Align mixed-market prices, then resample and diff as one frame.

    Resampling each series separately after D+1 alignment can drift bucket edges when
    the index carries close-time offsets; a single frame resample keeps QQQ/133690-style
    trend peers correlated at weekly/monthly frequencies too.
    """
    aligned = _align_prices_by_close_time(entries)
    if aligned.empty:
        return None
    # Date-only index so W-FRI / ME buckets match calendar periods.
    aligned.index = aligned.index.normalize()
    if frequency in _RESAMPLE_RULE:
        aligned = aligned.resample(_RESAMPLE_RULE[frequency]).last()
    frame = aligned.pct_change().dropna(how="any")
    return frame if len(frame) >= 3 else None


def _align_prices_by_close_time(entries: list[tuple[str, str, pd.Series]]) -> pd.DataFrame:
    """Align mixed-market prices by close timestamp (no timezone lookahead).

    The reference timeline is the earliest-closing market's calendar. Every price series
    is as-of joined onto it, so a US close pairs with the KR close of the day it was
    actually knowable (US date D ↔ KR date D+1). Resampling happens after this alignment;
    otherwise weekly/monthly correlation compares offset periods.
    """
    ref_market = min({m for _, m, _ in entries}, key=lambda m: _CLOSE_HOUR_ET[m])
    ref_ts = sorted(
        set().union(*[
            {t + pd.Timedelta(hours=_CLOSE_HOUR_ET[m]) for t in prices.index}
            for _, m, prices in entries if m == ref_market
        ])
    )
    ref = pd.DataFrame({"ts": ref_ts}).sort_values("ts")

    cols: dict[str, list] = {}
    for ticker, market, prices in entries:
        src = pd.DataFrame({
            "ts": prices.index + pd.Timedelta(hours=_CLOSE_HOUR_ET[market]),
            "val": prices.to_numpy(),
        }).sort_values("ts")
        merged = pd.merge_asof(ref, src, on="ts", direction="backward")
        cols[ticker] = merged["val"].to_numpy()
    return pd.DataFrame(cols, index=ref["ts"]).dropna()


@router.post("/matrix", response_model=CorrelationResponse)
def matrix(body: CorrelationRequest) -> CorrelationResponse:
    entries: list[tuple[str, str, pd.Series]] = []
    for ref in body.tickers:
        prices = _price_series(ref.ticker, ref.market, body.start_date, body.end_date)
        if prices is not None:
            entries.append((ref.ticker, ref.market, prices))
    if len(entries) < 2:
        raise HTTPException(
            status_code=422,
            detail="need at least two tickers with overlapping price history",
        )

    markets = {m for _, m, _ in entries}
    if len(markets) == 1:
        returns = {
            ticker: r
            for ticker, _, prices in entries
            if (r := _period_returns(prices, body.frequency)) is not None
        }
        frame = pd.DataFrame(returns).dropna()
    else:
        # Mixed markets — align by close time, then resample the whole frame together.
        frame = _cross_market_returns(entries, body.frequency)
        if frame is None:
            raise HTTPException(
                status_code=422, detail="not enough overlapping dates to correlate",
            )
    if len(frame) < 3:
        raise HTTPException(
            status_code=422, detail="not enough overlapping dates to correlate",
        )

    tickers = list(frame.columns)
    corr = frame.corr().to_numpy()
    matrix_out = [[round(float(v), 4) for v in row] for row in corr]

    ann = _PERIODS_PER_YEAR[body.frequency]
    stats: list[TickerStat] = []
    for t in tickers:
        col = frame[t]
        mean = float(col.mean()) * ann
        std = float(col.std(ddof=0)) * np.sqrt(ann)
        stats.append(
            TickerStat(ticker=t, mean=mean, std=std, sharpe=(mean / std) if std > 0 else 0.0)
        )

    return CorrelationResponse(tickers=tickers, matrix=matrix_out, stats=stats)
