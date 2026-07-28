"""Fixed-weight asset-allocation backtest (Change 14, Tier 2 정적배분).

A thin strategy over the shared `portfolio_sim`: the target basket is constant (the
normalised holding weights) every rebalance, so the `target_fn` ignores its decision date.
"""
from __future__ import annotations

import logging

import pandas as pd

from collections import defaultdict

import numpy as np

from ..schemas import (
    AllocationBacktestParams,
    AllocationStrategy,
    BacktestParams,
    BacktestResult,
    ExtractPortfolioResponse,
    PortfolioHolding,
    StaticAllocationRequest,
)
from ..services import data_service
from .engine import default_costs
from .metrics import compute_metrics
from .portfolio_sim import simulate_rebalanced
from .quant_engine import (
    QuantBacktestError,
    _default_price_loader,
    _market_caps,
    compute_rebalance_dates,
)

logger = logging.getLogger(__name__)

_DEFAULT_BENCHMARK = {"KR": "KS200", "US": "^GSPC"}
BARS_PER_MONTH = 21


def run_static_allocation(req: StaticAllocationRequest) -> BacktestResult:
    total_w = sum(h.weight for h in req.holdings)
    if total_w <= 0:
        raise QuantBacktestError("holding weights must sum to a positive number")
    targets = {h.ticker: h.weight / total_w for h in req.holdings}

    specs = [(h.ticker, h.market or req.market) for h in req.holdings]
    markets = {m for _, m in specs}
    if len(markets) > 1:
        return _run_cross_market(req, specs, targets)
    return _run_single_market(req, req.market, targets)


def _run_single_market(req, market, targets) -> BacktestResult:
    loader = _default_price_loader(market, start=req.start_date)

    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    for ticker in targets:
        df = loader(ticker)
        if df is None or df.empty:
            raise QuantBacktestError(f"no price data for {market}/{ticker}")
        s = df.set_index(pd.to_datetime(df["date"]).dt.date)
        closes[ticker] = s["adj_close"]
        opens[ticker] = s["adj_open"]

    panel_close = pd.DataFrame(closes).sort_index()
    panel_open = pd.DataFrame(opens).sort_index()
    calendar = [d for d in panel_close.index if req.start_date <= d <= req.end_date]
    if len(calendar) < 2:
        raise QuantBacktestError("not enough overlapping trading days for these holdings")

    rebalance_dates = set(
        compute_rebalance_dates(calendar, req.start_date, req.end_date, req.rebalance)
    )
    rebalance_dates.add(calendar[0])
    costs = default_costs(market, "KOSPI")

    return _finish(req, market, targets, panel_close, panel_open, rebalance_dates,
                   costs, _benchmark(req, market, loader))


def _run_cross_market(req, specs, targets) -> BacktestResult:
    """Mixed US+KR holdings: base-currency panels + intersection rebalance calendar."""
    from . import market_panel  # noqa: PLC0415 - avoid an import cycle at module load

    markets = {m for _, m in specs}
    base_currency = market_panel.base_currency_for(markets)
    panel_close, panel_open, rebal_cal = market_panel.build_panels(
        specs, base_currency, req.start_date, req.end_date
    )
    if len(rebal_cal) < 2:
        raise QuantBacktestError("not enough common trading days across the two markets")
    rebalance_dates = set(
        compute_rebalance_dates(rebal_cal, req.start_date, req.end_date, req.rebalance)
    )
    rebalance_dates.add(rebal_cal[0])

    # Costs follow the base currency's home market (a small approximation for the other leg).
    cost_market = "KR" if base_currency == "KRW" else "US"
    costs = default_costs(cost_market, "KOSPI")
    benchmark = _cross_benchmark(req, base_currency, panel_close.index)
    return _finish(req, cost_market, targets, panel_close, panel_open, rebalance_dates,
                   costs, benchmark)


def _finish(req, market, targets, panel_close, panel_open, rebalance_dates, costs, benchmark):
    fee = costs.buy_fee
    equity, trades, values = simulate_rebalanced(
        panel_close=panel_close,
        panel_open=panel_open,
        start_date=req.start_date,
        end_date=req.end_date,
        rebalance_dates=rebalance_dates,
        target_fn=lambda _decision_date: targets,
        initial_capital=req.initial_capital,
        slippage=req.slippage,
        fee=fee,
        sell_cost=fee + costs.sell_tax,
        benchmark=benchmark,
    )
    metrics = compute_metrics(values, trades, req.initial_capital)
    logger.info(
        "static allocation (%s) %s..%s: %d holdings, %d trades",
        market, req.start_date, req.end_date, len(targets), len(trades),
    )
    return BacktestResult(
        strategy_id=None,
        strategy_name=req.name,
        params=_params(req, market),
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )


