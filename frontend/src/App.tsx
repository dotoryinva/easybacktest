import { useState } from 'react'
import { MoreHorizontal, X } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { NAV_TABS } from './config/navigation'

const PRIMARY = NAV_TABS.filter((t) => t.primary)

export default function App() {
  const location = useLocation()
  const [moreOpen, setMoreOpen] = useState(false)

  const isActive = (match: string) =>
    location.pathname === match || location.pathname.startsWith(`${match}/`) ||
    (match === '/build' && location.pathname === '/')

  return (
    <div className="min-h-screen pb-16 md:pb-0">
      <header className="sticky top-0 z-40 border-b border-slate-100 bg-canvas/85 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 lg:px-6">
          <div className="flex items-center justify-between gap-6 py-3">
            <NavLink to="/build" className="flex shrink-0 items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-sm font-bold text-white">
                E
              </span>
              <span className="text-sm font-semibold tracking-tight text-primary">
                EasyBacktest
              </span>
            </NavLink>
          </div>

          {/* Desktop: horizontal, scrollable pill row of every tab. */}
          <nav className="hidden gap-1 overflow-x-auto pb-2 md:flex [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {NAV_TABS.map((item) => {
              const active = isActive(item.match)
              const Icon = item.icon
              return (
                <NavLink
                  key={item.match}
                  to={item.to}
                  className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? 'bg-slate-100 text-primary'
                      : 'text-secondary hover:bg-slate-50 hover:text-primary'
                  }`}
                >
                  <Icon size={15} strokeWidth={1.9} />
                  {item.ko}
                </NavLink>
              )
            })}
          </nav>
        </div>
      </header>

      <main>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>

      {/* Mobile: fixed bottom bar with the primary tabs + a 더보기 grid modal. */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-100 bg-canvas/95 backdrop-blur md:hidden">
        {PRIMARY.map((item) => {
          const active = isActive(item.match)
          const Icon = item.icon
          return (
            <NavLink
              key={item.match}
              to={item.to}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
                active ? 'text-accent' : 'text-secondary'
              }`}
            >
              <Icon size={19} strokeWidth={1.9} />
              {item.ko}
            </NavLink>
          )
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-secondary"
        >
          <MoreHorizontal size={19} strokeWidth={1.9} />
          더보기
        </button>
      </nav>

      {moreOpen && (
        <div
          className="fixed inset-0 z-50 flex flex-col bg-canvas md:hidden"
          role="dialog"
          aria-modal="true"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <span className="text-sm font-semibold text-primary">전체 메뉴</span>
            <button type="button" onClick={() => setMoreOpen(false)} aria-label="닫기">
              <X size={20} className="text-secondary" />
            </button>
          </div>
          <div className="grid grid-cols-3 gap-3 overflow-y-auto p-4">
            {NAV_TABS.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.match}
                  to={item.to}
                  onClick={() => setMoreOpen(false)}
                  className="flex flex-col items-center gap-2 rounded-xl border border-slate-100 py-4 text-xs font-medium text-primary hover:bg-slate-50"
                >
                  <Icon size={22} strokeWidth={1.75} className="text-accent" />
                  {item.ko}
                </NavLink>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
