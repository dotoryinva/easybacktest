import { Plus, X } from 'lucide-react'
import { useState } from 'react'

import {
  useQuantBacktest,
  type FilterOperator,
  type QuantFactor,
  type QuantPortfolioStrategy,
} from '../../../api/client'
import type { RebalanceFrequency } from '../../../api/client'
import { BacktestResultView } from '../../backtest/BacktestResultView'
import { ErrorNote } from '../../ui/ErrorNote'
import { Spinner } from '../../ui/Spinner'
import type { Market } from '../../../schemas/strategy'

// Factors the engine can compute live from cached OHLCV. Fundamentals are listed for
// completeness but disabled — the KR fundamentals source (pykrx) is currently broken.
type FactorMeta = { value: QuantFactor; label: string; live: boolean }
const FACTOR_GROUPS: { group: string; factors: FactorMeta[] }[] = [
  {
    group: '모멘텀 / 가격',
    factors: [
      { value: 'momentum_1m', label: '1개월 모멘텀', live: true },
      { value: 'momentum_3m', label: '3개월 모멘텀', live: true },
      { value: 'momentum_6m', label: '6개월 모멘텀', live: true },
      { value: 'momentum_12m', label: '12개월 모멘텀', live: true },
      { value: 'momentum_12m_1m', label: '12-1개월 모멘텀', live: true },
      { value: 'rsi_14', label: 'RSI(14)', live: true },
      { value: 'dist_sma_200', label: '200일선 이격도', live: true },
      { value: 'dist_high_52w', label: '52주 고점 대비', live: true },
    ],
  },
  {
    group: '밸류에이션 (데이터 준비 중)',
    factors: [
      { value: 'per', label: 'PER', live: false },
      { value: 'pbr', label: 'PBR', live: false },
      { value: 'earnings_yield', label: '이익수익률', live: false },
      { value: 'book_yield', label: '순자산수익률', live: false },
      { value: 'dividend_yield', label: '배당수익률', live: false },
    ],
  },
  {
    group: '수익성 (데이터 준비 중)',
    factors: [
      { value: 'roe', label: 'ROE', live: false },
      { value: 'roa', label: 'ROA', live: false },
    ],
  },
]

const OPERATORS: { value: FilterOperator; label: string }[] = [
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '>=', label: '≥' },
  { value: '<=', label: '≤' },
  { value: 'top_pct', label: '상위 %' },
  { value: 'bottom_pct', label: '하위 %' },
]