def _cross_benchmark(req, base_currency, index):
    """Default benchmark for a mixed portfolio: KS200 (KRW base) or ^GSPC (USD base)."""
    ticker = req.benchmark or ("KS200" if base_currency == "KRW" else "^GSPC")
    market = "KR" if base_currency == "KRW" else "US"
    loader = _default_price_loader(market, start=req.start_date)
    df = loader(ticker)
    if df is None or df.empty:
        return None
    s = df.set_index(pd.to_datetime(df["date"]).dt.date)["adj_close"]
    return s[(s.index >= req.start_date) & (s.index <= req.end_date)]


def _benchmark(req: StaticAllocationRequest, market: str, loader):
    ticker = req.benchmark or _DEFAULT_BENCHMARK.get(market)
    if not ticker:
        return None
    df = loader(ticker)
    if df is None or df.empty:
        return None
    s = df.set_index(pd.to_datetime(df["date"]).dt.date)["adj_close"]
    return s[(s.index >= req.start_date) & (s.index <= req.end_date)]


def _params(req: StaticAllocationRequest, market: str):
    from ..schemas import BacktestParams

    return BacktestParams(
        ticker=req.benchmark or _DEFAULT_BENCHMARK.get(market, "PORTFOLIO"),
        market=market,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        slippage=req.slippage,
    )


# =========================================================================== #
# Change 15 — unified allocation engine (algorithm + band + market timing + FX)
# =========================================================================== #

from . import market_panel  # noqa: E402
from .allocation_algorithms import compute_weights  # noqa: E402


def _asset_tickers(strategy: AllocationStrategy) -> list[str]:
    return [a.ticker for a in strategy.assets]


