/**
 * TradingView Lightweight Charts wrapper.
 *
 * Uses the official imperative ref pattern rather than a community React wrapper —
 * the wrappers lag the upstream version and hide the API we need for overlay series
 * and price-scale modes.
 */
import {
  ColorType,
  CrosshairMode,
  PriceScaleMode,
  TickMarkType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import { useEffect, useLayoutEffect, useRef } from 'react'

import type { Candle } from '../../schemas/backtest'
import type { LinePoint } from '../../utils/indicators'
import { CUSTOM_COLOR, EMA_COLORS, SMA_COLORS } from '../../utils/indicators'
import type { IndicatorSeries } from './useIndicatorSeries'

export type PriceScaleKind = 'linear' | 'logarithmic'

type Props = {
  candles: Candle[]
  indicators: IndicatorSeries
  scale?: PriceScaleKind
  height?: number
}

const UP = '#10B981'
const DOWN = '#EF4444'
const GRID = '#F1F5F9'
const AXIS_TEXT = '#94A3B8'

/**
 * Korean date axis: `2022년`, `5월`, `9월`, `2023년`.
 * Time can arrive as a BusinessDay object or a UTC timestamp depending on how the
 * series was fed, so handle both.
 */
function koreanTickMark(time: unknown, tickMarkType: TickMarkType): string {
  const asDate =
    typeof time === 'number'
      ? new Date(time * 1000)
      : new Date(
          (time as { year: number }).year,
          (time as { month: number }).month - 1,
          (time as { day: number }).day,
        )

  switch (tickMarkType) {
    case TickMarkType.Year:
      return `${asDate.getFullYear()}년`
    case TickMarkType.Month:
      return `${asDate.getMonth() + 1}월`
    case TickMarkType.DayOfMonth:
      return `${asDate.getDate()}일`
    default:
      return `${asDate.getHours()}:${String(asDate.getMinutes()).padStart(2, '0')}`
  }
}

export function PriceChart({ candles, indicators, scale = 'linear', height = 460 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlaysRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())

  // Create the chart once; keep it across data updates.
  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#FFFFFF' },
        textColor: AXIS_TEXT,
        fontFamily:
          "'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#E2E8F0' },
      timeScale: {
        borderColor: '#E2E8F0',
        timeVisible: false,
        tickMarkFormatter: koreanTickMark,
      },
      localization: { locale: 'ko-KR' },
    })
    chartRef.current = chart

    candleSeriesRef.current = chart.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })

    volumeSeriesRef.current = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    // Candles get the top 75%, volume the bottom 25% — the two panes never overlap.
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.06, bottom: 0.28 } })

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) chart.applyOptions({ width })
    })
    observer.observe(container)

    return () => {
      observer.disconnect()
      overlaysRef.current.clear()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [height])

  // Linear / logarithmic price scale.
  useEffect(() => {
    chartRef.current?.priceScale('right').applyOptions({
      mode: scale === 'logarithmic' ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    })
  }, [scale])

  // Price + volume data.
  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!candleSeries || !volumeSeries) return

    candleSeries.setData(
      candles.map((c) => ({
        time: c.time as unknown as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    volumeSeries.setData(
      candles.map((c) => ({
        time: c.time as unknown as UTCTimestamp,
        value: c.volume,
        // Volume bars match the candle direction.
        color: c.close >= c.open ? `${UP}55` : `${DOWN}55`,
      })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // Overlay series — add, update, and remove to match the current toggles.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const desired = new Map<string, { data: LinePoint[]; color: string; title: string }>()
    for (const [period, data] of Object.entries(indicators.sma)) {
      const p = Number(period)
      desired.set(`SMA${p}`, {
        data,
        color: SMA_COLORS[p] ?? CUSTOM_COLOR,
        title: `SMA ${p}`,
      })
    }
    for (const [period, data] of Object.entries(indicators.ema)) {
      const p = Number(period)
      desired.set(`EMA${p}`, {
        data,
        color: EMA_COLORS[p] ?? CUSTOM_COLOR,
        title: `EMA ${p}`,
      })
    }

    for (const [key, series] of overlaysRef.current) {
      if (!desired.has(key)) {
        chart.removeSeries(series)
        overlaysRef.current.delete(key)
      }
    }

    for (const [key, { data, color, title }] of desired) {
      let series = overlaysRef.current.get(key)
      if (!series) {
        series = chart.addLineSeries({
          color,
          lineWidth: 2,
          title,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        overlaysRef.current.set(key, series)
      }
      series.applyOptions({ color })
      series.setData(
        data.map((p) => ({ time: p.time as unknown as UTCTimestamp, value: p.value })),
      )
    }
  }, [indicators])

  return (
    <div>
      <div ref={containerRef} className="w-full" style={{ height }} />
      {/* TradingView attribution — required by the Lightweight Charts license. */}
      <a
        href="https://www.tradingview.com/"
        target="_blank"
        rel="noreferrer noopener"
        className="mt-1 inline-block text-[11px] text-tertiary hover:text-accent"
      >
        Charts by TradingView
      </a>
    </div>
  )
}
