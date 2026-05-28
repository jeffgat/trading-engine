import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

const EXECUTION_API_TARGET = process.env.EXECUTION_API_TARGET ?? "https://143.110.148.234.nip.io";
const EXECUTION_WS_TARGET = process.env.EXECUTION_WS_TARGET ?? "wss://143.110.148.234.nip.io";
const BACKTESTING_API_TARGET = process.env.BACKTESTING_API_TARGET ?? "https://143.110.148.234.nip.io";

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
      },
      "/exec-api": {
        target: EXECUTION_API_TARGET,
      },
      // Backtesting API — local dev matches production and uses the remote main DB.
      "/bt-api": {
        target: BACKTESTING_API_TARGET,
      },
    },
  },
});
