/** Fetch wrappers + TanStack Query hooks. Every response is validated with Zod. */
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import {
  backtestResultSchema,
  ohlcvResponseSchema,
  runSummarySchema,
  type BacktestParams,
  type BacktestResult,
} from '../schemas/backtest'
import {
  correlationResponseSchema,
  seasonalityResponseSchema,
  type CorrelationResponse,
} from '../schemas/analysis'
import {
  extractPortfolioResponseSchema,
  type AllocationStrategy,
  type ExtractPortfolioResponse,
} from '../schemas/allocation'
import { marketSnapshotResponseSchema, quotesResponseSchema } from '../schemas/market'
import {
  retirementResponseSchema,
  type RetirementInput,
  type RetirementResponse,
} from '../schemas/retirement'
import {
  parseStrategyResponseSchema,
  savedStrategySchema,
  strategySchema,
  tickerSchema,
  type ChatMessage,
  type Market,
  type ParseStrategyResponse,
  type Strategy,
} from '../schemas/strategy'

const BASE = (import.meta.env.VITE_API_BASE_URL ?? 'https://easybacktest-backend.onrender.com').replace(/\/$/, '')

/** Phase 1 has no auth: a ULID-ish id in localStorage owns the strategies. */
const USER_ID_KEY = 'easybacktest.user_id'

