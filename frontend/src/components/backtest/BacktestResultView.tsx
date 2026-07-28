import { useState } from 'react'

import { ApiError, downloadBacktestReport, type ReportFormat } from '../../api/client'
import type { BacktestResult, Trade } from '../../schemas/backtest'
import { formatMoney } from '../../utils/format'
import { DrawdownChart, EquityCurve } from './EquityCurve'
import { MetricsGrid } from './MetricsGrid'
import { TradeLogTable } from './TradeLogTable'

export function BacktestResultView({ result }: { result: BacktestResult }) {
  const [selected, setSelected] = useState<Trade | null>(null)
  const [downloading, setDownloading] = useState<ReportFormat | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)

  const first = result.equity_curve.at(0)
  const last = result.equity_curve.at(-1)
  const buyHoldReturn =
    first && last ? last.buy_hold_value / result.params.initial_capital - 1 : null

  const handleDownloadReport = async (format: ReportFormat) => {
    if (downloading) return
    setDownloading(format)
    setReportError(null)
    try {
      await downloadBacktestReport(result, format)
    } catch (err) {
      setReportError(
        err instanceof ApiError ? err.message : '리포트 생성에 실패했습니다.',
      )
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="space-y-5">
      <div className="card p-4 lg:p-5">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-primary">
            자산 곡선 / Equity curve
            <span className="ml-2 font-normal text-slate-500">
              {result.params.market}/{result.params.ticker} · {result.params.start_date} →{' '}
              {result.params.end_date}
            </span>
          </h3>
          <div className="flex items-center gap-3">
            {last && (
              <span className="font-mono text-sm text-secondary">
                {formatMoney(result.params.initial_capital, result.params.market)} →{' '}
                {formatMoney(last.portfolio_value, result.params.market)}
              </span>
            )}
            <div className="inline-flex items-center overflow-hidden rounded-md border border-ink-700 bg-ink-800 text-xs font-medium text-secondary">
              <span className="hidden px-2.5 py-1.5 text-slate-500 sm:inline">📊 상세 리포트</span>
              <button
                type="button"
                onClick={() => handleDownloadReport('html')}
                disabled={!!downloading}
                className="inline-flex items-center gap-1.5 border-l border-ink-700 px-3 py-1.5 transition hover:bg-ink-700 hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                title="상세 지표·차트가 담긴 HTML 리포트를 내려받습니다"
              >
                {downloading === 'html' ? (
                  <>
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
                    생성 중…
                  </>
                ) : (
                  'HTML'
                )}
              </button>
              <button
                type="button"
                onClick={() => handleDownloadReport('pdf')}
                disabled={!!downloading}
                className="inline-flex items-center gap-1.5 border-l border-ink-700 px-3 py-1.5 transition hover:bg-ink-700 hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                title="동일한 리포트를 PDF로 내려받습니다 (생성에 몇 초 걸립니다)"
              >
                {downloading === 'pdf' ? (
                  <>
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
                    생성 중…
                  </>
                ) : (
                  'PDF'
                )}
              </button>
            </div>
          </div>
        </div>
        {reportError && (
          <p className="mb-3 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            {reportError}
          </p>
        )}
        <EquityCurve result={result} highlighted={selected} />
        <div className="mt-2 border-t border-ink-700 pt-2">
          <div className="label">Drawdown</div>
          <DrawdownChart result={result} />
        </div>
      </div>

      <MetricsGrid metrics={result.metrics} buyHoldReturn={buyHoldReturn} />

      <div className="card p-4 lg:p-5">
        <h3 className="mb-3 text-sm font-semibold text-primary">
          거래 내역 / Trade log
        </h3>
        <TradeLogTable
          trades={result.trades}
          market={result.params.market}
          selected={selected}
          onSelect={setSelected}
        />
      </div>
    </div>
  )
}
