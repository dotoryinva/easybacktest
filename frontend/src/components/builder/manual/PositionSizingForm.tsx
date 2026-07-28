/** Radio group `[전액 / 고정 금액 / 자본 비율]` + conditional amount input. */
import type { Market, PositionSizing, Strategy } from '../../../schemas/strategy'

const OPTIONS: { value: PositionSizing; label: string; hint: string }[] = [
  { value: 'all_in', label: '전액', hint: '가용 현금 전부' },
  { value: 'fixed_amount', label: '고정 금액', hint: '매 진입마다 같은 금액' },
  { value: 'percent_of_capital', label: '자본 비율', hint: '평가액의 일정 비율' },
]

type Props = {
  strategy: Strategy
  market: Market
  onChange: (next: Strategy) => void
}

export function PositionSizingForm({ strategy, market, onChange }: Props) {
  const setMode = (mode: PositionSizing) =>
    onChange({
      ...strategy,
      position_sizing: mode,
      position_size_value:
        mode === 'all_in' ? null : mode === 'percent_of_capital' ? 0.5 : market === 'KR' ? 1_000_000 : 1_000,
    })

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-primary">포지션 사이징</h3>

      <div className="grid gap-2 sm:grid-cols-3">
        {OPTIONS.map((option) => {
          const active = strategy.position_sizing === option.value
          return (
            <label
              key={option.value}
              className={`flex cursor-pointer items-start gap-2 rounded-lg border p-3 transition-colors ${
                active
                  ? 'border-accent bg-accent/5'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <input
                type="radio"
                name="position_sizing"
                className="mt-0.5 h-4 w-4 accent-[#F59E0B]"
                checked={active}
                onChange={() => setMode(option.value)}
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-primary">{option.label}</span>
                <span className="block text-[11px] text-tertiary">{option.hint}</span>
              </span>
            </label>
          )
        })}
      </div>

      {strategy.position_sizing !== 'all_in' && (
        <div className="max-w-xs pt-1">
          <label className="label">
            {strategy.position_sizing === 'percent_of_capital'
              ? '비율 (0–1)'
              : `금액 (${market === 'KR' ? '원' : 'USD'})`}
          </label>
          <input
            type="number"
            className="input"
            min={strategy.position_sizing === 'percent_of_capital' ? 0.01 : 1}
            max={strategy.position_sizing === 'percent_of_capital' ? 1 : undefined}
            step={strategy.position_sizing === 'percent_of_capital' ? 0.05 : 100_000}
            value={strategy.position_size_value ?? ''}
            onChange={(e) =>
              onChange({
                ...strategy,
                position_size_value: e.target.value === '' ? null : Number(e.target.value),
              })
            }
          />
        </div>
      )}
    </section>
  )
}
