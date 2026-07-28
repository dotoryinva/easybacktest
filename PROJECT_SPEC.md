# EasyBacktest — AI-Native Stock Backtest Web App

## Context & Goal

Build a stock backtesting web app inspired by easyinvesting.app, targeting both Korean (KOSPI/KOSDAQ) and US (NYSE/NASDAQ) markets. The core differentiator is an AI-native strategy builder: users describe a trading strategy in plain natural language (Korean or English), the LLM parses it into an executable strategy, asks focused clarifying questions when ambiguous, runs a backtest immediately, and saves the strategy to the user's library.

This is not a general-purpose tool — it is specifically a conversation-first backtest app. The AI parser is not a bolt-on feature; it is the primary way strategies are created.

## Scope for This Build (Phase 1)

Build exactly these five surfaces. Do not build anything else.

1. **Chart Page** — TradingView Lightweight Charts, ticker search, SMA/EMA overlays, timeframe selector, CSV export.
2. **AI Strategy Builder** — natural language input → LLM parse → clarification loop → instant backtest → save.
3. **Manual Strategy Builder** — form-based editor. Shares the same `Strategy` schema, preview card, backtest execution, and save flow as the AI builder. First-class, not a fallback.
4. **Strategy Library** — list of saved strategies, click to re-run.
5. **Printable PDF Backtest Report** — server-generated PDF with equity curve chart, drawdown chart, monthly returns heatmap, all metrics, trade log, and strategy definition. Must render Korean correctly.

Explicitly out of scope for now: portfolio allocation, watchlist, portfolio tracking, screener, heatmap, macro dashboards, ETF tab, correlation search, seasonality, Guru (13F), crypto, retirement calculator, authentication. Design the data models so these can be added later, but do not implement them.

## Tech Stack (Non-Negotiable)

### Frontend

* Vite + React 18 + TypeScript (strict mode)
* TailwindCSS for styling
* TradingView Lightweight Charts v4.x for OHLCV charts (via the `lightweight-charts` npm package)
* Recharts for backtest result curves (equity curve, drawdown chart)
* TanStack Query for server state
* Zustand for local UI state (strategy builder session, chart preferences)
* React Router v6 for routing
* Zod for schema validation (mirrored from backend Pydantic models)
* `lucide-react` for all icons — no emoji as UI icons
* Pretendard Variable via the `pretendard` or `@fontsource-variable/pretendard` package
* See "Visual Design System" for the colors, typography scale, and per-page layout rules

### Backend

* FastAPI (Python 3.11+) + Pydantic v2
* Google Gemini SDK for the LLM parser (`google-generativeai` package) — migrated from
  Anthropic in Change 11
* pandas 2.x (pinned `<3`; the data providers do not yet support pandas 3), numpy, pyarrow
  for data and computation
* FinanceDataReader as the primary data source, with pykrx as a fallback for Korean market precision and yfinance as a fallback for US precision
* DuckDB for querying the local Parquet OHLCV cache (much faster than reading Parquet files one by one)
* SQLite for user data and saved strategies (schema designed to migrate to Postgres later)
* APScheduler for the nightly data refresh job
* matplotlib (Agg backend) + ReportLab for the PDF report — see "PDF Backtest Report" for
  the full constraints, including the ban on WeasyPrint / wkhtmltopdf / Playwright
* `hangul-romanize>=0.1.0` for romanizing Korean strategy names into PDF filenames
  (0.1.0 is the latest release on PyPI — do not pin above it)

### Deployment

* Frontend → Cloudflare Pages
* Backend → Fly.io (single machine, 1GB RAM is enough for Phase 1)
* OHLCV Parquet cache → mounted Fly.io volume (`/data`)

## Data Sources & Ingestion

### Ingestion Strategy

* On first startup, run `scripts/bootstrap_data.py` to download 15 years of history for the
  curated ticker universe enumerated in "Ticker Universe" below. Target size:
  **~1,100 US tickers + ~850 KR tickers.**
* Store each ticker as an individual Parquet file at `data/ohlcv/{market}/{ticker}.parquet` with columns `[date, open, high, low, close, volume, adj_close]`
* Also store `data/tickers/{market}.parquet` — a metadata table with `[ticker, name_en, name_ko, market, sector, industry, kind, is_tradable, aliases, first_traded, last_updated]`
* Nightly refresh at 07:00 KST via APScheduler: pull the last 5 trading days and upsert. Weekend runs are no-ops.

### Ticker Universe

> **As built (Change 12):** the universe is now **complete and metadata-heavy /
> OHLCV-lazy**. `scripts/bootstrap_metadata.py` loads *all* ticker metadata for both
> markets — US from the NASDAQ Trader SymbolDirectory (`nasdaqlisted.txt` +
> `otherlisted.txt`), KR from FinanceDataReader `StockListing('KRX')` + `StockListing('ETF/KR')`,
> plus the hand-curated indices below — writing `data/tickers/{US,KR}.parquet`
> (~11,300 US + ~4,000 KR rows, loads instantly, runs in seconds). OHLCV is **not**
> downloaded up front: `data_service.ensure_cached` fetches and caches a ticker's history
> on its first `/api/ohlcv` request. Search (`/api/tickers/search`) now spans the whole
> universe by default (`cached_only=false`), ranks by code/alias/name match with a
> popularity tie-break (`ticker_popularity` table), and expands Korean brand phonetics to
> their Latin ETF names (타이거 → TIGER). The original `bootstrap_data.py` remains for
> pre-warming a small OHLCV "warm set".

Indices and major ETFs are the most-searched tickers in a real backtest app, so they are
enumerated explicitly rather than left to a "top N by AUM" heuristic.

**Major indices** — chartable and backtestable, marked `kind="index"`, `is_tradable=False`:

| Market | Tickers |
|---|---|
| US | `^GSPC` (S&P 500), `^IXIC` (NASDAQ Composite), `^DJI` (Dow Jones), `^RUT` (Russell 2000), `^VIX` (Volatility) |
| KR | `KS11` (KOSPI), `KQ11` (KOSDAQ), `KS200` (KOSPI 200), `KQ150` (KOSDAQ 150) |

**Broad index ETFs (US, tradable):**
SPY, VOO, IVV, QQQ, QQQM, DIA, IWM, VTI, VEA, VWO, VXUS, TLT, IEF, SHY, GLD, SLV, USO, DBC

**Sector ETFs (US SPDR Select Sector):**
XLK, XLF, XLE, XLV, XLP, XLY, XLI, XLU, XLB, XLRE, XLC

**Country / theme ETFs (US):**
EWZ, EWJ, EWG, MCHI, INDA, EEM, EFA, ARKK, SOXX, SMH

**Korean index and theme ETFs** (KR ticker codes):

| Ticker | Name |
|---|---|
| 069500 | KODEX 200 |
| 102110 | TIGER 200 |
| 122630 | KODEX 레버리지 |
| 114800 | KODEX 인버스 |
| 226980 | KODEX 200TR |
| 305720 | KODEX 200선물인버스2X |
| 360750 | TIGER 미국S&P500 |
| 379800 | KODEX 미국S&P500TR |
| 381180 | TIGER 미국테크TOP10 |
| 133690 | TIGER 미국나스닥100 |
| 371460 | TIGER 차이나전기차SOLACTIVE |
| 305080 | TIGER 미국채10년선물 |
| 132030 | KODEX 골드선물 |

**Aliases.** `aliases` is a semicolon-separated string of common search terms, in both
Korean and English, so users find a ticker by the name they actually think in.

* `^GSPC` → `"S&P 500;S&P;SPX;SP500;스탠다드앤푸어스;스탠다드앤푸어스500;에스앤피"`
* `SPY` → `"SPY;S&P 500 ETF;에스피와이;미국S&P500ETF"`

### Bootstrap Priority Order

`scripts/bootstrap_data.py` downloads in this order, so an interrupted or rate-limited
run still leaves the most-searched tickers cached:

1. All indices (both markets)
2. All broad index ETFs (both markets)
3. All sector / theme / country ETFs
4. S&P 500 constituents
5. NASDAQ 100 constituents
6. KOSPI top 500 by market cap
7. KOSDAQ top 300 by market cap

### Data Source Selection Logic

Wrap each provider behind a common interface `DataProvider` with method `get_ohlcv(ticker, market, start, end) -> pd.DataFrame`. Order of attempt:

