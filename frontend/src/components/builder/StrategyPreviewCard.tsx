/**
 * Human-readable summary of a parsed strategy, with inline editing.
 *
 * The AI usually gets a strategy ~90% right, so every numeric field a user is likely
 * to want to tweak (indicator periods, stop loss, take profit) is editable in place.
 * Structural changes go through the form editor.
 */
import { useState } from 'react'

import type { Condition, Strategy } from '../../schemas/strategy'
import { indicatorLabel, operatorLabel, positionSizingLabel } from '../../utils/describe'
import { formatPct } from '../../utils/format'

type Props = {
  strategy: Strategy
  onChange: (strategy: Strategy) => void
  onRun: () => void
  onEditForm: () => void
  /** Ask AI to revise the strategy in natural language. */
  onAiEdit?: () => void
  /** Hand the strategy to the Manual Builder. Omitted when already in manual mode. */
  onEditManual?: () => void
  onSave: () => void
  onDiscard: () => void
  running?: boolean
  saving?: boolean
  disabledReason?: string | null
}

/** Click-to-edit numeric value rendered inline in the condition text. */
function InlineNumber({
  value,
  onCommit,
  suffix,
  min = 1,
  step = 1,
}: {
  value: number
  onCommit: (next: number) => void
  suffix?: string
  min?: number
  step?: number
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(value))

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => {
          setDraft(String(value))
          setEditing(true)
        }}
        className="rounded px-1 font-mono text-accent underline decoration-dotted underline-offset-2 hover:bg-accent/10"
        title="Click to edit"
      >
        {value}
        {suffix}
      </button>
    )
  }

  const commit = () => {
    const parsed = Number(draft)
    if (Number.isFinite(parsed) && parsed >= min) onCommit(parsed)
    setEditing(false)
  }

  return (
    <input
      autoFocus
      type="number"
      min={min}
      step={step}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        if (e.key === 'Escape') setEditing(false)
      }}
      className="w-20 rounded border border-accent bg-ink-850 px-1 py-0.5 font-mono text-sm text-primary focus:outline-none"
    />
  )
}

/** One side of a condition — editable in place when it carries a tweakable number. */
function ConditionSide({
  side,
  condition,
  onChange,
}: {
  side: 'left' | 'right'
  condition: Condition
  onChange: (next: Condition) => void
}) {
  const ref = condition[side]
  const replace = (params: Record<string, number>) =>
    onChange({ ...condition, [side]: { ...ref, params: { ...ref.params, ...params } } })

  if (ref.kind === 'CONSTANT') {
    return (
      <InlineNumber
        value={ref.params.value ?? 0}
        step={0.1}
        min={Number.NEGATIVE_INFINITY}
        onCommit={(value) => replace({ value })}
      />
    )
  }

  if (ref.kind === 'SMA' || ref.kind === 'EMA' || ref.kind === 'RSI') {
    return (
      <span className="inline-flex items-center font-mono text-primary">
        {ref.kind}(
        <InlineNumber
          value={ref.params.period ?? 0}
          onCommit={(period) => replace({ period })}
        />
        )
      </span>
    )
  }

  return <span className="font-mono text-primary">{indicatorLabel(ref)}</span>
}

/** Renders `left <operator> right`, keeping each part addressable for editing. */
function ConditionRow({
  condition,
  language,
  onChange,
}: {
  condition: Condition
  language: 'ko' | 'en'
  onChange: (next: Condition) => void
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1">
      <ConditionSide side="left" condition={condition} onChange={onChange} />
      <span className="text-slate-400">{operatorLabel(condition.operator, language)}</span>
      <ConditionSide side="right" condition={condition} onChange={onChange} />
    </span>
  )
}

