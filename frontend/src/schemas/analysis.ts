import { z } from 'zod'

export const tickerStatSchema = z.object({
  ticker: z.string(),
  mean: z.number(),
  std: z.number(),
  sharpe: z.number(),
})

export const correlationResponseSchema = z.object({
  tickers: z.array(z.string()),
  matrix: z.array(z.array(z.number())),
  stats: z.array(tickerStatSchema),
})

export type CorrelationResponse = z.infer<typeof correlationResponseSchema>

export const seasonalityResponseSchema = z.object({
  ticker: z.string(),
  market: z.enum(['KR', 'US']),
  name: z.string(),
  start_year: z.number(),
  end_year: z.number(),
  monthly: z.array(
    z.object({ year: z.number(), month: z.number(), return_pct: z.number() }),
  ),
  month_stats: z.array(
    z.object({
      month: z.number(),
      mean: z.number(),
      positive_rate: z.number(),
      best: z.number(),
      worst: z.number(),
      count: z.number(),
    }),
  ),
  weekday_stats: z.array(
    z.object({
      weekday: z.number(),
      mean: z.number(),
      positive_rate: z.number(),
      count: z.number(),
    }),
  ),
  turn_of_month: z.object({
    turn_mean: z.number(),
    rest_mean: z.number(),
    turn_count: z.number(),
    rest_count: z.number(),
  }),
})

export type SeasonalityResponse = z.infer<typeof seasonalityResponseSchema>
