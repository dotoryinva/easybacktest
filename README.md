# EasyBacktest 🚀

A full-stack backtesting platform with strategy builder, technical analysis, portfolio allocation, and Monte Carlo retirement planning.

**Live:** (coming soon)

## Tech Stack

- **Frontend:** React 18 + Vite + Tailwind CSS + TradingView Lightweight Charts + Recharts
- **Backend:** FastAPI + pandas + numpy + scipy + yfinance
- **State:** Zustand (frontend) + SQLite cache (backend)
- **LLM:** Google Gemini 3.6 Flash (strategy recommendations)

## Features

- 📊 **Chart & Indicators:** candlestick charts with SMA/EMA overlays, 1w–5y timeframes
- 🧠 **Strategy Builder:** visual rule engine + AI-assisted strategy suggestions
- 📈 **Backtesting:** D+1 lookahead-safe execution, cross-market signals (KR/US mix)
- 💼 **Asset Allocation:** static/dynamic rebalancing; scipy optimization (min_variance, max_sharpe, ERC, HRP)
- 📊 **Reports:** QuantStats HTML tearsheets + PDF export
- 🔥 **Market Tools:** price-metric heatmap, ETF browser, screener (RSI/volatility/momentum), correlation matrix
- 🎯 **Retirement:** Monte Carlo simulator with percentile bands, safe-spending calculation
- ⭐ **Watchlist:** persistent ticker tracking with live quotes

## Local Development

### Frontend
```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # production build
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload  # http://localhost:8010
python -m pytest                         # run tests
```

## Deployment

### 1. Push to GitHub
```bash
# Create a new repo on github.com
git remote add origin https://github.com/YOUR_USERNAME/easybacktest.git
git branch -M main
git push -u origin main
```

### 2. Frontend → Vercel
1. Go to [vercel.com](https://vercel.com)
2. Import your GitHub repo
3. Set root directory to `frontend/`
4. Deploy (auto-builds on push)

### 3. Backend → Railway
1. Go to [railway.app](https://railway.app)
2. Import your GitHub repo
3. Select Python environment
4. Add environment variables (if needed):
   - `PYTHONUNBUFFERED=1`
5. Deploy (auto-detects Procfile)

### 4. Connect Frontend to Backend
In `frontend/src/api/client.ts`, change:
```typescript
const API_BASE = process.env.VITE_API_BASE ?? 'https://YOUR-BACKEND.railway.app'
```

Then redeploy frontend on Vercel.

## Project Structure

```
easybacktest/
├── frontend/          # React + Vite
│   ├── src/
│   │   ├── pages/     # Main routes (Build, Chart, Allocation, etc.)
│   │   ├── components/
│   │   ├── api/       # TanStack Query hooks
│   │   ├── stores/    # Zustand state
│   │   └── schemas/   # Zod validators
│   └── package.json
├── backend/           # FastAPI
│   ├── app/
│   │   ├── main.py    # App entry point
│   │   ├── routers/   # API routes
│   │   ├── services/  # Business logic
│   │   ├── schemas.py # Pydantic models
│   │   └── backtest/  # Backtesting engine
│   ├── requirements.txt
│   ├── Procfile       # Railway config
│   └── pytest.ini
└── README.md
```

## Roadmap

- [ ] User auth (Phase 2)
- [ ] Portfolio sync to broker APIs
- [ ] Real-time notifications
- [ ] Mobile app (React Native)
- [ ] Global markets (Japan, EU, emerging)
- [ ] Crypto support

## License

MIT
