/** Full structural editor — add/remove conditions, change indicators and exit rules. */
import {
  indicatorKindSchema,
  operatorSchema,
  positionSizingSchema,
  type Condition,
  type IndicatorKind,
  type IndicatorRef,
  type Operator,
  type Strategy,
} from '../../schemas/strategy'

type Props = {
  strategy: Strategy
  onChange: (strategy: Strategy) => void
  onDone: () => void
}

const KINDS = indicatorKindSchema.options
const OPERATORS = operatorSchema.options
const SIZING = positionSizingSchema.options

/** Which numeric params a given indicator kind actually uses. */
function paramFields(kind: IndicatorKind): { key: string; label: string; step: number }[] {
  if (kind === 'SMA' || kind === 'EMA' || kind === 'RSI')
    return [{ key: 'period', label: 'Period', step: 1 }]
  if (kind === 'MACD_LINE' || kind === 'MACD_SIGNAL')
    return [
      { key: 'fast', label: 'Fast', step: 1 },
      { key: 'slow', label: 'Slow', step: 1 },
      { key: 'signal', label: 'Signal', step: 1 },
    ]
  if (kind.startsWith('BOLLINGER'))
    return [
      { key: 'period', label: 'Period', step: 1 },
      { key: 'std', label: 'Std dev', step: 0.1 },
    ]
  if (kind === 'CONSTANT') return [{ key: 'value', label: 'Value', step: 0.1 }]
  return []
}

/** Sensible starting params when the user switches an indicator's kind. */
function defaultParams(kind: IndicatorKind): Record<string, number> {
  if (kind === 'SMA' || kind === 'EMA') return { period: 20 }
  if (kind === 'RSI') return { period: 14 }
  if (kind === 'MACD_LINE' || kind === 'MACD_SIGNAL')
    return { fast: 12, slow: 26, signal: 9 }
  if (kind.startsWith('BOLLINGER')) return { period: 20, std: 2 }
  if (kind === 'CONSTANT') return { value: 30 }
  return {}
}

function IndicatorEditor({
  value,
  onChange,
}: {
  value: IndicatorRef
  onChange: (next: IndicatorRef) => void
}) {
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div>
        <label className="label">Indicator</label>
        <select
          className="input w-44"
          value={value.kind}
          onChange={(e) => {
            const kind = e.target.value as IndicatorKind
            onChange({ kind, params: defaultParams(kind) })
          }}
        >
          {KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
      </div>
      {paramFields(value.kind).map((field) => (
        <div key={field.key}>
          <label className="label">{field.label}</label>
          <input
            className="input w-24"
            type="number"
            step={field.step}
            value={(value.params as Record<string, number | undefined>)[field.key] ?? ''}
            onChange={(e) =>
              onChange({
                ...value,
                params: { ...value.params, [field.key]: Number(e.target.value) },
              })
            }
          />
        </div>
      ))}
    </div>
  )
}

function ConditionEditor({
  condition,
  onChange,
  onRemove,
}: {
  condition: Condition
  onChange: (next: Condition) => void
  onRemove: () => void
}) {
  return (
    <div className="space-y-3 rounded-lg border border-ink-700 bg-ink-850 p-3">
      <IndicatorEditor
        value={condition.left}
        onChange={(left) => onChange({ ...condition, left })}
      />
      <div>
        <label className="label">Operator</label>
        <select
          className="input w-44"
          value={condition.operator}
          onChange={(e) =>
            onChange({ ...condition, operator: e.target.value as Operator })
          }
        >
          {OPERATORS.map((op) => (
            <option key={op} value={op}>
              {op}
            </option>
          ))}
        </select>
      </div>
      <IndicatorEditor
        value={condition.right}
        onChange={(right) => onChange({ ...condition, right })}
      />
      <button type="button" className="btn-danger py-1 text-xs" onClick={onRemove}>
        Remove condition
      </button>
    </div>
  )
}

const NEW_CONDITION: Condition = {
  left: { kind: 'SMA', params: { period: 20 } },
  operator: 'cross_above',
  right: { kind: 'SMA', params: { period: 60 } },
}

/** Percent-typed field: stored as a fraction, edited as a percentage. */
function PercentField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number | null | undefined
  onChange: (next: number | null) => void
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex items-center gap-2">
        <input
          className="input w-28"
          type="number"
          step={0.5}
          min={0}
          placeholder="—"
          value={value != null ? +(value * 100).toFixed(4) : ''}
          onChange={(e) => {
            const raw = e.target.value
            onChange(raw === '' ? null : Number(raw) / 100)
          }}
        />
        <span className="text-sm text-slate-500">%</span>
      </div>
    </div>
  )
}