export function getUserId(): string {
  let id = localStorage.getItem(USER_ID_KEY)
  if (!id) {
    id = `u_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
    localStorage.setItem(USER_ID_KEY, id)
  }
  return id
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': getUserId(),
        ...(init?.headers ?? {}),
      },
    })
  } catch (cause) {
    console.error(`[api] network failure ${init?.method ?? 'GET'} ${path}`, cause)
    throw new ApiError(
      `Cannot reach the API at ${BASE}. Is the backend running?`,
      0,
    )
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: any) => d.msg).join('; ')
    } catch {
      /* non-JSON error body — keep the status line */
    }
    console.error(`[api] ${response.status} ${init?.method ?? 'GET'} ${path}: ${detail}`)
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  const parsed = schema.safeParse(await response.json())
  if (!parsed.success) {
    throw new ApiError(
      `Unexpected response shape from ${path}: ${parsed.error.issues[0]?.message ?? ''}`,
      response.status,
    )
  }
  return parsed.data
}

// --------------------------------------------------------------------------- //
// Tickers & OHLCV
// --------------------------------------------------------------------------- //

export function useTickerSearch(query: string, market: Market | null) {
  return useQuery({
    queryKey: ['tickers', 'search', query, market],
    enabled: query.trim().length > 0,
    staleTime: 5 * 60_000,
    queryFn: () => {
      const params = new URLSearchParams({ q: query, limit: '30' })
      if (market) params.set('market', market)
      return request(`/api/tickers/search?${params}`, z.array(tickerSchema))
    },
  })
}

export function useTicker(market: Market, ticker: string) {
  return useQuery({
    queryKey: ['tickers', market, ticker],
    staleTime: 60 * 60_000,
    queryFn: () => request(`/api/tickers/${market}/${ticker}`, tickerSchema),
  })
}

export function useOhlcv(market: Market, ticker: string, start?: string, end?: string) {
  return useQuery({
    queryKey: ['ohlcv', market, ticker, start, end],
    staleTime: 30 * 60_000,
    queryFn: () => {
      const params = new URLSearchParams()
      if (start) params.set('start', start)
      if (end) params.set('end', end)
      const qs = params.toString()
      return request(`/api/ohlcv/${market}/${ticker}${qs ? `?${qs}` : ''}`, ohlcvResponseSchema)
    },
  })
}

// --------------------------------------------------------------------------- //
// AI parser
// --------------------------------------------------------------------------- //

export type ParseStrategyInput = {
  description: string
  ticker: string
  market: Market
  conversation_history: ChatMessage[]
  /** When set, the parser revises this strategy instead of creating a new one. */
  current_strategy?: Strategy | null
}

export function useParseStrategy() {
  return useMutation<ParseStrategyResponse, ApiError, ParseStrategyInput>({
    mutationFn: (body) =>
      request('/api/ai/parse-strategy', parseStrategyResponseSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

// --------------------------------------------------------------------------- //
// Correlation (Tier 2)
// --------------------------------------------------------------------------- //

export type CorrelationInput = {
  tickers: { ticker: string; market: Market }[]
  start_date: string
  end_date: string
  frequency: 'daily' | 'weekly' | 'monthly'
}

export function useCorrelationMatrix() {
  return useMutation<CorrelationResponse, ApiError, CorrelationInput>({
    mutationFn: (body) =>
      request('/api/correlation/matrix', correlationResponseSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export function useSeasonality(market: Market, ticker: string, since?: number) {
  return useQuery({
    queryKey: ['seasonality', market, ticker, since],
    enabled: Boolean(ticker),
    staleTime: 60 * 60_000,
    queryFn: () =>
      request(
        `/api/seasonality/${market}/${encodeURIComponent(ticker)}${since ? `?since=${since}` : ''}`,
        seasonalityResponseSchema,
      ),
  })
}

// --------------------------------------------------------------------------- //
// Backtest
// --------------------------------------------------------------------------- //

export function useRunBacktest() {
  return useMutation<BacktestResult, ApiError, { strategy: Strategy; params: BacktestParams }>({
    mutationFn: (body) =>
      request('/api/backtest/run', backtestResultSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export type RebalanceFrequency = 'monthly' | 'quarterly' | 'semiannual' | 'annual'

export type StaticAllocationInput = {
  name: string
  market: Market
  holdings: { ticker: string; weight: number; market?: Market }[]
  start_date: string
  end_date: string
  initial_capital: number
  rebalance: RebalanceFrequency
  benchmark?: string | null
}

export function useStaticAllocation() {
  return useMutation<BacktestResult, ApiError, StaticAllocationInput>({
    mutationFn: (body) =>
      request('/api/backtest/allocation/static', backtestResultSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

// --- Quant portfolio (Family B) ---

export type QuantFactor =
  | 'per' | 'pbr' | 'psr' | 'earnings_yield' | 'book_yield' | 'dividend_yield' | 'roe' | 'roa'
  | 'momentum_1m' | 'momentum_3m' | 'momentum_6m' | 'momentum_12m' | 'momentum_12m_1m'
  | 'rsi_14' | 'dist_sma_200' | 'dist_high_52w'
  | 'market_cap'

export type FilterOperator = '>' | '<' | '>=' | '<=' | '==' | 'between' | 'top_pct' | 'bottom_pct'

export type QuantPortfolioStrategy = {
  name: string
  description?: string
  language?: 'ko' | 'en'
  universe: {
    market: Market
    boards: string[]
    exclude_etf: boolean
    exclude_preferred: boolean
    market_cap_min?: number | null
  }
  filters: { factor: QuantFactor; op: FilterOperator; value?: number | null; value2?: number | null }[]
  ranking: { factor: QuantFactor; direction: 'asc' | 'desc'; weight: number }[]
  portfolio: { num_holdings: number; weighting: 'equal' | 'rank' | 'market_cap'; max_position_pct: number }
  rebalance: { frequency: RebalanceFrequency }
}

export type QuantBacktestParams = {
  market: Market
  start_date: string
  end_date: string
  initial_capital: number
  benchmark?: string | null
}

export function useQuantBacktest() {
  return useMutation<
    BacktestResult,
    ApiError,
    { strategy: QuantPortfolioStrategy; params: QuantBacktestParams }
  >({
    mutationFn: (body) =>
      request('/api/backtest/quant', backtestResultSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

// --- Unified allocation (Change 15) ---

export type AllocationParams = {
  start_date: string
  end_date: string
  initial_capital: number
  initial_capital_currency: 'KRW' | 'USD'
  benchmark?: string | null
}

export function useAllocationBacktest() {
  return useMutation<BacktestResult, ApiError, { strategy: AllocationStrategy; params: AllocationParams }>({
    mutationFn: (body) =>
      request('/api/backtest/allocation', backtestResultSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export function useExtractPortfolio() {
  return useMutation<
    ExtractPortfolioResponse,
    ApiError,
    { strategy: AllocationStrategy; capital: number }
  >({
    mutationFn: (body) =>
      request('/api/allocation/extract-portfolio', extractPortfolioResponseSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export type DynamicStrategyKind = 'dual_momentum' | 'vaa' | 'laa' | 'gtaa' | 'qqq_trend_kr'

export type DynamicAllocationInput = {
  strategy: DynamicStrategyKind
  start_date: string
  end_date: string
  initial_capital: number
  lookback_months?: number
  benchmark?: string | null
}

export function useDynamicAllocation() {
  return useMutation<BacktestResult, ApiError, DynamicAllocationInput>({
    mutationFn: (body) =>
      request('/api/backtest/allocation/dynamic', backtestResultSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

// --------------------------------------------------------------------------- //
// QuantStats HTML report (Change 16)
// --------------------------------------------------------------------------- //

export type ReportFormat = 'html' | 'pdf'

/**
 * Ask the backend to render a full QuantStats tearsheet from a finished backtest and
 * trigger a browser download in the requested format (HTML or PDF). Bypasses the Zod
 * `request` wrapper because the response is a binary/HTML blob, not JSON.
 */
export async function downloadBacktestReport(
  result: BacktestResult,
  format: ReportFormat = 'html',
): Promise<void> {
  const points = result.equity_curve
    .filter((p) => Number.isFinite(p.portfolio_value) && Number.isFinite(p.buy_hold_value))
    .map((p) => ({ date: p.date, strategy: p.portfolio_value, benchmark: p.buy_hold_value }))

  const title =
    result.strategy_name?.trim() ||
    `${result.params.market}-${result.params.ticker} 백테스트`

  let response: Response
  try {
    response = await fetch(`${BASE}/api/report/quantstats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
      body: JSON.stringify({ title, points, format }),
    })
  } catch {
    throw new ApiError(`Cannot reach the API at ${BASE}. Is the backend running?`, 0)
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new ApiError(detail, response.status)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${title}.${format}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

// --------------------------------------------------------------------------- //
// Market snapshot (Heatmap / ETF / Screener) + Retirement (Change 17)
// --------------------------------------------------------------------------- //

export function useMarketSnapshot(market: Market) {
  return useQuery({
    queryKey: ['market', 'snapshot', market],
    staleTime: 10 * 60_000,
    queryFn: () =>
      request(`/api/market/snapshot?market=${market}`, marketSnapshotResponseSchema),
  })
}

export function useRetirementSim() {
  return useMutation<RetirementResponse, ApiError, RetirementInput>({
    mutationFn: (body) =>
      request('/api/retirement/simulate', retirementResponseSchema, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

/** Metric quotes for an explicit list of tickers (the watchlist; mixed markets allowed). */
export function useWatchlistQuotes(items: { ticker: string; market: Market }[]) {
  const key = items.map((i) => `${i.market}:${i.ticker}`).sort().join(',')
  return useQuery({
    queryKey: ['market', 'quotes', key],
    enabled: items.length > 0,
    staleTime: 5 * 60_000,
    queryFn: () =>
      request('/api/market/quotes', quotesResponseSchema, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ ticker: i.ticker, market: i.market })),
        }),
      }),
  })
}

