import { LineChart, PieChart } from 'lucide-react'

export type StrategyFamily = 'single_stock' | 'quant_portfolio'

const CARDS: {
  family: StrategyFamily
  icon: typeof LineChart
  titleKo: string
  titleEn: string
  desc: string
}[] = [
  {
    family: 'single_stock',
    icon: LineChart,
    titleKo: '개별 종목 매매전략',
    titleEn: 'Single-stock technical',
    desc: '골든크로스, RSI 반등 등 한 종목의 기술적 매매',
  },
  {
    family: 'quant_portfolio',
    icon: PieChart,
    titleKo: '퀀트 포트폴리오',
    titleEn: 'Multi-stock quantitative',
    desc: '팩터 랭킹으로 여러 종목을 골라 정기 리밸런싱',
  },
]

export function FamilySelector({
  value,
  onChange,
}: {
  value: StrategyFamily
  onChange: (family: StrategyFamily) => void
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {CARDS.map((c) => {
        const active = value === c.family
        const Icon = c.icon
        return (
          <button
            key={c.family}
            type="button"
            onClick={() => onChange(c.family)}
            className={`flex items-start gap-3 rounded-xl border p-4 text-left transition-colors ${
              active
                ? 'border-accent bg-accent/5'
                : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
            }`}
          >
            <div
              className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${
                active ? 'bg-accent text-white' : 'bg-slate-100 text-secondary'
              }`}
            >
              <Icon size={18} strokeWidth={1.9} />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-primary">{c.titleKo}</div>
              <div className="text-xs uppercase tracking-wide text-tertiary">{c.titleEn}</div>
              <p className="mt-1 text-xs leading-relaxed text-secondary">{c.desc}</p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
