import { Sparkles } from 'lucide-react'
import { useLocation } from 'react-router-dom'

import { ComingSoon } from '../components/ui/ComingSoon'
import { NAV_TABS, PLACEHOLDER_COPY } from '../config/navigation'

/** Renders the "coming soon" screen for any not-yet-built tab, keyed off the route. */
export function PlaceholderPage() {
  const { pathname } = useLocation()
  const tab =
    NAV_TABS.find((t) => pathname === t.match || pathname.startsWith(`${t.match}/`)) ?? null
  const key = tab?.match ?? pathname
  const description =
    PLACEHOLDER_COPY[key] ?? '이 기능은 곧 추가됩니다.'

  return (
    <ComingSoon
      icon={tab?.icon ?? Sparkles}
      titleKo={tab?.ko ?? '준비 중'}
      titleEn={tab?.en ?? 'Coming soon'}
      description={description}
    />
  )
}
