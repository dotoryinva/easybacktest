"""Price-derived metric snapshot over a set of tickers (Change 17).

Powers the Heatmap, ETF browser and Screener pages. The ticker universe has no populated
market-cap / sector / fundamentals, so every metric here is derived from cached adjusted
closes: trailing returns, annualised volatility, RSI(14) and distance from the 200-day SMA /
52-week high. A curated list of liquid names is warmed (in parallel, on a wall-clock budget)
so the pages are populated even on a cold cache; whatever is already cached is always
included.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import numpy as np
import pandas as pd

from . import data_service

logger = logging.getLogger(__name__)

# Liquid, widely-followed names so the pages have real content on first load. Overlaps with
# whatever users have already browsed (which is merged in). Not meant to be exhaustive.
CURATED: dict[str, list[str]] = {
    "KR": [
        # large-cap stocks
        "005930", "000660", "373220", "207940", "005380", "000270", "068270", "051910",
        "006400", "035420", "035720", "105560", "055550", "012330", "066570", "015760",
        "034730", "032830", "003670", "028260",
        # major ETFs
        "069500", "133690", "360750", "114260", "132030", "305720", "091160",
    ],
    "US": [
        # mega-cap stocks
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "JPM", "V",
        "WMT", "XOM", "UNH", "JNJ", "PG", "MA", "HD", "COST", "KO", "BAC",
        # major ETFs
        "SPY", "QQQ", "DIA", "IWM", "VTI", "TLT", "GLD", "XLK", "XLF", "XLE",
    ],
}

_LOOKBACK = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252}


def _warm(market: str, tickers: list[str], budget_seconds: float) -> None:
    """Best-effort parallel cache warm with a wall-clock deadline."""
    deadline = time.monotonic() + budget_seconds
    missing = [t for t in tickers if data_service.cached_range(t, market) is None]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(data_service.ensure_cached, t, market): t for t in missing}
        for fut in as_completed(futures):
            if time.monotonic() > deadline:
                break
            try:
                fut.result(timeout=max(0.1, deadline - time.monotonic()))
            except Exception:  # noqa: BLE001 - a single ticker failing must not sink the page
                logger.debug("warm failed for %s/%s", market, futures[fut])


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _pct(cur: float, prev: float) -> float | None:
    if prev is None or not np.isfinite(prev) or prev <= 0:
        return None
    return round((cur / prev - 1.0) * 100.0, 2)


def _metrics_for(closes: pd.Series) -> dict | None:
    s = closes.dropna()
    if len(s) < 6:
        return None
    last = float(s.iloc[-1])
    if not np.isfinite(last) or last <= 0:
        return None
    out: dict = {"price": round(last, 2)}

    for label, n in _LOOKBACK.items():
        out[f"ret_{label}"] = _pct(last, float(s.iloc[-1 - n])) if len(s) > n else None

    # Year-to-date: first close on/after Jan 1 of the last bar's year.
    year_start = pd.Timestamp(year=s.index[-1].year, month=1, day=1)
    ytd = s[s.index >= year_start]
    out["ret_ytd"] = _pct(last, float(ytd.iloc[0])) if len(ytd) >= 2 else None

    daily = s.pct_change().dropna().tail(252)
    out["vol_ann"] = round(float(daily.std(ddof=0) * np.sqrt(252) * 100.0), 2) if len(daily) >= 20 else None

    out["rsi_14"] = round(v, 1) if (v := _rsi(s)) is not None else None

    if len(s) >= 200:
        sma200 = float(s.tail(200).mean())
        out["dist_sma200"] = _pct(last, sma200)
    else:
        out["dist_sma200"] = None

    high52 = float(s.tail(252).max())
    out["dist_high52w"] = _pct(last, high52)  # ≤ 0: how far below the 52w high
    return out


def _row_for(ticker: str, market: str, *, ensure: bool = False) -> dict | None:
    """One metric row for a ticker, or None if it has no usable price history."""
    try:
        if ensure:
            data_service.ensure_cached(ticker, market)
        df = data_service.get_ohlcv(ticker, market)
    except (data_service.TickerNotFound, data_service.InvalidTicker):
        return None
    if df is None or df.empty:
        return None
    closes = df.set_index(pd.to_datetime(df["date"]))["adj_close"].sort_index()
    metrics = _metrics_for(closes)
    if metrics is None:
        return None
    try:
        meta = data_service.get_ticker(ticker, market)
        name_ko, name_en, kind = meta.name_ko, meta.name_en, meta.kind
    except data_service.TickerNotFound:
        name_ko, name_en, kind = None, ticker, "stock"
    return {
        "ticker": ticker,
        "market": market,
        "name_ko": name_ko,
        "name_en": name_en,
        "kind": kind,
        "as_of": closes.index[-1].date(),
        **metrics,
    }


def compute_snapshot(market: str, *, warm_budget: float = 18.0) -> list[dict]:
    """Metric rows for the curated + already-cached universe of `market`."""
    curated = CURATED.get(market, [])
    _warm(market, curated, warm_budget)

    tickers = sorted(set(curated) | set(data_service.list_cached(market)))
    rows = [_row_for(t, market) for t in tickers]
    return [r for r in rows if r is not None]


def compute_quotes(pairs: list[tuple[str, str]], *, warm_budget: float = 20.0) -> list[dict]:
    """Metric rows for an explicit list of (ticker, market) — e.g. a watchlist.

    Unlike the snapshot, these tickers are arbitrary, so any that are not yet cached are
    fetched on demand (in parallel, within a wall-clock budget)."""
    missing_by_market: dict[str, list[str]] = {}
    for ticker, market in pairs:
        if data_service.cached_range(ticker, market) is None:
            missing_by_market.setdefault(market, []).append(ticker)
    for market, tickers in missing_by_market.items():
        _warm(market, tickers, warm_budget)

    rows = [_row_for(t, m) for t, m in pairs]
    return [r for r in rows if r is not None]
