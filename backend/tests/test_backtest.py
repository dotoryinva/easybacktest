"""Backtest correctness checks from the Phase 1 validation list."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from app.backtest import indicators
from app.backtest.engine import run_backtest
from app.backtest.evaluator import evaluate_conditions
from app.schemas import BacktestParams, Condition, IndicatorRef, Strategy
from app.services import data_service


def sma_cross(fast: int, slow: int, **kw) -> Strategy:
    ind = lambda p: IndicatorRef(kind="SMA", params={"period": p})  # noqa: E731
    return Strategy(
        name=f"SMA {fast}/{slow}",
        description="test",
        language="en",
        buy_conditions=[Condition(left=ind(fast), operator="cross_above", right=ind(slow))],
        sell_conditions=[Condition(left=ind(fast), operator="cross_below", right=ind(slow))],
        **kw,
    )


def always_on(threshold: float = 50.0) -> IndicatorRef:
    return IndicatorRef(kind="CONSTANT", params={"value": threshold})


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #


def test_sma_and_ema_warmup_and_values():
    s = pd.Series([1.0, 2, 3, 4, 5, 6])
    out = indicators.sma(s, 3)
    assert out.iloc[:2].isna().all(), "warm-up bars must stay NaN, not be back-filled"
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[5] == pytest.approx(5.0)

    e = indicators.ema(s, 3)
    assert e.iloc[:2].isna().all()
    # Seeded from the 3-bar SMA (2.0), then recursive with alpha = 2/(3+1) = 0.5.
    assert e.iloc[2] == pytest.approx(2.0)
    assert e.iloc[3] == pytest.approx(3.0)


def test_rsi_bounds_and_all_up_series():
    up = pd.Series(np.arange(1, 40, dtype="float64"))
    r = indicators.rsi(up, 14)
    assert r.iloc[:13].isna().all()
    assert r.dropna().max() == pytest.approx(100.0)

    noisy = pd.Series(np.random.default_rng(0).normal(100, 3, 300).cumsum() / 10 + 100)
    rn = indicators.rsi(noisy, 14).dropna()
    assert rn.between(0, 100).all()


def test_cross_above_requires_opposite_sides_on_consecutive_days():
    # fast sits below, touches equal, then breaks above.
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=6, freq="D"),
            "open": 1.0, "high": 1.0, "low": 1.0, "volume": 1.0,
            "close": [10.0, 10, 10, 10, 10, 10],
            "adj_close": [10.0, 10, 10, 10, 10, 10],
        }
    )
    left = pd.Series([1.0, 2, 3, 3, 5, 6])
    right = pd.Series([3.0, 3, 3, 3, 3, 3])

    from app.backtest.evaluator import _compare

    ca = _compare(left, "cross_above", right)
    # index 3 is equal-to-equal (no cross); index 4 crosses from equal to above.
    assert list(ca) == [False, False, False, False, True, False]

    cb = _compare(right, "cross_below", left)
    assert list(cb) == [False, False, False, False, True, False]


def test_nan_never_produces_a_true_signal():
    from app.backtest.evaluator import _compare

    left = pd.Series([np.nan, np.nan, 5.0])
    right = pd.Series([1.0, 1.0, 1.0])
    assert list(_compare(left, ">", right)) == [False, False, True]
    assert list(_compare(left, "cross_above", right)) == [False, False, False]


# --------------------------------------------------------------------------- #
# Execution model
# --------------------------------------------------------------------------- #


def test_fees_and_slippage_on_a_single_round_trip(synthetic):
    """$100 buy / $110 sell, 0.025% fees + 0.1% slippage: pnl is ~$9.73, not $10.

    Derivation for one share:
        buy fill   = 100 * (1 + 0.001)            = 100.10
        buy cost   = 100.10 * (1 + 0.00025)       = 100.125025
        sell fill  = 110 * (1 - 0.001)            = 109.89
        proceeds   = 109.89 * (1 - 0.00025 - 0.0000278)
        pnl        = proceeds - buy cost          = 9.7343...
    The spec quotes ~$9.75; the exact figure depends on the SEC fee, which is
    included here.
    """
    synthetic(
        [
            {"date": "2024-01-02", "open": 100, "high": 100, "low": 100, "close": 100},
            {"date": "2024-01-03", "open": 100, "high": 300, "low": 100, "close": 300},
            {"date": "2024-01-04", "open": 110, "high": 110, "low": 110, "close": 110},
            {"date": "2024-01-05", "open": 110, "high": 110, "low": 110, "close": 110},
        ]
    )
    strategy = Strategy(
        name="round trip", description="test", language="en",
        buy_conditions=[
            Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(50))
        ],
        sell_conditions=[
            Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(200))
        ],
    )
    params = BacktestParams(
        ticker="TEST", market="US",
        start_date=dt.date(2024, 1, 1), end_date=dt.date(2024, 1, 5),
        initial_capital=150, slippage=0.001,
    )
    result = run_backtest(strategy, params)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.shares == 1
    assert trade.buy_date == dt.date(2024, 1, 3)
    assert trade.buy_price == pytest.approx(100.10)
    assert trade.sell_date == dt.date(2024, 1, 4)
    assert trade.sell_price == pytest.approx(109.89)

    buy_cost = 100.10 * 1.00025
    proceeds = 109.89 * (1 - 0.00025 - 0.0000278)
    assert trade.pnl == pytest.approx(proceeds - buy_cost, abs=1e-6)
    assert trade.pnl == pytest.approx(9.734, abs=0.01)
    assert trade.pnl < 9.79, "costs must reduce the raw 9.79 slippage-adjusted spread"


def test_stop_loss_fires_at_next_open_not_the_same_day_low(synthetic):
    """A 5% intraday drop triggers the stop, but the fill is the NEXT day's open."""
    synthetic(
        [
            {"date": "2024-01-02", "open": 100, "high": 100, "low": 100, "close": 100},
            {"date": "2024-01-03", "open": 100, "high": 101, "low": 100, "close": 100},
            # -6% intraday, closes flat: the stop is armed off this bar's low.
            {"date": "2024-01-04", "open": 100, "high": 100, "low": 94, "close": 99},
            {"date": "2024-01-05", "open": 97, "high": 97, "low": 97, "close": 97},
        ]
    )
    strategy = Strategy(
        name="stop test", description="test", language="en",
        buy_conditions=[
            Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(50))
        ],
        stop_loss_pct=0.05,
    )
    params = BacktestParams(
        ticker="TEST", market="US",
        start_date=dt.date(2024, 1, 1), end_date=dt.date(2024, 1, 5),
        initial_capital=10_000, slippage=0.0,
    )
    result = run_backtest(strategy, params)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.sell_date == dt.date(2024, 1, 5)
    assert trade.sell_price == pytest.approx(97.0), "must fill at the next open, not the 94 low"


