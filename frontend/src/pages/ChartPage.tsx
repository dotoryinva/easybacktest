import { Bell, ChevronDown, Download, GitCompare, Star, TrendingDown, TrendingUp, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useOhlcv, useOhlcvMany } from '../api/client'
import { ComparisonChart, type CompareSeries } from '../components/chart/ComparisonChart'
import { IndicatorToggles } from '../components/chart/IndicatorToggles'
import { PriceChart, type PriceScaleKind } from '../components/chart/PriceChart'
import {
  TimeframeSelector,
  timeframeStart,
  warmupStart,
  type Timeframe,
} from '../components/chart/TimeframeSelector'
import { useIndicatorSeries } from '../components/chart/useIndicatorSeries'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ErrorNote } from '../components/ui/ErrorNote'
import type { Market } from '../schemas/strategy'
import { useChartPrefs } from '../stores/builder'
import { useWatchlist, type WatchItem } from '../stores/watchlist'
import { downloadCsv, toCsv } from '../utils/csv'
import { formatPrice } from '../utils/format'

const BASE_COLOR = '#f59e0b'
const COMPARE_COLORS = ['#3b82f6', '#a855f7', '#ec4899']

export function ChartPage() {
  const { ticker = 'AAPL' } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const market = (searchParams.get('market') as Market | null) ?? 'US'

  const [timeframe, setTimeframe] = useState<Timeframe>('1Y')
  const [scale, setScale] = useState<PriceScaleKind>('linear')
  const [compareMode, setCompareMode] = useState(false)
  const [compareList, setCompareList] = useState<WatchItem[]>([])

  const watchItems = useWatchlist((s) => s.items)
  const toggleWatch = useWatchlist((s) => s.toggle)
  const isWatched = watchItems.some((i) => i.ticker === ticker && i.market === market)
  const {
    smaPeriods,
    emaPeriods,
    customSma,
    customEma,
    toggleSma,
    toggleEma,
    addCustom,
    removeCustom,
  } = useChartPrefs()

  // Preset chips and custom periods are plotted from the same pipeline.
  const activeSma = useMemo(
    () => [...new Set([...smaPeriods, ...customSma])].sort((a, b) => a - b),
    [smaPeriods, customSma],
  )
  const activeEma = useMemo(
    () => [...new Set([...emaPeriods, ...customEma])].sort((a, b) => a - b),
    [emaPeriods, customEma],
  )

  const visibleStart = timeframeStart(timeframe)
  const maxPeriod = Math.max(0, ...activeSma, ...activeEma)
  const fetchStart = warmupStart(visibleStart, maxPeriod)

  const { data, isLoading, error } = useOhlcv(market, ticker, fetchStart ?? undefined)

  // Compare overlay: fetch each comparison ticker's bars in parallel and rebase to %.
  const compareQueries = useOhlcvMany(compareList, fetchStart ?? undefined)
  const showComparison = compareMode && compareList.length > 0

  const addCompare = (t: string, m: Market) => {
    if (t === ticker && m === market) return
    setCompareList((prev) =>
      prev.some((i) => i.ticker === t && i.market === m) || prev.length >= 3
        ? prev
        : [...prev, { ticker: t, market: m }],
    )
  }
  const removeCompare = (t: string, m: Market) =>
    setCompareList((prev) => prev.filter((i) => !(i.ticker === t && i.market === m)))

  const allCandles = useMemo(() => data?.candles ?? [], [data?.candles])
  const allIndicators = useIndicatorSeries(allCandles, activeSma, activeEma)

  // Warm-up bars are fetched so the overlays are already warm at the left edge, but
  // both the candles and the overlay lines are trimmed to the visible window — an
  // overlay extending past the first candle would stretch the time axis.
  const candles = useMemo(
    () => (visibleStart ? allCandles.filter((c) => c.time >= visibleStart) : allCandles),
    [allCandles, visibleStart],
  )

  const indicators = useMemo(() => {
    if (!visibleStart) return allIndicators
    const trim = (series: Record<number, { time: string; value: number }[]>) =>
      Object.fromEntries(
        Object.entries(series).map(([period, points]) => [
          period,
          points.filter((p) => p.time >= visibleStart),
        ]),
      )
    return { sma: trim(allIndicators.sma), ema: trim(allIndicators.ema) }
  }, [allIndicators, visibleStart])

  const last = candles.at(-1)
  const prev = candles.at(-2)
  const change = last && prev ? last.close - prev.close : null
  const changePct = change != null && prev ? change / prev.close : null
  const up = (change ?? 0) >= 0

  const compareSeries = useMemo<CompareSeries[]>(() => {
    const base: CompareSeries = {
      key: `${market}:${ticker}`,
      label: data?.name ?? ticker,
      color: BASE_COLOR,
      candles: allCandles,
    }
    const others = compareList
      .map((item, i): CompareSeries | null => {
        const q = compareQueries[i]
        if (!q?.data) return null
        return {
          key: `${item.market}:${item.ticker}`,
          label: q.data.name ?? item.ticker,
          color: COMPARE_COLORS[i % COMPARE_COLORS.length],
          candles: q.data.candles,
        }
      })
      .filter((s): s is CompareSeries => s !== null)
    return [base, ...others]
  }, [market, ticker, data?.name, allCandles, compareList, compareQueries])

  const onDownload = () => {
    downloadCsv(
      `${market}_${ticker}_${timeframe}`,
      toCsv(candles as unknown as Record<string, unknown>[], [
        'time',
        'open',
        'high',
        'low',
        'close',
        'volume',
      ]),
    )
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
      <div className="max-w-xl">
        <TickerPicker
          ticker={ticker}
          market={market}
          onSelect={(t, m) => navigate(`/chart/${encodeURIComponent(t)}?market=${m}`)}
        />
      </div>

      <div className="card p-5 lg:p-6">
        {/* ---------- Top block ---------- */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-h1 text-primary">{data?.name ?? ticker}</h1>
              <span className="pill">{ticker}</span>
              {data?.kind === 'index' && <span className="chip">지수</span>}
              {data?.kind === 'etf' && <span className="chip">ETF</span>}
            </div>
            {isLoading ? (
              <div className="mt-2 h-10 w-56 skeleton" />
            ) : (
              last && (
                <div className="mt-1 flex items-baseline gap-2.5">
                  <span className="tnum text-display text-primary">
                    {formatPrice(last.close, market)}
                  </span>
                  {change != null && changePct != null && (
                    <span
                      className={`tnum flex items-center gap-1 text-body ${
                        up ? 'text-positive' : 'text-negative'
                      }`}
                    >
                      {up ? (
                        <TrendingUp className="h-4 w-4" />
                      ) : (
                        <TrendingDown className="h-4 w-4" />
                      )}
                      {up ? '+' : ''}
                      {formatPrice(change, market)} ({(changePct * 100).toFixed(2)}%)
                    </span>
                  )}
                </div>
              )
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className={`btn-icon ${isWatched ? 'border-accent text-accent' : ''}`}
              title={isWatched ? '관심목록에서 제거' : '관심목록에 추가'}
              aria-pressed={isWatched}
              onClick={() => toggleWatch({ ticker, market, name: data?.name })}
            >
              <Star className="h-4 w-4" fill={isWatched ? 'currentColor' : 'none'} />
            </button>
            <button
              type="button"
              className={`btn-icon ${compareMode ? 'border-accent text-accent' : ''}`}
              title="비교 / Compare"
              aria-pressed={compareMode}
              onClick={() => setCompareMode((v) => !v)}
            >
              <GitCompare className="h-4 w-4" />
            </button>
            <button type="button" className="btn-icon" title="알림 / Alerts (준비 중)" disabled>
              <Bell className="h-4 w-4" />
            </button>

            <div className="mx-1 h-6 w-px bg-slate-200" />

            <button
              type="button"
              className="btn-outline"
              onClick={onDownload}
              disabled={candles.length === 0}
            >
              <Download className="h-4 w-4" />
              Download CSV
            </button>

            <div className="segmented">
              {(['linear', 'logarithmic'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setScale(mode)}
                  className={`segmented-item ${scale === mode ? 'segmented-item-active' : ''}`}
                >
                  {mode === 'linear' ? 'Linear' : 'Log'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <ErrorNote className="mt-4" error={error} />}

        {/* ---------- Compare bar ---------- */}
        {compareMode && (
          <div className="mt-4 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <div className="mb-2 flex items-center gap-2">
              <GitCompare className="h-4 w-4 text-accent" />
              <span className="text-sm font-medium text-primary">비교 종목 추가 (최대 3개)</span>
              <span className="text-xs text-tertiary">· 시작 시점 대비 % 수익률로 겹쳐 보여줍니다</span>
            </div>
            <div className="max-w-md">
              <TickerPicker ticker="" market={market} onSelect={addCompare} />
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium">
                <span className="h-2 w-2 rounded-full" style={{ background: BASE_COLOR }} />
                <span className="font-mono text-primary">{ticker}</span>
                <span className="text-secondary">기준</span>
              </span>
              {compareList.map((it, i) => (
                <span
                  key={`${it.market}-${it.ticker}`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium"
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: COMPARE_COLORS[i % COMPARE_COLORS.length] }}
                  />
                  <span className="font-mono text-primary">{it.ticker}</span>
                  <span className="text-secondary">{it.market}</span>
                  <button type="button" onClick={() => removeCompare(it.ticker, it.market)} aria-label="제거">
                    <X size={13} className="text-secondary hover:text-primary" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ---------- Middle block ---------- */}
        <div className="mt-5 flex flex-wrap items-start justify-between gap-4 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2">
            {/* Phase 1 has only 일봉, but the control exists for when intraday lands. */}
            <button
              type="button"
              disabled
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 disabled:opacity-100"
              title="Phase 1 supports daily bars only"
            >
              일봉
              <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
            </button>
            <TimeframeSelector value={timeframe} onChange={setTimeframe} />
          </div>

          <IndicatorToggles
            smaPeriods={smaPeriods}
            emaPeriods={emaPeriods}
            customSma={customSma}
            customEma={customEma}
            onToggleSma={toggleSma}
            onToggleEma={toggleEma}
            onAddCustom={addCustom}
            onRemoveCustom={removeCustom}
          />
        </div>

        {/* ---------- Chart panel ---------- */}
        <div className="mt-4">
          {isLoading ? (
            <div className="h-[460px] skeleton" />
          ) : showComparison ? (
            <ComparisonChart series={compareSeries} visibleStart={visibleStart} />
          ) : candles.length === 0 ? (
            <div className="flex h-[460px] flex-col items-center justify-center gap-2 text-secondary">
              <TrendingUp className="h-6 w-6 text-tertiary" />
              <p className="text-body">이 기간에는 데이터가 없습니다 / No data for this range.</p>
            </div>
          ) : (
            <PriceChart candles={candles} indicators={indicators} scale={scale} />
          )}
        </div>

        <div className="mt-3 border-t border-slate-100 pt-3 text-small text-tertiary">
          {candles.length.toLocaleString()} bars
          {maxPeriod > 0 && ` · 이동평균 워밍업 ${fetchStart ?? '처음부터'}`}
        </div>
      </div>
    </div>
  )
}
