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
      "/api/ws": {
        target: "ws://143.110.148.234:8000",
        ws: true,
      },
      "/api": {
        target: "http://143.110.148.234:8000",
      },
    },
  },
});
