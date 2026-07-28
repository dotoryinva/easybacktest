/** The 5 preset chips. Clicking one fills the whole form. */
import { Sparkles } from 'lucide-react'

import { PRESETS, instantiatePreset, type StrategyPreset } from '../../../utils/presets'
import type { Strategy } from '../../../schemas/strategy'

type Props = {
  onLoad: (strategy: Strategy, preset: StrategyPreset) => void
  activeKey?: string | null
}

export function PresetChips({ onLoad, activeKey }: Props) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5 text-accent" />
        <h3 className="text-sm font-semibold text-primary">프리셋</h3>
        <span className="text-[11px] text-tertiary">클릭하면 폼이 채워집니다</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            title={preset.description}
            data-preset={preset.key}
            onClick={() => onLoad(instantiatePreset(preset), preset)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-all hover:-translate-y-px hover:shadow-md ${
              activeKey === preset.key
                ? 'border-accent bg-accent/10 text-accent-600'
                : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </section>
  )
}