/** Parallel OHLCV fetches for the chart's compare overlay. Shares cache keys with useOhlcv. */
export function useOhlcvMany(items: { ticker: string; market: Market }[], start?: string) {
  return useQueries({
    queries: items.map(({ ticker, market }) => ({
      queryKey: ['ohlcv', market, ticker, start, undefined],
      staleTime: 30 * 60_000,
      queryFn: () =>
        request(
          `/api/ohlcv/${market}/${encodeURIComponent(ticker)}${start ? `?start=${start}` : ''}`,
          ohlcvResponseSchema,
        ),
    })),
  })
}

// --------------------------------------------------------------------------- //
// Strategy library
// --------------------------------------------------------------------------- //

export function useStrategies() {
  return useQuery({
    queryKey: ['strategies', getUserId()],
    queryFn: () =>
      request(
        `/api/strategies?user_id=${encodeURIComponent(getUserId())}`,
        z.array(savedStrategySchema),
      ),
  })
}

export function useStrategy(id: string | undefined) {
  return useQuery({
    queryKey: ['strategies', 'one', id],
    enabled: Boolean(id),
    queryFn: () => request(`/api/strategies/${id}`, savedStrategySchema),
  })
}

export function useStrategyRuns(id: string | undefined) {
  return useQuery({
    queryKey: ['strategies', 'runs', id],
    enabled: Boolean(id),
    queryFn: () => request(`/api/strategies/${id}/runs`, z.array(runSummarySchema)),
  })
}

export function useSaveStrategy() {
  const qc = useQueryClient()
  return useMutation<Strategy, ApiError, Strategy>({
    mutationFn: (strategy) =>
      request('/api/strategies', strategySchema, {
        method: 'POST',
        body: JSON.stringify({ user_id: getUserId(), strategy }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useUpdateStrategy() {
  const qc = useQueryClient()
  return useMutation<Strategy, ApiError, Strategy>({
    mutationFn: (strategy) =>
      request(`/api/strategies/${strategy.id}`, strategySchema, {
        method: 'PATCH',
        body: JSON.stringify({ user_id: getUserId(), strategy }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useDeleteStrategy() {
  const qc = useQueryClient()
  return useMutation<void, ApiError, string>({
    mutationFn: (id) =>
      request(
        `/api/strategies/${id}?user_id=${encodeURIComponent(getUserId())}`,
        z.void(),
        { method: 'DELETE' },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useDuplicateStrategy() {
  const qc = useQueryClient()
  return useMutation<Strategy, ApiError, string>({
    mutationFn: (id) =>
      request(
        `/api/strategies/${id}/duplicate?user_id=${encodeURIComponent(getUserId())}`,
        strategySchema,
        { method: 'POST' },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}
