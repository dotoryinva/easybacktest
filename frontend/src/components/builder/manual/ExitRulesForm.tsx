/** Stop loss %, take profit %, max holding bars — all optional. */
import type { Strategy } from '../../../schemas/strategy'

type Props = {
  strategy: Strategy
  onChange: (next: Strategy) => void
}

/** Stored as a fraction (0.05), edited as a percentage (5). */
function PercentField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: number | null | undefined
  onChange: (next: number | null) => void
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          className="input w-full"
          step={0.5}
          min={0}
          placeholder="—"
          value={value != null ? Number((value * 100).toFixed(4)) : ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value) / 100)}
        />
        <span className="text-sm text-secondary">%</span>
      </div>
      <p className="mt-1 text-[11px] text-tertiary">{hint}</p>
    </div>
  )
}

export function ExitRulesForm({ strategy, onChange }: Props) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-primary">청산 규칙</h3>
      <div className="grid gap-4 sm:grid-cols-3">
        <PercentField
          label="손절 (Stop loss)"
          hint="진입가 대비 하락률"
          value={strategy.stop_loss_pct}
          onChange={(stop_loss_pct) => onChange({ ...strategy, stop_loss_pct })}
        />
        <PercentField
          label="익절 (Take profit)"
          hint="진입가 대비 상승률"
          value={strategy.take_profit_pct}
          onChange={(take_profit_pct) => onChange({ ...strategy, take_profit_pct })}
        />
        <div>
          <label className="label">최대 보유 (봉)</label>
          <input
            type="number"
            className="input"
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
          <p className="mt-1 text-[11px] text-tertiary">거래일 기준</p>
        </div>
      </div>
    </section>
  )
}
