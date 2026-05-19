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

- `/bt-api/*` -> remote backtesting API at `http://143.110.148.234:8200/api/*`
- `/exec-api/*` -> execution API at `http://143.110.148.234:8000/api/*`
- `/exec-api/ws` -> execution WebSocket

Local dev intentionally uses the same remote APIs as production so dashboard state comes from the remote main DB.

For deployed HTTPS frontends, set `VITE_EXEC_WS_URL` to a real `wss://` backend URL such as `wss://api.example.com/api/ws`.
Vercel rewrites work for REST, but the live dashboard WebSocket needs an HTTPS/WSS reverse proxy in front of the droplet.

## Layout

```
src/
├── App.tsx          # top-level route split
├── backtesting/     # /bt-api hooks, research views, charts, types
├── execution/       # /exec-api hooks, live views, WebSocket, types
├── shared/          # reusable UI primitives
└── index.css        # theme tokens
```