function FactorSelect({
  value,
  onChange,
}: {
  value: QuantFactor
  onChange: (v: QuantFactor) => void
}) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value as QuantFactor)}>
      {FACTOR_GROUPS.map((g) => (
        <optgroup key={g.group} label={g.group}>
          {g.factors.map((f) => (
            <option key={f.value} value={f.value} disabled={!f.live}>
              {f.label}
              {f.live ? '' : ' 🔒'}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}

const ISO = (d: Date) => d.toISOString().slice(0, 10)

type FilterRow = { factor: QuantFactor; op: FilterOperator; value: number }
type RankRow = { factor: QuantFactor; direction: 'asc' | 'desc'; weight: number }

export function QuantBuilder() {
  const [market, setMarket] = useState<Market>('KR')
  const [boards, setBoards] = useState<string[]>(['KOSPI', 'KOSDAQ'])
  const [excludeEtf, setExcludeEtf] = useState(true)
  const [excludePreferred, setExcludePreferred] = useState(true)

  const [filters, setFilters] = useState<FilterRow[]>([])
  const [ranking, setRanking] = useState<RankRow[]>([
    { factor: 'momentum_12m_1m', direction: 'desc', weight: 1 },
  ])

  const [numHoldings, setNumHoldings] = useState(20)
  const [weighting, setWeighting] = useState<'equal' | 'rank' | 'market_cap'>('equal')
  const [frequency, setFrequency] = useState<RebalanceFrequency>('monthly')

  const [start, setStart] = useState('2022-01-03')
  const [end, setEnd] = useState(ISO(new Date()))
  const [capital, setCapital] = useState(100_000_000)

  const mutation = useQuantBacktest()

  const boardOptions = market === 'KR' ? ['KOSPI', 'KOSDAQ', 'KONEX'] : ['US']
  const toggleBoard = (b: string) =>
    setBoards((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]))

  const applyMomentumPreset = () => {
    setFilters([])
    setRanking([{ factor: 'momentum_12m_1m', direction: 'desc', weight: 1 }])
    setNumHoldings(20)
    setWeighting('equal')
    setFrequency('monthly')
    mutation.reset()
  }

  const run = () => {
    const strategy: QuantPortfolioStrategy = {
      name: '퀀트 포트폴리오',
      universe: {
        market,
        boards: market === 'KR' ? boards : ['US'],
        exclude_etf: excludeEtf,
        exclude_preferred: excludePreferred,
      },
      filters: filters.map((f) => ({ factor: f.factor, op: f.op, value: f.value })),
      ranking,
      portfolio: { num_holdings: numHoldings, weighting, max_position_pct: 0.2 },
      rebalance: { frequency },
    }
    mutation.mutate({
      strategy,
      params: {
        market,
        start_date: start,
        end_date: end,
        initial_capital: capital,
        benchmark: market === 'KR' ? 'KS200' : '^GSPC',
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button type="button" className="chip" onClick={applyMomentumPreset}>
          모멘텀 상위 20
        </button>
      </div>

      {/* 1. Universe */}
      <section className="card space-y-3 p-4">
        <h3 className="text-sm font-semibold text-primary">1. 유니버스 / Universe</h3>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <select
            className="input w-28"
            value={market}
            onChange={(e) => {
              const m = e.target.value as Market
              setMarket(m)
              setBoards(m === 'KR' ? ['KOSPI', 'KOSDAQ'] : ['US'])
            }}
          >
            <option value="KR">한국 / KR</option>
            <option value="US">미국 / US</option>
          </select>
          {boardOptions.map((b) => (
            <label key={b} className="flex items-center gap-1.5 text-xs text-secondary">
              <input
                type="checkbox"
                checked={boards.includes(b)}
                onChange={() => toggleBoard(b)}
              />
              {b}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-secondary">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={excludeEtf} onChange={(e) => setExcludeEtf(e.target.checked)} />
            ETF 제외
          </label>
          {market === 'KR' && (
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={excludePreferred}
                onChange={(e) => setExcludePreferred(e.target.checked)}
              />
              우선주 제외
            </label>
          )}
        </div>
      </section>

      {/* 2. Filters */}
      <section className="card space-y-3 p-4">
        <h3 className="text-sm font-semibold text-primary">2. 필터 / Filters (모두 만족)</h3>
        {filters.length === 0 && (
          <p className="text-xs text-tertiary">필터 없음 — 전체 유니버스를 대상으로 랭킹합니다.</p>
        )}
        {filters.map((f, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <div className="min-w-40 flex-1">
              <FactorSelect
                value={f.factor}
                onChange={(v) => setFilters((p) => p.map((r, idx) => (idx === i ? { ...r, factor: v } : r)))}
              />
            </div>
            <select
              className="input w-24"
              value={f.op}
              onChange={(e) =>
                setFilters((p) => p.map((r, idx) => (idx === i ? { ...r, op: e.target.value as FilterOperator } : r)))
              }
            >
              {OPERATORS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <input
              className="input w-28"
              type="number"
              step="any"
              value={f.value}
              onChange={(e) =>
                setFilters((p) => p.map((r, idx) => (idx === i ? { ...r, value: Number(e.target.value) } : r)))
              }
            />
            <button type="button" onClick={() => setFilters((p) => p.filter((_, idx) => idx !== i))} aria-label="삭제">
              <X size={15} className="text-secondary hover:text-primary" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-medium text-accent"
          onClick={() => setFilters((p) => [...p, { factor: 'momentum_3m', op: 'top_pct', value: 50 }])}
        >
          <Plus size={14} /> 필터 추가
        </button>
      </section>

      {/* 3. Ranking */}
      <section className="card space-y-3 p-4">
        <h3 className="text-sm font-semibold text-primary">3. 팩터 랭킹 / Ranking</h3>
        {ranking.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <div className="min-w-40 flex-1">
              <FactorSelect
                value={r.factor}
                onChange={(v) => setRanking((p) => p.map((row, idx) => (idx === i ? { ...row, factor: v } : row)))}
              />
            </div>
            <select
              className="input w-36"
              value={r.direction}
              onChange={(e) =>
                setRanking((p) =>
                  p.map((row, idx) => (idx === i ? { ...row, direction: e.target.value as 'asc' | 'desc' } : row)),
                )
              }
            >
              <option value="desc">높을수록 좋음</option>
              <option value="asc">낮을수록 좋음</option>
            </select>
            <input
              className="input w-24"
              type="number"
              min={0}
              step="0.5"
              value={r.weight}
              onChange={(e) =>
                setRanking((p) => p.map((row, idx) => (idx === i ? { ...row, weight: Number(e.target.value) } : row)))
              }
            />
            <button
              type="button"
              onClick={() => setRanking((p) => (p.length > 1 ? p.filter((_, idx) => idx !== i) : p))}
              aria-label="삭제"
              disabled={ranking.length <= 1}
            >
              <X size={15} className="text-secondary hover:text-primary" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-medium text-accent"
          onClick={() => setRanking((p) => [...p, { factor: 'momentum_3m', direction: 'desc', weight: 1 }])}
        >
          <Plus size={14} /> 랭킹 팩터 추가
        </button>
      </section>

      {/* 4 + 5. Portfolio & rebalance */}
      <section className="card space-y-3 p-4">
        <h3 className="text-sm font-semibold text-primary">4. 포트폴리오 & 리밸런싱</h3>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-secondary">
            종목 수
            <input
              className="input mt-1 w-24"
              type="number"
              min={1}
              max={200}
              value={numHoldings}
              onChange={(e) => setNumHoldings(Number(e.target.value))}
            />
          </label>
          <label className="text-xs text-secondary">
            비중 방식
            <select
              className="input mt-1"
              value={weighting}
              onChange={(e) => setWeighting(e.target.value as typeof weighting)}
            >
              <option value="equal">동일가중</option>
              <option value="rank">랭크가중</option>
              <option value="market_cap">시총가중</option>
            </select>
          </label>
          <label className="text-xs text-secondary">
            리밸런싱
            <select
              className="input mt-1"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as RebalanceFrequency)}
            >
              <option value="monthly">매월</option>
              <option value="quarterly">매분기</option>
              <option value="semiannual">매반기</option>
              <option value="annual">매년</option>
            </select>
          </label>
        </div>
      </section>

      {/* 6. Backtest params */}
      <section className="card space-y-3 p-4">
        <h3 className="text-sm font-semibold text-primary">5. 백테스트 파라미터</h3>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-secondary">
            시작 / Start
            <input type="date" className="input mt-1" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="text-xs text-secondary">
            종료 / End
            <input type="date" className="input mt-1" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <label className="text-xs text-secondary">
            초기 자본
            <input
              type="number"
              className="input mt-1 w-40"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
            />
          </label>
          <button type="button" className="btn-primary" disabled={mutation.isPending} onClick={run}>
            {mutation.isPending ? '실행 중…' : '백테스트 실행'}
          </button>
        </div>
        <p className="text-xs text-tertiary">
          백테스트는 이미 조회된(캐시된) 종목을 대상으로 실행됩니다. 더 많은 종목을 포함하려면 해당
          종목의 차트를 먼저 열어 데이터를 캐시하세요. 밸류에이션·수익성 팩터(🔒)는 재무 데이터 연동 후
          제공됩니다.
        </p>
      </section>

      {mutation.isPending && <Spinner label="유니버스를 평가하고 리밸런싱하는 중…" />}
      {mutation.error && <ErrorNote error={mutation.error} />}
      {mutation.data && <BacktestResultView result={mutation.data} />}
    </div>
  )
}
