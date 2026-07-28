"""Factor-ranked, periodically-rebalanced portfolio backtest (Change 13.6).

Execution model
---------------
* Rebalance dates are the first trading day of each period (monthly / quarterly / …).
* At a rebalance, the ranking is computed from data **as of the prior trading day's
  close** — never the rebalance bar itself — and orders fill at that bar's **open**. So
  there is no lookahead, the same guarantee the single-stock engine gives.
* Rebalancing is full-turnover: the book is liquidated at the open and the new target
  basket bought at the open. Fees/slippage apply on every side. This keeps lots clean
  (one Trade per holding per period) and is deliberately conservative on costs.
* Between rebalances the basket is held and marked to market daily at the close.
* Fundamentals have a publication lag; the fundamentals loader is asked for a snapshot
  *as of the decision date*, so a value is only used once it would have been public.

The heavy data access (universe resolution, price panels, fundamentals) is injectable so
the engine can be tested hermetically with synthetic data.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from ..schemas import (
    BacktestMetrics,
    BacktestResult,
    EquityPoint,
    FilterCondition,
    QuantBacktestParams,
    QuantPortfolioStrategy,
    Trade,
    UniverseConfig,
)
from ..services import data_service
from .engine import default_costs
from .metrics import compute_metrics

logger = logging.getLogger(__name__)

# Trading-day offsets used by the price factors.
_MOMENTUM_LOOKBACK = {
    "momentum_1m": 21, "momentum_3m": 63, "momentum_6m": 126, "momentum_12m": 252,
}
_DEFAULT_BENCHMARK = {"KR": "KS200", "US": "^GSPC"}

PriceLoader = Callable[[str], pd.DataFrame | None]
FundamentalsLoader = Callable[[str, date], pd.DataFrame]


class QuantBacktestError(RuntimeError):
    """The quant backtest cannot be run as specified."""


# --------------------------------------------------------------------------- #
# Universe
# --------------------------------------------------------------------------- #


def resolve_universe(universe: UniverseConfig) -> list[str]:
    """Candidate tickers from the metadata table, before per-date filtering."""
    df = data_service._load_tickers(universe.market)
    if df.empty:
        return []
    mask = pd.Series(True, index=df.index)
    if universe.exclude_etf:
        mask &= df["kind"].fillna("stock") != "etf"
    mask &= df["kind"].fillna("stock") != "index"
    if universe.boards:
        boards = {b.upper() for b in universe.boards}
        mask &= df["board"].fillna("").astype(str).str.upper().isin(boards)
    tickers = df.loc[mask, "ticker"].astype(str).tolist()
    if universe.exclude_preferred and universe.market == "KR":
        # KR preferred shares end in a non-'0' 6th digit (e.g. 005935); common stock ends 0.
        tickers = [t for t in tickers if not (len(t) == 6 and t[-1] != "0")]
    return tickers


# --------------------------------------------------------------------------- #
# Factor computation
# --------------------------------------------------------------------------- #


def _price_factor(name: str, closes: np.ndarray) -> float | None:
    """A single price/momentum factor from a close series ending at the decision date."""
    n = closes.size
    if name in _MOMENTUM_LOOKBACK:
        k = _MOMENTUM_LOOKBACK[name]
        if n <= k or closes[-1 - k] <= 0:
            return None
        return float(closes[-1] / closes[-1 - k] - 1.0)
    if name == "momentum_12m_1m":
        if n <= 252 or closes[-1 - 252] <= 0 or closes[-1 - 21] <= 0:
            return None
        return float(closes[-1 - 21] / closes[-1 - 252] - 1.0)
    if name == "rsi_14":
        if n <= 15:
            return None
        diff = np.diff(closes[-15:])
        gain = diff[diff > 0].sum()
        loss = -diff[diff < 0].sum()
        if loss == 0:
            return 100.0
        rs = (gain / 14) / (loss / 14)
        return float(100.0 - 100.0 / (1.0 + rs))
    if name == "dist_sma_200":
        if n < 200:
            return None
        sma = closes[-200:].mean()
        return float(closes[-1] / sma - 1.0) if sma > 0 else None
    if name == "dist_high_52w":
        window = closes[-252:] if n >= 252 else closes
        hi = window.max()
        return float(closes[-1] / hi - 1.0) if hi > 0 else None
    return None


def _factor_frame(
    strategy: QuantPortfolioStrategy,
    candidates: list[str],
    closes_by_ticker: dict[str, np.ndarray],
    fundamentals: pd.DataFrame | None,
    market_caps: dict[str, float],
) -> pd.DataFrame:
    """A DataFrame indexed by ticker with one column per factor the strategy uses."""
    from ..schemas import FUNDAMENTAL_FACTORS, PRICE_FACTORS

    wanted = strategy.factors_used()
    rows: dict[str, dict[str, float]] = {}
    for ticker in candidates:
        closes = closes_by_ticker.get(ticker)
        if closes is None or closes.size == 0:
            continue
        values: dict[str, float] = {}
        ok = True
        for factor in wanted:
            if factor in PRICE_FACTORS:
                v = _price_factor(factor, closes)
            elif factor in FUNDAMENTAL_FACTORS:
                v = None
                if fundamentals is not None and ticker in fundamentals.index:
                    raw = fundamentals.at[ticker, factor] if factor in fundamentals.columns else None
                    v = float(raw) if raw is not None and pd.notna(raw) else None
            elif factor == "market_cap":
                v = market_caps.get(ticker)
            else:
                v = None
            if v is None:
                ok = False
                break
            values[factor] = v
        if ok:
            rows[ticker] = values
    if not rows:
        return pd.DataFrame(columns=list(wanted))
    return pd.DataFrame.from_dict(rows, orient="index")


def _apply_filter(frame: pd.DataFrame, cond: FilterCondition) -> pd.DataFrame:
    col = frame[cond.factor]
    if cond.op == ">":
        return frame[col > cond.value]
    if cond.op == "<":
        return frame[col < cond.value]
    if cond.op == ">=":
        return frame[col >= cond.value]
    if cond.op == "<=":
        return frame[col <= cond.value]
    if cond.op == "==":
        return frame[col == cond.value]
    if cond.op == "between":
        return frame[(col >= cond.value) & (col <= cond.value2)]
    if cond.op == "top_pct":
        return frame[col >= col.quantile(1.0 - cond.value / 100.0)]
    if cond.op == "bottom_pct":
        return frame[col <= col.quantile(cond.value / 100.0)]
    return frame


def _composite_rank(frame: pd.DataFrame, strategy: QuantPortfolioStrategy) -> pd.Series:
    """Weighted sum of per-factor percentile ranks (higher = better)."""
    total_weight = sum(r.weight for r in strategy.ranking) or 1.0
    score = pd.Series(0.0, index=frame.index)
    for r in strategy.ranking:
        pct = frame[r.factor].rank(pct=True)  # 0..1, higher value = higher rank
        if r.direction == "asc":
            pct = 1.0 - pct  # smaller is better (e.g. low PBR)
        score += (r.weight / total_weight) * pct
    return score.sort_values(ascending=False)


def _target_weights(
    strategy: QuantPortfolioStrategy, ranked: pd.Series, frame: pd.DataFrame,
    market_caps: dict[str, float],
) -> dict[str, float]:
    chosen = ranked.head(strategy.portfolio.num_holdings)
    if chosen.empty:
        return {}
    scheme = strategy.portfolio.weighting
    if scheme == "equal":
        raw = pd.Series(1.0, index=chosen.index)
    elif scheme == "rank":
        raw = pd.Series(np.arange(len(chosen), 0, -1), index=chosen.index, dtype="float64")
    else:  # market_cap
        raw = pd.Series({t: market_caps.get(t, 0.0) for t in chosen.index})
        if raw.sum() <= 0:
            raw = pd.Series(1.0, index=chosen.index)
    weights = raw / raw.sum()
    cap = strategy.portfolio.max_position_pct
    if (weights > cap).any():
        weights = weights.clip(upper=cap)
        weights = weights / weights.sum()  # renormalise after capping
    return weights.to_dict()


# --------------------------------------------------------------------------- #
# Rebalance calendar
# --------------------------------------------------------------------------- #


def _period_key(d: date, freq: str) -> tuple:
    if freq == "monthly":
        return (d.year, d.month)
    if freq == "quarterly":
        return (d.year, (d.month - 1) // 3)
    if freq == "semiannual":
        return (d.year, (d.month - 1) // 6)
    return (d.year,)  # annual


def compute_rebalance_dates(calendar: list[date], start: date, end: date, freq: str) -> list[date]:
    """First trading day of each period within [start, end]."""
    out: list[date] = []
    seen: set[tuple] = set()
    for d in calendar:
        if d < start or d > end:
            continue
        key = _period_key(d, freq)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


# --------------------------------------------------------------------------- #
# Data loading (default, non-injected path)
# --------------------------------------------------------------------------- #


def _default_price_loader(market: str, start: date | None = None) -> PriceLoader:
    """Reads cached bars, widening the cache when `start` predates what we hold."""

    def load(ticker: str) -> pd.DataFrame | None:
        try:
            data_service.ensure_cached(ticker, market, start=start)
            df = data_service.get_ohlcv(ticker, market)
        except data_service.TickerNotFound:
            return None
        factor = (df["adj_close"] / df["close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        df["adj_open"] = df["open"] * factor
        return df[["date", "adj_open", "adj_close"]]

    return load


def _market_caps(market: str) -> dict[str, float]:
    """Best-effort current market caps from metadata (approximate, point-in-time)."""
    df = data_service._load_tickers(market)
    if df.empty or "market_cap" not in df.columns:
        return {}
    caps = df.set_index("ticker")["market_cap"]
    return {str(k): float(v) for k, v in caps.items() if pd.notna(v)}


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def run_quant_backtest(
    strategy: QuantPortfolioStrategy,
    params: QuantBacktestParams,
    *,
    price_loader: PriceLoader | None = None,
    fundamentals_loader: FundamentalsLoader | None = None,
    universe: list[str] | None = None,
) -> BacktestResult:
    market = params.market
    # Ranking factors look back up to ~12 months, so pull history before the start date.
    warmup_start = params.start_date - timedelta(days=420)
    price_loader = price_loader or _default_price_loader(market, start=warmup_start)
    if universe is not None:
        candidates = universe
    else:
        # Backtest over the warmed (cached) slice of the eligible universe: downloading
        # hundreds of tickers synchronously inside one request would time out. The cache
        # fills as users browse charts and via the nightly refresh.
        eligible = set(resolve_universe(strategy.universe))
        candidates = [t for t in data_service.list_cached(market) if t in eligible]
        if not candidates:
            raise QuantBacktestError(
                "no warmed tickers in this universe yet — open a few of its charts first, "
                "or run the OHLCV bootstrap, then retry"
            )
    if not candidates:
        raise QuantBacktestError("universe is empty — check market/board filters")

    # Load adjusted open/close panels for every candidate that has data.
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    for ticker in candidates:
        df = price_loader(ticker)
        if df is None or df.empty:
            continue
        s = df.set_index(pd.to_datetime(df["date"]).dt.date)
        closes[ticker] = s["adj_close"]
        opens[ticker] = s["adj_open"]
    if not closes:
        raise QuantBacktestError("no price data for any universe member")

    panel_close = pd.DataFrame(closes).sort_index()
    panel_open = pd.DataFrame(opens).sort_index()
    calendar = [d for d in panel_close.index if params.start_date <= d <= params.end_date]
    if len(calendar) < 2:
        raise QuantBacktestError("not enough trading days in the requested range")

    rebalance_dates = set(
        compute_rebalance_dates(calendar, params.start_date, params.end_date,
                                strategy.rebalance.frequency)
    )
    caps = _market_caps(market)
    costs = default_costs(market, "KOSPI")
    fee = params.fee_rate if params.fee_rate is not None else costs.buy_fee
    sell_cost = fee + costs.sell_tax
    slip = params.slippage
    needs_fundamentals = bool(strategy.factors_used() & _fundamental_factor_names())

    cash = float(params.initial_capital)
    holdings: dict[str, int] = {}
    lots: dict[str, tuple[date, float]] = {}  # ticker -> (entry_date, entry_price)
    trades: list[Trade] = []
    equity_values: list[float] = []
    equity: list[EquityPoint] = []

    all_dates = list(panel_close.index)
    benchmark = _benchmark_series(params, market, price_loader)
    bh_base: float | None = None

    for pos, d in enumerate(all_dates):
        if d < params.start_date or d > params.end_date:
            continue

        if d in rebalance_dates and pos > 0:
            decision_date = all_dates[pos - 1]  # prior close — no lookahead
            fundamentals = None
            if needs_fundamentals and fundamentals_loader is not None:
                try:
                    fundamentals = fundamentals_loader(market, decision_date)
                except Exception as exc:  # noqa: BLE001
                    raise QuantBacktestError(
                        f"fundamentals unavailable for {decision_date}: {exc}"
                    ) from exc

            # 1. Liquidate the current book at today's open.
            for ticker, shares in list(holdings.items()):
                px = panel_open.at[d, ticker] if ticker in panel_open.columns else np.nan
                if not np.isfinite(px):
                    px = panel_close.at[decision_date, ticker]
                fill = px * (1.0 - slip)
                proceeds = shares * fill * (1.0 - sell_cost)
                cash += proceeds
                entry_date, entry_price = lots[ticker]
                basis = shares * entry_price * (1.0 + fee)
                trades.append(_trade(entry_date, entry_price, d, fill, shares, basis, "rebalance"))
            holdings.clear()
            lots.clear()

            # 2. Choose the new basket from data as of the decision date.
            target = _select(strategy, closes, decision_date, fundamentals, caps)
            pv = cash
            for ticker, weight in target.items():
                px = panel_open.at[d, ticker] if ticker in panel_open.columns else np.nan
                if not np.isfinite(px) or px <= 0:
                    continue
                fill = px * (1.0 + slip)
                budget = min(weight * pv, cash)
                qty = int(np.floor(budget / (fill * (1.0 + fee))))
                if qty <= 0:
                    continue
                cash -= qty * fill * (1.0 + fee)
                holdings[ticker] = qty
                lots[ticker] = (d, fill)

        # 3. Mark to market at today's close.
        position_value = 0.0
        for ticker, shares in holdings.items():
            px = panel_close.at[d, ticker] if ticker in panel_close.columns else np.nan
            if np.isfinite(px):
                position_value += shares * px
        total = cash + position_value
        equity_values.append(total)

        # Flat at initial capital until the benchmark has data — mirroring the portfolio
        # would read as a real comparison line when there is none.
        bh_value = float(params.initial_capital)
        if benchmark is not None and d in benchmark.index and np.isfinite(benchmark[d]):
            if bh_base is None:
                bh_base = float(benchmark[d])
            bh_value = params.initial_capital * float(benchmark[d]) / bh_base
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
    if holdings:
        last = equity[-1].date
        for ticker, shares in list(holdings.items()):
            px = panel_close.at[last, ticker]
            fill = px * (1.0 - slip)
            proceeds = shares * fill * (1.0 - sell_cost)
            cash += proceeds
            entry_date, entry_price = lots[ticker]
            basis = shares * entry_price * (1.0 + fee)
            trades.append(_trade(entry_date, entry_price, last, fill, shares, basis, "end_of_period"))
        equity_values[-1] = cash
        equity[-1] = equity[-1].model_copy(
            update={"portfolio_value": round(cash, 4), "cash": round(cash, 4),
                    "position_value": 0.0}
        )

    metrics: BacktestMetrics = compute_metrics(equity_values, trades, params.initial_capital)
    logger.info(
        "quant backtest %s %s..%s: %d rebalances, %d trades, final %.0f",
        market, params.start_date, params.end_date, len(rebalance_dates), len(trades),
        equity_values[-1] if equity_values else 0.0,
    )
    return BacktestResult(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        params=_as_single_params(params, market),
        metrics=metrics,
        equity_curve=equity,
        trades=trades,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fundamental_factor_names() -> set[str]:
    from ..schemas import FUNDAMENTAL_FACTORS

    return set(FUNDAMENTAL_FACTORS)


def _select(strategy, closes, decision_date, fundamentals, caps) -> dict[str, float]:
    """Filter + rank + weight the candidates using data as of `decision_date`."""
    series_by_ticker: dict[str, np.ndarray] = {}
    for ticker, s in closes.items():
        upto = s[s.index <= decision_date]
        if not upto.empty:
            series_by_ticker[ticker] = upto.to_numpy(dtype="float64")
    frame = _factor_frame(strategy, list(series_by_ticker), series_by_ticker, fundamentals, caps)
    if frame.empty:
        return {}
    for cond in strategy.filters:
        frame = _apply_filter(frame, cond)
        if frame.empty:
            return {}
    ranked = _composite_rank(frame, strategy)
    return _target_weights(strategy, ranked, frame, caps)


def _trade(entry_date, entry_price, exit_date, exit_price, shares, basis, reason) -> Trade:
    proceeds = shares * exit_price
    pnl = proceeds - basis
    return Trade(
        buy_date=entry_date, buy_price=round(entry_price, 6),
        sell_date=exit_date, sell_price=round(exit_price, 6), shares=shares,
        pnl=round(pnl, 6), pnl_pct=round(pnl / basis, 8) if basis else 0.0,
        exit_reason="sell_signal" if reason == "rebalance" else "end_of_period",
    )


def _benchmark_series(params: QuantBacktestParams, market: str, price_loader) -> pd.Series | None:
    ticker = params.benchmark or _DEFAULT_BENCHMARK.get(market)
    if not ticker:
        return None
    try:
        df = price_loader(ticker)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    s = df.set_index(pd.to_datetime(df["date"]).dt.date)["adj_close"]
    return s[(s.index >= params.start_date) & (s.index <= params.end_date)]


def _as_single_params(params: QuantBacktestParams, market: str):
    """A BacktestParams stand-in so the shared BacktestResult schema is satisfied."""
    from ..schemas import BacktestParams

    return BacktestParams(
        ticker=params.benchmark or _DEFAULT_BENCHMARK.get(market, "PORTFOLIO"),
        market=market,
        start_date=params.start_date,
        end_date=params.end_date,
        initial_capital=params.initial_capital,
        slippage=params.slippage,
    )
