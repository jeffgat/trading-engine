import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

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
        target: "ws://143.110.148.234:8000",
        ws: true,
        rewrite: (path) => path.replace(/^\/exec-api/, "/api"),
      },
      "/exec-api": {
        target: "http://143.110.148.234:8000",
        rewrite: (path) => path.replace(/^\/exec-api/, "/api"),
      },
      // Backtesting API — serve through the local FastAPI app.
      // The app persists/query state through the remote main DB by default,
      // while compute endpoints like backtest/optimize can still use local data.
      "/bt-api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/bt-api/, "/api"),
      },
    },
  },
});
