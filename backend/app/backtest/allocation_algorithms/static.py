"""Static allocation weight schemes (Change 15).

Every function takes a T×N returns frame (columns = tickers) and returns a weight Series
(index = tickers, sums to 1, all ≥ 0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _normalise(w: pd.Series) -> pd.Series:
    w = w.clip(lower=0.0)
    total = w.sum()
    if total <= 0:
        return pd.Series(1.0 / len(w), index=w.index)
    return w / total


def equal_weight(returns: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0 / returns.shape[1], index=returns.columns)


def custom_weight(returns: pd.DataFrame, custom: dict[str, float]) -> pd.Series:
    w = pd.Series({t: float(custom.get(t, 0.0)) for t in returns.columns})
    return _normalise(w)


def inverse_vol(returns: pd.DataFrame) -> pd.Series:
    vol = returns.std(ddof=0).replace(0.0, np.nan)
    w = (1.0 / vol).fillna(0.0)
    return _normalise(w)


def inverse_corr(returns: pd.DataFrame) -> pd.Series:
    """Weight ∝ 1 / (sum of correlations with the other assets) — favours diversifiers."""
    if returns.shape[1] < 2:
        return equal_weight(returns)
    corr = returns.corr().to_numpy()
    np.fill_diagonal(corr, 0.0)
    total_corr = corr.sum(axis=1)
    # Shift so the least-correlated asset gets the most weight; guard against ≤0.
    score = 1.0 / np.clip(total_corr - total_corr.min() + 0.1, 1e-6, None)
    return _normalise(pd.Series(score, index=returns.columns))


def market_cap_weight(returns: pd.DataFrame, caps: dict[str, float]) -> pd.Series:
    w = pd.Series({t: float(caps.get(t, 0.0)) for t in returns.columns})
    return _normalise(w) if w.sum() > 0 else equal_weight(returns)


def static_weights(
    weight_scheme: str,
    returns: pd.DataFrame,
    custom: dict[str, float] | None,
    caps: dict[str, float] | None,
) -> pd.Series:
    if weight_scheme == "custom":
        return custom_weight(returns, custom or {})
    if weight_scheme == "inverse_vol":
        return inverse_vol(returns)
    if weight_scheme == "inverse_corr":
        return inverse_corr(returns)
    if weight_scheme == "market_cap":
        return market_cap_weight(returns, caps or {})
    return equal_weight(returns)  # default / "equal"
