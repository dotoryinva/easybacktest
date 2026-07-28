import {
  Activity,
  Bitcoin,
  Bot,
  CalendarDays,
  CandlestickChart,
  Filter,
  Globe,
  LayoutGrid,
  Layers,
  Library,
  Network,
  PieChart,
  PiggyBank,
  Sparkles,
  Star,
  TrendingUp,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react'

export type NavTab = {
  /** Route prefix used to mark the tab active. */
  match: string
  /** Link target (may carry a query string). */
  to: string
  ko: string
  en: string
  icon: LucideIcon
  tier: 1 | 2 | 3
  /** Shown in the mobile bottom bar (max 3 + 더보기). */
  primary?: boolean
}

export const NAV_TABS: NavTab[] = [
  // Tier 1 — core, already built (Watchlist is a Tier-3 placeholder for now).
  { match: '/build', to: '/build', ko: '매수', en: 'Build', icon: Sparkles, tier: 1, primary: true },
  { match: '/chart', to: '/chart/AAPL?market=US', ko: '차트', en: 'Chart', icon: CandlestickChart, tier: 1, primary: true },
  { match: '/library', to: '/library', ko: '라이브러리', en: 'Library', icon: Library, tier: 1, primary: true },
  { match: '/watchlist', to: '/watchlist', ko: '관심목록', en: 'Watchlist', icon: Star, tier: 3 },

  // Tier 2 — analytical tools.
  { match: '/allocation', to: '/allocation', ko: '자산배분', en: 'Allocation', icon: PieChart, tier: 2 },
  { match: '/heatmap', to: '/heatmap', ko: '히트맵', en: 'Heatmap', icon: LayoutGrid, tier: 2 },
  { match: '/seasonality', to: '/seasonality/AAPL?market=US', ko: '계절성', en: 'Seasonality', icon: CalendarDays, tier: 2 },
  { match: '/correlation', to: '/correlation', ko: '상관관계', en: 'Correlation', icon: Network, tier: 2 },
  { match: '/etfs', to: '/etfs', ko: 'ETF', en: 'ETF', icon: Layers, tier: 2 },
  { match: '/screener', to: '/screener', ko: '스크리너', en: 'Screener', icon: Filter, tier: 2 },

  // Tier 3 — styled placeholders.
  { match: '/holdings', to: '/holdings', ko: '보유', en: 'Holdings', icon: Wallet, tier: 3 },
  { match: '/retirement', to: '/retirement', ko: '은퇴', en: 'Retirement', icon: PiggyBank, tier: 3 },
  { match: '/ai', to: '/ai', ko: 'AI', en: 'AI', icon: Bot, tier: 3 },
  { match: '/macro', to: '/macro', ko: '매크로', en: 'Macro', icon: Activity, tier: 3 },
  { match: '/rs', to: '/rs', ko: 'RS', en: 'RS', icon: TrendingUp, tier: 3 },
  { match: '/guru', to: '/guru', ko: 'Guru', en: 'Guru', icon: Users, tier: 3 },
  { match: '/global', to: '/global', ko: '글로벌', en: 'Global', icon: Globe, tier: 3 },
  { match: '/coins', to: '/coins', ko: '코인', en: 'Coins', icon: Bitcoin, tier: 3 },
]

/** Long-form copy for the "coming soon" placeholder pages (Change 14.3 + pending Tier 2). */
export const PLACEHOLDER_COPY: Record<string, string> = {
  '/allocation/static':
    '정적 자산배분 백테스트는 곧 추가됩니다. 영구 포트폴리오·60/40·올웨더 같은 고정 비중 포트폴리오를 정기 리밸런싱하며 검증할 수 있게 됩니다.',
  '/allocation/dynamic':
    '동적 자산배분은 곧 추가됩니다. 듀얼 모멘텀, VAA, LAA, GTAA 등 규칙 기반 로테이션 전략을 지원할 예정입니다.',
  '/holdings':
    '보유 종목 트래킹 기능은 곧 추가됩니다. 매매 기록을 입력하면 실시간 손익, 자산 배분 현황, 배당 캘린더를 볼 수 있게 됩니다.',
  '/ai':
    'AI 종목 분석 기능은 곧 추가됩니다. 종목명을 입력하면 AI가 재무, 밸류에이션, 최근 뉴스를 종합해 리포트를 생성합니다.',
  '/macro':
    '매크로 지표 대시보드는 곧 추가됩니다. 금리, CPI, 실업률, PMI 등 주요 지표 차트를 볼 수 있습니다.',
  '/rs':
    '상대강도(RS) 랭킹은 곧 추가됩니다. 시장 대비 상대적 강세 종목을 마크 미너비니 방식으로 찾을 수 있습니다.',
  '/guru':
    '구루 포트폴리오는 곧 추가됩니다. 워런 버핏, 레이 달리오 등 유명 투자자의 13F 공시를 추적할 예정입니다.',
  '/global':
    '글로벌 시장은 곧 추가됩니다. 일본, 중국, 유럽, 신흥국 지수와 주요 종목을 지원할 예정입니다.',
  '/coins':
    '암호화폐는 곧 추가됩니다. 비트코인, 이더리움 등 주요 코인의 백테스트를 지원할 예정입니다.',
}
