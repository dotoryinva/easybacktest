import { z } from 'zod'

import { marketSchema } from './strategy'

export const snapshotRowSchema = z.object({
  ticker: z.string(),
  market: marketSchema,
  name_ko: z.string().nullable().optional(),
  name_en: z.string(),
  kind: z.enum(['stock', 'index', 'etf']),
  as_of: z.string(),
  price: z.number(),
  ret_1w: z.number().nullable().optional(),
  ret_1m: z.number().nullable().optional(),
  ret_3m: z.number().nullable().optional(),
  ret_6m: z.number().nullable().optional(),
  ret_12m: z.number().nullable().optional(),
  ret_ytd: z.number().nullable().optional(),
  vol_ann: z.number().nullable().optional(),
  rsi_14: z.number().nullable().optional(),
  dist_sma200: z.number().nullable().optional(),
  dist_high52w: z.number().nullable().optional(),
})
export type SnapshotRow = z.infer<typeof snapshotRowSchema>

export const marketSnapshotResponseSchema = z.object({
  market: marketSchema,
  rows: z.array(snapshotRowSchema),
})
export type MarketSnapshotResponse = z.infer<typeof marketSnapshotResponseSchema>

export const quotesResponseSchema = z.object({
  rows: z.array(snapshotRowSchema),
})
export type QuotesResponse = z.infer<typeof quotesResponseSchema>

/** Metric keys that carry a trailing-return percentage (used by heatmap + screener). */
export type ReturnKey = 'ret_1w' | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m' | 'ret_ytd'
