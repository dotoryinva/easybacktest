"""Deterministic single-ticker daily-bar backtest engine.

Execution model
---------------
* Signals are read from the **close** of day D; the resulting order fills at the
  **open** of day D+1. Nothing ever fills on the bar that produced its own signal, so
  there is no lookahead.
* Stop-loss / take-profit triggers are detected from day D's intraday low/high against
  the actual entry fill price, and — like every other order — fill at the open of D+1.
  A same-day fill at the intraday extreme would be lookahead.
* `max_holding_days` counts **trading bars** held, which is what a daily-bar engine can
  actually measure.
* All arithmetic runs on split/dividend-adjusted prices. Raw OHLC is scaled by
  `adj_close / close` so the whole bar sits on one price scale.
* One position at a time (Phase 1 is single-ticker).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..schemas import (
    BacktestMetrics,
    BacktestParams,
    BacktestResult,
    EquityPoint,
    Strategy,
    StrategyDraft,
    Trade,
)
from ..services import data_service
from .evaluator import evaluate_conditions
from .indicators import longest_warmup
from .metrics import compute_metrics

logger = logging.getLogger(__name__)


class BacktestError(RuntimeError):
    """The backtest cannot be run as specified."""


@dataclass(frozen=True)
class CostModel:
    buy_fee: float
    sell_fee: float
    sell_tax: float

    def label(self) -> str:
        return (
            f"buy {self.buy_fee:.5%}, sell {self.sell_fee:.5%}, sell tax {self.sell_tax:.5%}"
        )


# KR: brokerage 0.015% each way; sell tax 0.18% KOSPI / 0.23% KOSDAQ.
# US: 0.025% each way; SEC fee 0.00278% on sells.
_KR_KOSPI = CostModel(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0018)
_KR_KOSDAQ = CostModel(buy_fee=0.00015, sell_fee=0.00015, sell_tax=0.0023)
_US = CostModel(buy_fee=0.00025, sell_fee=0.00025, sell_tax=0.0000278)


def default_costs(market: str, board: str | None) -> CostModel:
    if market == "US":
        return _US
    return _KR_KOSPI if (board or "").upper() == "KOSPI" else _KR_KOSDAQ


def resolve_costs(params: BacktestParams) -> CostModel:
    """Market defaults, with explicit overrides from the request applied on top."""
    base = default_costs(params.market, data_service.board_of(params.ticker, params.market))
    return CostModel(
        buy_fee=params.fee_rate if params.fee_rate is not None else base.buy_fee,
        sell_fee=params.fee_rate if params.fee_rate is not None else base.sell_fee,
        sell_tax=params.sell_tax_rate if params.sell_tax_rate is not None else base.sell_tax,
    )


def _warmup_buffer_days(strategy: StrategyDraft) -> int:
    warmup_bars = longest_warmup(strategy.indicator_refs())
    # ~252 trading days per 365 calendar days, with slack for holidays.
    return int(warmup_bars * 1.6) + 15 if warmup_bars else 0


def load_frame(strategy: StrategyDraft, params: BacktestParams) -> pd.DataFrame:
    """Load bars covering [start, end] plus enough history to warm the indicators up."""
    fetch_start = params.start_date - timedelta(days=_warmup_buffer_days(strategy))

    df = data_service.get_ohlcv(params.ticker, params.market, fetch_start, params.end_date)
    if df.empty:
        raise BacktestError(f"no cached bars for {params.market}/{params.ticker}")

    factor = (df["adj_close"] / df["close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    for col in ("open", "high", "low"):
        df[f"adj_{col}"] = df[col] * factor
    return df.reset_index(drop=True)


def load_source_frames(
    strategy: StrategyDraft, params: BacktestParams
) -> dict[tuple, pd.DataFrame]:
    """Native bars for every *other* asset a condition references (cross-asset signals)."""
    fetch_start = params.start_date - timedelta(days=_warmup_buffer_days(strategy) + 10)
    frames: dict[tuple, pd.DataFrame] = {}
    for ref in strategy.indicator_refs():
        if not ref.ticker:
            continue
        src_market = ref.market or params.market
        if ref.ticker.upper() == params.ticker.upper() and src_market == params.market:
            continue  # references the traded asset itself — resolved on the primary frame
        key = (ref.ticker, src_market)
        if key in frames:
            continue
        data_service.ensure_cached(ref.ticker, src_market, start=fetch_start)
        sdf = data_service.get_ohlcv(ref.ticker, src_market, fetch_start, params.end_date)
        if sdf.empty:
            raise BacktestError(f"no bars for signal asset {src_market}/{ref.ticker}")
        frames[key] = sdf.reset_index(drop=True)
    return frames


def _shares_for(
    sizing: str,
    size_value: float | None,
    cash: float,
    portfolio_value: float,
    fill_price: float,
    buy_fee: float,
) -> int:
    """Whole shares affordable under the sizing rule, fees included."""
    if fill_price <= 0:
        return 0
    if sizing == "all_in":
        budget = cash
    elif sizing == "fixed_amount":
        budget = min(size_value or 0.0, cash)
    else:  # percent_of_capital
        budget = min((size_value or 0.0) * portfolio_value, cash)
    per_share = fill_price * (1.0 + buy_fee)
    return max(0, int(math.floor(budget / per_share))) if per_share > 0 else 0


def simulate(
    df: pd.DataFrame,
    signals,
    strategy: StrategyDraft,
    params: BacktestParams,
    costs: CostModel,
) -> tuple[list[EquityPoint], list[Trade], BacktestMetrics]:
    sim_mask = (df["date"].dt.date >= params.start_date) & signals.ready
    sim_idx = np.flatnonzero(sim_mask.to_numpy())
    if sim_idx.size == 0:
        raise BacktestError(
            "no tradable bars: the indicator warm-up consumes the whole requested "
            "period. Widen the date range or shorten the indicator periods."
        )
    first, last = int(sim_idx[0]), int(sim_idx[-1])

    dates = df["date"].dt.date.to_numpy()
    op = df["adj_open"].to_numpy(dtype="float64")
    hi = df["adj_high"].to_numpy(dtype="float64")
    lo = df["adj_low"].to_numpy(dtype="float64")
    cl = df["adj_close"].to_numpy(dtype="float64")
    buy_sig = signals.buy.to_numpy(dtype=bool)
    sell_sig = signals.sell.to_numpy(dtype=bool)

    slip = params.slippage
    cash = float(params.initial_capital)
    shares = 0
    entry_price = 0.0
    entry_cost_basis = 0.0
    entry_date: date | None = None
    entry_bar = -1
    last_exit_bar = -(10**9)

    pending: str | None = None  # "buy" | "sell"
    pending_reason: str = ""

    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    equity_values: list[float] = []

    # Buy-and-hold baseline: same entry bar, same slippage and buy-side fee.
    bh_fill = op[first] * (1.0 + slip)
    bh_shares = _shares_for("all_in", None, params.initial_capital, params.initial_capital,
                            bh_fill, costs.buy_fee)
    bh_cash = params.initial_capital - bh_shares * bh_fill * (1.0 + costs.buy_fee)

    for i in range(first, last + 1):
        # 1. Fill yesterday's order at today's open.
        if pending == "sell" and shares > 0:
            fill = op[i] * (1.0 - slip)
            proceeds = shares * fill * (1.0 - costs.sell_fee - costs.sell_tax)
            pnl = proceeds - entry_cost_basis
            trades.append(
                Trade(
                    buy_date=entry_date,
                    buy_price=round(entry_price, 6),
                    sell_date=dates[i],
                    sell_price=round(fill, 6),
                    shares=shares,
                    pnl=round(pnl, 6),
                    pnl_pct=round(pnl / entry_cost_basis, 8) if entry_cost_basis else 0.0,
                    exit_reason=pending_reason,
                )
            )
            cash += proceeds
            shares = 0
            entry_price = entry_cost_basis = 0.0
            entry_date = None
            entry_bar = -1
            last_exit_bar = i

        elif pending == "buy" and shares == 0:
            cooling = (i - last_exit_bar) <= strategy.cooldown_days_after_exit
            if not cooling:
                fill = op[i] * (1.0 + slip)
                portfolio_value = cash + shares * cl[i]
                qty = _shares_for(
                    strategy.position_sizing, strategy.position_size_value,
                    cash, portfolio_value, fill, costs.buy_fee,
                )
                if qty > 0:
                    entry_cost_basis = qty * fill * (1.0 + costs.buy_fee)
                    cash -= entry_cost_basis
                    shares = qty
                    entry_price = fill
                    entry_date = dates[i]
                    entry_bar = i

        pending, pending_reason = None, ""

        # 2. Mark to market at today's close.
        position_value = shares * cl[i]
        total = cash + position_value
        equity_values.append(total)
        equity.append(
            EquityPoint(
                date=dates[i],
                portfolio_value=round(total, 4),
                cash=round(cash, 4),
                position_value=round(position_value, 4),
                buy_hold_value=round(bh_cash + bh_shares * cl[i], 4),
            )
        )

        if i == last:
            break

        # 3. Decide tomorrow's order from today's close.
        if shares > 0:
            if (
                strategy.stop_loss_pct is not None
                and lo[i] <= entry_price * (1.0 - strategy.stop_loss_pct)
            ):
                pending, pending_reason = "sell", "stop_loss"
            elif (
                strategy.take_profit_pct is not None
                and hi[i] >= entry_price * (1.0 + strategy.take_profit_pct)
            ):
                pending, pending_reason = "sell", "take_profit"
            elif sell_sig[i]:
                pending, pending_reason = "sell", "sell_signal"
            elif (
                strategy.max_holding_days is not None
                and (i - entry_bar) >= strategy.max_holding_days
            ):
                pending, pending_reason = "sell", "max_holding_days"
        elif buy_sig[i]:
            # An exit filled at this bar's open; re-entering off the same bar's close
            # is the "same day" case the strategy can opt into.
            if i != last_exit_bar or strategy.allow_reentry_same_day:
                pending, pending_reason = "buy", ""

    # Close any open position at the final close.
    if shares > 0:
        fill = cl[last] * (1.0 - slip)
        proceeds = shares * fill * (1.0 - costs.sell_fee - costs.sell_tax)
        pnl = proceeds - entry_cost_basis
        trades.append(
            Trade(
                buy_date=entry_date,
                buy_price=round(entry_price, 6),
                sell_date=dates[last],
                sell_price=round(fill, 6),
                shares=shares,
                pnl=round(pnl, 6),
                pnl_pct=round(pnl / entry_cost_basis, 8) if entry_cost_basis else 0.0,
                exit_reason="end_of_period",
            )
        )
        cash += proceeds
        shares = 0
        equity_values[-1] = cash
        equity[-1] = equity[-1].model_copy(
            update={
                "portfolio_value": round(cash, 4),
                "cash": round(cash, 4),
                "position_value": 0.0,
            }
        )

    metrics = compute_metrics(equity_values, trades, params.initial_capital)
    return equity, trades, metrics


def run_backtest(strategy: Strategy | StrategyDraft, params: BacktestParams) -> BacktestResult:
    df = load_frame(strategy, params)
    source_frames = load_source_frames(strategy, params)
    signals = evaluate_conditions(df, strategy, source_frames, params.market)
    costs = resolve_costs(params)

    logger.info(
        "backtest %s/%s %s..%s (%s)",
        params.market, params.ticker, params.start_date, params.end_date, costs.label(),
    )

    equity, trades, metrics = simulate(df, signals, strategy, params, costs)
    return BacktestResult(
        strategy_id=getattr(strategy, "id", None),
        strategy_name=strategy.name,
        params=params,
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )
