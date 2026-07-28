/**
 * AI ↔ Manual segmented control.
 *
 * The two modes are deliberately equal in size and weight — neither is labelled
 * "advanced" or presented as a fallback.
 */
import { PencilRuler, Sparkles } from 'lucide-react'

export type BuilderMode = 'ai' | 'manual'

type Props = {
  mode: BuilderMode
  onChange: (mode: BuilderMode) => void
}

const MODES: { value: BuilderMode; label: string; Icon: typeof Sparkles }[] = [
  { value: 'ai', label: 'AI로 만들기', Icon: Sparkles },
  { value: 'manual', label: '직접 만들기', Icon: PencilRuler },
]

export function ModeToggle({ mode, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="전략 작성 방식"
      className="grid grid-cols-2 gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1"
    >
      {MODES.map(({ value, label, Icon }) => {
        const active = mode === value
        return (
          <button
            key={value}
            role="tab"
            type="button"
            aria-selected={active}
            data-mode={value}
            onClick={() => onChange(value)}
            className={`flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
              active
                ? 'bg-white text-primary shadow-sm'
                : 'text-secondary hover:text-primary'
            }`}
          >
            <Icon className={`h-4 w-4 ${active ? 'text-accent' : 'text-tertiary'}`} />
            {label}
          </button>
        )
      })}
    </div>
  )
}
