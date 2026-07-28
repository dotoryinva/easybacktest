import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useRetirementSim } from '../api/client'
import { MarketToggle } from '../components/market/MarketToggle'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { RetirementInput } from '../schemas/retirement'
import type { Market } from '../schemas/strategy'

/** Form amounts are in the currency's major unit: 만원 (10k) for KRW, 천달러 (1k) for USD. */
const UNIT: Record<Market, number> = { KR: 10_000, US: 1_000 }
const UNIT_LABEL: Record<Market, string> = { KR: '만원', US: '천$' }

function compact(value: number, market: Market): string {
  const v = Math.round(value)
  if (market === 'KR') {
    if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`
    if (Math.abs(v) >= 1e4) return `${Math.round(v / 1e4).toLocaleString()}만`
    return v.toLocaleString()
  }
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
  if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(0)}K`
  return `$${v}`
}

type FormState = {
  current_age: number
  retirement_age: number
  end_age: number
  current_savings: number // major unit
  annual_contribution: number // major unit
  annual_spending: number // major unit
  expected_return: number // percent
  volatility: number // percent
  inflation: number // percent
}

const DEFAULTS: Record<Market, FormState> = {
  KR: {
    current_age: 35, retirement_age: 60, end_age: 90,
    current_savings: 10_000, annual_contribution: 1_200, annual_spending: 4_000,
    expected_return: 6, volatility: 12, inflation: 2.5,
  },
  US: {
    current_age: 35, retirement_age: 65, end_age: 95,
    current_savings: 200, annual_contribution: 24, annual_spending: 80,
    expected_return: 6, volatility: 12, inflation: 2.5,
  },
}

export function RetirementPage() {
  const [market, setMarket] = useState<Market>('KR')
  const [form, setForm] = useState<FormState>(DEFAULTS.KR)
  const sim = useRetirementSim()

  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }))

  const run = () => {
    const unit = UNIT[market]
    const body: RetirementInput = {
      current_age: form.current_age,
      retirement_age: form.retirement_age,
      end_age: form.end_age,
      current_savings: form.current_savings * unit,
      annual_contribution: form.annual_contribution * unit,
      annual_spending: form.annual_spending * unit,
      expected_return: form.expected_return / 100,
      volatility: form.volatility / 100,
      inflation: form.inflation / 100,
      num_simulations: 3000,
    }
    sim.mutate(body)
  }

  // Reset to sensible defaults when the currency changes, then re-run.
  const switchMarket = (m: Market) => {
    setMarket(m)
    setForm(DEFAULTS[m])
  }

  // Run once on mount and whenever the market default changes.
  useEffect(() => {
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market])

  const result = sim.data
  const chartData = useMemo(
    () =>
      (result?.bands ?? []).map((b) => ({
        age: b.age,
        p10: b.p10,
        spread: Math.max(0, b.p90 - b.p10),
        p50: b.p50,
      })),
    [result],
  )

  const successPct = result ? Math.round(result.success_probability * 100) : null
  const successTone =
    successPct == null ? '' : successPct >= 85 ? 'text-up' : successPct >= 60 ? 'text-accent' : 'text-down'

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-primary">은퇴 / Retirement</h1>
          <p className="mt-1 text-sm text-secondary">
            몬테카를로 시뮬레이션으로 은퇴 자금이 버틸 확률을 계산합니다. 금액 단위:{' '}
            {market === 'KR' ? '만원' : '천 달러'}.
          </p>
        </div>
        <MarketToggle value={market} onChange={switchMarket} />
      </header>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        {/* Inputs */}
        <div className="card space-y-3 p-4">
          <div className="grid grid-cols-3 gap-2">
            <NumField label="현재 나이" value={form.current_age} onChange={(v) => set({ current_age: v })} />
            <NumField label="은퇴 나이" value={form.retirement_age} onChange={(v) => set({ retirement_age: v })} />
            <NumField label="기대 수명" value={form.end_age} onChange={(v) => set({ end_age: v })} />
          </div>
          <NumField label={`현재 저축액 (${UNIT_LABEL[market]})`} value={form.current_savings}
            onChange={(v) => set({ current_savings: v })} />
          <NumField label={`연 저축액 (은퇴 전, ${UNIT_LABEL[market]})`} value={form.annual_contribution}
            onChange={(v) => set({ annual_contribution: v })} />
          <NumField label={`연 지출액 (은퇴 후, ${UNIT_LABEL[market]})`} value={form.annual_spending}
            onChange={(v) => set({ annual_spending: v })} />
          <div className="grid grid-cols-3 gap-2">
            <NumField label="기대수익 %" step={0.5} value={form.expected_return} onChange={(v) => set({ expected_return: v })} />
            <NumField label="변동성 %" step={0.5} value={form.volatility} onChange={(v) => set({ volatility: v })} />
            <NumField label="물가 %" step={0.1} value={form.inflation} onChange={(v) => set({ inflation: v })} />
          </div>
          <button type="button" className="btn-primary w-full" onClick={run} disabled={sim.isPending}>
            {sim.isPending ? '계산 중…' : '시뮬레이션 실행'}
          </button>
          <p className="text-[11px] leading-relaxed text-tertiary">
            연 지출액은 오늘 기준 금액이며 매년 물가만큼 늘어난다고 가정합니다. 수익률은 매년 정규분포(평균 기대수익,
            표준편차 변동성)로 무작위 추출한 3,000회 시뮬레이션입니다.
          </p>
        </div>

        {/* Results */}
        <div className="space-y-4">
          {sim.error && <ErrorNote error={sim.error} />}

          {sim.isPending && !result ? (
            <div className="flex items-center gap-3 py-16 text-sm text-secondary">
              <Spinner /> 시뮬레이션 계산 중…
            </div>
          ) : result ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="성공 확률" value={`${successPct}%`} tone={successTone}
                  hint={`${form.end_age}세까지 자금 유지`} />
                <Stat label="안전 연 지출" value={compact(result.safe_annual_spending, market)}
                  hint="성공확률 90% 수준" />
                <Stat label="예상 잔액 (중앙값)" value={compact(result.median_ending_balance, market)}
                  hint={`${form.end_age}세 시점`} />
                <Stat label="자금 소진 나이" value={result.depletion_age_p50 == null ? '없음' : `${result.depletion_age_p50}세`}
                  tone={result.depletion_age_p50 == null ? 'text-up' : 'text-down'} hint="중앙값 경로" />
              </div>

              <div className="card p-4">
                <div className="mb-1 text-sm font-semibold text-primary">자산 추이 (10–90 백분위)</div>
                <div className="h-[320px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.15)" vertical={false} />
                      <XAxis dataKey="age" tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }} minTickGap={24}
                        tickFormatter={(v: number) => `${v}세`} />
                      <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickLine={false} axisLine={false} width={52}
                        tickFormatter={(v: number) => compact(v, market)} />
                      <Tooltip
                        contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12 }}
                        labelFormatter={(v) => `${v}세`}
                        formatter={(value, name) => [
                          compact(Number(value), market),
                          name === 'p50' ? '중앙값' : name === 'p10' ? '하위 10%' : '범위',
                        ]}
                      />
                      <Area dataKey="p10" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
                      <Area dataKey="spread" stackId="band" stroke="none" fill="rgba(245,158,11,0.16)" isAnimationActive={false} />
                      <Line dataKey="p50" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
                      <ReferenceLine x={form.retirement_age} stroke="#94a3b8" strokeDasharray="4 3"
                        label={{ value: '은퇴', position: 'top', fill: '#94a3b8', fontSize: 11 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-1 text-[11px] text-tertiary">
                  음영은 시뮬레이션의 하위 10%~상위 90% 범위, 실선은 중앙값(50%) 경로입니다.
                </p>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function NumField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  step?: number
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        type="number"
        className="input"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

function Stat({ label, value, hint, tone = 'text-primary' }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="card p-3">
      <div className="text-xs text-secondary">{label}</div>
      <div className={`mt-0.5 text-xl font-bold ${tone}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-tertiary">{hint}</div>}
    </div>
  )
}
