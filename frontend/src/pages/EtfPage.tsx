import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useMarketSnapshot } from '../api/client'
import { MarketToggle } from '../components/market/MarketToggle'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { SnapshotRow } from '../schemas/market'
import type { Market } from '../schemas/strategy'
import { formatPrice } from '../utils/format'

type SortKey = 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m' | 'ret_ytd' | 'vol_ann'

const COLS: { key: SortKey; label: string }[] = [
  { key: 'ret_1m', label: '1개월' },
  { key: 'ret_3m', label: '3개월' },
  { key: 'ret_6m', label: '6개월' },
  { key: 'ret_12m', label: '1년' },
  { key: 'ret_ytd', label: 'YTD' },
  { key: 'vol_ann', label: '변동성' },
]

function Pct({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value)) return <span className="text-slate-300">—</span>
  const cls = value > 0 ? 'text-up' : value < 0 ? 'text-down' : 'text-secondary'
  return <span className={cls}>{`${value > 0 ? '+' : ''}${value.toFixed(1)}%`}</span>
}

export function EtfPage() {
  const [market, setMarket] = useState<Market>('KR')
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('ret_12m')
  const { data, isFetching, error } = useMarketSnapshot(market)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data?.rows ?? [])
      .filter((r) => r.kind === 'etf')
      .filter(
        (r) =>
          !q ||
          r.ticker.toLowerCase().includes(q) ||
          (r.name_ko ?? '').toLowerCase().includes(q) ||
          r.name_en.toLowerCase().includes(q),
      )
      .sort((a, b) => {
        const av = a[sortKey] ?? -Infinity
        const bv = b[sortKey] ?? -Infinity
        return sortKey === 'vol_ann' ? av - bv : bv - av // returns desc, vol asc
      })
  }, [data, query, sortKey])

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-primary">ETF</h1>
          <p className="mt-1 text-sm text-secondary">
            상장 ETF의 기간별 성과. 이름으로 검색하고, 열 제목을 눌러 정렬하세요.
          </p>
        </div>
        <MarketToggle value={market} onChange={setMarket} />
      </header>

      <input
        className="input max-w-sm"
        placeholder="ETF 이름 · 티커 검색 (예: 나스닥, KODEX, QQQ)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {error && <ErrorNote error={error} />}

      {isFetching && !data ? (
        <div className="flex items-center gap-3 py-16 text-sm text-secondary">
          <Spinner /> ETF 시세를 불러오는 중…
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-secondary">
                <th className="px-3 py-2.5 text-left font-medium">ETF</th>
                <th className="px-3 py-2.5 text-right font-medium">가격</th>
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className={`cursor-pointer select-none px-3 py-2.5 text-right font-medium hover:text-primary ${
                      sortKey === c.key ? 'text-accent' : ''
                    }`}
                    onClick={() => setSortKey(c.key)}
                  >
                    {c.label}
                    {sortKey === c.key ? ' ↓' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <EtfRow key={r.ticker} row={r} market={market} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={COLS.length + 2} className="py-10 text-center text-sm text-tertiary">
                    해당하는 ETF가 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function EtfRow({ row, market }: { row: SnapshotRow; market: Market }) {
  return (
    <tr className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
      <td className="px-3 py-2.5">
        <Link to={`/chart/${row.ticker}?market=${market}`} className="block">
          <div className="max-w-[240px] truncate font-medium text-primary">
            {row.name_ko || row.name_en}
          </div>
          <div className="font-mono text-xs text-tertiary">{row.ticker}</div>
        </Link>
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-secondary">{formatPrice(row.price, market)}</td>
      <td className="px-3 py-2.5 text-right font-mono"><Pct value={row.ret_1m} /></td>
      <td className="px-3 py-2.5 text-right font-mono"><Pct value={row.ret_3m} /></td>
      <td className="px-3 py-2.5 text-right font-mono"><Pct value={row.ret_6m} /></td>
      <td className="px-3 py-2.5 text-right font-mono"><Pct value={row.ret_12m} /></td>
      <td className="px-3 py-2.5 text-right font-mono"><Pct value={row.ret_ytd} /></td>
      <td className="px-3 py-2.5 text-right font-mono text-secondary">
        {row.vol_ann != null ? `${row.vol_ann.toFixed(0)}%` : '—'}
      </td>
    </tr>
  )
}
