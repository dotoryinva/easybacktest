import { useMemo, useState } from 'react'

import type { Trade } from '../../schemas/backtest'
import type { Market } from '../../schemas/strategy'
import { downloadCsv, toCsv } from '../../utils/csv'
import { EXIT_REASON_LABELS, formatPct, formatPrice, toneClass } from '../../utils/format'

type Props = {
  trades: Trade[]
  market: Market
  selected?: Trade | null
  onSelect?: (trade: Trade | null) => void
}

type SortKey = keyof Pick<
  Trade,
  'buy_date' | 'sell_date' | 'buy_price' | 'sell_price' | 'shares' | 'pnl' | 'pnl_pct' | 'exit_reason'
>

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'buy_date', label: 'Buy date' },
  { key: 'buy_price', label: 'Buy', numeric: true },
  { key: 'sell_date', label: 'Sell date' },
  { key: 'sell_price', label: 'Sell', numeric: true },
  { key: 'shares', label: 'Shares', numeric: true },
  { key: 'pnl', label: 'P&L', numeric: true },
  { key: 'pnl_pct', label: 'P&L %', numeric: true },
  { key: 'exit_reason', label: 'Exit' },
]

const PAGE_SIZE = 25

export function TradeLogTable({ trades, market, selected, onSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('buy_date')
  const [ascending, setAscending] = useState(true)
  const [page, setPage] = useState(0)

  const sorted = useMemo(() => {
    const copy = [...trades]
    copy.sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]
      if (typeof left === 'number' && typeof right === 'number')
        return ascending ? left - right : right - left
      return ascending
        ? String(left).localeCompare(String(right))
        : String(right).localeCompare(String(left))
    })
    return copy
  }, [trades, sortKey, ascending])

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const rows = sorted.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setAscending((prev) => !prev)
    else {
      setSortKey(key)
      setAscending(true)
    }
    setPage(0)
  }

  if (trades.length === 0) {
    return (
      <p className="rounded-lg border border-ink-700 bg-ink-850 px-4 py-6 text-center text-sm text-slate-500">
        이 조건으로는 거래가 발생하지 않았습니다 / This strategy produced no trades in the
        selected period.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-ink-700">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-ink-850">
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  className={`px-3 py-2 font-medium text-slate-400 ${
                    column.numeric ? 'text-right' : 'text-left'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    className="inline-flex items-center gap-1 hover:text-primary"
                  >
                    {column.label}
                    {sortKey === column.key && <span>{ascending ? '↑' : '↓'}</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((trade, index) => {
              const isSelected =
                selected?.buy_date === trade.buy_date && selected?.sell_date === trade.sell_date
              return (
                <tr
                  key={`${trade.buy_date}-${trade.sell_date}-${index}`}
                  onClick={() => onSelect?.(isSelected ? null : trade)}
                  className={`cursor-pointer border-t border-ink-700 transition-colors ${
                    isSelected ? 'bg-accent/15' : 'hover:bg-ink-850'
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-secondary">{trade.buy_date}</td>
                  <td className="px-3 py-2 text-right font-mono text-secondary">
                    {formatPrice(trade.buy_price, market)}
                  </td>
                  <td className="px-3 py-2 font-mono text-secondary">{trade.sell_date}</td>
                  <td className="px-3 py-2 text-right font-mono text-secondary">
                    {formatPrice(trade.sell_price, market)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-slate-400">
                    {trade.shares.toLocaleString()}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${toneClass(trade.pnl)}`}>
                    {formatPrice(trade.pnl, market)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono ${toneClass(trade.pnl)}`}>
                    {formatPct(trade.pnl_pct)}
                  </td>
                  <td className="px-3 py-2 text-slate-400">
                    {EXIT_REASON_LABELS[trade.exit_reason] ?? trade.exit_reason}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          {sorted.length} trades
          {onSelect && ' · click a row to mark it on the equity curve'}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-ghost px-2 py-1 text-xs"
            onClick={() =>
              downloadCsv(
                'trades',
                toCsv(trades as unknown as Record<string, unknown>[]),
              )
            }
          >
            CSV
          </button>
          {pageCount > 1 && (
            <>
              <button
                type="button"
                className="btn-ghost px-2 py-1 text-xs"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={safePage === 0}
              >
                Prev
              </button>
              <span>
                {safePage + 1} / {pageCount}
              </span>
              <button
                type="button"
                className="btn-ghost px-2 py-1 text-xs"
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={safePage >= pageCount - 1}
              >
                Next
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
