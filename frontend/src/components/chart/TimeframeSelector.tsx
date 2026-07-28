export const TIMEFRAMES = ['1W', '1M', '3M', '1Y', '3Y', '5Y', 'All'] as const
export type Timeframe = (typeof TIMEFRAMES)[number]

/** Start date for a timeframe, or null for "All" (server returns everything cached). */
export function timeframeStart(timeframe: Timeframe): string | null {
  const now = new Date()
  switch (timeframe) {
    case '1W':
      now.setDate(now.getDate() - 7)
      break
    case '1M':
      now.setMonth(now.getMonth() - 1)
      break
    case '3M':
      now.setMonth(now.getMonth() - 3)
      break
    case '1Y':
      now.setFullYear(now.getFullYear() - 1)
      break
    case '3Y':
      now.setFullYear(now.getFullYear() - 3)
      break
    case '5Y':
      now.setFullYear(now.getFullYear() - 5)
      break
    case 'All':
      return null
  }
  return now.toISOString().slice(0, 10)
}

/**
 * Extra history to fetch so a long moving average is already warm at the left edge
 * of the visible window, instead of starting partway into the chart.
 */
export function warmupStart(start: string | null, maxPeriod: number): string | null {
  if (!start || maxPeriod <= 0) return start
  const d = new Date(start)
  d.setDate(d.getDate() - Math.ceil(maxPeriod * 1.6) - 10)
  return d.toISOString().slice(0, 10)
}

type Props = {
  value: Timeframe
  onChange: (value: Timeframe) => void
}

export function TimeframeSelector({ value, onChange }: Props) {
  return (
    <div className="segmented">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf}
          type="button"
          onClick={() => onChange(tf)}
          className={`segmented-item ${value === tf ? 'segmented-item-active' : ''}`}
        >
          {tf}
        </button>
      ))}
    </div>
  )
}