* KR: FinanceDataReader first → pykrx fallback on failure or NaN gaps
* US: yfinance first → FinanceDataReader fallback

Never let the app hit a data provider at request time. All data must come from the local Parquet cache. If a ticker is requested that's not in the cache, return HTTP 404 with a clear error message. Ticker addition is a manual admin operation for now.

### Adjustments

Always use adjusted close for backtest calculations (splits and dividends). Store both `close` and `adj_close`. Show unadjusted close on the chart (which is what users expect visually), but pass adjusted close to the backtest engine.

## Data Models

### Core Pydantic Models (`app/schemas.py`)

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date, datetime

# Market and ticker
class Ticker(BaseModel):
    ticker: str
    name_en: str
    name_ko: str | None
    market: Literal["KR", "US"]
    sector: str | None
    industry: str | None
    kind: Literal["stock", "index", "etf"] = "stock"
    is_tradable: bool = True          # False for indices
    aliases: str = ""                 # semicolon-separated search terms

# Indicator reference used inside conditions
class IndicatorRef(BaseModel):
    kind: Literal["SMA", "EMA", "RSI", "MACD_LINE", "MACD_SIGNAL",
                  "BOLLINGER_UPPER", "BOLLINGER_LOWER", "BOLLINGER_MID",
                  "PRICE_CLOSE", "PRICE_OPEN", "PRICE_HIGH", "PRICE_LOW",
                  "VOLUME", "CONSTANT"]
    # Parameters interpretation depends on kind:
    # SMA/EMA: {"period": int}
    # RSI: {"period": int}  (default 14)
    # MACD_*: {"fast": int, "slow": int, "signal": int}  (default 12,26,9)
    # BOLLINGER_*: {"period": int, "std": float}  (default 20, 2.0)
    # CONSTANT: {"value": float}
    # PRICE_*/VOLUME: {"offset": int}  (optional, default 0)
    #   Bars to look back: offset=252 means "the close 252 bars ago". Lets a condition
    #   compare a series against its own past — required by the 듀얼 모멘텀 preset.
    #   The evaluator shifts the series by `offset`; shifted bars are NaN during warm-up
    #   and, like any NaN, can never produce a true signal.
    params: dict = Field(default_factory=dict)

# A single boolean condition
class Condition(BaseModel):
    left: IndicatorRef
    operator: Literal[">", "<", ">=", "<=", "==",
                      "cross_above", "cross_below"]
    right: IndicatorRef

# Complete strategy
class Strategy(BaseModel):
    id: str  # ULID
    name: str  # AI-suggested or user-edited
    description: str  # original natural language input, verbatim
    language: Literal["ko", "en"]

    # Entry: all must be true (AND)
    buy_conditions: list[Condition]

    # Exit rules — ANY of these triggers a sell
    sell_conditions: list[Condition] = Field(default_factory=list)
    stop_loss_pct: float | None = None  # e.g. 0.05 for -5%
    take_profit_pct: float | None = None  # e.g. 0.20 for +20%
    max_holding_days: int | None = None

    # Position sizing
    position_sizing: Literal["all_in", "fixed_amount", "percent_of_capital"] = "all_in"
    position_size_value: float | None = None

    # Reentry policy
    allow_reentry_same_day: bool = False
    cooldown_days_after_exit: int = 0

    created_at: datetime

class BacktestParams(BaseModel):
    ticker: str
    market: Literal["KR", "US"]
    start_date: date
    end_date: date
    initial_capital: float = 10_000_000  # KRW; adjust to USD equivalent when market=="US"
    fee_rate: float | None = None  # if None, use market default
    sell_tax_rate: float | None = None  # if None, use market default
    slippage: float = 0.001

class Trade(BaseModel):
    buy_date: date
    buy_price: float
    sell_date: date
    sell_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: Literal["sell_signal", "stop_loss", "take_profit", "max_holding_days", "end_of_period"]

class BacktestMetrics(BaseModel):
    total_return_pct: float
    cagr: float
    mdd: float  # max drawdown, negative number
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
    buy_hold_value: float  # comparison baseline

class BacktestResult(BaseModel):
    strategy_id: str | None  # null if ad-hoc
    params: BacktestParams
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    ran_at: datetime
```

Mirror these in TypeScript using Zod schemas at `frontend/src/schemas/`. Do NOT duplicate manually — use a codegen step or keep the mirror files as the single source of truth on the frontend side and match them by hand for now.

## The AI Strategy Builder (The Differentiator)

This is the most important feature. Build it with extra care.

### User Flow

1. User lands at `/build`. Sees:
   * A prominent ticker + market picker at the top (default: last-used, or 삼성전자 / KR)
   * A large multi-line textarea with placeholder: `"예: 20일 이동평균선이 60일 이동평균선을 상향돌파할 때 사고, 하향돌파할 때 팔아. 5% 손절."` and `"or in English: 'Buy when 20-day SMA crosses above 60-day SMA. Sell on cross below. 5% stop loss.'"`
   * A "전략 만들기 / Build Strategy" primary button
2. User submits. Frontend POSTs to `/api/ai/parse-strategy` with `{ description, ticker, market, conversation_history: [] }`.
3. Backend calls Claude via tool use. Claude MUST invoke exactly one of two tools:
   * `create_strategy` — the full `Strategy` schema (returns when description is complete)
   * `ask_clarification` — `{ questions: string[], partial_strategy: Strategy | null }` (returns when ambiguous)
4. If `ask_clarification`:
   * Frontend shows the questions as inline chat bubbles below the input
   * User types answers in a smaller text box
   * Frontend POSTs again with `conversation_history` containing the full back-and-forth
   * Loop up to 3 rounds; if still ambiguous, tell the user to rephrase
5. If `create_strategy`:
   * Frontend renders a Strategy Preview Card with human-readable summary:
     * Buy conditions bullet list
     * Sell conditions bullet list
     * Stop loss / take profit as chips
     * Position sizing
   * Below the card: `[백테스트 실행]` `[전략 수정]` `[저장]` buttons
   * The preview must be editable — clicking "전략 수정" opens a form-based editor that mutates the parsed `Strategy` object directly. Users often want to tweak a value the AI got 90% right.
6. On "백테스트 실행": frontend POSTs `{ strategy, params }` to `/api/backtest/run`. Response includes the full `BacktestResult`. Frontend displays:
   * Equity curve chart (Recharts, portfolio vs buy-and-hold overlay)
   * Metrics grid (CAGR, MDD, Sharpe, win rate, num trades)
   * Trade log table (paginated, sortable)
7. On "저장": POST to `/api/strategies` to persist. Redirect to `/library`.

### Gemini API Integration

> **As built (Change 11):** the LLM provider is **Google Gemini** via the
> `google-generativeai` SDK, not Anthropic. A `GenerativeModel` is constructed with the
> system prompt, the two tools, `tool_config` forcing `mode=ANY`, and `temperature=0`.
> The two Pydantic-derived tool schemas are converted from JSON Schema into Gemini's
> Schema subset (`ai_parser._to_gemini_schema`). Transient `ResourceExhausted` /
> `ServiceUnavailable` errors are retried with 1s/2s/4s backoff; a hard quota or a
> definite API error surfaces as a typed `AIParserUnavailable` / `AIParserError`.
> Default model `gemini-3.6-flash`, fallback `gemini-3.5-flash-lite`
> (`GEMINI_USE_FALLBACK_MODEL=true`).

The two-tool design below is unchanged; only the transport (Anthropic → Gemini) differs.

Define two tools:

```python
CREATE_STRATEGY_TOOL = {
    "name": "create_strategy",
    "description": "Emit a complete, executable trading strategy when the user's description contains all necessary information.",
    "input_schema": Strategy.model_json_schema()  # generate from Pydantic
}

ASK_CLARIFICATION_TOOL = {
    "name": "ask_clarification",
    "description": "Ask 1-3 focused clarifying questions when the description is missing critical information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3
            },
            "partial_strategy": {
                "type": ["object", "null"],
                "description": "The best-effort partial strategy so the frontend can show what's been understood so far"
            }
        },
        "required": ["questions"]
    }
}
```

Set `tool_choice={"type": "any"}` so Claude must use one.

### System Prompt for the Parser

```
You are a trading strategy parser. You convert natural language descriptions of stock trading strategies into structured, executable strategy definitions.

