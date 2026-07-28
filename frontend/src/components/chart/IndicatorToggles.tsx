import { Plus, X } from 'lucide-react'
import { useState } from 'react'

import {
  CUSTOM_COLOR,
  EMA_COLORS,
  EMA_PERIODS,
  SMA_COLORS,
  SMA_PERIODS,
} from '../../utils/indicators'

type Props = {
  smaPeriods: number[]
  emaPeriods: number[]
  customSma: number[]
  customEma: number[]
  onToggleSma: (period: number) => void
  onToggleEma: (period: number) => void
  onAddCustom: (kind: 'sma' | 'ema', period: number) => string | null
  onRemoveCustom: (kind: 'sma' | 'ema', period: number) => void
}

function Toggle({
  period,
  active,
  color,
  onClick,
}: {
  period: number
  active: boolean
  color: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors ${
        active
          ? 'border-slate-300 bg-slate-50 text-slate-900'
          : 'border-slate-200 bg-white text-slate-400 hover:text-slate-700'
      }`}
    >
      {/* Filled dot in the plotted color when active, hollow when off. */}
      <span
        className="h-2 w-2 rounded-full border"
        style={{
          backgroundColor: active ? color : 'transparent',
          borderColor: active ? color : '#CBD5E1',
        }}
      />
      {period}
    </button>
  )
}

/** An added custom period — always plotted, removable via the X. */
function CustomChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="flex items-center gap-1 rounded-md border border-slate-300 bg-slate-50 py-1 pl-2 pr-1 text-xs font-medium text-slate-900">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: CUSTOM_COLOR }}
      />
      {label}
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
        aria-label={`${label} 제거`}
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}

/** `[기간] [+SMA]` input pair in the 커스텀 row. */
function CustomAdder({
  kind,
  onAdd,
}: {
  kind: 'sma' | 'ema'
  onAdd: (kind: 'sma' | 'ema', period: number) => string | null
}) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    if (!value.trim()) return
    const message = onAdd(kind, Number(value))
    setError(message)
    if (!message) setValue('')
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-1">
        <input
          type="number"
          inputMode="numeric"
          min={2}
          max={500}
          value={value}
          placeholder={kind === 'sma' ? 'SMA 기간' : 'EMA 기간'}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          className="h-7 w-24 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-900 placeholder:text-slate-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
        />
        <button
          type="button"
          onClick={submit}
          className="flex h-7 items-center gap-0.5 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          <Plus className="h-3 w-3" />
          {kind.toUpperCase()}
        </button>
      </div>
      {error && (
        <p className="absolute left-0 top-8 whitespace-nowrap text-[11px] text-negative">
          {error}
        </p>
      )}
    </div>
  )
}

export function IndicatorToggles({
  smaPeriods,
  emaPeriods,
  customSma,
  customEma,
  onToggleSma,
  onToggleEma,
  onAddCustom,
  onRemoveCustom,
}: Props) {
  const rowLabel = 'w-12 shrink-0 text-xs font-semibold text-slate-500'

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className={rowLabel}>SMA</span>
        <div className="flex flex-wrap gap-1.5">
          {SMA_PERIODS.map((p) => (
            <Toggle
              key={p}
              period={p}
              active={smaPeriods.includes(p)}
              color={SMA_COLORS[p]}
              onClick={() => onToggleSma(p)}
            />
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className={rowLabel}>EMA</span>
        <div className="flex flex-wrap gap-1.5">
          {EMA_PERIODS.map((p) => (
            <Toggle
              key={p}
              period={p}
              active={emaPeriods.includes(p)}
              color={EMA_COLORS[p]}
              onClick={() => onToggleEma(p)}
            />
          ))}
        </div>
      </div>

      <div className="flex items-start gap-2">
        <span className={`${rowLabel} pt-1.5`}>커스텀</span>
        <div className="flex flex-wrap items-center gap-2">
          <CustomAdder kind="sma" onAdd={onAddCustom} />
          <CustomAdder kind="ema" onAdd={onAddCustom} />
          {customSma.map((p) => (
            <CustomChip
              key={`sma-${p}`}
              label={`SMA ${p}`}
              onRemove={() => onRemoveCustom('sma', p)}
            />
          ))}
          {customEma.map((p) => (
            <CustomChip
              key={`ema-${p}`}
              label={`EMA ${p}`}
              onRemove={() => onRemoveCustom('ema', p)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
