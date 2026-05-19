import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const EXECUTION_API_TARGET = "http://143.110.148.234:8000";
const EXECUTION_WS_TARGET = "ws://143.110.148.234:8000";
const BACKTESTING_API_TARGET = "http://143.110.148.234:8200";

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
        ws: true,
        rewrite: (path) => path.replace(/^\/exec-api/, "/api"),
      },
      "/exec-api": {
        target: EXECUTION_API_TARGET,
        rewrite: (path) => path.replace(/^\/exec-api/, "/api"),
      },
      // Backtesting API — local dev matches production and uses the remote main DB.
      "/bt-api": {
        target: BACKTESTING_API_TARGET,
        rewrite: (path) => path.replace(/^\/bt-api/, "/api"),
      },
    },
  },
});
