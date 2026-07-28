import type { BacktestMetrics } from '../../schemas/backtest'
import { formatNumber, formatPct, toneClass } from '../../utils/format'

type Props = {
  metrics: BacktestMetrics
  buyHoldReturn?: number | null
}

function Cell({
  label,
  value,
  tone,
  hint,
}: {
  label: string
  value: string
  tone?: string
  hint?: string
}) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-0.5 font-mono text-lg ${tone ?? 'text-primary'}`}>{value}</div>
      {hint && <div className="text-[11px] text-slate-500">{hint}</div>}
    </div>
  )
}

export function MetricsGrid({ metrics, buyHoldReturn }: Props) {
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      <Cell
        label="총 수익률 / Total return"
        value={formatPct(metrics.total_return_pct)}
        tone={toneClass(metrics.total_return_pct)}
        hint={
          buyHoldReturn != null
            ? `Buy & hold ${formatPct(buyHoldReturn)}`
            : undefined
        }
      />
      <Cell label="CAGR" value={formatPct(metrics.cagr)} tone={toneClass(metrics.cagr)} />
      <Cell label="MDD" value={formatPct(metrics.mdd)} tone="text-down" />
      <Cell label="Sharpe" value={formatNumber(metrics.sharpe_ratio)} />
      <Cell label="Sortino" value={formatNumber(metrics.sortino_ratio)} />
      <Cell
        label="승률 / Win rate"
        value={formatPct(metrics.win_rate, 1)}
        hint={`avg win ${formatPct(metrics.avg_win_pct, 1)} · avg loss ${formatPct(
          metrics.avg_loss_pct,
          1,
        )}`}
      />
      <Cell
        label="거래 횟수 / Trades"
        value={String(metrics.num_trades)}
        hint={
          metrics.profit_factor != null
            ? `profit factor ${formatNumber(metrics.profit_factor)}`
            : 'no losing trades'
        }
      />
      <Cell
        label="평균 보유 / Avg hold"
        value={`${formatNumber(metrics.avg_holding_days, 0)}d`}
      />
    </div>
  )
}
