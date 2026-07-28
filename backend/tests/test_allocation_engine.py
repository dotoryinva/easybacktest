"""Change 14 정적배분 — fixed-weight allocation engine + cache-widening regression.

Hermetic: prices come from an injected loader, so no network or Parquet cache is used.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest import allocation_engine as ae  # noqa: E402
from app.backtest import quant_engine as qe  # noqa: E402
from app.schemas import AllocationHolding, StaticAllocationRequest  # noqa: E402
from app.services import data_service as ds  # noqa: E402

DATES = list(pd.bdate_range("2020-01-01", "2022-12-30").date)


def _panel(drift: float) -> pd.DataFrame:
    close = 100.0 * np.power(1.0 + drift, np.arange(len(DATES)))
    return pd.DataFrame({"date": DATES, "adj_open": close * 0.999, "adj_close": close})


PANELS = {
    "STOCK": _panel(0.0006),   # rises
    "BOND": _panel(0.00005),   # nearly flat
    "^GSPC": _panel(0.0004),
}


@pytest.fixture
def loader(monkeypatch):
    monkeypatch.setattr(ae, "_default_price_loader", lambda market, start=None: PANELS.get)


def _request(**over) -> StaticAllocationRequest:
    base = dict(
        name="60/40",
        market="US",
        holdings=[
            AllocationHolding(ticker="STOCK", weight=60),
            AllocationHolding(ticker="BOND", weight=40),
        ],
        start_date=date(2020, 1, 2),
        end_date=date(2022, 12, 29),
        initial_capital=100_000,
        rebalance="quarterly",
        benchmark="^GSPC",
    )
    base.update(over)
    return StaticAllocationRequest(**base)


def test_static_allocation_runs_and_holds_both_sleeves(loader):
    result = ae.run_static_allocation(_request())
    assert result.equity_curve
    assert result.metrics.num_trades > 0
    traded = {t.buy_price for t in result.trades}
    assert traded, "trades recorded"
    # A 60/40 of a riser and a flat bond ends up ahead of where it started.
    assert result.equity_curve[-1].portfolio_value > 100_000


def test_weights_are_normalised(loader):
    # 6 and 4 must behave exactly like 60 and 40 — only the ratio matters.
    a = ae.run_static_allocation(_request())
    b = ae.run_static_allocation(
        _request(holdings=[
            AllocationHolding(ticker="STOCK", weight=6),
            AllocationHolding(ticker="BOND", weight=4),
        ])
    )
    assert a.equity_curve[-1].portfolio_value == b.equity_curve[-1].portfolio_value


def test_quarterly_rebalances_more_often_than_annual(loader):
    q = ae.run_static_allocation(_request(rebalance="quarterly"))
    y = ae.run_static_allocation(_request(rebalance="annual"))
    assert q.metrics.num_trades > y.metrics.num_trades


def test_benchmark_line_starts_at_initial_capital(loader):
    result = ae.run_static_allocation(_request())
    assert result.equity_curve[0].buy_hold_value == pytest.approx(100_000, rel=1e-6)


def test_unknown_ticker_is_rejected(monkeypatch):
    monkeypatch.setattr(ae, "_default_price_loader", lambda market, start=None: lambda t: None)
    with pytest.raises(qe.QuantBacktestError):
        ae.run_static_allocation(_request())


# --------------------------------------------------------------------------- #
# Cache widening (regression: a shallow cache silently truncated history)
# --------------------------------------------------------------------------- #


def test_ensure_cached_widens_a_too_shallow_window(monkeypatch, tmp_path):
    """A file cached from 2021 must be re-fetched when 2019 history is requested."""
    calls: list = []

    def fake_fetch(ticker, market, start, end):
        calls.append(start)
        idx = pd.bdate_range(start, periods=30)
        return pd.DataFrame({
            "date": idx, "open": 1.0, "high": 1.0, "low": 1.0,
            "close": 1.0, "volume": 1.0, "adj_close": 1.0,
        })

    path = tmp_path / "X.parquet"
    monkeypatch.setattr(ds, "ohlcv_file", lambda t, m: path)
    monkeypatch.setattr(ds, "in_universe", lambda t, m: True)
    monkeypatch.setattr("app.data_providers.fetch_ohlcv", fake_fetch)

    # Seed a cache that only reaches back to 2021.
    monkeypatch.setattr(ds, "cached_range", lambda t, m: (date(2021, 7, 19), date(2026, 1, 1)))
    path.write_bytes(b"")  # existence is what the coverage check keys off

    # Asking for 2019 must trigger a wider re-fetch...
    assert ds.ensure_cached("X", "US", start=date(2019, 1, 2)) is True
    assert calls and calls[0] <= date(2019, 1, 2)

    # ...but asking for 2022 (already covered) must not.
    calls.clear()
    assert ds.ensure_cached("X", "US", start=date(2022, 1, 3)) is False
    assert calls == []
