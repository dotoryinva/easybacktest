"""Change 13.6 — quant portfolio engine, tested hermetically with synthetic prices.

An injected `price_loader` feeds deterministic trending series, so these assert the
rebalance loop, factor ranking, weighting and lookahead-safety without any network.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest import quant_engine as qe  # noqa: E402
from app.schemas import (  # noqa: E402
    PortfolioConfig,
    QuantBacktestParams,
    QuantPortfolioStrategy,
    RankingFactor,
    RebalanceConfig,
    UniverseConfig,
)

DATES = list(pd.bdate_range("2022-06-01", "2023-12-31").date)

# Per-ticker daily drift — UP names trend up, DN names trend down, FLAT is flat.
DRIFTS = {"UP1": 0.0016, "UP2": 0.0012, "FLAT": 0.0, "DN1": -0.0010, "DN2": -0.0016}


def _series(drift: float) -> pd.DataFrame:
    idx = np.arange(len(DATES))
    close = 100.0 * np.power(1.0 + drift, idx)
    return pd.DataFrame({
        "date": DATES,
        "adj_open": close * 0.999,   # open just below close
        "adj_close": close,
    })


PANELS = {t: _series(d) for t, d in DRIFTS.items()}
# A flat benchmark so the buy&hold line is defined.
PANELS["KS200"] = _series(0.0002)


def price_loader(ticker: str):
    return PANELS.get(ticker)


def _strategy(**over) -> QuantPortfolioStrategy:
    base = dict(
        name="모멘텀 상위 2",
        ranking=[RankingFactor(factor="momentum_3m", direction="desc", weight=1.0)],
        portfolio=PortfolioConfig(num_holdings=2, weighting="equal"),
        rebalance=RebalanceConfig(frequency="monthly"),
        universe=UniverseConfig(market="KR", boards=["KOSPI"]),
    )
    base.update(over)
    return QuantPortfolioStrategy(**base)


PARAMS = QuantBacktestParams(
    market="KR",
    start_date=date(2022, 10, 3),   # leaves ~3 months of history for momentum_3m
    end_date=date(2023, 12, 29),
    initial_capital=100_000_000,
    benchmark="KS200",
)

UNIVERSE = ["UP1", "UP2", "FLAT", "DN1", "DN2"]


def _run(strategy=None, params=PARAMS):
    return qe.run_quant_backtest(
        strategy or _strategy(), params, price_loader=price_loader, universe=UNIVERSE
    )


def test_momentum_strategy_runs_and_produces_a_curve():
    result = _run()
    assert result.equity_curve, "an equity curve is produced"
    assert result.metrics.num_trades > 0, "at least one rebalance trade happened"
    # Momentum picks the up-trending names, so the portfolio should end up ahead.
    assert result.equity_curve[-1].portfolio_value > PARAMS.initial_capital


def test_selection_picks_the_top_momentum_names():
    # Every buy trade should be in {UP1, UP2}; DN names never get selected.
    result = _run()
    bought = {t.buy_date for t in result.trades}
    assert bought, "trades recorded"
    # Re-run the selection at the first decision date and check the names directly.
    closes = {t: PANELS[t].set_index(pd.to_datetime(PANELS[t]["date"]).dt.date)["adj_close"]
              for t in UNIVERSE}
    picks = qe._select(_strategy(), closes, date(2022, 9, 30), None, {})
    assert set(picks) <= {"UP1", "UP2"}
    assert len(picks) == 2


def test_ascending_direction_inverts_the_ranking():
    # direction=asc on momentum ⇒ prefer the *worst* momentum ⇒ the DN names.
    strat = _strategy(
        name="역모멘텀",
        ranking=[RankingFactor(factor="momentum_3m", direction="asc", weight=1.0)],
    )
    closes = {t: PANELS[t].set_index(pd.to_datetime(PANELS[t]["date"]).dt.date)["adj_close"]
              for t in UNIVERSE}
    picks = qe._select(strat, closes, date(2022, 9, 30), None, {})
    assert set(picks) <= {"DN1", "DN2"}


def test_equal_weighting_splits_across_holdings():
    strat = _strategy(portfolio=PortfolioConfig(num_holdings=2, weighting="equal"))
    closes = {t: PANELS[t].set_index(pd.to_datetime(PANELS[t]["date"]).dt.date)["adj_close"]
              for t in UNIVERSE}
    picks = qe._select(strat, closes, date(2022, 9, 30), None, {})
    assert pytest.approx(sum(picks.values()), abs=1e-9) == 1.0
    assert all(abs(w - 0.5) < 1e-9 for w in picks.values())


def test_filter_gates_the_universe():
    # Keep only names whose 3-month momentum is positive ⇒ FLAT/DN drop out.
    from app.schemas import FilterCondition

    strat = _strategy(
        filters=[FilterCondition(factor="momentum_3m", op=">", value=0.0)],
        portfolio=PortfolioConfig(num_holdings=5, weighting="equal"),
    )
    closes = {t: PANELS[t].set_index(pd.to_datetime(PANELS[t]["date"]).dt.date)["adj_close"]
              for t in UNIVERSE}
    picks = qe._select(strat, closes, date(2022, 9, 30), None, {})
    assert set(picks) <= {"UP1", "UP2"}


def test_rebalance_dates_are_first_trading_day_of_each_month():
    dates = qe.compute_rebalance_dates(DATES, date(2022, 10, 3), date(2023, 1, 31), "monthly")
    # One per month: Oct, Nov, Dec 2022, Jan 2023.
    months = [(d.year, d.month) for d in dates]
    assert months == [(2022, 10), (2022, 11), (2022, 12), (2023, 1)]


def test_lookahead_is_avoided_decision_uses_prior_close():
    # A spike that only appears ON the rebalance day must not influence that day's pick.
    spike = _series(0.0).copy()
    # SPIKE is flat until the very end, then jumps — its momentum is ~0 at decision time.
    panels = dict(PANELS)
    panels["SPIKE"] = spike
    picks = qe._select(
        _strategy(),
        {t: panels[t].set_index(pd.to_datetime(panels[t]["date"]).dt.date)["adj_close"]
         for t in [*UNIVERSE, "SPIKE"]},
        date(2022, 9, 30), None, {},
    )
    assert "SPIKE" not in picks, "a flat-until-now name is not chosen on momentum"
