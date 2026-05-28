import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const EXECUTION_API_TARGET = process.env.EXECUTION_API_TARGET ?? "https://143.110.148.234.nip.io";
const EXECUTION_WS_TARGET = process.env.EXECUTION_WS_TARGET ?? "wss://143.110.148.234.nip.io";
const BACKTESTING_API_TARGET = process.env.BACKTESTING_API_TARGET ?? "https://143.110.148.234.nip.io";

function isLoopbackTarget(target: string) {
  try {
    const { hostname } = new URL(target);
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0" || hostname === "::1";
  } catch {
    return false;
  }
}

function rewritePrefixedApiPath(prefix: string, target: string) {
  return isLoopbackTarget(target)
    ? (requestPath: string) => requestPath.replace(new RegExp(`^${prefix}`), "/api")
    : undefined;
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Execution API — WebSocket must come before HTTP catch-all
      "/exec-api/ws": {
        target: EXECUTION_WS_TARGET,
        changeOrigin: true,
        secure: true,
        ws: true,
        rewrite: rewritePrefixedApiPath("/exec-api", EXECUTION_WS_TARGET),
      },
      "/exec-api": {
        target: EXECUTION_API_TARGET,
        changeOrigin: true,
        secure: true,
        rewrite: rewritePrefixedApiPath("/exec-api", EXECUTION_API_TARGET),
      },
      // Backtesting API — use the configured target; local targets need the /bt-api -> /api rewrite.
      "/bt-api": {
        target: BACKTESTING_API_TARGET,
        changeOrigin: true,
        secure: true,
        rewrite: rewritePrefixedApiPath("/bt-api", BACKTESTING_API_TARGET),
      },
    },
  },
});
