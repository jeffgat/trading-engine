# Agent Instructions

This `AGENTS.md` file is the canonical instruction file for frontend work. `CLAUDE.md` is only a compatibility pointer for Anthropic tooling.

React dashboard for research and execution. Use React 19, Vite 7, TypeScript, Tailwind CSS 4, React Router, Recharts, lightweight-charts, Radix/local shared UI, and Lucide icons.

Commands:

```bash
npm install
npm run dev
npm run build
npm run lint
```

Keep backtesting and execution types separate in their local `lib/types.ts`. Shared primitives belong in `src/shared/ui`; feature composition stays in `src/backtesting/components` or `src/execution/components`.

Use frontend API prefixes and let Vite rewrite them:

- `/bt-api/*` -> remote backtesting API backed by the remote main DB
- `/exec-api/*` and `/exec-api/ws` -> execution API/WebSocket

Routes: `/` is research/backtesting; `/execution` is live execution. Local dev should use the same remote APIs as production unless a task explicitly asks for an isolated local backend.
