import type { Market } from '../schemas/strategy'

export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatMoney(value: number, market: Market): string {
  if (!Number.isFinite(value)) return '—'
  return market === 'KR'
    ? `₩${Math.round(value).toLocaleString('ko-KR')}`
    : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** KRW has no sub-unit in practice; USD keeps two decimals. */
export function formatPrice(value: number, market: Market): string {
  return market === 'KR'
    ? Math.round(value).toLocaleString('ko-KR')
    : value.toFixed(2)
}

export function toneClass(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value === 0) return 'text-slate-300'
  return value > 0 ? 'text-up' : 'text-down'
}

export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

export function yearsAgo(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return isoDate(d)
}

export const EXIT_REASON_LABELS: Record<string, string> = {
  sell_signal: 'Sell signal',
  stop_loss: 'Stop loss',
  take_profit: 'Take profit',
  max_holding_days: 'Max holding',
  end_of_period: 'End of period',
}
