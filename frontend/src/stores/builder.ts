/** Local UI state: the strategy-builder session and chart preferences. */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { BacktestResult } from '../schemas/backtest'
import type { ChatMessage, Market, Strategy } from '../schemas/strategy'
import { yearsAgo, isoDate } from '../utils/format'

export const MAX_CLARIFICATION_ROUNDS = 3

export type BuilderPhase = 'input' | 'clarifying' | 'preview' | 'editing' | 'ai_edit' | 'result'
export type BuilderMode = 'ai' | 'manual'

/** A blank but structurally valid strategy for a fresh manual session. */
export function emptyStrategy(): Strategy {
  return {
    id: `s_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`,
    name: '',
    description: '',
    language: 'ko',
    buy_conditions: [
      {
        left: { kind: 'SMA', params: { period: 20 } },
        operator: 'cross_above',
        right: { kind: 'SMA', params: { period: 60 } },
      },
    ],
    sell_conditions: [],
    stop_loss_pct: null,
    take_profit_pct: null,
    max_holding_days: null,
    position_sizing: 'all_in',
    position_size_value: null,
    allow_reentry_same_day: false,
    cooldown_days_after_exit: 0,
    created_at: new Date().toISOString(),
  }
}

type BuilderState = {
  ticker: string
  market: Market
  startDate: string
  endDate: string
  initialCapital: number

  draft: string
  history: ChatMessage[]
  questions: string[]
  rounds: number

  strategy: Strategy | null
  result: BacktestResult | null
  phase: BuilderPhase

  mode: BuilderMode
  /** Manual-mode form state, kept alive while the user is over in AI mode. */
  manualDraft: Strategy | null

  setMode: (mode: BuilderMode) => void
  setManualDraft: (strategy: Strategy) => void
  /** AI → Manual: carry the previewed strategy into the form. */
  adoptIntoManual: (strategy: Strategy) => void

  setTicker: (ticker: string, market: Market) => void
  setPeriod: (start: string, end: string) => void
  setInitialCapital: (value: number) => void
  setDraft: (value: string) => void

  /** Record the turn we just sent, so the next request carries full context. */
  pushUserTurn: (content: string) => void
  applyClarification: (questions: string[]) => void
  applyStrategy: (strategy: Strategy) => void
  updateStrategy: (strategy: Strategy) => void
  /** Open the AI composer to revise an existing strategy (AI-created or manual). */
  startAiEdit: (strategy: Strategy) => void
  setResult: (result: BacktestResult | null) => void
  setPhase: (phase: BuilderPhase) => void
  loadStrategy: (strategy: Strategy) => void
  reset: () => void
}

/** Default capital differs by market: ~10M KRW vs a comparable USD figure. */
export function defaultCapital(market: Market): number {
  return market === 'KR' ? 10_000_000 : 10_000
}

const initialSession = {
  draft: '',
  history: [] as ChatMessage[],
  questions: [] as string[],
  rounds: 0,
  strategy: null as Strategy | null,
  result: null as BacktestResult | null,
  phase: 'input' as BuilderPhase,
}

