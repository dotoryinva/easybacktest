/** Human-readable rendering of a parsed Strategy. Mirrors IndicatorRef.label() on the backend. */
import type { Condition, IndicatorRef, Operator, Strategy } from '../schemas/strategy'

const OPERATOR_LABELS: Record<Operator, { en: string; ko: string }> = {
  '>': { en: 'is above', ko: '이(가) 초과' },
  '<': { en: 'is below', ko: '이(가) 미만' },
  '>=': { en: 'is at or above', ko: '이(가) 이상' },
  '<=': { en: 'is at or below', ko: '이(가) 이하' },
  '==': { en: 'equals', ko: '와(과) 같음' },
  cross_above: { en: 'crosses above', ko: '상향돌파' },
  cross_below: { en: 'crosses below', ko: '하향돌파' },
}

export function indicatorLabel(ref: IndicatorRef): string {
  const p = ref.params ?? {}
  switch (ref.kind) {
    case 'SMA':
    case 'EMA':
      return `${ref.kind}(${p.period})`
    case 'RSI':
      return `RSI(${p.period ?? 14})`
    case 'MACD_LINE':
      return `MACD(${p.fast ?? 12},${p.slow ?? 26},${p.signal ?? 9})`
    case 'MACD_SIGNAL':
      return `MACD Signal(${p.fast ?? 12},${p.slow ?? 26},${p.signal ?? 9})`
    case 'BOLLINGER_UPPER':
      return `Bollinger Upper(${p.period ?? 20}, ${p.std ?? 2}σ)`
    case 'BOLLINGER_MID':
      return `Bollinger Mid(${p.period ?? 20})`
    case 'BOLLINGER_LOWER':
      return `Bollinger Lower(${p.period ?? 20}, ${p.std ?? 2}σ)`
    case 'PRICE_CLOSE':
      return 'Close'
    case 'PRICE_OPEN':
      return 'Open'
    case 'PRICE_HIGH':
      return 'High'
    case 'PRICE_LOW':
      return 'Low'
    case 'VOLUME':
      return 'Volume'
    case 'CONSTANT':
      return String(p.value ?? 0)
    default:
      return ref.kind
  }
}

export function operatorLabel(operator: Operator, language: 'ko' | 'en' = 'en'): string {
  return OPERATOR_LABELS[operator][language]
}

export function conditionLabel(condition: Condition, language: 'ko' | 'en' = 'en'): string {
  const op = operatorLabel(condition.operator, language)
  return `${indicatorLabel(condition.left)} ${op} ${indicatorLabel(condition.right)}`
}

export function positionSizingLabel(strategy: Strategy): string {
  switch (strategy.position_sizing) {
    case 'all_in':
      return 'All available cash'
    case 'fixed_amount':
      return `Fixed ${strategy.position_size_value?.toLocaleString() ?? '—'} per trade`
    case 'percent_of_capital':
      return `${((strategy.position_size_value ?? 0) * 100).toFixed(0)}% of portfolio`
  }
}

/** Indicator families used, for auto-generated library tags. */
export function strategyTags(strategy: Strategy): string[] {
  const tags = new Set<string>()
  for (const c of [...strategy.buy_conditions, ...strategy.sell_conditions]) {
    for (const side of [c.left, c.right]) {
      if (side.kind === 'CONSTANT') continue
      if (side.kind.startsWith('PRICE_')) tags.add('Price')
      else if (side.kind.startsWith('BOLLINGER')) tags.add('Bollinger')
      else if (side.kind.startsWith('MACD')) tags.add('MACD')
      else tags.add(side.kind)
    }
  }
  if (strategy.stop_loss_pct != null) tags.add('Stop loss')
  if (strategy.take_profit_pct != null) tags.add('Take profit')
  return [...tags]
}
