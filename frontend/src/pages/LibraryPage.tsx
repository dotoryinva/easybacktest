import { Link } from 'react-router-dom'

import { useStrategies } from '../api/client'
import { ErrorNote } from '../components/ui/ErrorNote'
import { Spinner } from '../components/ui/Spinner'
import { strategyTags } from '../utils/describe'
import { formatPct } from '../utils/format'

export function LibraryPage() {
  const { data, isLoading, error } = useStrategies()

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">
          전략 목록 / Strategy Library
        </h1>
        <Link to="/build" className="btn-primary">
          + 새 전략 / New
        </Link>
      </div>

      {error && <ErrorNote error={error} />}
      {isLoading && <Spinner label="Loading strategies…" />}

      {data?.length === 0 && (
        <div className="card px-6 py-12 text-center">
          <p className="text-sm text-slate-400">
            저장된 전략이 없습니다 / No saved strategies yet.
          </p>
          <Link to="/build" className="btn-primary mt-4">
            첫 전략 만들기 / Build your first strategy
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {data?.map(({ strategy, updated_at }) => (
          <Link
            key={strategy.id}
            to={`/library/${strategy.id}`}
            className="card block p-4 transition-colors hover:border-ink-600 hover:bg-ink-850"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="text-base font-semibold text-primary">{strategy.name}</h2>
              <span className="text-xs text-slate-500">
                {new Date(updated_at).toLocaleDateString()}
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-slate-400">
              {strategy.description}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {strategyTags(strategy).map((tag) => (
                <span key={tag} className="chip">
                  {tag}
                </span>
              ))}
              {strategy.stop_loss_pct != null && (
                <span className="chip border-down/40 text-down">
                  −{formatPct(strategy.stop_loss_pct, 1)}
                </span>
              )}
              {strategy.take_profit_pct != null && (
                <span className="chip border-up/40 text-up">
                  +{formatPct(strategy.take_profit_pct, 1)}
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
