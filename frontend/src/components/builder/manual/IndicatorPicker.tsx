/**
 * Indicator kind dropdown plus the inline parameter inputs that kind needs.
 * Used for both sides of a condition row.
 */
import type { IndicatorKind, IndicatorRef, Market } from '../../../schemas/strategy'

type ParamField = {
  key: 'period' | 'fast' | 'slow' | 'signal' | 'std' | 'offset'
  label: string
  step: number
  min: number
  max: number
  width: string
}

/** Ordered exactly as the spec lists them in the Left dropdown. */
export const INDICATOR_OPTIONS: { value: IndicatorKind; label: string }[] = [
  { value: 'SMA', label: 'SMA' },
  { value: 'EMA', label: 'EMA' },
  { value: 'RSI', label: 'RSI' },
  { value: 'MACD_LINE', label: 'MACD Line' },
  { value: 'MACD_SIGNAL', label: 'MACD Signal' },
  { value: 'BOLLINGER_UPPER', label: 'Bollinger Upper' },
  { value: 'BOLLINGER_LOWER', label: 'Bollinger Lower' },
  { value: 'BOLLINGER_MID', label: 'Bollinger Mid' },
  { value: 'PRICE_CLOSE', label: 'Close' },
  { value: 'PRICE_OPEN', label: 'Open' },
  { value: 'PRICE_HIGH', label: 'High' },
  { value: 'PRICE_LOW', label: 'Low' },
  { value: 'VOLUME', label: 'Volume' },
]

/** True for kinds that produce a time series (i.e. anything but a literal number). */
export function isSeries(kind: IndicatorKind): boolean {
  return kind !== 'CONSTANT'
}

export function paramFields(kind: IndicatorKind): ParamField[] {
  if (kind === 'SMA' || kind === 'EMA')
    return [{ key: 'period', label: '기간', step: 1, min: 2, max: 500, width: 'w-20' }]
  if (kind === 'RSI')
    return [{ key: 'period', label: '기간', step: 1, min: 2, max: 100, width: 'w-20' }]
  if (kind === 'MACD_LINE' || kind === 'MACD_SIGNAL')
    return [
      { key: 'fast', label: 'Fast', step: 1, min: 1, max: 200, width: 'w-16' },
      { key: 'slow', label: 'Slow', step: 1, min: 1, max: 400, width: 'w-16' },
      { key: 'signal', label: 'Signal', step: 1, min: 1, max: 200, width: 'w-16' },
    ]
  if (kind.startsWith('BOLLINGER'))
    return [
      { key: 'period', label: '기간', step: 1, min: 2, max: 500, width: 'w-20' },
      { key: 'std', label: '표준편차', step: 0.1, min: 0.1, max: 10, width: 'w-20' },
    ]
  if (kind.startsWith('PRICE_') || kind === 'VOLUME')
    return [{ key: 'offset', label: '지연(봉)', step: 1, min: 0, max: 2520, width: 'w-20' }]
  return []
}

/** Starting params when the user switches an indicator's kind. */
export function defaultParams(kind: IndicatorKind): Record<string, number> {
  if (kind === 'SMA' || kind === 'EMA') return { period: 20 }
  if (kind === 'RSI') return { period: 14 }
  if (kind === 'MACD_LINE' || kind === 'MACD_SIGNAL') return { fast: 12, slow: 26, signal: 9 }
  if (kind.startsWith('BOLLINGER')) return { period: 20, std: 2 }
  if (kind === 'CONSTANT') return { value: 30 }
  return {}
}

type Props = {
  value: IndicatorRef
  onChange: (next: IndicatorRef) => void
  onBlur?: () => void
  /** Compact mode hides the tiny field labels — used on the right-hand side. */
  compact?: boolean
}

export function IndicatorPicker({ value, onChange, onBlur, compact }: Props) {
  const fields = paramFields(value.kind)

  return (
    <div className="flex flex-wrap items-end gap-1.5">
      <select
        aria-label="지표"
        className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs font-medium text-slate-900 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
        value={value.kind}
        onChange={(e) => {
          const kind = e.target.value as IndicatorKind
          onChange({ kind, params: defaultParams(kind) })
        }}
      >
        {INDICATOR_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      {fields.map((field) => {
        const current = (value.params as Record<string, number | undefined>)[field.key]
        // `offset` is optional and usually 0 — don't force a value into the box.
        const shown = current ?? (field.key === 'offset' ? '' : '')
        return (
          <label key={field.key} className="flex flex-col gap-0.5">
            {!compact && (
              <span className="text-[10px] font-medium text-slate-400">{field.label}</span>
            )}
            <input
              type="number"
              aria-label={`${value.kind} ${field.label}`}
              className={`h-9 ${field.width} rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-900 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20`}
              step={field.step}
              min={field.min}
              max={field.max}
              placeholder={field.key === 'offset' ? '0' : ''}
              value={shown}
              onBlur={onBlur}
              onChange={(e) => {
                const raw = e.target.value
                const params = { ...value.params } as Record<string, number | undefined>
                if (raw === '') delete params[field.key]
                else params[field.key] = Number(raw)
                onChange({ ...value, params: params as IndicatorRef['params'] })
              }}
            />
          </label>
        )
      })}

      {/* Cross-asset source: compute this indicator on another asset (e.g. QQQ). Empty ⇒
          the traded ticker. */}
      {isSeries(value.kind) && (
        <div className="flex items-end gap-1">
          {!compact && (
            <span className="sr-only">신호 종목</span>
          )}
          <select
            aria-label="신호 종목 시장"
            className="h-9 rounded-lg border border-slate-200 bg-white px-1.5 text-xs text-slate-900 focus:border-accent focus:outline-none"
            value={value.market ?? 'US'}
            onChange={(e) =>
              onChange({ ...value, market: e.target.value as Market })
            }
            disabled={!value.ticker}
          >
            <option value="KR">KR</option>
            <option value="US">US</option>
          </select>
          <input
            aria-label="신호 종목 (다른 자산)"
            className="h-9 w-24 rounded-lg border border-slate-200 bg-white px-2 text-xs font-mono text-slate-900 placeholder:font-sans placeholder:text-slate-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            placeholder="타 종목(선택)"
            value={value.ticker ?? ''}
            onBlur={onBlur}
            onChange={(e) => {
              const t = e.target.value.trim().toUpperCase()
              onChange({
                ...value,
                ticker: t || null,
                market: t ? value.market ?? 'US' : null,
              })
            }}
          />
        </div>
      )}
    </div>
  )
}
