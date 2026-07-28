import { Star, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useWatchlistQuotes } from '../api/client'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { SnapshotRow } from '../schemas/market'
import { useWatchlist } from '../stores/watchlist'
import { formatPrice } from '../utils/format'

function Pct({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value)) return <span className="text-slate-300">—</span>
  const cls = value > 0 ? 'text-up' : value < 0 ? 'text-down' : 'text-secondary'
  return <span className={cls}>{`${value > 0 ? '+' : ''}${value.toFixed(1)}%`}</span>
}

export function WatchlistPage() {
  const items = useWatchlist((s) => s.items)
  const remove = useWatchlist((s) => s.remove)
  const { data, isFetching, error } = useWatchlistQuotes(items)

  const quoteFor = (ticker: string, market: string): SnapshotRow | undefined =>
    data?.rows.find((r) => r.ticker === ticker && r.market === market)

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-6 lg:px-6">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-primary">관심목록 / Watchlist</h1>
        </header>
        <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
          <Star className="h-8 w-8 text-tertiary" />
          <p className="text-sm text-secondary">
            아직 관심 종목이 없습니다.
            <br />
            차트 페이지에서 <Star className="mx-1 inline h-3.5 w-3.5 -translate-y-px" /> 별 아이콘을 눌러 추가하세요.
          </p>
          <Link to="/chart/AAPL?market=US" className="btn-outline mt-1">
            차트로 이동
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-primary">관심목록 / Watchlist</h1>
          <p className="mt-1 text-sm text-secondary">저장한 종목의 최근 성과입니다. {items.length}개 종목.</p>
        </div>
        {isFetching && <Spinner />}
      </header>

      {error && <ErrorNote error={error} />}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs text-secondary">
              <th className="px-3 py-2.5 text-left font-medium">종목</th>
              <th className="px-3 py-2.5 text-right font-medium">가격</th>
              <th className="px-3 py-2.5 text-right font-medium">1주</th>
              <th className="px-3 py-2.5 text-right font-medium">1개월</th>
              <th className="px-3 py-2.5 text-right font-medium">3개월</th>
              <th className="px-3 py-2.5 text-right font-medium">1년</th>
              <th className="px-3 py-2.5 text-right font-medium">YTD</th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const q = quoteFor(item.ticker, item.market)
              const name = q?.name_ko || q?.name_en || item.name || item.ticker
              return (
                <tr key={`${item.market}-${item.ticker}`} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                  <td className="px-3 py-2.5">
                    <Link to={`/chart/${item.ticker}?market=${item.market}`} className="block">
                      <div className="max-w-[220px] truncate font-medium text-primary">{name}</div>
                      <div className="font-mono text-xs text-tertiary">
                        {item.ticker} · {item.market}
                      </div>
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-secondary">
                    {q ? formatPrice(q.price, item.market) : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono"><Pct value={q?.ret_1w} /></td>
                  <td className="px-3 py-2.5 text-right font-mono"><Pct value={q?.ret_1m} /></td>
                  <td className="px-3 py-2.5 text-right font-mono"><Pct value={q?.ret_3m} /></td>
                  <td className="px-3 py-2.5 text-right font-mono"><Pct value={q?.ret_12m} /></td>
                  <td className="px-3 py-2.5 text-right font-mono"><Pct value={q?.ret_ytd} /></td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      type="button"
                      className="text-tertiary hover:text-down"
                      title="관심목록에서 제거"
                      onClick={() => remove(item.ticker, item.market)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
