import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useParseStrategy, useRunBacktest, useSaveStrategy } from '../api/client'
import { BacktestResultView } from '../components/backtest/BacktestResultView'
import { ConversationThread } from '../components/builder/ConversationThread'
import { FamilySelector, type StrategyFamily } from '../components/builder/FamilySelector'
import { ModeToggle, type BuilderMode } from '../components/builder/ModeToggle'
import { QuantBuilder } from '../components/builder/quant/QuantBuilder'
import { StrategyFormEditor } from '../components/builder/StrategyFormEditor'
import { StrategyPreviewCard } from '../components/builder/StrategyPreviewCard'
import { TickerPicker } from '../components/builder/TickerPicker'
import { ManualBuilder } from '../components/builder/manual/ManualBuilder'
import { ErrorNote } from '../components/ui/ErrorNote'
import type { BacktestParams } from '../schemas/backtest'
import { strategyIsRunnable, type Strategy } from '../schemas/strategy'
import { MAX_CLARIFICATION_ROUNDS, emptyStrategy, useBuilderStore } from '../stores/builder'

const PLACEHOLDER = `예: 20일 이동평균선이 60일 이동평균선을 상향돌파할 때 사고, 하향돌파할 때 팔아. 5% 손절.

or in English: "Buy when 20-day SMA crosses above 60-day SMA. Sell on cross below. 5% stop loss."`

const EDIT_PLACEHOLDER = `예: 손절을 3%로 바꿔줘 / 매도 조건에 RSI 70 추가해줘

or in English: "Change stop loss to 3%" / "Add RSI 70 as a sell condition"`

