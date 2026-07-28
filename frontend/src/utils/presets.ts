/**
 * The 5 Manual Builder preset chips (PROJECT_SPEC.md → "Preset Chips").
 *
 * Each preset is a complete, valid Strategy body — no placeholders. `id` and
 * `created_at` are filled in when the preset is loaded into the form.
 */
import type { Condition, IndicatorRef, Strategy } from '../schemas/strategy'

const sma = (period: number): IndicatorRef => ({ kind: 'SMA', params: { period } })
const rsi = (period: number): IndicatorRef => ({ kind: 'RSI', params: { period } })
const constant = (value: number): IndicatorRef => ({ kind: 'CONSTANT', params: { value } })
const close = (offset = 0): IndicatorRef => ({
  kind: 'PRICE_CLOSE',
  params: offset ? { offset } : {},
})
const bollinger = (
  band: 'BOLLINGER_UPPER' | 'BOLLINGER_MID' | 'BOLLINGER_LOWER',
  period: number,
  std: number,
): IndicatorRef => ({ kind: band, params: { period, std } })

const cond = (left: IndicatorRef, operator: Condition['operator'], right: IndicatorRef): Condition => ({
  left,
  operator,
  right,
})

/** A preset carries everything except the server-assigned id/timestamp. */
export type StrategyPreset = {
  key: string
  label: string
  description: string
  body: Omit<Strategy, 'id' | 'created_at'>
}

export const PRESETS: StrategyPreset[] = [
  {
    key: 'golden-cross',
    label: '골든크로스 (50/200)',
    description: '50일 이평선이 200일 이평선을 상향돌파하면 매수, 하향돌파하면 매도',
    body: {
      name: '골든크로스 (50/200)',
      description: '50일 이평선이 200일 이평선을 상향돌파하면 매수, 하향돌파하면 매도합니다.',
      language: 'ko',
      buy_conditions: [cond(sma(50), 'cross_above', sma(200))],
      sell_conditions: [cond(sma(50), 'cross_below', sma(200))],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      position_sizing: 'all_in',
      position_size_value: null,
      allow_reentry_same_day: false,
      cooldown_days_after_exit: 0,
    },
  },
  {
    key: 'rsi-bounce',
    label: 'RSI 반등',
    description: 'RSI(14)가 30을 상향돌파하면 매수, 70을 상향돌파하면 매도',
    body: {
      name: 'RSI 반등',
      description: 'RSI(14)가 30을 상향돌파할 때 매수하고, 70을 상향돌파할 때 매도합니다.',
      language: 'ko',
      buy_conditions: [cond(rsi(14), 'cross_above', constant(30))],
      sell_conditions: [cond(rsi(14), 'cross_above', constant(70))],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      position_sizing: 'all_in',
      position_size_value: null,
      allow_reentry_same_day: false,
      cooldown_days_after_exit: 0,
    },
  },
  {
    key: 'bollinger-lower',
    label: '볼린저 하단 매수',
    description: '종가가 볼린저 하단을 이탈하면 매수, 중심선을 상향돌파하면 매도 · 5% 손절',
    body: {
      name: '볼린저 하단 매수',
      description:
        '종가가 볼린저밴드 하단을 하향돌파하면 매수하고, 중심선을 상향돌파하면 매도합니다. 5% 손절.',
      language: 'ko',
      buy_conditions: [cond(close(), 'cross_below', bollinger('BOLLINGER_LOWER', 20, 2))],
      sell_conditions: [cond(close(), 'cross_above', bollinger('BOLLINGER_MID', 20, 2))],
      stop_loss_pct: 0.05,
      take_profit_pct: null,
      max_holding_days: null,
      position_sizing: 'all_in',
      position_size_value: null,
      allow_reentry_same_day: false,
      cooldown_days_after_exit: 0,
    },
  },
  {
    key: 'infinite-buy',
    label: '무한매수법 v1',
    description: '종가가 20일 이평선 아래일 때 매수 · 10% 익절 / 20% 손절 / 최대 40봉 보유',
    body: {
      name: '무한매수법 v1 (간소화)',
      description:
        '종가가 20일 이동평균선 아래일 때 매수하고, 10% 익절 · 20% 손절 · 최대 40봉 보유로 청산합니다.',
      language: 'ko',
      buy_conditions: [cond(close(), '<', sma(20))],
      sell_conditions: [],
      stop_loss_pct: 0.2,
      take_profit_pct: 0.1,
      max_holding_days: 40,
      position_sizing: 'all_in',
      position_size_value: null,
      allow_reentry_same_day: false,
      cooldown_days_after_exit: 0,
    },
  },
  {
    key: 'dual-momentum',
    label: '듀얼 모멘텀 (단일종목판)',
    description: '종가가 200일 이평선 위이고 1년 전보다 높으면 매수, 200일선 아래면 매도',
    body: {
      name: '듀얼 모멘텀 (단일종목판)',
      description:
        '종가가 200일 이동평균선 위에 있고 1년 전(252봉) 종가보다 높을 때 매수하고, 200일선 아래로 내려가면 매도합니다.',
      language: 'ko',
      buy_conditions: [
        cond(close(), '>', sma(200)),
        // (Close / Close[-252]) > 1 restated as a direct comparison — identical for
        // positive prices and expressible without a division operator.
        cond(close(), '>', close(252)),
      ],
      sell_conditions: [cond(close(), '<', sma(200))],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      position_sizing: 'all_in',
      position_size_value: null,
      allow_reentry_same_day: false,
      cooldown_days_after_exit: 0,
    },
  },
]

/** Build a runnable Strategy from a preset, with a fresh client-side id. */
export function instantiatePreset(preset: StrategyPreset): Strategy {
  return {
    ...structuredClone(preset.body),
    id: `s_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`,
    created_at: new Date().toISOString(),
  }
}
