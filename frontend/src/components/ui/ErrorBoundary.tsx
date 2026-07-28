import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
}

type State = {
  error: Error | null
}

/**
 * Top-level render-error safety net. A thrown error anywhere below is caught here and
 * shown as a recoverable screen instead of a blank white page. Network/data errors are
 * handled per-view by `ErrorNote`; this only catches unexpected render crashes.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary] render error:', error, info.componentStack)
  }

  private reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div
        role="alert"
        className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-6 text-center"
      >
        <div className="grid h-12 w-12 place-items-center rounded-full bg-down/10 text-2xl">
          ⚠️
        </div>
        <div>
          <h1 className="text-lg font-semibold text-primary">문제가 발생했습니다</h1>
          <p className="mt-1 text-sm text-secondary">
            Something went wrong while rendering this page.
          </p>
        </div>
        {error.message && (
          <pre className="max-w-full overflow-x-auto rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-left text-xs text-secondary">
            {error.message}
          </pre>
        )}
        <button
          type="button"
          onClick={this.reset}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90"
        >
          다시 시도 / Retry
        </button>
      </div>
    )
  }
}
