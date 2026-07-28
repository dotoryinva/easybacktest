"""Risk parity allocation (Change 15).

First pass: naive risk parity = inverse-volatility weighting (equal risk contribution under
the zero-correlation assumption). w_i ∝ 1/σ_i. The correlation-aware iterative solver (true
ERC) is the separate `erc` algorithm, deferred to the second pass with scipy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def risk_parity_weights(returns: pd.DataFrame) -> pd.Series:
    vol = returns.std(ddof=0).replace(0.0, np.nan)
    inv = (1.0 / vol).fillna(0.0)
    total = inv.sum()
    if total <= 0:
        return pd.Series(1.0 / returns.shape[1], index=returns.columns)
    return inv / total
