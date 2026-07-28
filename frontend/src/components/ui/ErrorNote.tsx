import { ApiError } from '../../api/client'

type Props = {
  error: unknown
  className?: string
}

export function ErrorNote({ error, className = '' }: Props) {
  if (!error) return null

  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : String(error)

  const hint =
    error instanceof ApiError && error.status === 404
      ? 'This ticker is not in the local cache. Run scripts/bootstrap_data.py to add it.'
      : error instanceof ApiError && error.status === 503
        ? 'Set GEMINI_API_KEY on the backend to enable the AI strategy builder.'
        : error instanceof ApiError && error.status === 0
          ? 'Start the backend with: uvicorn app.main:app --reload'
          : null

  return (
    <div
      role="alert"
      className={`rounded-lg border border-down/40 bg-down/10 px-3 py-2 text-sm text-down ${className}`}
    >
      <div>{message}</div>
      {hint && <div className="mt-1 text-xs text-down/80">{hint}</div>}
    </div>
  )
}
