import { type CSSProperties } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useSeasonality } from '../api/client'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { Market } from '../schemas/strategy'

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월']
const WEEKDAYS = ['월', '화', '수', '목', '금']

const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`

/** Diverging colour for a monthly return: green up, red down (US convention). */
function cellStyle(v: number | undefined): CSSProperties {
  if (v === undefined) return { backgroundColor: 'transparent' }
  const a = Math.min(Math.abs(v) / 0.12, 1) * 0.85 // saturate around ±12%
  const bg = v >= 0 ? `rgba(22, 163, 74, ${a})` : `rgba(220, 38, 38, ${a})`
  return { backgroundColor: bg, color: a > 0.55 ? 'white' : 'inherit' }
}

export function SeasonalityPage() {
  const { ticker = 'AAPL' } = useParams()
  const [params] = useSearchParams()
  const market = (params.get('market') as Market) || 'US'
  const navigate = useNavigate()

  const { data, isLoading, error } = useSeasonality(market, ticker)

  const years = data ? [...new Set(data.monthly.map((c) => c.year))].sort((a, b) => b - a) : []
  const cell = new Map(data?.monthly.map((c) => [`${c.year}-${c.month}`, c.return_pct]))
  const tom = data?.turn_of_month

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-6">
      <header>
        <h1 className="text-xl font-semibold text-primary">계절성 / Seasonality</h1>
        <p className="mt-1 text-sm text-secondary">
          월별·요일별 수익률 패턴과 월말 효과를 살펴봅니다.
        </p>
      </header>

      <div className="card p-4">
        <TickerPicker
          ticker={ticker}
          market={market}
          onSelect={(t, m) => navigate(`/seasonality/${encodeURIComponent(t)}?market=${m}`)}
        />
      </div>

      {isLoading && <Spinner label="계절성 계산 중…" />}
      {error && <ErrorNote error={error} />}

      {data && (
        <>
          <div className="card overflow-x-auto p-4">
            <h2 className="mb-3 text-sm font-semibold text-primary">
              월별 수익률 / Monthly returns
              <span className="ml-2 font-normal text-secondary">
                {data.name} · {data.start_year}–{data.end_year}
              </span>
            </h2>
            <table className="w-full border-collapse text-center text-xs">
              <thead>
                <tr>
                  <th className="p-1.5 text-left text-secondary">연도</th>
                  {MONTHS.map((m) => (
                    <th key={m} className="p-1.5 font-medium text-secondary">{m}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {years.map((y) => (
                  <tr key={y}>
                    <th className="p-1.5 text-left font-mono text-secondary">{y}</th>
                    {MONTHS.map((_, i) => {
                      const v = cell.get(`${y}-${i + 1}`)
                      return (
                        <td key={i} className="p-1.5 tabular-nums" style={cellStyle(v)}>
                          {v === undefined ? '' : (v * 100).toFixed(1)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-slate-200">
                  <th className="p-1.5 text-left text-secondary">평균</th>
                  {MONTHS.map((_, i) => {
                    const s = data.month_stats.find((m) => m.month === i + 1)
                    return (
                      <td key={i} className="p-1.5 font-semibold tabular-nums" style={cellStyle(s?.mean)}>
                        {s ? (s.mean * 100).toFixed(1) : ''}
                      </td>
                    )
                  })}
                </tr>
                <tr>
                  <th className="p-1.5 text-left text-secondary">상승률</th>
                  {MONTHS.map((_, i) => {
                    const s = data.month_stats.find((m) => m.month === i + 1)
                    return (
                      <td key={i} className="p-1.5 tabular-nums text-secondary">
                        {s ? `${Math.round(s.positive_rate * 100)}%` : ''}
                      </td>
                    )
                  })}
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-primary">요일별 / Day of week</h2>
              <div className="space-y-2">
                {data.weekday_stats.map((w) => {
                  const width = Math.min(Math.abs(w.mean) / 0.004, 1) * 100
                  return (
                    <div key={w.weekday} className="flex items-center gap-3 text-xs">
                      <span className="w-6 text-secondary">{WEEKDAYS[w.weekday]}</span>
                      <div className="relative h-4 flex-1 rounded bg-slate-100">
                        <div
                          className={`absolute top-0 h-4 rounded ${w.mean >= 0 ? 'bg-up' : 'bg-down'}`}
                          style={{ width: `${width / 2}%`, left: w.mean >= 0 ? '50%' : undefined,
                                   right: w.mean < 0 ? '50%' : undefined }}
                        />
                        <div className="absolute left-1/2 top-0 h-4 w-px bg-slate-300" />
                      </div>
                      <span className="w-20 text-right tabular-nums text-primary">
                        {pct(w.mean, 3)}
                      </span>
                      <span className="w-10 text-right tabular-nums text-secondary">
                        {Math.round(w.positive_rate * 100)}%
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-primary">
                월말 효과 / Turn of month
              </h2>
              {tom && (
                <div className="space-y-3 text-sm">
                  <div className="flex items-baseline justify-between">
                    <span className="text-secondary">월말 3거래일 평균</span>
                    <span className={`tabular-nums ${tom.turn_mean >= 0 ? 'text-up' : 'text-down'}`}>
                      {pct(tom.turn_mean, 3)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-secondary">그 외 거래일 평균</span>
                    <span className={`tabular-nums ${tom.rest_mean >= 0 ? 'text-up' : 'text-down'}`}>
                      {pct(tom.rest_mean, 3)}
                    </span>
                  </div>
                  <div className="border-t border-slate-100 pt-3 text-xs text-secondary">
                    차이 {pct(tom.turn_mean - tom.rest_mean, 3)} · 표본 {tom.turn_count} /{' '}
                    {tom.rest_count}일
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
