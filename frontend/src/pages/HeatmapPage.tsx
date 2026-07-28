import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useMarketSnapshot } from '../api/client'
import { heatColor, heatText, MarketToggle } from '../components/market/MarketToggle'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { ReturnKey, SnapshotRow } from '../schemas/market'
import type { Market } from '../schemas/strategy'

const PERIODS: { key: ReturnKey; label: string; cap: number }[] = [
  { key: 'ret_1w', label: '1주', cap: 6 },
  { key: 'ret_1m', label: '1개월', cap: 12 },
  { key: 'ret_3m', label: '3개월', cap: 20 },
  { key: 'ret_6m', label: '6개월', cap: 30 },
  { key: 'ret_12m', label: '1년', cap: 45 },
  { key: 'ret_ytd', label: 'YTD', cap: 30 },
]

const KIND_LABEL: Record<string, string> = { stock: '주식', etf: 'ETF', index: '지수' }

export function HeatmapPage() {
  const [market, setMarket] = useState<Market>('KR')
  const [periodKey, setPeriodKey] = useState<ReturnKey>('ret_1m')
  const { data, isFetching, error } = useMarketSnapshot(market)

  const period = PERIODS.find((p) => p.key === periodKey)!

  const groups = useMemo(() => {
    const rows = (data?.rows ?? []).filter((r) => r[periodKey] != null)
    const byKind = (k: string) =>
      rows
        .filter((r) => r.kind === k)
        .sort((a, b) => (b[periodKey] ?? 0) - (a[periodKey] ?? 0))
    return [
      { kind: 'stock', rows: byKind('stock') },
      { kind: 'etf', rows: byKind('etf') },
    ].filter((g) => g.rows.length > 0)
  }, [data, periodKey])

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 lg:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-primary">히트맵 / Heatmap</h1>
          <p className="mt-1 text-sm text-secondary">
            기간별 수익률을 색으로 표현합니다. 초록은 상승, 빨강은 하락. 타일을 누르면 차트로 이동합니다.
          </p>
        </div>
        <MarketToggle value={market} onChange={setMarket} />
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <div className="segmented">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPeriodKey(p.key)}
              className={`segmented-item ${periodKey === p.key ? 'segmented-item-active' : ''}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-xs text-tertiary">
            {data.rows.length}개 종목 · {data.rows[0]?.as_of ?? ''} 기준
          </span>
        )}
      </div>

      {error && <ErrorNote error={error} />}

      {isFetching && !data ? (
        <div className="flex items-center gap-3 py-16 text-sm text-secondary">
          <Spinner /> 시세를 불러오는 중… (최초 실행은 데이터 준비로 몇 초 걸릴 수 있습니다)
        </div>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.kind}>
              <h2 className="mb-2 text-sm font-semibold text-secondary">
                {KIND_LABEL[g.kind]} <span className="text-tertiary">({g.rows.length})</span>
              </h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                {g.rows.map((r) => (
                  <Tile key={r.ticker} row={r} periodKey={periodKey} cap={period.cap} market={market} />
                ))}
              </div>
            </section>
          ))}
          {groups.length === 0 && !isFetching && (
            <p className="py-10 text-center text-sm text-tertiary">표시할 데이터가 없습니다.</p>
          )}
        </div>
      )}
    </div>
  )
}

function Tile({
  row,
  periodKey,
  cap,
  market,
}: {
  row: SnapshotRow
  periodKey: ReturnKey
  cap: number
  market: Market
}) {
  const value = row[periodKey]
  const name = row.name_ko || row.name_en
  return (
    <Link
      to={`/chart/${row.ticker}?market=${market}`}
      className="flex aspect-[4/3] flex-col justify-between rounded-lg p-2.5 transition hover:ring-2 hover:ring-accent/50"
      style={{ background: heatColor(value, cap), color: heatText(value, cap) }}
      title={`${name} (${row.ticker})`}
    >
      <div className="min-w-0">
        <div className="truncate text-xs font-semibold leading-tight">{name}</div>
        <div className="font-mono text-[10px] opacity-70">{row.ticker}</div>
      </div>
      <div className="font-mono text-sm font-bold">
        {value != null ? `${value > 0 ? '+' : ''}${value.toFixed(1)}%` : '—'}
      </div>
    </Link>
  )
}