def test_take_profit_and_max_holding_days(synthetic):
    synthetic(
        [
            {"date": "2024-01-02", "open": 100, "high": 100, "low": 100, "close": 100},
            {"date": "2024-01-03", "open": 100, "high": 100, "low": 100, "close": 100},
            {"date": "2024-01-04", "open": 100, "high": 121, "low": 100, "close": 120},
            {"date": "2024-01-05", "open": 118, "high": 118, "low": 118, "close": 118},
        ]
    )
    buy = [Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(50))]

    tp = run_backtest(
        Strategy(name="tp", description="t", language="en", buy_conditions=buy, take_profit_pct=0.20),
        BacktestParams(ticker="T", market="US", start_date=dt.date(2024, 1, 1),
                       end_date=dt.date(2024, 1, 5), initial_capital=10_000, slippage=0.0),
    )
    assert tp.trades[0].exit_reason == "take_profit"
    assert tp.trades[0].sell_date == dt.date(2024, 1, 5)

    mh = run_backtest(
        Strategy(name="mh", description="t", language="en", buy_conditions=buy, max_holding_days=1),
        BacktestParams(ticker="T", market="US", start_date=dt.date(2024, 1, 1),
                       end_date=dt.date(2024, 1, 5), initial_capital=10_000, slippage=0.0),
    )
    assert mh.trades[0].exit_reason == "max_holding_days"
    # Entered at the 01-03 open, held one bar, exited at the 01-05 open.
    assert (mh.trades[0].buy_date, mh.trades[0].sell_date) == (dt.date(2024, 1, 3), dt.date(2024, 1, 5))