def _all_specs(strategy: AllocationStrategy) -> list[tuple[str, str]]:
    """Every (ticker, market) the strategy touches: assets + safe-haven + canary."""
    specs = [(a.ticker, a.market) for a in strategy.assets]
    t = strategy.momentum_timing
    if t:
        specs.append((t.safe_haven_ticker, t.safe_haven_market))
        if t.mode == "canary" and t.canary_ticker:
            specs.append((t.canary_ticker, t.canary_market))
    seen, out = set(), []
    for s in specs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _period_key(d, period: str):
    if period == "weekly":
        iso = d.isocalendar()
        return (iso[0], iso[1])
    if period == "monthly":
        return (d.year, d.month)
    if period == "quarterly":
        return (d.year, (d.month - 1) // 3)
    if period == "semi_annually":
        return (d.year, (d.month - 1) // 6)
    return (d.year,)  # annually


def _rebalance_dates(calendar: list, start, end, period: str) -> set:
    dates = [d for d in calendar if start <= d <= end]
    if not dates:
        return set()
    if period == "none":
        return {dates[0]}
    if period == "daily":
        return set(dates)
    out, seen = {dates[0]}, set()
    for d in dates:
        key = _period_key(d, period)
        if key not in seen:
            seen.add(key)
            out.add(d)
    return out


def _momentum_signal(series, indicator: str, lookback_months: int, decision_date, threshold: float):
    """True/False for on/off, or None when there isn't enough history yet (→ treat on)."""
    s = series[series.index <= decision_date].dropna()
    bars = lookback_months * BARS_PER_MONTH
    if indicator == "sma_cross":
        if len(s) < bars:
            return None
        return bool(s.iloc[-1] > s.iloc[-bars:].mean())
    if indicator == "13612w":
        def r(k):
            return (s.iloc[-1] / s.iloc[-1 - k] - 1.0) if len(s) > k and s.iloc[-1 - k] > 0 else None
        parts = [r(21), r(63), r(126), r(252)]
        if any(p is None for p in parts):
            return None
        score = 12 * parts[0] + 4 * parts[1] + 2 * parts[2] + parts[3]
        return bool(score > threshold)
    # absolute_momentum (and sortino, approximated by it in the first pass)
    if len(s) <= bars or s.iloc[-1 - bars] <= 0:
        return None
    return bool(s.iloc[-1] / s.iloc[-1 - bars] - 1.0 > threshold)


def _make_target_fn(strategy: AllocationStrategy, panel_close, caps: dict[str, float]):
    """Return a `decision_date -> {ticker: weight}` closure with timing state."""
    asset_tickers = _asset_tickers(strategy)
    custom = {
        a.ticker: float(a.target_weight_pct or 0.0)
        for a in strategy.assets
        if a.target_weight_pct is not None
    }
    timing = strategy.momentum_timing
    reentry = strategy.reentry_timing
    # Per-asset timing state (across rebalances, evaluated in chronological order).
    streak: dict[str, int] = defaultdict(int)
    off_count: dict[str, int] = defaultdict(int)
    is_off: dict[str, bool] = defaultdict(bool)

    def base_weights(decision_date) -> "pd.Series":
        window = panel_close.loc[panel_close.index <= decision_date, asset_tickers]
        returns = window.tail(strategy.lookback_days_for_estimation + 1).pct_change().dropna(how="all")
        if returns.empty:
            return pd.Series(1.0 / len(asset_tickers), index=asset_tickers)
        return compute_weights(
            strategy.algorithm, strategy.weight_scheme, returns,
            custom_weights=custom, market_caps=caps,
            vol_target_annual=strategy.vol_target_annual,
        )

    def decide_on(ticker: str, positive: bool) -> bool:
        if positive:
            streak[ticker] += 1
        else:
            streak[ticker] = 0
        if not positive:
            off_count[ticker] += 1
            is_off[ticker] = True
            return False
        if not is_off[ticker]:
            return True
        # Was off, signal now positive — apply the reentry rule.
        rule = reentry.rule if reentry else "immediate"
        n = reentry.n if reentry else 1
        forced = bool(reentry and reentry.max_off_months and off_count[ticker] >= reentry.max_off_months)
        on = forced or rule == "immediate" or streak[ticker] >= n
        if on:
            is_off[ticker] = False
            off_count[ticker] = 0
        return on

    def target_fn(decision_date) -> dict[str, float]:
        if decision_date is None:
            return {}
        weights = base_weights(decision_date)
        if timing is None:
            return {t: float(w) for t, w in weights.items() if w > 0}

        sh = timing.safe_haven_ticker
        if timing.mode == "canary" and timing.canary_ticker:
            sig = _momentum_signal(
                panel_close[timing.canary_ticker], timing.indicator,
                timing.lookback_months, decision_date, timing.threshold,
            )
            risk_on = sig is None or sig
            return {t: float(w) for t, w in weights.items() if w > 0} if risk_on else {sh: 1.0}

        out: dict[str, float] = {}
        freed = 0.0
        for t, w in weights.items():
            if w <= 0:
                continue
            sig = _momentum_signal(
                panel_close[t], timing.indicator, timing.lookback_months,
                decision_date, timing.threshold,
            )
            positive = True if sig is None else sig
            if decide_on(t, positive):
                out[t] = out.get(t, 0.0) + float(w)
            else:
                freed += float(w)
        if freed > 0:
            out[sh] = out.get(sh, 0.0) + freed
        return out

    return target_fn


def _equal_weight_benchmark(panel_close, asset_tickers, start, end, initial_capital):
    sub = panel_close.loc[(panel_close.index >= start) & (panel_close.index <= end), asset_tickers]
    sub = sub.dropna()
    if sub.empty:
        return None
    per_asset = initial_capital / len(asset_tickers)
    shares = per_asset / sub.iloc[0]
    return (sub * shares).sum(axis=1)


def run_allocation_backtest(
    strategy: AllocationStrategy, params: AllocationBacktestParams
) -> BacktestResult:
    specs = _all_specs(strategy)
    markets = {m for _, m in specs}
    base_currency = params.initial_capital_currency
    base_market = "KR" if base_currency == "KRW" else "US"

    # Pull enough history before the start for the estimation lookback + momentum window.
    from datetime import timedelta

    buffer_days = int(strategy.lookback_days_for_estimation * 1.6) + 400
    fetch_start = params.start_date - timedelta(days=buffer_days)
    panel_close, panel_open, rebal_cal = market_panel.build_panels(
        specs, base_currency, fetch_start, params.end_date, apply_fx=strategy.apply_fx
    )
    if len([d for d in panel_close.index if params.start_date <= d <= params.end_date]) < 2:
        raise QuantBacktestError("not enough overlapping trading days for these assets")

    caps = _market_caps(base_market) if strategy.weight_scheme == "market_cap" else {}
    rebalance_dates = _rebalance_dates(
        rebal_cal, params.start_date, params.end_date, strategy.rebalance_period
    )
    rebalance_dates.add(min(d for d in rebal_cal if d >= params.start_date))  # establish day one

    target_fn = _make_target_fn(strategy, panel_close, caps)
    costs = default_costs(base_market, "KOSPI")
    fee = costs.buy_fee
    benchmark = _equal_weight_benchmark(
        panel_close, _asset_tickers(strategy), params.start_date, params.end_date,
        params.initial_capital,
    )

    equity, trades, values = simulate_rebalanced(
        panel_close=panel_close,
        panel_open=panel_open,
        start_date=params.start_date,
        end_date=params.end_date,
        rebalance_dates=rebalance_dates,
        target_fn=target_fn,
        initial_capital=params.initial_capital,
        slippage=params.slippage,
        fee=fee,
        sell_cost=fee + costs.sell_tax,
        benchmark=benchmark,
        band_pct=strategy.rebalance_band_pct,
    )
    metrics = compute_metrics(values, trades, params.initial_capital)
    logger.info(
        "allocation backtest %s (%s) %s..%s: %d assets, %d trades",
        strategy.algorithm, strategy.rebalance_period, params.start_date, params.end_date,
        len(strategy.assets), len(trades),
    )
    return BacktestResult(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        params=BacktestParams(
            ticker="ALLOCATION", market=base_market, start_date=params.start_date,
            end_date=params.end_date, initial_capital=params.initial_capital,
            slippage=params.slippage,
        ),
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )


def extract_portfolio(strategy: AllocationStrategy, as_of, capital: float) -> ExtractPortfolioResponse:
    """Today's actionable target book: integer share counts + KRW remainder."""
    from datetime import date as _date, timedelta

    as_of = as_of or _date.today()
    base_currency = "KRW"  # extraction is always shown in KRW for a Korean user
    specs = _all_specs(strategy)
    buffer_days = int(strategy.lookback_days_for_estimation * 1.6) + 400
    panel_close, _open, _cal = market_panel.build_panels(
        specs, base_currency, as_of - timedelta(days=buffer_days), as_of,
        apply_fx=strategy.apply_fx,
    )
    dates = [d for d in panel_close.index if d <= as_of]
    if not dates:
        raise QuantBacktestError("no price data available as of the requested date")
    decision_date = dates[-1]

    caps = _market_caps("KR") if strategy.weight_scheme == "market_cap" else {}
    target_fn = _make_target_fn(strategy, panel_close, caps)
    weights = target_fn(decision_date)

    market_of = {a.ticker: a.market for a in strategy.assets}
    if strategy.momentum_timing:
        market_of.setdefault(strategy.momentum_timing.safe_haven_ticker, strategy.momentum_timing.safe_haven_market)

    holdings: list[PortfolioHolding] = []
    spent = 0.0
    for ticker, weight in sorted(weights.items(), key=lambda kv: -kv[1]):
        if weight <= 0 or ticker not in panel_close.columns:
            continue
        price = round(float(panel_close.at[decision_date, ticker]), 2)
        if not np.isfinite(price) or price <= 0:
            continue
        shares = int(np.floor(weight * capital / price))
        if shares <= 0:
            continue
        actual = round(shares * price, 2)  # consistent with the displayed price
        spent += actual
        mkt = market_of.get(ticker, "KR")
        try:
            meta = data_service.get_ticker(ticker, mkt)
            name = meta.name_ko or meta.name_en
        except data_service.TickerNotFound:
            name = ticker
        holdings.append(PortfolioHolding(
            ticker=ticker, name=name, market=mkt, weight=round(weight, 6),
            price=price, target_shares=shares, target_krw=actual,
        ))

    return ExtractPortfolioResponse(
        as_of_date=decision_date,
        holdings=holdings,
        cash_remainder=round(capital - spent, 2),
        total_krw=round(capital, 2),
    )