You have two tools. You MUST use exactly one of them:

1. `create_strategy` — Use this when the user's description contains all the information needed to run a backtest.
2. `ask_clarification` — Use this when critical information is missing. Ask 1 to 3 focused questions.

"Complete" means all of the following:
- At least one buy condition with specific indicators and thresholds
- Either at least one sell condition, or a stop_loss_pct, or a take_profit_pct (any exit rule is fine)
- Buy/sell conditions reference specific periods (e.g., "20-day SMA", not just "moving average")

"Ambiguous" examples that require clarification:
- "Buy when the stock is cheap" → ask what "cheap" means (RSI < 30? P/E ratio? % off 52-week high?)
- "Buy on the golden cross" → ask which two moving averages (5/20? 20/60? 50/200?)
- "Buy when it's going up" → ask what specific signal indicates uptrend
- Buy conditions specified but NO exit rule at all → ask for either sell conditions or a stop loss

Defaults you SHOULD assume without asking:
- Position sizing: "all_in" if not mentioned
- Fee rate and tax rate: null (backend will fill market defaults)
- Slippage: 0.1%
- Reentry: allow_reentry_same_day=false, cooldown_days_after_exit=0
- Moving average price basis: closing price
- RSI period: 14
- MACD parameters: 12/26/9
- Bollinger Bands: 20-period, 2 standard deviations

Language:
- Detect the user's language from their description
- Ask clarification questions in the SAME language
- The Strategy's `name` field: generate a short, descriptive name in the user's language (e.g., "20/60 골든크로스 + 5% 손절" or "RSI Oversold Bounce")
- The Strategy's `description` field: copy the user's original description verbatim

Common Korean trading terms to recognize:
- "골든크로스" = shorter MA crosses above longer MA
- "데드크로스" = shorter MA crosses below longer MA
- "이평선" or "이동평균선" = moving average (usually SMA unless specified)
- "손절" = stop loss
- "익절" = take profit
- "돌파" = cross above (breakout)
- "이탈" = cross below (breakdown)
- "과매수/과매도" = overbought/oversold (typically RSI > 70 / RSI < 30)

Common English terms:
- "Golden cross" / "death cross"
- "Cross above" / "cross below"
- "Stop loss" / "take profit" / "trailing stop"

Never invent numbers the user didn't specify. If the user says "moving average" without a period, ASK. Do not default to a period unless it's a well-known named pattern (e.g., "golden cross" without periods commonly means 50/200 SMA — you may assume this default and MENTION your assumption in the strategy name).

Never emit a strategy with zero buy conditions.
Never emit a strategy with zero exit rules (no sell conditions AND no stop_loss AND no take_profit).
```

### Few-Shot Examples

Include these in the system prompt as examples:

**Example 1 (Korean, complete):** User: "삼성전자 20일 이평선이 60일 이평선을 상향돌파할 때 사고, 하향돌파할 때 팔아. 5% 손절도 걸어줘." Action: `create_strategy` with:

* name: "20/60 골든크로스 + 5% 손절"
* buy: SMA(20) cross_above SMA(60)
* sell: SMA(20) cross_below SMA(60)
* stop_loss_pct: 0.05

**Example 2 (English, ambiguous):** User: "Buy Apple when it's oversold and sell when it recovers." Action: `ask_clarification` with:

* questions: ["What indicator defines 'oversold'? Common options are RSI (e.g., RSI < 30) or price % below moving average.", "What defines 'recovery' — a specific RSI level like 50, or crossing back above a moving average?"]

**Example 3 (Korean, mixed):** User: "RSI가 30 밑으로 갔다가 다시 30 위로 올라올 때 사고, 10% 오르거나 3% 내리면 팔아" Action: `create_strategy` with:

* name: "RSI 30 반등 매수, 10%/-3% 청산"
* buy: RSI(14) cross_above 30 (interpret "밑으로 갔다가 다시 위로" as cross_above)
* take_profit_pct: 0.10
* stop_loss_pct: 0.03

## The Manual Strategy Builder

**This is a mandatory Phase 1 feature with equal weight to the AI Builder.** It is not a
fallback, not an "advanced" mode, and not a power-user escape hatch. The non-negotiables
below govern any part of this spec that might understate it.

### Non-Negotiables

1. **Route parity.** `/build` opens with a segmented control at the top of the page. The
   two modes are visually equal in size, weight, and hierarchy. Neither is labeled
   "advanced" or "power user". Default mode is `ai` for first-time visitors; returning
   visitors get their persisted mode from localStorage.
2. **Every file under `frontend/src/components/builder/manual/` ships** — see Project
   Structure. None may be dropped or merged away in a later edit.
3. **All 5 presets are implemented**, each loading a complete, valid `Strategy` object
   into the form on click. No preset chip is a placeholder.
4. **Round-trip verification is a mandatory development-order step, before PDF work
   begins**: a strategy built in Manual mode and the semantically equivalent strategy
   built via AI mode must produce byte-identical `BacktestResult` objects when run on the
   same ticker and date range.
5. **State preservation across mode switches.** AI → Manual carries the currently-visible
   strategy (from the Preview Card) into the form. Manual → AI preserves the current form
   state as JSON in Zustand so the user can come back without losing work. Neither switch
   triggers a page reload.
6. **Save endpoint parity.** Both modes call the identical `POST /api/strategies` with the
   same payload shape. Saved strategies do not record which mode produced them — a
   strategy is a strategy regardless of authoring path.

### Placement

Same route as AI builder (`/build`), with a segmented control at the top: Active mode stored in URL query param (`?mode=ai` or `?mode=manual`) and persisted in localStorage. Default: `ai`.

### UI Layout (Manual Mode) — top to bottom

1. **Header inputs**: ticker + market picker, backtest date range (same as AI mode)
2. **Strategy name input** — free text, required
3. **Buy Conditions section** — title "매수 조건 (모두 만족)", list of condition rows, `[+ 조건 추가]` button. Empty state shows one row pre-filled with SMA(20) cross_above SMA(60).
4. **Sell Conditions section** — same structure; optional if stop_loss or take_profit is set
5. **Exit rules section** — Stop loss %, Take profit %, Max holding days (all optional)
6. **Position sizing section** — radio: `[전액 / 고정 금액 / 자본 비율]`, conditional numeric input for the latter two
7. **Advanced (collapsed by default)** — allow_reentry_same_day, cooldown_days_after_exit
8. **Sticky action bar** — `[미리보기]` `[백테스트 실행]` `[저장]`

### Condition Row Component

Structure: `[Left dropdown] [Operator dropdown] [Right selector]`

* **Left dropdown**: indicator kind (SMA / EMA / RSI / MACD Line / MACD Signal / Bollinger Upper/Lower/Mid / Close / Open / High / Low / Volume). Show inline parameter inputs based on selection (period for SMA/EMA/RSI, fast/slow/signal for MACD, period/std for Bollinger).
* **Operator dropdown**: `>`, `<`, `>=`, `<=`, `==`, `cross_above`, `cross_below`. Filter available operators by combination: `cross_above`/`cross_below` require the **left** side to be a time series, since crossing is a property of the moving side. A constant on the right is valid and common (`RSI(14) cross_above 30`).
* **Right selector**: toggle between "지표" and "값" — indicator dropdown OR number input.

Inline validation on blur:

* SMA/EMA period 2–500, RSI period 2–100
* Both sides referencing same indicator with same params → error
* `cross_above/cross_below` with a constant on the left → error

### Preset Chips (above Buy Conditions section)

Horizontal chip row of 5 presets that pre-fill the entire form. Store as static JSON on the frontend.

1. **골든크로스 (50/200)**: Buy SMA(50) cross_above SMA(200), Sell SMA(50) cross_below SMA(200)
2. **RSI 반등**: Buy RSI(14) cross_above 30, Sell RSI(14) cross_above 70
3. **볼린저 하단 매수**: Buy Close cross_below Bollinger Lower(20, 2), Sell Close cross_above Bollinger Mid(20, 2), stop_loss 5%
4. **무한매수법 v1** (simplified): Buy Close < SMA(20), take_profit 10%, stop_loss 20%, max_holding_days 40
5. **듀얼 모멘텀 (단일종목판)**: Buy Close > SMA(200) AND Close > Close[offset=252], Sell Close < SMA(200)
   * The second buy condition is the spec's original `(Close / Close[-252]) > 1` restated
     as a direct comparison — identical for positive prices, and expressible in
     `Condition` without a division operator. It relies on the `offset` param added to
     `IndicatorRef` (see Data Models).

### Interoperability with AI Mode

* After AI parses a strategy, "수동으로 편집" button on the Preview Card switches to Manual Mode with the strategy pre-loaded
* Save button in either mode → same `POST /api/strategies` endpoint
* Run Backtest in either mode → same `POST /api/backtest/run` endpoint
* Preview Card is a shared component used by both modes

## PDF Backtest Report

### Tech Stack (Non-Negotiable)

* **matplotlib** (Agg backend) for chart generation → PNG bytes at 200 DPI
* **ReportLab** (Platypus flowables) for PDF layout — automatic multi-page

Do NOT use WeasyPrint, wkhtmltopdf, or Playwright PDF generation. They require cairo/pango/chromium native deps that break Fly.io Docker builds. Pure Python only.

### Korean Font Handling — Critical

Bundle NanumGothic in `backend/app/reports/fonts/`:

* `NanumGothic-Regular.ttf`
* `NanumGothic-Bold.ttf`

At module load in `pdf_report.py`:

```python
import matplotlib
matplotlib.use('Agg')
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from matplotlib import font_manager
import matplotlib.pyplot as plt

