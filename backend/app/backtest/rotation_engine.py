"""Rule-based rotation strategies (Change 14, Tier 2 동적배분).

Each preset is a `target_fn(decision_date) -> {ticker: weight}` evaluated from the prior
close and executed at the next open via the shared `portfolio_sim`. Momentum and moving
averages are approximated on daily bars (≈21 trading days per month), which is standard
for these month-end strategies. US-only: mixing markets would need per-market calendars
(see the D+1 note in PROJECT_SPEC).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Callable

import pandas as pd

from ..schemas import BacktestResult, DynamicAllocationRequest
from .engine import default_costs
from .metrics import compute_metrics
from .portfolio_sim import simulate_rebalanced
from .quant_engine import (
    QuantBacktestError,
    _default_price_loader,
    compute_rebalance_dates,
)

logger = logging.getLogger(__name__)

BARS_PER_MONTH = 21
BENCHMARK = "^GSPC"

# Every ticker each preset can touch, so the price panel is loaded once.
_ASSETS = {
    "dual_momentum": ["SPY", "VEU", "BND", "BIL"],
    "vaa": ["SPY", "VEA", "VWO", "AGG", "BIL", "IEF", "LQD"],
    "laa": ["IWD", "GLD", "IEF", "SHY", "SPY"],
    "gtaa": ["SPY", "VEA", "VNQ", "DBC", "TLT"],
}
_FREQUENCY = {
    "dual_momentum": "monthly", "vaa": "monthly", "laa": "quarterly", "gtaa": "monthly",
    "qqq_trend_kr": "monthly",
}
_LABELS = {
    "dual_momentum": "듀얼 모멘텀 (GEM)",
    "vaa": "VAA-4",
    "laa": "LAA",
    "gtaa": "GTAA-5",
    "qqq_trend_kr": "나스닥 추세추종 (QQQ→TIGER)",
}


# --------------------------------------------------------------------------- #
# Series helpers (each `s` is a close series indexed by date, ascending)
# --------------------------------------------------------------------------- #


def _ret(closes: dict[str, pd.Series], t: str, dd: date, bars: int) -> float | None:
    s = closes.get(t)
    if s is None:
        return None
    s = s[s.index <= dd]
    if len(s) <= bars or s.iloc[-1 - bars] <= 0:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - bars] - 1.0)


def _above_sma(closes: dict[str, pd.Series], t: str, dd: date, bars: int) -> bool | None:
    s = closes.get(t)
    if s is None:
        return None
    s = s[s.index <= dd]
    if len(s) < bars:
        return None
    return bool(s.iloc[-1] > s.iloc[-bars:].mean())


def _score_13612w(closes, t, dd) -> float | None:
    r1, r3 = _ret(closes, t, dd, BARS_PER_MONTH), _ret(closes, t, dd, 3 * BARS_PER_MONTH)
    r6, r12 = _ret(closes, t, dd, 6 * BARS_PER_MONTH), _ret(closes, t, dd, 12 * BARS_PER_MONTH)
    if None in (r1, r3, r6, r12):
        return None
    return 12 * r1 + 4 * r3 + 2 * r6 + r12


# --------------------------------------------------------------------------- #
# Presets — each returns target weights (sum ≤ 1; the rest is cash)
# --------------------------------------------------------------------------- #


def _dual_momentum(closes, dd, lookback):
    bars = lookback * BARS_PER_MONTH
    r_spy, r_bil = _ret(closes, "SPY", dd, bars), _ret(closes, "BIL", dd, bars)
    r_veu = _ret(closes, "VEU", dd, bars)
    if None in (r_spy, r_bil, r_veu):
        return {}
    if r_spy > r_bil:  # risk-on: hold the stronger of US / international
        return {"SPY": 1.0} if r_spy >= r_veu else {"VEU": 1.0}
    return {"BND": 1.0}  # risk-off


def _vaa(closes, dd, _lookback):
    offensive = ["SPY", "VEA", "VWO", "AGG"]
    defensive = ["BIL", "IEF", "LQD"]
    off = {t: _score_13612w(closes, t, dd) for t in offensive}
    if any(v is None for v in off.values()):
        return {}
    if all(v > 0 for v in off.values()):  # all offensive healthy → best offensive
        return {max(off, key=off.get): 1.0}
    dfn = {t: _score_13612w(closes, t, dd) for t in defensive}
    dfn = {t: v for t, v in dfn.items() if v is not None}
    if not dfn:
        return {}
    return {max(dfn, key=dfn.get): 1.0}  # crash protection → best defensive


def _laa(closes, dd, _lookback):
    # Three permanent sleeves + one timing sleeve (IWD when the market is above its
    # 12-month SMA, otherwise short-term bonds).
    weights = {"GLD": 0.25, "IEF": 0.25, "SHY": 0.25}
    healthy = _above_sma(closes, "SPY", dd, 12 * BARS_PER_MONTH)
    risky = "IWD" if healthy else "SHY"
    weights[risky] = weights.get(risky, 0.0) + 0.25
    return weights


def _gtaa(closes, dd, _lookback):
    # Each of five sleeves is held only while above its 10-month SMA, else it goes to cash.
    weights: dict[str, float] = {}
    for t in ["SPY", "VEA", "VNQ", "DBC", "TLT"]:
        sig = _above_sma(closes, t, dd, 10 * BARS_PER_MONTH)
        if sig:
            weights[t] = 0.2
    return weights


def _qqq_trend_kr(closes, dd, _lookback):
    # Cross-market: signal off US QQQ's 10-month trend, trade KR-listed ETFs (D+1).
    # Above trend → TIGER 미국나스닥100 (133690, KRW); below → KR 10Y govt bond ETF (148070).
    sig = _above_sma(closes, "QQQ", dd, 10 * BARS_PER_MONTH)
    if sig is None:
        return {}
    return {"133690": 1.0} if sig else {"148070": 1.0}


_PRESETS: dict[str, Callable] = {
    "dual_momentum": _dual_momentum,
    "vaa": _vaa,
    "laa": _laa,
    "gtaa": _gtaa,
    "qqq_trend_kr": _qqq_trend_kr,
}

# Cross-market presets: assets carry an explicit market; base currency is inferred.
_CROSS_ASSETS: dict[str, list[tuple[str, str]]] = {
    "qqq_trend_kr": [("QQQ", "US"), ("133690", "KR"), ("148070", "KR")],
}


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def run_dynamic_allocation(
    req: DynamicAllocationRequest, *, price_loader=None
) -> BacktestResult:
    if req.strategy in _CROSS_ASSETS:
        return _run_cross_market(req)

    market = "US"
    loader = price_loader or _default_price_loader(market, start=req.start_date)
    assets = _ASSETS[req.strategy]
    target_preset = _PRESETS[req.strategy]

    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    for ticker in assets:
        df = loader(ticker)
        if df is None or df.empty:
            raise QuantBacktestError(f"no price data for US/{ticker}")
        s = df.set_index(pd.to_datetime(df["date"]).dt.date)
        closes[ticker] = s["adj_close"]
        opens[ticker] = s["adj_open"]

    panel_close = pd.DataFrame(closes).sort_index()
    panel_open = pd.DataFrame(opens).sort_index()
    calendar = [d for d in panel_close.index if req.start_date <= d <= req.end_date]
    if len(calendar) < 2:
        raise QuantBacktestError("not enough overlapping trading days")

    rebalance_dates = set(
        compute_rebalance_dates(calendar, req.start_date, req.end_date, _FREQUENCY[req.strategy])
    )

    def target_fn(decision_date):
        if decision_date is None:
            return {}
        return target_preset(closes, decision_date, req.lookback_months)

    costs = default_costs(market, None)
    fee = costs.buy_fee
    benchmark = _benchmark(req, loader)

    equity, trades, values = simulate_rebalanced(
        panel_close=panel_close,
        panel_open=panel_open,
        start_date=req.start_date,
        end_date=req.end_date,
        rebalance_dates=rebalance_dates,
        target_fn=target_fn,
        initial_capital=req.initial_capital,
        slippage=req.slippage,
        fee=fee,
        sell_cost=fee + costs.sell_tax,
        benchmark=benchmark,
    )

    metrics = compute_metrics(values, trades, req.initial_capital)
    logger.info(
        "dynamic allocation %s %s..%s: %d trades",
        req.strategy, req.start_date, req.end_date, len(trades),
    )
    return BacktestResult(
        strategy_id=None,
        strategy_name=_LABELS[req.strategy],
        params=_params(req),
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )


def _run_cross_market(req: DynamicAllocationRequest) -> BacktestResult:
    """A rotation whose signal and traded assets span both markets (US signal → KR trade)."""
    from . import market_panel  # noqa: PLC0415

    specs = _CROSS_ASSETS[req.strategy]
    base_currency = market_panel.base_currency_for({m for _, m in specs})
    panel_close, panel_open, rebal_cal = market_panel.build_panels(
        specs, base_currency, req.start_date, req.end_date
    )
    if len(rebal_cal) < 2:
        raise QuantBacktestError("not enough common trading days across the two markets")

    closes = {t: panel_close[t] for t in panel_close.columns}
    target_preset = _PRESETS[req.strategy]

    def target_fn(decision_date):
        if decision_date is None:
            return {}
        return target_preset(closes, decision_date, req.lookback_months)

    rebalance_dates = set(
        compute_rebalance_dates(rebal_cal, req.start_date, req.end_date, _FREQUENCY[req.strategy])
    )
    cost_market = "KR" if base_currency == "KRW" else "US"
    costs = default_costs(cost_market, "KOSPI")
    fee = costs.buy_fee

    # Benchmark: KS200 for a KRW-base strategy, in base currency, normalised.
    bench_ticker = req.benchmark or ("KS200" if base_currency == "KRW" else BENCHMARK)
    bench_market = "KR" if base_currency == "KRW" else "US"
    bench_loader = _default_price_loader(bench_market, start=req.start_date)
    bdf = bench_loader(bench_ticker)
    benchmark = None
    if bdf is not None and not bdf.empty:
        bs = bdf.set_index(pd.to_datetime(bdf["date"]).dt.date)["adj_close"]
        benchmark = bs[(bs.index >= req.start_date) & (bs.index <= req.end_date)]

    equity, trades, values = simulate_rebalanced(
        panel_close=panel_close,
        panel_open=panel_open,
        start_date=req.start_date,
        end_date=req.end_date,
        rebalance_dates=rebalance_dates,
        target_fn=target_fn,
        initial_capital=req.initial_capital,
        slippage=req.slippage,
        fee=fee,
        sell_cost=fee + costs.sell_tax,
        benchmark=benchmark,
    )
    metrics = compute_metrics(values, trades, req.initial_capital)
    logger.info(
        "dynamic (cross-market) %s %s..%s: %d trades",
        req.strategy, req.start_date, req.end_date, len(trades),
    )
    from ..schemas import BacktestParams

    return BacktestResult(
        strategy_id=None,
        strategy_name=_LABELS[req.strategy],
        params=BacktestParams(
            ticker=bench_ticker, market=bench_market, start_date=req.start_date,
            end_date=req.end_date, initial_capital=req.initial_capital, slippage=req.slippage,
        ),
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )


def _benchmark(req: DynamicAllocationRequest, loader):
    ticker = req.benchmark or BENCHMARK
    df = loader(ticker)
    if df is None or df.empty:
        return None
    s = df.set_index(pd.to_datetime(df["date"]).dt.date)["adj_close"]
    return s[(s.index >= req.start_date) & (s.index <= req.end_date)]


def _params(req: DynamicAllocationRequest):
    from ..schemas import BacktestParams

    return BacktestParams(
        ticker=req.benchmark or BENCHMARK,
        market="US",
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        slippage=req.slippage,
    )
