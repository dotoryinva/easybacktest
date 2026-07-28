"""Cross-market price panels for mixed US+KR portfolios.

Builds base-currency open/close panels for tickers spanning both markets:

* Each ticker's adjusted prices are converted into the base currency via `fx_service`
  (KR→USD or US→KRW as needed).
* Close prices are indexed on the **union** of both calendars and forward-filled, so a
  holding always has a mark even on the other market's holiday (correct daily MTM).
* Open prices stay on their native dates (no fill) — you can only trade on a day the
  asset actually traded.
* The **rebalance calendar** is the intersection of the involved markets' trading days,
  so every target can execute at its open on a rebalance date.

Lookahead stays safe automatically: the sim decides from the prior union trading day's
close and fills at the next open, and any earlier calendar date's close (even a US 16:00
ET close) precedes the next date's earliest open (KR 09:00 KST ≈ 3h later). So a US-signal
→ KR-trade strategy is a genuine D+1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..services import data_service, fx_service
from .quant_engine import QuantBacktestError

# (ticker, market)
Spec = tuple[str, str]


def _load_adj(ticker: str, market: str, start) -> pd.DataFrame | None:
    """Adjusted open/close in the ticker's native currency, lazy-cached and widened."""
    try:
        data_service.ensure_cached(ticker, market, start=start)
        df = data_service.get_ohlcv(ticker, market)
    except data_service.TickerNotFound:
        return None
    factor = (df["adj_close"] / df["close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    return pd.DataFrame({
        "date": pd.to_datetime(df["date"]),
        "adj_open": df["open"] * factor,
        "adj_close": df["adj_close"],
    })


def build_panels(
    specs: list[Spec],
    base_currency: str,
    start,
    end,
    *,
    load_fn=None,
    apply_fx: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """Return (panel_close_ffilled, panel_open_native, rebalance_calendar).

    `load_fn(ticker, market, start) -> DataFrame[date, adj_open, adj_close]` is injectable
    for tests; it defaults to the lazy cache loader. With `apply_fx=False`, foreign prices
    are left in their native currency (useful only for comparing pure asset returns).
    """
    load_fn = load_fn or _load_adj
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    market_dates: dict[str, set] = {}

    for ticker, market in specs:
        df = load_fn(ticker, market, start)
        if df is None or df.empty:
            raise QuantBacktestError(f"no price data for {market}/{ticker}")
        s = df.set_index(pd.to_datetime(df["date"])).sort_index()
        fx = fx_service.convert_factor(market, base_currency, s.index, start, end) if apply_fx else 1.0
        closes[ticker] = s["adj_close"] * fx
        opens[ticker] = s["adj_open"] * fx
        market_dates.setdefault(market, set()).update(d.date() for d in s.index)

    panel_close = pd.DataFrame(closes).sort_index()
    panel_open = pd.DataFrame(opens).sort_index()
    panel_close.index = [d.date() for d in panel_close.index]
    panel_open.index = [d.date() for d in panel_open.index]
    panel_close = panel_close.sort_index().ffill()  # forward-fill for daily MTM
    panel_open = panel_open.sort_index()             # native — execution only

    # Rebalance only on days every involved market is open, so all targets can execute.
    date_sets = list(market_dates.values())
    common = set.intersection(*date_sets) if len(date_sets) > 1 else date_sets[0]
    rebalance_calendar = sorted(d for d in common if start <= d <= end)
    return panel_close, panel_open, rebalance_calendar


def base_currency_for(markets: set[str]) -> str:
    """KRW when any Korean asset is present (Korean-user default), else USD."""
    return "KRW" if "KR" in markets else "USD"