def test_no_lookahead_signal_never_fills_on_its_own_bar(synthetic):
    synthetic(
        [
            {"date": "2024-01-02", "open": 10, "high": 10, "low": 10, "close": 10},
            {"date": "2024-01-03", "open": 20, "high": 20, "low": 20, "close": 20},
            {"date": "2024-01-04", "open": 30, "high": 30, "low": 30, "close": 30},
        ]
    )
    strategy = Strategy(
        name="lookahead", description="t", language="en",
        buy_conditions=[
            Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(5))
        ],
        max_holding_days=1,
    )
    result = run_backtest(
        strategy,
        BacktestParams(ticker="T", market="US", start_date=dt.date(2024, 1, 1),
                       end_date=dt.date(2024, 1, 4), initial_capital=1000, slippage=0.0),
    )
    # The signal is true at the 01-02 close; the fill is the 01-03 open (20), never 10.
    assert result.trades[0].buy_date == dt.date(2024, 1, 3)
    assert result.trades[0].buy_price == pytest.approx(20.0)


def test_position_sizing_modes(synthetic):
    rows = [
        {"date": "2024-01-02", "open": 100, "high": 100, "low": 100, "close": 100},
        {"date": "2024-01-03", "open": 100, "high": 100, "low": 100, "close": 100},
        {"date": "2024-01-04", "open": 100, "high": 100, "low": 100, "close": 100},
    ]
    buy = [Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(50))]
    params = BacktestParams(ticker="T", market="US", start_date=dt.date(2024, 1, 1),
                            end_date=dt.date(2024, 1, 4), initial_capital=10_000,
                            slippage=0.0, fee_rate=0.0, sell_tax_rate=0.0)

    synthetic(rows)
    all_in = run_backtest(
        Strategy(name="a", description="t", language="en", buy_conditions=buy, max_holding_days=5),
        params,
    )
    assert all_in.trades[0].shares == 100

    synthetic(rows)
    fixed = run_backtest(
        Strategy(name="b", description="t", language="en", buy_conditions=buy,
                 max_holding_days=5, position_sizing="fixed_amount", position_size_value=2500),
        params,
    )
    assert fixed.trades[0].shares == 25

    synthetic(rows)
    pct = run_backtest(
        Strategy(name="c", description="t", language="en", buy_conditions=buy,
                 max_holding_days=5, position_sizing="percent_of_capital", position_size_value=0.5),
        params,
    )
    assert pct.trades[0].shares == 50


def test_cooldown_blocks_immediate_reentry(synthetic):
    rows = [{"date": f"2024-01-{d:02d}", "open": 100, "high": 100, "low": 100, "close": 100}
            for d in range(2, 12)]
    buy = [Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator=">", right=always_on(50))]
    params = BacktestParams(ticker="T", market="US", start_date=dt.date(2024, 1, 1),
                            end_date=dt.date(2024, 1, 12), initial_capital=10_000,
                            slippage=0.0, fee_rate=0.0, sell_tax_rate=0.0)

    synthetic(rows)
    hot = run_backtest(
        Strategy(name="hot", description="t", language="en", buy_conditions=buy, max_holding_days=1),
        params,
    )
    synthetic(rows)
    cool = run_backtest(
        Strategy(name="cool", description="t", language="en", buy_conditions=buy,
                 max_holding_days=1, cooldown_days_after_exit=3),
        params,
    )
    assert len(cool.trades) < len(hot.trades)