FONT_DIR = 'app/reports/fonts'
pdfmetrics.registerFont(TTFont('NanumGothic', f'{FONT_DIR}/NanumGothic-Regular.ttf'))
pdfmetrics.registerFont(TTFont('NanumGothic-Bold', f'{FONT_DIR}/NanumGothic-Bold.ttf'))
font_manager.fontManager.addfont(f'{FONT_DIR}/NanumGothic-Regular.ttf')
plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False  # critical: prevents minus sign rendering as tofu
```

Use `'NanumGothic'` and `'NanumGothic-Bold'` as fontName in every ReportLab style. Do not fall back to Helvetica for any user-facing string.

### Report Structure

A4 portrait, 20mm margins, target 4–6 pages.

**Page 1 — Cover / Summary**

* Top-right: app logo/name + generation timestamp (small)
* Title: strategy name (24pt bold)
* Subtitle: ticker name + code (e.g., "삼성전자 (005930.KS)")
* Backtest period: e.g., "2020-01-01 ~ 2024-12-31 (5년)"
* Initial capital: e.g., "10,000,000원"
* Big metrics block (2 columns × 4 rows, each metric large):
  * 총수익률 (Total Return)
  * 연복리수익률 (CAGR)
  * 최대낙폭 (MDD)
  * 샤프비율 (Sharpe)
  * Sortino Ratio
  * 승률 (Win Rate)
  * 거래 횟수
  * 평균 보유일
* Bottom: buy-and-hold comparison line ("동일 기간 단순 매수 후 보유: +XX% (CAGR YY%)")

**Page 2 — Equity Curve**

* Full-width matplotlib chart, ~500px tall
* Two lines: strategy value (bold, primary color) + buy-and-hold value (thin, gray)
* Legend, light gridlines, Korean-formatted date axis
* Y-axis: portfolio value with thousand separators
* Below: 1-paragraph interpretation ("전략이 단순 매수 후 보유 대비 X% 초과 수익…")

**Page 3 — Drawdown Chart + Monthly Returns Heatmap**

* Top half: drawdown chart (filled area, all negative, Y-axis in %)
* Bottom half: monthly returns heatmap. Rows = years, cols = months 1–12, cell = monthly return %. Red for negative, green for positive, intensity by magnitude. YTD column on the right.

**Page 4+ — Trade Log**

* Columns: `#`, `매수일`, `매수가`, `매도일`, `매도가`, `보유일`, `손익`, `수익률`, `청산사유`
* Alternate row shading
* If > 30 trades, paginate with header row repeated
* Last page: summary totals row

**Last Page — Strategy Definition**

* Human-readable strategy schema:
  * 매수 조건 (bullet list)
  * 매도 조건 (bullet list)
  * 손절 / 익절 / 최대 보유일 (key-value)
  * 포지션 사이징
  * Original natural language description (verbatim, quoted block) — if AI-built
* Disclaimer at the very bottom: "이 리포트는 과거 데이터 기반 시뮬레이션이며, 미래 수익을 보장하지 않습니다. 실제 거래에는 슬리피지, 세금, 수수료 외에도 유동성·체결·감정적 요인이 영향을 미칩니다."

### Backend Implementation

Create `backend/app/reports/pdf_report.py`:

```python
def generate_backtest_pdf(
    result: BacktestResult,
    strategy: Strategy,
    ticker_meta: Ticker,
) -> bytes:
    """Generate a print-ready PDF report. Returns raw PDF bytes."""
```

Structure:

* `_setup_fonts()` — called once at module import
* `_build_cover_page(story, ...) -> list[Flowable]`
* `_build_equity_chart_image(equity_curve) -> BytesIO`  # matplotlib figure → PNG bytes
* `_build_drawdown_chart_image(equity_curve) -> BytesIO`
* `_build_monthly_returns_heatmap(equity_curve) -> BytesIO`
* `_build_trades_table(trades) -> Table`
* `_build_strategy_definition_page(strategy) -> list[Flowable]`

Also create `backend/app/reports/run_cache.py`:

* In-memory dict `{run_id: (BacktestResult, Strategy, Ticker, created_at)}`
* TTL 1 hour, evict on access when expired
* Phase 2 will migrate to Redis

### API Changes

#### Modified: `POST /api/backtest/run`

Add a `run_id` field of type string (ULID, 26 chars). Same request body as before, no
other changes.

```
POST /api/backtest/run
     body: { strategy: Strategy, params: BacktestParams }     # unchanged
     → BacktestResult + { run_id: str }                       # ULID, 26 chars
```

* The `run_id` is generated server-side, stored as the key into the in-memory run cache
  alongside `(BacktestResult, Strategy, Ticker, created_at)`
* No persistence to any `backtest_runs` DB table in Phase 1 — the cache is ephemeral,
  TTL 1 hour

#### New: `GET /api/backtest/report/{run_id}`

```
GET /api/backtest/report/{run_id}?disposition={attachment|inline}
     → application/pdf stream
```

* Query param: `disposition` = `attachment` (default) or `inline`
* Response: `application/pdf` stream
* Response headers:
  * `Content-Type: application/pdf`
  * `Content-Disposition: {disposition}; filename="{filename}"`
* Filename convention: `backtest_{strategy_slug}_{ticker}_{end_date}.pdf` — see the slug
  algorithm below.
  Example: `backtest_20_60_goldeunkeuloseu_5_sonjeol_005930_2024-12-31.pdf`
* Returns HTTP 404 with body `{"detail": "run_id expired or not found"}` on a cache miss
  (either TTL passed or process restarted)
* Generation is synchronous — the request blocks until the PDF bytes are ready. Expected
  latency 1–3 seconds. Do NOT introduce a job queue or async status polling in Phase 1.
* Do NOT re-run the backtest to generate the PDF. Read `BacktestResult` from `run_cache`
  only.

#### Slug generation algorithm

For the strategy-name portion of the PDF filename:

1. Convert to lowercase
2. Romanize Korean characters with the `hangul-romanize` package, `academic` rule —
   deterministic, no lookup table required
3. Replace any run of non-alphanumeric characters with a single underscore
4. Strip leading and trailing underscores
5. Truncate to 60 characters (cut at an underscore boundary if possible)
6. If the result is empty (e.g. an emoji-only strategy name), fall back to `strategy`

```python
import re
from hangul_romanize import Transliter
from hangul_romanize.rule import academic

_transliter = Transliter(academic)

def strategy_slug(name: str, cap: int = 60) -> str:
    s = _transliter.translit(name.lower())
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    if len(s) > cap:
        s = s[:cap]
        if "_" in s:
            s = s[: s.rindex("_")]
    return s or "strategy"
```

Verified outputs (`hangul-romanize==0.1.0`):

