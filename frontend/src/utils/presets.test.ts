/**
 * Every preset chip must load a complete, valid Strategy — no placeholders.
 * They are validated against the same Zod schema the AI parser's output goes through,
 * so a preset can never be something the manual path accepts but the AI path wouldn't.
 */
import { describe, expect, it } from 'vitest'

import { strategyIsRunnable, strategySchema } from '../schemas/strategy'
import { PRESETS, instantiatePreset } from './presets'

describe('preset chips', () => {
  it('ships exactly the 5 presets the spec lists', () => {
    expect(PRESETS.map((p) => p.label)).toEqual([
      '골든크로스 (50/200)',
      'RSI 반등',
      '볼린저 하단 매수',
      '무한매수법 v1',
      '듀얼 모멘텀 (단일종목판)',
    ])
  })

  it.each(PRESETS.map((p) => [p.label, p] as const))(
    '%s produces a schema-valid, runnable strategy',
    (_label, preset) => {
      const strategy = instantiatePreset(preset)

      const parsed = strategySchema.safeParse(strategy)
      expect(parsed.success, JSON.stringify(parsed.error?.issues)).toBe(true)

      // Same gate the Run Backtest button uses.
      expect(strategyIsRunnable(strategy)).toBeNull()

      expect(strategy.name.trim()).not.toBe('')
      expect(strategy.description.trim()).not.toBe('')
      expect(strategy.buy_conditions.length).toBeGreaterThan(0)
      expect(strategy.id).toMatch(/^s_/)
      expect(Number.isNaN(Date.parse(strategy.created_at))).toBe(false)
    },
  )

  it('gives each instantiation a distinct id', () => {
    const a = instantiatePreset(PRESETS[0])
    const b = instantiatePreset(PRESETS[0])
    expect(a.id).not.toBe(b.id)
  })

  it('deep-clones, so editing one instance cannot mutate the preset', () => {
    const first = instantiatePreset(PRESETS[0])
    first.buy_conditions[0].left.params.period = 999
    const second = instantiatePreset(PRESETS[0])
    expect(second.buy_conditions[0].left.params.period).toBe(50)
  })
})

describe('specific preset semantics', () => {
  it('골든크로스 is SMA(50) crossing SMA(200) both ways', () => {
    const s = instantiatePreset(PRESETS[0])
    expect(s.buy_conditions[0]).toMatchObject({
      left: { kind: 'SMA', params: { period: 50 } },
      operator: 'cross_above',
      right: { kind: 'SMA', params: { period: 200 } },
    })
    expect(s.sell_conditions[0].operator).toBe('cross_below')
  })

  it('RSI 반등 crosses a constant, which is legal on the right', () => {
    const s = instantiatePreset(PRESETS[1])
    expect(s.buy_conditions[0].right).toMatchObject({ kind: 'CONSTANT', params: { value: 30 } })
    expect(s.buy_conditions[0].operator).toBe('cross_above')
  })

  it('볼린저 하단 매수 carries the 5% stop', () => {
    const s = instantiatePreset(PRESETS[2])
    expect(s.buy_conditions[0].right.kind).toBe('BOLLINGER_LOWER')
    expect(s.stop_loss_pct).toBeCloseTo(0.05)
  })

  it('무한매수법 has no sell conditions but three exit rules', () => {
    const s = instantiatePreset(PRESETS[3])
    expect(s.sell_conditions).toHaveLength(0)
    expect(s.take_profit_pct).toBeCloseTo(0.1)
    expect(s.stop_loss_pct).toBeCloseTo(0.2)
    expect(s.max_holding_days).toBe(40)
    // Still runnable: exit rules alone satisfy the schema.
    expect(strategyIsRunnable(s)).toBeNull()
  })

  it('듀얼 모멘텀 compares close against its own value 252 bars back', () => {
    const s = instantiatePreset(PRESETS[4])
    expect(s.buy_conditions).toHaveLength(2)
    expect(s.buy_conditions[1]).toMatchObject({
      left: { kind: 'PRICE_CLOSE' },
      operator: '>',
      right: { kind: 'PRICE_CLOSE', params: { offset: 252 } },
    })
  })
})