export function StrategyPreviewCard({
  strategy,
  onChange,
  onRun,
  onEditForm,
  onAiEdit,
  onEditManual,
  onSave,
  onDiscard,
  running,
  saving,
  disabledReason,
}: Props) {
  const [editingName, setEditingName] = useState(false)
  const language = strategy.language

  const setCondition = (
    key: 'buy_conditions' | 'sell_conditions',
    index: number,
    next: Condition,
  ) => {
    const list = [...strategy[key]]
    list[index] = next
    onChange({ ...strategy, [key]: list })
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-700 px-5 py-4">
        <div className="min-w-0 flex-1">
          {editingName ? (
            <input
              autoFocus
              className="input text-base font-semibold"
              value={strategy.name}
              onChange={(e) => onChange({ ...strategy, name: e.target.value })}
              onBlur={() => setEditingName(false)}
              onKeyDown={(e) => e.key === 'Enter' && setEditingName(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setEditingName(true)}
              className="text-left text-base font-semibold text-primary hover:text-accent"
              title="Click to rename"
            >
              {strategy.name}
            </button>
          )}
          <p className="mt-1 line-clamp-2 text-xs text-slate-500">{strategy.description}</p>
        </div>
        <span className="chip shrink-0">{language.toUpperCase()}</span>
      </div>

      <div className="space-y-5 px-5 py-4">
        <section>
          <div className="label">매수 조건 / Buy — all must be true</div>
          <ul className="space-y-1.5">
            {strategy.buy_conditions.map((condition, index) => (
              <li key={index} className="flex gap-2 text-sm text-primary">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-up" />
                <ConditionRow
                  condition={condition}
                  language={language}
                  onChange={(next) => setCondition('buy_conditions', index, next)}
                />
              </li>
            ))}
          </ul>
        </section>

        {strategy.sell_conditions.length > 0 && (
          <section>
            <div className="label">매도 조건 / Sell — any triggers an exit</div>
            <ul className="space-y-1.5">
              {strategy.sell_conditions.map((condition, index) => (
                <li key={index} className="flex gap-2 text-sm text-primary">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-down" />
                  <ConditionRow
                    condition={condition}
                    language={language}
                    onChange={(next) => setCondition('sell_conditions', index, next)}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="flex flex-wrap gap-2">
          {strategy.stop_loss_pct != null && (
            <span className="chip border-down/40 text-down">
              손절 / Stop loss −{formatPct(strategy.stop_loss_pct, 1)}
            </span>
          )}
          {strategy.take_profit_pct != null && (
            <span className="chip border-up/40 text-up">
              익절 / Take profit +{formatPct(strategy.take_profit_pct, 1)}
            </span>
          )}
          {strategy.max_holding_days != null && (
            <span className="chip">최대 보유 / Max hold {strategy.max_holding_days}d</span>
          )}
          <span className="chip">{positionSizingLabel(strategy)}</span>
          {strategy.cooldown_days_after_exit > 0 && (
            <span className="chip">Cooldown {strategy.cooldown_days_after_exit}d</span>
          )}
        </section>

        {disabledReason && (
          <p className="rounded-lg border border-down/40 bg-down/10 px-3 py-2 text-xs text-down">
            {disabledReason}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-t border-ink-700 bg-ink-850/50 px-5 py-3">
        <button
          type="button"
          className="btn-primary"
          onClick={onRun}
          disabled={running || Boolean(disabledReason)}
        >
          {running ? '실행 중…' : '백테스트 실행 / Run Backtest'}
        </button>
        <button type="button" className="btn-ghost" onClick={onEditForm}>
          전략 수정 / Edit as Form
        </button>
        {onAiEdit && (
          <button type="button" className="btn-ghost" onClick={onAiEdit}>
            AI에게 수정 요청
          </button>
        )}
        {onEditManual && (
          <button type="button" className="btn-ghost" onClick={onEditManual}>
            수동으로 편집
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onSave} disabled={saving}>
          {saving ? '저장 중…' : '저장 / Save to Library'}
        </button>
        <button type="button" className="btn-danger ml-auto" onClick={onDiscard}>
          Discard
        </button>
      </div>
    </div>
  )
}
