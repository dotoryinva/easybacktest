/** Zod mirror of the backtest models in `backend/app/schemas.py`. */
import { z } from 'zod'
import { marketSchema, tickerKindSchema } from './strategy'

export const backtestParamsSchema = z.object({
  ticker: z.string(),
  market: marketSchema,
  start_date: z.string(),
  end_date: z.string(),
  initial_capital: z.number().positive(),
  fee_rate: z.number().nullable().optional(),
  sell_tax_rate: z.number().nullable().optional(),
  slippage: z.number().min(0).lt(1).default(0.001),
})
export type BacktestParams = z.infer<typeof backtestParamsSchema>

export const exitReasonSchema = z.enum([
  'sell_signal',
  'stop_loss',
  'take_profit',
  'max_holding_days',
  'end_of_period',
])
export type ExitReason = z.infer<typeof exitReasonSchema>

export const tradeSchema = z.object({
  buy_date: z.string(),
  buy_price: z.number(),
  sell_date: z.string(),
  sell_price: z.number(),
  shares: z.number().int(),
  pnl: z.number(),
  pnl_pct: z.number(),
  exit_reason: exitReasonSchema,
})
export type Trade = z.infer<typeof tradeSchema>

export const backtestMetricsSchema = z.object({
  total_return_pct: z.number(),
  cagr: z.number(),
  mdd: z.number(),
  sharpe_ratio: z.number(),
  sortino_ratio: z.number(),
  win_rate: z.number(),
  num_trades: z.number().int(),
  avg_holding_days: z.number(),
  avg_win_pct: z.number(),
  avg_loss_pct: z.number(),
  profit_factor: z.number().nullable(),
})
export type BacktestMetrics = z.infer<typeof backtestMetricsSchema>

export const equityPointSchema = z.object({
  date: z.string(),
  portfolio_value: z.number(),
  cash: z.number(),
  position_value: z.number(),
  buy_hold_value: z.number(),
})
export type EquityPoint = z.infer<typeof equityPointSchema>

export const backtestResultSchema = z.object({
  strategy_id: z.string().nullable().optional(),
  strategy_name: z.string().nullable().optional(),
  params: backtestParamsSchema,
  metrics: backtestMetricsSchema,
  equity_curve: z.array(equityPointSchema),
  trades: z.array(tradeSchema),
  ran_at: z.string(),
})
export type BacktestResult = z.infer<typeof backtestResultSchema>

export const candleSchema = z.object({
  time: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
})
export type Candle = z.infer<typeof candleSchema>

export const ohlcvResponseSchema = z.object({
  ticker: z.string(),
  market: marketSchema,
  name: z.string(),
  kind: tickerKindSchema.default('stock'),
  is_tradable: z.boolean().default(true),
  candles: z.array(candleSchema),
})
export type OHLCVResponse = z.infer<typeof ohlcvResponseSchema>

export const runSummarySchema = z.object({
  ticker: z.string(),
  market: marketSchema,
  params: backtestParamsSchema,
  metrics: backtestMetricsSchema,
  ran_at: z.string(),
})
export type RunSummary = z.infer<typeof runSummarySchema>
