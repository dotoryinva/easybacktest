import { ChevronDown, ChevronRight, Lock, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { NavLink } from 'react-router-dom'

import { useAllocationBacktest, useExtractPortfolio } from '../api/client'
import { BacktestResultView } from '../components/backtest/BacktestResultView'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type {
  AllocationAlgorithm,
  AllocationRebalancePeriod,
  AssetSlot,
  WeightScheme,
} from '../schemas/allocation'
import type { Market } from '../schemas/strategy'
import {
  ALLOCATION_PRESETS,
  algorithmControlsWeights,
  useAllocationBuilder,
} from '../stores/allocationBuilder'

const ALGORITHMS: { value: AllocationAlgorithm; label: string }[] = [
  { value: 'static', label: '전략배분 (정적자산배분)' },
  { value: 'risk_parity', label: '위험균형 (리스크 패리티)' },
  { value: 'min_variance', label: '최소분산 (Min Variance)' },
  { value: 'max_sharpe', label: '최대샤프 (Max Sharpe)' },
  { value: 'vol_target', label: '변동성 목표' },
  { value: 'erc', label: '동일위험기여 (ERC)' },
  { value: 'hrp', label: 'HRP' },
]

const WEIGHT_SCHEMES: { value: WeightScheme; label: string }[] = [
  { value: 'equal', label: '동일 비중' },
  { value: 'custom', label: '사용자 지정' },
  { value: 'inverse_vol', label: '역변동성 가중' },
  { value: 'inverse_corr', label: '역상관 가중' },
  { value: 'market_cap', label: '시가총액 가중' },
]

const REBALANCE_PERIODS: { value: AllocationRebalancePeriod; label: string }[] = [
  { value: 'none', label: '리밸런싱 없음' },
  { value: 'daily', label: '매일' },
  { value: 'weekly', label: '매주' },
  { value: 'monthly', label: '매월' },
  { value: 'quarterly', label: '매분기' },
  { value: 'semi_annually', label: '매반기' },
  { value: 'annually', label: '매년' },
]

const ISO = (d: Date) => d.toISOString().slice(0, 10)

function Card({
  n, title, required, children, defaultOpen = true,
}: {
  n: number; title: string; required?: boolean; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <span className="grid h-5 w-5 place-items-center rounded bg-slate-100 text-xs font-semibold text-secondary">
          {n}
        </span>
        <span className="text-sm font-semibold text-primary">{title}</span>
        {required && <span className="text-xs font-semibold text-accent">[필수]</span>}
        <span className="ml-auto text-secondary">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
      </button>
      {open && <div className="space-y-3 border-t border-slate-100 px-4 py-4">{children}</div>}
    </section>
  )
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="flex flex-col gap-1 text-xs text-secondary">
    {label}
    {children}
  </label>
)

export function AllocationPage() {
  const store = useAllocationBuilder()
  const s = store.strategy
  const backtest = useAllocationBacktest()
  const extract = useExtractPortfolio()

  const capitalWon = store.initialCapitalManwon * 10_000
  const weightLocked = algorithmControlsWeights(s.algorithm)
  const isCustom = !weightLocked && s.weight_scheme === 'custom'
  const filledAssets = s.assets.filter((a) => a.ticker.trim())
  const weightSum = filledAssets.reduce((sum, a) => sum + (a.target_weight_pct ?? 0), 0)

  const validation = (() => {
    if (filledAssets.length < 2) return '자산을 2개 이상 추가하세요.'
    if (isCustom && Math.abs(weightSum - 100) > 0.01) return `비중 합계가 100%가 되어야 합니다 (현재 ${weightSum.toFixed(1)}%).`
    if (store.startDate >= store.endDate) return '종료일이 시작일보다 뒤여야 합니다.'
    if (s.momentum_timing && !s.momentum_timing.safe_haven_ticker) return '마켓 타이밍의 위험회피 자산을 선택하세요.'
    if (s.algorithm === 'vol_target' && !(s.vol_target_annual && s.vol_target_annual > 0))
      return '변동성 목표 알고리즘은 목표 변동성(연 %)을 입력해야 합니다.'
    return null
  })()

  const buildRequestStrategy = () => ({
    ...s,
    assets: filledAssets.map((a) => ({
      ticker: a.ticker.trim().toUpperCase(),
      market: a.market,
      target_weight_pct: isCustom ? a.target_weight_pct : null,
    })),
    weight_scheme: weightLocked ? null : s.weight_scheme,
  })

  const runBacktest = () => {
    if (validation) return
    extract.reset()
    backtest.mutate({
      strategy: buildRequestStrategy(),
      params: {
        start_date: store.startDate,
        end_date: store.endDate,
        initial_capital: capitalWon,
        initial_capital_currency: 'KRW',
      },
    })
  }

  const runExtract = () => {
    if (validation) return
    backtest.reset()
    extract.mutate({ strategy: buildRequestStrategy(), capital: capitalWon })
  }

  const updateAsset = (i: number, patch: Partial<AssetSlot>) =>
    store.setAssets(s.assets.map((a, idx) => (idx === i ? { ...a, ...patch } : a)))

  return (
    <div className="mx-auto max-w-4xl px-4 py-5 lg:px-6">
      {/* Sub-tab strip */}
      <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-100 pb-2 text-sm">
        <NavLink to="/build?mode=manual" className="rounded-lg px-3 py-1.5 font-medium text-secondary hover:bg-slate-50">
          팩터 전략
        </NavLink>
        <span className="rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-primary">자산배분</span>
        <NavLink to="/allocation/examples" className="rounded-lg px-3 py-1.5 font-medium text-secondary hover:bg-slate-50">
          전략 예시
        </NavLink>
        <NavLink to="/partnership" className="rounded-lg px-3 py-1.5 font-medium text-secondary hover:bg-slate-50">
          파트너십
        </NavLink>
      </div>

      {/* Sticky action bar */}
      <div className="sticky top-[57px] z-30 mb-4 flex items-center justify-end gap-2 rounded-lg border border-slate-100 bg-canvas/90 px-3 py-2 backdrop-blur">
        {validation && <span className="mr-auto text-xs text-down">{validation}</span>}
        <button type="button" className="btn-ghost text-sm" disabled title="라이브러리 저장은 곧 지원됩니다">
          저장하기
        </button>
        <button type="button" className="btn-primary text-sm" disabled={!!validation || backtest.isPending} onClick={runBacktest}>
          {backtest.isPending ? '실행 중…' : '백테스트'}
        </button>
        <button type="button" className="btn-ghost text-sm" disabled={!!validation || extract.isPending} onClick={runExtract}>
          포트 추출
        </button>
      </div>

      <div className="space-y-4">
        {/* Card 1 — 자산배분 설정 */}
        <Card n={1} title="자산배분 설정" required>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="자산배분 알고리즘">
              <select className="input" value={s.algorithm}
                onChange={(e) => store.set({ algorithm: e.target.value as AllocationAlgorithm })}>
                {ALGORITHMS.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            </Field>
            <Field label="초기 투자 금액 (만원)">
              <input type="number" className="input" min={1} value={store.initialCapitalManwon}
                onChange={(e) => store.setCapital(Number(e.target.value))} />
            </Field>
            <Field label="주기 리밸런싱">
              <select className="input" value={s.rebalance_period}
                onChange={(e) => store.set({ rebalance_period: e.target.value as AllocationRebalancePeriod })}>
                {REBALANCE_PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </Field>
            <Field label="밴드 리밸런싱 (%, 0=비활성화)">
              <input type="number" className="input" min={0} max={100} value={s.rebalance_band_pct}
                onChange={(e) => store.set({ rebalance_band_pct: Number(e.target.value) })} />
            </Field>
            <Field label="가중치 배분 방식">
              <div className="relative">
                <select className="input w-full" value={s.weight_scheme ?? 'equal'} disabled={weightLocked}
                  onChange={(e) => store.set({ weight_scheme: e.target.value as WeightScheme })}>
                  {WEIGHT_SCHEMES.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
                </select>
                {weightLocked && <Lock size={13} className="absolute right-8 top-2.5 text-secondary" />}
              </div>
              {weightLocked && <span className="text-[11px] text-tertiary">이 알고리즘은 가중치를 자동으로 계산합니다</span>}
            </Field>
            {s.algorithm === 'vol_target' && (
              <Field label="목표 변동성 (연 %)">
                <input type="number" className="input" min={1} max={100} step={1}
                  value={s.vol_target_annual != null ? Math.round(s.vol_target_annual * 100) : ''}
                  placeholder="예: 10"
                  onChange={(e) => store.set({
                    vol_target_annual: e.target.value === '' ? null : Number(e.target.value) / 100,
                  })} />
                <span className="text-[11px] text-tertiary">목표보다 조용하면 전액 투자, 초과하면 현금 비중으로 낮춥니다</span>
              </Field>
            )}
            {weightLocked && (
              <Field label="추정 기간 (거래일)">
                <input type="number" className="input" min={20} max={1260} step={1}
                  value={s.lookback_days_for_estimation}
                  onChange={(e) => store.set({
                    lookback_days_for_estimation: Math.min(1260, Math.max(20, Number(e.target.value) || 252)),
                  })} />
                <span className="text-[11px] text-tertiary">변동성·상관관계 추정에 쓰는 과거 창 (기본 252 ≈ 1년)</span>
              </Field>
            )}
            <label className="flex items-center gap-2 self-end text-xs text-secondary">
              <input type="checkbox" checked={s.apply_fx} onChange={(e) => store.set({ apply_fx: e.target.checked })} />
              전체 환율 반영 (해외 자산 원화 환산)
            </label>
          </div>
        </Card>

        {/* Card 2 — 자산군 추가 */}
        <Card n={2} title="자산군 추가" required>
          <p className="text-[11px] leading-relaxed text-tertiary">
            상관관계가 낮은 자산을 조합할 때 분산 효과가 큽니다. 예: 주식 지수 ETF + 채권 ETF + 금 + 원자재.
          </p>
          <div className="flex flex-wrap gap-2">
            {ALLOCATION_PRESETS.map((p) => (
              <button key={p.label} type="button" className="chip" onClick={() => store.loadPreset(p)}>
                {p.label}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            {s.assets.map((a, i) => (
              <div key={i} className="flex items-start gap-2">
                <select className="input mt-0 w-16 shrink-0" value={a.market}
                  onChange={(e) => updateAsset(i, { market: e.target.value as Market })}>
                  <option value="KR">KR</option>
                  <option value="US">US</option>
                </select>
                <div className="min-w-0 flex-1">
                  <TickerPicker ticker={a.ticker || '—'} market={a.market}
                    onSelect={(ticker, market) => updateAsset(i, { ticker, market })} />
                </div>
                {isCustom && (
                  <input type="number" className="input w-24" placeholder="%" value={a.target_weight_pct ?? ''}
                    onChange={(e) => updateAsset(i, { target_weight_pct: e.target.value === '' ? null : Number(e.target.value) })} />
                )}
                <button type="button" className="mt-2" aria-label="삭제" disabled={s.assets.length <= 2}
                  onClick={() => store.setAssets(s.assets.filter((_, idx) => idx !== i))}>
                  <Trash2 size={15} className="text-secondary hover:text-down" />
                </button>
              </div>
            ))}
          </div>
          {isCustom && (
            <p className={`text-xs ${Math.abs(weightSum - 100) > 0.01 ? 'text-down' : 'text-secondary'}`}>
              비중 합계: {weightSum.toFixed(1)}% / 100%
            </p>
          )}
          <button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-accent"
            onClick={() => store.setAssets([...s.assets, { ticker: '', market: 'KR', target_weight_pct: null }])}>
            <Plus size={14} /> 자산 추가
          </button>
        </Card>

        {/* Card 3 — 마켓 타이밍 */}
        <MarketTimingCard />

        {/* Card 4 — 기간 설정 */}
        <Card n={4} title="기간 설정" required>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="시작일">
              <input type="date" className="input" value={store.startDate}
                onChange={(e) => store.setPeriod(e.target.value, store.endDate)} />
            </Field>
            <Field label="종료일">
              <input type="date" className="input" value={store.endDate}
                onChange={(e) => store.setPeriod(store.startDate, e.target.value)} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            {[3, 5, 10, 20].map((y) => (
              <button key={y} type="button" className="chip"
                onClick={() => store.setPeriod(ISO(new Date(Date.now() - y * 365 * 864e5)), ISO(new Date()))}>
                최근 {y}년
              </button>
            ))}
          </div>
        </Card>

        <button type="button" className="text-xs text-tertiary hover:text-secondary"
          onClick={() => { if (confirm('설정을 초기화할까요?')) store.reset() }}>
          설정 값 초기화
        </button>

        {backtest.isPending && <Spinner label="자산군 데이터를 받아오는 중입니다…" />}
        {backtest.error && <ErrorNote error={backtest.error} />}
        {backtest.data && <BacktestResultView result={backtest.data} />}

        {extract.isPending && <Spinner label="목표 포트폴리오 계산 중…" />}
        {extract.error && <ErrorNote error={extract.error} />}
        {extract.data && <ExtractResult data={extract.data} />}
      </div>
    </div>
  )
}

/** Card 3 — momentum + reentry market timing. */
function MarketTimingCard() {
  const store = useAllocationBuilder()
  const t = store.strategy.momentum_timing
  const on = !!t

  const toggle = (enabled: boolean) =>
    store.set({
      momentum_timing: enabled
        ? { indicator: 'absolute_momentum', lookback_months: 12, mode: 'per_asset',
            safe_haven_ticker: '', safe_haven_market: 'KR', threshold: 0, canary_market: 'US' }
        : null,
    })
  const patch = (p: Partial<NonNullable<typeof t>>) => t && store.set({ momentum_timing: { ...t, ...p } })

  return (
    <Card n={3} title="마켓 타이밍 설정" defaultOpen={false}>
      <label className="flex items-center gap-2 text-sm text-secondary">
        <input type="checkbox" checked={on} onChange={(e) => toggle(e.target.checked)} />
        모멘텀 마켓 타이밍 적용 (신호가 음(−)이면 위험회피 자산으로 이동)
      </label>
      {on && t && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="모멘텀 지표">
            <select className="input" value={t.indicator} onChange={(e) => patch({ indicator: e.target.value as typeof t.indicator })}>
              <option value="absolute_momentum">절대 모멘텀</option>
              <option value="sma_cross">이동평균선</option>
              <option value="13612w">13612W</option>
            </select>
          </Field>
          <Field label="모멘텀 계산 기간 (개월)">
            <input type="number" className="input" min={1} max={36} value={t.lookback_months}
              onChange={(e) => patch({ lookback_months: Number(e.target.value) })} />
          </Field>
          <Field label="적용 방식">
            <select className="input" value={t.mode} onChange={(e) => patch({ mode: e.target.value as typeof t.mode })}>
              <option value="per_asset">개별 자산</option>
              <option value="canary">카나리 자산</option>
            </select>
          </Field>
          {t.mode === 'canary' && (
            <Field label="카나리 자산">
              <TickerPicker ticker={t.canary_ticker || '—'} market={t.canary_market}
                onSelect={(ticker, market) => patch({ canary_ticker: ticker, canary_market: market })} />
            </Field>
          )}
          <Field label="위험회피 자산 (safe-haven)">
            <TickerPicker ticker={t.safe_haven_ticker || '—'} market={t.safe_haven_market}
              onSelect={(ticker, market) => patch({ safe_haven_ticker: ticker, safe_haven_market: market })} />
          </Field>
        </div>
      )}
    </Card>
  )
}

function ExtractResult({ data }: { data: import('../schemas/allocation').ExtractPortfolioResponse }) {
  return (
    <div className="card overflow-x-auto p-4">
      <h3 className="mb-1 text-sm font-semibold text-primary">포트 추출 / Target portfolio</h3>
      <p className="mb-3 text-xs text-secondary">
        기준일 {data.as_of_date} · 총 {Math.round(data.total_krw).toLocaleString()}원 · 잔여 현금 {Math.round(data.cash_remainder).toLocaleString()}원
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-secondary">
            <th className="p-2">종목</th><th className="p-2 text-right">비중</th>
            <th className="p-2 text-right">가격(원)</th><th className="p-2 text-right">수량</th>
            <th className="p-2 text-right">금액(원)</th>
          </tr>
        </thead>
        <tbody>
          {data.holdings.map((h) => (
            <tr key={`${h.market}-${h.ticker}`} className="border-t border-slate-100">
              <td className="p-2"><span className="font-mono text-accent">{h.ticker}</span> <span className="text-secondary">{h.name}</span></td>
              <td className="p-2 text-right tabular-nums">{(h.weight * 100).toFixed(1)}%</td>
              <td className="p-2 text-right tabular-nums">{Math.round(h.price).toLocaleString()}</td>
              <td className="p-2 text-right tabular-nums">{h.target_shares}</td>
              <td className="p-2 text-right tabular-nums">{Math.round(h.target_krw).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