# --------------------------------------------------------------------------- #
# Checks against real cached data
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not data_service.ohlcv_file("AAPL", "US").exists(), reason="AAPL not bootstrapped"
)
def test_buy_and_hold_aapl_matches_adjusted_price_appreciation():
    """AAPL 2015-01-01 -> 2024-12-31, $10,000: within 0.5% of the raw adj-close ratio."""
    start, end = dt.date(2015, 1, 1), dt.date(2024, 12, 31)
    strategy = Strategy(
        name="never trades", description="t", language="en",
        buy_conditions=[
            Condition(left=IndicatorRef(kind="PRICE_CLOSE"), operator="<", right=always_on(0.0))
        ],
        stop_loss_pct=0.5,
    )
    params = BacktestParams(ticker="AAPL", market="US", start_date=start, end_date=end,
                            initial_capital=10_000)
    result = run_backtest(strategy, params)
    assert result.metrics.num_trades == 0

    raw = data_service.get_ohlcv("AAPL", "US", start, end)
    first, final = raw.iloc[0], raw.iloc[-1]

    # Hand calculation: buy at the first bar's adjusted open with slippage and the US
    # commission, hold to the last adjusted close.
    factor = first["adj_close"] / first["close"]
    entry = first["open"] * factor * 1.001
    shares = int(10_000 // (entry * 1.00025))
    manual = (10_000 - shares * entry * 1.00025 + shares * final["adj_close"]) / 10_000

    engine = result.equity_curve[-1].buy_hold_value / 10_000
    naive_close_to_close = final["adj_close"] / first["adj_close"]
    print(
        f"\nAAPL 2015-2024 buy & hold: engine {engine - 1:.2%}, "
        f"hand calc {manual - 1:.2%}, naive close-to-close {naive_close_to_close - 1:.2%}"
    )
    assert abs(engine - manual) / manual < 0.005

    # The residual against a close-to-close quote (what Yahoo shows) is the first bar's
    # open-to-close move plus costs — AAPL opened ~1.9% above its 2015-01-02 close.
    assert abs(engine - naive_close_to_close) / naive_close_to_close < 0.03


@pytest.mark.skipif(
    not data_service.ohlcv_file("005930", "KR").exists(), reason="005930 not bootstrapped"
)
def test_samsung_sma_20_60_entries_follow_a_real_crossover():
    """Every entry must be the bar after a genuine SMA20/SMA60 cross."""
    start, end = dt.date(2020, 1, 1), dt.date(2024, 12, 31)
    result = run_backtest(
        sma_cross(20, 60),
        BacktestParams(ticker="005930", market="KR", start_date=start, end_date=end,
                       initial_capital=10_000_000),
    )
    assert result.metrics.num_trades >= 3

    df = data_service.get_ohlcv("005930", "KR", start - dt.timedelta(days=200), end)
    fast = indicators.sma(df["adj_close"], 20)
    slow = indicators.sma(df["adj_close"], 60)
    crossed_up = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
    cross_dates = set(df.loc[crossed_up, "date"].dt.date)
    bar_dates = list(df["date"].dt.date)

    for trade in result.trades[:3]:
        i = bar_dates.index(trade.buy_date)
        assert i > 0, "an entry cannot be the first available bar"
        assert bar_dates[i - 1] in cross_dates, (
            f"entry {trade.buy_date} is not the bar after an SMA20/60 cross"
        )
        assert trade.sell_date > trade.buy_date


@pytest.mark.skipif(
    not data_service.ohlcv_file("AAPL", "US").exists(), reason="AAPL not bootstrapped"
)
def test_equity_curve_and_metrics_are_self_consistent():
    result = run_backtest(
        sma_cross(20, 60),
        BacktestParams(ticker="AAPL", market="US", start_date=dt.date(2020, 1, 1),
                       end_date=dt.date(2024, 12, 31), initial_capital=10_000),
    )
    curve = result.equity_curve
    assert curve[0].date >= dt.date(2020, 1, 1), "warm-up must be pre-loaded, not eaten"
    assert all(p.portfolio_value > 0 for p in curve)
    for p in curve:
        assert p.portfolio_value == pytest.approx(p.cash + p.position_value, rel=1e-6)

    values = np.array([p.portfolio_value for p in curve])
    peaks = np.maximum.accumulate(values)
    assert result.metrics.mdd == pytest.approx(((values - peaks) / peaks).min(), rel=1e-6)
    assert result.metrics.total_return_pct == pytest.approx(values[-1] / 10_000 - 1, rel=1e-6)
    assert result.metrics.mdd <= 0
    assert 0 <= result.metrics.win_rate <= 1
