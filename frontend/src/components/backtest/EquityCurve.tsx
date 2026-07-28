import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { BacktestResult, Trade } from '../../schemas/backtest'
import type { Market } from '../../schemas/strategy'
import { formatMoney } from '../../utils/format'

type Props = {
  result: BacktestResult
  highlighted?: Trade | null
}

function compactMoney(value: number, market: Market): string {
  const abs = Math.abs(value)
  const unit = market === 'KR' ? '₩' : '$'
  if (abs >= 1e8) return `${unit}${(value / 1e8).toFixed(1)}억`
  if (abs >= 1e6) return `${unit}${(value / 1e6).toFixed(1)}M`
  if (abs >= 1e4) return `${unit}${(value / 1e3).toFixed(0)}K`
  return `${unit}${value.toFixed(0)}`
}

export function EquityCurve({ result, highlighted }: Props) {
  const market = result.params.market
  const data = result.equity_curve.map((point) => ({
    date: point.date,
    strategy: point.portfolio_value,
    buyHold: point.buy_hold_value,
  }))

  const findPoint = (date: string) => data.find((d) => d.date === date)
  const entry = highlighted ? findPoint(highlighted.buy_date) : undefined
  const exit = highlighted ? findPoint(highlighted.sell_date) : undefined

  return (
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#64748b', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: '#262d3d' }}
            minTickGap={48}
            tickFormatter={(value: string) => value.slice(0, 7)}
          />
          <YAxis
            tick={{ fill: '#64748b', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
            // 'auto' anchors the axis at zero, which squashes the curve into the
            // bottom of the plot. Pad the actual data range instead.
            domain={[
              (dataMin: number) => Math.max(0, dataMin * 0.95),
              (dataMax: number) => dataMax * 1.05,
            ]}
            tickFormatter={(value: number) => compactMoney(value, market)}
          />
          <Tooltip
            contentStyle={{
              background: '#161b28',
              border: '1px solid #262d3d',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value, name) => [formatMoney(Number(value), market), String(name)]}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Line
            type="monotone"
            dataKey="strategy"
            name="Strategy"
            stroke="#5b8def"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="buyHold"
            name="Buy & hold"
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
          {entry && (
            <ReferenceDot
              x={entry.date}
              y={entry.strategy}
              r={5}
              fill="#26a69a"
              stroke="#0b0e14"
              strokeWidth={2}
            />
          )}
          {exit && (
            <ReferenceDot
              x={exit.date}
              y={exit.strategy}
              r={5}
              fill="#ef5350"
              stroke="#0b0e14"
              strokeWidth={2}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Underwater (drawdown) curve derived from the same equity series. */
export function DrawdownChart({ result }: { result: BacktestResult }) {
  let peak = Number.NEGATIVE_INFINITY
  const data = result.equity_curve.map((point) => {
    peak = Math.max(peak, point.portfolio_value)
    return {
      date: point.date,
      drawdown: peak > 0 ? ((point.portfolio_value - peak) / peak) * 100 : 0,
    }
  })

  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#64748b', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: '#262d3d' }}
            minTickGap={48}
            tickFormatter={(value: string) => value.slice(0, 7)}
          />
          <YAxis
            tick={{ fill: '#64748b', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
            // Drawdown is never positive: anchor the top at 0% and pad 15% below the
            // deepest trough so a sharp one-day spike floats clear of the plot floor
            // (never clipped) and the axis keeps clean, even ticks.
            domain={[(dataMin: number) => Math.min(dataMin * 1.15, -1), 0]}
            tickFormatter={(value: number) => `${value.toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{
              background: '#161b28',
              border: '1px solid #262d3d',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(value) => [`${Number(value).toFixed(2)}%`, 'Drawdown']}
          />
          <Line
            type="monotone"
            dataKey="drawdown"
            stroke="#ef5350"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