| Strategy name | Slug |
|---|---|
| `20/60 골든크로스 + 5% 손절` | `20_60_goldeunkeuloseu_5_sonjeol` |
| `RSI 반등` | `rsi_bandeung` |
| `볼린저 하단 매수` | `bollinjeo_hadan_maesu` |
| `무한매수법 v1` | `muhanmaesubeob_v1` |
| `듀얼 모멘텀 (단일종목판)` | `dyu_eol_momenteom_dan_iljongmogpan` |
| `🚀🚀` | `strategy` |

Two things to know about the `academic` rule, both confirmed against the installed
package rather than assumed:

* It transliterates ㄹ as **`l`** in every position, so 골든크로스 → `goldeunkeuloseu`.
  Strict Revised Romanization would give `goldeunkeuroseu` (ㄹ → `r` before a vowel).
  `academic` is the only ready-made rule the package ships; the difference is cosmetic
  for a filename, but do not "correct" the expected value in tests to the RR spelling.
* Step 1 lowercases before romanizing so that ASCII inside a mixed name is normalized;
  step 3 lowercases again because the transliterator preserves any uppercase ASCII it
  passes through (`RSI 반등` → `RSI bandeung`).

Do NOT attempt semantic translation (`골든크로스` → `golden_cross`). No reliable Python
library provides Korean-to-English domain translation for financial terms, and hardcoding
a lookup table would fail on any strategy name the developer didn't anticipate.

#### Report reachability from the library — intentional limitation

The library detail page **cannot** reach an old report. If a user opens a strategy from
the library and wants a PDF, they must click "Run Backtest" first (which produces a fresh
`run_id`), then "Download PDF Report".

Rationale: persisting every backtest result to disk creates a storage-growth problem this
early in the product's life, and users almost always want a fresh backtest anyway when
revisiting a saved strategy.

Add a small hint text on the library detail page:
`"PDF 리포트는 백테스트 실행 후 다운로드할 수 있습니다"`

#### Storage

No changes needed to the SQLite schema for this feature. The only new backend state is
the in-memory `run_cache` dict — Phase 2 will migrate this to Redis or a persistent
`backtest_runs` table when we want shareable report URLs.

## Backtest Engine (`app/backtest/engine.py`)

Deterministic, pandas-based. No lookahead bias.

> **Cross-asset signals (as built).** An `IndicatorRef` may carry a `ticker`/`market`, so a
> condition computes its indicator on a *different* asset than the one being traded — e.g.
> buy a KR stock when **US QQQ crosses its 10-day SMA**. The source asset is loaded
> natively (`engine.load_source_frames`), the indicator is computed on its own bars, then
> as-of aligned onto the traded asset's calendar by **market close time**
> (`indicators._align_to_primary`): KR closes ~01:30 ET, US 16:00 ET, so a US close on
> date D is only visible to a KR bar on D+1 — the alignment enforces exactly that, keeping
> the cross-market signal lookahead-safe. In the manual builder each indicator has an
> optional "타 종목(선택)" source field (market + ticker).

> **As built (Change 13):** a second engine, `app/backtest/quant_engine.py`, runs the
> **quant-portfolio family** (`QuantPortfolioStrategy`) — a factor-ranked,
> periodically-rebalanced multi-stock backtest served at `POST /api/backtest/quant`. It
> resolves a universe from the ticker metadata, computes the ranking **as of the prior
> trading day** and fills at the rebalance bar's open (lookahead-safe), full-turnover
> rebalances monthly/quarterly/…, marks to market daily, and reuses `compute_metrics` +
> the shared `BacktestResult`. **Price/momentum factors** (`momentum_*`, `rsi_14`,
> `dist_sma_200`, `dist_high_52w`) compute from cached OHLCV and work live; **fundamental
> factors** (`per`, `pbr`, `roe`, …) go through an injectable fundamentals loader — the
> live KR provider is currently blocked by a pykrx/KRX API incompatibility, so the engine
> is verified with a live **momentum** portfolio plus hermetic unit tests. Default engine
> path backtests the warmed (cached) slice of the universe to stay responsive. The
> single-stock family (`Strategy`, `family="single_stock"`) is unchanged.
>
> **Family-B wizard UI (13.1–13.3) — built.** The Manual builder now opens with a
> **family selector** (`FamilySelector.tsx`): 개별 종목 매매전략 keeps the existing single-stock
> form + ticker controls, while 퀀트 포트폴리오 swaps in `QuantBuilder.tsx` — a sectioned
> wizard for universe / filters / factor-ranking / portfolio / rebalance / backtest params,
> a 모멘텀 상위 20 preset, and results through the shared `BacktestResultView`. Live
> price/momentum factors are selectable; fundamental factors appear locked (🔒) with a note
> that they await a data source. Verified end-to-end (momentum portfolio on a KOSPI
> universe vs KS200). **Still pending:** a live fundamentals provider (13.5) and the quant
> PDF report (13.7).

### Core Function

```python
def run_backtest(strategy: Strategy, params: BacktestParams) -> BacktestResult:
    df = data_service.get_ohlcv(params.ticker, params.market, params.start_date, params.end_date)
    df = compute_indicators(df, strategy)
    signals = evaluate_conditions(df, strategy)
    return simulate(df, signals, strategy, params)
```

### Key Rules

* T+1 execution: signal generated at close of day D → order fills at open of day D+1. Never fill at same-day close.
* Position sizing:
  * `all_in`: use all available cash to buy shares (floor to integer)
  * `fixed_amount`: use `position_size_value` KRW/USD (floor to shares)
  * `percent_of_capital`: use `position_size_value * current_portfolio_value`
* Fees:
  * KR default: 0.015% buy + 0.015% sell + 0.23% sell tax (KOSDAQ default; 0.18% for KOSPI — infer from ticker prefix or ticker metadata)
  * US default: 0.025% buy + 0.025% sell + 0.00278% SEC fee on sells
  * Slippage: multiply buy price by (1 + slippage), sell price by (1 - slippage)
* Only one position at a time in Phase 1 (single-ticker backtests only)
* Cross_above/cross_below: detect actual crossover — value must be on opposite sides on consecutive days
* Indicator warmup: skip days where required indicators have NaN. Do NOT extrapolate.

### Indicator Computation

Implement each indicator as a pure function `pd.DataFrame → pd.Series`. Use `ta` package if convenient, or write directly with pandas rolling operations. Cache indicator computations within a single request using a `@lru_cache` on (ticker, kind, params).

### Metrics Computation

```python
def compute_metrics(equity_curve, trades, initial_capital, trading_days_per_year=252):
    total_return_pct = (equity_curve[-1] / initial_capital) - 1
    years = len(equity_curve) / trading_days_per_year
    cagr = (equity_curve[-1] / initial_capital) ** (1/years) - 1

    # MDD
    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peaks) / peaks
    mdd = drawdowns.min()

    # Sharpe (assume risk-free rate 0 for simplicity in Phase 1)
    daily_returns = np.diff(equity_curve) / equity_curve[:-1]
    sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(trading_days_per_year) if np.std(daily_returns) > 0 else 0

    # Sortino
    downside_returns = daily_returns[daily_returns < 0]
    sortino = np.mean(daily_returns) / np.std(downside_returns) * np.sqrt(trading_days_per_year) if len(downside_returns) > 0 else 0

    # Trade stats
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win_pct = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss_pct = np.mean([t.pnl_pct for t in losses]) if losses else 0
    profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else None
    avg_holding_days = np.mean([(t.sell_date - t.buy_date).days for t in trades]) if trades else 0

    return BacktestMetrics(...)
```

## API Endpoints

All routes prefixed with `/api`. FastAPI with standard error handling.

```
# Ticker / OHLCV
GET  /api/tickers/search?q={query}&market={KR|US}&limit=20
     → list[Ticker]  (searches ticker, name_en, name_ko AND aliases — see below)
GET  /api/tickers/{market}/{ticker}
     → Ticker
GET  /api/ohlcv/{market}/{ticker}?start={date}&end={date}
     → { candles: [{time, open, high, low, close, volume}] }  (Lightweight Charts format)

# AI strategy builder
POST /api/ai/parse-strategy
     body: { description: str, ticker: str, market: str, conversation_history: list }
     → { kind: "strategy", strategy: Strategy }
       | { kind: "clarification", questions: list[str], partial_strategy: Strategy | null }

# Backtest execution
POST /api/backtest/run
     body: { strategy: Strategy, params: BacktestParams }
     → BacktestResult + { run_id: str }   # ULID, 26 chars; keys the 1h run cache

GET  /api/backtest/report/{run_id}?disposition={attachment|inline}
     → application/pdf stream (see "PDF Backtest Report" for filename + 404 semantics)

# Strategy library (Phase 1: no auth, use a client-generated user_id stored in localStorage)
POST /api/strategies                          → save strategy, returns { id }
GET  /api/strategies?user_id={uid}            → list[Strategy]
GET  /api/strategies/{id}                     → Strategy
PATCH /api/strategies/{id}                    → update (name, description, conditions)
DELETE /api/strategies/{id}                   → delete
```

