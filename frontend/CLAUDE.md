# Frontend Dashboard

React + TypeScript dashboard for viewing backtest results and optimization sweeps from the Python backtester.

## Commands

```bash
npm install
npm run dev       # Dev server on :5173 (proxies /api to :8000)
npm run build     # Type-check + bundle to dist/
npm run lint
```

## Stack

- **React 19** + TypeScript (strict mode)
- **Vite** (bundler, dev server, API proxy)
- **Tailwind CSS 4** (dark-only theme, utility classes)
- **Recharts** (equity curve charts)
- **Radix UI** (Dialog, ScrollArea — accessible primitives)
- **No router** — tab-based navigation (Backtests | Saved | Optimizations | Coverage)
- **No state manager** — React hooks only (useState, useEffect, custom hooks)

## Project Structure

```
src/
├── App.tsx                        # Tab routing: Backtests | Saved | Optimizations | Coverage
├── main.tsx                       # React DOM mount
├── index.css                      # Tailwind config + CSS theme variables
├── components/
│   ├── BacktestDashboard.tsx      # Main backtest view (sidebar + detail)
│   ├── OptimizeDashboard.tsx      # Main optimization view
│   ├── BacktestHistoryPanel.tsx   # Sidebar: saved backtest runs
│   ├── OptimizationHistoryPanel.tsx
│   ├── ConfigBar.tsx              # Displays config params per-session
│   ├── StatBar.tsx                # Metrics grid (Net R, Max DD, Win Rate, etc.)
│   ├── StatCard.tsx               # Reusable stat display with tooltip
│   ├── EquityChart.tsx            # Recharts equity curve + per-trade bars
│   ├── TradesTable.tsx            # Scrollable filled trades table
│   ├── BestResults.tsx            # Top 3 configs (by Sharpe, R, PF)
│   ├── Heatmap.tsx                # 1D/2D parameter sweep heatmap
│   ├── OptimizationTable.tsx      # Sortable/filterable results table
│   ├── SessionTag.tsx             # Colored badge (NY=blue, ASIA=red, LDN=gold)
│   ├── CoverageDashboard.tsx      # Per-instrument testing coverage + checklist
│   ├── Skeleton.tsx               # Loading placeholder
│   ├── ConfirmDeleteDialog.tsx    # Delete confirmation modal
│   └── ui/                        # Radix UI wrappers (dialog, scroll-area)
├── hooks/
│   ├── useBacktest.ts             # POST /api/backtest
│   ├── useBacktestHistory.ts      # GET /api/backtests (polls every 5s)
│   ├── useOptimize.ts             # POST /api/optimize
│   ├── useOptimizationHistory.ts  # GET /api/optimizations (polls every 5s)
│   └── useCoverage.ts             # GET /api/coverage + testing-plan CRUD (polls every 30s)
└── lib/
    ├── types.ts                   # TypeScript interfaces for all API data
    ├── utils.ts                   # Formatting helpers
    └── mockData.ts                # Mock data for testing
```

## API Integration

Proxied to Python FastAPI backend at `http://localhost:8000`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/backtest` | POST | Run a backtest |
| `/api/backtests` | GET | List saved backtests |
| `/api/backtests/{id}` | GET | Load full result |
| `/api/backtests/{id}` | DELETE | Delete result |
| `/api/optimize` | POST | Run optimization sweep |
| `/api/optimizations` | GET | List saved optimizations |
| `/api/optimizations/{id}` | GET | Load full optimization |
| `/api/optimizations/{id}` | DELETE | Delete optimization |
| `/api/coverage` | GET | Auto-derived stats per instrument |
| `/api/coverage/{inst}/params` | GET | Distinct param values tested |
| `/api/testing-plan` | GET/POST | List or create checklist items |
| `/api/testing-plan/{id}` | PUT/DELETE | Update or delete checklist item |

## Theme

Dark-only. Custom CSS variables in `index.css`:
- Fonts: Sora (display), JetBrains Mono (data/code)
- Colors: `--color-profit` (green), `--color-loss` (red), `--color-accent` (purple)
- Backgrounds: `--color-bg-primary` (#111113) through `--color-bg-card-hover` (#242429)

## Key Patterns

- **History panels** poll the API every 5 seconds for live refresh
- **EquityChart** thins data to ~300 points for rendering performance
- **Heatmap** supports 5 zoom levels and metric switching (Sharpe, Net R, PF, Win Rate, Avg R, Max DD)
- **OptimizationTable** has column sorting + numeric filters with >= / <= toggle
- **TradesTable** shows only filled trades, sorted newest-first
- **CoverageDashboard** shows instrument cards with auto-derived stats + manual testing checklist (polls every 30s)
