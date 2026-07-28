"""Cross-asset signals — a condition may reference another asset's indicator.

Example: buy a KR stock when US QQQ crosses above its 10-day SMA. Hermetic: per-ticker
OHLCV is stubbed, so no network or cache is touched.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest import indicators  # noqa: E402
from app.backtest.engine import run_backtest  # noqa: E402
from app.schemas import (  # noqa: E402
    BacktestParams,
    Condition,
    IndicatorRef,
    Strategy,
)
from app.services import data_service  # noqa: E402


# --------------------------------------------------------------------------- #
# Alignment: the timezone-aware, lookahead-safe part
# --------------------------------------------------------------------------- #


def test_kr_primary_uses_the_us_signal_from_the_day_before():
    # US closes 16:00 ET, KR closes ~01:30 ET the SAME date — so a US close on date D is
    # only known to a KR bar on date D+1. aligned[KR D] must equal the US value of D-1.
    dates = pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04"])
    native = pd.Series([10.0, 20.0, 30.0])
    aligned = indicators._align_to_primary(
        native, pd.Series(dates), "US", pd.Series(dates), "KR", pd.RangeIndex(3)
    )
    assert np.isnan(aligned.iloc[0])          # no US close known yet at the first KR bar
    assert aligned.iloc[1] == 10.0            # KR 01-03 uses US 01-02
    assert aligned.iloc[2] == 20.0            # KR 01-04 uses US 01-03


def test_us_primary_uses_the_kr_signal_from_the_same_day():
    # KR closes hours BEFORE the US close, so a US bar may use the KR value of the same date.
    dates = pd.to_datetime(["2023-01-02", "2023-01-03", "2023-01-04"])
    native = pd.Series([10.0, 20.0, 30.0])
    aligned = indicators._align_to_primary(
        native, pd.Series(dates), "KR", pd.Series(dates), "US", pd.RangeIndex(3)
    )
    assert list(aligned) == [10.0, 20.0, 30.0]


# --------------------------------------------------------------------------- #
# End to end: trade a KR stock off a US QQQ signal
# --------------------------------------------------------------------------- #


DATES = pd.bdate_range("2023-01-02", periods=60)


def _frame(prices: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({
        "date": DATES, "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": np.ones(len(prices)), "adj_close": prices,
    })


@pytest.fixture
def two_assets(monkeypatch):
    # QQQ: falls for 20 bars then rallies — a clean SMA(10) cross-up, then a cross-down.
    qqq = np.concatenate([
        np.linspace(100, 80, 20),
        np.linspace(80, 120, 20),
        np.linspace(120, 90, 20),
    ])
    # The traded KR stock drifts gently up, so a buy→sell round trip books some P&L.
    kr = 1000.0 * np.power(1.0003, np.arange(len(DATES)))
    frames = {"QQQ": _frame(qqq), "005930": _frame(kr)}

    def fake_get_ohlcv(ticker, market, start=None, end=None):
        f = frames[ticker].copy()
        f["date"] = pd.to_datetime(f["date"])
        return f

    monkeypatch.setattr(data_service, "get_ohlcv", fake_get_ohlcv)
    monkeypatch.setattr(data_service, "ensure_cached", lambda *a, **k: False)
    monkeypatch.setattr(data_service, "board_of", lambda t, m: "KOSPI")


def _qqq_ref(kind, **params):
    return IndicatorRef(kind=kind, params=params, ticker="QQQ", market="US")


def test_buys_a_kr_stock_when_qqq_crosses_its_sma(two_assets):
    strategy = Strategy(
        name="QQQ 신호로 삼성전자 매매",
        description="미국 QQQ가 10일선을 상향돌파하면 매수, 하향돌파하면 매도",
        language="ko",
        buy_conditions=[
            Condition(left=_qqq_ref("PRICE_CLOSE"), operator="cross_above",
                      right=_qqq_ref("SMA", period=10)),
        ],
        sell_conditions=[
            Condition(left=_qqq_ref("PRICE_CLOSE"), operator="cross_below",
                      right=_qqq_ref("SMA", period=10)),
        ],
    )
    params = BacktestParams(
        ticker="005930", market="KR",
        start_date=dt.date(2023, 1, 20), end_date=dt.date(2023, 3, 24),
        initial_capital=10_000_000,
    )
    result = run_backtest(strategy, params)

    assert result.metrics.num_trades >= 1, "the QQQ cross should trigger a trade on 005930"
    # The traded asset is the KR stock, not QQQ — prices are ~1000, not ~100.
    assert result.trades[0].buy_price > 500


def test_label_shows_the_source_ticker():
    ref = _qqq_ref("SMA", period=10)
    assert ref.label().startswith("QQQ·")
    assert ref.cache_key() != IndicatorRef(kind="SMA", params={"period": 10}).cache_key()