export const useBuilderStore = create<BuilderState>()(
  persist(
    (set, get) => ({
      ticker: '005930',
      market: 'KR',
      startDate: yearsAgo(5),
      endDate: isoDate(new Date()),
      initialCapital: defaultCapital('KR'),
      ...initialSession,

      mode: 'ai',
      manualDraft: null,

      setMode: (mode) => set({ mode }),
      setManualDraft: (manualDraft) => set({ manualDraft }),
      adoptIntoManual: (strategy) =>
        set({ manualDraft: structuredClone(strategy), mode: 'manual' }),

      setTicker: (ticker, market) =>
        set((state) => ({
          ticker,
          market,
          // Only re-baseline capital if the user hadn't customised it.
          initialCapital:
            state.initialCapital === defaultCapital(state.market)
              ? defaultCapital(market)
              : state.initialCapital,
        })),
      setPeriod: (startDate, endDate) => set({ startDate, endDate }),
      setInitialCapital: (initialCapital) => set({ initialCapital }),
      setDraft: (draft) => set({ draft }),

      pushUserTurn: (content) =>
        set((state) => ({
          history: [...state.history, { role: 'user', content }],
          draft: '',
        })),

      applyClarification: (questions) =>
        set((state) => ({
          questions,
          rounds: state.rounds + 1,
          phase: 'clarifying',
          history: [...state.history, { role: 'assistant', content: questions.join('\n') }],
        })),

      applyStrategy: (strategy) =>
        set((state) => ({
          strategy,
          questions: [],
          phase: 'preview',
          result: null,
          history: [
            ...state.history,
            { role: 'assistant', content: `Created strategy: ${strategy.name}` },
          ],
        })),

      updateStrategy: (strategy) => set({ strategy, result: null }),

      startAiEdit: (strategy) =>
        set({
          mode: 'ai',
          strategy,
          phase: 'ai_edit',
          draft: '',
          result: null,
        }),

      setResult: (result) => set({ result, phase: result ? 'result' : get().phase }),
      setPhase: (phase) => set({ phase }),

      loadStrategy: (strategy) =>
        set({ ...initialSession, strategy, phase: 'preview' }),

      reset: () => set({ ...initialSession }),
    }),
    {
      name: 'easybacktest.builder',
      // Persist only the inputs a returning user would want back — not the session.
      partialize: (state) => ({
        ticker: state.ticker,
        market: state.market,
        startDate: state.startDate,
        endDate: state.endDate,
        initialCapital: state.initialCapital,
        // Returning visitors land in the mode they last used.
        mode: state.mode,
        manualDraft: state.manualDraft,
      }),
    },
  ),
)

/** Matches the backend's SMA/EMA period bounds so the chart can't plot what the
 *  engine would reject. */
export const MIN_PERIOD = 2
export const MAX_PERIOD = 500

type ChartPrefs = {
  smaPeriods: number[]
  emaPeriods: number[]
  /** Periods added through the 커스텀 row, i.e. outside the preset chip lists. */
  customSma: number[]
  customEma: number[]
  toggleSma: (period: number) => void
  toggleEma: (period: number) => void
  addCustom: (kind: 'sma' | 'ema', period: number) => string | null
  removeCustom: (kind: 'sma' | 'ema', period: number) => void
}

const sorted = (values: number[]) => [...new Set(values)].sort((a, b) => a - b)

export const useChartPrefs = create<ChartPrefs>()(
  persist(
    (set, get) => ({
      smaPeriods: [20, 60],
      emaPeriods: [],
      customSma: [],
      customEma: [],

      toggleSma: (period) =>
        set((state) => ({
          smaPeriods: state.smaPeriods.includes(period)
            ? state.smaPeriods.filter((p) => p !== period)
            : sorted([...state.smaPeriods, period]),
        })),
      toggleEma: (period) =>
        set((state) => ({
          emaPeriods: state.emaPeriods.includes(period)
            ? state.emaPeriods.filter((p) => p !== period)
            : sorted([...state.emaPeriods, period]),
        })),

      /** Returns an error message, or null on success. */
      addCustom: (kind, period) => {
        if (!Number.isInteger(period)) return '정수만 입력할 수 있습니다'
        if (period < MIN_PERIOD || period > MAX_PERIOD)
          return `기간은 ${MIN_PERIOD}–${MAX_PERIOD} 사이여야 합니다`

        const state = get()
        const preset = kind === 'sma' ? state.smaPeriods : state.emaPeriods
        const custom = kind === 'sma' ? state.customSma : state.customEma
        if (preset.includes(period) || custom.includes(period))
          return '이미 표시 중인 기간입니다'

        set(
          kind === 'sma'
            ? { customSma: sorted([...custom, period]) }
            : { customEma: sorted([...custom, period]) },
        )
        return null
      },

      removeCustom: (kind, period) =>
        set((state) =>
          kind === 'sma'
            ? { customSma: state.customSma.filter((p) => p !== period) }
            : { customEma: state.customEma.filter((p) => p !== period) },
        ),
    }),
    {
      name: 'easybacktest.chart',
      version: 2,
      // v1 had no custom arrays; give them a default rather than dropping the prefs.
      migrate: (persisted) => ({
        customSma: [],
        customEma: [],
        ...(persisted as object),
      }),
    },
  ),
)
