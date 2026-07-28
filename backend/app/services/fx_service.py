"""FX rates for cross-market portfolios (Change: US+KR mixing).

Only USD/KRW is needed today. Rates are lazy-fetched via FinanceDataReader and cached to
`data/fx/USDKRW.parquet`, then reindexed onto whatever trading calendar the caller needs
with a forward fill (a weekend/holiday uses the last known rate).
"""
from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

import pandas as pd

from ..config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
CURRENCY_OF_MARKET = {"KR": "KRW", "US": "USD"}


def _fx_path() -> "pd.Path":  # type: ignore[name-defined]
    from pathlib import Path

    return Path(settings.data_path) / "fx" / "USDKRW.parquet"


def _load_usdkrw(start: date, end: date) -> pd.Series:
    """KRW-per-USD daily close, cached and widened on demand."""
    path = _fx_path()
    have: pd.Series | None = None
    if path.exists():
        df = pd.read_parquet(path)
        have = pd.Series(df["rate"].to_numpy(), index=pd.to_datetime(df["date"]))
        covered_lo = have.index.min().date()
        covered_hi = have.index.max().date()
        if covered_lo <= start and covered_hi >= min(end, date.today()):
            return have

    with _lock:
        import FinanceDataReader as fdr  # noqa: PLC0415 - heavy, network

        fetch_start = min(start, (have.index.min().date() if have is not None else start))
        raw = fdr.DataReader("USD/KRW", fetch_start - timedelta(days=5), end)
        series = raw["Close"].dropna()
        series.index = pd.to_datetime(series.index)
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"date": series.index, "rate": series.to_numpy()}).to_parquet(
            path, index=False
        )
        logger.info("cached USD/KRW: %d rows %s..%s", len(series), fetch_start, end)
        return series


def usdkrw_on(index: pd.DatetimeIndex, start: date, end: date) -> pd.Series:
    """USD→KRW rate aligned onto `index` (forward-filled, then back-filled at the head)."""
    series = _load_usdkrw(start, end).sort_index()
    return series.reindex(series.index.union(index)).ffill().bfill().reindex(index)


def convert_factor(from_market: str, base_currency: str, index: pd.DatetimeIndex,
                   start: date, end: date) -> pd.Series | float:
    """Multiplier turning a `from_market` price into `base_currency`, per date in `index`.

    Same currency → 1.0. USD→KRW → the rate. KRW→USD → 1/rate.
    """
    src = CURRENCY_OF_MARKET.get(from_market, "USD")
    if src == base_currency:
        return 1.0
    rate = usdkrw_on(index, start, end)  # KRW per USD
    if src == "USD" and base_currency == "KRW":
        return rate
    if src == "KRW" and base_currency == "USD":
        return 1.0 / rate
    return 1.0
