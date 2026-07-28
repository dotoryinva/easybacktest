import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  useDeleteStrategy,
  useDuplicateStrategy,
  useRunBacktest,
  useStrategy,
  useStrategyRuns,
} from '../api/client'
import { BacktestResultView } from '../components/backtest/BacktestResultView'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import type { BacktestParams } from '../schemas/backtest'
import type { Market } from '../schemas/strategy'
import { conditionLabel, positionSizingLabel, strategyTags } from '../utils/describe'
import { defaultCapital, useBuilderStore } from '../stores/builder'
import { formatPct, isoDate, toneClass, yearsAgo } from '../utils/format'

export function StrategyDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const loadStrategy = useBuilderStore((s) => s.loadStrategy)
  const setTicker = useBuilderStore((s) => s.setTicker)

  const { data, isLoading, error } = useStrategy(id)
  const runs = useStrategyRuns(id)
  const run = useRunBacktest()
  const remove = useDeleteStrategy()
  const duplicate = useDuplicateStrategy()

  const [ticker, setLocalTicker] = useState('005930')
  const [market, setMarket] = useState<Market>('KR')
  const [startDate, setStartDate] = useState(yearsAgo(5))
  const [endDate, setEndDate] = useState(isoDate(new Date()))

  if (isLoading) return <div className="p-6"><Spinner label="Loading strategy…" /></div>
  if (error) return <div className="p-6"><ErrorNote error={error} /></div>
  if (!data) return null

  const strategy = data.strategy

  const rerun = () => {
    const params: BacktestParams = {
      ticker,
      market,
      start_date: startDate,
      end_date: endDate,
      initial_capital: defaultCapital(market),
      slippage: 0.001,
      fee_rate: null,
      sell_tax_rate: null,
    }
    run.mutate({ strategy, params }, { onSuccess: () => runs.refetch() })
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(strategy, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${strategy.name.replace(/[^\w가-힣-]+/g, '_')}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4 lg:p-6">
      <Link to="/library" className="text-sm text-slate-400 hover:text-primary">
        ← 전략 목록 / Library
      </Link>

      <div className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-primary">{strategy.name}</h1>
            <p className="mt-1 text-sm text-slate-400">{strategy.description}</p>
          </div>
          <span className="chip">{strategy.language.toUpperCase()}</span>
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5">
          {strategyTags(strategy).map((tag) => (
            <span key={tag} className="chip">
              {tag}
            </span>
          ))}
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="label">매수 / Buy (all)</div>
            <ul className="space-y-1 text-sm text-primary">
              {strategy.buy_conditions.map((c, i) => (
                <li key={i} className="font-mono text-xs">
                  {conditionLabel(c)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="label">매도 / Sell (any)</div>
            <ul className="space-y-1 text-sm text-primary">
              {strategy.sell_conditions.length === 0 && (
                <li className="text-xs text-slate-500">No sell conditions.</li>
              )}
              {strategy.sell_conditions.map((c, i) => (
                <li key={i} className="font-mono text-xs">
                  {conditionLabel(c)}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-700 pt-4">
          {strategy.stop_loss_pct != null && (
            <span className="chip border-down/40 text-down">
              Stop −{formatPct(strategy.stop_loss_pct, 1)}
            </span>
          )}
          {strategy.take_profit_pct != null && (
            <span className="chip border-up/40 text-up">
              Target +{formatPct(strategy.take_profit_pct, 1)}
            </span>
          )}
          {strategy.max_holding_days != null && (
            <span className="chip">Max hold {strategy.max_holding_days}d</span>
          )}
          <span className="chip">{positionSizingLabel(strategy)}</span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-700 pt-4">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              loadStrategy(strategy)
              setTicker(ticker, market)
              navigate('/build')
            }}
          >
            Open in builder
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => duplicate.mutate(strategy.id, { onSuccess: () => navigate('/library') })}
          >
            Duplicate
          </button>
          <button type="button" className="btn-ghost" onClick={exportJson}>
            Export JSON
          </button>
          <button
            type="button"
            className="btn-danger ml-auto"
            onClick={() => {
              if (confirm(`Delete "${strategy.name}"? This cannot be undone.`)) {
                remove.mutate(strategy.id, { onSuccess: () => navigate('/library') })
              }
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Re-run on a different ticker */}
      <div className="card space-y-4 p-5">
        <h2 className="text-sm font-semibold text-primary">
          다른 종목으로 다시 실행 / Re-run on a different ticker
        </h2>
        <TickerPicker
          ticker={ticker}
          market={market}
          onSelect={(t, m) => {
            setLocalTicker(t)
            setMarket(m)
          }}
        />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <label className="label">Start</label>
            <input
              type="date"
              className="input"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div>
            <label className="label">End</label>
            <input
              type="date"
              className="input"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <button
              type="button"
              className="btn-primary w-full"
              onClick={rerun}
              disabled={run.isPending}
            >
              {run.isPending ? '실행 중…' : `Run on ${market}/${ticker}`}
            </button>
          </div>
        </div>
        {run.error && <ErrorNote error={run.error} />}
      </div>

      {/* Recent runs */}
      {(runs.data?.length ?? 0) > 0 && (
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-semibold text-primary">
            최근 실행 / Recent runs
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2">Ticker</th>
                  <th className="pb-2">Period</th>
                  <th className="pb-2 text-right">Return</th>
                  <th className="pb-2 text-right">CAGR</th>
                  <th className="pb-2 text-right">MDD</th>
                  <th className="pb-2 text-right">Trades</th>
                </tr>
              </thead>
              <tbody>
                {runs.data?.map((entry, index) => (
                  <tr key={index} className="border-t border-ink-700">
                    <td className="py-2 font-mono text-secondary">
                      {entry.market}/{entry.ticker}
                    </td>
                    <td className="py-2 text-xs text-slate-500">
                      {entry.params.start_date} → {entry.params.end_date}
                    </td>
                    <td
                      className={`py-2 text-right font-mono ${toneClass(
                        entry.metrics.total_return_pct,
                      )}`}
                    >
                      {formatPct(entry.metrics.total_return_pct)}
                    </td>
                    <td className={`py-2 text-right font-mono ${toneClass(entry.metrics.cagr)}`}>
                      {formatPct(entry.metrics.cagr)}
                    </td>
                    <td className="py-2 text-right font-mono text-down">
                      {formatPct(entry.metrics.mdd)}
                    </td>
                    <td className="py-2 text-right font-mono text-slate-400">
                      {entry.metrics.num_trades}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {run.data && <BacktestResultView result={run.data} />}
    </div>
  )
}