### Ticker Search Behaviour

* Match against `ticker`, `name_en`, `name_ko`, **and** `aliases` — case-insensitive,
  prefix + substring
* Sort results: exact ticker match → exact alias match → prefix match on name →
  substring match
* Group results in the UI dropdown by `kind`, in this order:
  Indices (label "지수") → ETFs (label "ETF") → Stocks (label "주식")
* If a user selects an index for backtesting, the Backtest Result view shows a small
  non-blocking banner:
  `"지수는 실제 거래가 불가능합니다. 실전 매매를 원하시면 지수 추종 ETF(예: SPY, 069500)를 사용하세요."`

## Frontend Pages

> **As built (Change 14):** the app now has an **18-tab navigation**. Desktop shows a
> horizontal, scrollable pill row of every tab (`src/config/navigation.tsx` +
> `App.tsx`); mobile shows a fixed bottom bar with the primary tabs (매수/차트/라이브러리)
> plus a **더보기** grid modal. **Tier 1** (매수, 차트, 라이브러리) is built; **관심목록**
> and all **Tier 3** tabs (보유, 은퇴, AI, 매크로, RS, Guru, 글로벌, 코인) render a styled
> `ComingSoon` placeholder with a Lucide icon, description, and a 알림 받기 mailto button;
> Four **Tier 2** tabs are functional end-to-end: **상관관계 / Correlation**
> (`POST /api/correlation/matrix` → returns-based correlation heatmap + annualised
> mean/vol/Sharpe) and **정적배분 / Static Allocation**
> (`POST /api/backtest/allocation/static` → `app/backtest/allocation_engine.py`,
> fixed-weight full-turnover rebalancing reusing the quant engine's calendar/cost/price
> machinery, with 60/40 · 영구 포트폴리오 · All Weather · 3-Fund · KR 60/40 presets, results
> rendered through the shared `BacktestResultView`), and **계절성 / Seasonality**
> (`GET /api/seasonality/{market}/{ticker}?since=` → month-by-year return heatmap with
> per-month mean/win-rate footer, day-of-week diverging bars, and a last-3-trading-days
> turn-of-month comparison), and **동적배분 / Dynamic Allocation**
> (`POST /api/backtest/allocation/dynamic` → `app/backtest/rotation_engine.py`, the
> rule-based rotation presets 듀얼 모멘텀 GEM · VAA-4 · LAA · GTAA-5, US-ETF only). The
> remaining Tier 2 tabs (히트맵, ETF, 스크리너) are placeholders — 히트맵 and ETF need a
> market-cap / AUM source we do not have, and 스크리너's value factors need the fundamentals
> pykrx can no longer fetch. Every one of the 18 routes resolves.
>
> **Shared engine core:** the three portfolio engines (quant, static, dynamic) run on one
> `app/backtest/portfolio_sim.py` — a full-turnover rebalance loop that reads targets from
> the **prior trading day's close** and fills at the next **open (D+1 / T+1, no
> lookahead)**, marks to market daily, and holds the benchmark flat until it has data.
> Each engine supplies only a `target_fn`.
>
> **Cross-market (US+KR) portfolios — supported.** `app/backtest/market_panel.py` builds
> base-currency panels for tickers spanning both markets: each leg is converted via
> `fx_service` (USD↔KRW, lazy-cached), closes are indexed on the **union** calendar and
> forward-filled (correct daily MTM even on the other market's holiday), and rebalances
> happen only on the **intersection** (days both markets trade, so every leg can execute).
> The D+1 discipline stays lookahead-safe automatically: a prior trading date's close
> (even a US 16:00 ET close) precedes the next date's earliest open (KR 09:00 KST ≈ 3h
> later), so a **US-signal → KR-trade** strategy is a genuine D+1. 정적배분 now takes a
> per-holding market (mixed → KRW base, KS200 benchmark), and 동적배분 adds the
> `qqq_trend_kr` preset (US QQQ 10-month trend → KR-listed TIGER 나스닥100 / KR bond).
> Single-market backtests keep their original code path unchanged.
>
> **Bug fixed along the way:** `data_service.ensure_cached` previously only checked that a
> Parquet file *existed*, so a ticker bootstrapped with a short window (e.g. `^GSPC` from
> 2021) silently returned a truncated series for older backtests — which quietly distorted
> benchmark lines. It is now coverage-aware: passing `start=` re-fetches and widens the
> cached window when needed. Both portfolio engines also now hold the benchmark line flat
> at initial capital before it has data, instead of mirroring the portfolio.

`/` — Redirect to `/build`

### `/chart/:ticker` — Chart Page

Layout:

* Top bar: ticker name, price, change (styled like the reference screenshot)
* Right side: SMA/EMA period toggles (5, 10, 20, 50, 60, 120, 200 for SMA; 9, 21, 65 for EMA)
* Timeframe buttons: 1W, 1M, 3M, 1Y (default), 3Y, 5Y, All
* Main: TradingView Lightweight Charts (candlestick + volume histogram)
* Below chart: "Download CSV" button (client-side CSV generation from loaded data)

Implementation notes:

* Use the official `lightweight-charts` React ref pattern; do NOT use the `lightweight-charts-react-wrapper` package (it lags versions)
* Compute SMA/EMA client-side in a Web Worker if lookback is > 3 years — otherwise on main thread is fine
* Show the TradingView attribution ("TV" mark) — required by license

### `/build` — AI Strategy Builder

Layout (top to bottom):

* Ticker + market picker (searchable dropdown backed by `/api/tickers/search`)
* Backtest period range (start / end date pickers, default: last 5 years)
* Large textarea (min 3 rows, expands to 8) for natural language
* Primary button: "전략 만들기 / Build Strategy"

After first submission:

* Conversation thread appears above the input (user messages right-aligned, AI messages left-aligned)
* If clarification: show questions inline with input for the answer directly below
* If strategy complete: show Strategy Preview Card (see below) and hide the input

Strategy Preview Card:

* Human-readable summary rendered from the parsed `Strategy` object
* Editable — clicking a field opens an inline edit dropdown (e.g., changing "20-day SMA" to "10-day SMA")
* Buttons: `[Run Backtest]` `[Edit as Form]` `[Save to Library]` `[Discard]`

After Run Backtest:

* Show `BacktestResultView` component:
  * Equity curve (Recharts): user strategy line + buy-and-hold overlay
  * Metrics grid (2 columns × 4 rows on desktop): Total Return, CAGR, MDD, Sharpe, Sortino, Win Rate, # Trades, Avg Hold Days
  * Trade log table below: sortable by any column, click a row to highlight that trade on the equity curve

### `/library` — Strategy Library

* List view of saved strategies (one card per strategy)
* Each card: name, description snippet, created_at, tags (auto-generated from indicators used)
* Click → strategy detail page with:
  * Full strategy definition
  * Recent backtest results (last 5 runs on different tickers/periods)
  * "Re-run on different ticker" button
  * "Delete" / "Duplicate" / "Export JSON"

## Visual Design System

The Phase 1 UI must reach professional-app quality, not prototype quality. Default browser
controls, unstyled forms, and generic Tailwind boilerplate are not acceptable output.
Enforce this design system across all pages.

### Colors

Define as CSS variables in `frontend/src/index.css`.

