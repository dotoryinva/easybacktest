import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { Market } from '../schemas/strategy'

export type WatchItem = { ticker: string; market: Market; name?: string }

const same = (a: WatchItem, ticker: string, market: Market) =>
  a.ticker === ticker && a.market === market

type WatchlistState = {
  items: WatchItem[]
  add: (item: WatchItem) => void
  remove: (ticker: string, market: Market) => void
  toggle: (item: WatchItem) => void
}

/** localStorage-backed watchlist (Phase 1 has no auth). */
export const useWatchlist = create<WatchlistState>()(
  persist(
    (set, get) => ({
      items: [],
      add: (item) =>
        set((s) =>
          s.items.some((i) => same(i, item.ticker, item.market))
            ? s
            : { items: [...s.items, item] },
        ),
      remove: (ticker, market) =>
        set((s) => ({ items: s.items.filter((i) => !same(i, ticker, market)) })),
      toggle: (item) => {
        const exists = get().items.some((i) => same(i, item.ticker, item.market))
        exists ? get().remove(item.ticker, item.market) : get().add(item)
      },
    }),
    { name: 'easybacktest.watchlist' },
  ),
)