export function BuildPage() {
  const navigate = useNavigate()
  const store = useBuilderStore()
  const [answer, setAnswer] = useState('')
  const [family, setFamily] = useState<StrategyFamily>('single_stock')
  const [searchParams, setSearchParams] = useSearchParams()

  const parse = useParseStrategy()
  const run = useRunBacktest()
  const save = useSaveStrategy()

  // Mode resolution: URL param wins, then the persisted preference, then `ai`.
  const urlMode = searchParams.get('mode')
  const mode: BuilderMode = urlMode === 'manual' || urlMode === 'ai' ? urlMode : store.mode

  useEffect(() => {
    if (urlMode !== mode) {
      const next = new URLSearchParams(searchParams)
      next.set('mode', mode)
      setSearchParams(next, { replace: true })
    }
    if (store.mode !== mode) store.setMode(mode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, urlMode])

  const switchMode = (next: BuilderMode) => {
    // Manual → AI keeps the form in Zustand; AI → Manual keeps the conversation.
    // Neither reloads the page — this is a client-side param change only.
    store.setMode(next)
    const params = new URLSearchParams(searchParams)
    params.set('mode', next)
    setSearchParams(params, { replace: false })
  }

  const manualStrategy: Strategy = store.manualDraft ?? emptyStrategy()

  const backtestParams = (): BacktestParams => ({
    ticker: store.ticker,
    market: store.market,
    start_date: store.startDate,
    end_date: store.endDate,
    initial_capital: store.initialCapital,
    slippage: 0.001,
    fee_rate: null,
    sell_tax_rate: null,
  })

  const runManual = () => {
    run.mutate(
      { strategy: manualStrategy, params: backtestParams() },
      { onSuccess: (result) => store.setResult(result) },
    )
  }

  const saveManual = () => {
    save.mutate(manualStrategy, { onSuccess: () => navigate('/library') })
  }

  const submit = (text: string) => {
    const description = text.trim()
    if (!description) return

    const history = [...store.history]
    const editing = store.phase === 'ai_edit' && store.strategy != null
    store.pushUserTurn(description)
    setAnswer('')

    parse.mutate(
      {
        description,
        ticker: store.ticker,
        market: store.market,
        conversation_history: history,
        current_strategy: editing ? store.strategy : undefined,
      },
      {
        onSuccess: (response) => {
          if (response.kind === 'strategy') store.applyStrategy(response.strategy)
          else store.applyClarification(response.questions)
        },
      },
    )
  }

  const runBacktest = () => {
    if (!store.strategy) return
    const params: BacktestParams = {
      ticker: store.ticker,
      market: store.market,
      start_date: store.startDate,
      end_date: store.endDate,
      initial_capital: store.initialCapital,
      slippage: 0.001,
      fee_rate: null,
      sell_tax_rate: null,
    }
    run.mutate(
      { strategy: store.strategy, params },
      { onSuccess: (result) => store.setResult(result) },
    )
  }

  const saveStrategy = () => {
    if (!store.strategy) return
    save.mutate(store.strategy, { onSuccess: () => navigate('/library') })
  }

  const roundsLeft = MAX_CLARIFICATION_ROUNDS - store.rounds
  const runnableError = store.strategy ? strategyIsRunnable(store.strategy) : null
  const showComposer =
    store.phase === 'input' || store.phase === 'clarifying' || store.phase === 'ai_edit'
  const isAiEdit = store.phase === 'ai_edit' && store.strategy != null
  // The quant builder is universe-based, so it hides the single-ticker controls.
  const showTickerControls = mode === 'ai' || family === 'single_stock'

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4 lg:p-6">
      <ModeToggle mode={mode} onChange={switchMode} />

      {/* Strategy family — single-stock (Family A) vs quant portfolio (Family B). */}
      {mode === 'manual' && <FamilySelector value={family} onChange={setFamily} />}

      {/* Ticker + period controls — single-ticker only; the quant builder is universe-based. */}
      {showTickerControls && (
      <div className="card space-y-4 p-4 lg:p-5">
        <div>
          <div className="label">종목 / Ticker</div>
          <TickerPicker
            ticker={store.ticker}
            market={store.market}
            onSelect={(ticker, market) => store.setTicker(ticker, market)}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            Backtesting{' '}
            <span className="font-mono text-secondary">
              {store.market}/{store.ticker}
            </span>
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <label className="label">시작일 / Start</label>
            <input
              type="date"
              className="input"
              value={store.startDate}
              onChange={(e) => store.setPeriod(e.target.value, store.endDate)}
            />
          </div>
          <div>
            <label className="label">종료일 / End</label>
            <input
              type="date"
              className="input"
              value={store.endDate}
              onChange={(e) => store.setPeriod(store.startDate, e.target.value)}
            />
          </div>
          <div>
            <label className="label">초기 자본 / Capital</label>
            <input
              type="number"
              className="input"
              min={1}
              value={store.initialCapital}
              onChange={(e) => store.setInitialCapital(Number(e.target.value))}
            />
          </div>
        </div>
      </div>
      )}

      {/* ---------------- Manual mode: Family A (single stock) ---------------- */}
      {mode === 'manual' && family === 'single_stock' && (
        <ManualBuilder
          strategy={manualStrategy}
          market={store.market}
          onChange={store.setManualDraft}
          onRun={runManual}
          onSave={saveManual}
          onPreview={() => {
            store.updateStrategy(manualStrategy)
            store.setPhase('preview')
            switchMode('ai')
          }}
          onAiEdit={() => store.startAiEdit(manualStrategy)}
          running={run.isPending}
          saving={save.isPending}
        />
      )}

      {/* ---------------- Manual mode: Family B (quant portfolio) ---------------- */}
      {mode === 'manual' && family === 'quant_portfolio' && <QuantBuilder />}

      {/* ---------------- AI mode ---------------- */}
      {mode === 'ai' && (store.history.length > 0 || isAiEdit) && (
        <div className="card p-4 lg:p-5">
          {isAiEdit && (
            <p className="mb-3 text-xs text-slate-500">
              현재 전략 <span className="font-medium text-primary">{store.strategy!.name}</span>
              을(를) 수정합니다. 바꾸고 싶은 부분을 자연어로 설명하세요.
            </p>
          )}
          <ConversationThread history={store.history} pending={parse.isPending} />
        </div>
      )}

      {mode === 'ai' && parse.error && <ErrorNote error={parse.error} />}

      {/* Composer */}
      {mode === 'ai' && showComposer && (
        <div className="card space-y-3 p-4 lg:p-5">
          {store.phase === 'input' || isAiEdit ? (
            <>
              <label className="label">
                {isAiEdit
                  ? '수정 요청 / Describe what to change'
                  : '전략을 자연어로 설명하세요 / Describe your strategy'}
              </label>
              <textarea
                className="input min-h-[112px] resize-y leading-relaxed"
                rows={4}
                placeholder={isAiEdit ? EDIT_PLACEHOLDER : PLACEHOLDER}
                value={isAiEdit ? answer : store.draft}
                onChange={(e) =>
                  isAiEdit ? setAnswer(e.target.value) : store.setDraft(e.target.value)
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    submit(isAiEdit ? answer : store.draft)
                  }
                }}
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">⌘/Ctrl + Enter to submit</span>
                <div className="flex gap-2">
                  {isAiEdit && (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => store.setPhase('preview')}
                    >
                      취소 / Cancel
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => submit(isAiEdit ? answer : store.draft)}
                    disabled={
                      parse.isPending || !(isAiEdit ? answer.trim() : store.draft.trim())
                    }
                  >
                    {parse.isPending
                      ? '분석 중…'
                      : isAiEdit
                        ? '수정 적용 / Apply Changes'
                        : '전략 만들기 / Build Strategy'}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="label">
                답변해주세요 / Answer to continue
                <span className="ml-2 normal-case text-slate-500">
                  {roundsLeft > 0
                    ? `${roundsLeft} clarification round${roundsLeft === 1 ? '' : 's'} left`
                    : 'last round — please rephrase from scratch'}
                </span>
              </div>
              <textarea
                className="input min-h-[72px] resize-y"
                rows={2}
                placeholder="예: RSI 14 기준으로, 30 아래면 과매도로 봐줘"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(answer)
                }}
              />
              <div className="flex justify-between">
                <button type="button" className="btn-ghost" onClick={store.reset}>
                  처음부터 / Start over
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => submit(answer)}
                  disabled={parse.isPending || !answer.trim()}
                >
                  {parse.isPending ? '분석 중…' : '답변 보내기 / Send'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Strategy preview / editor */}
      {mode === 'ai' && store.strategy && store.phase === 'editing' && (
        <StrategyFormEditor
          strategy={store.strategy}
          onChange={store.updateStrategy}
          onDone={() => store.setPhase('preview')}
        />
      )}

      {mode === 'ai' && store.strategy && store.phase !== 'editing' && store.phase !== 'ai_edit' && (
        <StrategyPreviewCard
          strategy={store.strategy}
          onChange={store.updateStrategy}
          onRun={runBacktest}
          onEditForm={() => store.setPhase('editing')}
          onAiEdit={() => store.startAiEdit(store.strategy!)}
          onEditManual={() => {
            // AI → Manual, carrying the previewed strategy into the form.
            store.adoptIntoManual(store.strategy!)
            switchMode('manual')
          }}
          onSave={saveStrategy}
          onDiscard={store.reset}
          running={run.isPending}
          saving={save.isPending}
          disabledReason={runnableError}
        />
      )}

      {run.error && <ErrorNote error={run.error} />}
      {save.error && <ErrorNote error={save.error} />}

      {store.result && <BacktestResultView result={store.result} />}
    </div>
  )
}