| Token | Value |
|---|---|
| Background | `#FAFAF7` (warm off-white) |
| Surface (cards) | `#FFFFFF` |
| Text primary | `#0F172A` |
| Text secondary | `#64748B` |
| Text tertiary | `#94A3B8` |
| Border | `#E2E8F0` |
| Border subtle | `#F1F5F9` |
| Positive | `#10B981` / bg `#ECFDF5` |
| Negative | `#EF4444` / bg `#FEF2F2` |
| Accent (primary interactive) | `#F59E0B` (amber, matches the reference's favorite-star hue) |

Chart SMA colors: 5=`#94A3B8`, 10=`#94A3B8`, 20=`#F97316`, 50=`#3B82F6`, 60=`#94A3B8`,
120=`#94A3B8`, 200=`#A855F7`

Chart EMA colors: 9=`#3B82F6`, 21=`#94A3B8`, 65=`#94A3B8`

### Typography

* Font stack: `'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`
* Bundle Pretendard Variable via the `pretendard` npm package or `@fontsource-variable/pretendard`
* All numeric displays (prices, metrics, table cells) get `font-variant-numeric: tabular-nums` — non-negotiable, otherwise number columns will not align vertically
* Sizes: display 32px/700, h1 24px/700, h2 20px/600, body 14px/500, small 12px/500

### Component Styling

* Cards: `bg-white rounded-xl shadow-sm border border-slate-100 p-6` — never a hard 1px border alone
* Buttons: primary uses accent color, secondary is `bg-slate-100 hover:bg-slate-200`, ghost is transparent with hover
* Inputs: consistent 40px height, `rounded-lg`, focus ring in accent color
* All icons come from `lucide-react` at consistent sizes (`h-4 w-4` inline, `h-5 w-5` in buttons, `h-6 w-6` for page-level actions)
* No emoji as UI icons — always Lucide

### Chart Page Layout

Match the reference screenshot exactly.

**Top block (above the chart)**

* Line 1: company name (24px bold) + ticker pill badge (small bordered chip with the code)
* Line 2: price (32px bold) + arrow icon + change amount and percent (colored green/red)
* Right side of the top block: three round icon buttons — star (favorite), compare tool, bell (alerts) — in that left-to-right order
* Far right of the same row: `[⬇ Download CSV]` outline button + `[Linear | Log]` segmented control. The Log toggle actually works — pass `mode: 'logarithmic'` to the Lightweight Charts price scale.

**Middle block (between top and chart)**

* Left group: `일봉 ▾` dropdown (Phase 1 has only 일봉 as an option, but the dropdown exists) + timeframe segmented control `1W 1M 3M 1Y 3Y 5Y All` (active tab in accent color)
* Right group: three rows of indicator toggles
  * Row 1: `SMA` label + 7 toggle chips (`5 10 20 50 60 120 200`), each chip showing a filled colored dot matching the plotted color when active
  * Row 2: `EMA` label + 3 toggle chips (`9 21 65`)
  * Row 3: `커스텀` label + inline inputs `[SMA 기간] [+SMA]` and `[EMA 기간] [+EMA]`

**Chart panel**

* Candlestick main pane (75% height) + volume histogram pane (25% height, no overlap)
* Green/red volume bars matching the candle colors
* Right price scale, bottom time scale in Korean format (`2022년`, `5월`, `9월`, `2023년`…)
* Gridlines at `#F1F5F9` opacity
* TradingView attribution mark bottom-left corner (do not remove — license requirement)

### AI Builder Polish

* Chat thread rendered as message bubbles: user messages right-aligned with subtle amber background; AI messages left-aligned with white background and a small AI avatar
* Streaming text (character-by-character) for AI responses using the Anthropic SDK's streaming mode
* Clarification questions render as both readable prose AND clickable quick-answer chips where applicable (e.g. "이동평균 종류는?" with chips `SMA` `EMA`)
* Strategy Preview Card styled as a "receipt": clear section headers (매수 조건 / 매도 조건 / 청산 규칙 / 포지션 사이징), inline-editable fields with a subtle underline hover state, primary action `[백테스트 실행]` in accent color at the bottom-right

### Manual Builder Polish

* Each Condition Row is a light card (`bg-slate-50 rounded-lg p-3`) with a drag handle icon on the left (drag-to-reorder is Phase 1.5 — the handle can be visible but non-functional in Phase 1)
* Between condition rows within the same section, render a small centered `AND` label so users understand the boolean semantics
* Preset chips are rounded pills with a subtle hover lift shadow effect
* Sticky action bar at the bottom of the viewport (not the page) so buttons stay reachable while scrolling long condition lists

### Backtest Result Polish

* Hero metric block at the top: `총수익률` in 40px bold with color (green/red), followed by a horizontal row of secondary metrics (CAGR, MDD, Sharpe, Win Rate) each in its own small card
* Equity curve uses Recharts with the app's palette — strategy line in accent color (2px), buy-and-hold line in slate-400 (1.5px dashed)
* Trade log table: sticky header, alternating row shading (`even:bg-slate-50`), PnL column colored, right-align all numeric columns, `tabular-nums` on numeric cells
* Prominent `[⬇ PDF 리포트 다운로드]` button in the top-right of the result view, with a secondary `[미리보기]` link next to it

### Navigation

* Desktop: minimal top nav bar with the app name/logo left, links `차트 / 전략 만들기 / 라이브러리` right. No 18-tab bottom bar; disabled "coming soon" tabs look unprofessional at MVP scale.
* Mobile (`sm:` breakpoint): bottom tab bar with 3 icons + labels for the 3 pages.

### Empty and Loading States

* Every list view (library, chart search, trade log) has a styled empty state with a Lucide icon and a one-line prompt. No blank white screens.
* Loading uses skeleton loaders (grey pulsing blocks) matching the layout of the final content — no spinners in the middle of empty pages.

## Project Structure

```
backtest-app/
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes.tsx
│   │   ├── pages/
│   │   │   ├── ChartPage.tsx
│   │   │   ├── BuildPage.tsx
│   │   │   ├── LibraryPage.tsx
│   │   │   └── StrategyDetailPage.tsx
│   │   ├── components/
│   │   │   ├── chart/
│   │   │   │   ├── PriceChart.tsx        # Lightweight Charts wrapper
│   │   │   │   ├── IndicatorToggles.tsx
│   │   │   │   └── TimeframeSelector.tsx
│   │   │   ├── builder/
│   │   │   │   ├── ModeToggle.tsx            # ai | manual segmented control
│   │   │   │   ├── ConversationThread.tsx
│   │   │   │   ├── StrategyPreviewCard.tsx   # shared by both modes
│   │   │   │   ├── TickerPicker.tsx
│   │   │   │   └── manual/                   # all 7 files are mandatory
│   │   │   │       ├── ManualBuilder.tsx     # container
│   │   │   │       ├── ConditionRow.tsx
│   │   │   │       ├── ConditionList.tsx
│   │   │   │       ├── IndicatorPicker.tsx
│   │   │   │       ├── ExitRulesForm.tsx
│   │   │   │       ├── PositionSizingForm.tsx
│   │   │   │       └── PresetChips.tsx
│   │   │   ├── backtest/
│   │   │   │   ├── EquityCurve.tsx
│   │   │   │   ├── MetricsGrid.tsx
│   │   │   │   ├── TradeLogTable.tsx
│   │   │   │   └── DownloadReportButton.tsx  # GET the PDF for a run_id
│   │   │   └── ui/                       # shadcn-style primitives
│   │   ├── schemas/
│   │   │   ├── strategy.ts               # Zod mirror of Pydantic
│   │   │   └── backtest.ts
│   │   ├── api/
│   │   │   └── client.ts                 # fetch wrappers with TanStack Query hooks
│   │   ├── stores/
│   │   │   └── builder.ts                # Zustand session state (incl. ai|manual mode)
│   │   └── utils/
│   │       ├── indicators.ts             # client-side SMA/EMA for chart overlays
│   │       ├── presets.ts                # the 5 preset chips, static JSON
│   │       └── csv.ts
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app entry
│   │   ├── routers/
│   │   │   ├── tickers.py
│   │   │   ├── ohlcv.py
│   │   │   ├── ai.py                     # /api/ai/parse-strategy
│   │   │   ├── backtest.py               # /run and /report/{run_id} share the prefix
│   │   │   └── strategies.py
│   │   ├── schemas.py                    # Pydantic models
│   │   ├── services/
│   │   │   ├── data_service.py           # Parquet read via DuckDB
│   │   │   ├── ai_parser.py              # Anthropic client, tool defs, system prompt
│   │   │   └── strategy_service.py       # SQLite CRUD
│   │   ├── backtest/
│   │   │   ├── engine.py                 # run_backtest entry
│   │   │   ├── indicators.py             # SMA, EMA, RSI, MACD, Bollinger
│   │   │   ├── evaluator.py              # evaluate conditions per bar
│   │   │   └── metrics.py                # CAGR, MDD, Sharpe, etc.
│   │   ├── reports/
│   │   │   ├── pdf_report.py             # matplotlib charts + ReportLab layout
│   │   │   ├── run_cache.py              # {run_id: (result, strategy, ticker, ts)}, 1h TTL
│   │   │   └── fonts/
│   │   │       ├── NanumGothic-Regular.ttf
│   │   │       └── NanumGothic-Bold.ttf
│   │   ├── data_providers/
│   │   │   ├── base.py                   # DataProvider ABC
│   │   │   ├── fdr_provider.py
│   │   │   ├── pykrx_provider.py
│   │   │   └── yfinance_provider.py
│   │   └── db.py                         # SQLite connection
│   ├── scripts/
│   │   ├── bootstrap_data.py             # initial 15-year download
│   │   └── nightly_refresh.py            # incremental update
│   ├── data/                             # gitignored
│   │   ├── ohlcv/{market}/{ticker}.parquet
│   │   └── tickers/{market}.parquet
│   ├── strategies.db                     # SQLite
│   ├── pyproject.toml
│   └── fly.toml
├── README.md
└── .env.example                          # GEMINI_API_KEY, etc.
```

## Development Order

Do this in strict order. Each step must be verifiable before moving on.

1. Backend data layer: implement `DataProvider` interface + FDR provider. Write `bootstrap_data.py` to download 5 tickers (AAPL, MSFT, 005930, 000660, KO) for 5 years. Verify Parquet files land in the right structure.
2. Backend OHLCV API: `/api/ohlcv/{market}/{ticker}` returning Lightweight Charts-formatted candles. Test with curl.
3. Frontend chart page: bare TradingView Lightweight Charts loading data from step 2. No indicators yet. Verify AAPL renders.
4. Add indicator overlays on the chart page (SMA 20/50/200 client-side computation).
5. Backend backtest engine: implement `run_backtest` with a hardcoded strategy (SMA 20/60 crossover on AAPL 2020-2024). Verify it produces a plausible equity curve. Match numbers against a manual calculation for at least one round trip.
6. Backend `/api/backtest/run` endpoint. Test with curl using a JSON strategy.
7. Frontend backtest result view: equity curve + metrics + trade log. Wire it to run a hardcoded strategy first.
8. AI parser (backend): implement `/api/ai/parse-strategy` with the two-tool Claude call. Test with 5 hand-written natural language descriptions in both Korean and English. Verify tool selection is correct for ambiguous vs complete cases.
9. AI parser (frontend): conversation thread UI. Wire to the parser endpoint. Verify multi-turn clarification works.
10. Strategy Preview Card + Edit: rendering the parsed strategy in human-readable form and allowing inline edits. Build it as a shared component from the start — the manual builder reuses it as-is.
11. Manual Strategy Builder: mode toggle on `/build` (URL param + localStorage), condition row component with operator filtering and inline validation, exit rules, position sizing, preset chips. Verify each of the 5 presets produces a `Strategy` object that validates against the same schema the AI parser emits, and that "수동으로 편집" round-trips an AI-parsed strategy without losing fields.
12. **Mode round-trip verification (mandatory gate — PDF work does not start until this passes).** Build 골든크로스 50/200 in Manual mode; build the semantically equivalent strategy through the AI parser. Run both on the same ticker and date range and assert the two `BacktestResult` objects are byte-identical. Also verify AI → Manual carries the previewed strategy into the form, Manual → AI preserves form state in Zustand, and neither switch reloads the page.
13. End-to-end flow: natural language → parse → preview → backtest → save. Verify the happy path in both modes.
14. Strategy library page: list, detail, delete, duplicate.
15. PDF report backend: `generate_backtest_pdf` + `run_cache`, and thread `run_id` through `POST /api/backtest/run`. Verify Korean renders with no tofu boxes (labels, strategy name, and the minus sign on negative metrics), a 40-trade log paginates with a repeated header, and the whole report builds in a container with no system fonts installed.
16. PDF report frontend: download button on the result view, wired to the `run_id` from the last run. Add the hint text on the library detail page explaining that a PDF needs a fresh run first. Verify a 404 on an expired `run_id` surfaces as a readable message, not a broken download.
17. Deploy backend to Fly.io with mounted volume for `data/`. Confirm nightly refresh cron works and the bundled fonts ship in the image.
18. Deploy frontend to Cloudflare Pages with `VITE_API_BASE_URL` pointing to the Fly.io backend.

## Validation Tests (Write These)

Before shipping Phase 1, verify:

### Backtest Correctness

* Buy-and-hold on AAPL 2015-01-01 → 2024-12-31 with $10,000 initial capital produces total return within 0.5% of a manually calculated Yahoo Finance number
* SMA 20/60 crossover strategy on 005930 (Samsung) for 2020-2024 produces trade log with defensible entry/exit dates (spot-check 3 trades against the actual chart)
* Fee application: a single round-trip trade at $100 buy / $110 sell with 0.025% fees and 0.1% slippage returns $9.75 pnl, not $10 (accounting for costs)
* Stop loss trigger: if price drops 5% intraday, ensure sell fires at next day's open, not same-day low

### AI Parser Robustness

Test each of these inputs and verify the correct tool is called:

Should return `create_strategy`:

1. "20일 이평선이 60일 이평선을 상향돌파할 때 사고, 하향돌파할 때 팔아"
2. "RSI 30 미만에서 사고, RSI 70 이상에서 팔아"
3. "Buy when the price crosses above the 200-day SMA. Sell when it drops 10% from entry."
4. "볼린저밴드 하단 터치하면 사고, 5% 익절 3% 손절"

Should return `ask_clarification`:

1. "저평가일 때 사서 오르면 팔아" (what defines "저평가"?)
2. "골든크로스에서 사고 데드크로스에서 팔아" (which two MAs? — assume 50/200 with a note, OR ask)
3. "Buy AAPL when it looks good" (no signal defined)
4. "이평선 돌파할 때 사" (which MA? no exit rule)

## Environment Variables

```
# Backend  (as built — Change 11 migrated the LLM provider to Google Gemini)
GEMINI_API_KEY=AQ...            # or an AI Studio "AIza..." key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
GEMINI_USE_FALLBACK_MODEL=false
DATA_DIR=/data
DATABASE_URL=sqlite:///strategies.db
CORS_ORIGINS=https://<your-domain>.pages.dev,http://localhost:5173

# Frontend
VITE_API_BASE_URL=https://<your-backend>.fly.dev
```

## What to Avoid

* Do NOT use a heavy backtesting library (`backtesting.py`, `vectorbt`, `bt`) for Phase 1. Write the engine yourself in ~300 lines of pandas. This gives full control over the AI-parsed strategy schema without shoehorning it into a library's DSL.
* Do NOT implement authentication in Phase 1. Use a client-side generated user_id (ULID stored in localStorage) as the strategy owner.
* Do NOT support multi-ticker strategies in Phase 1. One ticker per strategy. Portfolio allocation is Phase 2.
* Do NOT support intraday / minute bars in Phase 1. Daily bars only.
* Do NOT paginate the equity curve or trade log via server-side. All results are small enough to send in one response.
* Do NOT try to make the parser handle every possible strategy expression. If the LLM can't parse it after 3 clarification rounds, tell the user to rephrase and provide a link to a syntax reference page.
* Do NOT bundle indicators into the OHLCV API response. Indicators are computed on demand — either client-side (for chart overlays) or backend (for backtest evaluation).
* Do NOT skip the T+1 execution rule. Lookahead bias is the #1 way backtest engines produce fake alpha.

## Success Criteria for Phase 1

A user can:

1. Open the app, land on `/build`
2. Type "삼성전자 20일 이평선이 60일 이평선을 상향돌파할 때 사고, 5% 손절" in Korean
3. See the parsed strategy preview within 5 seconds
4. Click "Run Backtest" and see a chart + metrics within 3 seconds
5. Save the strategy and find it in the library on next visit
6. Switch to Manual Editor mode, pick a preset (골든크로스 50/200), tweak periods to 20/60, run backtest — get identical results to step 3–4.
7. Re-run the same strategy on a different ticker without retyping

That's the whole Phase 1 loop. Build exactly that.
