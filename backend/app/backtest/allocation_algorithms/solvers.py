"""Optimizer-based allocation algorithms (Change 16, scipy second pass).

All are long-only. `min_variance`, `max_sharpe` and `erc` return fully-invested weights
(sum = 1). `vol_target` scales a risk-balanced book down toward a target volatility and
leaves the remainder in cash (sum ≤ 1) — the simulator holds any unspent weight as cash.

Covariance/means are annualised (252 trading days). A tiny ridge is added to the covariance
diagonal so the pairwise-estimated matrix (assets can trade on different calendars) stays
positive-definite for the solver.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

TRADING_DAYS = 252


def _cov_annual(returns: pd.DataFrame) -> np.ndarray:
    cov = returns.cov().fillna(0.0).to_numpy() * TRADING_DAYS
    n = cov.shape[0]
    # Ridge for numerical stability / positive-definiteness.
    cov += np.eye(n) * 1e-8
    return cov


def _mean_annual(returns: pd.DataFrame) -> np.ndarray:
    return returns.mean().fillna(0.0).to_numpy() * TRADING_DAYS


def _finalise(weights: np.ndarray, columns, *, renormalise: bool) -> pd.Series:
    w = np.clip(np.nan_to_num(weights, nan=0.0), 0.0, None)
    total = w.sum()
    if renormalise:
        w = np.full(len(w), 1.0 / len(w)) if total <= 0 else w / total
    elif total > 1.0:  # vol_target: never lever above fully invested
        w = w / total
    return pd.Series(w, index=columns)


def _equal(returns: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0 / returns.shape[1], index=returns.columns)


def min_variance_weights(returns: pd.DataFrame) -> pd.Series:
    """Long-only global minimum-variance portfolio: min wᵀΣw, Σw = 1, w ≥ 0."""
    if returns.shape[1] == 1:
        return _equal(returns)
    cov = _cov_annual(returns)
    n = cov.shape[0]
    w0 = np.full(n, 1.0 / n)
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    return _finalise(res.x if res.success else w0, returns.columns, renormalise=True)


def max_sharpe_weights(returns: pd.DataFrame, risk_free: float = 0.0) -> pd.Series:
    """Long-only tangency portfolio: max (wᵀμ − rf) / √(wᵀΣw), Σw = 1, w ≥ 0.

    When no asset has a positive excess return the objective has no meaningful maximum, so
    we fall back to minimum variance (the sensible long-only choice)."""
    if returns.shape[1] == 1:
        return _equal(returns)
    mu = _mean_annual(returns)
    if np.all(mu - risk_free <= 0):
        return min_variance_weights(returns)
    cov = _cov_annual(returns)
    n = len(mu)
    w0 = np.full(n, 1.0 / n)

    def neg_sharpe(w: np.ndarray) -> float:
        vol = np.sqrt(max(float(w @ cov @ w), 1e-12))
        return -float(w @ mu - risk_free) / vol

    res = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    return _finalise(res.x if res.success else w0, returns.columns, renormalise=True)


def erc_weights(returns: pd.DataFrame) -> pd.Series:
    """Equal Risk Contribution (true risk parity): each asset contributes equal risk.

    Minimises the dispersion of risk contributions RCᵢ = wᵢ·(Σw)ᵢ around their mean."""
    if returns.shape[1] == 1:
        return _equal(returns)
    cov = _cov_annual(returns)
    n = cov.shape[0]
    w0 = np.full(n, 1.0 / n)

    def dispersion(w: np.ndarray) -> float:
        mrc = cov @ w  # marginal risk contribution
        rc = w * mrc  # risk contribution
        return float(np.sum((rc - rc.mean()) ** 2))

    res = minimize(
        dispersion,
        w0,
        method="SLSQP",
        bounds=[(1e-4, 1.0)] * n,  # keep every asset in; RC is undefined at w=0
        constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},),
        options={"maxiter": 800, "ftol": 1e-14},
    )
    return _finalise(res.x if res.success else w0, returns.columns, renormalise=True)


def vol_target_weights(returns: pd.DataFrame, target_annual: float) -> pd.Series:
    """Scale a risk-balanced (inverse-vol) book to hit a target annual volatility.

    Long-only, so exposure is capped at 1 (no leverage); when the balanced book is already
    calmer than the target the whole thing is held. Any scaled-down remainder is cash."""
    vol = returns.std(ddof=0).replace(0.0, np.nan)
    inv = (1.0 / vol).fillna(0.0)
    base = _equal(returns) if inv.sum() <= 0 else inv / inv.sum()

    cov = _cov_annual(returns)
    port_vol = float(np.sqrt(max(base.to_numpy() @ cov @ base.to_numpy(), 1e-12)))
    if not target_annual or target_annual <= 0 or port_vol <= 0:
        scale = 1.0
    else:
        scale = min(1.0, target_annual / port_vol)
    return _finalise(base.to_numpy() * scale, returns.columns, renormalise=False)
