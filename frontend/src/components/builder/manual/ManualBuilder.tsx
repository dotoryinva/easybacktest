/**
 * Manual Strategy Builder container.
 *
 * Produces the exact same `Strategy` object the AI parser emits, so both modes share
 * the preview card, the backtest endpoint and the save endpoint.
 */
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import type { Market, Strategy } from '../../../schemas/strategy'
import { strategyIsRunnable } from '../../../schemas/strategy'
import type { StrategyPreset } from '../../../utils/presets'
import { ConditionList } from './ConditionList'
import { validateCondition } from './ConditionRow'
import { ExitRulesForm } from './ExitRulesForm'
import { PositionSizingForm } from './PositionSizingForm'
import { PresetChips } from './PresetChips'

type Props = {
  strategy: Strategy
  market: Market
  onChange: (next: Strategy) => void
  onRun: () => void
  onSave: () => void
  onPreview: () => void
  /** Switch to AI mode and ask for natural-language edits. */
  onAiEdit?: () => void
  running?: boolean
  saving?: boolean
}

/** All blocking problems, form-wide. Empty means the strategy can be run. */
export function collectErrors(strategy: Strategy): string[] {
  const errors: string[] = []
  if (!strategy.name.trim()) errors.push('전략 이름을 입력하세요')

  strategy.buy_conditions.forEach((condition, i) => {
    const error = validateCondition(condition)
    if (error) errors.push(`매수 조건 ${i + 1}: ${error}`)
  })
  strategy.sell_conditions.forEach((condition, i) => {
    const error = validateCondition(condition)
    if (error) errors.push(`매도 조건 ${i + 1}: ${error}`)
  })

  const runnable = strategyIsRunnable(strategy)
  if (runnable) errors.push(runnable)

  return errors
}

export function ManualBuilder({
  strategy,
  market,
  onChange,
  onRun,
  onSave,
  onPreview,
  onAiEdit,
  running,
  saving,
}: Props) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)

  const errors = collectErrors(strategy)
  const valid = errors.length === 0

  const loadPreset = (next: Strategy, preset: StrategyPreset) => {
    onChange(next)
    setActivePreset(preset.key)
  }

  // Any hand edit means it's no longer verbatim the preset.
  const edit = (next: Strategy) => {
    onChange(next)
    setActivePreset(null)
  }

  return (
    <div className="space-y-5 pb-24">
      <div className="card space-y-5 p-5">
        <PresetChips onLoad={loadPreset} activeKey={activePreset} />

        <div>
          <label className="label" htmlFor="strategy-name">
            전략 이름 <span className="text-negative">*</span>
          </label>
          <input
            id="strategy-name"
            className="input"
            placeholder="예: 20/60 골든크로스 + 5% 손절"
            value={strategy.name}
            onChange={(e) => edit({ ...strategy, name: e.target.value })}
          />
        </div>
      </div>

      <div className="card space-y-5 p-5">
        <ConditionList
          title="매수 조건 (모두 만족)"
          joiner="AND"
          conditions={strategy.buy_conditions}
          minRows={1}
          onChange={(buy_conditions) => edit({ ...strategy, buy_conditions })}
        />

        <div className="border-t border-slate-100 pt-5">
          <ConditionList
            title="매도 조건 (하나라도 만족)"
            joiner="OR"
            conditions={strategy.sell_conditions}
            emptyHint="매도 조건이 없습니다 — 손절 또는 익절을 설정하세요"
            onChange={(sell_conditions) => edit({ ...strategy, sell_conditions })}
          />
        </div>
      </div>

      <div className="card space-y-5 p-5">
        <ExitRulesForm strategy={strategy} onChange={edit} />
        <div className="border-t border-slate-100 pt-5">
          <PositionSizingForm strategy={strategy} market={market} onChange={edit} />
        </div>

        <div className="border-t border-slate-100 pt-4">
          <button
            type="button"
            className="flex items-center gap-1 text-sm font-medium text-secondary hover:text-primary"
            onClick={() => setAdvancedOpen((open) => !open)}
            aria-expanded={advancedOpen}
          >
            {advancedOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            고급 설정
          </button>

          {advancedOpen && (
            <div className="mt-3 space-y-3 pl-5">
              <label className="flex items-center gap-2 text-sm text-primary">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[#F59E0B]"
                  checked={strategy.allow_reentry_same_day}
                  onChange={(e) =>
                    edit({ ...strategy, allow_reentry_same_day: e.target.checked })
                  }
                />
                청산 당일 재진입 허용
              </label>
              <div className="max-w-xs">
                <label className="label">청산 후 재진입 대기 (봉)</label>
                <input
                  type="number"
                  className="input"
                  min={0}
                  value={strategy.cooldown_days_after_exit}
                  onChange={(e) =>
                    edit({
                      ...strategy,
                      cooldown_days_after_exit: Number(e.target.value || 0),
                    })
                  }
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {!valid && (
        <ul className="rounded-lg border border-negative/30 bg-negative-bg px-4 py-3 text-xs text-negative">
          {errors.map((error) => (
            <li key={error}>· {error}</li>
          ))}
        </ul>
      )}

      {/* Sticky to the viewport so the actions stay reachable down a long form. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-end gap-2 px-4 py-3 lg:px-6">
          {onAiEdit && (
            <button
              type="button"
              className="btn-ghost mr-auto"
              onClick={onAiEdit}
              disabled={!valid}
            >
              AI에게 수정 요청
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={onPreview} disabled={!valid}>
            미리보기
          </button>
          <button type="button" className="btn-secondary" onClick={onSave} disabled={!valid || saving}>
            {saving ? '저장 중…' : '저장'}
          </button>
          <button type="button" className="btn-primary" onClick={onRun} disabled={!valid || running}>
            {running ? '실행 중…' : '백테스트 실행'}
          </button>
        </div>
      </div>
    </div>
  )
}
