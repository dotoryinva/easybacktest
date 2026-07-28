import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Candle } from '../../schemas/backtest'

export type CompareSeries = {
  key: string // unique — `${market}:${ticker}`
  label: string
  color: string
  candles: Candle[]
}

/**
 * Normalised comparison: every series is rebased to 0% at its first bar in the visible
 * window, so assets at very different price levels can be compared on one axis.
 */
export function ComparisonChart({
  series,
  visibleStart,
  height = 460,
}: {
  series: CompareSeries[]
  visibleStart: string | null
  height?: number
}) {
  const data = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>()
    for (const s of series) {
      const pts = (visibleStart ? s.candles.filter((c) => c.time >= visibleStart) : s.candles).filter(
        (c) => Number.isFinite(c.close) && c.close > 0,
      )
      const base = pts[0]?.close
      if (!base) continue
      for (const p of pts) {
        const row = byDate.get(p.time) ?? { date: p.time }
        row[s.key] = (p.close / base - 1) * 100
        byDate.set(p.time, row)
      }
    }
    return [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : 1))
  }, [series, visibleStart])

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="#F1F5F9" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#94A3B8', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: '#E2E8F0' }}
            minTickGap={48}
            tickFormatter={(v: string) => v.slice(0, 7)}
          />
          <YAxis
            tick={{ fill: '#94A3B8', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={52}
            tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#64748b' }}
            formatter={(value, name) => {
              const s = series.find((x) => x.key === name)
              const v = Number(value)
              return [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, s?.label ?? String(name)]
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            formatter={(value) => series.find((x) => x.key === value)?.label ?? value}
          />
          <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="3 3" />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.key}
              stroke={s.color}
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
