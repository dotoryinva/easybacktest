"""Cross-market (US+KR) portfolios — FX conversion, union/intersection calendars, D+1.

Hermetic: prices come from an injected loader and the FX factor is monkeypatched, so no
network or cache is touched.
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
from app.backtest import market_panel  # noqa: E402
from app.backtest import rotation_engine as re  # noqa: E402
from app.schemas import (  # noqa: E402
    AllocationHolding,
    DynamicAllocationRequest,
    StaticAllocationRequest,
)
from app.services import fx_service  # noqa: E402

BASE = list(pd.bdate_range("2018-01-01", "2021-12-31").date)
KR_HOLIDAY = BASE[100]   # a day KR is closed but US trades
US_HOLIDAY = BASE[150]   # a day US is closed but KR trades
KR_DATES = [d for d in BASE if d != KR_HOLIDAY]
US_DATES = [d for d in BASE if d != US_HOLIDAY]


def _loader(drifts: dict[str, float]):
    def load_fn(ticker: str, market: str, start):
        dates = KR_DATES if market == "KR" else US_DATES
        close = 100.0 * np.power(1.0 + drifts.get(ticker, 0.0003), np.arange(len(dates)))
        return pd.DataFrame({
            "date": pd.to_datetime(dates), "adj_open": close * 0.999, "adj_close": close,
        })

    return load_fn


@pytest.fixture
def fx_x3(monkeypatch):
    """US→KRW factor of exactly 3.0 (KR→KRW is 1.0), so conversion is easy to check."""
    monkeypatch.setattr(
        fx_service, "convert_factor",
        lambda from_market, base, index, s, e: 3.0 if from_market == "US" else 1.0,
    )


# --------------------------------------------------------------------------- #
# Panel builder
# --------------------------------------------------------------------------- #


def test_base_currency_inference():
    assert market_panel.base_currency_for({"KR", "US"}) == "KRW"
    assert market_panel.base_currency_for({"US"}) == "USD"
    assert market_panel.base_currency_for({"KR"}) == "KRW"


def test_fx_converts_the_us_leg_into_the_base_currency(fx_x3):
    close, _open, _cal = market_panel.build_panels(
        [("KODEX", "KR"), ("QQQ", "US")], "KRW", BASE[0], BASE[-1],
        load_fn=_loader({"KODEX": 0.0, "QQQ": 0.0}),  # flat at 100
    )
    # KR stays 100; US is multiplied by the 3.0 FX factor ⇒ 300.
    assert close["KODEX"].iloc[-1] == pytest.approx(100.0)
    assert close["QQQ"].iloc[-1] == pytest.approx(300.0)


def test_union_calendar_and_forward_fill(fx_x3):
    close, open_, _cal = market_panel.build_panels(
        [("KODEX", "KR"), ("QQQ", "US")], "KRW", BASE[0], BASE[-1], load_fn=_loader({}),
    )
    # The close panel spans the UNION of both calendars, forward-filled (no gaps).
    assert set(close.index) == set(BASE)
    assert not close.isna().any().any()
    # On the KR holiday the KR open is missing (can't trade) but US traded.
    assert np.isnan(open_.at[KR_HOLIDAY, "KODEX"])
    assert np.isfinite(open_.at[KR_HOLIDAY, "QQQ"])
    # ...yet the KR close is still marked (forward-filled) for daily MTM.
    assert np.isfinite(close.at[KR_HOLIDAY, "KODEX"])


def test_rebalance_calendar_is_the_intersection(fx_x3):
    _c, _o, cal = market_panel.build_panels(
        [("KODEX", "KR"), ("QQQ", "US")], "KRW", BASE[0], BASE[-1], load_fn=_loader({}),
    )
    # Rebalances only happen when BOTH markets are open.
    assert KR_HOLIDAY not in cal
    assert US_HOLIDAY not in cal
    assert set(cal) == set(BASE) - {KR_HOLIDAY, US_HOLIDAY}


# --------------------------------------------------------------------------- #
# Static — mixed holdings end to end
# --------------------------------------------------------------------------- #


def test_mixed_static_allocation_runs(monkeypatch, fx_x3):
    monkeypatch.setattr(market_panel, "_load_adj", _loader({"KODEX": 0.0002, "QQQ": 0.0006}))
    result = ae.run_static_allocation(
        StaticAllocationRequest(
            name="KR+US",
            market="KR",
            holdings=[
                AllocationHolding(ticker="KODEX", weight=50, market="KR"),
                AllocationHolding(ticker="QQQ", weight=50, market="US"),
            ],
            start_date=BASE[10],
            end_date=BASE[-1],
            initial_capital=100_000_000,
            rebalance="quarterly",
            benchmark="KODEX",  # reuse a loaded ticker as the benchmark
        )
    )
    assert result.equity_curve
    assert result.metrics.num_trades > 0
    # Both legs bought ⇒ the QQQ leg (faster drift) lifts the book above the start.
    assert result.equity_curve[-1].portfolio_value > 100_000_000


def test_single_market_still_uses_the_original_path(monkeypatch):
    # No FX, no market_panel — a pure-KR request must not touch the cross-market code.
    called = {"cross": False}
    monkeypatch.setattr(
        market_panel, "build_panels", lambda *a, **k: called.__setitem__("cross", True)
    )
    load_fn = _loader({})
    monkeypatch.setattr(
        ae, "_default_price_loader", lambda market, start=None: (lambda t: load_fn(t, market, start))
    )
    ae.run_static_allocation(
        StaticAllocationRequest(
            name="KR only", market="KR",
            holdings=[AllocationHolding(ticker="KODEX", weight=1, market="KR")],
            start_date=BASE[10], end_date=BASE[-1], initial_capital=1_000_000,
            benchmark="KODEX",
        )
    )
    assert called["cross"] is False, "single-market must not use the cross-market path"


# --------------------------------------------------------------------------- #
# Dynamic — cross-market QQQ→TIGER
# --------------------------------------------------------------------------- #


def test_qqq_trend_kr_runs_cross_market(monkeypatch, fx_x3):
    # QQQ strongly up ⇒ signal above its SMA ⇒ hold the KR nasdaq ETF (133690).
    monkeypatch.setattr(
        market_panel, "_load_adj",
        _loader({"QQQ": 0.0008, "133690": 0.0007, "148070": 0.0}),
    )
    monkeypatch.setattr(re, "_default_price_loader",
                        lambda market, start=None: lambda t: _loader({})(t, market, start))
    result = re.run_dynamic_allocation(
        DynamicAllocationRequest(
            strategy="qqq_trend_kr", start_date=BASE[260], end_date=BASE[-1],
            initial_capital=100_000_000,
        )
    )
    assert result.strategy_name == "나스닥 추세추종 (QQQ→TIGER)"
    assert result.equity_curve
    assert result.metrics.num_trades > 0


def test_qqq_trend_selects_the_bond_when_qqq_is_below_trend():
    closes = {}
    n = 300
    idx = pd.to_datetime(BASE[:n])
    closes["QQQ"] = pd.Series(100.0 * np.power(0.999, np.arange(n)), index=[d.date() for d in idx])
    closes["133690"] = pd.Series(np.full(n, 100.0), index=[d.date() for d in idx])
    closes["148070"] = pd.Series(np.full(n, 100.0), index=[d.date() for d in idx])
    dd = BASE[n - 1]
    # QQQ trending down ⇒ risk-off into the KR bond ETF.
    assert re._qqq_trend_kr(closes, dd, 12) == {"148070": 1.0}
