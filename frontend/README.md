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

- `/bt-api/*` -> backtesting API through Vite/Vercel/Nginx
- `/exec-api/*` -> execution API through Vite/Vercel/Nginx
- `/exec-api/ws` -> execution WebSocket

`bash ../start-dev.sh` starts the local backtesting API and points `/bt-api/*` at it by default. Use
`USE_REMOTE_BACKTESTING=1 bash ../start-dev.sh` when you intentionally want the local frontend to read
from the deployed backtesting API.

For deployed HTTPS frontends, use a real `wss://` backend URL such as `wss://143.110.148.234.nip.io/exec-api/ws`.
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
