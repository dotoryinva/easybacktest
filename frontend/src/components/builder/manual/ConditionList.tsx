/**
 * A titled list of condition rows with `AND` / `OR` separators so the boolean
 * semantics are visible, plus the `+ 조건 추가` button.
 */
import { Plus } from 'lucide-react'

import type { Condition } from '../../../schemas/strategy'
import { ConditionRow } from './ConditionRow'

export const NEW_CONDITION: Condition = {
  left: { kind: 'SMA', params: { period: 20 } },
  operator: 'cross_above',
  right: { kind: 'SMA', params: { period: 60 } },
}

type Props = {
  title: string
  /** Rendered between rows — buy conditions AND together, sell conditions OR. */
  joiner: 'AND' | 'OR'
  conditions: Condition[]
  onChange: (next: Condition[]) => void
  emptyHint?: string
  /** Buy conditions must keep at least one row; sell conditions may be emptied. */
  minRows?: number
}

export function ConditionList({
  title,
  joiner,
  conditions,
  onChange,
  emptyHint,
  minRows = 0,
}: Props) {
  const update = (index: number, next: Condition) => {
    const list = [...conditions]
    list[index] = next
    onChange(list)
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-primary">{title}</h3>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          onClick={() => onChange([...conditions, structuredClone(NEW_CONDITION)])}
        >
          <Plus className="h-3.5 w-3.5" />
          조건 추가
        </button>
      </div>

      {conditions.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-200 px-3 py-4 text-center text-xs text-slate-400">
          {emptyHint ?? '조건이 없습니다'}
        </p>
      ) : (
        <div className="space-y-1.5">
          {conditions.map((condition, index) => (
            <div key={index}>
              {index > 0 && (
                <div className="flex items-center justify-center py-1">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-slate-500">
                    {joiner}
                  </span>
                </div>
              )}
              <ConditionRow
                condition={condition}
                onChange={(next) => update(index, next)}
                onRemove={() => onChange(conditions.filter((_, i) => i !== index))}
                removable={conditions.length > minRows}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
