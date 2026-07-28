import type { Market } from '../../schemas/strategy'

/** KR / US segmented control shared by the market-data pages. */
export function MarketToggle({
  value,
  onChange,
}: {
  value: Market
  onChange: (m: Market) => void
}) {
  return (
    <div className="segmented">
      {(['KR', 'US'] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={`segmented-item ${value === m ? 'segmented-item-active' : ''}`}
        >
          {m}
        </button>
      ))}
    </div>
  )
}

/**
 * Diverging heat colour for a return **in percent** (e.g. -5.47 → red, +8 → green).
 * Intensity saturates at ±`cap` percent so a single outlier doesn't wash the grid out.
 */
export function heatColor(pct: number | null | undefined, cap = 10): string {
  if (pct == null || !Number.isFinite(pct)) return 'rgb(241, 245, 249)' // slate-100
  const a = Math.min(Math.abs(pct) / cap, 1)
  // green (16,185,129) for gains, red (239,68,68) for losses, fading to near-white at 0.
  const [r, g, b] = pct >= 0 ? [16, 185, 129] : [239, 68, 68]
  const mix = 0.12 + a * 0.88
  return `rgba(${r}, ${g}, ${b}, ${mix})`
}

/** Text colour that stays legible on top of a heat tile of the given return. */
export function heatText(pct: number | null | undefined, cap = 10): string {
  if (pct == null || !Number.isFinite(pct)) return 'rgb(100,116,139)'
  return Math.min(Math.abs(pct) / cap, 1) > 0.45 ? '#ffffff' : 'rgb(15,23,42)'
}
