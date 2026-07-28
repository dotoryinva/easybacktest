/// <reference lib="webworker" />
/**
 * Off-main-thread SMA/EMA for long lookbacks (> 3 years of daily bars).
 * Shares the exact implementations in `utils/indicators.ts`.
 */
import { ema, sma, toLineData, type LinePoint } from '../utils/indicators'

export type IndicatorRequest = {
  id: number
  times: string[]
  closes: number[]
  smaPeriods: number[]
  emaPeriods: number[]
}

export type IndicatorResponse = {
  id: number
  sma: Record<number, LinePoint[]>
  ema: Record<number, LinePoint[]>
}

self.onmessage = (event: MessageEvent<IndicatorRequest>) => {
  const { id, times, closes, smaPeriods, emaPeriods } = event.data

  const smaResult: Record<number, LinePoint[]> = {}
  for (const period of smaPeriods) {
    smaResult[period] = toLineData(times, sma(closes, period))
  }

  const emaResult: Record<number, LinePoint[]> = {}
  for (const period of emaPeriods) {
    emaResult[period] = toLineData(times, ema(closes, period))
  }

  const response: IndicatorResponse = { id, sma: smaResult, ema: emaResult }
  ;(self as unknown as DedicatedWorkerGlobalScope).postMessage(response)
}
