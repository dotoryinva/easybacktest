"""Turn a Strategy's conditions into per-bar boolean signal series."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schemas import Condition, StrategyDraft
from .indicators import compute_indicators


def _compare(left: pd.Series, operator: str, right: pd.Series) -> pd.Series:
    """Elementwise comparison. NaN on either side yields False, never True."""
    valid = left.notna() & right.notna()

    if operator in (">", "<", ">=", "<=", "=="):
        raw = {
            ">": left > right,
            "<": left < right,
            ">=": left >= right,
            "<=": left <= right,
            # Float equality needs a tolerance to be usable at all.
            "==": np.isclose(left, right, rtol=1e-9, atol=1e-9, equal_nan=False),
        }[operator]
        return pd.Series(np.asarray(raw), index=left.index).fillna(False) & valid

    if operator in ("cross_above", "cross_below"):
        prev_left, prev_right = left.shift(1), right.shift(1)
        prev_valid = prev_left.notna() & prev_right.notna()
        if operator == "cross_above":
            crossed = (prev_left <= prev_right) & (left > right)
        else:
            crossed = (prev_left >= prev_right) & (left < right)
        return crossed.fillna(False) & valid & prev_valid

    raise ValueError(f"unsupported operator {operator!r}")


def evaluate_condition(
    condition: Condition, cache: dict[tuple, pd.Series], index: pd.Index
) -> tuple[pd.Series, pd.Series]:
    """Returns (result, inputs_defined) — both boolean series on `index`."""
    left = cache[condition.left.cache_key()]
    right = cache[condition.right.cache_key()]

    defined = left.notna() & right.notna()
    if condition.operator in ("cross_above", "cross_below"):
        defined = defined & left.shift(1).notna() & right.shift(1).notna()

    return (
        _compare(left, condition.operator, right).reindex(index, fill_value=False),
        defined.reindex(index, fill_value=False),
    )


class Signals:
    """Per-bar entry/exit signals plus the warm-up mask."""

    def __init__(self, buy: pd.Series, sell: pd.Series, ready: pd.Series):
        self.buy = buy
        self.sell = sell
        # False until every indicator the strategy uses has a value.
        self.ready = ready


def evaluate_conditions(
    df: pd.DataFrame,
    strategy: StrategyDraft,
    source_frames: dict[tuple, pd.DataFrame] | None = None,
    primary_market: str = "US",
) -> Signals:
    cache = compute_indicators(df, strategy.indicator_refs(), source_frames, primary_market)
    index = df.index

    buy = pd.Series(True, index=index)
    ready = pd.Series(True, index=index)
    for cond in strategy.buy_conditions:
        result, defined = evaluate_condition(cond, cache, index)
        buy &= result
        ready &= defined

    if strategy.sell_conditions:
        sell = pd.Series(False, index=index)
        for cond in strategy.sell_conditions:
            result, defined = evaluate_condition(cond, cache, index)
            sell |= result
            ready &= defined
    else:
        sell = pd.Series(False, index=index)

    # Warm-up bars can neither enter nor exit on a signal.
    buy &= ready
    sell &= ready
    return Signals(buy=buy, sell=sell, ready=ready)
