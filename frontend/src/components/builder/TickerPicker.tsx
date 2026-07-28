import { useEffect, useRef, useState } from 'react'

import { useTickerSearch } from '../../api/client'
import type { Market, Ticker } from '../../schemas/strategy'

type Props = {
  ticker: string
  market: Market
  onSelect: (ticker: string, market: Market) => void
}

const DEBOUNCE_MS = 200

export function TickerPicker({ ticker, market, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [marketFilter, setMarketFilter] = useState<Market | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const { data, isFetching } = useTickerSearch(debounced, marketFilter)

  const choose = (t: Ticker) => {
    onSelect(t.ticker, t.market)
    setQuery('')
    setOpen(false)
  }

  // Group results by kind: 지수 / Indices first, then ETF, then 주식 / Stocks.
  const results = data ?? []
  const groups: { key: Ticker['kind']; label: string; cap: number; items: Ticker[] }[] = [
    { key: 'index', label: '지수 / Indices', cap: 5, items: [] },
    { key: 'etf', label: 'ETF', cap: 15, items: [] },
    { key: 'stock', label: '주식 / Stocks', cap: 15, items: [] },
  ]
  for (const t of results) {
    const g = groups.find((grp) => grp.key === t.kind) ?? groups[2]
    if (g.items.length < g.cap) g.items.push(t)
  }
  const visibleGroups = groups.filter((g) => g.items.length > 0)

  return (
    <div ref={rootRef} className="relative">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            className="input"
            placeholder={`${market}/${ticker} — 종목 검색 / search ticker`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
          />
          {isFetching && (
            <span className="absolute right-3 top-2.5 text-xs text-slate-500">…</span>
          )}
        </div>
        <div className="inline-flex rounded-lg border border-ink-700 bg-ink-850 p-0.5">
          {([null, 'KR', 'US'] as const).map((m) => (
            <button
              key={m ?? 'all'}
              type="button"
              onClick={() => setMarketFilter(m)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                marketFilter === m
                  ? 'bg-accent text-white'
                  : 'text-slate-400 hover:text-primary'
              }`}
            >
              {m ?? 'ALL'}
            </button>
          ))}
        </div>
      </div>

      {open && debounced.trim() && (
        <div className="absolute z-30 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-ink-700 bg-ink-850 shadow-xl">
          {results.length === 0 && !isFetching && (
            <div className="px-3 py-3 text-sm text-slate-500">
              결과 없음 / No tickers match "{debounced}".
            </div>
          )}
          {visibleGroups.map((group) => (
            <div key={group.key}>
              <div className="sticky top-0 bg-ink-850/95 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 backdrop-blur">
                {group.label}
              </div>
              {group.items.map((t) => (
                <button
                  key={`${t.market}-${t.ticker}`}
                  type="button"
                  onClick={() => choose(t)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-ink-800"
                >
                  <span className="w-16 shrink-0 truncate font-mono text-xs font-semibold text-accent">
                    {t.ticker}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-primary">
                      {t.name_ko || t.name_en}
                    </div>
                    {t.name_ko &&
                      t.name_en &&
                      t.name_en !== t.name_ko &&
                      t.name_en !== t.ticker && (
                        <div className="truncate text-xs text-secondary">{t.name_en}</div>
                      )}
                  </div>
                  <span className="chip shrink-0 uppercase">{t.kind}</span>
                  <span className="chip shrink-0">{t.market}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