export function StrategyFormEditor({ strategy, onChange, onDone }: Props) {
  const setList = (key: 'buy_conditions' | 'sell_conditions', list: Condition[]) =>
    onChange({ ...strategy, [key]: list })

  const renderSection = (
    key: 'buy_conditions' | 'sell_conditions',
    title: string,
  ) => (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary">{title}</h3>
        <button
          type="button"
          className="btn-ghost py-1 text-xs"
          onClick={() => setList(key, [...strategy[key], structuredClone(NEW_CONDITION)])}
        >
          + Add
        </button>
      </div>
      {strategy[key].length === 0 && (
        <p className="text-xs text-slate-500">None.</p>
      )}
      {strategy[key].map((condition, index) => (
        <ConditionEditor
          key={index}
          condition={condition}
          onChange={(next) => {
            const list = [...strategy[key]]
            list[index] = next
            setList(key, list)
          }}
          onRemove={() => setList(key, strategy[key].filter((_, i) => i !== index))}
        />
      ))}
    </section>
  )

  return (
    <div className="card space-y-6 p-5">
      <div>
        <label className="label">Strategy name</label>
        <input
          className="input"
          value={strategy.name}
          onChange={(e) => onChange({ ...strategy, name: e.target.value })}
        />
      </div>

      {renderSection('buy_conditions', '매수 조건 / Buy conditions (AND)')}
      {renderSection('sell_conditions', '매도 조건 / Sell conditions (OR)')}

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <PercentField
          label="Stop loss"
          value={strategy.stop_loss_pct}
          onChange={(stop_loss_pct) => onChange({ ...strategy, stop_loss_pct })}
        />
        <PercentField
          label="Take profit"
          value={strategy.take_profit_pct}
          onChange={(take_profit_pct) => onChange({ ...strategy, take_profit_pct })}
        />
        <div>
          <label className="label">Max holding (bars)</label>
          <input
            className="input"
            type="number"
            min={1}
            placeholder="—"
            value={strategy.max_holding_days ?? ''}
            onChange={(e) =>
              onChange({
                ...strategy,
                max_holding_days: e.target.value === '' ? null : Number(e.target.value),
              })
            }
          />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <label className="label">Position sizing</label>
          <select
            className="input"
            value={strategy.position_sizing}
            onChange={(e) =>
              onChange({
                ...strategy,
                position_sizing: e.target.value as Strategy['position_sizing'],
                position_size_value:
                  e.target.value === 'all_in'
                    ? null
                    : e.target.value === 'percent_of_capital'
                      ? 0.5
                      : 1_000_000,
              })
            }
          >
            {SIZING.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
        </div>
        {strategy.position_sizing !== 'all_in' && (
          <div>
            <label className="label">
              {strategy.position_sizing === 'percent_of_capital'
                ? 'Fraction (0–1)'
                : 'Amount per trade'}
            </label>
            <input
              className="input"
              type="number"
              step={strategy.position_sizing === 'percent_of_capital' ? 0.05 : 1000}
              value={strategy.position_size_value ?? ''}
              onChange={(e) =>
                onChange({ ...strategy, position_size_value: Number(e.target.value) })
              }
            />
          </div>
        )}
        <div>
          <label className="label">Cooldown after exit (bars)</label>
          <input
            className="input"
            type="number"
            min={0}
            value={strategy.cooldown_days_after_exit}
            onChange={(e) =>
              onChange({ ...strategy, cooldown_days_after_exit: Number(e.target.value) })
            }
          />
        </div>
      </section>

      <label className="flex items-center gap-2 text-sm text-secondary">
        <input
          type="checkbox"
          className="h-4 w-4 accent-[#5b8def]"
          checked={strategy.allow_reentry_same_day}
          onChange={(e) =>
            onChange({ ...strategy, allow_reentry_same_day: e.target.checked })
          }
        />
        Allow re-entry from the same bar an exit filled
      </label>

      <div className="flex justify-end border-t border-ink-700 pt-4">
        <button type="button" className="btn-primary" onClick={onDone}>
          Done editing
        </button>
      </div>
    </div>
  )
}
