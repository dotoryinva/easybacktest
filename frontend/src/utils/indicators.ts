/**
 * Client-side SMA / EMA for chart overlays.
 *
 * These mirror `backend/app/backtest/indicators.py` — notably EMA is seeded with the
 * first `period`-bar SMA, the same convention TradingView uses. If you change one side,
 * change the other, or the overlay will drift from the backtest's signals.
 *
 * Chart overlays are computed on the *unadjusted* close shown on the chart; the backtest
 * uses adjusted prices. The two can differ around splits — that is intentional.
 */

export type LinePoint = { time: string; value: number }

export function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (period < 1 || values.length < period) return out

  let sum = 0
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

export function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null)
  if (period < 1 || values.length < period) return out

  let seed = 0
  for (let i = 0; i < period; i += 1) seed += values[i]
  let prev = seed / period
  out[period - 1] = prev

  const alpha = 2 / (period + 1)
  for (let i = period; i < values.length; i += 1) {
    prev = alpha * values[i] + (1 - alpha) * prev
    out[i] = prev
  }
  return out
}

/** Zip an indicator series with dates, dropping the warm-up nulls. */
export function toLineData(
  times: string[],
  series: (number | null)[],
): LinePoint[] {
  const points: LinePoint[] = []
  for (let i = 0; i < series.length; i += 1) {
    const value = series[i]
    if (value != null && Number.isFinite(value)) points.push({ time: times[i], value })
  }
  return points
}

export const SMA_PERIODS = [5, 10, 20, 50, 60, 120, 200] as const
export const EMA_PERIODS = [9, 21, 65] as const

/**
 * Overlay colors — PROJECT_SPEC.md → "Visual Design System".
 * Mirrored as CSS variables (--sma-20 etc.) in index.css.
 */
export const SMA_COLORS: Record<number, string> = {
  5: '#94A3B8',
  10: '#94A3B8',
  20: '#F97316',
  50: '#3B82F6',
  60: '#94A3B8',
  120: '#94A3B8',
  200: '#A855F7',
}

export const EMA_COLORS: Record<number, string> = {
  9: '#3B82F6',
  21: '#94A3B8',
  65: '#94A3B8',
}

/** Fallback for user-added custom periods (step 4's 커스텀 row). */
export const CUSTOM_COLOR = '#64748B'
