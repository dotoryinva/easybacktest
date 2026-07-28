"""Allocation algorithm dispatcher (Change 15 + 16).

`compute_weights` maps an algorithm + weight scheme onto target weights from a returns
window. `static` and `risk_parity` need no solver; `min_variance`, `max_sharpe`,
`vol_target`, `erc` and `hrp` are scipy-backed (Change 16).
"""
from __future__ import annotations

import pandas as pd

from .hrp import hrp_weights
from .risk_parity import risk_parity_weights
from .solvers import (
    erc_weights,
    max_sharpe_weights,
    min_variance_weights,
    vol_target_weights,
)
from .static import static_weights

# Algorithms that derive weights themselves (weight_scheme is ignored / None).
ALGORITHM_CONTROLS_WEIGHTS = {
    "risk_parity", "min_variance", "max_sharpe", "vol_target", "erc", "hrp",
}


class AlgorithmUnavailable(RuntimeError):
    """The requested allocation algorithm could not be computed."""


def compute_weights(
    algorithm: str,
    weight_scheme: str | None,
    returns: pd.DataFrame,
    *,
    custom_weights: dict[str, float] | None = None,
    market_caps: dict[str, float] | None = None,
    vol_target_annual: float | None = None,
) -> pd.Series:
    """Target weights (index = tickers, ≥ 0) from a T×N returns window.

    All algorithms sum to 1 except `vol_target`, which may sum to < 1 (the remainder is
    held as cash by the simulator)."""
    if returns.empty or returns.shape[1] == 0:
        raise AlgorithmUnavailable("no return history to allocate over")

    if algorithm == "static":
        return static_weights(weight_scheme or "equal", returns, custom_weights, market_caps)
    if algorithm == "risk_parity":
        return risk_parity_weights(returns)
    if algorithm == "min_variance":
        return min_variance_weights(returns)
    if algorithm == "max_sharpe":
        return max_sharpe_weights(returns)
    if algorithm == "erc":
        return erc_weights(returns)
    if algorithm == "hrp":
        return hrp_weights(returns)
    if algorithm == "vol_target":
        return vol_target_weights(returns, vol_target_annual or 0.0)
    raise AlgorithmUnavailable(f"unknown algorithm {algorithm!r}")
