"""Change 15 — unified allocation engine: algorithms, band, momentum, extraction.

Hermetic: `market_panel._load_adj` is stubbed with synthetic per-ticker frames, so no
network or cache is touched. All assets are KR (no FX invoked).
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
from app.backtest.allocation_algorithms import compute_weights  # noqa: E402
from app.schemas import (  # noqa: E402
    AllocationBacktestParams,
    AllocationStrategy,
    AssetSlot,
    MomentumTiming,
)

DATES = list(pd.bdate_range("2018-01-01", "2021-12-31").date)


def _frame(prices: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(DATES), "adj_open": prices * 0.999, "adj_close": prices})


def _series(drift: float, vol: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, len(DATES))
    return 100.0 * np.cumprod(1 + rets)


# STOCK: upward, high vol. BOND: flat, low vol. CASH(safe): flat, tiny vol.
PANELS = {
    "STOCK": _frame(_series(0.0005, 0.012, 1)),
    "BOND": _frame(_series(0.0001, 0.003, 2)),
    "CASH": _frame(_series(0.00005, 0.001, 3)),
}


@pytest.fixture
def stub_prices(monkeypatch):
    monkeypatch.setattr(
        market_panel, "_load_adj",
        lambda ticker, market, start: PANELS[ticker].copy(),
    )


# --------------------------------------------------------------------------- #
# Algorithms (unit)
# --------------------------------------------------------------------------- #


def _returns(tickers):
    cols = {t: pd.Series(PANELS[t]["adj_close"].to_numpy(), index=pd.to_datetime(DATES)) for t in tickers}
    return pd.DataFrame(cols).pct_change().dropna()


def test_equal_weight():
    w = compute_weights("static", "equal", _returns(["STOCK", "BOND"]))
    assert w["STOCK"] == pytest.approx(0.5) and w["BOND"] == pytest.approx(0.5)


def test_custom_weight_normalises():
    w = compute_weights("static", "custom", _returns(["STOCK", "BOND"]),
                        custom_weights={"STOCK": 70, "BOND": 30})
    assert w["STOCK"] == pytest.approx(0.7) and w["BOND"] == pytest.approx(0.3)


def test_inverse_vol_favours_low_vol_asset():
    w = compute_weights("static", "inverse_vol", _returns(["STOCK", "BOND"]))
    assert w["BOND"] > w["STOCK"], "the lower-vol bond gets more weight"
    assert w.sum() == pytest.approx(1.0)


def test_risk_parity_equals_inverse_vol():
    r = _returns(["STOCK", "BOND"])
    rp = compute_weights("risk_parity", None, r)
    iv = compute_weights("static", "inverse_vol", r)
    assert rp.round(6).equals(iv.round(6))


def test_unknown_algorithm_raises_clearly():
    from app.backtest.allocation_algorithms import AlgorithmUnavailable

    with pytest.raises(AlgorithmUnavailable):
        compute_weights("does_not_exist", None, _returns(["STOCK", "BOND"]))


@pytest.mark.parametrize("algo", ["min_variance", "max_sharpe", "erc", "hrp"])
def test_solver_algorithms_are_valid_long_only_weights(algo):
    w = compute_weights(algo, None, _returns(["STOCK", "BOND", "CASH"]))
    assert (w >= -1e-9).all(), "long-only"
    assert w.sum() == pytest.approx(1.0, abs=1e-4)
    assert list(w.index) == ["STOCK", "BOND", "CASH"]


def test_min_variance_favours_low_vol_asset():
    w = compute_weights("min_variance", None, _returns(["STOCK", "BOND", "CASH"]))
    assert w["CASH"] > w["STOCK"], "the calmest asset carries the most weight"


def test_erc_equalises_risk_contributions():
    r = _returns(["STOCK", "BOND", "CASH"])
    w = compute_weights("erc", None, r).to_numpy()
    cov = r.cov().to_numpy() * 252
    rc = w * (cov @ w)  # per-asset risk contribution
    assert (rc.max() - rc.min()) / rc.mean() < 0.05, "risk contributions ~equal"


def test_vol_target_scales_down_to_cash():
    r = _returns(["STOCK", "BOND"])
    # A tiny target forces heavy de-risking: weights sum below 1 (remainder = cash).
    low = compute_weights("vol_target", None, r, vol_target_annual=0.01)
    assert low.sum() < 0.9
    # A huge target can't lever a long-only book past fully invested.
    high = compute_weights("vol_target", None, r, vol_target_annual=5.0)
    assert high.sum() == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# Rebalance-date selection
# --------------------------------------------------------------------------- #


def test_rebalance_dates_per_period():
    cal = DATES
    s, e = date(2018, 1, 1), date(2019, 12, 31)
    assert len(ae._rebalance_dates(cal, s, e, "none")) == 1
    assert len(ae._rebalance_dates(cal, s, e, "annually")) == 2          # 2018, 2019
    assert 7 <= len(ae._rebalance_dates(cal, s, e, "quarterly")) <= 9    # ~8 quarters
    assert len(ae._rebalance_dates(cal, s, e, "daily")) > 400            # every trading day


# --------------------------------------------------------------------------- #
# End-to-end backtest
# --------------------------------------------------------------------------- #


def _params(**over):
    base = dict(start_date=date(2019, 1, 2), end_date=date(2021, 12, 30),
                initial_capital=10_000_000, initial_capital_currency="KRW", apply_fx=False)
    base.update(over)
    return AllocationBacktestParams(**base)


def test_static_equal_allocation_runs(stub_prices):
    strat = AllocationStrategy(
        name="60/40", algorithm="static", weight_scheme="custom",
        assets=[AssetSlot(ticker="STOCK", market="KR", target_weight_pct=60),
                AssetSlot(ticker="BOND", market="KR", target_weight_pct=40)],
        rebalance_period="annually",
    )
    result = ae.run_allocation_backtest(strat, _params())
    assert result.equity_curve and result.metrics.num_trades > 0
    assert result.equity_curve[-1].portfolio_value > 0


def test_band_rebalancing_adds_trades(stub_prices):
    """A 90/10 book that drifts should rebalance more often with a tight band."""
    def strat(band):
        return AllocationStrategy(
            name="90/10", algorithm="static", weight_scheme="custom",
            assets=[AssetSlot(ticker="STOCK", market="KR", target_weight_pct=90),
                    AssetSlot(ticker="BOND", market="KR", target_weight_pct=10)],
            rebalance_period="none", rebalance_band_pct=band,
        )
    no_band = ae.run_allocation_backtest(strat(0), _params()).metrics.num_trades
    tight_band = ae.run_allocation_backtest(strat(1), _params()).metrics.num_trades
    assert tight_band > no_band, "band rebalancing should trigger extra trades on drift"


def test_risk_parity_allocation_runs(stub_prices):
    strat = AllocationStrategy(
        name="RP", algorithm="risk_parity", weight_scheme=None,
        assets=[AssetSlot(ticker="STOCK", market="KR"), AssetSlot(ticker="BOND", market="KR")],
        rebalance_period="quarterly",
    )
    result = ae.run_allocation_backtest(strat, _params())
    assert result.metrics.num_trades > 0


# --------------------------------------------------------------------------- #
# Momentum timing overlay
# --------------------------------------------------------------------------- #


def test_momentum_off_moves_weight_to_safe_haven(stub_prices):
    # A steadily-FALLING asset should be switched off (absolute momentum < 0) → CASH.
    falling = _frame(_series(-0.001, 0.004, 9))
    monkey_panels = dict(PANELS, DOWN=falling)
    import app.backtest.market_panel as mp
    orig = mp._load_adj

    strat = AllocationStrategy(
        name="momentum", algorithm="static", weight_scheme="equal",
        assets=[AssetSlot(ticker="DOWN", market="KR")],
        rebalance_period="monthly",
        momentum_timing=MomentumTiming(indicator="absolute_momentum", lookback_months=12,
                                       mode="per_asset", safe_haven_ticker="CASH", safe_haven_market="KR"),
    )
    # Build a panel with DOWN + CASH and evaluate the target_fn directly at a late date.
    panel_close = pd.DataFrame({
        "DOWN": pd.Series(falling["adj_close"].to_numpy(), index=pd.to_datetime(DATES)),
        "CASH": pd.Series(PANELS["CASH"]["adj_close"].to_numpy(), index=pd.to_datetime(DATES)),
    })
    panel_close.index = [d.date() for d in panel_close.index]
    target_fn = ae._make_target_fn(strat, panel_close, {})
    weights = target_fn(DATES[400])
    assert weights.get("CASH", 0) == pytest.approx(1.0), "falling asset → 100% safe haven"
    assert weights.get("DOWN", 0) == 0


# --------------------------------------------------------------------------- #
# Portfolio extraction
# --------------------------------------------------------------------------- #


def test_extract_portfolio_integer_shares_sum_to_capital(stub_prices):
    strat = AllocationStrategy(
        name="60/40", algorithm="static", weight_scheme="custom",
        assets=[AssetSlot(ticker="STOCK", market="KR", target_weight_pct=60),
                AssetSlot(ticker="BOND", market="KR", target_weight_pct=40)],
    )
    res = ae.extract_portfolio(strat, DATES[-1], capital=10_000_000)
    assert res.holdings
    for h in res.holdings:
        assert h.target_shares == int(h.target_shares) and h.target_shares > 0
        assert h.target_krw == pytest.approx(h.target_shares * h.price, abs=1.0)
    spent = sum(h.target_krw for h in res.holdings)
    assert spent + res.cash_remainder == pytest.approx(10_000_000, abs=1.0)
    assert res.cash_remainder >= 0
