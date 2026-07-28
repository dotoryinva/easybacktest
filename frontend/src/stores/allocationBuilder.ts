/** Change 15 — the AllocationStrategy under construction, auto-saved to localStorage. */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type {
  AllocationAlgorithm,
  AllocationRebalancePeriod,
  AllocationStrategy,
  AssetSlot,
  WeightScheme,
} from '../schemas/allocation'
import { ALGORITHM_CONTROLS_WEIGHTS } from '../schemas/allocation'
import { isoDate, yearsAgo } from '../utils/format'

export type AllocationPreset = {
  label: string
  algorithm: AllocationAlgorithm
  weight_scheme: WeightScheme | null
  rebalance_period: AllocationRebalancePeriod
  assets: AssetSlot[]
  apply_fx?: boolean
}

/** Curated presets (subset of 15.9 — enough to seed the page and examples gallery). */
export const ALLOCATION_PRESETS: AllocationPreset[] = [
  {
    label: '레이 달리오 All Weather',
    algorithm: 'static', weight_scheme: 'custom', rebalance_period: 'annually', apply_fx: true,
    assets: [
      { ticker: 'VTI', market: 'US', target_weight_pct: 30 },
      { ticker: 'TLT', market: 'US', target_weight_pct: 40 },
      { ticker: 'IEF', market: 'US', target_weight_pct: 15 },
      { ticker: 'GLD', market: 'US', target_weight_pct: 7.5 },
      { ticker: 'DBC', market: 'US', target_weight_pct: 7.5 },
    ],
  },
  {
    label: '글로벌 60/40',
    algorithm: 'static', weight_scheme: 'custom', rebalance_period: 'annually', apply_fx: true,
    assets: [
      { ticker: 'VTI', market: 'US', target_weight_pct: 60 },
      { ticker: 'BND', market: 'US', target_weight_pct: 40 },
    ],
  },
  {
    label: '한국형 4자산',
    algorithm: 'static', weight_scheme: 'equal', rebalance_period: 'quarterly', apply_fx: true,
    assets: [
      { ticker: '069500', market: 'KR' }, // KODEX 200
      { ticker: '148070', market: 'KR' }, // KODEX 국고채10년
      { ticker: '132030', market: 'KR' }, // KODEX 골드선물
      { ticker: '360750', market: 'KR' }, // TIGER 미국S&P500
    ],
  },
  {
    label: '리스크 패리티 3자산',
    algorithm: 'risk_parity', weight_scheme: null, rebalance_period: 'quarterly', apply_fx: true,
    assets: [
      { ticker: 'VTI', market: 'US' },
      { ticker: 'TLT', market: 'US' },
      { ticker: 'GLD', market: 'US' },
    ],
  },
]

const emptyStrategy = (): AllocationStrategy => ({
  family: 'allocation',
  name: '자산배분 전략',
  description: '',
  language: 'ko',
  algorithm: 'static',
  assets: [
    { ticker: '', market: 'KR', target_weight_pct: null },
    { ticker: '', market: 'KR', target_weight_pct: null },
  ],
  weight_scheme: 'equal',
  rebalance_period: 'annually',
  rebalance_band_pct: 0,
  apply_fx: true,
  lookback_days_for_estimation: 252,
})

type State = {
  strategy: AllocationStrategy
  startDate: string
  endDate: string
  initialCapitalManwon: number // 만원 units, per Quantus
  set: (patch: Partial<AllocationStrategy>) => void
  setAssets: (assets: AssetSlot[]) => void
  setPeriod: (start: string, end: string) => void
  setCapital: (manwon: number) => void
  loadPreset: (preset: AllocationPreset) => void
  reset: () => void
}

export const useAllocationBuilder = create<State>()(
  persist(
    (setState) => ({
      strategy: emptyStrategy(),
      startDate: yearsAgo(10),
      endDate: isoDate(new Date()),
      initialCapitalManwon: 1000, // 1,000만원 = 10,000,000원
      set: (patch) => setState((s) => ({ strategy: { ...s.strategy, ...patch } })),
      setAssets: (assets) => setState((s) => ({ strategy: { ...s.strategy, assets } })),
      setPeriod: (startDate, endDate) => setState({ startDate, endDate }),
      setCapital: (initialCapitalManwon) => setState({ initialCapitalManwon }),
      loadPreset: (preset) =>
        setState((s) => ({
          strategy: {
            ...s.strategy,
            name: preset.label,
            algorithm: preset.algorithm,
            weight_scheme: preset.weight_scheme,
            rebalance_period: preset.rebalance_period,
            apply_fx: preset.apply_fx ?? true,
            assets: preset.assets.map((a) => ({ ...a })),
            momentum_timing: null,
          },
        })),
      reset: () =>
        setState({
          strategy: emptyStrategy(),
          startDate: yearsAgo(10),
          endDate: isoDate(new Date()),
          initialCapitalManwon: 1000,
        }),
    }),
    { name: 'easybacktest.allocation' },
  ),
)

export function algorithmControlsWeights(algorithm: AllocationAlgorithm): boolean {
  return ALGORITHM_CONTROLS_WEIGHTS.includes(algorithm)
}
