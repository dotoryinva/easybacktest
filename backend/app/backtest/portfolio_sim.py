"""Shared multi-asset rebalancing simulator.

Three engines drive portfolios on the same mechanics — the factor-ranked quant engine,
fixed-weight static allocation, and rule-based rotation — so the loop lives here once and
each engine supplies only a `target_fn`.

Execution model
---------------
* On a rebalance bar the book is liquidated at the **open** and the new target basket is
  bought at the open. Fees/slippage apply on every side. Full turnover keeps lots clean
  (one Trade per holding per period) and is deliberately conservative on costs.
* `target_fn` is handed the **prior trading day** as its decision date, never the
  rebalance bar itself, so a rule can never see the bar it trades on. On the very first
  bar there is no prior day and `None` is passed; a strategy that needs history returns
  an empty basket and simply stays in cash for that period.
* Between rebalances the basket is held and marked to market daily at the close.
* The benchmark line stays flat at the initial capital until the benchmark has data —
  mirroring the portfolio would read as a real comparison when there is none.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from ..schemas import EquityPoint, Trade

TargetFn = Callable[[date | None], dict[str, float]]


def make_trade(entry_date, entry_price, exit_date, exit_price, shares, basis, reason) -> Trade:
    proceeds = shares * exit_price
    pnl = proceeds - basis
    return Trade(
        buy_date=entry_date,
        buy_price=round(entry_price, 6),
        sell_date=exit_date,
        sell_price=round(exit_price, 6),
        shares=shares,
        pnl=round(pnl, 6),
        pnl_pct=round(pnl / basis, 8) if basis else 0.0,
        exit_reason="sell_signal" if reason == "rebalance" else "end_of_period",
    )


def _px(panel: pd.DataFrame, d, ticker: str) -> float:
    if ticker not in panel.columns or d not in panel.index:
        return np.nan
    return panel.at[d, ticker]


def simulate_rebalanced(
    *,
    panel_close: pd.DataFrame,
    panel_open: pd.DataFrame,
    start_date: date,
    end_date: date,
    rebalance_dates: set,
    target_fn: TargetFn,
    initial_capital: float,
    slippage: float,
    fee: float,
    sell_cost: float,
    benchmark: pd.Series | None = None,
    band_pct: float = 0.0,
) -> tuple[list[EquityPoint], list[Trade], list[float]]:
    """Run the rebalance loop; returns (equity points, trades, raw equity values).

    When `band_pct > 0`, an extra rebalance is triggered on the next open whenever any
    holding's weight drifts more than `band_pct` percentage points from its last target.
    """
    all_dates = list(panel_close.index)

    cash = float(initial_capital)
    holdings: dict[str, int] = {}
    lots: dict[str, tuple] = {}
    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    values: list[float] = []
    bh_base: float | None = None
    current_targets: dict[str, float] = {}
    pending_band = False

    for pos, d in enumerate(all_dates):
        if d < start_date or d > end_date:
            continue

        is_rebalance = d in rebalance_dates or pending_band
        pending_band = False
        if is_rebalance:
            # 1. Liquidate at the open.
            for ticker, shares in list(holdings.items()):
                px = _px(panel_open, d, ticker)
                if not np.isfinite(px):
                    px = _px(panel_close, d, ticker)
                if not np.isfinite(px):
                    continue
                fill = px * (1.0 - slippage)
                cash += shares * fill * (1.0 - sell_cost)
                entry_date, entry_price = lots[ticker]
                basis = shares * entry_price * (1.0 + fee)
                trades.append(
                    make_trade(entry_date, entry_price, d, fill, shares, basis, "rebalance")
                )
            holdings.clear()
            lots.clear()

            # 2. Buy the new basket, decided from the prior close.
            decision_date = all_dates[pos - 1] if pos > 0 else None
            targets = target_fn(decision_date) or {}
            current_targets = dict(targets)
            portfolio_value = cash
            for ticker, weight in targets.items():
                px = _px(panel_open, d, ticker)
                if not np.isfinite(px) or px <= 0:
                    continue
                fill = px * (1.0 + slippage)
                budget = min(weight * portfolio_value, cash)
                qty = int(np.floor(budget / (fill * (1.0 + fee))))
                if qty <= 0:
                    continue
                cash -= qty * fill * (1.0 + fee)
                holdings[ticker] = qty
                lots[ticker] = (d, fill)

        # 3. Mark to market at the close.
        position_value = 0.0
        for ticker, shares in holdings.items():
            px = _px(panel_close, d, ticker)
            if np.isfinite(px):
                position_value += shares * px
        total = cash + position_value
        values.append(total)

        # Band rebalance: if any weight has drifted past the band, rebalance next open.
        if band_pct > 0 and current_targets and total > 0 and d != end_date:
            tol = band_pct / 100.0
            drifted = False
            for ticker in set(current_targets) | set(holdings):
                px = _px(panel_close, d, ticker)
                held = holdings.get(ticker, 0)
                cur_w = (held * px / total) if np.isfinite(px) else 0.0
                if abs(cur_w - current_targets.get(ticker, 0.0)) > tol:
                    drifted = True
                    break
            pending_band = drifted

        bh_value = float(initial_capital)
        if benchmark is not None and d in benchmark.index and np.isfinite(benchmark[d]):
            bh_base = bh_base if bh_base is not None else float(benchmark[d])
            bh_value = initial_capital * float(benchmark[d]) / bh_base
        equity.append(
            EquityPoint(
                date=d,
                portfolio_value=round(total, 4),
                cash=round(cash, 4),
                position_value=round(position_value, 4),
                buy_hold_value=round(bh_value, 4),
            )
        )

    # Close whatever is still held at the final close.
    if holdings and equity:
        last = equity[-1].date
        for ticker, shares in list(holdings.items()):
            px = _px(panel_close, last, ticker)
            if not np.isfinite(px):
                continue
            fill = px * (1.0 - slippage)
            cash += shares * fill * (1.0 - sell_cost)
            entry_date, entry_price = lots[ticker]
            basis = shares * entry_price * (1.0 + fee)
            trades.append(
                make_trade(entry_date, entry_price, last, fill, shares, basis, "end_of_period")
            )
        values[-1] = cash
        equity[-1] = equity[-1].model_copy(
            update={"portfolio_value": round(cash, 4), "cash": round(cash, 4),
                    "position_value": 0.0}
        )

    return equity, trades, values
