import { createBrowserRouter, Navigate } from 'react-router-dom'

import App from './App'
import { AllocationPage } from './pages/AllocationPage'
import { BuildPage } from './pages/BuildPage'
import { ChartPage } from './pages/ChartPage'
import { CorrelationPage } from './pages/CorrelationPage'
import { EtfPage } from './pages/EtfPage'
import { HeatmapPage } from './pages/HeatmapPage'
import { LibraryPage } from './pages/LibraryPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { RetirementPage } from './pages/RetirementPage'
import { ScreenerPage } from './pages/ScreenerPage'
import { SeasonalityPage } from './pages/SeasonalityPage'
import { StrategyDetailPage } from './pages/StrategyDetailPage'
import { WatchlistPage } from './pages/WatchlistPage'

// Tabs that render a styled "coming soon" placeholder (Change 14 Tier 3 + pending pages).
const PLACEHOLDER_PATHS = [
  'holdings',
  'ai',
  'macro',
  'rs',
  'guru',
  'global',
  'coins',
  'allocation/examples', // Change 15.9 — curated gallery, deferred
  'partnership',
]

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/build" replace /> },
      { path: 'build', element: <BuildPage /> },
      { path: 'chart/:ticker', element: <ChartPage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'library/:id', element: <StrategyDetailPage /> },
      { path: 'correlation', element: <CorrelationPage /> },
      // Change 15: unified allocation. The old static/dynamic tabs redirect here.
      { path: 'allocation', element: <AllocationPage /> },
      { path: 'allocation/static', element: <Navigate to="/allocation" replace /> },
      { path: 'allocation/dynamic', element: <Navigate to="/allocation" replace /> },
      { path: 'seasonality/:ticker', element: <SeasonalityPage /> },
      // Change 17 — market-data & planning tabs.
      { path: 'watchlist', element: <WatchlistPage /> },
      { path: 'heatmap', element: <HeatmapPage /> },
      { path: 'etfs', element: <EtfPage /> },
      { path: 'screener', element: <ScreenerPage /> },
      { path: 'retirement', element: <RetirementPage /> },
      ...PLACEHOLDER_PATHS.map((path) => ({ path, element: <PlaceholderPage /> })),
      { path: '*', element: <Navigate to="/build" replace /> },
    ],
  },
])
