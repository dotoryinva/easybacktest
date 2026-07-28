import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useMarketSnapshot } from '../api/client'
import { MarketToggle } from '../components/market/MarketToggle'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { SnapshotRow } from '../schemas/market'
import type { Market } from '../schemas/strategy'
import { formatPrice } from '../utils/format'

type MetricKey =
  | 'ret_1m' | 'ret_3m' | 'ret_12m' | 'ret_ytd'
  | 'rsi_14' | 'vol_ann' | 'dist_sma200' | 'dist_high52w'

const METRICS: { key: MetricKey; label: string; unit: string }[] = [
  { key: 'ret_1m', label: '1개월 수익률', unit: '%' },
  { key: 'ret_3m', label: '3개월 수익률', unit: '%' },
  { key: 'ret_12m', label: '1년 수익률', unit: '%' },
  { key: 'ret_ytd', label: 'YTD 수익률', unit: '%' },
  { key: 'rsi_14', label: 'RSI(14)', unit: '' },
  { key: 'vol_ann', label: '연변동성', unit: '%' },
  { key: 'dist_sma200', label: '200일선 대비', unit: '%' },
  { key: 'dist_high52w', label: '52주 고점 대비', unit: '%' },
]

type Bounds = { min: string; max: string }
type Filters = Partial<Record<MetricKey, Bounds>>

const PRESETS: { label: string; filters: Filters }[] = [
  { label: '상승 모멘텀', filters: { ret_3m: { min: '0', max: '' }, dist_sma200: { min: '0', max: '' } } },
  { label: '과매도 반등', filters: { rsi_14: { min: '', max: '35' } } },
  { label: '신고가 근접', filters: { dist_high52w: { min: '-5', max: '' } } },
  { label: '저변동성', filters: { vol_ann: { min: '', max: '25' } } },
]

function Pct({ value, suffix = '%' }: { value: number | null | undefined; suffix?: string }) {
  if (value == null || !Number.isFinite(value)) return <span className="text-slate-300">—</span>
  const cls = suffix === '%' && value !== 0 ? (value > 0 ? 'text-up' : 'text-down') : 'text-secondary'
  return <span className={cls}>{`${value > 0 && suffix === '%' ? '+' : ''}${value.toFixed(suffix ? 1 : 0)}${suffix}`}</span>
}

export function ScreenerPage() {
  const [market, setMarket] = useState<Market>('KR')
  const [kind, setKind] = useState<'all' | 'stock' | 'etf'>('all')
  const [filters, setFilters] = useState<Filters>({})
  const [sortKey, setSortKey] = useState<MetricKey>('ret_3m')
  const { data, isFetching, error } = useMarketSnapshot(market)

  const setBound = (key: MetricKey, side: 'min' | 'max', value: string) =>
    setFilters((f) => ({ ...f, [key]: { ...{ min: '', max: '' }, ...f[key], [side]: value } }))

  const rows = useMemo(() => {
    const pass = (r: SnapshotRow) => {
      if (kind !== 'all' && r.kind !== kind) return false
      for (const { key } of METRICS) {
        const b = filters[key]
        if (!b) continue
        const v = r[key]
        const min = b.min === '' ? null : Number(b.min)
        const max = b.max === '' ? null : Number(b.max)
        if (min != null || max != null) {
          if (v == null || !Number.isFinite(v)) return false
          if (min != null && v < min) return false
          if (max != null && v > max) return false
        }
      }
      return true
    }
    return (data?.rows ?? [])
      .filter(pass)
      .sort((a, b) => (b[sortKey] ?? -Infinity) - (a[sortKey] ?? -Infinity))
  }, [data, filters, kind, sortKey])

  const activeCount = Object.values(filters).filter((b) => b && (b.min !== '' || b.max !== '')).length

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 lg:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-primary">스크리너 / Screener</h1>
          <p className="mt-1 text-sm text-secondary">
            가격·모멘텀 지표로 종목을 걸러냅니다. 최신 시세 기준 스냅샷입니다.
          </p>
        </div>
        <MarketToggle value={market} onChange={setMarket} />
      </header>

      <div className="card space-y-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="segmented">
            {(['all', 'stock', 'etf'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`segmented-item ${kind === k ? 'segmented-item-active' : ''}`}
              >
                {k === 'all' ? '전체' : k === 'stock' ? '주식' : 'ETF'}
              </button>
            ))}
          </div>
          <span className="text-xs text-tertiary">빠른 필터:</span>
          {PRESETS.map((p) => (
            <button key={p.label} type="button" className="chip hover:border-accent hover:text-accent"
              onClick={() => setFilters(p.filters)}>
              {p.label}
            </button>
          ))}
          {activeCount > 0 && (
            <button type="button" className="chip text-down hover:border-down" onClick={() => setFilters({})}>
              초기화 ({activeCount})
            </button>
          )}
        </div>

        <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          {METRICS.map((m) => (
            <div key={m.key} className="flex items-center gap-2">
              <span className="w-28 shrink-0 text-xs text-secondary">{m.label}</span>
              <input
                className="input h-8 px-2 text-xs" placeholder="min" inputMode="numeric"
                value={filters[m.key]?.min ?? ''}
                onChange={(e) => setBound(m.key, 'min', e.target.value)}
              />
              <span className="text-tertiary">~</span>
              <input
                className="input h-8 px-2 text-xs" placeholder="max" inputMode="numeric"
                value={filters[m.key]?.max ?? ''}
                onChange={(e) => setBound(m.key, 'max', e.target.value)}
              />
            </div>
          ))}
        </div>
      </div>

      {error && <ErrorNote error={error} />}

      {isFetching && !data ? (
        <div className="flex items-center gap-3 py-16 text-sm text-secondary">
          <Spinner /> 시세를 불러오는 중…
        </div>
      ) : (
        <>
          <div className="text-xs text-tertiary">결과 {rows.length}개 · {data?.rows[0]?.as_of ?? ''} 기준</div>
          <div className="card overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-xs text-secondary">
                  <th className="px-3 py-2.5 text-left font-medium">종목</th>
                  <th className="px-3 py-2.5 text-right font-medium">가격</th>
                  {METRICS.map((m) => (
                    <th
                      key={m.key}
                      className={`cursor-pointer select-none px-3 py-2.5 text-right font-medium hover:text-primary ${
                        sortKey === m.key ? 'text-accent' : ''
                      }`}
                      onClick={() => setSortKey(m.key)}
                    >
                      {m.label.replace(' 수익률', '').replace(' 대비', '')}
                      {sortKey === m.key ? ' ↓' : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ticker} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                    <td className="px-3 py-2.5">
                      <Link to={`/chart/${r.ticker}?market=${market}`} className="block">
                        <div className="max-w-[200px] truncate font-medium text-primary">
                          {r.name_ko || r.name_en}
                        </div>
                        <div className="font-mono text-xs text-tertiary">
                          {r.ticker}
                          <span className="ml-1 text-slate-300">{r.kind === 'etf' ? 'ETF' : ''}</span>
                        </div>
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-secondary">{formatPrice(r.price, market)}</td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.ret_1m} /></td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.ret_3m} /></td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.ret_12m} /></td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.ret_ytd} /></td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.rsi_14} suffix="" /></td>
                    <td className="px-3 py-2.5 text-right font-mono text-secondary">
                      {r.vol_ann != null ? `${r.vol_ann.toFixed(0)}%` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.dist_sma200} /></td>
                    <td className="px-3 py-2.5 text-right font-mono"><Pct value={r.dist_high52w} /></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={METRICS.length + 2} className="py-10 text-center text-sm text-tertiary">
                      조건에 맞는 종목이 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
