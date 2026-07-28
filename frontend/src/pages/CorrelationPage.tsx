import { X } from 'lucide-react'
import { type CSSProperties, useState } from 'react'

import { useCorrelationMatrix } from '../api/client'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { Market } from '../schemas/strategy'

type Sel = { ticker: string; market: Market }

const ISO = (d: Date) => d.toISOString().slice(0, 10)
const DEFAULT_END = ISO(new Date())
const DEFAULT_START = ISO(new Date(Date.now() - 3 * 365 * 24 * 3600 * 1000))

/** Diverging colour: red for positive correlation, blue for negative, faint near zero. */
function cellStyle(v: number): CSSProperties {
  const a = Math.min(Math.abs(v), 1)
  const bg = v >= 0 ? `rgba(220, 38, 38, ${a * 0.85})` : `rgba(37, 99, 235, ${a * 0.85})`
  return { backgroundColor: bg, color: a > 0.55 ? 'white' : 'inherit' }
}

export function CorrelationPage() {
  const [tickers, setTickers] = useState<Sel[]>([
    { ticker: '005930', market: 'KR' },
    { ticker: '000660', market: 'KR' },
  ])
  const [start, setStart] = useState(DEFAULT_START)
  const [end, setEnd] = useState(DEFAULT_END)
  const [frequency, setFrequency] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const mutation = useCorrelationMatrix()

  const add = (ticker: string, market: Market) => {
    setTickers((prev) =>
      prev.some((t) => t.ticker === ticker && t.market === market) || prev.length >= 15
        ? prev
        : [...prev, { ticker, market }],
    )
  }
  const remove = (t: Sel) =>
    setTickers((prev) => prev.filter((x) => !(x.ticker === t.ticker && x.market === t.market)))

  const result = mutation.data

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-6">
      <header>
        <h1 className="text-xl font-semibold text-primary">상관관계 / Correlation</h1>
        <p className="mt-1 text-sm text-secondary">
          종목 간 수익률 상관계수 매트릭스. 낮을수록 분산 효과가 큽니다.
        </p>
      </header>

      <div className="card space-y-4 p-4">
        <TickerPicker ticker="" market="US" onSelect={add} />

        {tickers.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tickers.map((t) => (
              <span
                key={`${t.market}-${t.ticker}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-primary"
              >
                <span className="font-mono text-accent">{t.ticker}</span>
                <span className="text-secondary">{t.market}</span>
                <button type="button" onClick={() => remove(t)} aria-label="제거">
                  <X size={13} className="text-secondary hover:text-primary" />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-secondary">
            시작 / Start
            <input type="date" className="input mt-1" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="text-xs text-secondary">
            종료 / End
            <input type="date" className="input mt-1" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <label className="text-xs text-secondary">
            주기 / Frequency
            <select
              className="input mt-1"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as typeof frequency)}
            >
              <option value="daily">일간 / Daily</option>
              <option value="weekly">주간 / Weekly</option>
              <option value="monthly">월간 / Monthly</option>
            </select>
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={tickers.length < 2 || mutation.isPending}
            onClick={() =>
              mutation.mutate({ tickers, start_date: start, end_date: end, frequency })
            }
          >
            {mutation.isPending ? '계산 중…' : '계산 / Compute'}
          </button>
        </div>
      </div>

      {mutation.isPending && <Spinner />}
      {mutation.error && <ErrorNote error={mutation.error} />}

      {result && (
        <div className="card overflow-x-auto p-4">
          <table className="w-full border-collapse text-center text-sm">
            <thead>
              <tr>
                <th className="p-2" />
                {result.tickers.map((t) => (
                  <th key={t} className="p-2 font-mono text-xs text-secondary">{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.matrix.map((row, i) => (
                <tr key={result.tickers[i]}>
                  <th className="p-2 text-left font-mono text-xs text-secondary">
                    {result.tickers[i]}
                  </th>
                  {row.map((v, j) => (
                    <td
                      key={j}
                      className="p-2 text-xs tabular-nums"
                      style={cellStyle(v)}
                    >
                      {v.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <table className="mt-5 w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-secondary">
                <th className="p-2">종목</th>
                <th className="p-2 text-right">연 수익률</th>
                <th className="p-2 text-right">연 변동성</th>
                <th className="p-2 text-right">Sharpe</th>
              </tr>
            </thead>
            <tbody>
              {result.stats.map((s) => (
                <tr key={s.ticker} className="border-t border-slate-100">
                  <td className="p-2 font-mono text-xs text-primary">{s.ticker}</td>
                  <td className="p-2 text-right tabular-nums">{(s.mean * 100).toFixed(1)}%</td>
                  <td className="p-2 text-right tabular-nums">{(s.std * 100).toFixed(1)}%</td>
                  <td className="p-2 text-right tabular-nums">{s.sharpe.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
