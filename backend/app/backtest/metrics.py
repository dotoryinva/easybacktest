"""Performance statistics for a finished simulation."""
from __future__ import annotations

import numpy as np

from ..schemas import BacktestMetrics, Trade

TRADING_DAYS_PER_YEAR = 252


def compute_metrics(
    equity_curve: np.ndarray | list[float],
    trades: list[Trade],
    initial_capital: float,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> BacktestMetrics:
    equity = np.asarray(equity_curve, dtype="float64")

    if equity.size == 0 or initial_capital <= 0:
        return BacktestMetrics(
            total_return_pct=0.0, cagr=0.0, mdd=0.0, sharpe_ratio=0.0,
            sortino_ratio=0.0, win_rate=0.0, num_trades=0, avg_holding_days=0.0,
            avg_win_pct=0.0, avg_loss_pct=0.0, profit_factor=None,
        )

    final = float(equity[-1])
    total_return_pct = final / initial_capital - 1.0

    years = equity.size / trading_days_per_year
    if years > 0 and final > 0:
        cagr = (final / initial_capital) ** (1.0 / years) - 1.0
    else:
        # A wipeout has no meaningful annualised rate; report the total loss.
        cagr = -1.0 if final <= 0 else 0.0

    peaks = np.maximum.accumulate(equity)
    drawdowns = np.divide(
        equity - peaks, peaks, out=np.zeros_like(equity), where=peaks > 0
    )
    mdd = float(drawdowns.min()) if drawdowns.size else 0.0

    if equity.size > 1:
        prev = equity[:-1]
        daily_returns = np.divide(
            np.diff(equity), prev, out=np.zeros(equity.size - 1), where=prev > 0
        )
    else:
        daily_returns = np.array([], dtype="float64")

    ann = np.sqrt(trading_days_per_year)
    std = daily_returns.std(ddof=0) if daily_returns.size else 0.0
    sharpe = float(daily_returns.mean() / std * ann) if std > 0 else 0.0

    downside = daily_returns[daily_returns < 0]
    dstd = downside.std(ddof=0) if downside.size else 0.0
    sortino = float(daily_returns.mean() / dstd * ann) if dstd > 0 else 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    loss_total = sum(t.pnl for t in losses)

    return BacktestMetrics(
        total_return_pct=total_return_pct,
        cagr=cagr,
        mdd=mdd,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        win_rate=(len(wins) / len(trades)) if trades else 0.0,
        num_trades=len(trades),
        avg_holding_days=(
            float(np.mean([(t.sell_date - t.buy_date).days for t in trades])) if trades else 0.0
        ),
        avg_win_pct=float(np.mean([t.pnl_pct for t in wins])) if wins else 0.0,
        avg_loss_pct=float(np.mean([t.pnl_pct for t in losses])) if losses else 0.0,
        profit_factor=(
            abs(sum(t.pnl for t in wins) / loss_total) if losses and loss_total != 0 else None
        ),
    )
