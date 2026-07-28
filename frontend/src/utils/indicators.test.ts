/**
 * Client-side indicator tests.
 *
 * The important one is parity: these overlays are drawn on the chart, but the *same*
 * maths decides buy/sell signals in `backend/app/backtest/indicators.py`. If the two
 * drift, a user sees a crossover on the chart that the backtest never traded on.
 *
 * `__fixtures__/indicators.python.json` is generated from the backend implementation:
 *
 *   .venv/bin/python -c "...sma(close, p)... json.dump(...)"
 *
 * Regenerate it if the Python side ever changes.
 */
import { describe, expect, it } from 'vitest'

import fixture from './__fixtures__/indicators.python.json'
import { ema, sma, toLineData } from './indicators'

const close: number[] = fixture.close
const TOLERANCE = 1e-6 // fixture is rounded to 9dp

function comparable(actual: (number | null)[], expected: (number | null)[]) {
  expect(actual.length).toBe(expected.length)
  let compared = 0
  for (let i = 0; i < expected.length; i += 1) {
    if (expected[i] == null) {
      expect(actual[i], `index ${i} should be warm-up NaN/null`).toBeNull()
    } else {
      expect(actual[i], `index ${i}`).not.toBeNull()
      expect(Math.abs((actual[i] as number) - (expected[i] as number))).toBeLessThan(TOLERANCE)
      compared += 1
    }
  }
  return compared
}

describe('parity with the Python backtest engine', () => {
  it('has a fixture with enough bars to exercise SMA 200', () => {
    expect(close.length).toBeGreaterThan(250)
  })

  it.each([20, 50, 200])('SMA(%i) matches the backend exactly', (period) => {
    const compared = comparable(sma(close, period), fixture.sma[String(period) as '20'])
    expect(compared).toBeGreaterThan(100)
  })

  it.each([9, 21, 65])('EMA(%i) matches the backend exactly', (period) => {
    const compared = comparable(ema(close, period), fixture.ema[String(period) as '9'])
    expect(compared).toBeGreaterThan(100)
  })

  it('seeds EMA with the SMA of the first `period` bars, like the backend', () => {
    // This is the specific convention that would silently drift if someone swapped in
    // a naive recursive EMA seeded from the first value.
    const period = 9
    const seeded = ema(close, period)
    const expectedSeed = close.slice(0, period).reduce((a, b) => a + b, 0) / period
    expect(seeded[period - 2]).toBeNull()
    expect(Math.abs((seeded[period - 1] as number) - expectedSeed)).toBeLessThan(1e-9)
  })
})

describe('warm-up behaviour', () => {
  it('SMA is null until the window is full', () => {
    const out = sma([1, 2, 3, 4, 5], 3)
    expect(out.slice(0, 2)).toEqual([null, null])
    expect(out[2]).toBeCloseTo(2)
    expect(out[4]).toBeCloseTo(4)
  })

  it('returns all nulls when the series is shorter than the period', () => {
    expect(sma([1, 2], 5)).toEqual([null, null])
    expect(ema([1, 2], 5)).toEqual([null, null])
  })

  it('rejects nonsensical periods instead of throwing', () => {
    expect(sma([1, 2, 3], 0)).toEqual([null, null, null])
    expect(ema([1, 2, 3], -1)).toEqual([null, null, null])
  })
})

describe('toLineData', () => {
  it('drops warm-up nulls and pairs the rest with dates', () => {
    const times = ['2024-01-01', '2024-01-02', '2024-01-03']
    const points = toLineData(times, [null, 5, 6])
    expect(points).toEqual([
      { time: '2024-01-02', value: 5 },
      { time: '2024-01-03', value: 6 },
    ])
  })

  it('drops non-finite values so the chart never receives NaN', () => {
    const times = ['2024-01-01', '2024-01-02']
    expect(toLineData(times, [Number.NaN, 3])).toEqual([{ time: '2024-01-02', value: 3 }])
  })
})
