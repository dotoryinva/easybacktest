import { useEffect, useRef, useState } from 'react'

import type { Candle } from '../../schemas/backtest'
import { ema, sma, toLineData, type LinePoint } from '../../utils/indicators'
import type { IndicatorRequest, IndicatorResponse } from '../../workers/indicators.worker'

/** ~3 years of daily bars — above this the computation moves off the main thread. */
const WORKER_THRESHOLD_BARS = 756

export type IndicatorSeries = {
  sma: Record<number, LinePoint[]>
  ema: Record<number, LinePoint[]>
}

const EMPTY: IndicatorSeries = { sma: {}, ema: {} }

export function useIndicatorSeries(
  candles: Candle[],
  smaPeriods: number[],
  emaPeriods: number[],
): IndicatorSeries {
  const [series, setSeries] = useState<IndicatorSeries>(EMPTY)
  const workerRef = useRef<Worker | null>(null)
  const requestId = useRef(0)

  useEffect(() => {
    return () => {
      workerRef.current?.terminate()
      workerRef.current = null
    }
  }, [])

  const smaKey = smaPeriods.join(',')
  const emaKey = emaPeriods.join(',')

  useEffect(() => {
    if (candles.length === 0 || (smaPeriods.length === 0 && emaPeriods.length === 0)) {
      setSeries(EMPTY)
      return
    }

    const times = candles.map((c) => c.time)
    const closes = candles.map((c) => c.close)

    if (candles.length <= WORKER_THRESHOLD_BARS) {
      const next: IndicatorSeries = { sma: {}, ema: {} }
      for (const period of smaPeriods) next.sma[period] = toLineData(times, sma(closes, period))
      for (const period of emaPeriods) next.ema[period] = toLineData(times, ema(closes, period))
      setSeries(next)
      return
    }

    if (!workerRef.current) {
      workerRef.current = new Worker(
        new URL('../../workers/indicators.worker.ts', import.meta.url),
        { type: 'module' },
      )
    }
    const worker = workerRef.current
    requestId.current += 1
    const id = requestId.current

    const onMessage = (event: MessageEvent<IndicatorResponse>) => {
      // Drop stale results — the user may have toggled again mid-computation.
      if (event.data.id !== requestId.current) return
      setSeries({ sma: event.data.sma, ema: event.data.ema })
    }
    worker.addEventListener('message', onMessage)

    const request: IndicatorRequest = { id, times, closes, smaPeriods, emaPeriods }
    worker.postMessage(request)

    return () => worker.removeEventListener('message', onMessage)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, smaKey, emaKey])

  return series
}
