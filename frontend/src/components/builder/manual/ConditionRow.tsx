/**
 * One condition: `[Left indicator] [Operator] [Right: 지표 | 값]`.
 *
 * Validation runs on blur and is surfaced inline; `validateCondition` is exported so
 * the container can block "Run Backtest" while anything is invalid.
 */
import { GripVertical, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { Condition, IndicatorRef, Operator } from '../../../schemas/strategy'
import { IndicatorPicker, defaultParams, isSeries, paramFields } from './IndicatorPicker'

const ALL_OPERATORS: { value: Operator; label: string }[] = [
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '>=', label: '≥' },
  { value: '<=', label: '≤' },
  { value: '==', label: '=' },
  { value: 'cross_above', label: '상향돌파' },
  { value: 'cross_below', label: '하향돌파' },
]

/**
 * Crossing is a property of the moving side, so `cross_*` needs a time series on the
 * left. A constant on the right is valid and common (`RSI(14) 상향돌파 30`).
 */
export function availableOperators(left: IndicatorRef): typeof ALL_OPERATORS {
  return isSeries(left.kind)
    ? ALL_OPERATORS
    : ALL_OPERATORS.filter((o) => o.value !== 'cross_above' && o.value !== 'cross_below')
}

function sameRef(a: IndicatorRef, b: IndicatorRef): boolean {
  if (a.kind !== b.kind) return false
  const keys = new Set([...Object.keys(a.params ?? {}), ...Object.keys(b.params ?? {})])
  for (const key of keys) {
    const av = (a.params as Record<string, unknown>)[key] ?? 0
    const bv = (b.params as Record<string, unknown>)[key] ?? 0
    if (av !== bv) return false
  }
  return true
}

/** Returns a Korean error message, or null when the condition is valid. */
export function validateCondition(condition: Condition): string | null {
  const { left, right, operator } = condition

  for (const [side, ref] of [
    ['왼쪽', left],
    ['오른쪽', right],
  ] as const) {
    if (ref.kind === 'CONSTANT') {
      if (ref.params.value == null || !Number.isFinite(ref.params.value))
        return `${side} 값을 입력하세요`
      continue
    }
    for (const field of paramFields(ref.kind)) {
      const value = (ref.params as Record<string, number | undefined>)[field.key]
      if (field.key === 'offset' && value == null) continue // optional, defaults to 0
      if (value == null || Number.isNaN(value)) return `${side} ${field.label}을(를) 입력하세요`
      if (value < field.min || value > field.max)
        return `${side} ${field.label}은(는) ${field.min}–${field.max} 사이여야 합니다`
      if (field.step === 1 && !Number.isInteger(value))
        return `${side} ${field.label}은(는) 정수여야 합니다`
    }
  }

  if ((operator === 'cross_above' || operator === 'cross_below') && !isSeries(left.kind))
    return '돌파 조건의 왼쪽은 지표여야 합니다'

  if (sameRef(left, right)) return '양쪽이 같은 지표입니다'

  return null
}

type Props = {
  condition: Condition
  onChange: (next: Condition) => void
  onRemove: () => void
  removable: boolean
}

export function ConditionRow({ condition, onChange, onRemove, removable }: Props) {
  const [touched, setTouched] = useState(false)
  const error = validateCondition(condition)
  const rightIsValue = condition.left && condition.right.kind === 'CONSTANT'
  const operators = availableOperators(condition.left)

  const setRightMode = (mode: 'indicator' | 'value') => {
    if (mode === 'value') {
      onChange({ ...condition, right: { kind: 'CONSTANT', params: { value: 30 } } })
    } else {
      const next: Condition = {
        ...condition,
        right: { kind: 'SMA', params: defaultParams('SMA') },
      }
      onChange(next)
    }
  }

  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="flex items-start gap-2">
        {/* Drag-to-reorder is Phase 1.5; the handle is present but inert. */}
        <GripVertical
          className="mt-2 h-4 w-4 shrink-0 cursor-grab text-secondary"
          aria-hidden
        />

        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-2">
          <IndicatorPicker
            value={condition.left}
            onChange={(left) => {
              // Switching to a constant on the left invalidates cross operators.
              const stillValid = availableOperators(left).some(
                (o) => o.value === condition.operator,
              )
              onChange({
                ...condition,
                left,
                operator: stillValid ? condition.operator : '>',
              })
            }}
            onBlur={() => setTouched(true)}
          />

          <select
            aria-label="연산자"
            className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-xs font-medium text-slate-900 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            value={condition.operator}
            onChange={(e) => onChange({ ...condition, operator: e.target.value as Operator })}
          >
            {operators.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <div className="flex items-end gap-1.5">
            <div className="segmented h-9">
              {(['indicator', 'value'] as const).map((mode) => {
                const active = mode === 'value' ? rightIsValue : !rightIsValue
                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setRightMode(mode)}
                    className={`segmented-item ${active ? 'segmented-item-active' : ''}`}
                  >
                    {mode === 'indicator' ? '지표' : '값'}
                  </button>
                )
              })}
            </div>

            {rightIsValue ? (
              <input
                type="number"
                aria-label="값"
                step="any"
                className="h-9 w-24 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-900 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                value={condition.right.params.value ?? ''}
                onBlur={() => setTouched(true)}
                onChange={(e) =>
                  onChange({
                    ...condition,
                    right: {
                      kind: 'CONSTANT',
                      params: {
                        value: e.target.value === '' ? undefined : Number(e.target.value),
                      },
                    },
                  })
                }
              />
            ) : (
              <IndicatorPicker
                compact
                value={condition.right}
                onChange={(right) => onChange({ ...condition, right })}
                onBlur={() => setTouched(true)}
              />
            )}
          </div>
        </div>

        {removable && (
          <button
            type="button"
            onClick={onRemove}
            aria-label="조건 삭제"
            className="mt-1 rounded-md p-1.5 text-slate-400 hover:bg-slate-200 hover:text-negative"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {touched && error && <p className="mt-2 pl-6 text-[11px] text-negative">{error}</p>}
    </div>
  )
}
