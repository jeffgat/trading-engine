# Frontend Dashboard

React + TypeScript dashboard for research and execution.

## Commands

```bash
npm install
npm run dev       # http://localhost:5173
npm run build
npm run lint
```

## Routes

- `/` — backtesting dashboard
- `/execution` — live execution dashboard

## Proxies

- `/bt-api/*` -> local backtesting API at `http://localhost:8000/api/*`
- `/exec-api/*` -> execution API at `http://143.110.148.234:8000/api/*`
- `/exec-api/ws` -> execution WebSocket

Start the local backtesting API before using compute-heavy research views:

```bash
cd ../backtesting
uv run python scripts/run_server.py
```

## Layout

```
src/
├── App.tsx          # top-level route split
├── backtesting/     # /bt-api hooks, research views, charts, types
├── execution/       # /exec-api hooks, live views, WebSocket, types
├── shared/          # reusable UI primitives
└── index.css        # theme tokens
```
