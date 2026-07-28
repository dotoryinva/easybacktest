import { z } from 'zod'

export const retirementBandSchema = z.object({
  age: z.number(),
  p10: z.number(),
  p25: z.number(),
  p50: z.number(),
  p75: z.number(),
  p90: z.number(),
})

export const retirementResponseSchema = z.object({
  bands: z.array(retirementBandSchema),
  success_probability: z.number(),
  median_ending_balance: z.number(),
  depletion_age_p50: z.number().nullable().optional(),
  safe_annual_spending: z.number(),
})
export type RetirementResponse = z.infer<typeof retirementResponseSchema>

export type RetirementInput = {
  current_age: number
  retirement_age: number
  end_age: number
  current_savings: number
  annual_contribution: number
  annual_spending: number
  expected_return: number
  volatility: number
  inflation: number
  num_simulations: number
}
