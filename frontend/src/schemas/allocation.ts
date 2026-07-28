/** Zod mirror of the Change 15 allocation models in backend/app/schemas.py. */
import { z } from 'zod'

import { marketSchema } from './strategy'

export const allocationAlgorithmSchema = z.enum([
  'static', 'risk_parity', 'min_variance', 'max_sharpe', 'vol_target', 'erc', 'hrp',
])
export type AllocationAlgorithm = z.infer<typeof allocationAlgorithmSchema>

export const weightSchemeSchema = z.enum([
  'equal', 'custom', 'inverse_vol', 'inverse_corr', 'market_cap',
])
export type WeightScheme = z.infer<typeof weightSchemeSchema>

export const rebalancePeriodSchema = z.enum([
  'none', 'daily', 'weekly', 'monthly', 'quarterly', 'semi_annually', 'annually',
])
export type AllocationRebalancePeriod = z.infer<typeof rebalancePeriodSchema>

export const momentumIndicatorSchema = z.enum([
  'absolute_momentum', 'sma_cross', '13612w', 'sortino',
])

export const assetSlotSchema = z.object({
  ticker: z.string(),
  market: marketSchema.default('KR'),
  target_weight_pct: z.number().nullable().optional(),
})
export type AssetSlot = z.infer<typeof assetSlotSchema>

export const momentumTimingSchema = z.object({
  indicator: momentumIndicatorSchema.default('absolute_momentum'),
  lookback_months: z.number().int().default(12),
  mode: z.enum(['per_asset', 'canary']).default('per_asset'),
  canary_ticker: z.string().nullable().optional(),
  canary_market: marketSchema.default('US'),
  safe_haven_ticker: z.string(),
  safe_haven_market: marketSchema.default('KR'),
  threshold: z.number().default(0),
})
export type MomentumTiming = z.infer<typeof momentumTimingSchema>

export const reentryTimingSchema = z.object({
  rule: z.enum(['immediate', 'delayed', 'consecutive']).default('immediate'),
  n: z.number().int().default(1),
  max_off_months: z.number().int().nullable().optional(),
})
export type ReentryTiming = z.infer<typeof reentryTimingSchema>

export const allocationStrategySchema = z.object({
  family: z.literal('allocation').default('allocation'),
  id: z.string().optional(),
  name: z.string().default('자산배분 전략'),
  description: z.string().default(''),
  language: z.enum(['ko', 'en']).default('ko'),
  algorithm: allocationAlgorithmSchema.default('static'),
  assets: z.array(assetSlotSchema).min(1),
  weight_scheme: weightSchemeSchema.nullable().default('equal'),
  rebalance_period: rebalancePeriodSchema.default('annually'),
  rebalance_band_pct: z.number().default(0),
  apply_fx: z.boolean().default(true),
  lookback_days_for_estimation: z.number().int().default(252),
  vol_target_annual: z.number().nullable().optional(),
  momentum_timing: momentumTimingSchema.nullable().optional(),
  reentry_timing: reentryTimingSchema.nullable().optional(),
})
export type AllocationStrategy = z.infer<typeof allocationStrategySchema>

export const portfolioHoldingSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  market: marketSchema,
  weight: z.number(),
  price: z.number(),
  target_shares: z.number(),
  target_krw: z.number(),
})

export const extractPortfolioResponseSchema = z.object({
  as_of_date: z.string(),
  holdings: z.array(portfolioHoldingSchema),
  cash_remainder: z.number(),
  total_krw: z.number(),
})
export type ExtractPortfolioResponse = z.infer<typeof extractPortfolioResponseSchema>

/** Algorithms that compute their own weights (weight scheme locked in the UI). */
export const ALGORITHM_CONTROLS_WEIGHTS: AllocationAlgorithm[] = [
  'risk_parity', 'min_variance', 'max_sharpe', 'vol_target', 'erc', 'hrp',
]
