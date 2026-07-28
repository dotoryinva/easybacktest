/**
 * Zod mirror of `backend/app/schemas.py`.
 *
 * Hand-maintained: when a Pydantic model changes, change it here too. Keep field
 * names and Literal members byte-identical to the Python side.
 */
import { z } from 'zod'

export const marketSchema = z.enum(['KR', 'US'])
export type Market = z.infer<typeof marketSchema>

export const indicatorKindSchema = z.enum([
  'SMA',
  'EMA',
  'RSI',
  'MACD_LINE',
  'MACD_SIGNAL',
  'BOLLINGER_UPPER',
  'BOLLINGER_LOWER',
  'BOLLINGER_MID',
  'PRICE_CLOSE',
  'PRICE_OPEN',
  'PRICE_HIGH',
  'PRICE_LOW',
  'VOLUME',
  'CONSTANT',
])
export type IndicatorKind = z.infer<typeof indicatorKindSchema>

export const operatorSchema = z.enum([
  '>',
  '<',
  '>=',
  '<=',
  '==',
  'cross_above',
  'cross_below',
])
export type Operator = z.infer<typeof operatorSchema>

export const indicatorParamsSchema = z.object({
  period: z.number().int().positive().optional(),
  fast: z.number().int().positive().optional(),
  slow: z.number().int().positive().optional(),
  signal: z.number().int().positive().optional(),
  std: z.number().positive().optional(),
  value: z.number().optional(),
  /** Price/volume series only: bars to look back. offset=252 is "the close a year ago". */
  offset: z.number().int().min(0).optional(),
})
export type IndicatorParams = z.infer<typeof indicatorParamsSchema>

export const indicatorRefSchema = z.object({
  kind: indicatorKindSchema,
  params: indicatorParamsSchema.default({}),
  // Cross-asset signal: compute this indicator on another asset (e.g. QQQ) instead of the
  // traded ticker. null/undefined ⇒ the backtest ticker.
  ticker: z.string().nullable().optional(),
  market: marketSchema.nullable().optional(),
})
export type IndicatorRef = z.infer<typeof indicatorRefSchema>

export const conditionSchema = z.object({
  left: indicatorRefSchema,
  operator: operatorSchema,
  right: indicatorRefSchema,
})
export type Condition = z.infer<typeof conditionSchema>

export const positionSizingSchema = z.enum([
  'all_in',
  'fixed_amount',
  'percent_of_capital',
])
export type PositionSizing = z.infer<typeof positionSizingSchema>

export const tickerKindSchema = z.enum(['stock', 'index', 'etf'])
export type TickerKind = z.infer<typeof tickerKindSchema>

export const tickerSchema = z.object({
  ticker: z.string(),
  name_en: z.string(),
  name_ko: z.string().nullable().optional(),
  market: marketSchema,
  sector: z.string().nullable().optional(),
  industry: z.string().nullable().optional(),
  kind: tickerKindSchema.default('stock'),
  is_tradable: z.boolean().default(true),
  aliases: z.string().default(''),
})
export type Ticker = z.infer<typeof tickerSchema>

export const strategySchema = z.object({
  id: z.string(),
  name: z.string().min(1),
  description: z.string(),
  language: z.enum(['ko', 'en']),

  buy_conditions: z.array(conditionSchema).min(1),
  sell_conditions: z.array(conditionSchema).default([]),
  stop_loss_pct: z.number().positive().lt(1).nullable().optional(),
  take_profit_pct: z.number().positive().nullable().optional(),
  max_holding_days: z.number().int().positive().nullable().optional(),

  position_sizing: positionSizingSchema.default('all_in'),
  position_size_value: z.number().positive().nullable().optional(),

  allow_reentry_same_day: z.boolean().default(false),
  cooldown_days_after_exit: z.number().int().min(0).default(0),

  created_at: z.string(),
})
export type Strategy = z.infer<typeof strategySchema>

export const savedStrategySchema = z.object({
  strategy: strategySchema,
  user_id: z.string(),
  updated_at: z.string(),
})
export type SavedStrategy = z.infer<typeof savedStrategySchema>

/** Mirrors the discriminated response of POST /api/ai/parse-strategy. */
export const parseStrategyResponseSchema = z.union([
  z.object({ kind: z.literal('strategy'), strategy: strategySchema }),
  z.object({
    kind: z.literal('clarification'),
    questions: z.array(z.string()),
    partial_strategy: z.unknown().nullable().optional(),
  }),
])
export type ParseStrategyResponse = z.infer<typeof parseStrategyResponseSchema>

export const parseStrategyRequestSchema = z.object({
  description: z.string(),
  ticker: z.string(),
  market: marketSchema,
  conversation_history: z.array(z.object({
    role: z.enum(['user', 'assistant']),
    content: z.string(),
  })),
  current_strategy: strategySchema.nullable().optional(),
})

export type ChatMessage = { role: 'user' | 'assistant'; content: string }

/** Client-side validity check used before enabling "Run Backtest". */
export function strategyIsRunnable(strategy: Strategy): string | null {
  if (strategy.buy_conditions.length === 0) return 'Add at least one buy condition.'
  const hasExit =
    strategy.sell_conditions.length > 0 ||
    strategy.stop_loss_pct != null ||
    strategy.take_profit_pct != null ||
    strategy.max_holding_days != null
  if (!hasExit) return 'Add an exit rule: a sell condition, stop loss, or take profit.'
  if (strategy.position_sizing !== 'all_in' && strategy.position_size_value == null)
    return 'Position sizing needs a value.'
  return null
}
