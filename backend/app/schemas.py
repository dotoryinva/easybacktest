"""Pydantic v2 models — the single source of truth for the API surface.

The TypeScript/Zod mirror lives at `frontend/src/schemas/`. Keep them in sync by hand.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from ulid import ULID

Market = Literal["KR", "US"]

IndicatorKind = Literal[
    "SMA",
    "EMA",
    "RSI",
    "MACD_LINE",
    "MACD_SIGNAL",
    "BOLLINGER_UPPER",
    "BOLLINGER_LOWER",
    "BOLLINGER_MID",
    "PRICE_CLOSE",
    "PRICE_OPEN",
    "PRICE_HIGH",
    "PRICE_LOW",
    "VOLUME",
    "CONSTANT",
]

Operator = Literal[">", "<", ">=", "<=", "==", "cross_above", "cross_below"]

ExitReason = Literal[
    "sell_signal", "stop_loss", "take_profit", "max_holding_days", "end_of_period"
]

# Indicator defaults applied when the parser omits them.
INDICATOR_DEFAULTS: dict[str, dict[str, Any]] = {
    "RSI": {"period": 14},
    "MACD_LINE": {"fast": 12, "slow": 26, "signal": 9},
    "MACD_SIGNAL": {"fast": 12, "slow": 26, "signal": 9},
    "BOLLINGER_UPPER": {"period": 20, "std": 2.0},
    "BOLLINGER_LOWER": {"period": 20, "std": 2.0},
    "BOLLINGER_MID": {"period": 20, "std": 2.0},
}

# Kinds that carry no parameters at all.
PARAMLESS_KINDS = {
    "PRICE_CLOSE",
    "PRICE_OPEN",
    "PRICE_HIGH",
    "PRICE_LOW",
    "VOLUME",
}

# Explicit JSON Schema for `params`. Pydantic would render a bare `{"type": "object"}`
# for `dict`, which gives the LLM nothing to aim at; this spells out every key.
_PARAMS_JSON_SCHEMA = {
    "type": "object",
    "description": (
        "Parameters for the indicator. Which keys apply depends on `kind`: "
        "SMA/EMA -> period; RSI -> period (default 14); "
        "MACD_LINE/MACD_SIGNAL -> fast, slow, signal (default 12/26/9); "
        "BOLLINGER_* -> period, std (default 20/2.0); "
        "CONSTANT -> value; PRICE_*/VOLUME -> no parameters."
    ),
    "properties": {
        "period": {"type": "integer", "description": "Lookback in trading days."},
        "fast": {"type": "integer", "description": "MACD fast EMA period."},
        "slow": {"type": "integer", "description": "MACD slow EMA period."},
        "signal": {"type": "integer", "description": "MACD signal EMA period."},
        "std": {"type": "number", "description": "Bollinger standard deviations."},
        "value": {"type": "number", "description": "Literal number for CONSTANT."},
        "offset": {
            "type": "integer",
            "description": (
                "Bars to look back, for PRICE_*/VOLUME only. offset=252 means "
                "'the close 252 bars ago'. Default 0."
            ),
        },
    },
    "additionalProperties": False,
}


TickerKind = Literal["stock", "index", "etf"]


class Ticker(BaseModel):
    ticker: str
    name_en: str
    name_ko: str | None = None
    market: Market
    sector: str | None = None
    industry: str | None = None
    kind: TickerKind = "stock"
    is_tradable: bool = True
    aliases: str = ""  # semicolon-separated search terms


class IndicatorRef(BaseModel):
    kind: IndicatorKind
    params: dict = Field(default_factory=dict, json_schema_extra=_PARAMS_JSON_SCHEMA)
    # Cross-asset signals: compute this indicator on a *different* asset than the one being
    # traded (e.g. buy a KR stock when US QQQ crosses its 10-day SMA). Null → the backtest
    # ticker. The signal is aligned to the traded asset's calendar with no lookahead.
    ticker: str | None = Field(
        default=None,
        description="Source asset for this indicator; null means the backtest ticker.",
    )
    market: Market | None = Field(
        default=None, description="Market of the source asset; null means the backtest market."
    )

    @model_validator(mode="after")
    def _fill_and_check_params(self) -> IndicatorRef:
        params = dict(self.params or {})

        if self.kind in PARAMLESS_KINDS:
            # Price/volume series carry no periods, but may be shifted back N bars so a
            # condition can compare a series against its own past (momentum).
            offset = int(params.get("offset", 0) or 0)
            if offset < 0:
                raise ValueError("`offset` must be >= 0")
            if offset > 2520:  # ~10 years of daily bars
                raise ValueError("`offset` must be <= 2520 bars")
            self.params = {"offset": offset} if offset else {}
            return self

        for key, value in INDICATOR_DEFAULTS.get(self.kind, {}).items():
            params.setdefault(key, value)

        if self.kind in ("SMA", "EMA"):
            if "period" not in params:
                raise ValueError(f"{self.kind} requires a `period` parameter")
        if self.kind == "CONSTANT" and "value" not in params:
            raise ValueError("CONSTANT requires a `value` parameter")

        for int_key in ("period", "fast", "slow", "signal"):
            if int_key in params:
                params[int_key] = int(params[int_key])
                if params[int_key] < 1:
                    raise ValueError(f"`{int_key}` must be >= 1")

        self.params = params
        return self

    def cache_key(self) -> tuple:
        return (self.kind, self.ticker, self.market, tuple(sorted(self.params.items())))

    def label(self) -> str:
        base = self._label_body()
        return f"{self.ticker}·{base}" if self.ticker else base

    def _label_body(self) -> str:
        p = self.params
        if self.kind in ("SMA", "EMA"):
            return f"{self.kind}({p['period']})"
        if self.kind == "RSI":
            return f"RSI({p['period']})"
        if self.kind in ("MACD_LINE", "MACD_SIGNAL"):
            name = "MACD" if self.kind == "MACD_LINE" else "MACD Signal"
            return f"{name}({p['fast']},{p['slow']},{p['signal']})"
        if self.kind.startswith("BOLLINGER"):
            band = self.kind.split("_")[1].title()
            return f"Bollinger {band}({p['period']}, {p['std']}σ)"
        if self.kind == "CONSTANT":
            return str(p["value"])
        base = self.kind.replace("PRICE_", "").title()
        offset = int(p.get("offset", 0) or 0)
        return f"{base}[-{offset}]" if offset else base


class Condition(BaseModel):
    left: IndicatorRef
    operator: Operator
    right: IndicatorRef

    def label(self) -> str:
        return f"{self.left.label()} {self.operator} {self.right.label()}"


class StrategyDraft(BaseModel):
    """The part of a Strategy the LLM is responsible for producing.

    `Strategy` adds the server-assigned `id` and `created_at`; keeping them out of the
    tool schema stops the model from inventing ULIDs and timestamps.
    """

    name: str = Field(description="Short descriptive name, in the user's language.")
    description: str = Field(
        description="The user's original natural-language description, verbatim."
    )
    language: Literal["ko", "en"]

    buy_conditions: list[Condition] = Field(
        min_length=1, description="Entry conditions. ALL must be true (AND)."
    )

    sell_conditions: list[Condition] = Field(
        default_factory=list, description="Exit conditions. ANY triggers a sell (OR)."
    )
    stop_loss_pct: float | None = Field(
        default=None, gt=0, lt=1, description="Fraction, e.g. 0.05 for -5%."
    )
    take_profit_pct: float | None = Field(
        default=None, gt=0, description="Fraction, e.g. 0.20 for +20%."
    )
    max_holding_days: int | None = Field(default=None, gt=0)

    position_sizing: Literal["all_in", "fixed_amount", "percent_of_capital"] = "all_in"
    position_size_value: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Currency amount when position_sizing=fixed_amount; "
            "fraction 0-1 when position_sizing=percent_of_capital."
        ),
    )

    allow_reentry_same_day: bool = False
    cooldown_days_after_exit: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_exits_and_sizing(self) -> StrategyDraft:
        has_exit = bool(
            self.sell_conditions
            or self.stop_loss_pct is not None
            or self.take_profit_pct is not None
            or self.max_holding_days is not None
        )
        if not has_exit:
            raise ValueError(
                "A strategy needs at least one exit rule: sell_conditions, "
                "stop_loss_pct, take_profit_pct or max_holding_days."
            )
        if self.position_sizing != "all_in" and self.position_size_value is None:
            raise ValueError(
                f"position_sizing={self.position_sizing} requires position_size_value"
            )
        if (
            self.position_sizing == "percent_of_capital"
            and self.position_size_value is not None
            and not 0 < self.position_size_value <= 1
        ):
            raise ValueError("percent_of_capital expects a fraction in (0, 1]")
        return self

    def indicator_refs(self) -> list[IndicatorRef]:
        refs: list[IndicatorRef] = []
        for cond in [*self.buy_conditions, *self.sell_conditions]:
            refs.extend([cond.left, cond.right])
        return refs


class Strategy(StrategyDraft):
    id: str = Field(default_factory=lambda: str(ULID()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Discriminator across authoring families. Single-stock is the original (and default,
    # so strategies stored before Change 13 still validate). See QuantPortfolioStrategy.
    family: Literal["single_stock"] = "single_stock"


# --------------------------------------------------------------------------- #
# Change 13 — Quant portfolio family (factor-ranked multi-stock portfolios)
# --------------------------------------------------------------------------- #

# Factors computable purely from cached OHLCV (work anywhere lazy-loading reaches).
PRICE_FACTORS = {
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m", "momentum_12m_1m",
    "rsi_14", "dist_sma_200", "dist_high_52w",
}
# Factors that require a fundamentals snapshot (KR via the fundamentals service).
FUNDAMENTAL_FACTORS = {
    "per", "pbr", "psr", "earnings_yield", "book_yield", "dividend_yield", "roe", "roa",
}
# `market_cap` comes from the ticker metadata snapshot (approximate / point-in-time now).

QuantFactor = Literal[
    "per", "pbr", "psr", "earnings_yield", "book_yield", "dividend_yield", "roe", "roa",
    "momentum_1m", "momentum_3m", "momentum_6m", "momentum_12m", "momentum_12m_1m",
    "rsi_14", "dist_sma_200", "dist_high_52w",
    "market_cap",
]

FilterOperator = Literal[">", "<", ">=", "<=", "==", "between", "top_pct", "bottom_pct"]
RebalanceFrequency = Literal["monthly", "quarterly", "semiannual", "annual"]
WeightingScheme = Literal["equal", "rank", "market_cap"]


class UniverseConfig(BaseModel):
    """Step 1 — which stocks are eligible before any filtering."""

    market: Market = "KR"
    boards: list[str] = Field(
        default_factory=lambda: ["KOSPI", "KOSDAQ"],
        description="Board/exchange names to include, e.g. KOSPI/KOSDAQ or NASDAQ/NYSE.",
    )
    exclude_etf: bool = True
    exclude_preferred: bool = True  # KR preferred shares end in a non-'0' 6th digit
    market_cap_min: float | None = Field(
        default=None, ge=0, description="Minimum market cap in 억원 (KR) / USD (US)."
    )


class FilterCondition(BaseModel):
    """Step 2 — a boolean gate a stock must pass. `top_pct`/`bottom_pct` are relative."""

    factor: QuantFactor
    op: FilterOperator
    value: float | None = None
    value2: float | None = None  # upper bound for `between`

    @model_validator(mode="after")
    def _check(self) -> FilterCondition:
        if self.op == "between" and (self.value is None or self.value2 is None):
            raise ValueError("`between` requires both value and value2")
        if self.op in ("top_pct", "bottom_pct"):
            if self.value is None or not 0 < self.value <= 100:
                raise ValueError(f"{self.op} requires value in (0, 100]")
        elif self.value is None:
            raise ValueError(f"operator {self.op} requires a value")
        return self


class RankingFactor(BaseModel):
    """Step 3 — a factor contributing to the composite rank, with a weight."""

    factor: QuantFactor
    direction: Literal["asc", "desc"] = "desc"  # asc = smaller is better (e.g. PBR)
    weight: float = Field(default=1.0, ge=0)


class PortfolioConfig(BaseModel):
    """Step 4 — how the selected stocks are held."""

    num_holdings: int = Field(default=20, ge=1, le=200)
    weighting: WeightingScheme = "equal"
    max_position_pct: float = Field(default=0.2, gt=0, le=1)


class RebalanceConfig(BaseModel):
    """Step 5 — how often the portfolio is rebalanced."""

    frequency: RebalanceFrequency = "monthly"


class QuantPortfolioStrategy(BaseModel):
    """A factor-ranked, periodically-rebalanced multi-stock portfolio (Quantus style)."""

    family: Literal["quant_portfolio"] = "quant_portfolio"
    id: str = Field(default_factory=lambda: str(ULID()))
    name: str
    description: str = ""
    language: Literal["ko", "en"] = "ko"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    filters: list[FilterCondition] = Field(default_factory=list)
    ranking: list[RankingFactor] = Field(
        min_length=1, description="At least one ranking factor drives selection."
    )
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    rebalance: RebalanceConfig = Field(default_factory=RebalanceConfig)

    def factors_used(self) -> set[str]:
        return {f.factor for f in self.filters} | {r.factor for r in self.ranking}


class QuantBacktestParams(BaseModel):
    market: Market = "KR"
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000_000, gt=0)
    benchmark: str | None = Field(
        default=None, description="Index ticker for the comparison line (default per market)."
    )
    slippage: float = Field(default=0.001, ge=0, lt=1)
    fee_rate: float | None = Field(default=None, ge=0, lt=1)

    @model_validator(mode="after")
    def _check_dates(self) -> QuantBacktestParams:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class RunQuantBacktestRequest(BaseModel):
    strategy: QuantPortfolioStrategy
    params: QuantBacktestParams


# --------------------------------------------------------------------------- #
# Change 14 — Correlation (Tier 2)
# --------------------------------------------------------------------------- #


class TickerRef(BaseModel):
    ticker: str
    market: Market


class TickerStat(BaseModel):
    ticker: str
    mean: float   # annualised mean return
    std: float    # annualised volatility
    sharpe: float


class CorrelationRequest(BaseModel):
    tickers: list[TickerRef] = Field(min_length=2, max_length=15)
    start_date: date
    end_date: date
    frequency: Literal["daily", "weekly", "monthly"] = "daily"

    @model_validator(mode="after")
    def _check_dates(self) -> CorrelationRequest:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class CorrelationResponse(BaseModel):
    tickers: list[str]
    matrix: list[list[float]]
    stats: list[TickerStat]


# --------------------------------------------------------------------------- #
# Change 14 — Static asset allocation (Tier 2)
# --------------------------------------------------------------------------- #


class AllocationHolding(BaseModel):
    ticker: str
    weight: float = Field(gt=0, description="Relative weight; normalised to sum to 1.")
    market: Market | None = Field(
        default=None, description="Per-holding market; falls back to the request market."
    )


class StaticAllocationRequest(BaseModel):
    name: str = "정적 배분"
    market: Market = "US"  # default for holdings that don't specify their own
    holdings: list[AllocationHolding] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000_000, gt=0)
    rebalance: RebalanceFrequency = "quarterly"
    benchmark: str | None = None
    slippage: float = Field(default=0.001, ge=0, lt=1)

    @model_validator(mode="after")
    def _check(self) -> StaticAllocationRequest:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


# --------------------------------------------------------------------------- #
# Change 14 — Dynamic (rule-based rotation) allocation (Tier 2)
# --------------------------------------------------------------------------- #

# Named preset rotation strategies. Custom rule-building is Phase 2.
# `qqq_trend_kr` is cross-market: a US QQQ trend signal that trades KR-listed ETFs (D+1).
DynamicStrategyKind = Literal["dual_momentum", "vaa", "laa", "gtaa", "qqq_trend_kr"]


class DynamicAllocationRequest(BaseModel):
    strategy: DynamicStrategyKind
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000_000, gt=0)
    lookback_months: int = Field(default=12, ge=1, le=24)
    benchmark: str | None = None
    slippage: float = Field(default=0.001, ge=0, lt=1)

    @model_validator(mode="after")
    def _check(self) -> DynamicAllocationRequest:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


# --------------------------------------------------------------------------- #
# Change 15 — Unified asset allocation (Quantus-style)
# --------------------------------------------------------------------------- #

# First pass implements `static` + `risk_parity`. The solver-based algorithms
# (min_variance/max_sharpe/vol_target/erc/hrp) need scipy and are deferred.
AllocationAlgorithm = Literal[
    "static", "risk_parity", "min_variance", "max_sharpe", "vol_target", "erc", "hrp"
]
WeightScheme = Literal["equal", "custom", "inverse_vol", "inverse_corr", "market_cap"]
AllocationRebalancePeriod = Literal[
    "none", "daily", "weekly", "monthly", "quarterly", "semi_annually", "annually"
]
MomentumIndicator = Literal["absolute_momentum", "sma_cross", "13612w", "sortino"]


class AssetSlot(BaseModel):
    ticker: str
    market: Market = "KR"
    target_weight_pct: float | None = None  # only for algorithm=static + weight_scheme=custom


class MomentumTiming(BaseModel):
    indicator: MomentumIndicator = "absolute_momentum"
    lookback_months: int = Field(default=12, ge=1, le=36)
    mode: Literal["per_asset", "canary"] = "per_asset"
    canary_ticker: str | None = None
    canary_market: Market = "US"
    safe_haven_ticker: str
    safe_haven_market: Market = "KR"
    threshold: float = 0.0


class ReentryTiming(BaseModel):
    rule: Literal["immediate", "delayed", "consecutive"] = "immediate"
    n: int = Field(default=1, ge=1, le=12)
    max_off_months: int | None = None


class AllocationStrategy(BaseModel):
    """Weighted basket of ETFs/indices with an allocation algorithm + optional timing.

    Standalone `family="allocation"` model (like QuantPortfolioStrategy), saved via the
    same POST /api/strategies. Not folded into a `Strategy.body` union to avoid churning
    the existing single-stock/quant models.
    """

    family: Literal["allocation"] = "allocation"
    id: str = Field(default_factory=lambda: str(ULID()))
    name: str = "자산배분 전략"
    description: str = ""
    language: Literal["ko", "en"] = "ko"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    algorithm: AllocationAlgorithm = "static"
    assets: list[AssetSlot] = Field(min_length=1, max_length=30)
    weight_scheme: WeightScheme | None = "equal"  # None ⇒ algorithm-controlled
    rebalance_period: AllocationRebalancePeriod = "annually"
    rebalance_band_pct: float = Field(default=0.0, ge=0, le=100)  # 0 disables band rebalance
    apply_fx: bool = True
    lookback_days_for_estimation: int = Field(default=252, ge=20, le=1260)
    vol_target_annual: float | None = None

    momentum_timing: MomentumTiming | None = None
    reentry_timing: ReentryTiming | None = None

    def markets(self) -> set[str]:
        m = {a.market for a in self.assets}
        if self.momentum_timing:
            m.add(self.momentum_timing.safe_haven_market)
            if self.momentum_timing.canary_ticker:
                m.add(self.momentum_timing.canary_market)
        return m


class AllocationBacktestParams(BaseModel):
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000_000, gt=0)
    initial_capital_currency: Literal["KRW", "USD"] = "KRW"
    benchmark: str | None = None
    slippage: float = Field(default=0.001, ge=0, lt=1)

    @model_validator(mode="after")
    def _check(self) -> AllocationBacktestParams:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class RunAllocationRequest(BaseModel):
    strategy: AllocationStrategy
    params: AllocationBacktestParams


class ExtractPortfolioRequest(BaseModel):
    strategy: AllocationStrategy
    as_of_date: date | None = None
    capital: float = Field(default=10_000_000, gt=0)


class PortfolioHolding(BaseModel):
    ticker: str
    name: str
    market: Market
    weight: float
    price: float
    target_shares: int
    target_krw: float


class ExtractPortfolioResponse(BaseModel):
    as_of_date: date
    holdings: list[PortfolioHolding]
    cash_remainder: float
    total_krw: float


# --------------------------------------------------------------------------- #
# Change 14 — Seasonality (Tier 2)
# --------------------------------------------------------------------------- #


class MonthlyCell(BaseModel):
    year: int
    month: int  # 1-12
    return_pct: float


class MonthStat(BaseModel):
    month: int
    mean: float
    positive_rate: float
    best: float
    worst: float
    count: int


class WeekdayStat(BaseModel):
    weekday: int  # 0=Mon .. 4=Fri
    mean: float
    positive_rate: float
    count: int


class TurnOfMonthStat(BaseModel):
    """Last 3 trading days of a month vs. every other trading day."""

    turn_mean: float
    rest_mean: float
    turn_count: int
    rest_count: int


class SeasonalityResponse(BaseModel):
    ticker: str
    market: Market
    name: str
    start_year: int
    end_year: int
    monthly: list[MonthlyCell]
    month_stats: list[MonthStat]
    weekday_stats: list[WeekdayStat]
    turn_of_month: TurnOfMonthStat


class BacktestParams(BaseModel):
    ticker: str
    market: Market
    start_date: date
    end_date: date
    initial_capital: float = Field(default=10_000_000, gt=0)
    fee_rate: float | None = Field(default=None, ge=0, lt=1)
    sell_tax_rate: float | None = Field(default=None, ge=0, lt=1)
    slippage: float = Field(default=0.001, ge=0, lt=1)

    @model_validator(mode="after")
    def _check_dates(self) -> BacktestParams:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class Trade(BaseModel):
    buy_date: date
    buy_price: float
    sell_date: date
    sell_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: ExitReason


class BacktestMetrics(BaseModel):
    total_return_pct: float
    cagr: float
    mdd: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    num_trades: int
    avg_holding_days: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float | None


class EquityPoint(BaseModel):
    date: date
    portfolio_value: float
    cash: float
    position_value: float
    buy_hold_value: float


class BacktestResult(BaseModel):
    strategy_id: str | None = None
    strategy_name: str | None = None
    params: BacktestParams
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    ran_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
# Request / response envelopes
# --------------------------------------------------------------------------- #


class Candle(BaseModel):
    """Lightweight Charts wire format (`time` is an ISO date string)."""

    time: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCVResponse(BaseModel):
    ticker: str
    market: Market
    name: str
    kind: TickerKind = "stock"
    is_tradable: bool = True
    candles: list[Candle]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ParseStrategyRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    ticker: str
    market: Market
    conversation_history: list[ChatMessage] = Field(default_factory=list)
    current_strategy: Strategy | None = Field(
        default=None,
        description="Existing strategy to revise; omitted when creating a brand-new strategy.",
    )

    @field_validator("conversation_history")
    @classmethod
    def _cap_history(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        # 3 clarification rounds => at most 6 prior turns plus the opening message.
        if len(v) > 12:
            raise ValueError("conversation_history is too long; start a new session")
        return v


class ParsedStrategyResponse(BaseModel):
    kind: Literal["strategy"] = "strategy"
    strategy: Strategy


class ClarificationResponse(BaseModel):
    kind: Literal["clarification"] = "clarification"
    questions: list[str]
    partial_strategy: dict | None = None


class RunBacktestRequest(BaseModel):
    strategy: Strategy
    params: BacktestParams


class SaveStrategyRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    strategy: Strategy


class UpdateStrategyRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    strategy: Strategy


class SavedStrategy(BaseModel):
    strategy: Strategy
    user_id: str
    updated_at: datetime
    last_run: BacktestParams | None = None


# --------------------------------------------------------------------------- #
# QuantStats HTML report (Change 16)
# --------------------------------------------------------------------------- #


class ReportPoint(BaseModel):
    """One day of the equity curve: strategy value + benchmark (buy & hold) value."""

    date: date
    strategy: float
    benchmark: float = 0.0


class QuantStatsReportRequest(BaseModel):
    title: str = Field(default="Backtest Report", max_length=200)
    points: list[ReportPoint] = Field(min_length=20)
    format: Literal["html", "pdf"] = "html"


# --------------------------------------------------------------------------- #
# Market snapshot — Heatmap / ETF / Screener (Change 17)
# --------------------------------------------------------------------------- #


class SnapshotRow(BaseModel):
    ticker: str
    market: Market
    name_ko: str | None = None
    name_en: str
    kind: TickerKind
    as_of: date
    price: float
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None
    ret_ytd: float | None = None
    vol_ann: float | None = None
    rsi_14: float | None = None
    dist_sma200: float | None = None
    dist_high52w: float | None = None


class MarketSnapshotResponse(BaseModel):
    market: Market
    rows: list[SnapshotRow]


class QuoteItem(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    market: Market


class QuotesRequest(BaseModel):
    items: list[QuoteItem] = Field(default_factory=list, max_length=100)


class QuotesResponse(BaseModel):
    rows: list[SnapshotRow]


# --------------------------------------------------------------------------- #
# Retirement Monte Carlo (Change 17)
# --------------------------------------------------------------------------- #


class RetirementRequest(BaseModel):
    current_age: int = Field(ge=18, le=90)
    retirement_age: int = Field(ge=30, le=95)
    end_age: int = Field(default=95, ge=60, le=110)
    current_savings: float = Field(ge=0)
    annual_contribution: float = Field(default=0, ge=0)  # while still working
    annual_spending: float = Field(ge=0)  # in retirement, today's money
    expected_return: float = Field(default=0.06, ge=-0.2, le=0.4)  # nominal, annual
    volatility: float = Field(default=0.12, ge=0.0, le=0.6)
    inflation: float = Field(default=0.025, ge=0.0, le=0.2)
    num_simulations: int = Field(default=2000, ge=200, le=10000)

    @model_validator(mode="after")
    def _order(self) -> "RetirementRequest":
        if self.retirement_age <= self.current_age:
            raise ValueError("retirement_age must be greater than current_age")
        if self.end_age <= self.retirement_age:
            raise ValueError("end_age must be greater than retirement_age")
        return self


class RetirementBand(BaseModel):
    age: int
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class RetirementResponse(BaseModel):
    bands: list[RetirementBand]
    success_probability: float  # fraction of paths solvent through end_age
    median_ending_balance: float
    depletion_age_p50: int | None = None  # median age money runs out (null if it usually lasts)
    safe_annual_spending: float  # spending (today's money) that hits ~90% success
